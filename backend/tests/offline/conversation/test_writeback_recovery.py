"""Conversation writeback survives DB failures and Host restarts."""

from __future__ import annotations

import pytest

from app.agent.events import AgentEvent, AgentEventType
from app.agent.result import AgentResult, AgentStopReason
from app.checkpoint import SQLiteCheckpointStore
from app.context import (
    ConversationSummaryState,
    RollingConversationSummary,
    SQLiteConversationSummaryStore,
)
from app.conversation import SQLiteConversationStore
from app.conversation.service import ConversationService
from app.models.types import Message, MessageRole
from app.run import RunManager, SQLiteRunStore
from app.trace import SQLiteTraceStore


async def _stores(tmp_path):
    database = tmp_path / "vesta.db"
    conversation_store = SQLiteConversationStore(database)
    summary_store = SQLiteConversationSummaryStore(database)
    run_store = SQLiteRunStore(database)
    trace_store = SQLiteTraceStore(database)
    checkpoint_store = SQLiteCheckpointStore(database)
    for store in (
        conversation_store,
        summary_store,
        run_store,
        trace_store,
        checkpoint_store,
    ):
        await store.initialize()
    return conversation_store, summary_store, run_store, trace_store, checkpoint_store


async def test_writeback_transaction_rolls_back_and_retries(
    tmp_path, monkeypatch
) -> None:
    conversations, summaries, runs, _, _ = await _stores(tmp_path)
    original = Message(role=MessageRole.USER, content="old")
    conversation = await conversations.create(messages=(original,))
    run = await runs.create(
        conversation_id=conversation.id,
        user_message="new",
        needs_writeback=True,
    )
    state = ConversationSummaryState(
        summary=RollingConversationSummary(current_objective="new task"),
        covered_message_count=2,
    )
    result = AgentResult(
        run_id=run.id,
        final_message=Message(role=MessageRole.ASSISTANT, content="done"),
        messages=(
            original,
            Message(role=MessageRole.USER, content="new"),
            Message(role=MessageRole.ASSISTANT, content="done"),
        ),
        stop_reason=AgentStopReason.FINAL_ANSWER,
        summary_state=state,
    )
    insert_messages = SQLiteConversationStore._insert_messages

    async def fail_after_delete(*_args) -> None:
        raise OSError("injected write failure")

    monkeypatch.setattr(
        SQLiteConversationStore, "_insert_messages", staticmethod(fail_after_delete)
    )
    with pytest.raises(OSError, match="injected write failure"):
        await conversations.commit_run_writeback(run.id, conversation.id, result)
    assert await conversations.load_messages(conversation.id) == (original,)
    assert await runs.list_pending_writebacks(conversation.id) == (run,)
    assert await summaries.load(conversation.id) is None

    monkeypatch.setattr(
        SQLiteConversationStore, "_insert_messages", staticmethod(insert_messages)
    )
    assert await conversations.commit_run_writeback(run.id, conversation.id, result)
    assert not await conversations.commit_run_writeback(run.id, conversation.id, result)
    assert await conversations.load_messages(conversation.id) == result.messages
    assert await summaries.load(conversation.id) == state
    assert await runs.list_pending_writebacks(conversation.id) == ()


async def test_startup_replays_terminal_trace_without_overwriting_again(
    tmp_path,
) -> None:
    conversations, summaries, runs, traces, checkpoints = await _stores(tmp_path)
    conversation = await conversations.create()
    run = await runs.create(
        conversation_id=conversation.id,
        user_message="question",
        needs_writeback=True,
    )
    await runs.mark_started(run.id)
    final = Message(role=MessageRole.ASSISTANT, content="answer")
    result = AgentResult(
        run_id=run.id,
        final_message=final,
        messages=(Message(role=MessageRole.USER, content="question"), final),
        stop_reason=AgentStopReason.FINAL_ANSWER,
    )
    await traces.record_event(
        AgentEvent(
            run_id=run.id,
            conversation_id=conversation.id,
            type=AgentEventType.AGENT_COMPLETED,
            result=result,
        )
    )
    await runs.mark_completed(run.id)
    manager = RunManager(runs, checkpoints, object())  # type: ignore[arg-type]
    service = ConversationService(
        conversations, manager, traces, summary_store=summaries
    )

    await service.reconcile_all_writebacks()
    assert await conversations.load_messages(conversation.id) == result.messages
    assert await runs.list_pending_writebacks(conversation.id) == ()
    await service.reconcile_all_writebacks()
    assert await conversations.load_messages(conversation.id) == result.messages


async def test_interrupted_run_without_final_event_keeps_user_input(tmp_path) -> None:
    conversations, _, runs, traces, checkpoints = await _stores(tmp_path)
    conversation = await conversations.create()
    run = await runs.create(
        conversation_id=conversation.id,
        user_message="unfinished request",
        needs_writeback=True,
    )
    await runs.mark_started(run.id)
    await runs.mark_interrupted(run.id, error="private diagnostic")
    manager = RunManager(runs, checkpoints, object())  # type: ignore[arg-type]
    service = ConversationService(conversations, manager, traces)

    await service.reconcile_pending_writebacks(conversation.id)
    messages = await conversations.load_messages(conversation.id)
    assert [message.role for message in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert messages[0].content == "unfinished request"
    assert "private diagnostic" not in (messages[1].content or "")
    assert await runs.list_pending_writebacks(conversation.id) == ()


async def test_pending_active_run_blocks_new_conversation_work(tmp_path) -> None:
    conversations, _, runs, traces, checkpoints = await _stores(tmp_path)
    conversation = await conversations.create()
    await runs.create(conversation_id=conversation.id, needs_writeback=True)
    manager = RunManager(runs, checkpoints, object())  # type: ignore[arg-type]
    service = ConversationService(conversations, manager, traces)

    with pytest.raises(RuntimeError, match="previous run is still active"):
        await service.reconcile_pending_writebacks(conversation.id)
    assert len(await runs.list_pending_writebacks(conversation.id)) == 1
