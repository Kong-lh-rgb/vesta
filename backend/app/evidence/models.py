"""不可变工具证据的数据结构。"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvidenceRecord(BaseModel):
    """一份工具原始输出的不可变元数据。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    conversation_id: str
    run_id: str
    tool_call_id: str
    tool_name: str
    content_type: str = "text/plain; charset=utf-8"
    content_chars: int = Field(ge=0)
    content_bytes: int = Field(ge=0)
    sha256: str
    task_id: str | None = None
    task_step_id: str | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evidence created_at must include timezone")
        return value.astimezone(UTC)


class EvidenceDocument(BaseModel):
    """证据元数据与完整原始正文。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record: EvidenceRecord
    content: str


class EvidenceSearchHit(BaseModel):
    """面向模型的有界搜索结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record: EvidenceRecord
    snippet: str


__all__ = ["EvidenceDocument", "EvidenceRecord", "EvidenceSearchHit"]
