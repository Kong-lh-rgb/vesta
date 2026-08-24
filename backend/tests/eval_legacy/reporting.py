"""综合评测报告渲染与Baseline比较。"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from pydantic import BaseModel, ConfigDict

from .records import (
    EvalSampleRecord,
    EvalSuiteReport,
    format_stability_key,
)

_RAW_OUTPUT_PREVIEW_CHARS = 1200


class EvalComparison(BaseModel):
    """当前报告相对同模型Baseline的结构化变化。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    model: str
    blocked: bool = False
    regressions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    pass_rate_delta: float = 0.0
    stable_pass_rate_delta: float = 0.0
    chargeable_tokens_delta_ratio: float | None = None


def compare_reports(
    current: EvalSuiteReport,
    baseline: EvalSuiteReport,
    *,
    cost_warning_ratio: float = 0.20,
) -> EvalComparison:
    """比较同Provider/Model报告；安全与稳定正确性退化会阻断。"""

    current.refresh_completeness()
    baseline.refresh_completeness()
    if not current.complete:
        raise ValueError(
            "当前评测样本不完整，不能与Baseline比较："
            + "; ".join(current.completeness_issues)
        )
    if not baseline.complete:
        raise ValueError(
            "Baseline样本不完整，不能用于比较："
            + "; ".join(baseline.completeness_issues)
        )
    if (current.provider, current.model) != (baseline.provider, baseline.model):
        raise ValueError(
            "Baseline provider/model 与当前评测不一致："
            f"{baseline.provider}/{baseline.model} != "
            f"{current.provider}/{current.model}"
        )
    if current.suites != baseline.suites or current.tier != baseline.tier:
        raise ValueError("Baseline suites/tier 与当前评测不一致")
    if current.requested_runs != baseline.requested_runs:
        raise ValueError(
            "Baseline requested_runs 与当前评测不一致："
            f"{baseline.requested_runs} != {current.requested_runs}"
        )
    if (
        current.scenario_digest is not None
        and baseline.scenario_digest is not None
        and current.scenario_digest != baseline.scenario_digest
    ):
        raise ValueError("Baseline 场景定义版本与当前评测不一致")
    current_keys = set(current.stability_groups)
    baseline_keys = set(baseline.stability_groups)
    if current_keys != baseline_keys:
        raise ValueError("Baseline 场景集合与当前评测不一致")

    for key in sorted(current_keys, key=_stability_sort_key):
        current_indices = sorted(
            sample.run_index for sample in current.stability_groups[key]
        )
        baseline_indices = sorted(
            sample.run_index for sample in baseline.stability_groups[key]
        )
        if current_indices != baseline_indices:
            raise ValueError(
                "Baseline每个稳定性键的样本数量或Run编号与当前评测不一致："
                f"{format_stability_key(key)} "
                f"baseline={baseline_indices}, current={current_indices}"
            )

    current_groups = current.stability_groups
    regressions: list[str] = []
    for key, old_samples in baseline.stability_groups.items():
        if not all(sample.passed for sample in old_samples):
            continue
        new_samples = current_groups.get(key)
        if new_samples is not None and not all(sample.passed for sample in new_samples):
            regressions.append(f"{_format_key(key)}：稳定通过 → 不稳定/失败")

    failed_safety = [
        sample
        for sample in current.samples
        if sample.group == "safety" and not sample.passed
    ]
    regressions.extend(
        f"安全场景 {sample.scenario_id} run#{sample.run_index} 失败"
        for sample in failed_safety
    )

    warnings: list[str] = []
    cost_delta = _ratio_delta(
        current.average_chargeable_tokens,
        baseline.average_chargeable_tokens,
    )
    if cost_delta is not None and cost_delta > cost_warning_ratio:
        warnings.append(
            "平均可计费Token较Baseline增加"
            f" {cost_delta:.1%}（V1仅警告，不阻断）"
        )

    return EvalComparison(
        provider=current.provider,
        model=current.model,
        blocked=bool(regressions),
        regressions=tuple(dict.fromkeys(regressions)),
        warnings=tuple(warnings),
        pass_rate_delta=current.pass_rate - baseline.pass_rate,
        stable_pass_rate_delta=(
            current.stable_pass_rate - baseline.stable_pass_rate
        ),
        chargeable_tokens_delta_ratio=cost_delta,
    )


def render_report(report: EvalSuiteReport) -> str:
    """渲染统一Markdown报告。"""

    report.refresh_completeness()
    cache_rate = report.average_cache_hit_rate
    safety_rate = report.safety_pass_rate
    lines = [
        "# Vesta Agent 综合评测报告",
        "",
        "## 汇总",
        "",
        "| 指标 | 值 |",
        "| --- | --- |",
        f"| 请求重复次数 | {report.requested_runs} |",
        f"| 预期样本数 | {report.expected_sample_count} |",
        f"| 实际样本数 | {report.actual_sample_count} |",
        f"| 样本完整性 | {'✅ 完整' if report.complete else '❌ 不完整'} |",
        f"| 通过数 | {report.passed_count} |",
        f"| 样本通过率 | {report.pass_rate:.1%} |",
        f"| 稳定通过率 | {report.stable_pass_rate:.1%} |",
        f"| 安全场景通过率 | {_percent(safety_rate)} |",
        f"| 平均 Steps | {report.average_steps:.1f} |",
        f"| 平均模型调用 | {report.average_model_calls:.1f} |",
        f"| 平均可计费 Token | {report.average_chargeable_tokens:.0f} |",
        f"| P95 可计费 Token | {report.p95_chargeable_tokens} |",
        f"| 平均缓存命中率 | {_percent(cache_rate)} |",
        f"| 平均耗时 | {report.average_duration_s:.1f}s |",
        "",
        "## 运行信息",
        "",
        f"- Provider / Model：{report.provider} / {report.model}",
        f"- Suites：{', '.join(report.suites)}",
        f"- Tier：{report.tier}",
        f"- Git Commit：{report.git_commit or '-'}",
        f"- Scenario Digest：{report.scenario_digest or '-'}",
        f"- 生成时间：{report.generated_at}",
        f"- 运行现场：{report.run_root or '-'}",
        "",
        "## 样本完整性",
        "",
    ]
    if report.completeness_issues:
        lines.extend(f"- {issue}" for issue in report.completeness_issues)
    else:
        lines.append("所有稳定性键均包含完整的重复运行样本。")
    lines.extend(
        [
            "",
            "| 稳定性样本 | 期望 Run | 实际 Run | 完整 |",
            "| --- | --- | --- | --- |",
        ]
    )
    groups = report.stability_groups
    expected_indices = list(range(1, report.requested_runs + 1))
    for key in sorted(report.expected_key_set, key=_stability_sort_key):
        actual_indices = sorted(
            sample.run_index for sample in groups.get(key, [])
        )
        complete = actual_indices == expected_indices
        lines.append(
            f"| {format_stability_key(key)} | {expected_indices} | "
            f"{actual_indices or '-'} | {'✅' if complete else '❌'} |"
        )
    lines.extend(
        [
            "",
            "## 分组结果",
            "",
            "| Suite / Group | 通过 | 样本 | 通过率 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for key, samples in sorted(_group_samples(report.samples).items()):
        passed = sum(sample.passed for sample in samples)
        lines.append(
            f"| {key} | {passed} | {len(samples)} | "
            f"{passed / len(samples):.1%} |"
        )

    lines.extend(
        [
            "",
            "## 分样本",
            "",
            "| Suite | 场景 / Phase | Run | 结果 | Stop | Steps | Tools | "
            "Main | Summary | Reflection | Total | Chargeable | Cache | 耗时 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | "
            "--- | --- | --- | --- | --- |",
        ]
    )
    for sample in report.samples:
        usage = sample.usage
        label = sample.scenario_id
        if sample.phase_id:
            label += f"/{sample.phase_id}"
        lines.append(
            f"| {sample.suite} | {label} | {sample.run_index} | "
            f"{'✅' if sample.passed else '❌'} | {sample.stop_reason or '-'} | "
            f"{sample.steps} | {sample.tool_calls} | "
            f"{usage.main_agent.total_tokens} | "
            f"{usage.context_summary.total_tokens} | "
            f"{usage.memory_reflection.total_tokens} | "
            f"{usage.provider_total.total_tokens} | "
            f"{sample.provider_chargeable_tokens} | "
            f"{_percent(sample.cache_hit_rate)} | {sample.duration_s:.1f}s |"
        )

    lines.extend(["", "## 失败归因", ""])
    failures = [sample for sample in report.samples if not sample.passed]
    if not failures:
        lines.append("无失败样本。")
    for sample in failures:
        phase = f"/{sample.phase_id}" if sample.phase_id else ""
        lines.append(
            f"### {sample.suite} · {sample.scenario_id}{phase} "
            f"· run#{sample.run_index}"
        )
        for check in sample.checks:
            if check.applicable and not check.ok:
                lines.append(f"- [{check.name}] {check.detail}")
        if sample.error:
            lines.append(f"- 运行错误：{sample.error}")
        if sample.trace_path:
            lines.append(f"- Trace：`{sample.trace_path}`")
        diagnostics = sample.learning_diagnostics
        if diagnostics is not None:
            mining = diagnostics.mining
            lines.append(
                "- Pattern Mining："
                f"scanned={mining.scanned_task_count}, "
                f"clusters={mining.cluster_count}"
            )
            _append_raw_output(
                lines,
                label="Pattern Mining",
                raw_output=mining.raw_output,
            )
            for cluster in mining.clusters:
                lines.append(
                    "  - Cluster："
                    f"{cluster.get('pattern_name', '-')} · "
                    f"tasks={cluster.get('task_ids', [])}"
                )
            if not diagnostics.distillations:
                lines.append("- Distillation：未调用")
            for item in diagnostics.distillations:
                lines.append(
                    "- Distillation："
                    f"cluster={item.cluster_name}, action={item.action or '-'}, "
                    f"reason={item.reason or '-'}, error={item.error or '-'}"
                )
                _append_raw_output(
                    lines,
                    label=f"Distillation {item.cluster_name}",
                    raw_output=item.raw_output,
                )
                _append_raw_output(
                    lines,
                    label=f"Overlap Adjudication {item.cluster_name}",
                    raw_output=item.adjudication_raw_output,
                )
        lines.append("")
    return "\n".join(lines)


def render_comparison(comparison: EvalComparison) -> str:
    """渲染Baseline差异报告。"""

    lines = [
        "# Vesta Eval Baseline Comparison",
        "",
        f"- Provider / Model：{comparison.provider} / {comparison.model}",
        f"- 结论：{'BLOCKED' if comparison.blocked else 'PASS'}",
        f"- 通过率变化：{comparison.pass_rate_delta:+.1%}",
        f"- 稳定通过率变化：{comparison.stable_pass_rate_delta:+.1%}",
        "- 可计费Token变化："
        + (
            f"{comparison.chargeable_tokens_delta_ratio:+.1%}"
            if comparison.chargeable_tokens_delta_ratio is not None
            else "无法比较"
        ),
        "",
        "## 阻断项",
        "",
    ]
    lines.extend(f"- {item}" for item in comparison.regressions)
    if not comparison.regressions:
        lines.append("无。")
    lines.extend(["", "## 警告", ""])
    lines.extend(f"- {item}" for item in comparison.warnings)
    if not comparison.warnings:
        lines.append("无。")
    return "\n".join(lines)


def stop_reason_counts(report: EvalSuiteReport) -> Counter[str]:
    """为后续前端或分析脚本提供稳定的停止原因分布。"""

    return Counter(sample.stop_reason or "unknown" for sample in report.samples)


def _group_samples(
    samples: list[EvalSampleRecord],
) -> dict[str, list[EvalSampleRecord]]:
    grouped: dict[str, list[EvalSampleRecord]] = defaultdict(list)
    for sample in samples:
        grouped[f"{sample.suite} / {sample.group}"].append(sample)
    return dict(grouped)


def _format_key(key: tuple[str, str, str | None, str]) -> str:
    return format_stability_key(key)


def _stability_sort_key(
    key: tuple[str, str, str | None, str],
) -> tuple[str, str, str, str]:
    suite, scenario, phase, mode = key
    return (suite, scenario, phase or "", mode)


def _ratio_delta(current: float, baseline: float) -> float | None:
    if baseline <= 0:
        return None
    return (current - baseline) / baseline


def _append_raw_output(
    lines: list[str],
    *,
    label: str,
    raw_output: str | None,
) -> None:
    """在失败报告中安全展示截断后的模型原始输出。"""

    if raw_output is None:
        return
    preview = raw_output[:_RAW_OUTPUT_PREVIEW_CHARS]
    if len(raw_output) > _RAW_OUTPUT_PREVIEW_CHARS:
        preview += (
            f"…（已截断，原始输出共 {len(raw_output)} 字符）"
        )
    lines.extend(
        [
            f"- {label} raw_output（报告预览）：",
            "```json",
            json.dumps(preview, ensure_ascii=False),
            "```",
        ]
    )


def _percent(value: float | None) -> str:
    return "未知" if value is None else f"{value:.1%}"


__all__ = [
    "EvalComparison",
    "compare_reports",
    "render_comparison",
    "render_report",
    "stop_reason_counts",
]
