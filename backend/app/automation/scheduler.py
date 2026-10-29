"""AutomationScheduler：到时间向 Conversation 投递一条新的输入。

关键链路：

    Automation
        ↓ 到时间（APScheduler DateTrigger）
    AutomationScheduler
        ↓
    ConversationService.dispatch(conversation_id, content, trigger)
        ↓
    RunManager
        ↓
    AgentRuntime

Scheduler 不负责执行 Agent，也不负责 load history / load summary / 写回
Conversation / 处理 Trace —— 这些统一由 ConversationService 完成。
Scheduler 只关心：到时间 → 投递一条 Conversation Input → 拿到 run_id →
更新 Automation 生命周期。

V1 调度模型：每个 ACTIVE Automation 注册一个"下次触发"的一次性
``DateTrigger`` job；每次触发后计算下一次触发时间并注册下一个一次性 job。
"""

from __future__ import annotations

import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.conversation import ConversationSource, TriggerContext
from app.conversation.service import ConversationService

from .models import Automation, AutomationStatus, Schedule, ScheduleKind
from .store import SQLiteAutomationStore

logger = logging.getLogger("vesta.automation.scheduler")

_JOB_PREFIX = "automation-"
# ONCE 型触发失败（Run 尚未启动）后的重试间隔：可见于日志，用户可 cancel。
_FAILURE_RETRY_SECONDS = 300.0


class AutomationScheduler:
    """Automation 生命周期与到点投递（同时充当 Agent 工具的领域门面）。"""

    def __init__(
        self,
        store: SQLiteAutomationStore,
        conversation_service: ConversationService,
        *,
        timezone: str = "UTC",
    ) -> None:
        self._store = store
        self._conversation_service = conversation_service
        self._timezone = ZoneInfo(timezone)
        self._scheduler = AsyncIOScheduler(
            timezone=self._timezone,
            # misfire_grace_time=None：到点 job 不因事件循环瞬时阻塞
            # （大 trace 同步解析等）被判 MISSED 丢弃——默认 1 秒宽限
            # 会让 Automation 静默失联。coalesce 只补跑一次。
            job_defaults={
                "misfire_grace_time": None,
                "coalesce": True,
            },
        )
        self._job_ids: dict[str, str] = {}
        self._running: set[str] = set()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """建表并恢复所有 ACTIVE Automation（应用 misfire 规则）后启动调度器。"""

        await self._store.initialize()
        active = await self._store.list(status=AutomationStatus.ACTIVE)
        for automation in active:
            await self._restore(automation)
        self._scheduler.start()

    async def shutdown(self) -> None:
        """优雅关闭：不阻塞、不遗留后台 asyncio task。"""

        try:
            self._scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            logger.debug("automation scheduler already shut down", exc_info=True)
        self._running.clear()
        self._job_ids.clear()

    # ------------------------------------------------------------------
    # 领域操作（供 Agent 工具 / CLI 使用）
    # ------------------------------------------------------------------

    async def create_automation(
        self,
        *,
        title: str,
        prompt: str,
        conversation_id: str | None,
        schedule: Schedule,
        next_run_at: datetime,
    ) -> Automation:
        automation = await self._store.create(
            title=title,
            prompt=prompt,
            conversation_id=conversation_id,
            schedule=schedule,
            next_run_at=next_run_at,
        )
        self._schedule(automation, automation.next_run_at)
        return automation

    async def get(self, automation_id: str) -> Automation | None:
        return await self._store.get(automation_id)

    async def resolve(self, identifier: str) -> Automation | None:
        """按完整 ID 或唯一前缀查找。"""

        return await self._store.resolve(identifier)

    async def list(
        self,
        *,
        status: AutomationStatus | str | None = None,
        conversation_id: str | None = None,
        limit: int = 50,
    ) -> tuple[Automation, ...]:
        return await self._store.list(
            status=status,
            conversation_id=conversation_id,
            limit=limit,
        )

    async def cancel(self, automation_id: str) -> Automation:
        automation = await self._store.require(automation_id)
        if automation.status is AutomationStatus.CANCELLED:
            return automation
        updated = await self._store.update_status(
            automation_id,
            AutomationStatus.CANCELLED,
        )
        self._remove_job(automation_id)
        return updated

    async def delete_for_conversation(self, conversation_id: str) -> int:
        """撤销调度并删除会话关联的自动化，防止删除后再次触发。"""

        automations = await self._store.list_for_conversation(conversation_id)
        for automation in automations:
            self._remove_job(automation.id)
        return await self._store.delete_for_conversation(conversation_id)

    async def pause(self, automation_id: str) -> Automation:
        automation = await self._store.require(automation_id)
        if automation.status is not AutomationStatus.ACTIVE:
            raise ValueError(
                f"only active automation can be paused: {automation_id} "
                f"({automation.status.value})"
            )
        updated = await self._store.update_status(
            automation_id,
            AutomationStatus.PAUSED,
        )
        self._remove_job(automation_id)
        return updated

    async def resume(self, automation_id: str) -> Automation:
        automation = await self._store.require(automation_id)
        if automation.status is not AutomationStatus.PAUSED:
            raise ValueError(
                f"only paused automation can be resumed: {automation_id} "
                f"({automation.status.value})"
            )
        now = datetime.now(UTC)
        if automation.schedule.kind is ScheduleKind.ONCE:
            # 一次性任务创建后未执行被 pause → resume 后若已过期，立即补跑一次；
            # 一次性触发即 COMPLETED，因此 PAUSED 的一次性不会出现 last_run_id。
            next_run = automation.next_run_at or now
            if next_run < now:
                next_run = now
        else:
            next_run = self._next_future(automation, now)
        updated = await self._store.update_status(
            automation_id,
            AutomationStatus.ACTIVE,
            next_run_at=next_run,
        )
        self._schedule(updated, next_run)
        return updated

    # ------------------------------------------------------------------
    # 内部：恢复 / 调度
    # ------------------------------------------------------------------

    async def _restore(self, automation: Automation) -> None:
        """启动恢复：应用 misfire 规则后把 Automation 重新接入调度。"""

        now = datetime.now(UTC)
        if automation.schedule.kind is ScheduleKind.ONCE:
            expired = (
                automation.next_run_at is None
                or automation.next_run_at <= now
            )
            if not expired:
                self._schedule(automation, automation.next_run_at)
                return
            if automation.last_run_id is None:
                # 程序关闭期间错过的一次性任务：只补执行一次。
                refreshed = await self._store.set_next_run_at(
                    automation.id,
                    now,
                )
                self._schedule(refreshed, now)
            elif automation.status is not AutomationStatus.COMPLETED:
                # 已执行过 → 直接完成，不重复触发。触发失败路径可能已
                # 提前转入 COMPLETED：保持幂等，不重复转换。
                await self._store.update_status(
                    automation.id,
                    AutomationStatus.COMPLETED,
                )
            return

        # 重复任务：misfire 恢复 —— 不补跑所有错过次数，从未来最近触发点继续。
        next_run = self._next_future(automation, now)
        if automation.next_run_at is None or next_run != automation.next_run_at:
            refreshed = await self._store.set_next_run_at(automation.id, next_run)
            automation = refreshed
        self._schedule(automation, next_run)

    def _schedule(self, automation: Automation, run_at: datetime) -> None:
        """注册（或重排）下一个一次性触发 job。"""

        automation_key = automation.id
        if automation_key in self._job_ids:
            try:
                self._scheduler.reschedule_job(
                    self._job_ids[automation_key],
                    trigger=DateTrigger(run_at),
                )
                return
            except Exception:  # noqa: BLE001
                self._job_ids.pop(automation_key, None)
        job = self._scheduler.add_job(
            self._job_func(automation.id),
            trigger=DateTrigger(run_at),
            id=_JOB_PREFIX + automation.id,
            replace_existing=True,
        )
        self._job_ids[automation.id] = job.id

    def _remove_job(self, automation_id: str) -> None:
        job_id = self._job_ids.pop(automation_id, None)
        if job_id is None:
            return
        try:
            self._scheduler.remove_job(job_id)
        except Exception:  # noqa: BLE001
            pass

    def _job_func(self, automation_id: str) -> Any:
        async def _run() -> None:
            try:
                await self._trigger(automation_id)
            except Exception:  # noqa: BLE001
                # 单个 Automation 失败不能让整个 Scheduler 崩溃。
                logger.exception(
                    "automation trigger failed: %s",
                    automation_id,
                )

        return _run

    # ------------------------------------------------------------------
    # 触发
    # ------------------------------------------------------------------

    async def _trigger(self, automation_id: str) -> None:
        """到点触发：向 Conversation 投递一条输入并更新 Automation 生命周期。

        max_instances = 1：若该 Automation 上一次 Run 仍在执行，跳过本次触发
        （coalesce —— 直接把 next_run_at 推进到下一个未来触发点，不新建 Run）。
        """

        if automation_id in self._running:
            return
        automation = await self._store.get(automation_id)
        if automation is None or automation.status is not AutomationStatus.ACTIVE:
            return

        now = datetime.now(UTC)
        if automation.last_run_id is not None:
            if await self._conversation_service.is_run_running(
                automation.last_run_id
            ):
                # 上一次 Run 还在执行 → 跳过本次，仍以计划点为锚推进。
                anchor = automation.next_run_at or now
                next_run = self._next_future(automation, now, anchor=anchor)
                await self._store.mark_triggered(
                    automation_id,
                    last_run_id=automation.last_run_id,
                    last_run_at=automation.last_run_at or now,
                    next_run_at=next_run,
                )
                self._schedule(automation, next_run)
                return

        self._running.add(automation_id)
        try:
            dispatch = await self._conversation_service.dispatch(
                conversation_id=automation.conversation_id,
                content=automation.prompt,
                trigger=TriggerContext(
                    source=ConversationSource.AUTOMATION,
                    automation_id=automation.id,
                    scheduled_for=automation.next_run_at,
                    triggered_at=now,
                ),
                on_run_started=self._record_run_started(
                    automation_id,
                    triggered_at=now,
                ),
            )
            run_id = dispatch.run.id
            now = datetime.now(UTC)
            if automation.schedule.kind is ScheduleKind.ONCE:
                # 一次性任务：Run 已创建并记录 last_run_id，本次触发即进入
                # COMPLETED（保留 last_run_id 供查看 Run 结果；崩溃后也不会
                # 再被当作"从未执行"补跑）。
                await self._store.update_status(
                    automation_id,
                    AutomationStatus.COMPLETED,
                )
                self._remove_job(automation_id)
                return

            # 重复任务：仍 ACTIVE。以本次计划触发点为锚推进——interval
            # 周期不随 Run 实际耗时漂移（否则"每 2 小时"会变成
            # 2 小时 + 每次 Run 耗时，且逐次累积）。
            anchor = automation.next_run_at or now
            next_run = self._next_future(automation, now, anchor=anchor)
            await self._store.mark_triggered(
                automation_id,
                last_run_id=run_id,
                last_run_at=now,
                next_run_at=next_run,
            )
            self._schedule(automation, next_run)
        except Exception:
            # 触发失败不能让 Automation 失联：本次 job 已被消费移除，
            # 不重排就会停留 ACTIVE 却永不触发。
            logger.exception("automation trigger failed: %s", automation_id)
            with suppress(Exception):
                await self._reschedule_after_failure(automation_id)
        finally:
            self._running.discard(automation_id)

    async def _reschedule_after_failure(self, automation_id: str) -> None:
        """触发失败后的自愈重排（调用前已记录异常日志）。"""

        automation = await self._store.get(automation_id)
        if automation is None or automation.status is not AutomationStatus.ACTIVE:
            return
        now = datetime.now(UTC)
        if automation.schedule.kind is ScheduleKind.ONCE:
            if automation.last_run_id is not None:
                # Run 已启动过（dispatch 在启动后才失败）：按已触发完成，
                # 不重复投递一次性任务。
                await self._store.update_status(
                    automation_id,
                    AutomationStatus.COMPLETED,
                )
                self._remove_job(automation_id)
                return
            # Run 从未启动：稍后重试。本地单用户场景接受可见的周期重试
            # （日志 + 用户可 cancel），好过静默失联。
            retry_at = now + timedelta(seconds=_FAILURE_RETRY_SECONDS)
            refreshed = await self._store.set_next_run_at(automation_id, retry_at)
            self._schedule(refreshed, retry_at)
            return
        next_run = self._next_future(automation, now)
        refreshed = await self._store.set_next_run_at(automation_id, next_run)
        self._schedule(refreshed, next_run)

    def _record_run_started(
        self,
        automation_id: str,
        *,
        triggered_at: datetime,
    ) -> Any:
        """返回 on_run_started 回调：Run 创建后立刻持久化 last_run_id / last_run_at。

        关键：Run 一旦启动（即使未完成、进程随后崩溃），Automation 就已记录
        该 run —— 重启后不会把已启动的一次性 Automation 再当作"从未执行"补跑。
        """

        async def _record(run_id: str) -> None:
            await self._store.mark_triggered(
                automation_id,
                last_run_id=run_id,
                last_run_at=triggered_at,
                next_run_at=None,
            )

        return _record

    # ------------------------------------------------------------------
    # 时间计算
    # ------------------------------------------------------------------

    def _build_trigger(self, schedule: Schedule):
        tz = ZoneInfo(schedule.timezone)
        if schedule.kind is ScheduleKind.INTERVAL:
            return IntervalTrigger(
                seconds=schedule.interval_seconds,
                timezone=tz,
            )
        if schedule.kind is ScheduleKind.CRON:
            return CronTrigger.from_crontab(schedule.cron_expr, timezone=tz)
        return DateTrigger(schedule.run_at)

    def _next_future(
        self,
        automation: Automation,
        now: datetime,
        *,
        anchor: datetime | None = None,
    ) -> datetime:
        """计算下一次（未来）触发时间；错过点不会被批量补跑。

        ``anchor`` 是本次的计划触发点：INTERVAL 周期以它推进（与 Run 实际
        耗时无关）；缺省从 now 起算（创建 / 恢复 / 失败重排场景）。
        锚点推进的结果若仍落在过去（Run 超过周期），从 now 起算下一个
        未来点 —— 不批量补跑中间错过的触发。
        """

        schedule = automation.schedule
        timezone = ZoneInfo(schedule.timezone)
        trigger = self._build_trigger(schedule)
        local_now = now.astimezone(timezone)
        previous = anchor.astimezone(timezone) if anchor is not None else None
        next_local = trigger.get_next_fire_time(previous, local_now)
        if next_local is None or next_local <= local_now:
            next_local = trigger.get_next_fire_time(None, local_now)
        if next_local is None:
            raise ValueError(
                f"automation {automation.id} has no future trigger time"
            )
        return next_local.astimezone(UTC)


__all__ = ["AutomationScheduler"]
