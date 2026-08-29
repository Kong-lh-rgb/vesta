"""Agent Runtime 使用的无状态解析、预算与请求前缀辅助函数。"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.context import ConversationSummaryState
from app.models.types import (
    Message,
    MessageRole,
    ModelProvider,
    ModelUsage,
    ToolCall,
    ToolDefinition,
    add_model_usage,
)

from .budget import RunBudgetConfig, RunBudgetDecision, RunBudgetStatus
from .result import ToolCallRecord

_LEGACY_DATE_PATTERN = re.compile(r"当前日期是 \d{4}-\d{2}-\d{2}。")


@dataclass(frozen=True)
class RequestPrefixState:
    """保存当前 Run 最近一次已发送请求的稳定前缀。"""

    source_messages: tuple[Message, ...]
    context_messages: tuple[Message, ...]
    tools: tuple[ToolDefinition, ...]
    sent_messages: tuple[Message, ...]

    def extend(
        self,
        *,
        source_messages: tuple[Message, ...],
        context_messages: tuple[Message, ...],
        tools: tuple[ToolDefinition, ...],
    ) -> tuple[Message, ...] | None:
        """上下文形状未变时，只把新产生的消息追加到已发送前缀。"""

        if context_messages != self.context_messages or tools != self.tools:
            return None
        previous_count = len(self.source_messages)
        if len(source_messages) < previous_count:
            return None
        if source_messages[:previous_count] != self.source_messages:
            return None
        return (*self.sent_messages, *source_messages[previous_count:])


def computer_verification_status(output: object) -> str | None:
    """从统一工具输出中读取电脑输入的效果验证状态。"""

    if not isinstance(output, str):
        return None
    try:
        payload = json.loads(output)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    status = payload.get("verification_status")
    return status if isinstance(status, str) else None


def looks_like_textual_tool_call(content: str | None) -> bool:
    """识别被模型错误输出为普通文本的常见工具协议标记。"""

    if not content:
        return False
    lowered = content.lower()
    return any(
        marker in lowered
        for marker in (
            "<tool_calls",
            "<｜｜dsml｜｜tool_calls",
            "<｜｜dsml｜｜invoke",
        )
    )


def offset_summary_state(
    state: ConversationSummaryState | None,
    offset: int,
) -> ConversationSummaryState | None:
    """在 request-only 系统消息坐标与原始历史坐标之间转换摘要水位。"""

    if state is None or offset == 0:
        return state
    covered_message_count = state.covered_message_count + offset
    if covered_message_count < 0:
        raise ValueError("summary offset moved covered_message_count below zero")
    return state.model_copy(
        update={"covered_message_count": covered_message_count}
    )


def skill_read_outcome(output: object) -> tuple[str | None, bool]:
    """解析 skill_read 结果，保留“查询成功但未找到”的失败语义。"""

    if isinstance(output, str):
        try:
            payload = json.loads(output)
        except (ValueError, TypeError):
            return None, False
    elif isinstance(output, dict):
        payload = output
    else:
        return None, False
    name = payload.get("name")
    normalized_name = name if isinstance(name, str) and name else None
    return normalized_name, payload.get("found") is True


def plan_failure_message(message: Message, prefix: str) -> Message:
    """Plan Mode 未形成有效计划时，在最终回复前附加明确提示。"""

    content = message.content or ""
    return message.model_copy(update={"content": f"{prefix}\n\n{content}"})


def plan_task_id_from_output(output: object) -> str | None:
    """从 task_create / task_update 的工具输出 JSON 中提取任务 ID。"""

    if isinstance(output, str):
        try:
            payload = json.loads(output)
        except (ValueError, TypeError):
            return None
    elif isinstance(output, dict):
        payload = output
    else:
        return None
    if not isinstance(payload, dict):
        return None
    task_id = payload.get("id")
    return task_id if isinstance(task_id, str) and task_id else None


def add_usage(total: ModelUsage, current: ModelUsage) -> ModelUsage:
    """累加多轮模型调用的 Token 用量。"""

    return add_model_usage(total, current)


def usage_call_count(usage: ModelUsage) -> int:
    """从附属模型 Usage 中取得调用数；旧实现仅有 Token 时推断为一次。"""

    if usage.model_calls > 0:
        return usage.model_calls
    if usage.input_tokens or usage.output_tokens or usage.total_tokens:
        return 1
    return 0


def run_budget_detail(decision: RunBudgetDecision) -> str:
    """生成稳定、可诊断的预算停止原因。"""

    reason = decision.reason.value if decision.reason is not None else "unknown"
    return (
        f"reason={reason}, chargeable_tokens={decision.chargeable_tokens}, "
        f"model_calls={decision.model_calls}"
    )


def run_budget_event_fields(
    decision: RunBudgetDecision,
    config: RunBudgetConfig,
    *,
    status: RunBudgetStatus | None = None,
) -> dict[str, object]:
    """把预算快照转换为 AgentEvent 的统一字段。"""

    return {
        "run_budget_status": (status or decision.status).value,
        "run_budget_reason": (
            decision.reason.value if decision.reason is not None else None
        ),
        "run_budget_chargeable_tokens": decision.chargeable_tokens,
        "run_budget_model_calls": decision.model_calls,
        "run_budget_warning_tokens": config.warning_tokens,
        "run_budget_finalization_tokens": config.finalization_tokens,
        "run_budget_hard_tokens": config.hard_tokens,
        "run_budget_warning_model_calls": config.warning_model_calls,
        "run_budget_finalization_model_calls": config.finalization_model_calls,
        "run_budget_hard_model_calls": config.hard_model_calls,
    }


def reflection_tool_context(
    records: Sequence[ToolCallRecord],
    *,
    max_chars: int,
) -> tuple[str, ...]:
    """为 Reflector 提供有界工具摘要，不默认复制全部原始输出。"""

    if max_chars <= 0:
        return ()
    remaining = max_chars
    items: list[str] = []
    for record in records:
        payload = json.dumps(
            {
                "tool": record.tool_call.name,
                "arguments": record.tool_call.arguments,
                "success": record.result.success,
                "output": record.result.output,
                "error": record.result.error,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        if len(payload) > remaining:
            payload = payload[:remaining]
        if payload:
            items.append(payload)
            remaining -= len(payload)
        if remaining <= 0:
            break
    return tuple(items)


def recalled_memory_revisions(
    records: Sequence[ToolCallRecord],
) -> dict[str, int]:
    """返回本轮确实读到的 Memory ID 与当时的语义 revision。"""

    recalled: dict[str, int] = {}
    for record in records:
        if record.tool_call.name != "memory_read" or not record.result.success:
            continue
        arguments: Any = record.tool_call.arguments
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                continue
        if not isinstance(arguments, dict):
            continue
        memory_id = arguments.get("memory_id")
        if not isinstance(memory_id, str):
            continue
        try:
            output = json.loads(record.result.output or "")
        except (json.JSONDecodeError, TypeError):
            continue
        normalized = memory_id.strip().upper()
        revision = output.get("revision") if isinstance(output, dict) else None
        if (
            isinstance(output, dict)
            and output.get("found") is True
            and output.get("id") == normalized
            and isinstance(revision, int)
            and revision > 0
        ):
            recalled[normalized] = revision
    return recalled


def without_legacy_fixed_date(message: Message) -> Message:
    """仅清理模型请求副本中的旧固定日期，保留数据库原始历史。"""

    if message.role is not MessageRole.SYSTEM or not message.content:
        return message
    cleaned = _LEGACY_DATE_PATTERN.sub("", message.content)
    if cleaned == message.content:
        return message
    return message.model_copy(update={"content": cleaned})


def provider_name(provider: ModelProvider | str | None) -> str | None:
    """把 Provider 枚举转换为事件可序列化名称。"""

    if isinstance(provider, ModelProvider):
        return provider.value
    return provider


def tool_call_signature(tool_call: ToolCall) -> str:
    """为重复工具调用检测生成稳定签名。"""

    arguments: Any = tool_call.arguments
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return f"{tool_call.name}:{arguments}"

    canonical_arguments = json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"{tool_call.name}:{canonical_arguments}"


__all__ = [
    "RequestPrefixState",
    "add_usage",
    "computer_verification_status",
    "looks_like_textual_tool_call",
    "offset_summary_state",
    "plan_failure_message",
    "plan_task_id_from_output",
    "provider_name",
    "recalled_memory_revisions",
    "reflection_tool_context",
    "run_budget_detail",
    "run_budget_event_fields",
    "skill_read_outcome",
    "tool_call_signature",
    "usage_call_count",
    "without_legacy_fixed_date",
]
