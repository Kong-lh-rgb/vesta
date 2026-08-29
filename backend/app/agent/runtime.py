"""Agent 的公开运行生命周期、恢复边界与流式入口。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import suppress
from typing import Any
from uuid import uuid4

from app.checkpoint import (
    RunCheckpoint,
    SQLiteCheckpointStore,
)
from app.context import ContextManager, ConversationSummaryState
from app.memory import (
    MemoryMaintenanceReflector,
    MemoryManager,
    PostRunMemoryReflector,
)
from app.models.registry import ModelAdapterRegistry
from app.models.types import (
    AgentMode,
    Message,
    MessageRole,
    ModelProvider,
)
from app.skills import (
    SkillContextProvider,
    SkillStore,
)
from app.task.context import TaskContextProvider
from app.tools.approval import ApprovalGate
from app.tools.executor import ToolExecutor
from app.tools.hooks import ToolHook
from app.tools.observability import ToolExecutionRecord
from app.tools.output import ToolOutputRecorder
from app.tools.permissions.policy import PermissionPolicyEngine
from app.tools.permissions.store import PermissionRuleStore
from app.tools.registry import ToolRegistry

from .budget import (
    RunBudget,
    RunBudgetConfig,
)
from .event_stream import (
    STREAM_FINISHED as _STREAM_FINISHED,
)
from .event_stream import (
    EventEmitter as _EventEmitter,
)
from .event_stream import (
    QueueEventHandler as _QueueEventHandler,
)
from .events import (
    AgentEvent,
    AgentEventHandler,
    AgentEventType,
    CompositeEventHandler,
    NullEventHandler,
)
from .loop import AgentLoop
from .memory_post_run import PostRunMemoryCoordinator
from .result import (
    AgentResult,
)


class AgentRuntime:
    """运行模型，直到返回最终消息或循环必须停止。"""

    def __init__(
        self,
        model_registry: ModelAdapterRegistry,
        tool_registry: ToolRegistry,
        *,
        provider: ModelProvider | str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        max_steps: int = 12,
        max_tool_rounds: int | None = None,
        max_output_tokens: int | None = None,
        tool_executor: ToolExecutor | None = None,
        tool_hooks: Sequence[ToolHook] = (),
        approval_gate: ApprovalGate | None = None,
        policy_engine: PermissionPolicyEngine | None = None,
        rule_store: PermissionRuleStore | None = None,
        context_manager: ContextManager | None = None,
        task_context_provider: TaskContextProvider | None = None,
        checkpoint_store: SQLiteCheckpointStore | None = None,
        memory_manager: MemoryManager | None = None,
        memory_reflector: PostRunMemoryReflector | None = None,
        memory_maintenance_reflector: MemoryMaintenanceReflector | None = None,
        skill_store: SkillStore | None = None,
        skill_context_provider: SkillContextProvider | None = None,
        tool_output_recorder: ToolOutputRecorder | None = None,
        post_run_submit: Callable[[Callable[[], Any]], bool] | None = None,
        run_budget_config: RunBudgetConfig | None = None,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        if max_output_tokens is not None and max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1")
        if max_tool_rounds is not None and max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be at least 1")
        if system_prompt is not None and not isinstance(system_prompt, str):
            raise TypeError("system_prompt must be a string or None")
        if memory_reflector is not None and memory_manager is None:
            raise ValueError("memory_reflector requires memory_manager")
        if memory_maintenance_reflector is not None and memory_manager is None:
            raise ValueError("memory_maintenance_reflector requires memory_manager")
        if skill_context_provider is not None and skill_store is None:
            raise ValueError("skill_context_provider requires skill_store")

        self._system_prompt = (
            system_prompt
            if system_prompt is not None and system_prompt.strip()
            else None
        )
        self._context_manager = context_manager or ContextManager()
        self._checkpoint_store = checkpoint_store
        self._post_run = PostRunMemoryCoordinator(
            manager=memory_manager,
            reflector=memory_reflector,
            maintenance_reflector=memory_maintenance_reflector,
            task_context_provider=task_context_provider,
            submit=post_run_submit,
        )
        self._run_budget = RunBudget(run_budget_config)
        self._tool_executor = tool_executor or ToolExecutor(
            tool_registry,
            approval_gate=approval_gate,
            policy_engine=policy_engine,
            rule_store=rule_store,
            hooks=tool_hooks,
            output_recorder=tool_output_recorder,
        )
        self._loop = AgentLoop(
            model_registry=model_registry,
            tool_registry=tool_registry,
            tool_executor=self._tool_executor,
            provider=provider,
            model=model,
            system_prompt=self._system_prompt,
            max_steps=max_steps,
            max_tool_rounds=max_tool_rounds,
            max_output_tokens=max_output_tokens,
            context_manager=self._context_manager,
            task_context_provider=task_context_provider,
            checkpoint_store=checkpoint_store,
            memory_manager=memory_manager,
            skill_store=skill_store,
            skill_context_provider=skill_context_provider,
            run_budget=self._run_budget,
        )

    @property
    def tool_executor(self) -> ToolExecutor:
        return self._tool_executor

    @property
    def tool_records(self) -> tuple[ToolExecutionRecord, ...]:
        """返回工具执行器当前累计保存的观测记录。"""
        return self._tool_executor.execution_records

    async def run(
        self,
        user_input: str,
        *,
        history: Sequence[Message] = (),
        conversation_id: str | None = None,
        event_handler: AgentEventHandler | None = None,
        summary_state: ConversationSummaryState | None = None,
        run_id: str | None = None,
        recovery_run_id: str | None = None,
        mode: AgentMode = AgentMode.NORMAL,
    ) -> AgentResult:
        """处理一次用户输入并返回完整的运行结果（AgentResult）。

        模型和工具运行时错误不会向外抛出，而是以结构化的
        ``AgentResult.error`` 与停止原因返回。

        ``run_id`` 可选：由调用方指定 Run ID（RunManager 用它把 Run 与
        Checkpoint / Trace 关联），缺省时内部生成。
        ``recovery_run_id`` 可选：显式指定要恢复的旧中断 Checkpoint（对应旧 Run）。
        只有显式传入 ``recovery_run_id`` 时本 Run 才会加载恢复证据；普通调用
        永远不隐式自动恢复 —— 恢复哪个 Run 的决定权属于 RunManager.recover()。
        ``mode`` 可选：一次执行的模式（NORMAL / PLAN），默认 NORMAL。
        """

        run_id = run_id or uuid4().hex
        emitter = _EventEmitter(
            handler=event_handler or NullEventHandler(),
            run_id=run_id,
            conversation_id=conversation_id,
        )
        try:
            recovery_checkpoint: RunCheckpoint | None = None
            if self._checkpoint_store is not None:
                if recovery_run_id is not None:
                    recovery_checkpoint = (
                        await self._checkpoint_store.get_unrecovered(
                            recovery_run_id
                        )
                    )
                await self._checkpoint_store.start(
                    run_id,
                    conversation_id=conversation_id,
                    user_message=Message(
                        role=MessageRole.USER,
                        content=user_input,
                    ),
                )
            try:
                result = await self._loop.run(
                    run_id,
                    user_input,
                    history=history,
                    conversation_id=conversation_id,
                    emitter=emitter,
                    summary_state=summary_state,
                    recovery_checkpoint=recovery_checkpoint,
                    mode=mode,
                )
            except BaseException as exc:
                if self._checkpoint_store is not None:
                    with suppress(Exception):
                        await self._checkpoint_store.interrupt(
                            run_id,
                            error=f"{type(exc).__name__}: {exc}",
                        )
                raise

            if self._checkpoint_store is not None:
                if result.ok:
                    await self._checkpoint_store.complete(
                        run_id,
                        stop_reason=result.stop_reason,
                    )
                    if recovery_checkpoint is not None:
                        with suppress(Exception):
                            await self._checkpoint_store.mark_recovered(
                                recovery_checkpoint.run_id,
                                recovered_by_run_id=run_id,
                            )
                else:
                    await self._checkpoint_store.fail(
                        run_id,
                        stop_reason=result.stop_reason,
                        error=(
                            result.error.message
                            if result.error is not None
                            else None
                        ),
                    )
            # Critical path 在 checkpoint + AGENT_COMPLETED/FAILED 处结束；
            # Memory Reflection 属于 post-run housekeeping，交给独立协调器，
            # 不再阻塞 Run completed / conversation.send。
            await emitter.emit(
                (
                    AgentEventType.AGENT_COMPLETED
                    if result.ok
                    else AgentEventType.AGENT_FAILED
                ),
                step=result.steps or None,
                message=result.final_message,
                usage=result.usage,
                stop_reason=result.stop_reason,
                error=result.error,
                result=result,
            )
            await self._post_run.schedule(
                result,
                user_input=user_input,
                conversation_id=conversation_id,
                emitter=emitter,
            )
            return result
        finally:
            with suppress(Exception):
                await self._tool_executor.clear_run_rules(run_id)

    async def run_stream(
        self,
        user_input: str,
        *,
        history: Sequence[Message] = (),
        conversation_id: str | None = None,
        event_handler: AgentEventHandler | None = None,
        summary_state: ConversationSummaryState | None = None,
        run_id: str | None = None,
        recovery_run_id: str | None = None,
        mode: AgentMode = AgentMode.NORMAL,
    ) -> AsyncIterator[AgentEvent]:
        """以事件流方式执行任务，内部复用同一个 ``run()`` 循环。"""

        queue_handler = _QueueEventHandler()
        handler: AgentEventHandler = queue_handler
        if event_handler is not None:
            handler = CompositeEventHandler(queue_handler, event_handler)

        async def execute() -> None:
            try:
                await self.run(
                    user_input,
                    history=history,
                    conversation_id=conversation_id,
                    event_handler=handler,
                    summary_state=summary_state,
                    run_id=run_id,
                    recovery_run_id=recovery_run_id,
                    mode=mode,
                )
            finally:
                await queue_handler.finish()

        task = asyncio.create_task(execute())
        try:
            while True:
                item = await queue_handler.next()
                if item is _STREAM_FINISHED:
                    break
                if isinstance(item, AgentEvent):
                    yield item
            await task
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
