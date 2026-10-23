"""ConversationService：统一的 Conversation 输入执行链。

职责：把“一条输入投递到某个 Conversation”完整执行到底，并统一接入 Trace：

    load 最新持久化 history
      → load Conversation Summary
      → RunManager.start()
      → 等待 Run 完成（含 Trace handler 注入）
      → 获取 AgentResult
      → 把完整 Conversation history 写回 ConversationStore
      → 保存最新 Summary
      → 返回 DispatchResult(run, result, trigger)

CLI、Automation、未来 API / Desktop 都通过它执行，不再各自维护一套
load→start→wait→save 逻辑。本 Service 不包含任何 CLI print/input 逻辑。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.agent.event_stream import EventEmitter
from app.agent.events import (
    AgentEventHandler,
    AgentEventType,
    CompositeEventHandler,
)
from app.agent.result import AgentResult, AgentStopReason
from app.models.types import AgentMode, Message, MessageRole
from app.run.models import RunStatus
from app.trace import SQLiteTraceEventHandler, SQLiteTraceStore

from .coordinator import ConversationOperationCoordinator
from .inputs import ConversationSource, TriggerContext
from .store import SQLiteConversationStore

if TYPE_CHECKING:  # 避免 app.context ↔ app.conversation 循环导入
    from app.context import (
        ConversationSummaryState,
        SQLiteConversationSummaryStore,
    )
    from app.run import Run, RunManager

logger = logging.getLogger("vesta.conversation.service")


@dataclass
class DispatchResult:
    """一次 Conversation 输入投递的完整结果。"""

    run: Run
    result: AgentResult
    trigger: TriggerContext
    conversation_id: str | None


class ConversationService:
    """统一执行一次 Conversation 输入（手动 / Automation 同路径）。

    同一 conversation 的 dispatch 按会话串行（per-conversation asyncio.Lock），
    避免两个 Run 同时 load history 后互相 replace_messages 导致消息丢失；
    不同 conversation 仍可并行。
    """

    def __init__(
        self,
        conversation_store: SQLiteConversationStore,
        run_manager: RunManager,
        trace_store: SQLiteTraceStore,
        *,
        summary_store: SQLiteConversationSummaryStore | None = None,
        shared_event_handler: AgentEventHandler | None = None,
        operation_coordinator: ConversationOperationCoordinator | None = None,
    ) -> None:
        self._conversation_store = conversation_store
        self._run_manager = run_manager
        self._trace_store = trace_store
        self._summary_store = summary_store
        # 全局共享观察者（如 Desktop WebSocket 广播）：始终与 Trace 一起组合，
        # 手动 / Automation 触发的 Run 最终都进入同一条 broadcast path。
        self._shared_event_handler = shared_event_handler
        self.operation_coordinator = (
            operation_coordinator or ConversationOperationCoordinator()
        )

    async def dispatch(
        self,
        *,
        conversation_id: str | None,
        content: str,
        trigger: TriggerContext | None = None,
        event_handler: AgentEventHandler | None = None,
        on_run_started: Any | None = None,
        mode: AgentMode = AgentMode.NORMAL,
    ) -> DispatchResult:
        """投递一条输入并完整执行（加载最新 → Run → 写回 → Summary）。

        ``event_handler`` 是可选的额外观察者（如 CLI 打印）；Trace 总是由本
        Service 统一注入，Automation 与手动输入走同一条 Trace 路径。

        ``on_run_started`` 可选：Run 创建并拿到 run_id 后、等待完成前被调用
        （``await on_run_started(run_id)``）。Automation 用它立即持久化
        last_run_id —— Run 已启动即记录，崩溃后不会重复补跑。

        ``mode`` 可选：本次执行的模式（NORMAL / PLAN），默认 NORMAL。
        """

        trigger = trigger or TriggerContext(
            source=ConversationSource.MANUAL
        )
        async with self.operation_coordinator.execution(conversation_id):
            return await self._dispatch_locked(
                conversation_id=conversation_id,
                content=content,
                trigger=trigger,
                event_handler=event_handler,
                on_run_started=on_run_started,
                mode=mode,
            )

    async def _dispatch_locked(
        self,
        *,
        conversation_id: str | None,
        content: str,
        trigger: TriggerContext,
        event_handler: AgentEventHandler | None,
        on_run_started: Any | None,
        mode: AgentMode,
    ) -> DispatchResult:
        # 1) 从持久化源加载“触发那一刻最新”的 history / summary。
        history, summary_state = await self._load_history_and_summary(
            conversation_id
        )

        # 2) 统一注入 Trace handler（+ 全局共享观察者 + 本次额外观察者）。
        handler = self._compose_handler(event_handler)

        # 3) 启动 Run（携带 provenance + mode）并等待完成。
        run_id, _ = await self._run_manager.start(
            content,
            conversation_id=conversation_id,
            history=history,
            summary_state=summary_state,
            event_handler=handler,
            source=trigger.source.value,
            source_id=trigger.automation_id,
            scheduled_for=trigger.scheduled_for,
            triggered_at=trigger.triggered_at,
            mode=mode,
        )
        if on_run_started is not None:
            await on_run_started(run_id)
        run = await self._wait_for_run(run_id)
        result = await self._resolve_terminal_result(
            run=run,
            conversation_id=conversation_id,
            handler=handler,
            history=history,
            user_content=content,
        )

        # 4) 把新的完整 history 写回 ConversationStore（保存最新 Summary）。
        await self._write_back(conversation_id, result)

        return DispatchResult(
            run=run,
            result=result,
            trigger=trigger,
            conversation_id=conversation_id,
        )

    async def recover(
        self,
        run_id: str,
        *,
        trigger: TriggerContext | None = None,
        event_handler: AgentEventHandler | None = None,
        on_run_started: Any | None = None,
    ) -> DispatchResult:
        """恢复一个 INTERRUPTED Run，并像 dispatch 一样完整收口。

        CLI 与 RPC 的 recover 都收敛到这里，不再各自维护一条
        load→recover→wait→写回 的链路：

            load 最新持久化 history / summary
            → RunManager.recover()（生命周期只归 RunManager）
            → 等待恢复后的 Run 完成（含 Trace handler 注入）
            → 获取 AgentResult
            → 把最终 messages 写回 ConversationStore
            → 保存最新 Summary
            → 返回 DispatchResult

        recover 语义保持：旧 Run 保持 INTERRUPTED；新 Run 的
        recovered_from_run_id 指向旧 Run（由 RunManager 负责）。
        """

        run = await self._run_manager.get_run(run_id)
        if run is None:
            raise KeyError(f"Run 不存在：{run_id}")
        conversation_id = run.conversation_id
        trigger = trigger or TriggerContext(source=ConversationSource.MANUAL)
        async with self.operation_coordinator.execution(conversation_id):
            return await self._recover_locked(
                run_id=run_id,
                conversation_id=conversation_id,
                trigger=trigger,
                event_handler=event_handler,
                on_run_started=on_run_started,
            )

    async def _recover_locked(
        self,
        *,
        run_id: str,
        conversation_id: str | None,
        trigger: TriggerContext,
        event_handler: AgentEventHandler | None,
        on_run_started: Any | None,
    ) -> DispatchResult:
        # 1) 从持久化源加载最新 history / summary（与 dispatch 一致）。
        history, summary_state = await self._load_history_and_summary(
            conversation_id
        )

        # 2) 统一注入 Trace handler（+ 全局共享观察者 + 本次额外观察者）。
        handler = self._compose_handler(event_handler)

        # 3) 由 RunManager 启动恢复后的新 Run 并等待完成。
        new_run_id, _ = await self._run_manager.recover(
            run_id,
            history=history,
            summary_state=summary_state,
            event_handler=handler,
        )
        if on_run_started is not None:
            await on_run_started(new_run_id)
        recovered_run = await self._wait_for_run(new_run_id)
        # 恢复 Run 的 user 消息在旧 Run dispatch 时已落库（history 已包含），
        # 合成取消 / 中断终态时不重复插入。
        result = await self._resolve_terminal_result(
            run=recovered_run,
            conversation_id=conversation_id,
            handler=handler,
            history=history,
            user_content=None,
        )

        # 4) 把恢复后的完整 history 写回 ConversationStore（保存最新 Summary）。
        await self._write_back(conversation_id, result)

        return DispatchResult(
            run=recovered_run,
            result=result,
            trigger=trigger,
            conversation_id=conversation_id,
        )

    async def _load_history_and_summary(
        self,
        conversation_id: str | None,
    ) -> tuple[tuple[Message, ...], ConversationSummaryState | None]:
        """从持久化源加载最新 history / summary（dispatch 与 recover 共用）。"""

        history: tuple[Message, ...] = ()
        if conversation_id is not None:
            history = tuple(
                await self._conversation_store.load_messages(conversation_id)
            )
        summary_state = (
            await self._summary_store.load(conversation_id)
            if self._summary_store is not None and conversation_id is not None
            else None
        )
        return history, summary_state

    def _compose_handler(
        self,
        event_handler: AgentEventHandler | None,
    ) -> AgentEventHandler:
        """统一注入 Trace handler（+ 全局共享观察者 + 本次额外观察者）。"""

        trace_handler = SQLiteTraceEventHandler(self._trace_store)
        handlers: list[AgentEventHandler] = [trace_handler]
        if self._shared_event_handler is not None:
            handlers.append(self._shared_event_handler)
        if event_handler is not None:
            handlers.append(event_handler)
        return (
            CompositeEventHandler(*handlers)
            if len(handlers) > 1
            else handlers[0]
        )

    async def _wait_for_run(self, run_id: str) -> Any:
        """等待 Run 完成；用户 Ctrl+C 时先取消 Run（不残留 task）再传播。"""

        try:
            return await self._run_manager.wait(run_id)
        except KeyboardInterrupt:
            try:
                await self._run_manager.cancel(run_id)
            except (ValueError, KeyError):
                pass
            raise

    async def _resolve_terminal_result(
        self,
        *,
        run: Any,
        conversation_id: str | None,
        handler: AgentEventHandler,
        history: tuple[Message, ...],
        user_content: str | None,
    ) -> AgentResult:
        """取回 AgentResult；Run 被取消 / 中断时合成终态结果。

        取消 / 中断的 Run 不会产生 AgentResult：不合成的话 user 消息与
        中断说明无法落库，前端还会一直卡在运行态。dispatch 与 recover
        共用本收口，避免两条链路行为分叉。

        终态事件同样经过 EventEmitter 分配序号：序号从 TraceStore 已
        持久化的最大序号继续，避免与 agent_started(sequence=0) 冲突
        被 UNIQUE(run_id, sequence) 的 INSERT OR IGNORE 静默丢弃。

        ``user_content``：dispatch 传入本次输入，合成 history 需要补上
        user 消息；recover 的 user 消息已在旧 Run 时落库，传 None。
        """

        run_id = run.id
        result = self._run_manager.result(run_id)
        if result is not None:
            return result
        emitter = EventEmitter(
            handler=handler,
            run_id=run_id,
            conversation_id=conversation_id,
            sequence_offset=await self._trace_store.next_sequence(run_id),
        )
        user_messages = (
            (Message(role=MessageRole.USER, content=user_content),)
            if user_content is not None
            else ()
        )
        if run.status is RunStatus.CANCELLED:
            cancelled_message = Message(
                role=MessageRole.ASSISTANT,
                content=(
                    "Run cancelled：已停止，未生成最终回复。"
                    "（本轮未完成的内容不会显示）"
                ),
            )
            cancelled_result = AgentResult(
                run_id=run_id,
                final_message=cancelled_message,
                messages=(*history, *user_messages, cancelled_message),
                steps=0,
                stop_reason=AgentStopReason.CANCELLED,
            )
            await emitter.emit(
                AgentEventType.AGENT_CANCELLED,
                message=cancelled_message,
                stop_reason=AgentStopReason.CANCELLED,
                result=cancelled_result,
            )
            return cancelled_result
        if run.status is RunStatus.INTERRUPTED:
            # 暂停（中断）：合成 INTERRUPTED 终态结果并 emit agent_failed
            # (stop_reason=interrupted)，前端进入 interrupted 终态并展示
            # “Recover/继续”入口，用户可从 Checkpoint 断点恢复执行。
            interrupted_message = Message(
                role=MessageRole.ASSISTANT,
                content=(
                    "Run interrupted：已暂停，可从断点继续。"
                    "（点击 Recover 从保存的中断点恢复）"
                ),
            )
            interrupted_result = AgentResult(
                run_id=run_id,
                final_message=interrupted_message,
                messages=(*history, *user_messages, interrupted_message),
                steps=0,
                stop_reason=AgentStopReason.INTERRUPTED,
            )
            await emitter.emit(
                AgentEventType.AGENT_FAILED,
                message=interrupted_message,
                stop_reason=AgentStopReason.INTERRUPTED,
                result=interrupted_result,
            )
            return interrupted_result
        raise RuntimeError("RunManager 未返回最终 AgentResult")

    async def _write_back(
        self,
        conversation_id: str | None,
        result: AgentResult,
    ) -> None:
        """把完整 history 写回 ConversationStore（保存最新 Summary）。"""

        if conversation_id is not None:
            await self._conversation_store.replace_messages(
                conversation_id,
                result.messages,
            )
        if (
            self._summary_store is not None
            and conversation_id is not None
            and result.summary_state is not None
        ):
            await self._summary_store.save(
                conversation_id,
                result.summary_state,
            )

    async def is_run_running(self, run_id: str) -> bool:
        """供 Scheduler 做 max_instances 检查（只读 Run 生命周期查询）。"""

        run = await self._run_manager.get_run(run_id)
        return run is not None and run.status is RunStatus.RUNNING


__all__ = ["ConversationService", "DispatchResult"]
