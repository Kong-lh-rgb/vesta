"""单次 Agent Run 的临时上下文来源与 Skill 激活状态。"""

from __future__ import annotations

from dataclasses import dataclass

from app.checkpoint import RunCheckpoint, render_checkpoint_context
from app.memory import MemoryManager, MemoryRecallQueryInputs, MemoryRecallSnapshot
from app.models.types import Message, ToolResult
from app.skills import Skill, SkillContextProvider, SkillMetadata, SkillStore
from app.task.context import TaskContextProvider

from .event_stream import EventEmitter
from .events import AgentEventType
from .runtime_helpers import skill_read_outcome


@dataclass(frozen=True, slots=True)
class RuntimeContextInjection:
    """一次模型请求需要插入的临时消息与 Skill / Memory Recall 观测字段。"""

    messages: tuple[Message, ...]
    available_skill_count: int | None
    skill_catalog_tokens: int | None
    active_skill_names: tuple[str, ...]
    active_skill_tokens: int | None
    active_skill_message_names: tuple[str, ...]
    recall_candidate_ids: tuple[str, ...] = ()
    recall_mode: str | None = None


class RuntimeContextSession:
    """缓存 Run 级上下文，并在每个 Step 重新读取可变 Task 状态。

    Memory 自动召回遵循"每 Run 一次"：首次 ``build()`` 时用确定性
    Recall Query 检索并缓存快照，后续所有 Step 复用同一份 Recall Context，
    不重复检索，也不写入原始聊天历史或滚动摘要。
    """

    def __init__(
        self,
        *,
        memory_manager: MemoryManager | None,
        skill_store: SkillStore | None,
        skill_context_provider: SkillContextProvider | None,
        task_context_provider: TaskContextProvider | None,
        recall_query: MemoryRecallQueryInputs | None = None,
    ) -> None:
        self._memory_manager = memory_manager
        self._skill_store = skill_store
        self._skill_context_provider = skill_context_provider
        self._task_context_provider = task_context_provider
        self._recall_query = recall_query
        self._memory_messages: tuple[Message, ...] = ()
        self._memory_loaded = False
        self._recall_snapshot: MemoryRecallSnapshot | None = None
        self._catalog: tuple[SkillMetadata, ...] = ()
        self._catalog_loaded = False
        self._active_skills: dict[str, Skill] = {}

    @property
    def active_skill_names(self) -> tuple[str, ...]:
        return tuple(self._active_skills)

    async def build(
        self,
        *,
        conversation_id: str | None,
        recovery_checkpoint: RunCheckpoint | None,
        trailing_system_messages: tuple[Message, ...],
    ) -> RuntimeContextInjection:
        """按稳定顺序构建临时上下文，不写入原始聊天历史。"""

        messages: list[Message] = []
        if self._memory_manager is not None and not self._memory_loaded:
            self._memory_loaded = True
            try:
                self._memory_messages = await self._load_memory_messages(
                    conversation_id
                )
            except Exception:
                self._memory_messages = ()
        messages.extend(self._memory_messages)

        provider = self._skill_context_provider
        if provider is not None and self._skill_store is not None:
            if not self._catalog_loaded:
                self._catalog_loaded = True
                try:
                    self._catalog = await self._skill_store.catalog()
                except Exception:
                    self._catalog = ()
            catalog_message = provider.catalog_message(self._catalog)
            if catalog_message is not None:
                messages.append(catalog_message)

        injected_active_names: tuple[str, ...] = ()
        if provider is not None and self._active_skills:
            active_messages = provider.active_messages(
                tuple(self._active_skills.values())
            )
            if active_messages:
                injected_active_names = tuple(self._active_skills)
                messages.extend(active_messages)

        if recovery_checkpoint is not None:
            messages.append(render_checkpoint_context(recovery_checkpoint))
        if self._task_context_provider is not None:
            task_message = await self._task_context_provider.message_for(
                conversation_id
            )
            if task_message is not None:
                messages.append(task_message)
        messages.extend(trailing_system_messages)

        return RuntimeContextInjection(
            messages=tuple(messages),
            available_skill_count=(
                len(self._catalog) if provider is not None else None
            ),
            skill_catalog_tokens=(
                provider.catalog_tokens(self._catalog)
                if provider is not None
                else None
            ),
            active_skill_names=tuple(self._active_skills),
            active_skill_tokens=(
                provider.active_tokens(tuple(self._active_skills.values()))
                if provider is not None
                else None
            ),
            active_skill_message_names=injected_active_names,
            recall_candidate_ids=tuple(
                candidate.memory_id
                for candidate in (
                    self._recall_snapshot.candidates
                    if self._recall_snapshot is not None
                    else ()
                )
            ),
            recall_mode=(
                self._recall_snapshot.mode.value
                if self._recall_snapshot is not None
                else None
            ),
        )

    async def _load_memory_messages(
        self,
        conversation_id: str | None,
    ) -> tuple[Message, ...]:
        """加载 Memory 注入消息；Hybrid 可用时执行一次自动召回。

        Hybrid 模式注入 Core + 本 Run 的 Recall Candidates + Policy，
        不再注入完整 INDEX.md；召回失败或索引不可用时回退 Legacy 注入。
        检索结果缓存在 ``self._recall_snapshot``，所有 Step 复用。
        """

        manager = self._memory_manager
        if manager is None:
            return ()
        hybrid = bool(getattr(manager, "hybrid_recall_enabled", False))
        if not hybrid or self._recall_query is None:
            return await _legacy_context_messages(manager)
        try:
            query = await self._recall_query_with_task(conversation_id)
            snapshot = await manager.recall(query)
        except Exception:
            # 自动召回失败不能阻塞 Run：退回 Legacy INDEX 注入。
            return await _legacy_context_messages(manager)
        self._recall_snapshot = snapshot
        return await manager.context_messages(recall=snapshot)

    async def _recall_query_with_task(
        self,
        conversation_id: str | None,
    ) -> MemoryRecallQueryInputs:
        """补上活动 Task 标题与进行中步骤（确定性输入，不调用模型）。"""

        assert self._recall_query is not None
        task_title: str | None = None
        task_steps: tuple[str, ...] = ()
        provider = self._task_context_provider
        recall_fields = getattr(provider, "recall_fields_for", None)
        if callable(recall_fields):
            task_title, task_steps = await recall_fields(conversation_id)
        return self._recall_query.with_task(task_title, task_steps)

    async def activate_skill(
        self,
        result: ToolResult,
        *,
        emitter: EventEmitter,
        step: int,
    ) -> None:
        """把 skill_read 命中的 Skill 加入本 Run 的活动集合。"""

        provider = self._skill_context_provider
        if self._skill_store is None or provider is None:
            return
        skill_name, found = skill_read_outcome(result.output)
        if not skill_name:
            return
        if not found:
            await self._emit_activation_failed(
                emitter,
                step=step,
                skill_name=skill_name,
                error="skill not found",
            )
            return
        if skill_name in self._active_skills:
            return
        skill = await self._skill_store.load(skill_name)
        if skill is None:
            await self._emit_activation_failed(
                emitter,
                step=step,
                skill_name=skill_name,
                error="skill not found",
            )
            return
        if provider.would_exceed_budget(
            tuple(self._active_skills.values()),
            skill,
        ):
            await self._emit_activation_failed(
                emitter,
                step=step,
                skill_name=skill_name,
                error="active skill context budget exceeded",
            )
            return
        self._active_skills[skill.metadata.name] = skill
        await emitter.emit(
            AgentEventType.SKILL_ACTIVATED,
            step=step,
            skill_name=skill.metadata.name,
            skill_scope=skill.metadata.scope.value,
            active_skill_names=tuple(self._active_skills),
            active_skill_tokens=provider.active_tokens(
                tuple(self._active_skills.values())
            ),
        )

    @staticmethod
    async def _emit_activation_failed(
        emitter: EventEmitter,
        *,
        step: int,
        skill_name: str,
        error: str,
    ) -> None:
        await emitter.emit(
            AgentEventType.SKILL_ACTIVATION_FAILED,
            step=step,
            skill_name=skill_name,
            skill_error=error,
        )


async def _legacy_context_messages(manager: MemoryManager) -> tuple[Message, ...]:
    """兼容鸭子类型 Memory 门面：不加参数地调用 context_messages。"""

    return await manager.context_messages()


__all__ = ["RuntimeContextInjection", "RuntimeContextSession"]
