"""把工具原始输出写入 Evidence Store。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from app.tools.hooks import ToolExecutionContext
from app.tools.output import RecordedToolOutput

from .store import SQLiteEvidenceStore


@dataclass(frozen=True, slots=True)
class EvidenceAttribution:
    """工具证据在记录时所属的活动任务与步骤。"""

    task_id: str | None = None
    task_step_id: str | None = None


class EvidenceAttributionResolver(Protocol):
    async def resolve(
        self,
        conversation_id: str,
    ) -> EvidenceAttribution:
        """解析当前会话的活动工作位置。"""


_SKIPPED_PREFIXES = (
    "evidence_",
    "history_",
    "task_",
    "memory_",
    "core_memory_",
    "skill_",
    "artifact_",
    "automation_",
)
_SKIPPED_NAMES = frozenset({"tool_search", "current_time", "mcp_status"})


class EvidenceRecorder:
    """在模型预览截断前保存可复查的外部/工具事实。"""

    def __init__(
        self,
        store: SQLiteEvidenceStore,
        *,
        attribution_resolver: EvidenceAttributionResolver | None = None,
    ) -> None:
        self._store = store
        self._attribution_resolver = attribution_resolver

    async def record(
        self,
        context: ToolExecutionContext,
        content: str,
    ) -> RecordedToolOutput | None:
        if not context.run_id or not context.conversation_id:
            return None
        tool_name = context.tool_call.name
        if tool_name in _SKIPPED_NAMES or tool_name.startswith(_SKIPPED_PREFIXES):
            return None
        attribution = EvidenceAttribution()
        if self._attribution_resolver is not None:
            attribution = await self._attribution_resolver.resolve(
                context.conversation_id
            )
        digest = sha256(content.encode("utf-8")).hexdigest()
        record = await self._store.create(
            conversation_id=context.conversation_id,
            run_id=context.run_id,
            tool_call_id=context.tool_call.id,
            tool_name=tool_name,
            content=content,
            sha256=digest,
            task_id=attribution.task_id,
            task_step_id=attribution.task_step_id,
        )
        return RecordedToolOutput(
            id=record.id,
            content_chars=record.content_chars,
            sha256=record.sha256,
        )


__all__ = [
    "EvidenceAttribution",
    "EvidenceAttributionResolver",
    "EvidenceRecorder",
]
