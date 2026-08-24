"""统一运行Core、Memory与Skill Learning Eval并生成可比较报告。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from app.model_settings import load_effective_model_configuration
from app.models.config import ModelSettings
from app.models.registry import ModelAdapterRegistry
from tests.eval_legacy.memory.assertions import check_phase
from tests.eval_legacy.memory.harness import run_scenario as run_memory_scenario
from tests.eval_legacy.memory.loader import load_scenarios as load_memory_scenarios
from tests.eval_legacy.memory.scenario import MemoryEvalScenario

from . import harness
from .adapters import (
    core_sample_from_outcome,
    learning_sample_from_outcome,
    memory_sample_from_phase,
)
from .assertions import run_checks
from .learning_harness import run_learning_scenario
from .learning_judge import judge_scenario
from .loader import load_scenarios
from .records import EvalSampleRecord, EvalSuiteReport, StabilityKey
from .reporting import compare_reports, render_comparison, render_report
from .scenario import Scenario

_REPORTS_DIR = Path(__file__).resolve().parent / "reports" / "comprehensive"
_VALID_SUITES = ("core", "memory", "learning")
_VALID_TIERS = ("smoke", "regression", "manual")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Vesta comprehensive live eval suites."
    )
    parser.add_argument(
        "--suite",
        action="append",
        choices=_VALID_SUITES,
        help="评测套件；可多次指定，默认 core。",
    )
    parser.add_argument(
        "--tier",
        choices=_VALID_TIERS,
        default="smoke",
        help="smoke 仅关键场景；regression 包含 smoke+regression；manual 仅设备场景。",
    )
    parser.add_argument("--scenario", action="append", help="指定场景ID。")
    parser.add_argument("--group", action="append", help="筛选Core分组。")
    parser.add_argument("--tag", action="append", help="按场景标签筛选。")
    parser.add_argument("--runs", type=int, default=1, help="每条场景运行次数。")
    parser.add_argument("--provider", help="模型提供商。")
    parser.add_argument("--model", help="模型名。")
    parser.add_argument("--root", type=Path, help="保留运行现场的根目录。")
    parser.add_argument("--out-dir", type=Path, help="综合报告输出目录。")
    parser.add_argument("--baseline", type=Path, help="用于比较的report.json。")
    parser.add_argument("--save-baseline", type=Path, help="额外保存本次JSON基线。")
    parser.add_argument(
        "--compare-memory-off",
        action="store_true",
        help="Memory套件同时运行关闭长期记忆的对照组。",
    )
    parser.add_argument("--print", action="store_true", help="打印Markdown报告。")
    parser.add_argument("--allow-failures", action="store_true")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    return args


async def main(args: argparse.Namespace) -> int:
    requested_suites = set(args.suite or ("core",))
    suites = tuple(
        suite for suite in _VALID_SUITES if suite in requested_suites
    )
    effective = load_effective_model_configuration()
    provider, model = _resolve_model(
        args.provider,
        args.model,
        settings=effective.settings,
    )
    registry = ModelAdapterRegistry(effective.settings)
    invocation = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    root = (
        args.root / f"eval-{invocation}"
        if args.root
        else Path(tempfile.mkdtemp(prefix="vesta-comprehensive-eval-"))
    )
    output = args.out_dir or _REPORTS_DIR / invocation
    expected_stability_keys = _expected_stability_keys(args, suites)
    report = EvalSuiteReport(
        provider=provider,
        model=model,
        suites=suites,
        tier=args.tier,
        requested_runs=args.runs,
        expected_sample_count=len(expected_stability_keys) * args.runs,
        expected_stability_keys=expected_stability_keys,
        git_commit=(
            os.environ.get("VESTA_EVAL_GIT_COMMIT")
            or os.environ.get("GITHUB_SHA")
        ),
        scenario_digest=_scenario_digest(args, suites),
        run_root=str(root),
    )

    try:
        if "core" in suites:
            await _run_core(
                args,
                report=report,
                root=root,
                provider=provider,
                model=model,
                registry=registry,
            )
        if "memory" in suites:
            await _run_memory(
                args,
                report=report,
                root=root,
                provider=provider,
                model=model,
                registry=registry,
            )
        if "learning" in suites:
            await _run_learning(
                args,
                report=report,
                root=root,
                provider=provider,
                model=model,
                registry=registry,
            )
    finally:
        await registry.close()
    report.refresh_completeness()
    if not report.samples:
        print("没有匹配的评测场景。", file=sys.stderr)
        return 2

    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "report.json"
    markdown_path = output / "report.md"
    report.save_json(json_path)
    markdown = render_report(report)
    markdown_path.write_text(markdown, encoding="utf-8")
    if args.save_baseline:
        if not report.complete:
            print(
                "评测样本不完整，拒绝保存Baseline："
                + "; ".join(report.completeness_issues),
                file=sys.stderr,
            )
        else:
            args.save_baseline.parent.mkdir(parents=True, exist_ok=True)
            if args.save_baseline.resolve() != json_path.resolve():
                shutil.copyfile(json_path, args.save_baseline)

    comparison_blocked = False
    if args.baseline:
        comparison = compare_reports(
            report,
            EvalSuiteReport.load_json(args.baseline),
        )
        comparison_blocked = comparison.blocked
        (output / "comparison.json").write_text(
            comparison.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (output / "comparison.md").write_text(
            render_comparison(comparison),
            encoding="utf-8",
        )

    print(f"综合报告已保存：{markdown_path}")
    print(f"结构化报告已保存：{json_path}")
    if args.print:
        print("\n" + markdown)
    if not report.complete:
        return 1
    failed = report.passed_count != report.sample_count or comparison_blocked
    return 1 if failed and not args.allow_failures else 0


async def _run_core(
    args: argparse.Namespace,
    *,
    report: EvalSuiteReport,
    root: Path,
    provider: str,
    model: str,
    registry: ModelAdapterRegistry,
) -> None:
    scenarios = _select_core(args)
    for scenario in scenarios:
        for run_index in range(1, args.runs + 1):
            outcome = await harness.run_scenario(
                scenario,
                root=root / "core" / scenario.id / f"run-{run_index}",
                provider=args.provider,
                model=args.model,
                registry=registry,
            )
            checks, passed = await run_checks(scenario, outcome=outcome)
            sample = core_sample_from_outcome(
                scenario,
                outcome,
                checks,
                passed,
                provider=provider,
                model=model,
                run_index=run_index,
            )
            report.samples.append(sample)
            _print_sample(sample)


def _select_core(args: argparse.Namespace) -> list[Scenario]:
    return [
        scenario
        for scenario in load_scenarios()
        if scenario.group != "learning"
        and _matches_tier(scenario.tier, args.tier)
        and _matches_filters(
            scenario.id,
            scenario.group,
            scenario.tags,
            args,
        )
    ]


async def _run_memory(
    args: argparse.Namespace,
    *,
    report: EvalSuiteReport,
    root: Path,
    provider: str,
    model: str,
    registry: ModelAdapterRegistry,
) -> None:
    scenarios = _select_memory(args)
    modes = (
        (("on", True), ("off", False))
        if args.compare_memory_off
        else (("on", True),)
    )
    for scenario in scenarios:
        for run_index in range(1, args.runs + 1):
            for mode, enabled in modes:
                run_root = (
                    root
                    / "memory"
                    / scenario.id
                    / f"run-{run_index}"
                    / mode
                )
                outcome = await run_memory_scenario(
                    scenario,
                    root=run_root,
                    provider=args.provider,
                    model=args.model,
                    registry=registry,
                    memory_enabled=enabled,
                )
                for phase in outcome.phases:
                    checks, passed = check_phase(
                        scenario,
                        phase,
                        aliases=outcome.aliases,
                        mode=mode,
                    )
                    sample = memory_sample_from_phase(
                        scenario,
                        phase,
                        checks,
                        passed,
                        provider=provider,
                        model=model,
                        run_index=run_index,
                        mode=mode,
                        run_root=run_root,
                    )
                    report.samples.append(sample)
                    _print_sample(sample)


def _select_memory(args: argparse.Namespace) -> list[MemoryEvalScenario]:
    return [
        scenario
        for scenario in load_memory_scenarios()
        if _matches_tier(scenario.tier, args.tier)
        and _matches_filters(
            scenario.id,
            "memory",
            scenario.tags,
            args,
            use_group=False,
        )
    ]


async def _run_learning(
    args: argparse.Namespace,
    *,
    report: EvalSuiteReport,
    root: Path,
    provider: str,
    model: str,
    registry: ModelAdapterRegistry,
) -> None:
    for scenario in _select_learning(args):
        for run_index in range(1, args.runs + 1):
            outcome = await run_learning_scenario(
                scenario,
                root=(
                    root / "learning" / scenario.id / f"run-{run_index}"
                ),
                registry=registry,
                provider=args.provider or provider,
                model=args.model or model,
                accept_all=scenario.id == "learning-07",
                reject_all=scenario.id == "learning-08",
            )
            verdict = judge_scenario(scenario, outcome)
            sample = learning_sample_from_outcome(
                scenario,
                outcome,
                verdict,
                provider=provider,
                model=model,
                run_index=run_index,
            )
            report.samples.append(sample)
            _print_sample(sample)


def _select_learning(args: argparse.Namespace) -> list[Scenario]:
    return [
        scenario
        for scenario in load_scenarios()
        if scenario.group == "learning"
        and _matches_tier(scenario.tier, args.tier)
        and _matches_filters(
            scenario.id,
            scenario.group,
            scenario.tags,
            args,
        )
    ]


def _matches_tier(scenario_tier: str, requested: str) -> bool:
    if requested == "regression":
        return scenario_tier in {"smoke", "regression"}
    return scenario_tier == requested


def _matches_filters(
    scenario_id: str,
    group: str,
    tags: tuple[str, ...],
    args: argparse.Namespace,
    *,
    use_group: bool = True,
) -> bool:
    if args.scenario and scenario_id not in args.scenario:
        return False
    if use_group and args.group and group not in args.group:
        return False
    return not args.tag or bool(set(tags) & set(args.tag))


def _resolve_model(
    provider: str | None,
    model: str | None,
    *,
    settings: ModelSettings,
) -> tuple[str, str]:
    resolved_provider = provider or settings.model_default_provider.value
    try:
        resolved_model = model or settings.provider_config(resolved_provider).model
    except ValueError:
        resolved_model = model or "未知"
    return resolved_provider, resolved_model


def _scenario_digest(args: argparse.Namespace, suites: tuple[str, ...]) -> str:
    """哈希实际选中的场景定义，防止不同题集误做Baseline比较。"""

    payload: list[dict[str, object]] = []
    if "core" in suites:
        payload.extend(
            {"suite": "core", "scenario": scenario.model_dump(mode="json")}
            for scenario in _select_core(args)
        )
    if "memory" in suites:
        payload.extend(
            {"suite": "memory", "scenario": scenario.model_dump(mode="json")}
            for scenario in _select_memory(args)
        )
    if "learning" in suites:
        payload.extend(
            {"suite": "learning", "scenario": scenario.model_dump(mode="json")}
            for scenario in _select_learning(args)
        )
    serialized = json.dumps(
        {
            "compare_memory_off": args.compare_memory_off,
            "scenarios": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _expected_stability_keys(
    args: argparse.Namespace,
    suites: tuple[str, ...],
) -> tuple[StabilityKey, ...]:
    """在执行前枚举所有预期稳定性样本，完整缺组时也能被发现。"""

    keys: list[StabilityKey] = []
    if "core" in suites:
        keys.extend(
            ("core", scenario.id, None, "on")
            for scenario in _select_core(args)
        )
    if "memory" in suites:
        modes = ("on", "off") if args.compare_memory_off else ("on",)
        keys.extend(
            ("memory", scenario.id, phase.id, mode)
            for scenario in _select_memory(args)
            for phase in scenario.phases
            for mode in modes
        )
    if "learning" in suites:
        keys.extend(
            ("learning", scenario.id, None, "on")
            for scenario in _select_learning(args)
        )
    if len(keys) != len(set(keys)):
        raise ValueError("评测场景产生了重复的稳定性键")
    return tuple(keys)


def _print_sample(sample: EvalSampleRecord) -> None:
    label = sample.scenario_id
    if sample.phase_id:
        label += f"/{sample.phase_id}"
    print(
        f"{'✅' if sample.passed else '❌'} {sample.suite}/{label} "
        f"run#{sample.run_index} steps={sample.steps} "
        f"calls={sample.usage.provider_total.model_calls} "
        f"chargeable={sample.provider_chargeable_tokens}",
        flush=True,
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(main(_parse_args())))
