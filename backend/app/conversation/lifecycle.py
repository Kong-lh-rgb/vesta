"""会话删除生命周期：停止工作并清理所有会话私有数据。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.agent.post_run_processor import PostRunProcessor
from app.approval import SQLiteApprovalStore
from app.artifact import ArtifactService
from app.automation import AutomationScheduler
from app.checkpoint import SQLiteCheckpointStore
from app.evidence import SQLiteEvidenceStore
from app.run import RunManager, SQLiteRunStore
from app.task import FileTaskStore
from app.tools import ApprovalScope, PermissionRuleStore
from app.trace import SQLiteTraceStore

from .coordinator import ConversationOperationCoordinator
from .store import SQLiteConversationStore

_HEX_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_EMBEDDED_ID_RE = re.compile(
    r'["\'](?:id|screenshot_ref)["\']\s*:\s*["\'](?:[^"\']*/)?'
    r"([0-9a-f]{32})(?:\.png)?[\"']"
)


class ConversationDeletionResult(BaseModel):
    """一次硬删除的可观测结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str
    deleted: bool = True
    cancelled_runs: int = Field(default=0, ge=0)
    cancelled_post_run_jobs: int = Field(default=0, ge=0)
    deleted_automations: int = Field(default=0, ge=0)
    deleted_approvals: int = Field(default=0, ge=0)
    deleted_permission_rules: int = Field(default=0, ge=0)
    deleted_tasks: int = Field(default=0, ge=0)
    deleted_artifacts: int = Field(default=0, ge=0)
    deleted_evidence: int = Field(default=0, ge=0)
    deleted_checkpoints: int = Field(default=0, ge=0)
    deleted_traces: int = Field(default=0, ge=0)
    deleted_runs: int = Field(default=0, ge=0)
    deleted_screenshots: int = Field(default=0, ge=0)
    # V1 采用本地硬删除，不保留会话级审计副本。
    audit_records_retained: bool = False


class ConversationLifecycleService:
    """统一收口会话硬删除，避免 RPC 层逐项拼装清理流程。

    Memory、已接受 Skill 与 workspace 源文件是跨会话或用户拥有的数据，不随
    会话删除；会话私有的运行、审计、恢复、任务与托管交付物则全部删除。
    """

    def __init__(
        self,
        conversation_store: SQLiteConversationStore,
        operation_coordinator: ConversationOperationCoordinator,
        run_manager: RunManager,
        run_store: SQLiteRunStore,
        checkpoint_store: SQLiteCheckpointStore,
        trace_store: SQLiteTraceStore,
        evidence_store: SQLiteEvidenceStore,
        approval_store: SQLiteApprovalStore,
        artifact_service: ArtifactService,
        task_store: FileTaskStore,
        permission_rule_store: PermissionRuleStore,
        automation_scheduler: AutomationScheduler,
        post_run_processor: PostRunProcessor,
        *,
        screenshot_dir: str | Path | None = None,
    ) -> None:
        self._conversation_store = conversation_store
        self._operations = operation_coordinator
        self._run_manager = run_manager
        self._run_store = run_store
        self._checkpoint_store = checkpoint_store
        self._trace_store = trace_store
        self._evidence_store = evidence_store
        self._approval_store = approval_store
        self._artifact_service = artifact_service
        self._task_store = task_store
        self._permission_rule_store = permission_rule_store
        self._automation_scheduler = automation_scheduler
        self._post_run_processor = post_run_processor
        self._screenshot_dir = (
            Path(screenshot_dir).expanduser().resolve()
            if screenshot_dir is not None
            else None
        )

    async def delete(
        self,
        conversation_id: str,
    ) -> ConversationDeletionResult | None:
        """硬删除会话私有数据；会话不存在时返回 ``None``。

        顺序刻意把 Conversation 本体放在最后。任何前置清理失败时，会话仍
        存在，调用方可以安全重试；已完成的子清理均为幂等操作。
        """

        normalized = conversation_id.strip()
        if not normalized:
            raise ValueError("conversation_id cannot be empty")
        if await self._conversation_store.get(normalized) is None:
            return None

        deleted_automations = 0
        cancelled_runs = 0
        cancelled_post_run_jobs = 0

        async def stop_active_work() -> None:
            nonlocal deleted_automations
            nonlocal cancelled_runs
            nonlocal cancelled_post_run_jobs

            # 删除调度入口后再停 Run，避免新的 Automation Run 趁清理间隙启动。
            deleted_automations = (
                await self._automation_scheduler.delete_for_conversation(normalized)
            )
            cancelled_runs = len(
                await self._run_manager.cancel_for_conversation(normalized)
            )
            cancelled_post_run_jobs = (
                await self._post_run_processor.cancel_for_conversation(normalized)
            )
            # Run 取消会处理正常关联审批；这里补齐没有活跃 Run 的孤儿审批。
            await self._approval_store.cancel_pending_for_conversation(normalized)

        async with self._operations.deletion(
            normalized,
            stop_active_work=stop_active_work,
        ):
            # 当前 dispatch 取消后可能已经完成最后一次会话写回，因此在独占区
            # 重新确认本体仍存在，并基于最终关联集合做清理。
            if await self._conversation_store.get(normalized) is None:
                return None

            runs = await self._run_store.list_for_conversation(normalized)
            run_ids = tuple(run.id for run in runs)
            event_payloads = (
                await self._trace_store.load_event_payloads_for_conversation(
                    normalized,
                    run_ids=run_ids,
                )
            )
            screenshot_ids = _extract_screenshot_ids(event_payloads)

            owned_tasks = await self._task_store.list_for_conversation(normalized)
            task_ids = tuple(task.id for task in owned_tasks)
            artifact_ids = await self._artifact_service.delete_for_conversation(
                normalized,
                run_ids=run_ids,
                task_ids=task_ids,
            )
            deleted_task_ids = (
                await self._task_store.delete_for_conversation(normalized)
            )

            deleted_permission_rules = await self._permission_rule_store.remove_scope(
                ApprovalScope.CONVERSATION,
                normalized,
            )
            for run_id in run_ids:
                deleted_permission_rules += (
                    await self._permission_rule_store.remove_scope(
                        ApprovalScope.RUN,
                        run_id,
                    )
                )

            deleted_approvals = (
                await self._approval_store.delete_for_conversation(
                    normalized,
                    run_ids=run_ids,
                )
            )
            deleted_evidence = (
                await self._evidence_store.delete_for_conversation(normalized)
            )
            deleted_checkpoints = (
                await self._checkpoint_store.delete_for_conversation(
                    normalized,
                    run_ids=run_ids,
                )
            )
            deleted_traces = (
                await self._trace_store.delete_for_conversation(
                    normalized,
                    run_ids=run_ids,
                )
            )
            deleted_runs = await self._run_store.delete_for_conversation(normalized)
            self._run_manager.forget_results(run_ids)
            deleted_screenshots = await _delete_screenshots(
                self._screenshot_dir,
                screenshot_ids,
            )

            deleted = await self._conversation_store.delete(normalized)
            if not deleted:  # pragma: no cover - 独占区内的防御性检查
                raise RuntimeError(f"删除会话失败：{normalized}")

        return ConversationDeletionResult(
            conversation_id=normalized,
            cancelled_runs=cancelled_runs,
            cancelled_post_run_jobs=cancelled_post_run_jobs,
            deleted_automations=deleted_automations,
            deleted_approvals=deleted_approvals,
            deleted_permission_rules=deleted_permission_rules,
            deleted_tasks=len(deleted_task_ids),
            deleted_artifacts=len(artifact_ids),
            deleted_evidence=deleted_evidence,
            deleted_checkpoints=deleted_checkpoints,
            deleted_traces=deleted_traces,
            deleted_runs=deleted_runs,
            deleted_screenshots=deleted_screenshots,
        )


def _extract_screenshot_ids(event_payloads: tuple[str, ...]) -> tuple[str, ...]:
    """从 computer_observe 事件提取截图 ID，不信任事件里的任意路径。"""

    found: set[str] = set()
    for raw_event in event_payloads:
        try:
            event = json.loads(raw_event)
        except (TypeError, json.JSONDecodeError):
            continue
        tool_result = event.get("tool_result")
        if not isinstance(tool_result, dict):
            continue
        if tool_result.get("tool_name") != "computer_observe":
            continue
        output = tool_result.get("output")
        if not isinstance(output, str):
            continue
        try:
            observation = json.loads(output)
        except json.JSONDecodeError:
            observation = None
        if isinstance(observation, dict):
            observation_id = observation.get("id")
            if isinstance(observation_id, str) and _HEX_ID_RE.fullmatch(
                observation_id
            ):
                found.add(observation_id)
            screenshot_ref = observation.get("screenshot_ref")
            if isinstance(screenshot_ref, str):
                stem = Path(screenshot_ref).stem
                if _HEX_ID_RE.fullmatch(stem):
                    found.add(stem)
        for match in _EMBEDDED_ID_RE.finditer(output):
            found.add(match.group(1))
    return tuple(sorted(found))


async def _delete_screenshots(
    screenshot_dir: Path | None,
    screenshot_ids: tuple[str, ...],
) -> int:
    """仅删除已验证 ID 对应的 PNG，不遍历或清空整个截图目录。"""

    if screenshot_dir is None:
        return 0
    deleted = 0
    for screenshot_id in screenshot_ids:
        if not _HEX_ID_RE.fullmatch(screenshot_id):  # pragma: no cover
            continue
        path = screenshot_dir / f"{screenshot_id}.png"
        if path.is_file() or path.is_symlink():
            path.unlink()
            deleted += 1
    return deleted


__all__ = ["ConversationDeletionResult", "ConversationLifecycleService"]
