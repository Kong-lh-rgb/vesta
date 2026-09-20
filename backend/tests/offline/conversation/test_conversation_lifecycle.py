"""会话硬删除测试：关联数据清理、隔离与并发阻断。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.agent.events import AgentEvent, AgentEventType
from app.approval import SQLiteApprovalStore
from app.artifact import ArtifactService, SQLiteArtifactStore
from app.automation import Schedule, ScheduleKind, SQLiteAutomationStore
from app.checkpoint import SQLiteCheckpointStore
from app.context import (
    ConversationSummaryState,
    RollingConversationSummary,
    SQLiteConversationSummaryStore,
)
from app.conversation.coordinator import ConversationOperationCoordinator
from app.conversation.lifecycle import ConversationLifecycleService
from app.conversation.store import SQLiteConversationStore
from app.evidence import SQLiteEvidenceStore
from app.models.types import Message, MessageRole, ToolResult
from app.run import SQLiteRunStore
from app.task import FileTaskStore
from app.tools import ApprovalScope, PermissionEffect, PermissionRule
from app.tools.permissions import SQLitePermissionRuleStore
from app.trace import SQLiteTraceStore


class _RunManagerStub:
    async def cancel_for_conversation(self, conversation_id: str) -> tuple[()]:
        return ()

    def forget_results(self, run_ids: tuple[str, ...]) -> None:
        pass


class _AutomationSchedulerStub:
    def __init__(self, store: SQLiteAutomationStore) -> None:
        self.store = store

    async def delete_for_conversation(self, conversation_id: str) -> int:
        return await self.store.delete_for_conversation(conversation_id)


class _PostRunProcessorStub:
    async def cancel_for_conversation(self, conversation_id: str) -> int:
        return 0


@pytest.mark.asyncio
async def test_delete_removes_all_conversation_private_data(tmp_path) -> None:
    database = tmp_path / "vesta.db"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tasks_dir = tmp_path / "tasks"
    screenshots = tmp_path / "screenshots"
    screenshots.mkdir()

    conversations = SQLiteConversationStore(database)
    summaries = SQLiteConversationSummaryStore(database)
    runs = SQLiteRunStore(database)
    checkpoints = SQLiteCheckpointStore(database)
    traces = SQLiteTraceStore(database)
    evidence = SQLiteEvidenceStore(database)
    approvals = SQLiteApprovalStore(database)
    artifacts_store = SQLiteArtifactStore(database)
    artifacts = ArtifactService(
        artifacts_store,
        workspace,
        managed_dir=tmp_path / "artifacts",
    )
    tasks = FileTaskStore(tasks_dir)
    rules = SQLitePermissionRuleStore(database)
    automations = SQLiteAutomationStore(database)

    for store in (
        conversations,
        summaries,
        runs,
        checkpoints,
        traces,
        evidence,
        approvals,
        artifacts_store,
        tasks,
        rules,
        automations,
    ):
        await store.initialize()

    conversation_a = await conversations.create(
        messages=(Message(role=MessageRole.USER, content="仅属于 A"),)
    )
    conversation_b = await conversations.create(
        messages=(Message(role=MessageRole.USER, content="仅属于 B"),)
    )
    await summaries.save(
        conversation_a.id,
        ConversationSummaryState(
            summary=RollingConversationSummary(current_objective="删除测试"),
            covered_message_count=1,
        ),
    )

    run_a = await runs.create(
        conversation_id=conversation_a.id,
        user_message="执行 A",
    )
    await runs.mark_started(run_a.id)
    await runs.mark_completed(run_a.id)
    run_b = await runs.create(
        conversation_id=conversation_b.id,
        user_message="执行 B",
    )
    await runs.mark_started(run_b.id)
    await runs.mark_completed(run_b.id)

    await checkpoints.start(
        run_a.id,
        conversation_id=conversation_a.id,
        user_message=Message(role=MessageRole.USER, content="执行 A"),
    )

    screenshot_id = "a" * 32
    screenshot_path = screenshots / f"{screenshot_id}.png"
    screenshot_path.write_bytes(b"PNG")
    await traces.record_event(
        AgentEvent(
            run_id=run_a.id,
            conversation_id=conversation_a.id,
            sequence=0,
            type=AgentEventType.TOOL_COMPLETED,
            tool_result=ToolResult(
                tool_call_id="observe-a",
                tool_name="computer_observe",
                success=True,
                output=json.dumps(
                    {
                        "id": screenshot_id,
                        "screenshot_ref": str(screenshot_path),
                    }
                ),
                duration_ms=1,
            ),
        )
    )
    await traces.record_event(
        AgentEvent(
            run_id=run_b.id,
            conversation_id=conversation_b.id,
            sequence=0,
            type=AgentEventType.AGENT_STARTED,
        )
    )

    content = "A 的不可变工具证据"
    await evidence.create(
        conversation_id=conversation_a.id,
        run_id=run_a.id,
        tool_call_id="tool-a",
        tool_name="read_file",
        content=content,
        sha256=hashlib.sha256(content.encode()).hexdigest(),
    )
    await approvals.create(
        run_id=run_a.id,
        conversation_id=conversation_a.id,
        tool_name="run_shell_command",
        tool_call_id="approval-a",
    )
    task_a = await tasks.create(
        title="A 的任务",
        owner_conversation_id=conversation_a.id,
    )
    task_b = await tasks.create(
        title="B 的任务",
        owner_conversation_id=conversation_b.id,
    )

    (workspace / "report.txt").write_text("artifact", encoding="utf-8")
    artifact_a = await artifacts.publish_file(
        path="report.txt",
        run_id=run_a.id,
        # 验证旧数据即使缺失 conversation_id，也能通过 Run 关联清理。
        conversation_id=None,
        task_id=task_a.id,
    )
    artifact_path = await artifacts.file_path(artifact_a.id)
    assert artifact_path is not None and artifact_path.is_file()

    await rules.add(
        PermissionRule(
            id="conversation-rule-a",
            tool_name="run_shell_command",
            scope=ApprovalScope.CONVERSATION,
            scope_id=conversation_a.id,
            effect=PermissionEffect.ALLOW,
            matcher_type="arguments_exact",
            matcher={"command": "pwd"},
            description="A 会话规则",
        )
    )
    await rules.add(
        PermissionRule(
            id="run-rule-a",
            tool_name="run_shell_command",
            scope=ApprovalScope.RUN,
            scope_id=run_a.id,
            effect=PermissionEffect.ALLOW,
            matcher_type="arguments_exact",
            matcher={"command": "pwd"},
            description="A Run 规则",
        )
    )
    await automations.create(
        title="A 自动化",
        prompt="继续 A",
        conversation_id=conversation_a.id,
        schedule=Schedule(
            kind=ScheduleKind.ONCE,
            run_at=datetime.now(UTC) + timedelta(days=1),
        ),
        next_run_at=datetime.now(UTC) + timedelta(days=1),
    )

    coordinator = ConversationOperationCoordinator()
    lifecycle = ConversationLifecycleService(
        conversations,
        coordinator,
        _RunManagerStub(),  # type: ignore[arg-type]
        runs,
        checkpoints,
        traces,
        evidence,
        approvals,
        artifacts,
        tasks,
        rules,
        _AutomationSchedulerStub(automations),  # type: ignore[arg-type]
        _PostRunProcessorStub(),  # type: ignore[arg-type]
        screenshot_dir=screenshots,
    )

    result = await lifecycle.delete(conversation_a.id)

    assert result is not None
    assert result.deleted is True
    assert result.deleted_runs == 1
    assert result.deleted_checkpoints == 1
    assert result.deleted_traces == 1
    assert result.deleted_evidence == 1
    assert result.deleted_approvals == 1
    assert result.deleted_permission_rules == 2
    assert result.deleted_tasks == 1
    assert result.deleted_artifacts == 1
    assert result.deleted_automations == 1
    assert result.deleted_screenshots == 1
    assert result.audit_records_retained is False

    assert await conversations.get(conversation_a.id) is None
    assert await summaries.load(conversation_a.id) is None
    assert await runs.get(run_a.id) is None
    assert await checkpoints.get(run_a.id) is None
    assert await traces.get(run_a.id) is None
    assert await evidence.list_recent(conversation_id=conversation_a.id) == ()
    assert await approvals.list(conversation_id=conversation_a.id) == ()
    assert await artifacts_store.get(artifact_a.id) is None
    assert not artifact_path.exists()
    assert await tasks.get(task_a.id) is None
    assert await rules.list(scope_ids=(conversation_a.id, run_a.id)) == ()
    assert await automations.list(conversation_id=conversation_a.id) == ()
    assert not screenshot_path.exists()

    # B 会话及其关联数据不受影响。
    assert await conversations.get(conversation_b.id) is not None
    assert await runs.get(run_b.id) is not None
    assert await traces.get(run_b.id) is not None
    assert await tasks.get(task_b.id) is not None


@pytest.mark.asyncio
async def test_delete_missing_conversation_is_noop(tmp_path) -> None:
    database = tmp_path / "vesta.db"
    conversations = SQLiteConversationStore(database)
    await conversations.initialize()

    class _MustNotRun:
        def __getattr__(self, name: str):
            raise AssertionError(f"不应调用：{name}")

    lifecycle = ConversationLifecycleService(
        conversations,
        ConversationOperationCoordinator(),
        _MustNotRun(),  # type: ignore[arg-type]
        _MustNotRun(),  # type: ignore[arg-type]
        _MustNotRun(),  # type: ignore[arg-type]
        _MustNotRun(),  # type: ignore[arg-type]
        _MustNotRun(),  # type: ignore[arg-type]
        _MustNotRun(),  # type: ignore[arg-type]
        _MustNotRun(),  # type: ignore[arg-type]
        _MustNotRun(),  # type: ignore[arg-type]
        _MustNotRun(),  # type: ignore[arg-type]
        _MustNotRun(),  # type: ignore[arg-type]
        _MustNotRun(),  # type: ignore[arg-type]
    )

    assert await lifecycle.delete("missing") is None


@pytest.mark.asyncio
async def test_deletion_blocks_new_conversation_execution() -> None:
    coordinator = ConversationOperationCoordinator()
    stop_started = asyncio.Event()
    allow_stop = asyncio.Event()

    async def stop_active_work() -> None:
        stop_started.set()
        await allow_stop.wait()

    async def delete() -> None:
        async with coordinator.deletion(
            "conversation-a",
            stop_active_work=stop_active_work,
        ):
            pass

    deletion = asyncio.create_task(delete())
    await stop_started.wait()
    with pytest.raises(KeyError, match="正在删除"):
        async with coordinator.execution("conversation-a"):
            pass
    allow_stop.set()
    await deletion


# ---------------------------------------------------------------------------
# P1：删除中途失败加固（故障注入 / 重试幂等 / 取消 / 不误删）
# ---------------------------------------------------------------------------


class _CountingRunManagerStub:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    async def cancel_for_conversation(self, conversation_id: str) -> tuple[str, ...]:
        self.cancelled.append(conversation_id)
        return ("run-active-1",)

    def forget_results(self, run_ids: tuple[str, ...]) -> None:
        pass


class _CountingPostRunStub:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    async def cancel_for_conversation(self, conversation_id: str) -> int:
        self.cancelled.append(conversation_id)
        return 2


class _CountingAutomationStub(_AutomationSchedulerStub):
    def __init__(self, store: SQLiteAutomationStore) -> None:
        super().__init__(store)
        self.deleted: list[str] = []

    async def delete_for_conversation(self, conversation_id: str) -> int:
        self.deleted.append(conversation_id)
        return await super().delete_for_conversation(conversation_id)


async def _build_deletion_fixture(tmp_path):
    """构建带完整关联数据的会话删除环境（P1 加固测试共用）。"""

    database = tmp_path / "vesta.db"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    memory_dir = tmp_path / "memory"
    skills_dir = tmp_path / "project-skills" / "keep-skill"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: keep-skill\ndescription: 不能被会话删除波及\n---\n\n正文",
        encoding="utf-8",
    )
    (workspace / "user-file.txt").write_text("用户文件", encoding="utf-8")
    (memory_dir).mkdir()

    conversations = SQLiteConversationStore(database)
    summaries = SQLiteConversationSummaryStore(database)
    runs = SQLiteRunStore(database)
    checkpoints = SQLiteCheckpointStore(database)
    traces = SQLiteTraceStore(database)
    evidence = SQLiteEvidenceStore(database)
    approvals = SQLiteApprovalStore(database)
    artifacts_store = SQLiteArtifactStore(database)
    artifacts = ArtifactService(
        artifacts_store, workspace, managed_dir=tmp_path / "artifacts"
    )
    tasks = FileTaskStore(tmp_path / "tasks")
    rules = SQLitePermissionRuleStore(database)
    automations = SQLiteAutomationStore(database)
    for store in (
        conversations, summaries, runs, checkpoints, traces, evidence,
        approvals, artifacts_store, tasks, rules, automations,
    ):
        await store.initialize()

    conversation = await conversations.create(
        messages=(Message(role=MessageRole.USER, content="主会话"),)
    )
    run = await runs.create(
        conversation_id=conversation.id, user_message="执行"
    )
    await runs.mark_started(run.id)
    await traces.record_event(
        AgentEvent(
            run_id=run.id,
            conversation_id=conversation.id,
            sequence=0,
            type=AgentEventType.AGENT_STARTED,
        )
    )
    await checkpoints.start(
        run.id,
        conversation_id=conversation.id,
        user_message=Message(role=MessageRole.USER, content="执行"),
    )
    content = "证据"
    await evidence.create(
        conversation_id=conversation.id,
        run_id=run.id,
        tool_call_id="tool-x",
        tool_name="read_file",
        content=content,
        sha256=hashlib.sha256(content.encode()).hexdigest(),
    )
    await approvals.create(
        run_id=run.id,
        conversation_id=conversation.id,
        tool_name="run_shell_command",
        tool_call_id="approval-x",
    )
    task = await tasks.create(
        title="任务", owner_conversation_id=conversation.id
    )
    (workspace / "art.txt").write_text("artifact", encoding="utf-8")
    artifact = await artifacts.publish_file(
        path="art.txt", run_id=run.id, conversation_id=conversation.id
    )

    run_manager = _CountingRunManagerStub()
    post_run = _CountingPostRunStub()
    automation_scheduler = _CountingAutomationStub(automations)
    lifecycle = ConversationLifecycleService(
        conversations,
        ConversationOperationCoordinator(),
        run_manager,  # type: ignore[arg-type]
        runs,
        checkpoints,
        traces,
        evidence,
        approvals,
        artifacts,
        tasks,
        rules,
        automation_scheduler,  # type: ignore[arg-type]
        post_run,  # type: ignore[arg-type]
        screenshot_dir=tmp_path / "screenshots",
    )
    return {
        "lifecycle": lifecycle,
        "conversations": conversations,
        "runs": runs,
        "traces": traces,
        "evidence": evidence,
        "tasks": tasks,
        "approvals": approvals,
        "artifacts_store": artifacts_store,
        "checkpoints": checkpoints,
        "run_manager": run_manager,
        "post_run": post_run,
        "conversation_id": conversation.id,
        "run_id": run.id,
        "task_id": task.id,
        "artifact_id": artifact.id,
        "workspace": workspace,
        "memory_dir": memory_dir,
        "skills_dir": skills_dir,
    }


_STAGE_METHODS = {
    "artifacts": ("_artifact_service", "delete_for_conversation"),
    "tasks": ("_task_store", "delete_for_conversation"),
    "approvals": ("_approval_store", "delete_for_conversation"),
    "evidence": ("_evidence_store", "delete_for_conversation"),
    "checkpoints": ("_checkpoint_store", "delete_for_conversation"),
    "traces": ("_trace_store", "delete_for_conversation"),
    "runs": ("_run_store", "delete_for_conversation"),
}


@pytest.mark.parametrize("stage", sorted(_STAGE_METHODS))
@pytest.mark.asyncio
async def test_failure_at_any_stage_preserves_conversation_and_retry_completes(
    tmp_path, stage, monkeypatch
) -> None:
    """任意子清理阶段失败：会话保留、报错可见；重试继续完成全部清理。"""

    fixture = await _build_deletion_fixture(tmp_path)
    lifecycle = fixture["lifecycle"]
    conversations = fixture["conversations"]
    attribute, method = _STAGE_METHODS[stage]
    target = getattr(lifecycle, attribute)
    original = getattr(target, method)

    async def explode(*args, **kwargs):
        raise RuntimeError(f"injected failure at {stage}")

    monkeypatch.setattr(target, method, explode)

    with pytest.raises(RuntimeError, match="injected failure"):
        await lifecycle.delete(fixture["conversation_id"])

    # 失败后会话本体仍在（Conversation 最后删除），可以安全重试。
    assert await conversations.get(fixture["conversation_id"]) is not None

    monkeypatch.setattr(target, method, original)
    result = await lifecycle.delete(fixture["conversation_id"])

    assert result is not None and result.deleted is True
    assert await conversations.get(fixture["conversation_id"]) is None
    assert await fixture["runs"].get(fixture["run_id"]) is None
    assert await fixture["traces"].get(fixture["run_id"]) is None
    assert await fixture["checkpoints"].get(fixture["run_id"]) is None
    await _assert_store_empty(fixture, stage)


async def _assert_store_empty(fixture, failed_stage: str) -> None:
    conversation_id = fixture["conversation_id"]
    assert await fixture["evidence"].list_recent(
        conversation_id=conversation_id
    ) == ()
    assert await fixture["approvals"].list(conversation_id=conversation_id) == ()
    assert await fixture["artifacts_store"].get(fixture["artifact_id"]) is None
    if failed_stage != "tasks":
        assert await fixture["tasks"].get(fixture["task_id"]) is None


@pytest.mark.asyncio
async def test_deletion_cancels_active_work_and_post_run_jobs(tmp_path) -> None:
    """活动 Run、Automation、Post-Run Job 在删除期间全部被取消。"""

    fixture = await _build_deletion_fixture(tmp_path)

    result = await fixture["lifecycle"].delete(fixture["conversation_id"])

    assert result is not None
    assert result.cancelled_runs == 1
    assert result.cancelled_post_run_jobs == 2
    assert fixture["run_manager"].cancelled == [fixture["conversation_id"]]
    assert fixture["post_run"].cancelled == [fixture["conversation_id"]]


@pytest.mark.asyncio
async def test_deletion_does_not_touch_memory_skills_or_user_files(
    tmp_path,
) -> None:
    """Memory、正式 Skill、workspace 用户文件不属于会话私有数据，不删除。"""

    fixture = await _build_deletion_fixture(tmp_path)
    timestamp = "2026-01-01T00:00:00+00:00"
    (fixture["memory_dir"] / "M001.md").write_text(
        "---\n"
        "id: M001\n"
        "title: 记忆\n"
        "summary: s\n"
        f"created_at: {timestamp}\n"
        f"updated_at: {timestamp}\n"
        f"last_accessed_at: {timestamp}\n"
        "---\n# 记忆\n\n## Memory\n\n正文",
        encoding="utf-8",
    )

    result = await fixture["lifecycle"].delete(fixture["conversation_id"])

    assert result is not None and result.deleted is True
    assert (fixture["memory_dir"] / "M001.md").exists()
    assert (fixture["skills_dir"] / "SKILL.md").exists()
    assert (fixture["workspace"] / "user-file.txt").exists()
