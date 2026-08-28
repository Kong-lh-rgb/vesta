"""工具原始输出持久化的最小协议。

ToolExecutor 只依赖这个中立协议，不直接依赖 Evidence 的存储实现。这样工具层
继续负责统一执行边界，Evidence 层负责不可变持久化，Application 负责装配。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .hooks import ToolExecutionContext


@dataclass(frozen=True, slots=True)
class RecordedToolOutput:
    """一次成功归档后的稳定引用。"""

    id: str
    content_chars: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ToolOutputAttribution:
    """工具输出所属的可选工作位置，不依赖具体 Evidence 实现。"""

    task_id: str | None = None
    task_step_id: str | None = None


class ToolOutputAttributionResolver(Protocol):
    """从 Harness 上下文解析工具输出归因。"""

    async def resolve(
        self,
        conversation_id: str,
    ) -> ToolOutputAttribution:
        """解析当前会话的活动工作位置。"""


class ToolOutputRecorder(Protocol):
    """在模型可见截断发生前保存工具原始输出。"""

    async def record(
        self,
        context: ToolExecutionContext,
        content: str,
    ) -> RecordedToolOutput | None:
        """保存输出；明确不需要归档时返回 None。"""


__all__ = [
    "RecordedToolOutput",
    "ToolOutputAttribution",
    "ToolOutputAttributionResolver",
    "ToolOutputRecorder",
]
