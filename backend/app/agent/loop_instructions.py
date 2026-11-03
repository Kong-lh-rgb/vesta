"""Agent Run request and stopping instructions."""

from __future__ import annotations

from app.models.types import AgentMode, Message, MessageRole

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
_TASK_WRITEBACK_REMINDER_MESSAGE = (
    "当前会话的 Task 仍有进行中的步骤，但本次 Run 还没有任何成功的 "
    "task_update 写回。若本轮工作确实有进展、完成或阻塞，请先用 task_update "
    "把真实状态写回（禁止把未完成的步骤伪造成 done）；若本轮与该 Task 无关"
    "或确无状态变化，直接给出最终回答即可。"
)


def context_instructions(
    mode: AgentMode, *, budget_warning: bool
) -> tuple[Message, ...]:
    messages: list[Message] = []
    if mode is AgentMode.PLAN:
        messages.append(Message(
            role=MessageRole.SYSTEM,
            name="vesta_plan_mode",
            content=_PLAN_MODE_SYSTEM_MESSAGE,
        ))
    if budget_warning:
        messages.append(Message(
            role=MessageRole.SYSTEM,
            content=_RUN_BUDGET_WARNING_MESSAGE,
        ))
    return tuple(messages)


def final_request_instruction(
    *, computer_halted: bool, budget_forces_final: bool
) -> Message:
    if computer_halted:
        content = (
            "Computer 操作已因同一失败且桌面无进展而停止。不要再输出"
            "或伪造任何工具调用；请根据已有证据直接说明阻塞原因、"
            "已经完成的部分和用户可采取的恢复步骤。"
        )
    elif budget_forces_final:
        content = _RUN_BUDGET_FINALIZATION_MESSAGE
    else:
        content = (
            "工具调用轮次已用完。请读取最后一条工具结果，停止"
            "调用工具并直接回答用户。对于 verification_status="
            "unverified 的电脑操作，只能说明事件已投递、效果未"
            "确认，不能宣称界面操作已经完成。"
        )
    return Message(role=MessageRole.SYSTEM, content=content)
