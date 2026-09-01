"""一次 Agent Run 内的模型 Step 与工具轮执行器。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from app.checkpoint import RunCheckpoint, SQLiteCheckpointStore
from app.context import ContextManager, ConversationSummaryState
from app.memory import MemoryManager, MemoryRecallQueryInputs, recent_user_message_texts
from app.models.registry import ModelAdapterRegistry
from app.models.types import (
    AgentMode,
    Message,
    MessageRole,
    ModelProvider,
    ModelRequest,
    ModelUsage,
)
from app.skills import SkillContextProvider, SkillStore
from app.task.context import TaskContextProvider
from app.tools.catalog import (
    ensure_tool_search_registered,
)
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry

from .budget import RunBudget, RunBudgetStatus, chargeable_tokens
from .computer_guard import ComputerStagnationGuard
from .context_session import RuntimeContextSession
from .errors import (
    AgentRuntimeError,
    ContextPreparationError,
    ContextWindowExceededError,
    MaxStepsExceededError,
    ModelInvocationError,
    RunBudgetExceededError,
)
from .event_stream import EventEmitter
from .events import AgentEventType
from .result import (
    AgentError,
    AgentResult,
    AgentStopReason,
    ToolCallRecord,
    ToolRound,
)
from .runtime_helpers import (
    RequestPrefixState,
    add_usage,
    looks_like_textual_tool_call,
    offset_summary_state,
    plan_failure_message,
    provider_name,
    run_budget_detail,
    run_budget_event_fields,
    usage_call_count,
    without_legacy_fixed_date,
)
from .tool_hooks import AgentEventHook
from .tool_round_executor import ToolRoundExecutor

# Plan Mode 系统指令（补充；真正的限制由工具过滤 + 执行层硬阻断保证）。
_PLAN_MODE_SYSTEM_MESSAGE = (
    "你现在处于 PLAN MODE（规划模式）：只分析、调查并形成计划，不要修改用户环境。\n"
    "你可以使用只读 / 搜索工具（read_file、list_files、web_search、get_current_time、"
    "memory_read、memory_search、history_search/read、evidence_search/read）与任务工具"
    "（task_create、task_update、task_get、task_list）。\n"
    "完成必要调查后，必须创建（task_create）或更新（task_update）一个 PENDING 任务"
    "作为本轮计划，至少包含 title、goal 与具体可执行的 steps；不要伪造 DONE 步骤、"
    "已完成 state 或已验证 key_facts。\n"
    "最后返回简洁的计划说明。"
)

_PLAN_NO_TASK_MESSAGE = "Plan mode finished without creating a task."
_PLAN_NO_VALID_TASK_MESSAGE = "Plan mode finished without a valid pending task."
_RUN_BUDGET_FINALIZATION_MESSAGE = (
    "本 Run 已达到 Main Agent 用量收口线。不要再调用工具，请基于已有证据立即"
    "给出简洁的最终答复；明确区分已完成、未完成和无法验证的内容，不要伪造"
    "执行结果。"
)
_RUN_BUDGET_CLOSING_MESSAGE = (
    "本 Run 已达到 Main Agent 用量收口线，现在进入 Closing。仅保留完成当前"
    "目标所必需的交付工具；不要继续搜索、调查或扩展任务。若已有结果尚未写入"
    "文件、发布为交付物或同步到任务状态，请立即完成这一次交付；否则直接给出"
    "简洁的最终答复。"
)
_RUN_BUDGET_WARNING_MESSAGE = (
    "本 Run 的累计 Main Agent 用量已进入预警区。请减少不必要的重复调查和工具"
    "调用，优先完成当前目标；仍可在确有必要时继续使用工具。"
)
_TOOL_ROUND_LIMIT_FALLBACK_MESSAGE = (
    "已达到本 Run 的工具调用轮次上限，系统已停止继续执行工具。已有工具结果"
    "仍保留在本轮记录中，但模型未能在无工具模式下生成可靠总结；如需继续，"
    "请基于当前结果提出下一步要求。"
)
_EMPTY_FINAL_RETRY_MESSAGE = (
    "上一条模型响应没有可展示文本，也没有工具调用。请基于已有上下文给出一条"
    "完整、可直接展示给用户的最终回答；不要只输出内部思考。"
)
_TEXTUAL_TOOL_CALL_RETRY_MESSAGE = (
    "上一条模型响应把工具调用协议作为普通文本输出，系统不会执行这类文本。"
    "如需调用工具，必须使用 Provider 的结构化 tool_calls；否则请直接给出一条"
    "完整、可展示给用户的最终回答，不要输出 DSML、XML 或其他工具协议标记。"
)



class AgentLoop:
    """执行单次 Run 内的模型请求、工具调用和停止判定。"""

    def __init__(
        self,
        *,
        model_registry: ModelAdapterRegistry,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        provider: ModelProvider | str | None,
        model: str | None,
        system_prompt: str | None,
        max_steps: int,
        max_tool_rounds: int | None,
        max_output_tokens: int | None,
        context_manager: ContextManager,
        task_context_provider: TaskContextProvider | None,
        checkpoint_store: SQLiteCheckpointStore | None,
        memory_manager: MemoryManager | None,
        skill_store: SkillStore | None,
        skill_context_provider: SkillContextProvider | None,
        run_budget: RunBudget,
    ) -> None:
        self._model_registry = model_registry
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._provider = provider
        self._model = model
        self._system_prompt = system_prompt
        self._max_steps = max_steps
        self._max_tool_rounds = max_tool_rounds
        self._max_output_tokens = max_output_tokens
        self._context_manager = context_manager
        self._task_context_provider = task_context_provider
        self._checkpoint_store = checkpoint_store
        self._memory_manager = memory_manager
        self._skill_store = skill_store
        self._skill_context_provider = skill_context_provider
        self._run_budget = run_budget
        self._tool_round_executor = ToolRoundExecutor(
            registry=tool_registry,
            executor=tool_executor,
            checkpoint_store=checkpoint_store,
        )

    async def run(
        self,
        run_id: str,
        user_input: str,
        *,
        history: Sequence[Message],
        conversation_id: str | None,
        emitter: EventEmitter,
        summary_state: ConversationSummaryState | None,
        recovery_checkpoint: RunCheckpoint | None,
        mode: AgentMode,
    ) -> AgentResult:
        """执行一次已分配 Run ID 的 Agent 循环。"""

        tool_event_hook = AgentEventHook(emitter)
        user_message = Message(role=MessageRole.USER, content=user_input)
        # 原始消息用于 AgentResult 和数据库持久化，始终保留完整工具协议。
        historical_message_count = len(history)
        messages = [*history, user_message]
        transformed_history = tuple(
            without_legacy_fixed_date(message) for message in history
        )
        request_system_message = (
            Message(role=MessageRole.SYSTEM, content=self._system_prompt)
            if self._system_prompt is not None
            and not any(
                message.role is MessageRole.SYSTEM
                and message.content == self._system_prompt
                for message in transformed_history
            )
            else None
        )
        request_history_offset = 1 if request_system_message is not None else 0
        request_historical_message_count = (
            historical_message_count + request_history_offset
        )
        previous_signature: str | None = None
        repeated_count = 0
        tool_rounds: list[ToolRound] = []
        tool_calls: list[ToolCallRecord] = []
        usage = ModelUsage()
        main_model_calls = 0
        budget_chargeable_tokens = 0
        current_summary_state = summary_state
        context_session = RuntimeContextSession(
            memory_manager=self._memory_manager,
            skill_store=self._skill_store,
            skill_context_provider=self._skill_context_provider,
            task_context_provider=self._task_context_provider,
            # Memory 自动召回的确定性 Query 输入：当前用户消息 + 近期用户
            # 消息 + 会话摘要目标（活动 Task 字段由 Session 首次构建时补齐）。
            recall_query=(
                MemoryRecallQueryInputs(
                    user_message=user_input,
                    recent_user_messages=recent_user_message_texts(history),
                    summary_objective=(
                        summary_state.summary.current_objective
                        if summary_state is not None
                        and summary_state.summary.current_objective
                        else None
                    ),
                )
                if self._memory_manager is not None
                else None
            ),
        )
        activated_tools: set[str] = set()
        ensure_tool_search_registered(self._tool_registry)
        # Plan Mode：本轮是否创建/更新了 PENDING Task，以及最新 Task ID。
        plan_task_created = False
        plan_task_id: str | None = None
        finalization_pending = False
        computer_verification_pending = False
        computer_guard = ComputerStagnationGuard()
        computer_halted = False
        budget_warning_emitted = False
        budget_closing_started = False
        budget_closing_delivery_used = False
        budget_closing_reporting_attempted = False
        empty_final_retry_used = False
        textual_tool_call_retry_used = False
        response_repair_message: Message | None = None
        request_prefix_state: RequestPrefixState | None = None

        await emitter.emit(
            AgentEventType.AGENT_STARTED,
            message=user_message,
            provider=provider_name(self._provider),
            model=self._model,
        )

        async def stop_with_error(
            error: AgentRuntimeError,
            stop_reason: AgentStopReason,
            *,
            step: int,
        ) -> AgentResult:
            """构造失败结果；公共 run() 在后置阶段结束后发射终止事件。"""

            return self._result(
                run_id=run_id,
                final_message=self._error_message(error),
                messages=messages,
                steps=step,
                stop_reason=stop_reason,
                tool_rounds=tool_rounds,
                tool_calls=tool_calls,
                usage=usage,
                error=error,
                summary_state=current_summary_state,
            )

        def stop_at_tool_round_limit(*, step: int) -> AgentResult:
            """模型拒绝无工具收尾时，由 Harness 给出诚实且确定性的边界说明。"""

            final_message = Message(
                role=MessageRole.ASSISTANT,
                content=_TOOL_ROUND_LIMIT_FALLBACK_MESSAGE,
            )
            messages[-1] = final_message
            return self._result(
                run_id=run_id,
                final_message=final_message,
                messages=messages,
                steps=step,
                stop_reason=AgentStopReason.FINAL_ANSWER,
                tool_rounds=tool_rounds,
                tool_calls=tool_calls,
                usage=usage,
                summary_state=current_summary_state,
            )

        for step in range(1, self._max_steps + 2):
            finalization_step = step > self._max_steps
            if finalization_step and not finalization_pending:
                break
            budget_decision = self._run_budget.evaluate(
                usage,
                chargeable_tokens_override=budget_chargeable_tokens,
                model_calls_override=main_model_calls,
            )
            budget_warning_in_request = budget_decision.should_warn
            budget_config = self._run_budget.config
            if budget_decision.exceeded:
                await emitter.emit(
                    AgentEventType.RUN_BUDGET_EXCEEDED,
                    step=step,
                    **run_budget_event_fields(budget_decision, budget_config),
                )
                return await stop_with_error(
                    RunBudgetExceededError(
                        run_budget_detail(budget_decision)
                    ),
                    AgentStopReason.RUN_BUDGET,
                    step=max(0, step - 1),
                )
            if budget_decision.should_warn and not budget_warning_emitted:
                budget_warning_emitted = True
                await emitter.emit(
                    AgentEventType.RUN_BUDGET_WARNING,
                    step=step,
                    **run_budget_event_fields(budget_decision, budget_config),
                )
            budget_forces_final = budget_decision.should_finalize
            if budget_forces_final:
                if budget_closing_delivery_used:
                    if budget_closing_reporting_attempted:
                        await emitter.emit(
                            AgentEventType.RUN_BUDGET_EXCEEDED,
                            step=step,
                            **run_budget_event_fields(
                                budget_decision,
                                budget_config,
                                status=RunBudgetStatus.EXCEEDED,
                            ),
                        )
                        return await stop_with_error(
                            RunBudgetExceededError(
                                "dedicated closing report call was already used"
                            ),
                            AgentStopReason.RUN_BUDGET,
                            step=max(0, step - 1),
                        )
                    budget_closing_reporting_attempted = True
                elif not budget_closing_started:
                    budget_closing_started = True
                    await emitter.emit(
                        AgentEventType.RUN_BUDGET_FINALIZING,
                        step=step,
                        **run_budget_event_fields(budget_decision, budget_config),
                    )
            if self._checkpoint_store is not None:
                await self._checkpoint_store.before_model(run_id, step=step)
            tool_round_limit_reached = (
                self._max_tool_rounds is not None
                and len(tool_rounds) >= self._max_tool_rounds
            )
            forced_without_budget = (
                finalization_step or computer_halted or tool_round_limit_reached
            )
            closing_can_deliver = (
                budget_forces_final
                and not budget_closing_delivery_used
                and not forced_without_budget
            )
            force_final_answer = forced_without_budget or (
                budget_forces_final and not closing_can_deliver
            )
            # 原始历史保持不变；模型请求视图会移除旧版持久提示词中的固定日期。
            raw_source_messages = tuple(
                without_legacy_fixed_date(message) for message in messages
            )
            if response_repair_message is not None:
                raw_source_messages = (
                    *raw_source_messages,
                    response_repair_message,
                )
            source_messages = (
                (request_system_message, *raw_source_messages)
                if request_system_message is not None
                else raw_source_messages
            )
            request_summary_state = offset_summary_state(
                current_summary_state,
                request_history_offset,
            )
            request_messages = source_messages
            if closing_can_deliver:
                request_tools = self._tool_registry.closing_definitions_for_mode(
                    mode,
                    activated_names=activated_tools,
                )
                if not request_tools:
                    closing_can_deliver = False
                    force_final_answer = True
            elif force_final_answer:
                request_tools = ()
            else:
                request_tools = self._tool_registry.model_definitions_for_mode(
                    mode,
                    activated_names=activated_tools,
                )
            # 先解析实际使用的模型和输出上限，确保预算与请求完全一致。
            try:
                adapter = self._model_registry.get(self._provider)
                resolved_model = self._model or adapter.default_model
                resolved_provider = adapter.provider
                effective_max_output_tokens = (
                    self._max_output_tokens or adapter.config.default_max_output_tokens
                )
                if budget_forces_final and force_final_answer:
                    effective_max_output_tokens = min(
                        effective_max_output_tokens,
                        budget_config.finalization_max_output_tokens,
                    )
            except Exception as exc:
                return await stop_with_error(
                    ModelInvocationError(f"{type(exc).__name__}: {exc}"),
                    AgentStopReason.MODEL_ERROR,
                    step=step,
                )

            try:
                # 易变事实通过按需工具获取；Run 级缓存与 Skill 状态由
                # RuntimeContextSession 管理，Task 仍在每个 Step 重新读取。
                trailing_system_messages: list[Message] = []
                if mode is AgentMode.PLAN:
                    trailing_system_messages.append(
                        Message(
                            role=MessageRole.SYSTEM,
                            name="vesta_plan_mode",
                            content=_PLAN_MODE_SYSTEM_MESSAGE,
                        )
                    )
                if budget_warning_in_request:
                    trailing_system_messages.append(
                        Message(
                            role=MessageRole.SYSTEM,
                            content=_RUN_BUDGET_WARNING_MESSAGE,
                        )
                    )
                context_injection = await context_session.build(
                    conversation_id=conversation_id,
                    recovery_checkpoint=recovery_checkpoint,
                    trailing_system_messages=tuple(trailing_system_messages),
                )
                context_messages = context_injection.messages
                if context_messages:
                    request_messages = (
                        *request_messages[:request_historical_message_count],
                        *context_messages,
                        *request_messages[request_historical_message_count:],
                    )
                if closing_can_deliver:
                    request_messages = (
                        *request_messages,
                        Message(
                            role=MessageRole.SYSTEM,
                            content=_RUN_BUDGET_CLOSING_MESSAGE,
                        ),
                    )
                elif force_final_answer:
                    if computer_halted:
                        final_instruction = (
                            "Computer 操作已因同一失败且桌面无进展而停止。不要再输出"
                            "或伪造任何工具调用；请根据已有证据直接说明阻塞原因、"
                            "已经完成的部分和用户可采取的恢复步骤。"
                        )
                    elif budget_forces_final:
                        final_instruction = _RUN_BUDGET_FINALIZATION_MESSAGE
                    else:
                        final_instruction = (
                            "工具调用轮次已用完。请读取最后一条工具结果，停止"
                            "调用工具并直接回答用户。对于 verification_status="
                            "unverified 的电脑操作，只能说明事件已投递、效果未"
                            "确认，不能宣称界面操作已经完成。"
                        )
                    request_messages = (
                        *request_messages,
                        Message(
                            role=MessageRole.SYSTEM,
                            content=final_instruction,
                        ),
                    )
            except Exception as exc:
                return await stop_with_error(
                    ContextPreparationError(f"{type(exc).__name__}: {exc}"),
                    AgentStopReason.CONTEXT_ERROR,
                    step=step,
                )

            continuation_messages = (
                request_prefix_state.extend(
                    source_messages=source_messages,
                    context_messages=context_messages,
                    tools=request_tools,
                )
                if request_prefix_state is not None and not force_final_answer
                else None
            )
            cache_prefix_reused = continuation_messages is not None
            cache_prefix_message_count = (
                len(request_prefix_state.sent_messages)
                if cache_prefix_reused and request_prefix_state is not None
                else 0
            )
            context_input_messages = continuation_messages or request_messages
            context_history_count = (
                0
                if continuation_messages is not None
                else request_historical_message_count
            )
            context_summary_state = (
                None if continuation_messages is not None else request_summary_state
            )
            try:
                context_decision = await self._context_manager.prepare(
                    context_input_messages,
                    tools=request_tools,
                    model=resolved_model,
                    provider=resolved_provider,
                    max_output_tokens=effective_max_output_tokens,
                    history_count=context_history_count,
                    summary_state=context_summary_state,
                )
                if (
                    continuation_messages is not None
                    and current_summary_state is None
                    and context_decision.requires_compaction
                    and context_decision.needs_next_compaction_stage
                ):
                    # Prefix continuation 只携带已经发送过的模型上下文，无法可靠
                    # 标出原始历史边界。它在越过压缩线后若仍未达到目标，必须回到
                    # canonical request 重新准备，才能让首次滚动摘要读取真实历史。
                    # 已存在摘要时，sent prefix 已经携带同一摘要，不应反复重建。
                    continuation_messages = None
                    cache_prefix_reused = False
                    cache_prefix_message_count = 0
                    context_decision = await self._context_manager.prepare(
                        request_messages,
                        tools=request_tools,
                        model=resolved_model,
                        provider=resolved_provider,
                        max_output_tokens=effective_max_output_tokens,
                        history_count=request_historical_message_count,
                        summary_state=request_summary_state,
                    )
            except Exception as exc:
                return await stop_with_error(
                    ContextPreparationError(f"{type(exc).__name__}: {exc}"),
                    AgentStopReason.CONTEXT_ERROR,
                    step=step,
                )

            if continuation_messages is not None:
                # continuation 输入已经包含上一轮生成的滚动摘要。这里保留其对应
                # 的持久化水位，避免一次“无需重建”的 Step 把 Summary State 清空。
                context_decision = replace(
                    context_decision,
                    summary_state=request_summary_state,
                )
                previous_prefix = request_prefix_state.sent_messages
                cache_prefix_reused = (
                    context_decision.messages[: len(previous_prefix)]
                    == previous_prefix
                )
                if not cache_prefix_reused:
                    cache_prefix_message_count = 0

            current_summary_state = offset_summary_state(
                context_decision.summary_state,
                -request_history_offset,
            )
            usage = add_usage(usage, context_decision.summary_usage)
            main_model_calls += usage_call_count(context_decision.summary_usage)
            budget_chargeable_tokens += chargeable_tokens(
                context_decision.summary_usage
            )
            request_messages = context_decision.messages
            request_tools = context_decision.tools
            # Context summary 也是 critical-path 模型调用；它可能让本 Run 在真正
            # 请求主模型前跨过预算线，因此准备完成后必须再评估一次。
            prepared_budget_decision = self._run_budget.evaluate(
                usage,
                chargeable_tokens_override=budget_chargeable_tokens,
                model_calls_override=main_model_calls,
            )
            budget_decision = prepared_budget_decision
            if budget_decision.exceeded:
                await emitter.emit(
                    AgentEventType.RUN_BUDGET_EXCEEDED,
                    step=step,
                    **run_budget_event_fields(budget_decision, budget_config),
                )
                return await stop_with_error(
                    RunBudgetExceededError(run_budget_detail(budget_decision)),
                    AgentStopReason.RUN_BUDGET,
                    step=max(0, step - 1),
                )
            if budget_decision.should_warn and not budget_warning_emitted:
                budget_warning_emitted = True
                await emitter.emit(
                    AgentEventType.RUN_BUDGET_WARNING,
                    step=step,
                    **run_budget_event_fields(budget_decision, budget_config),
                )
            if budget_decision.should_warn and not budget_warning_in_request:
                warning_appended_after_prepare = True
                request_messages = (
                    *request_messages,
                    Message(
                        role=MessageRole.SYSTEM,
                        content=_RUN_BUDGET_WARNING_MESSAGE,
                    ),
                )
            else:
                warning_appended_after_prepare = False
            if budget_decision.should_finalize and not budget_forces_final:
                budget_forces_final = True
                budget_closing_started = True
                closing_can_deliver = not forced_without_budget
                if closing_can_deliver:
                    request_tools = (
                        self._tool_registry.closing_definitions_for_mode(
                            mode,
                            activated_names=activated_tools,
                        )
                    )
                    closing_can_deliver = bool(request_tools)
                force_final_answer = forced_without_budget or not closing_can_deliver
                if force_final_answer:
                    request_tools = ()
                    effective_max_output_tokens = min(
                        effective_max_output_tokens,
                        budget_config.finalization_max_output_tokens,
                    )
                request_messages = (
                    *request_messages,
                    Message(
                        role=MessageRole.SYSTEM,
                        content=(
                            _RUN_BUDGET_CLOSING_MESSAGE
                            if closing_can_deliver
                            else _RUN_BUDGET_FINALIZATION_MESSAGE
                        ),
                    ),
                )
                await emitter.emit(
                    AgentEventType.RUN_BUDGET_FINALIZING,
                    step=step,
                    **run_budget_event_fields(budget_decision, budget_config),
                )
            if (
                request_prefix_state is not None
                and request_tools != request_prefix_state.tools
            ):
                # 工具集合变化会改变 Provider 请求前缀，不能把消息前缀相同误报为
                # 完整缓存前缀复用。
                cache_prefix_reused = False
                cache_prefix_message_count = 0
            await emitter.emit(
                AgentEventType.MODEL_STARTED,
                step=step,
                provider=resolved_provider,
                model=resolved_model,
                original_estimated_input_tokens=(
                    context_decision.original_estimated_input_tokens
                ),
                prepared_input_tokens=context_decision.prepared_input_tokens,
                estimated_input_tokens=context_decision.estimated_input_tokens,
                context_trimmed=context_decision.trimmed,
                context_window=context_decision.context_window,
                input_budget=context_decision.input_budget,
                working_input_budget=context_decision.working_input_budget,
                hard_trigger_tokens=context_decision.hard_trigger_tokens,
                hard_target_tokens=context_decision.hard_target_tokens,
                usage_ratio=context_decision.usage_ratio,
                trigger_tokens=context_decision.trigger_tokens,
                target_tokens=context_decision.target_tokens,
                tool_result_budget_tokens=(
                    context_decision.tool_result_budget_tokens
                ),
                tool_result_tokens_before=(
                    context_decision.tool_result_tokens_before
                ),
                tool_result_tokens_after=(
                    context_decision.tool_result_tokens_after
                ),
                tool_schema_tokens=context_decision.tool_schema_tokens,
                message_tokens_before=context_decision.message_tokens_before,
                message_tokens_after=context_decision.message_tokens_after,
                unsummarized_conversation_blocks=(
                    context_decision.unsummarized_conversation_blocks
                ),
                conversation_block_limit=(
                    context_decision.conversation_block_limit
                ),
                conversation_block_triggered=(
                    context_decision.conversation_block_triggered
                ),
                requires_compaction=context_decision.requires_compaction,
                exceeds_input_budget=context_decision.exceeds_input_budget,
                capability_source=context_decision.capability_source,
                original_usage_ratio=context_decision.original_usage_ratio,
                prepared_usage_ratio=context_decision.prepared_usage_ratio,
                compaction_stage=context_decision.compaction_stage.value,
                compacted_tool_results=context_decision.compacted_tool_results,
                removed_tool_rounds=context_decision.removed_tool_rounds,
                reached_target=context_decision.reached_target,
                needs_next_compaction_stage=(
                    context_decision.needs_next_compaction_stage
                ),
                summary_updated=context_decision.summary_updated,
                summarized_conversation_blocks=(
                    context_decision.summarized_conversation_blocks
                ),
                summary_usage=context_decision.summary_usage,
                summary_provider=context_decision.summary_provider,
                summary_model=context_decision.summary_model,
                summary_duration_ms=context_decision.summary_duration_ms,
                summary_error=context_decision.summary_error,
                cache_prefix_reused=cache_prefix_reused,
                cache_prefix_message_count=cache_prefix_message_count,
                available_skill_count=context_injection.available_skill_count,
                skill_catalog_tokens=context_injection.skill_catalog_tokens,
                active_skill_names=context_injection.active_skill_names,
                active_skill_tokens=context_injection.active_skill_tokens,
                active_skill_message_names=(
                    context_injection.active_skill_message_names
                ),
                recall_candidate_ids=context_injection.recall_candidate_ids,
                recall_mode=context_injection.recall_mode,
                **run_budget_event_fields(budget_decision, budget_config),
            )
            if context_decision.exceeds_input_budget:
                return await stop_with_error(
                    ContextWindowExceededError(
                        context_decision.estimated_input_tokens or 0,
                        context_decision.input_budget or 0,
                    ),
                    AgentStopReason.CONTEXT_ERROR,
                    step=step,
                )

            if not force_final_answer and not warning_appended_after_prepare:
                request_prefix_state = RequestPrefixState(
                    source_messages=source_messages,
                    context_messages=context_messages,
                    tools=request_tools,
                    sent_messages=request_messages,
                )
            else:
                request_prefix_state = None

            try:
                async def emit_text_delta(delta: str) -> None:
                    if not delta:
                        return
                    await emitter.emit(
                        AgentEventType.MODEL_OUTPUT_DELTA,
                        step=step,
                        provider=resolved_provider,
                        model=resolved_model,
                        delta=delta,
                    )

                response = await adapter.complete_stream(
                    ModelRequest(
                        messages=request_messages,
                        model=resolved_model,
                        tools=request_tools,
                        max_output_tokens=effective_max_output_tokens,
                    ),
                    on_text_delta=emit_text_delta,
                    # Provider 原始 reasoning 属于内部推理，不进入聊天、Trace 或
                    # Desktop 事件流；可观察执行过程只使用结构化 AgentEvent。
                    on_reasoning_delta=None,
                )
            except Exception as exc:
                return await stop_with_error(
                    ModelInvocationError(f"{type(exc).__name__}: {exc}"),
                    AgentStopReason.MODEL_ERROR,
                    step=step,
                )

            usage = add_usage(usage, response.usage)
            main_model_calls += max(1, response.usage.model_calls)
            budget_chargeable_tokens += chargeable_tokens(response.usage)
            assistant_message = response.message.model_copy(
                update={"reasoning": None}
            )
            # 单次响应修复提示只属于刚完成的 ModelRequest；无论模型返回文本
            # 还是工具调用，都不能进入原始聊天历史或后续请求。
            response_repair_message = None
            messages.append(assistant_message)
            await emitter.emit(
                AgentEventType.MODEL_COMPLETED,
                step=step,
                provider=response.provider,
                model=response.model,
                message=assistant_message,
                usage=response.usage,
            )
            tool_calls_in_message = assistant_message.tool_calls
            if force_final_answer and tool_calls_in_message:
                # 最终化请求没有提供工具定义；即使模型伪造工具调用也不执行。
                if budget_forces_final:
                    return await stop_with_error(
                        RunBudgetExceededError(
                            "model attempted a tool call during budget finalization"
                        ),
                        AgentStopReason.RUN_BUDGET,
                        step=step,
                    )
                if tool_round_limit_reached:
                    return stop_at_tool_round_limit(step=step)
                return await stop_with_error(
                    ModelInvocationError(
                        "model attempted a tool call during forced finalization"
                    ),
                    AgentStopReason.MODEL_ERROR,
                    step=step,
                )
            if not tool_calls_in_message:
                if not (assistant_message.content or "").strip():
                    if tool_round_limit_reached:
                        return stop_at_tool_round_limit(step=step)
                    # 空 assistant 不是合法 Provider 历史消息。所有非 fallback
                    # 路径都先移除，避免失败结果或后续会话携带非法协议消息。
                    messages.pop()
                    if budget_forces_final:
                        return await stop_with_error(
                            RunBudgetExceededError(
                                "model returned empty content during budget "
                                "finalization"
                            ),
                            AgentStopReason.RUN_BUDGET,
                            step=step,
                        )
                    if force_final_answer:
                        return await stop_with_error(
                            ModelInvocationError(
                                "model returned empty content during forced "
                                "finalization"
                            ),
                            AgentStopReason.MODEL_ERROR,
                            step=step,
                        )
                    if not empty_final_retry_used:
                        empty_final_retry_used = True
                        response_repair_message = Message(
                            role=MessageRole.SYSTEM,
                            content=_EMPTY_FINAL_RETRY_MESSAGE,
                        )
                        continue
                    return await stop_with_error(
                        ModelInvocationError(
                            "model returned empty content twice without tool calls"
                        ),
                        AgentStopReason.MODEL_ERROR,
                        step=step,
                    )
                if looks_like_textual_tool_call(assistant_message.content):
                    # 部分模型在 tools=() 时仍会把 Provider 工具协议作为普通文本
                    # 输出。它没有被执行，不能因此把 Run 标为 completed。
                    if force_final_answer:
                        if budget_forces_final:
                            return await stop_with_error(
                                RunBudgetExceededError(
                                    "model emitted a textual tool call during "
                                    "budget finalization"
                                ),
                                AgentStopReason.RUN_BUDGET,
                                step=step,
                            )
                        if tool_round_limit_reached:
                            return stop_at_tool_round_limit(step=step)
                        return await stop_with_error(
                            ModelInvocationError(
                                "model emitted a textual tool call during forced "
                                "finalization"
                            ),
                            AgentStopReason.MODEL_ERROR,
                            step=step,
                        )
                    # 普通响应里的文本协议既不能执行，也不能作为最终答案持久化。
                    # 只允许一次有界修复，避免模型在协议文本中无限循环。
                    messages.pop()
                    if not textual_tool_call_retry_used:
                        textual_tool_call_retry_used = True
                        response_repair_message = Message(
                            role=MessageRole.SYSTEM,
                            content=_TEXTUAL_TOOL_CALL_RETRY_MESSAGE,
                        )
                        continue
                    return await stop_with_error(
                        ModelInvocationError(
                            "model emitted a textual tool call twice without "
                            "structured tool_calls"
                        ),
                        AgentStopReason.MODEL_ERROR,
                        step=step,
                    )
                if computer_verification_pending and not computer_halted:
                    messages.append(
                        Message(
                            role=MessageRole.SYSTEM,
                            content=(
                                "最近一次 computer_type 只确认输入事件已投递，尚未"
                                "确认界面效果。必须先调用 computer_observe 获取新证据，"
                                "不能直接向用户宣称操作完成。"
                            ),
                        )
                    )
                    continue
                final_message = assistant_message
                if mode is AgentMode.PLAN:
                    # Plan Mode 完成条件：不仅要 task_create/task_update 成功，
                    # 还要最终重新读取 Task 并确认是有效的 PENDING 计划
                    # （PENDING + goal 非空 + steps 非空 + 无 DONE/IN_PROGRESS 步骤）。
                    plan_valid = False
                    if (
                        plan_task_id is not None
                        and self._task_context_provider is not None
                    ):
                        plan_valid = (
                            await self._task_context_provider.pending_plan_is_valid(
                                conversation_id,
                                plan_task_id,
                            )
                        )
                    if not plan_valid:
                        prefix = (
                            _PLAN_NO_TASK_MESSAGE
                            if not plan_task_created
                            else _PLAN_NO_VALID_TASK_MESSAGE
                        )
                        final_message = plan_failure_message(
                            assistant_message,
                            prefix,
                        )
                        plan_task_id = None
                        messages[-1] = final_message
                return self._result(
                    run_id=run_id,
                    final_message=final_message,
                    messages=messages,
                    steps=step,
                    stop_reason=AgentStopReason.FINAL_ANSWER,
                    tool_rounds=tool_rounds,
                    tool_calls=tool_calls,
                    usage=usage,
                    plan_task_id=plan_task_id,
                    summary_state=current_summary_state,
                )

            round_outcome = await self._tool_round_executor.execute(
                tool_calls_in_message,
                run_id=run_id,
                conversation_id=conversation_id,
                user_input=user_input,
                step=step,
                mode=mode,
                round_index=len(tool_rounds),
                closing_can_deliver=closing_can_deliver,
                activated_tools=activated_tools,
                context_session=context_session,
                computer_guard=computer_guard,
                computer_halted=computer_halted,
                computer_verification_pending=computer_verification_pending,
                previous_signature=previous_signature,
                repeated_count=repeated_count,
                emitter=emitter,
                hook=tool_event_hook,
            )
            tool_calls.extend(round_outcome.records)
            messages.extend(round_outcome.result_messages)
            previous_signature = round_outcome.previous_signature
            repeated_count = round_outcome.repeated_count
            computer_halted = round_outcome.computer_halted
            computer_verification_pending = (
                round_outcome.computer_verification_pending
            )
            plan_task_created = (
                plan_task_created or round_outcome.plan_task_created
            )
            if round_outcome.plan_task_id is not None:
                plan_task_id = round_outcome.plan_task_id
            if round_outcome.repeated_error is not None:
                return self._result(
                    run_id=run_id,
                    final_message=self._error_message(
                        round_outcome.repeated_error
                    ),
                    messages=messages,
                    steps=step,
                    stop_reason=AgentStopReason.REPEATED_TOOL_CALL,
                    tool_rounds=tool_rounds,
                    tool_calls=tool_calls,
                    usage=usage,
                    error=round_outcome.repeated_error,
                    summary_state=current_summary_state,
                )
            pending_activations = set(round_outcome.pending_activations)
            round_records = list(round_outcome.records)
            tool_rounds.append(
                ToolRound(
                    round_index=len(tool_rounds),
                    assistant_message=assistant_message,
                    records=tuple(round_records),
                )
            )
            if closing_can_deliver:
                # Closing 最多保留一次交付工具轮；下一请求只负责汇报结果。
                budget_closing_delivery_used = True
            # 本轮模型没有见过新定义，必须等下一步请求后才能调用。
            activated_tools.update(pending_activations)
            finalization_pending = (
                step == self._max_steps
                and (
                    computer_halted
                    or any(
                        call.name == "computer_observe"
                        for call in tool_calls_in_message
                    )
                    or self._run_budget.evaluate(
                        usage,
                        chargeable_tokens_override=budget_chargeable_tokens,
                        model_calls_override=main_model_calls,
                    ).should_finalize
                )
            )

        error = MaxStepsExceededError(self._max_steps)
        return self._result(
            run_id=run_id,
            final_message=self._error_message(error),
            messages=messages,
            steps=self._max_steps,
            stop_reason=AgentStopReason.MAX_STEPS,
            tool_rounds=tool_rounds,
            tool_calls=tool_calls,
            usage=usage,
            error=error,
            summary_state=current_summary_state,
        )

    @staticmethod
    def _error_message(error: AgentRuntimeError) -> Message:
        return Message(
            role=MessageRole.ASSISTANT,
            content=f"Agent stopped: {error}",
        )

    @staticmethod
    def _result(
        *,
        run_id: str,
        final_message: Message,
        messages: Sequence[Message],
        steps: int,
        stop_reason: AgentStopReason,
        tool_rounds: list[ToolRound],
        tool_calls: list[ToolCallRecord],
        usage: ModelUsage,
        error: AgentRuntimeError | None = None,
        summary_state: ConversationSummaryState | None = None,
        plan_task_id: str | None = None,
    ) -> AgentResult:
        complete_messages = tuple(messages)
        if not complete_messages or complete_messages[-1] != final_message:
            complete_messages = (*complete_messages, final_message)

        return AgentResult(
            run_id=run_id,
            final_message=final_message,
            messages=complete_messages,
            steps=steps,
            stop_reason=stop_reason,
            tool_rounds=tuple(tool_rounds),
            tool_calls=tuple(tool_calls),
            usage=usage,
            error=(
                AgentError(type=type(error).__name__, message=str(error))
                if error is not None
                else None
            ),
            summary_state=summary_state,
            plan_task_id=plan_task_id,
        )


__all__ = ["AgentLoop"]
