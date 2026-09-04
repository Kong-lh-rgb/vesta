"""模型主动提出 Skill Candidate 的离线测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.types import ToolCall
from app.skill_learning import (
    SKILL_PROPOSE_TOOL_NAME,
    SkillCandidateOrigin,
    SkillCandidateStore,
    register_skill_learning_tools,
)
from app.skills import SkillScope, SkillStore
from app.tools.hooks import ToolExecutionContext
from app.tools.registry import ToolRegistry


async def _environment(
    tmp_path: Path,
) -> tuple[ToolRegistry, SkillStore, SkillCandidateStore]:
    skill_store = SkillStore(
        tmp_path / "user-skills",
        tmp_path / "project-skills",
    )
    await skill_store.initialize()
    candidate_store = SkillCandidateStore(tmp_path / "learning")
    await candidate_store.initialize()
    registry = ToolRegistry()
    register_skill_learning_tools(registry, candidate_store, skill_store)
    return registry, skill_store, candidate_store


def _arguments(*, action: str = "create", name: str = "review-python") -> dict:
    return {
        "action": action,
        "name": name,
        "description": "在 Python 修改完成后进行结构化复查",
        "reason": "用户明确要求保存本轮已验证的复查方法",
        "procedure": ["检查变更范围", "运行针对性测试", "报告剩余风险"],
        "pitfalls": ["不要把测试通过等同于没有风险"],
        "verification": ["ruff 与 pytest 均通过"],
    }


def _context(arguments: dict) -> ToolExecutionContext:
    return ToolExecutionContext(
        tool_call=ToolCall(
            id="call-skill-propose",
            name=SKILL_PROPOSE_TOOL_NAME,
            arguments=arguments,
        ),
        run_id="run-1",
        conversation_id="conversation-1",
    )


@pytest.mark.asyncio
async def test_skill_propose_creates_pending_candidate_only(
    tmp_path: Path,
) -> None:
    registry, skill_store, candidate_store = await _environment(tmp_path)
    tool = registry.get(SKILL_PROPOSE_TOOL_NAME)
    arguments = _arguments()

    output = await tool.execute_with_context(arguments, _context(arguments))

    assert output["status"] == "pending"
    assert output["requires_human_review"] is True
    candidate = await candidate_store.get(output["candidate_id"])
    assert candidate is not None
    assert candidate.origin is SkillCandidateOrigin.AGENT_PROPOSAL
    assert candidate.source_run_ids == ("run-1",)
    assert candidate.source_conversation_id == "conversation-1"
    assert candidate.source_tool_call_id == "call-skill-propose"
    # 提案阶段绝不能提前写入正式 Skill 目录。
    assert await skill_store.load("review-python") is None


@pytest.mark.asyncio
async def test_skill_propose_replay_is_idempotent(tmp_path: Path) -> None:
    registry, _, candidate_store = await _environment(tmp_path)
    tool = registry.get(SKILL_PROPOSE_TOOL_NAME)
    arguments = _arguments()
    context = _context(arguments)

    first = await tool.execute_with_context(arguments, context)
    second = await tool.execute_with_context(arguments, context)

    assert second["candidate_id"] == first["candidate_id"]
    assert second["replayed"] is True
    assert len(await candidate_store.list()) == 1


@pytest.mark.asyncio
async def test_skill_propose_rejects_second_pending_target(tmp_path: Path) -> None:
    registry, _, _ = await _environment(tmp_path)
    tool = registry.get(SKILL_PROPOSE_TOOL_NAME)
    arguments = _arguments()
    await tool.execute_with_context(arguments, _context(arguments))
    another_context = ToolExecutionContext(
        tool_call=ToolCall(
            id="another-call",
            name=SKILL_PROPOSE_TOOL_NAME,
            arguments=arguments,
        ),
        run_id="run-2",
        conversation_id="conversation-1",
    )

    with pytest.raises(ValueError, match="already has pending candidate"):
        await tool.execute_with_context(arguments, another_context)


@pytest.mark.asyncio
async def test_skill_propose_update_requires_existing_skill(
    tmp_path: Path,
) -> None:
    registry, skill_store, _ = await _environment(tmp_path)
    tool = registry.get(SKILL_PROPOSE_TOOL_NAME)
    missing_arguments = _arguments(action="update")
    with pytest.raises(ValueError, match="not found"):
        await tool.execute_with_context(
            missing_arguments,
            _context(missing_arguments),
        )

    await skill_store.install(
        name="review-python",
        description="旧描述",
        instructions="# Review Python\n\n旧流程",
        scope=SkillScope.PROJECT,
    )
    output = await tool.execute_with_context(
        missing_arguments,
        _context(missing_arguments),
    )
    assert output["action"] == "update"


@pytest.mark.asyncio
async def test_skill_propose_requires_execution_context(tmp_path: Path) -> None:
    registry, _, _ = await _environment(tmp_path)
    with pytest.raises(ValueError, match="requires run and conversation"):
        await registry.get(SKILL_PROPOSE_TOOL_NAME).execute(_arguments())


@pytest.mark.asyncio
async def test_skill_store_update_preserves_resources(tmp_path: Path) -> None:
    _, skill_store, _ = await _environment(tmp_path)
    installed = await skill_store.install(
        name="review-python",
        description="旧描述",
        instructions="# Review Python\n\n旧流程",
    )
    references = installed.root / "references"
    references.mkdir()
    (references / "checklist.md").write_text("检查项", encoding="utf-8")

    updated = await skill_store.update(
        name="review-python",
        description="新描述",
        instructions="# Review Python\n\n新流程",
    )

    assert updated.metadata.description == "新描述"
    assert "新流程" in updated.content
    assert (updated.root / "references" / "checklist.md").read_text(
        encoding="utf-8"
    ) == "检查项"
