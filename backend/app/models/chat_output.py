"""Terminal formatting for CLI run, trace, approval, and memory views."""

from __future__ import annotations

from collections.abc import Sequence

from app.agent.events import AgentEvent, AgentEventType
from app.checkpoint import RunCheckpoint
from app.conversation import Conversation
from app.mcp import MCPServerState, MCPServerStatus
from app.memory import MemoryRecord
from app.run import Run, RunStatus
from app.skill_learning import SkillCandidate
from app.tools import PermissionRule
from app.trace import AgentRunTrace


def _print_agent_event(event: AgentEvent) -> None:
    """把 Runtime 事件转换为简洁的终端进度信息。"""

    event_time = event.event_time.astimezone().strftime("%H:%M:%S")
    prefix = f"[{event_time}]"
    if event.type is AgentEventType.AGENT_STARTED:
        print(f"{prefix} Agent 开始执行")
    elif event.type is AgentEventType.MODEL_STARTED:
        print(f"{prefix} 第 {event.step} 步：正在请求模型")
    elif event.type is AgentEventType.MODEL_COMPLETED:
        tool_count = len(event.message.tool_calls) if event.message else 0
        if tool_count:
            print(f"{prefix} 模型请求调用 {tool_count} 个工具")
        else:
            print(f"{prefix} 模型已返回回复")
    elif event.type is AgentEventType.RUN_BUDGET_WARNING:
        print(
            f"{prefix} Run 用量进入预警区："
            f"{event.run_budget_chargeable_tokens or 0} tokens · "
            f"{event.run_budget_model_calls or 0} calls"
        )
    elif event.type is AgentEventType.RUN_BUDGET_FINALIZING:
        print(f"{prefix} Run 用量达到收口线，正在生成最终答复")
    elif event.type is AgentEventType.RUN_BUDGET_EXCEEDED:
        print(f"{prefix} Run 用量达到硬上限，停止继续请求模型")
    elif event.type is AgentEventType.TOOL_STARTED and event.tool_call:
        print(f"{prefix} 开始执行工具：{event.tool_call.name}")
    elif event.type is AgentEventType.TOOL_COMPLETED and event.tool_result:
        status = "成功" if event.tool_result.success else "失败"
        print(
            f"{prefix} 工具 {event.tool_result.tool_name} {status} "
            f"({event.tool_result.duration_ms:.1f}ms)"
        )
    elif event.type is AgentEventType.TOOL_APPROVAL_REQUIRED and event.tool_call:
        print(f"{prefix} 工具等待人工审批：{event.tool_call.name}")
    elif event.type is AgentEventType.TOOL_APPROVAL_COMPLETED and event.tool_call:
        decision = (
            event.approval_decision.value
            if event.approval_decision is not None
            else "unknown"
        )
        rule_text = (
            f" · 规则：{event.rule_description}"
            if event.rule_description is not None
            else ""
        )
        print(
            f"{prefix} 工具权限检查完成：{event.tool_call.name} · {decision}{rule_text}"
        )
    elif event.type is AgentEventType.MEMORY_REFLECTION_STARTED:
        print(f"{prefix} 正在整理本轮长期记忆")
    elif event.type is AgentEventType.MEMORY_REFLECTION_COMPLETED:
        action = event.reflection_action or "none"
        suffix = (
            f" · {event.reflection_memory_id}"
            if event.reflection_memory_id is not None
            else ""
        )
        print(f"{prefix} 长期记忆整理完成：{action}{suffix}")
    elif event.type is AgentEventType.MEMORY_REFLECTION_FAILED:
        print(f"{prefix} 长期记忆整理失败，已跳过")
    elif event.type is AgentEventType.MEMORY_REFLECTION_SKIPPED:
        reason = event.reflection_skip_reason or "policy"
        print(f"{prefix} 长期记忆整理已跳过：{reason}")
    elif event.type is AgentEventType.MEMORY_MAINTENANCE_STARTED:
        print(f"{prefix} 长期记忆容量不足，正在选择可归档候选")
    elif event.type is AgentEventType.MEMORY_MAINTENANCE_COMPLETED:
        action = event.maintenance_action or "unknown"
        suffix = (
            f" · {event.maintenance_memory_id}"
            if event.maintenance_memory_id is not None
            else ""
        )
        print(f"{prefix} 长期记忆容量维护完成：{action}{suffix}")
    elif event.type is AgentEventType.MEMORY_MAINTENANCE_FAILED:
        print(f"{prefix} 长期记忆容量维护失败，未执行归档")
    elif event.type is AgentEventType.AGENT_COMPLETED:
        print(f"{prefix} Agent 执行完成")
    elif event.type is AgentEventType.AGENT_FAILED:
        reason = event.stop_reason.value if event.stop_reason else "unknown"
        print(f"{prefix} Agent 执行停止：{reason}")

def _print_conversations(
    conversations: tuple[Conversation, ...],
    current_id: str,
) -> None:
    if not conversations:
        print("暂无会话。")
        return
    for conversation in conversations:
        marker = "*" if conversation.id == current_id else " "
        print(
            f"{marker} {conversation.id[:8]}  "
            f"{conversation.title}  ({conversation.message_count} 条消息)"
        )

def _print_runs(runs: tuple[AgentRunTrace, ...], current_conversation_id: str) -> None:
    """显示最近的 Agent Run 摘要。"""

    if not runs:
        print("暂无运行记录。")
        return
    for run in runs:
        marker = "*" if run.conversation_id == current_conversation_id else " "
        started_at = run.started_at.astimezone().strftime("%m-%d %H:%M:%S")
        reason = run.stop_reason.value if run.stop_reason else "-"
        print(
            f"{marker} {run.run_id[:8]}  {started_at}  {run.status.value:<9} "
            f"steps={run.steps} tokens={run.total_tokens} reason={reason}"
        )

def _print_run_lifecycle(runs: tuple[Run, ...], current_conversation_id: str) -> None:
    """显示 Run 生命周期记录（含 CANCELLED / INTERRUPTED 等完整状态）。"""

    if not runs:
        print("暂无 Run 记录。")
        return
    for run in runs:
        marker = "*" if run.conversation_id == current_conversation_id else " "
        created_at = run.created_at.astimezone().strftime("%m-%d %H:%M:%S")
        stop_reason = run.stop_reason or "-"
        print(
            f"{marker} {run.id[:8]}  {created_at}  "
            f"{run.status.value:<11} reason={stop_reason}"
        )

def _print_run_detail(run: Run) -> None:
    """显示单个 Run 的生命周期详情。"""

    if run is None:
        print("找不到 Run。")
        return
    started = (
        run.started_at.astimezone().strftime("%m-%d %H:%M:%S")
        if run.started_at is not None
        else "-"
    )
    completed = (
        run.completed_at.astimezone().strftime("%m-%d %H:%M:%S")
        if run.completed_at is not None
        else "-"
    )
    print(f"Run {run.id}")
    print(f"  conversation_id: {run.conversation_id or '-'}")
    print(f"  status: {run.status.value}")
    print(f"  created_at: {run.created_at.astimezone().strftime('%m-%d %H:%M:%S')}")
    print(f"  started_at: {started}")
    print(f"  completed_at: {completed}")
    print(f"  stop_reason: {run.stop_reason or '-'}")
    if run.error:
        print(f"  error: {run.error}")
    if run.recovered_from_run_id:
        print(f"  recovered_from: {run.recovered_from_run_id[:8]}")
    print(f"  user_message: {(run.user_message or '')[:120]}")

def _print_automations(automations: tuple[object, ...]) -> None:
    """显示自动化列表。"""

    if not automations:
        print("暂无 Automation。")
        return
    for item in automations:
        next_run = (
            item.next_run_at.astimezone().strftime("%m-%d %H:%M")
            if item.next_run_at is not None
            else "-"
        )
        print(
            f"{item.id[:8]}  {item.title[:24]:<24}  "
            f"{item.status.value:<9} next={next_run}"
        )

def _print_automation(automation: object) -> None:
    """显示单个自动化详情。"""

    if automation is None:
        print("找不到 Automation。")
        return
    schedule = automation.schedule
    print(f"Automation {automation.id}")
    print(f"  title: {automation.title}")
    print(f"  status: {automation.status.value}")
    print(f"  kind: {schedule.kind.value}")
    if schedule.kind.value == "once":
        print(f"  run_at: {schedule.run_at}")
    elif schedule.kind.value == "interval":
        print(f"  interval_seconds: {schedule.interval_seconds}")
    else:
        print(f"  cron_expr: {schedule.cron_expr}")
    print(f"  timezone: {schedule.timezone}")
    print(f"  conversation_id: {automation.conversation_id or '-'}")
    next_run = (
        automation.next_run_at.astimezone().strftime("%m-%d %H:%M:%S")
        if automation.next_run_at is not None
        else "-"
    )
    print(f"  next_run_at: {next_run}")
    print(f"  last_run_id: {automation.last_run_id or '-'}")
    print(f"  prompt: {(automation.prompt or '')[:160]}")

def _print_checkpoints(checkpoints: tuple[RunCheckpoint, ...]) -> None:
    """显示当前会话最近的恢复边界。"""

    if not checkpoints:
        print("当前会话暂无 Checkpoint。")
        return
    for checkpoint in checkpoints:
        updated_at = checkpoint.updated_at.astimezone().strftime("%m-%d %H:%M:%S")
        pending = len(checkpoint.pending_tool_calls)
        print(
            f"{checkpoint.run_id[:8]}  {updated_at}  "
            f"{checkpoint.status.value:<11} phase={checkpoint.phase.value} "
            f"step={checkpoint.step} pending_tools={pending}"
        )

def _print_mcp_statuses(statuses: tuple[MCPServerStatus, ...]) -> None:
    """显示 MCP Server 状态和已注册工具。"""

    if not statuses:
        print("尚未配置 MCP Server。")
        return
    for status in statuses:
        marker = "✓" if status.state is MCPServerState.RUNNING else "-"
        print(f"{marker} {status.name} · {status.state.value}")
        if status.error:
            print(f"  错误：{status.error}")
        for tool_name in status.tool_names:
            print(f"  - {tool_name}")

def _print_recovered_runs(runs: tuple[Run, ...]) -> None:
    """展示启动 reconciliation / 会话切换发现的未正常结束 Run（只读展示）。"""

    for run in runs:
        if run.status is RunStatus.INTERRUPTED:
            print(
                f"检测到中断 Run：{run.id[:8]} · 可恢复 "
                f"（/run recover {run.id[:8]} 继续执行）"
            )
        else:
            print(
                f"Run 状态修正：{run.id[:8]} RUNNING → {run.status.value}"
                + (f" · {run.error}" if run.error else "")
            )

def _print_trace(events: tuple[AgentEvent, ...]) -> None:
    """显示一次 Run 的完整事件时间线。"""

    for event in events:
        event_time = event.event_time.astimezone().strftime("%H:%M:%S.%f")[:-3]
        details: list[str] = []
        if event.step is not None:
            details.append(f"step={event.step}")
        if event.tool_call is not None:
            details.append(f"tool={event.tool_call.name}")
        if event.approval_decision is not None:
            details.append(f"decision={event.approval_decision.value}")
        if event.rule_id is not None:
            details.append(f"rule={event.rule_id[:8]}")
        if event.tool_result is not None:
            details.append(
                f"success={'true' if event.tool_result.success else 'false'}"
            )
        if event.type is AgentEventType.MODEL_STARTED:
            if event.prepared_input_tokens is not None:
                details.append(f"input≈{event.prepared_input_tokens}")
            if event.tool_schema_tokens is not None:
                details.append(f"schemas≈{event.tool_schema_tokens}")
            if (
                event.tool_result_tokens_before is not None
                and event.tool_result_tokens_after is not None
            ):
                details.append(
                    "tool_results≈"
                    f"{event.tool_result_tokens_before}→"
                    f"{event.tool_result_tokens_after}"
                )
            if event.compaction_stage not in (None, "none"):
                details.append(f"context={event.compaction_stage}")
            if event.summary_provider is not None:
                details.append(
                    "summary="
                    f"{event.summary_provider}/{event.summary_model or 'default'}"
                )
            if event.summary_duration_ms is not None:
                details.append(f"summary_ms={event.summary_duration_ms:.1f}")
        if event.run_budget_status is not None:
            details.append(
                f"budget={event.run_budget_status}:"
                f"{event.run_budget_chargeable_tokens or 0}t/"
                f"{event.run_budget_model_calls or 0}calls"
            )
        detail_text = f"  {' '.join(details)}" if details else ""
        print(f"{event.sequence:03d}  {event_time}  {event.type.value}{detail_text}")

def _print_skill_candidates(candidates: tuple[SkillCandidate, ...]) -> None:
    """输出 Skill Learning 候选列表。"""

    if not candidates:
        print("没有 Skill Learning 候选。")
        return
    for candidate in candidates:
        print(
            f"{candidate.id}  [{candidate.status.value}] "
            f"{candidate.action.value.upper()} {candidate.proposed_name} "
            f"· 来源 {len(candidate.source_task_ids)} Task"
        )

def _print_permission_rules(rules: tuple[PermissionRule, ...]) -> None:
    """显示当前会话记住的工具审批规则。"""

    if not rules:
        print("当前会话没有已记住的审批规则。")
        return
    for rule in rules:
        created_at = rule.created_at.astimezone().strftime("%m-%d %H:%M:%S")
        print(f"{rule.id[:8]}  {created_at}  {rule.tool_name}  {rule.description}")

def _print_memories(memories: Sequence[MemoryRecord]) -> None:
    """输出适合终端快速浏览的长期记忆列表（Recall Cue）。"""

    if not memories:
        print("没有长期记忆。")
        return
    for memory in memories:
        cue = " ".join(memory.summary.split())
        print(f"{memory.id}  [{memory.status.value}]  {memory.title}")
        print(f"  Cue: {cue}")

def _print_memory(memory: MemoryRecord) -> None:
    """输出单条长期记忆的完整内容。"""

    print(
        f"ID: {memory.id}\n"
        f"状态: {memory.status.value}\n"
        f"标题: {memory.title}\n"
        f"访问次数: {memory.access_count}\n"
        f"创建时间: {memory.created_at.astimezone().isoformat()}\n"
        f"内容:\n{memory.render_full()}"
    )
