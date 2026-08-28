"""把工具原始输出写入 Evidence Store。"""

from __future__ import annotations

import logging
from hashlib import sha256

from app.tools.hooks import ToolExecutionContext
from app.tools.output import (
    RecordedToolOutput,
    ToolOutputAttribution,
    ToolOutputAttributionResolver,
)

from .store import SQLiteEvidenceStore

logger = logging.getLogger("vesta.evidence.recorder")


class EvidenceRecorder:
    """在模型预览截断前保存可复查的外部/工具事实。"""

    def __init__(
        self,
        store: SQLiteEvidenceStore,
        *,
        attribution_resolver: ToolOutputAttributionResolver | None = None,
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
        definition = context.tool_definition
        if definition is not None and not definition.record_output:
            return None
        attribution = ToolOutputAttribution()
        if self._attribution_resolver is not None:
            try:
                attribution = await self._attribution_resolver.resolve(
                    context.conversation_id
                )
            except Exception as exc:
                # 归因只是可选元数据；Task 扫描失败不能阻止原始证据落盘。
                logger.warning(
                    "Evidence attribution failed conversation_id=%s error=%s: %s",
                    context.conversation_id,
                    type(exc).__name__,
                    exc,
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
    "EvidenceRecorder",
]
