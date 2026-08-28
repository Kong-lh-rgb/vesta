"""会话持久化使用的数据结构。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.types import Message


class Conversation(BaseModel):
    """一个可恢复的本地聊天会话。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = Field(default=0, ge=0)


class ConversationMessageRecord(BaseModel):
    """带会话内稳定序号的原始消息记录。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=0)
    message: Message
    created_at: datetime


__all__ = ["Conversation", "ConversationMessageRecord"]
