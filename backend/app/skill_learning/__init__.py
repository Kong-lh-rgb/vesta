"""Skill Learning：自动模式学习 + Agent 主动提案 + 人工审核。

领域边界：
- Task = 当前任务 / 最终任务事实的权威状态；
- Trace = Agent 实际执行过程的原始证据；
- SkillCandidate = 从历史 Task 提炼或当前 Run 主动提出的候选过程知识；
- Skill = 经用户确认后正式生效的长期 procedural knowledge。

正式 Skill 只允许在 Candidate 被 accept 后由 Service 生成；本模块不修改
Task，也不在每个 Run 后调用模型（只有达到 batch_size 才触发 mining）。
"""

from .config import SkillLearningSettings
from .distiller import DistillationOutcome, ProcedureDistiller
from .evidence import TraceEvidenceBuilder
from .miner import PatternMiningOutcome, TaskPatternMiner
from .models import (
    PatternMiningResult,
    SkillCandidate,
    SkillCandidateAction,
    SkillCandidateOrigin,
    SkillCandidateStatus,
    TaskCard,
    TaskPatternCluster,
)
from .service import DistillationRecord, SkillLearningOutcome, SkillLearningService
from .store import InflightBatch, MiningWatermark, SkillCandidateStore
from .tools import (
    SKILL_PROPOSE_TOOL_NAME,
    SkillProposeTool,
    register_skill_learning_tools,
)

__all__ = [
    "DistillationOutcome",
    "DistillationRecord",
    "InflightBatch",
    "MiningWatermark",
    "PatternMiningOutcome",
    "PatternMiningResult",
    "ProcedureDistiller",
    "SkillCandidate",
    "SkillCandidateAction",
    "SkillCandidateOrigin",
    "SkillCandidateStatus",
    "SkillCandidateStore",
    "SkillLearningOutcome",
    "SkillLearningService",
    "SkillLearningSettings",
    "SkillProposeTool",
    "SKILL_PROPOSE_TOOL_NAME",
    "TaskCard",
    "TaskPatternCluster",
    "TaskPatternMiner",
    "TraceEvidenceBuilder",
    "register_skill_learning_tools",
]
