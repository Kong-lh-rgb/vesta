"""通过生产 TaskStore 接口预置 Eval Task。"""

from __future__ import annotations

from collections.abc import Sequence

from app.task import FileTaskStore, Task, TaskPatch, TaskStatus, TaskStep

from .scenario import InitialTask


async def create_initial_task(
    store: FileTaskStore,
    spec: InitialTask,
    *,
    owner_conversation_id: str,
    steps: Sequence[TaskStep],
) -> Task:
    """完整写入场景 Task，并复用生产领域层的原子更新路径。"""

    task = await store.create(
        title=spec.title,
        description=spec.description,
        goal=spec.goal,
        steps=steps,
        owner_conversation_id=spec.owner or owner_conversation_id,
        run_ids=spec.run_ids,
    )
    patch = TaskPatch(
        status=(
            spec.status if spec.status is not TaskStatus.PENDING else None
        ),
        add_constraints=spec.constraints,
        add_key_facts=spec.key_facts,
    )
    if patch.has_changes:
        task = await store.apply_patch(task.id, patch)
    return task


__all__ = ["create_initial_task"]
