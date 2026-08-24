"""Agent综合评测统一记录、报告与Baseline比较测试。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.config import ModelSettings
from app.models.types import ModelUsage
from app.tools.approval import ApprovalDecision, ApprovalRequest
from app.trace import RunUsageSummary
from tests.eval_legacy import run_suite
from tests.eval_legacy.adapters import learning_sample_from_outcome
from tests.eval_legacy.harness import EvalApprovalGate
from tests.eval_legacy.loader import load_scenarios
from tests.eval_legacy.memory.loader import load_scenarios as load_memory_scenarios
from tests.eval_legacy.mocks import fake_registry, model_response
from tests.eval_legacy.records import EvalCheckRecord, EvalSampleRecord, EvalSuiteReport
from tests.eval_legacy.reporting import (
    compare_reports,
    render_comparison,
    render_report,
)


def _sample(
    scenario_id: str,
    *,
    passed: bool = True,
    group: str = "basic",
    run_index: int = 1,
    chargeable: int = 100,
    cached: int | None = 60,
) -> EvalSampleRecord:
    usage = RunUsageSummary(
        main_agent=ModelUsage(
            input_tokens=100,
            output_tokens=10,
            total_tokens=110,
            cached_input_tokens=cached,
            uncached_input_tokens=(100 - cached if cached is not None else None),
            model_calls=1,
        ),
        provider_total=ModelUsage(
            input_tokens=100,
            output_tokens=10,
            total_tokens=110,
            cached_input_tokens=cached,
            uncached_input_tokens=(100 - cached if cached is not None else None),
            model_calls=1,
        ),
        main_agent_chargeable_tokens=chargeable,
    )
    # chargeable_tokens按Provider Usage重建，因此通过uncached字段构造期望成本。
    if cached is not None:
        usage = usage.model_copy(
            update={
                "provider_total": usage.provider_total.model_copy(
                    update={"uncached_input_tokens": max(0, chargeable - 10)}
                )
            }
        )
    return EvalSampleRecord(
        suite="core",
        scenario_id=scenario_id,
        scenario_name=scenario_id,
        group=group,
        tier="smoke",
        run_index=run_index,
        provider="fake",
        model="fake-model",
        passed=passed,
        checks=(EvalCheckRecord(name="answer", ok=passed),),
        stop_reason="final_answer",
        steps=2,
        tool_calls=1,
        duration_s=0.5,
        usage=usage,
    )


def _report(
    *samples: EvalSampleRecord,
    requested_runs: int | None = None,
    expected_keys: tuple[tuple[str, str, str | None, str], ...] | None = None,
) -> EvalSuiteReport:
    runs = requested_runs or max(
        (sample.run_index for sample in samples),
        default=1,
    )
    keys = expected_keys or tuple(
        dict.fromkeys(sample.stability_key for sample in samples)
    )
    report = EvalSuiteReport(
        provider="fake",
        model="fake-model",
        suites=("core",),
        tier="smoke",
        requested_runs=runs,
        expected_sample_count=len(keys) * runs,
        expected_stability_keys=keys,
        samples=list(samples),
    )
    report.refresh_completeness()
    return report


def test_report_tracks_sample_and_stable_pass_rates() -> None:
    report = _report(
        _sample("stable", run_index=1),
        _sample("stable", run_index=2),
        _sample("flaky", run_index=1),
        _sample("flaky", run_index=2, passed=False),
    )

    assert report.pass_rate == 0.75
    assert report.stable_pass_rate == 0.5
    assert report.average_steps == 2
    assert report.average_model_calls == 1
    assert report.average_cache_hit_rate == pytest.approx(0.6)
    assert report.complete is True
    assert report.actual_sample_count == 4


def test_report_marks_missing_or_duplicate_runs_incomplete() -> None:
    report = _report(
        _sample("unstable", run_index=1),
        _sample("unstable", run_index=1),
        requested_runs=2,
    )

    assert report.complete is False
    assert report.stable_pass_rate == 0.0
    assert any("actual_runs=[1, 1]" in item for item in report.completeness_issues)
    assert "❌ 不完整" in render_report(report)


def test_report_detects_completely_missing_stability_key() -> None:
    expected = (
        ("core", "present", None, "on"),
        ("core", "missing", None, "on"),
    )
    report = _report(
        _sample("present"),
        requested_runs=1,
        expected_keys=expected,
    )

    assert report.complete is False
    assert report.expected_sample_count == 2
    assert report.actual_sample_count == 1
    assert any("core/missing" in item for item in report.completeness_issues)


def test_unknown_cache_detail_remains_unknown() -> None:
    report = _report(_sample("unknown-cache", cached=None))

    assert report.samples[0].cache_hit_rate is None
    assert report.average_cache_hit_rate is None
    assert "未知" in render_report(report)


def test_report_json_round_trip_and_markdown(tmp_path: Path) -> None:
    report = _report(_sample("eval-01"))
    path = tmp_path / "report.json"

    report.save_json(path)
    loaded = EvalSuiteReport.load_json(path)
    markdown = render_report(loaded)

    assert loaded.samples[0].scenario_id == "eval-01"
    assert loaded.requested_runs == 1
    assert loaded.expected_sample_count == 1
    assert loaded.actual_sample_count == 1
    assert loaded.complete is True
    assert "Vesta Agent 综合评测报告" in markdown
    assert "稳定通过率" in markdown
    assert "Chargeable" in markdown


def test_baseline_blocks_stable_and_safety_regressions() -> None:
    baseline = _report(
        _sample("stable"),
        _sample("safe", group="safety"),
    )
    current = _report(
        _sample("stable", passed=False),
        _sample("safe", group="safety", passed=False),
    )

    comparison = compare_reports(current, baseline)

    assert comparison.blocked is True
    assert any("稳定通过" in item for item in comparison.regressions)
    assert any("安全场景" in item for item in comparison.regressions)
    assert "BLOCKED" in render_comparison(comparison)


def test_cost_growth_is_warning_not_blocker() -> None:
    baseline = _report(_sample("cost", chargeable=100))
    current = _report(_sample("cost", chargeable=150))

    comparison = compare_reports(current, baseline)

    assert comparison.blocked is False
    assert comparison.chargeable_tokens_delta_ratio == pytest.approx(0.5)
    assert comparison.warnings


def test_baseline_rejects_different_model() -> None:
    baseline = _report(_sample("same"))
    current = _report(_sample("same"))
    current.model = "other-model"

    with pytest.raises(ValueError, match="provider/model"):
        compare_reports(current, baseline)


def test_baseline_rejects_different_scenario_set() -> None:
    baseline = _report(_sample("one"))
    current = _report(_sample("two"))

    with pytest.raises(ValueError, match="场景集合"):
        compare_reports(current, baseline)


def test_baseline_rejects_different_requested_runs() -> None:
    baseline = _report(_sample("same"), requested_runs=1)
    current = _report(
        _sample("same", run_index=1),
        _sample("same", run_index=2),
        requested_runs=2,
    )

    with pytest.raises(ValueError, match="requested_runs"):
        compare_reports(current, baseline)


def test_baseline_rejects_incomplete_samples() -> None:
    baseline = _report(_sample("same"), requested_runs=1)
    current = _report(_sample("same"), requested_runs=2)

    with pytest.raises(ValueError, match="当前评测样本不完整"):
        compare_reports(current, baseline)


@pytest.mark.asyncio
async def test_eval_approval_gate_denies_unlisted_tools_by_default() -> None:
    gate = EvalApprovalGate()
    request = ApprovalRequest(
        tool_call_id="call-1",
        tool_name="run_shell_command",
        arguments={"command": "echo hello"},
    )

    response = await gate.request_approval(request)

    assert response.decision is ApprovalDecision.DENIED


@pytest.mark.asyncio
async def test_eval_approval_gate_only_approves_explicit_tools() -> None:
    request = ApprovalRequest(
        tool_call_id="call-1",
        tool_name="run_shell_command",
        arguments={"command": "echo hello"},
    )
    approved = EvalApprovalGate(approve_tools=("run_shell_command",))
    denied_wins = EvalApprovalGate(
        approve_tools=("run_shell_command",),
        deny_tools=("run_shell_command",),
    )

    approved_response = await approved.request_approval(request)
    denied_response = await denied_wins.request_approval(request)

    assert approved_response.decision is ApprovalDecision.APPROVED
    assert denied_response.decision is ApprovalDecision.DENIED


def test_smoke_tiers_are_explicit_and_small() -> None:
    core = [
        scenario
        for scenario in load_scenarios()
        if scenario.tier == "smoke" and scenario.group != "learning"
    ]
    memory = [
        scenario
        for scenario in load_memory_scenarios()
        if scenario.tier == "smoke"
    ]

    assert {scenario.id for scenario in core} == {
        "eval-01",
        "eval-02",
        "eval-04",
        "eval-05",
        "eval-06",
        "eval-14",
        "eval-19",
        "eval-30",
        "skill-01",
    }
    assert {scenario.id for scenario in memory} == {"memory-01", "memory-05"}
    learning = [
        scenario
        for scenario in load_scenarios()
        if scenario.tier == "smoke" and scenario.group == "learning"
    ]
    assert {scenario.id for scenario in learning} == {
        "learning-01",
        "learning-02",
        "learning-05b",
    }


def test_learning_adapter_uses_same_usage_ledger(tmp_path: Path) -> None:
    scenario = next(
        item for item in load_scenarios() if item.id == "learning-02"
    )
    mining_raw_output = '{"clusters":[{"id":"cluster-1"}]}' + "矿" * 1400
    distillation_raw_output = '{"action":"none"}' + "蒸" * 1400
    outcome = SimpleNamespace(
        mining=SimpleNamespace(
            input_tokens=80,
            output_tokens=20,
            total_tokens=100,
            pattern_mining_calls=1,
            distillation_calls=1,
            total_duration_ms=250.0,
            scanned_task_count=3,
            pattern_mining_raw_output=mining_raw_output,
            clusters=(
                SimpleNamespace(
                    model_dump=lambda **_: {
                        "id": "cluster-1",
                        "task_ids": ["a", "b", "c"],
                        "pattern_name": "python-debug",
                    }
                ),
            ),
            distillations=(
                SimpleNamespace(
                    cluster_name="python-debug",
                    action="none",
                    reason="证据不足",
                    proposed_name=None,
                    existing_skill_name=None,
                    related_skill_names=(),
                    raw_output=distillation_raw_output,
                    error=None,
                ),
            ),
        ),
        environment=SimpleNamespace(root=tmp_path),
        error=None,
    )
    verdict = SimpleNamespace(passed=False, reasons=("未创建候选",))

    sample = learning_sample_from_outcome(
        scenario,
        outcome,
        verdict,
        provider="fake",
        model="fake-model",
        run_index=1,
    )

    assert sample.suite == "learning"
    assert sample.usage.provider_total.total_tokens == 100
    assert sample.usage.provider_total.model_calls == 2
    assert sample.provider_chargeable_tokens == 100
    assert sample.duration_s == pytest.approx(0.25)
    assert sample.learning_diagnostics is not None
    assert sample.learning_diagnostics.mining.scanned_task_count == 3
    assert sample.learning_diagnostics.mining.cluster_count == 1
    assert sample.learning_diagnostics.mining.raw_output == mining_raw_output
    assert sample.learning_diagnostics.distillations[0].action == "none"
    assert (
        sample.learning_diagnostics.distillations[0].raw_output
        == distillation_raw_output
    )
    assert (tmp_path / "sample.json").exists()
    payload = json.loads((tmp_path / "sample.json").read_text(encoding="utf-8"))
    diagnostics = payload["learning_diagnostics"]
    assert diagnostics["mining"]["raw_output"] == mining_raw_output
    assert diagnostics["distillations"][0]["raw_output"] == (
        distillation_raw_output
    )

    markdown = render_report(_report(sample))
    assert "Pattern Mining raw_output" in markdown
    assert "Distillation python-debug raw_output" in markdown
    assert "已截断" in markdown
    assert mining_raw_output not in markdown
    assert distillation_raw_output not in markdown


@pytest.mark.asyncio
async def test_unified_cli_writes_json_markdown_and_sample_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _ = fake_registry([model_response(content="答案是 5。")])
    monkeypatch.setattr(
        run_suite,
        "load_effective_model_configuration",
        lambda: SimpleNamespace(settings=ModelSettings(_env_file=None)),
    )
    monkeypatch.setattr(run_suite, "ModelAdapterRegistry", lambda settings: registry)
    output = tmp_path / "report"
    root = tmp_path / "runs"
    args = argparse.Namespace(
        suite=["core"],
        tier="smoke",
        scenario=["eval-01"],
        group=None,
        tag=None,
        runs=1,
        provider="fake",
        model="fake-model",
        root=root,
        out_dir=output,
        baseline=None,
        save_baseline=None,
        compare_memory_off=False,
        print=False,
        allow_failures=False,
    )

    exit_code = await run_suite.main(args)

    assert exit_code == 0
    report = EvalSuiteReport.load_json(output / "report.json")
    assert report.samples[0].scenario_id == "eval-01"
    assert report.scenario_digest
    assert report.requested_runs == 1
    assert report.expected_sample_count == 1
    assert report.actual_sample_count == 1
    assert report.complete is True
    assert (output / "report.md").exists()
    run_root = next(root.glob("eval-*/core/eval-01/run-1"))
    assert (run_root / "trace.json").exists()
    assert (run_root / "sample.json").exists()


@pytest.mark.asyncio
async def test_unified_cli_refuses_to_save_incomplete_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _ = fake_registry([])
    monkeypatch.setattr(
        run_suite,
        "load_effective_model_configuration",
        lambda: SimpleNamespace(settings=ModelSettings(_env_file=None)),
    )
    monkeypatch.setattr(run_suite, "ModelAdapterRegistry", lambda settings: registry)

    async def append_only_first_run(
        args: argparse.Namespace,
        *,
        report: EvalSuiteReport,
        **_: object,
    ) -> None:
        report.samples.append(_sample("eval-01", run_index=1))

    monkeypatch.setattr(run_suite, "_run_core", append_only_first_run)
    output = tmp_path / "report"
    baseline = tmp_path / "baseline.json"
    args = argparse.Namespace(
        suite=["core"],
        tier="smoke",
        scenario=["eval-01"],
        group=None,
        tag=None,
        runs=2,
        provider="fake",
        model="fake-model",
        root=tmp_path / "runs",
        out_dir=output,
        baseline=None,
        save_baseline=baseline,
        compare_memory_off=False,
        print=False,
        allow_failures=True,
    )

    exit_code = await run_suite.main(args)

    report = EvalSuiteReport.load_json(output / "report.json")
    assert exit_code == 1
    assert report.complete is False
    assert report.actual_sample_count == 1
    assert report.expected_sample_count == 2
    assert not baseline.exists()
