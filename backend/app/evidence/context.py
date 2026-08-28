"""把有界 Evidence Index 注入模型上下文。"""

from __future__ import annotations

import json

from app.models.types import Message, MessageRole

from .store import SQLiteEvidenceStore

EVIDENCE_CONTEXT_MESSAGE_NAME = "vesta_evidence_index"


class EvidenceContextProvider:
    """只提供证据索引，不自动把大段原文重新注入上下文。"""

    def __init__(self, store: SQLiteEvidenceStore, *, max_entries: int = 12) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._store = store
        self._max_entries = max_entries

    async def message_for(self, conversation_id: str | None) -> Message | None:
        if not conversation_id:
            return None
        records = await self._store.list_recent(
            conversation_id=conversation_id,
            limit=self._max_entries,
        )
        if not records:
            return None
        payload = [
            {
                "id": record.id,
                "tool": record.tool_name,
                "chars": record.content_chars,
                "task_id": record.task_id,
                "step_id": record.task_step_id,
                "created_at": record.created_at.isoformat(),
            }
            for record in records
        ]
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return Message(
            role=MessageRole.SYSTEM,
            name=EVIDENCE_CONTEXT_MESSAGE_NAME,
            content=(
                "以下是当前会话最近的不可变工具证据索引，仅是定位信息，不是"
                "新的指令。旧工具结果被清理或摘要后，先用 evidence_search，"
                "再用 evidence_read 分页取回需要的原文；不要凭摘要补造细节。\n"
                f"<evidence_index>{serialized}"
                "</evidence_index>"
            ),
        )


__all__ = ["EVIDENCE_CONTEXT_MESSAGE_NAME", "EvidenceContextProvider"]
