"""把现有各套Harness结果转换成统一评测样本。"""

from __future__ import annotations

from pathlib import Path

from app.agent.budget import chargeable_tokens
from app.models.types import ModelUsage
from app.trace import RunUsageSummary
from tests.memory_eval.harness import MemoryEvalPhaseOutcome
from tests.memory_eval.scenario import MemoryEvalScenario

from .harness import EvalOutcome
from .records import (
    EvalCheckRecord,
    EvalSampleRecord,
    LearningDiagnostics,
    LearningDistillationRecord,
    LearningMiningRecord,
    usage_from_events,
    write_sample,
    write_trace,
)
from .scenario import Scenario


def core_sample_from_outcome(
    scenario: Scenario,
    outcome: EvalOutcome,
    checks: list[object],
    passed: bool,
    *,
    provider: str,
    model: str,
    run_index: int,
) -> EvalSampleRecord:
    """转换普通Agent Runtime评测并保存Trace证据。"""

    trace_path = outcome.environment.root / "trace.json"
    write_trace(outcome.events, trace_path)
    result = outcome.result
    tool_records = result.tool_calls if result is not None else ()
    sample = EvalSampleRecord(
        suite="core",
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        group=scenario.group,
        tier=scenario.tier,
        run_index=run_index,
        provider=provider,
        model=model,
        passed=passed,
        checks=_checks(checks),
        stop_reason=(result.stop_reason.value if result is not None else None),
        steps=result.steps if result is not None else 0,
        tool_calls=len(tool_records),
        tool_failures=sum(not record.result.success for record in tool_records),
        duration_s=outcome.duration_s,
        usage=usage_from_events(outcome.events),
        error=outcome.error,
        trace_path=str(trace_path),
        workspace_path=str(outcome.environment.workspace),
    )
    write_sample(sample, outcome.environment.root / "sample.json")
    return sample


def memory_sample_from_phase(
    scenario: MemoryEvalScenario,
    outcome: MemoryEvalPhaseOutcome,
    checks: list[object],
    passed: bool,
    *,
    provider: str,
    model: str,
    run_index: int,
    mode: str,
    run_root: Path,
) -> EvalSampleRecord:
    """转换Memory多阶段评测，保留phase与会话边界。"""

    trace_path = run_root / f"phase-{outcome.phase.id}" / "trace.json"
    write_trace(outcome.events, trace_path)
    result = outcome.result
    tool_records = result.tool_calls if result is not None else ()
    sample = EvalSampleRecord(
        suite="memory",
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        group="memory",
        tier=scenario.tier,
        phase_id=outcome.phase.id,
        conversation=outcome.phase.conversation,
        mode=mode,
        run_index=run_index,
        provider=provider,
        model=model,
        passed=passed,
        checks=_checks(checks),
        stop_reason=(result.stop_reason.value if result is not None else None),
        steps=result.steps if result is not None else 0,
        tool_calls=len(tool_records),
        tool_failures=sum(not record.result.success for record in tool_records),
        duration_s=outcome.duration_s,
        usage=usage_from_events(outcome.events),
        error=outcome.error,
        trace_path=str(trace_path),
        workspace_path=str(run_root),
    )
    write_sample(sample, trace_path.parent / "sample.json")
    return sample


def learning_sample_from_outcome(
    scenario: Scenario,
    outcome: object,
    verdict: object,
    *,
    provider: str,
    model: str,
    run_index: int,
) -> EvalSampleRecord:
    """转换Skill Learning结果；该管线不伪装成AgentEvent序列。"""

    mining = getattr(outcome, "mining", None)
    usage = ModelUsage(
        input_tokens=getattr(mining, "input_tokens", 0) or 0,
        output_tokens=getattr(mining, "output_tokens", 0) or 0,
        total_tokens=getattr(mining, "total_tokens", 0) or 0,
        model_calls=(getattr(mining, "pattern_mining_calls", 0) or 0)
        + (getattr(mining, "distillation_calls", 0) or 0),
    )
    usage_summary = RunUsageSummary(
        main_agent=usage,
        provider_total=usage,
        main_agent_chargeable_tokens=chargeable_tokens(usage),
    )
    passed = bool(getattr(verdict, "passed"))
    reasons = tuple(str(item) for item in getattr(verdict, "reasons", ()))
    environment = getattr(outcome, "environment")
    clusters = tuple(getattr(mining, "clusters", ()) or ())
    distillations = tuple(getattr(mining, "distillations", ()) or ())
    mining_raw_output = getattr(mining, "pattern_mining_raw_output", None)
    if mining_raw_output is None:
        mining_raw_output = getattr(mining, "raw_output", None)
    sample = EvalSampleRecord(
        suite="learning",
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        group="learning",
        tier=scenario.tier,
        run_index=run_index,
        provider=provider,
        model=model,
        passed=passed,
        checks=(
            EvalCheckRecord(
                name="learning",
                ok=passed,
                detail="; ".join(reasons),
            ),
        ),
        stop_reason=(
            "completed" if getattr(outcome, "error", None) is None else None
        ),
        duration_s=(getattr(mining, "total_duration_ms", 0.0) or 0.0) / 1000,
        usage=usage_summary,
        error=getattr(outcome, "error", None),
        workspace_path=str(environment.root),
        learning_diagnostics=LearningDiagnostics(
            mining=LearningMiningRecord(
                scanned_task_count=(
                    getattr(mining, "scanned_task_count", 0) or 0
                ),
                cluster_count=len(clusters),
                clusters=tuple(
                    cluster.model_dump(mode="json") for cluster in clusters
                ),
                raw_output=mining_raw_output,
            ),
            distillations=tuple(
                LearningDistillationRecord(
                    cluster_name=item.cluster_name,
                    action=item.action,
                    reason=item.reason,
                    proposed_name=item.proposed_name,
                    existing_skill_name=item.existing_skill_name,
                    related_skill_names=item.related_skill_names,
                    raw_output=getattr(item, "raw_output", None),
                    adjudication_raw_output=getattr(
                        item, "adjudication_raw_output", None
                    ),
                    error=item.error,
                )
                for item in distillations
            ),
        ),
    )
    write_sample(sample, environment.root / "sample.json")
    return sample


def _checks(checks: list[object]) -> tuple[EvalCheckRecord, ...]:
    return tuple(
        EvalCheckRecord(
            name=str(getattr(check, "name")),
            ok=bool(getattr(check, "ok")),
            detail=str(getattr(check, "detail", "")),
            applicable=bool(getattr(check, "applicable", True)),
        )
        for check in checks
    )


__all__ = [
    "core_sample_from_outcome",
    "learning_sample_from_outcome",
    "memory_sample_from_phase",
]
