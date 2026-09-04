"""模型主动提出 Skill 候选的受限工具。

模型只能创建待人工评审的 Candidate，不能直接写入正式 Skill 目录。正式
CREATE / UPDATE 始终由 Human Gate 与 ``SkillStore`` 完成。
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from app.models.types import ToolDefinition
from app.skills import SkillStore
from app.tools.base import BaseTool
from app.tools.hooks import ToolExecutionContext
from app.tools.registry import ToolRegistry

from .models import (
    SkillCandidate,
    SkillCandidateAction,
    SkillCandidateOrigin,
    SkillCandidateStatus,
)
from .store import SkillCandidateStore

SKILL_PROPOSE_TOOL_NAME = "skill_propose"


class SkillProposeTool(BaseTool):
    """把用户明确要求沉淀的过程知识保存为待审核候选。"""

    def __init__(
        self,
        candidate_store: SkillCandidateStore,
        skill_store: SkillStore,
    ) -> None:
        self._candidate_store = candidate_store
        self._skill_store = skill_store

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=SKILL_PROPOSE_TOOL_NAME,
            record_output=False,
            description=(
                "仅当用户明确要求把已完成、已验证的方法保存或更新为 Skill 时，"
                "创建一个待人工审核的 Skill 候选。该工具不会修改正式 Skill；"
                "不要用它保存事实、偏好、密钥、未验证猜测或一次性任务内容。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "update"],
                        "description": "创建新 Skill，或更新已有 Skill。",
                    },
                    "name": {
                        "type": "string",
                        "description": (
                            "Skill 名称；必须使用小写字母、数字和单连字符。"
                            "update 时必须是已有 Skill 的名称。"
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": "说明何时应该使用这个 Skill。",
                    },
                    "reason": {
                        "type": "string",
                        "description": "为什么本轮经验值得沉淀或更新。",
                    },
                    "procedure": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "可复用、按顺序执行的步骤。",
                    },
                    "pitfalls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选的常见错误与规避方式。",
                    },
                    "verification": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选的结果验证方法。",
                    },
                },
                "required": [
                    "action",
                    "name",
                    "description",
                    "reason",
                    "procedure",
                ],
                "additionalProperties": False,
            },
            strict=False,
        )

    async def execute(self, arguments: dict[str, Any]) -> Any:
        raise ValueError("skill_propose requires run and conversation context")

    async def execute_with_context(
        self,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> dict[str, Any]:
        run_id = (context.run_id or "").strip()
        conversation_id = (context.conversation_id or "").strip()
        tool_call_id = context.tool_call.id.strip()
        if not run_id or not conversation_id or not tool_call_id:
            raise ValueError(
                "skill_propose requires run, conversation, and tool call context"
            )

        action = SkillCandidateAction(str(arguments.get("action", "")))
        name = str(arguments.get("name", "")).strip()
        existing = await self._skill_store.load(name)
        if action is SkillCandidateAction.CREATE and existing is not None:
            raise ValueError(f"skill '{name}' already exists; use action=update")
        if action is SkillCandidateAction.UPDATE and existing is None:
            raise ValueError(f"existing skill '{name}' not found; use action=create")

        candidate_id = sha256(
            f"agent-proposal:{run_id}:{tool_call_id}".encode()
        ).hexdigest()
        existing_candidate = await self._candidate_store.get(candidate_id)
        if existing_candidate is not None:
            return _candidate_output(existing_candidate, replayed=True)
        for pending in await self._candidate_store.list(
            status=SkillCandidateStatus.PENDING
        ):
            if pending.proposed_name == name:
                raise ValueError(
                    f"skill '{name}' already has pending candidate "
                    f"'{pending.id}'; review it before proposing another"
                )

        candidate = SkillCandidate(
            id=candidate_id,
            origin=SkillCandidateOrigin.AGENT_PROPOSAL,
            action=action,
            proposed_name=name,
            description=arguments.get("description"),
            reason=arguments.get("reason"),
            procedure=arguments.get("procedure"),
            pitfalls=arguments.get("pitfalls", ()),
            verification=arguments.get("verification", ()),
            source_run_ids=(run_id,),
            source_conversation_id=conversation_id,
            source_tool_call_id=tool_call_id,
            existing_skill_name=(
                name if action is SkillCandidateAction.UPDATE else None
            ),
            status=SkillCandidateStatus.PENDING,
            created_at=datetime.now(UTC),
            evidence_summary=(
                "由主 Agent 根据用户明确要求提出；正式生效前需要人工审核。"
            ),
        )
        await self._candidate_store.create(candidate)
        return _candidate_output(candidate, replayed=False)


def _candidate_output(
    candidate: SkillCandidate,
    *,
    replayed: bool,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate.id,
        "action": candidate.action.value,
        "name": candidate.proposed_name,
        "status": candidate.status.value,
        "requires_human_review": True,
        "replayed": replayed,
        "message": "Skill 候选已保存，正式生效前需要用户审核。",
    }


def register_skill_learning_tools(
    registry: ToolRegistry,
    candidate_store: SkillCandidateStore,
    skill_store: SkillStore,
) -> None:
    """注册模型可见的 Skill 候选提案工具。"""

    registry.register(SkillProposeTool(candidate_store, skill_store))


__all__ = [
    "SKILL_PROPOSE_TOOL_NAME",
    "SkillProposeTool",
    "register_skill_learning_tools",
]
