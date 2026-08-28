from __future__ import annotations

import pytest

from app.conversation import SQLiteConversationStore
from app.conversation.tools import HistoryReadTool, HistorySearchTool
from app.models.types import Message, MessageRole, ToolCall
from app.tools import ToolExecutionContext


@pytest.mark.asyncio
async def test_history_search_and_read_use_raw_current_conversation(tmp_path) -> None:
    store = SQLiteConversationStore(tmp_path / "vesta.db")
    await store.initialize()
    first = await store.create(
        messages=(
            Message(role=MessageRole.USER, content="项目必须使用中文注释"),
            Message(role=MessageRole.ASSISTANT, content="已记录这个约束"),
            Message(role=MessageRole.USER, content="继续开发"),
        )
    )
    await store.create(
        messages=(Message(role=MessageRole.USER, content="另一个会话也有中文"),)
    )
    call = ToolCall(id="history", name="history_search", arguments={})
    context = ToolExecutionContext(
        tool_call=call,
        conversation_id=first.id,
    )

    searched = await HistorySearchTool(store).execute_with_context(
        {"query": "中文"},
        context,
    )
    window = await HistoryReadTool(store).execute_with_context(
        {"sequence": searched["results"][0]["sequence"], "before": 0, "after": 1},
        context,
    )

    assert searched["count"] == 1
    assert "必须使用中文注释" in searched["results"][0]["content"]
    assert [item["sequence"] for item in window["messages"]] == [0, 1]


@pytest.mark.asyncio
async def test_history_tool_rejects_missing_conversation_context(tmp_path) -> None:
    store = SQLiteConversationStore(tmp_path / "vesta.db")
    await store.initialize()
    call = ToolCall(id="history", name="history_search", arguments={})

    with pytest.raises(ValueError, match="conversation context"):
        await HistorySearchTool(store).execute_with_context(
            {"query": "anything"},
            ToolExecutionContext(tool_call=call),
        )
