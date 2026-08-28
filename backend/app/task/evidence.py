"""Task 与不可变 Evidence 之间的只读归因适配器。"""

from __future__ import annotations

from app.evidence import EvidenceAttribution

from .models import TaskStepStatus
from .store import FileTaskStore


class TaskEvidenceAttributionResolver:
    """把工具输出关联到当前活动 Task 与唯一执行中 Step。"""

    def __init__(self, store: FileTaskStore) -> None:
        self._store = store

    async def resolve(self, conversation_id: str) -> EvidenceAttribution:
        task = await self._store.active_for_conversation(conversation_id)
        if task is None:
            return EvidenceAttribution()
        step = next(
            (
                item
                for item in task.steps
                if item.status is TaskStepStatus.IN_PROGRESS
            ),
            None,
        )
        return EvidenceAttribution(
            task_id=task.id,
            task_step_id=step.id if step is not None else None,
        )


__all__ = ["TaskEvidenceAttributionResolver"]
