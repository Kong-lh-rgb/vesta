"""单个 Agent 工具轮的执行、能力校验与状态归并。"""

from __future__ import annotations

from dataclasses import dataclass

from app.checkpoint import SQLiteCheckpointStore
from app.models.types import AgentMode, Message, MessageRole, ToolCall, ToolResult
from app.skills import SKILL_READ_TOOL_NAME
from app.tools.catalog import TOOL_SEARCH_NAME, activated_tool_names
from app.tools.executor import ToolExecutor
from app.tools.hooks import ToolExecutionContext, ToolHook
from app.tools.registry import ToolRegistry

from .computer_guard import ComputerStagnationGuard
from .context_session import RuntimeContextSession
from .errors import RepeatedToolCallError
from .event_stream import EventEmitter
from .result import ToolCallRecord
from .runtime_helpers import (
    computer_verification_status,
    plan_task_id_from_output,
    tool_call_signature,
)


@dataclass(frozen=True, slots=True)
class ToolRoundOutcome:
    """工具轮产生的记录以及需要交还给 Agent Loop 的状态。"""

    records: tuple[ToolCallRecord, ...]
    result_messages: tuple[Message, ...]
    pending_activations: frozenset[str]
    previous_signature: str | None
    repeated_count: int
    computer_halted: bool
    computer_verification_pending: bool
    plan_task_created: bool
    plan_task_id: str | None
    repeated_error: RepeatedToolCallError | None = None


class ToolRoundExecutor:
    """执行一个模型响应中的全部结构化工具调用。"""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        executor: ToolExecutor,
        checkpoint_store: SQLiteCheckpointStore | None,
    ) -> None:
        self._registry = registry
        self._executor = executor
        self._checkpoint_store = checkpoint_store

    async def execute(
        self,
        tool_calls: tuple[ToolCall, ...],
        *,
        run_id: str,
        conversation_id: str | None,
        user_input: str,
        step: int,
        mode: AgentMode,
        round_index: int,
        closing_can_deliver: bool,
        activated_tools: set[str],
        context_session: RuntimeContextSession,
        computer_guard: ComputerStagnationGuard,
        computer_halted: bool,
        computer_verification_pending: bool,
        previous_signature: str | None,
        repeated_count: int,
        emitter: EventEmitter,
        hook: ToolHook,
    ) -> ToolRoundOutcome:
        """执行工具轮；重复调用错误也连同已完成的前序记录返回。"""

        records: list[ToolCallRecord] = []
        result_messages: list[Message] = []
        pending_activations: set[str] = set()
        plan_task_created = False
        plan_task_id: str | None = None

        if self._checkpoint_store is not None:
            await self._checkpoint_store.before_tools(
                run_id,
                step=step,
                tool_calls=tool_calls,
            )

        for tool_call in tool_calls:
            signature = tool_call_signature(tool_call)
            if signature == previous_signature:
                repeated_count += 1
            else:
                previous_signature = signature
                repeated_count = 1
            if repeated_count >= 3:
                return ToolRoundOutcome(
                    records=tuple(records),
                    result_messages=tuple(result_messages),
                    pending_activations=frozenset(pending_activations),
                    previous_signature=previous_signature,
                    repeated_count=repeated_count,
                    computer_halted=computer_halted,
                    computer_verification_pending=computer_verification_pending,
                    plan_task_created=plan_task_created,
                    plan_task_id=plan_task_id,
                    repeated_error=RepeatedToolCallError(tool_call.name),
                )

            context = ToolExecutionContext(
                run_id=run_id,
                conversation_id=conversation_id,
                user_input=user_input,
                step=step,
                tool_call=tool_call,
                metadata={
                    "active_skill_names": context_session.active_skill_names
                },
                mode=mode,
            )
            result = await self._execute_one(
                tool_call,
                context=context,
                hook=hook,
                mode=mode,
                closing_can_deliver=closing_can_deliver,
                activated_tools=activated_tools,
                computer_halted=computer_halted,
            )
            guard_decision = computer_guard.record(tool_call, result)
            if guard_decision.feedback:
                result = result.model_copy(
                    update={
                        "error": "\n".join(
                            part
                            for part in (result.error, guard_decision.feedback)
                            if part
                        )
                    }
                )
            if guard_decision.halt:
                computer_halted = True
            if self._checkpoint_store is not None:
                await self._checkpoint_store.complete_tool(run_id, result)

            if (
                mode is AgentMode.PLAN
                and result.success
                and tool_call.name in ("task_create", "task_update")
            ):
                plan_task_created = True
                task_id = plan_task_id_from_output(result.output)
                if task_id:
                    plan_task_id = task_id

            records.append(
                ToolCallRecord(
                    round_index=round_index,
                    tool_call=tool_call,
                    result=result,
                )
            )
            result_messages.append(self._result_message(result))

            if tool_call.name == "computer_type" and result.success:
                computer_verification_pending = (
                    computer_verification_status(result.output) == "unverified"
                )
            elif (
                tool_call.name == "computer_observe"
                and result.success
                and computer_verification_pending
            ):
                computer_verification_pending = False
            if tool_call.name == TOOL_SEARCH_NAME and result.success:
                pending_activations.update(
                    name
                    for name in activated_tool_names(result.output)
                    if self._registry.is_deferred(name)
                )
            if tool_call.name == SKILL_READ_TOOL_NAME and result.success:
                await context_session.activate_skill(
                    result,
                    emitter=emitter,
                    step=step,
                )

        return ToolRoundOutcome(
            records=tuple(records),
            result_messages=tuple(result_messages),
            pending_activations=frozenset(pending_activations),
            previous_signature=previous_signature,
            repeated_count=repeated_count,
            computer_halted=computer_halted,
            computer_verification_pending=computer_verification_pending,
            plan_task_created=plan_task_created,
            plan_task_id=plan_task_id,
        )

    async def _execute_one(
        self,
        tool_call: ToolCall,
        *,
        context: ToolExecutionContext,
        hook: ToolHook,
        mode: AgentMode,
        closing_can_deliver: bool,
        activated_tools: set[str],
        computer_halted: bool,
    ) -> ToolResult:
        """执行一次工具调用，并在执行层落实模式与 Closing 边界。"""

        rejection = self._rejection_reason(
            tool_call,
            mode=mode,
            closing_can_deliver=closing_can_deliver,
            activated_tools=activated_tools,
            computer_halted=computer_halted,
        )
        if rejection is not None:
            await hook.before_execute(context)
            result = ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                success=False,
                error=rejection,
                duration_ms=0,
            )
            await hook.after_execute(context, result)
            return result
        try:
            return await self._executor.execute(
                tool_call,
                context=context,
                hooks=(hook,),
            )
        except Exception as exc:
            result = ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=0.0,
            )
            await hook.after_execute(context, result)
            return result

    def _rejection_reason(
        self,
        tool_call: ToolCall,
        *,
        mode: AgentMode,
        closing_can_deliver: bool,
        activated_tools: set[str],
        computer_halted: bool,
    ) -> str | None:
        if computer_halted and tool_call.name.startswith("computer_"):
            return (
                "computer_attempts_halted: repeated failures without desktop "
                "progress; explain the blocker instead"
            )
        if closing_can_deliver and not (
            self._registry.is_allowed_during_closing(tool_call.name, mode)
            and (
                not self._registry.is_deferred(tool_call.name)
                or tool_call.name in activated_tools
            )
        ):
            return (
                "Tool is not allowed during budget closing "
                "(delivery tools only)."
            )
        if mode is AgentMode.PLAN and not self._registry.is_allowed_for_mode(
            tool_call.name,
            mode,
        ):
            return (
                "Tool is not allowed in plan mode "
                "(read-only / planning tools only)."
            )
        if not self._registry.is_available_for_mode(
            tool_call.name,
            mode,
            activated_names=activated_tools,
        ):
            return "Deferred tool is not active. Call tool_search first."
        return None

    @staticmethod
    def _result_message(result: ToolResult) -> Message:
        return Message(
            role=MessageRole.TOOL,
            name=result.tool_name,
            tool_call_id=result.tool_call_id,
            content=result.model_dump_json(exclude_none=True),
        )


__all__ = ["ToolRoundExecutor", "ToolRoundOutcome"]
