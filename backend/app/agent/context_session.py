"""单次 Agent Run 的临时上下文来源与 Skill 激活状态。"""

from __future__ import annotations

from dataclasses import dataclass

from app.checkpoint import RunCheckpoint, render_checkpoint_context
from app.memory import MemoryManager
from app.models.types import Message, ToolResult
from app.skills import Skill, SkillContextProvider, SkillMetadata, SkillStore
from app.task.context import TaskContextProvider

from .event_stream import EventEmitter
from .events import AgentEventType
from .runtime_helpers import skill_read_outcome


@dataclass(frozen=True, slots=True)
class RuntimeContextInjection:
    """一次模型请求需要插入的临时消息与 Skill 观测字段。"""

    messages: tuple[Message, ...]
    available_skill_count: int | None
    skill_catalog_tokens: int | None
    active_skill_names: tuple[str, ...]
    active_skill_tokens: int | None
    active_skill_message_names: tuple[str, ...]


class RuntimeContextSession:
    """缓存 Run 级上下文，并在每个 Step 重新读取可变 Task 状态。"""

    def __init__(
        self,
        *,
        memory_manager: MemoryManager | None,
        skill_store: SkillStore | None,
        skill_context_provider: SkillContextProvider | None,
        task_context_provider: TaskContextProvider | None,
    ) -> None:
        self._memory_manager = memory_manager
        self._skill_store = skill_store
        self._skill_context_provider = skill_context_provider
        self._task_context_provider = task_context_provider
        self._memory_messages: tuple[Message, ...] = ()
        self._memory_loaded = False
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
                self._memory_messages = (
                    await self._memory_manager.context_messages()
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
        )

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


__all__ = ["RuntimeContextInjection", "RuntimeContextSession"]
