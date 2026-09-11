from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agent.events import AgentEvent, AgentEventType
from app.agent.result import AgentError, AgentResult, AgentStopReason
from app.models.types import Message, MessageRole, ModelUsage, ToolCall
from app.tools.approval import ApprovalDecision
from app.trace import RunStatus, SQLiteTraceEventHandler, SQLiteTraceStore


def _trace_events() -> tuple[AgentEvent, ...]:
    started_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    tool_call = ToolCall(
        id="call-1",
        name="run_shell_command",
        arguments={"command": "pwd"},
    )
    final_message = Message(role=MessageRole.ASSISTANT, content="完成")
    usage = ModelUsage(input_tokens=20, output_tokens=5, total_tokens=25)
    result = AgentResult(
        run_id="run-trace-1",
        final_message=final_message,
        messages=(final_message,),
        steps=1,
        stop_reason=AgentStopReason.FINAL_ANSWER,
        usage=usage,
    )
    return (
        AgentEvent(
            run_id=result.run_id,
            conversation_id="conversation-1",
            sequence=0,
            type=AgentEventType.AGENT_STARTED,
            event_time=started_at,
            provider="fake",
            model="fake-model",
        ),
        AgentEvent(
            run_id=result.run_id,
            conversation_id="conversation-1",
            sequence=1,
            type=AgentEventType.TOOL_APPROVAL_REQUIRED,
            event_time=started_at + timedelta(milliseconds=1),
            step=1,
            tool_call=tool_call,
        ),
        AgentEvent(
            run_id=result.run_id,
            conversation_id="conversation-1",
            sequence=2,
            type=AgentEventType.TOOL_APPROVAL_COMPLETED,
            event_time=started_at + timedelta(milliseconds=2),
            step=1,
            tool_call=tool_call,
            approval_decision=ApprovalDecision.APPROVED,
        ),
        AgentEvent(
            run_id=result.run_id,
            conversation_id="conversation-1",
            sequence=3,
            type=AgentEventType.AGENT_COMPLETED,
            event_time=started_at + timedelta(milliseconds=3),
            step=1,
            provider="fake",
            model="fake-model",
            message=final_message,
            usage=usage,
            stop_reason=result.stop_reason,
            result=result,
        ),
    )


@pytest.mark.asyncio
async def test_trace_handler_does_not_persist_text_deltas(tmp_path) -> None:
    store = SQLiteTraceStore(tmp_path / "stream.db")
    await store.initialize()
    handler = SQLiteTraceEventHandler(store)

    await handler.emit(
        AgentEvent(
            run_id="run-stream",
            sequence=1,
            type=AgentEventType.MODEL_OUTPUT_DELTA,
            step=1,
            delta="partial",
        )
    )

    assert await store.get("run-stream") is None


@pytest.mark.asyncio
async def test_trace_survives_restart_and_restores_complete_events(tmp_path) -> None:
    database_path = tmp_path / "vesta.db"
    store = SQLiteTraceStore(database_path)
    await store.initialize()
    events = _trace_events()
    for event in events:
        await store.record_event(event)

    reopened = SQLiteTraceStore(database_path)
    await reopened.initialize()
    run = await reopened.get("run-trace-1")

    assert run is not None
    assert run.status is RunStatus.COMPLETED
    assert run.conversation_id == "conversation-1"
    assert run.steps == 1
    assert run.stop_reason is AgentStopReason.FINAL_ANSWER
    assert run.total_tokens == 25
    assert run.event_count == 4
    assert await reopened.load_events(run.run_id) == events
    assert await reopened.resolve("run-tr") == run


@pytest.mark.asyncio
async def test_trace_recording_is_idempotent_and_does_not_regress_status(
    tmp_path,
) -> None:
    store = SQLiteTraceStore(tmp_path / "vesta.db")
    await store.initialize()
    events = _trace_events()
    for event in events:
        await store.record_event(event)
    await store.record_event(events[0])

    run = await store.get("run-trace-1")

    assert run is not None
    assert run.status is RunStatus.COMPLETED
    assert run.event_count == 4
    assert len(await store.list_runs(conversation_id="conversation-1")) == 1


@pytest.mark.asyncio
async def test_memory_post_run_events_do_not_overwrite_main_model_or_usage(
    tmp_path,
) -> None:
    store = SQLiteTraceStore(tmp_path / "vesta.db")
    await store.initialize()
    started_at = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)
    await store.record_event(
        AgentEvent(
            run_id="run-reflection",
            sequence=0,
            type=AgentEventType.MODEL_COMPLETED,
            event_time=started_at,
            step=1,
            provider="main",
            model="main-model",
            usage=ModelUsage(
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
            ),
        )
    )
    await store.record_event(
        AgentEvent(
            run_id="run-reflection",
            sequence=1,
            type=AgentEventType.MEMORY_REFLECTION_COMPLETED,
            event_time=started_at + timedelta(milliseconds=1),
            provider="cheap",
            model="memory-model",
            usage=ModelUsage(
                input_tokens=300,
                output_tokens=30,
                total_tokens=330,
            ),
            reflection_triggered=True,
            reflection_action="none",
        )
    )
    await store.record_event(
        AgentEvent(
            run_id="run-reflection",
            sequence=2,
            type=AgentEventType.MEMORY_MAINTENANCE_COMPLETED,
            event_time=started_at + timedelta(milliseconds=2),
            provider="cheap",
            model="maintenance-model",
            usage=ModelUsage(
                input_tokens=400,
                output_tokens=40,
                total_tokens=440,
            ),
            maintenance_triggered=True,
            maintenance_action="defer",
        )
    )
    await store.record_event(
        AgentEvent(
            run_id="run-reflection",
            sequence=3,
            type=AgentEventType.AGENT_COMPLETED,
            event_time=started_at + timedelta(milliseconds=3),
            step=1,
            stop_reason=AgentStopReason.FINAL_ANSWER,
        )
    )

    run = await store.get("run-reflection")

    assert run is not None
    assert run.provider == "main"
    assert run.model == "main-model"
    assert run.total_tokens == 120
    assert run.event_count == 4


@pytest.mark.asyncio
async def test_trace_delete_removes_run_and_events(tmp_path) -> None:
    store = SQLiteTraceStore(tmp_path / "vesta.db")
    await store.initialize()
    for event in _trace_events():
        await store.record_event(event)

    assert await store.delete("run-trace-1") is True
    assert await store.delete("run-trace-1") is False
    assert await store.get("run-trace-1") is None
    with pytest.raises(KeyError, match="Run 不存在"):
        await store.load_events("run-trace-1")


@pytest.mark.asyncio
async def test_failed_event_marks_trace_as_failed(tmp_path) -> None:
    store = SQLiteTraceStore(tmp_path / "vesta.db")
    await store.initialize()
    final_message = Message(role=MessageRole.ASSISTANT, content="模型调用失败")
    error = AgentError(type="ModelInvocationError", message="连接失败")
    result = AgentResult(
        run_id="run-failed",
        final_message=final_message,
        messages=(final_message,),
        steps=1,
        stop_reason=AgentStopReason.MODEL_ERROR,
        error=error,
    )
    await store.record_event(
        AgentEvent(
            run_id=result.run_id,
            type=AgentEventType.AGENT_FAILED,
            step=1,
            message=final_message,
            stop_reason=result.stop_reason,
            error=error,
            result=result,
        )
    )

    run = await store.get(result.run_id)

    assert run is not None
    assert run.status is RunStatus.FAILED
    assert run.stop_reason is AgentStopReason.MODEL_ERROR
    assert run.completed_at is not None


@pytest.mark.asyncio
async def test_cancelled_event_marks_trace_as_cancelled(tmp_path) -> None:
    """AGENT_CANCELLED 终态：Trace 状态与 RunStore 的 cancelled 保持一致。"""

    store = SQLiteTraceStore(tmp_path / "vesta.db")
    await store.initialize()
    cancelled_message = Message(role=MessageRole.ASSISTANT, content="已取消")
    result = AgentResult(
        run_id="run-cancelled",
        final_message=cancelled_message,
        messages=(cancelled_message,),
        steps=0,
        stop_reason=AgentStopReason.CANCELLED,
    )
    await store.record_event(
        AgentEvent(
            run_id=result.run_id,
            type=AgentEventType.AGENT_CANCELLED,
            message=cancelled_message,
            stop_reason=result.stop_reason,
            result=result,
        )
    )

    run = await store.get(result.run_id)

    assert run is not None
    assert run.status is RunStatus.CANCELLED
    assert run.stop_reason is AgentStopReason.CANCELLED
    assert run.completed_at is not None


@pytest.mark.asyncio
async def test_failed_event_with_interrupted_reason_marks_interrupted(
    tmp_path,
) -> None:
    """AGENT_FAILED + stop_reason=interrupted：Trace 记为 interrupted。"""

    store = SQLiteTraceStore(tmp_path / "vesta.db")
    await store.initialize()
    interrupted_message = Message(role=MessageRole.ASSISTANT, content="已中断")
    result = AgentResult(
        run_id="run-interrupted",
        final_message=interrupted_message,
        messages=(interrupted_message,),
        steps=0,
        stop_reason=AgentStopReason.INTERRUPTED,
    )
    await store.record_event(
        AgentEvent(
            run_id=result.run_id,
            type=AgentEventType.AGENT_FAILED,
            message=interrupted_message,
            stop_reason=result.stop_reason,
            result=result,
        )
    )

    run = await store.get(result.run_id)

    assert run is not None
    assert run.status is RunStatus.INTERRUPTED
    assert run.stop_reason is AgentStopReason.INTERRUPTED


@pytest.mark.asyncio
async def test_next_sequence_allocates_after_persisted_events(tmp_path) -> None:
    """next_sequence 从已持久化最大序号继续：补发终态不撞 UNIQUE 约束。"""

    store = SQLiteTraceStore(tmp_path / "vesta.db")
    await store.initialize()

    # 无事件的新 Run：序号从 0 开始。
    assert await store.next_sequence("run-next") == 0

    started_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    for sequence in (0, 1, 2):
        await store.record_event(
            AgentEvent(
                run_id="run-next",
                sequence=sequence,
                type=AgentEventType.AGENT_STARTED,
                event_time=started_at + timedelta(milliseconds=sequence),
            )
        )

    assert await store.next_sequence("run-next") == 3

    # 用分配到的序号补发取消终态：事件必须落库（不被 IGNORE 丢弃）。
    await store.record_event(
        AgentEvent(
            run_id="run-next",
            sequence=await store.next_sequence("run-next"),
            type=AgentEventType.AGENT_CANCELLED,
            event_time=started_at + timedelta(milliseconds=10),
        )
    )
    events = await store.load_events("run-next")
    assert [event.sequence for event in events] == [0, 1, 2, 3]
    assert events[-1].type is AgentEventType.AGENT_CANCELLED
    run = await store.get("run-next")
    assert run is not None
    assert run.status is RunStatus.CANCELLED
