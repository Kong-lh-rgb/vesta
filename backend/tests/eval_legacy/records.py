"""跨评测套件共享的样本与报告模型。"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agent.budget import chargeable_tokens
from app.agent.events import AgentEvent
from app.trace import RunUsageSummary, summarize_run_usage

type StabilityKey = tuple[str, str, str | None, str]


class EvalCheckRecord(BaseModel):
    """一条可序列化的评测断言。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    ok: bool
    detail: str = ""
    applicable: bool = True


class LearningMiningRecord(BaseModel):
    """Skill Learning 的 Pattern Mining 中间结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scanned_task_count: int = Field(default=0, ge=0)
    cluster_count: int = Field(default=0, ge=0)
    clusters: tuple[dict[str, Any], ...] = ()
    raw_output: str | None = None


class LearningDistillationRecord(BaseModel):
    """单个模式簇的 Distillation 判断，包括 action=none。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_name: str
    action: str | None = None
    reason: str | None = None
    proposed_name: str | None = None
    existing_skill_name: str | None = None
    related_skill_names: tuple[str, ...] = ()
    raw_output: str | None = None
    adjudication_raw_output: str | None = None
    error: str | None = None


class LearningDiagnostics(BaseModel):
    """综合 Eval 保存的 Skill Learning 可诊断现场。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mining: LearningMiningRecord = Field(default_factory=LearningMiningRecord)
    distillations: tuple[LearningDistillationRecord, ...] = ()


class EvalSampleRecord(BaseModel):
    """任意评测 Harness 输出的统一最小样本。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    suite: str
    scenario_id: str
    scenario_name: str
    group: str
    tier: str = "regression"
    phase_id: str | None = None
    conversation: str | None = None
    mode: str = "on"
    run_index: int = Field(default=1, ge=1)
    provider: str
    model: str
    passed: bool
    checks: tuple[EvalCheckRecord, ...] = ()
    stop_reason: str | None = None
    steps: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    tool_failures: int = Field(default=0, ge=0)
    duration_s: float = Field(default=0.0, ge=0.0)
    usage: RunUsageSummary = Field(default_factory=RunUsageSummary)
    error: str | None = None
    trace_path: str | None = None
    workspace_path: str | None = None
    learning_diagnostics: LearningDiagnostics | None = None

    @property
    def stability_key(self) -> tuple[str, str, str | None, str]:
        """同一语义样本多次运行时使用的稳定性分组键。"""

        return (self.suite, self.scenario_id, self.phase_id, self.mode)

    @property
    def provider_chargeable_tokens(self) -> int:
        """按Provider缓存明细计算全链路可计费Token近似值。"""

        return chargeable_tokens(self.usage.provider_total)

    @property
    def cache_hit_rate(self) -> float | None:
        """返回Provider总输入的缓存命中率；缺失明细时保持未知。"""

        usage = self.usage.provider_total
        if usage.cached_input_tokens is None or usage.input_tokens <= 0:
            return None
        return usage.cached_input_tokens / usage.input_tokens


class EvalSuiteReport(BaseModel):
    """可持久化、可比较的综合评测报告。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 3
    provider: str
    model: str
    suites: tuple[str, ...]
    tier: str
    requested_runs: int = Field(default=1, ge=1)
    expected_sample_count: int = Field(default=0, ge=0)
    expected_stability_keys: tuple[StabilityKey, ...] = ()
    actual_sample_count: int = Field(default=0, ge=0)
    complete: bool = False
    completeness_issues: tuple[str, ...] = ()
    generated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    git_commit: str | None = None
    scenario_digest: str | None = None
    run_root: str | None = None
    samples: list[EvalSampleRecord] = Field(default_factory=list)

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    @property
    def passed_count(self) -> int:
        return sum(sample.passed for sample in self.samples)

    @property
    def pass_rate(self) -> float:
        return self.passed_count / self.sample_count if self.samples else 0.0

    @property
    def stability_groups(self) -> dict[
        StabilityKey, list[EvalSampleRecord]
    ]:
        groups: dict[StabilityKey, list[EvalSampleRecord]] = defaultdict(list)
        for sample in self.samples:
            groups[sample.stability_key].append(sample)
        return dict(groups)

    @property
    def expected_key_set(self) -> set[StabilityKey]:
        """返回运行前声明的稳定性键；旧报告回退为实际键集合。"""

        if self.expected_stability_keys:
            return set(self.expected_stability_keys)
        return set(self.stability_groups)

    def refresh_completeness(self) -> None:
        """根据当前样本重算并持久化完整性状态。"""

        groups = self.stability_groups
        expected_keys = self.expected_key_set
        if not self.expected_stability_keys:
            self.expected_stability_keys = tuple(
                sorted(expected_keys, key=_stability_sort_key)
            )
        if self.expected_sample_count == 0 and expected_keys:
            self.expected_sample_count = len(expected_keys) * self.requested_runs

        issues: list[str] = []
        self.actual_sample_count = self.sample_count
        if self.actual_sample_count != self.expected_sample_count:
            issues.append(
                "样本总数不一致："
                f"expected={self.expected_sample_count}, "
                f"actual={self.actual_sample_count}"
            )

        if len(self.expected_stability_keys) != len(expected_keys):
            issues.append("预期稳定性键存在重复项")
        metadata_count = len(expected_keys) * self.requested_runs
        if self.expected_sample_count != metadata_count:
            issues.append(
                "预期样本元数据不一致："
                f"expected_sample_count={self.expected_sample_count}, "
                f"keys*runs={metadata_count}"
            )

        actual_keys = set(groups)
        for key in sorted(expected_keys - actual_keys, key=_stability_sort_key):
            issues.append(f"缺少稳定性样本：{format_stability_key(key)}")
        for key in sorted(actual_keys - expected_keys, key=_stability_sort_key):
            issues.append(f"出现意外稳定性样本：{format_stability_key(key)}")

        expected_indices = list(range(1, self.requested_runs + 1))
        for key in sorted(expected_keys & actual_keys, key=_stability_sort_key):
            samples = groups[key]
            actual_indices = sorted(sample.run_index for sample in samples)
            if (
                len(samples) != self.requested_runs
                or actual_indices != expected_indices
            ):
                issues.append(
                    f"稳定性样本不完整：{format_stability_key(key)} "
                    f"expected_runs={expected_indices}, "
                    f"actual_runs={actual_indices}"
                )
        self.completeness_issues = tuple(issues)
        self.complete = not issues

    @property
    def stable_pass_count(self) -> int:
        groups = self.stability_groups
        expected_indices = list(range(1, self.requested_runs + 1))
        return sum(
            len(samples) == self.requested_runs
            and sorted(sample.run_index for sample in samples)
            == expected_indices
            and all(sample.passed for sample in samples)
            for key in self.expected_key_set
            if (samples := groups.get(key)) is not None
        )

    @property
    def stable_pass_rate(self) -> float:
        expected_keys = self.expected_key_set
        return (
            self.stable_pass_count / len(expected_keys)
            if expected_keys
            else 0.0
        )

    @property
    def safety_pass_rate(self) -> float | None:
        samples = [sample for sample in self.samples if sample.group == "safety"]
        if not samples:
            return None
        return sum(sample.passed for sample in samples) / len(samples)

    @property
    def average_steps(self) -> float:
        return _average(sample.steps for sample in self.samples)

    @property
    def average_model_calls(self) -> float:
        return _average(
            sample.usage.provider_total.model_calls for sample in self.samples
        )

    @property
    def average_chargeable_tokens(self) -> float:
        return _average(
            sample.provider_chargeable_tokens for sample in self.samples
        )

    @property
    def p95_chargeable_tokens(self) -> int:
        return _nearest_rank(
            [sample.provider_chargeable_tokens for sample in self.samples],
            0.95,
        )

    @property
    def average_duration_s(self) -> float:
        return _average(sample.duration_s for sample in self.samples)

    @property
    def average_cache_hit_rate(self) -> float | None:
        rates = [
            rate
            for sample in self.samples
            if (rate := sample.cache_hit_rate) is not None
        ]
        return mean(rates) if rates else None

    def save_json(self, path: Path) -> None:
        """原子性要求由调用方目录隔离保证，这里写入稳定JSON结构。"""

        self.refresh_completeness()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self.model_dump_json(indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load_json(cls, path: Path) -> EvalSuiteReport:
        report = cls.model_validate_json(path.read_text(encoding="utf-8"))
        report.refresh_completeness()
        return report


def usage_from_events(events: list[AgentEvent]) -> RunUsageSummary:
    """以生产Trace聚合器作为评测Usage的唯一口径。"""

    return summarize_run_usage(events)


def write_trace(events: list[AgentEvent], path: Path) -> None:
    """保存完整事件证据，报告只引用路径而不复制大字段。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [event.model_dump(mode="json") for event in events]
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_sample(sample: EvalSampleRecord, path: Path) -> None:
    """保存单样本结构化现场，便于脱离汇总报告独立诊断。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sample.model_dump_json(indent=2), encoding="utf-8")


def _average(values) -> float:
    collected = list(values)
    return mean(collected) if collected else 0.0


def _nearest_rank(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def format_stability_key(key: StabilityKey) -> str:
    """把稳定性键格式化为适合报告与错误消息的标签。"""

    suite, scenario, phase, mode = key
    label = f"{suite}/{scenario}"
    if phase:
        label += f"/{phase}"
    return f"{label} ({mode})"


def _stability_sort_key(key: StabilityKey) -> tuple[str, str, str, str]:
    suite, scenario, phase, mode = key
    return (suite, scenario, phase or "", mode)


__all__ = [
    "EvalCheckRecord",
    "EvalSampleRecord",
    "EvalSuiteReport",
    "LearningDiagnostics",
    "LearningDistillationRecord",
    "LearningMiningRecord",
    "StabilityKey",
    "format_stability_key",
    "usage_from_events",
    "write_sample",
    "write_trace",
]
