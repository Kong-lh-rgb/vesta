"""前缀复用优先的压缩决策（defer / 强制压缩线 / 大折叠）离线测试。

覆盖：预算新线（强制压缩线与强制目标）、压缩目标覆写直达 Reducer、
未摘要块数上限助手、大折叠摘要输出上限、配置校验。
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from app.context import (
    ContextBudgetPolicy,
    ContextManager,
    ContextSettings,
    ContextSummarizer,
    ConversationReducer,
    ConversationSummaryState,
    ModelCapabilities,
    RollingConversationSummary,
    SummaryGenerationResult,
)
from app.context.capabilities import CapabilitySource
from app.models.types import Message, MessageRole, ModelUsage


def _caps(
    context_window: int = 131_072,
    max_output: int = 8_192,
) -> ModelCapabilities:
    return ModelCapabilities(
        provider="qwen",
        model="qwen3.7-plus",
        context_window=context_window,
        max_output_tokens=max_output,
        source=CapabilitySource.BUILTIN,
    )


# ----------------------------------------------------------------------
# 预算新线：强制压缩线与强制目标
# ----------------------------------------------------------------------


def test_budget_compact_lines_default_to_twice_soft_line() -> None:
    """大窗口默认：128K 强制线，压回 64K 软线。"""

    policy = ContextBudgetPolicy(safety_margin_tokens=4_096)
    budget = policy.compute(
        _caps(context_window=1_048_576, max_output=4_096),
        max_output_tokens=4_096,
    )

    assert budget.trigger_tokens == 51_200  # 64K 软线 × 0.80
    assert budget.target_tokens == 28_800  # 64K 软线 × 0.45
    assert budget.compact_ceiling_tokens == 128_000  # preferred × 2
    assert budget.forced_target_tokens == 64_000  # 压回软线


def test_budget_compact_ceiling_never_exceeds_hard_trigger() -> None:
    """小窗口：强制线被硬保护触发线钳制，defer 区间退化消失。"""

    policy = ContextBudgetPolicy(safety_margin_tokens=100)
    budget = policy.compute(
        _caps(context_window=2_140, max_output=512),
        max_output_tokens=512,
    )

    assert budget.compact_ceiling_tokens == budget.hard_trigger_tokens
    # 无 defer 区间时，强制目标退化为深压目标，行为与旧版本一致。
    assert budget.forced_target_tokens == budget.target_tokens


def test_budget_compact_input_tokens_override() -> None:
    policy = ContextBudgetPolicy(
        safety_margin_tokens=100,
        compact_input_tokens=96_000,
    )
    budget = policy.compute(
        _caps(context_window=1_048_576, max_output=4_096),
        max_output_tokens=4_096,
    )

    assert budget.compact_ceiling_tokens == 96_000
    # 强制目标 = 强制线的一半（默认 128K 时恰为 64K 软线）。
    assert budget.forced_target_tokens == 48_000


def test_budget_rejects_non_positive_compact_input_tokens() -> None:
    with pytest.raises(ValueError, match="compact_input_tokens"):
        ContextBudgetPolicy(compact_input_tokens=0)


def test_settings_rejects_lower_large_fold_summary_cap() -> None:
    with pytest.raises(
        ValueError,
        match="context_summary_max_output_tokens_large_fold",
    ):
        ContextSettings(
            _env_file=None,
            context_summary_max_output_tokens_large_fold=512,
        )


# ----------------------------------------------------------------------
# 压缩目标覆写直达 Reducer
# ----------------------------------------------------------------------


class _TargetCapturingReducer(ConversationReducer):
    """捕获 reduce 收到的目标线。"""

    def __init__(self) -> None:
        super().__init__(_FixedSummarizer())
        self.targets: list[int] = []

    async def reduce(self, **kwargs):
        self.targets.append(kwargs["target_tokens"])
        return await super().reduce(**kwargs)


class _FixedSummarizer(ContextSummarizer):
    async def summarize(
        self,
        previous_summary: RollingConversationSummary | None,
        messages: Sequence[Message],
        *,
        max_output_tokens: int | None = None,
    ) -> SummaryGenerationResult:
        return SummaryGenerationResult(
            summary=RollingConversationSummary(current_objective="目标"),
            usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        )


def _big_history(blocks: int = 6) -> tuple[Message, ...]:
    messages: list[Message] = []
    for index in range(blocks):
        messages.append(
            Message(role=MessageRole.USER, content=f"问题 {index} " + "细" * 200)
        )
        messages.append(
            Message(
                role=MessageRole.ASSISTANT,
                content=f"回答 {index} " + "节" * 200,
            )
        )
    return tuple(messages)


@pytest.mark.asyncio
async def test_prepare_forwards_compaction_target_override() -> None:
    reducer = _TargetCapturingReducer()
    manager = ContextManager(
        # preferred 1K：确保测试历史越过触发线，实际走到 Reducer。
        budget_policy=ContextBudgetPolicy(
            safety_margin_tokens=100,
            preferred_input_tokens=1_000,
        ),
        conversation_reducer=reducer,
    )
    history = _big_history()
    current = (Message(role=MessageRole.USER, content="当前问题"),)

    await manager.prepare(
        (*history, *current),
        model="qwen3.7-plus",
        provider="qwen",
        history_count=len(history),
        compaction_target_tokens=64_000,
    )

    assert reducer.targets == [64_000]


@pytest.mark.asyncio
async def test_prepare_uses_deep_target_without_override() -> None:
    reducer = _TargetCapturingReducer()
    manager = ContextManager(
        budget_policy=ContextBudgetPolicy(
            safety_margin_tokens=100,
            preferred_input_tokens=1_000,
        ),
        conversation_reducer=reducer,
    )
    history = _big_history()
    current = (Message(role=MessageRole.USER, content="当前问题"),)

    decision = await manager.prepare(
        (*history, *current),
        model="qwen3.7-plus",
        provider="qwen",
        history_count=len(history),
    )

    assert reducer.targets == [decision.target_tokens]


@pytest.mark.asyncio
async def test_prepare_rejects_non_positive_compaction_target() -> None:
    manager = ContextManager()
    with pytest.raises(
        ValueError,
        match="compaction_target_tokens must be greater than zero",
    ):
        await manager.prepare(
            (Message(role=MessageRole.USER, content="hi"),),
            compaction_target_tokens=0,
        )


# ----------------------------------------------------------------------
# 未摘要块数上限（defer 也必须尊重的陈旧度保护）
# ----------------------------------------------------------------------


def test_exceeds_unsummarized_block_limit() -> None:
    manager = ContextManager(
        context_settings=ContextSettings(
            _env_file=None,
            context_max_unsummarized_conversation_blocks=1,
        ),
    )
    # 每对 user/assistant 是一个对话块：blocks=2 → 2 个块。
    history = _big_history(blocks=2)
    covered_first_block = ConversationSummaryState(
        summary=RollingConversationSummary(current_objective="目标"),
        covered_message_count=2,
    )

    assert manager.exceeds_unsummarized_block_limit(history, None) is True
    # 摘要已覆盖第一个块：剩余 1 块不超限。
    assert (
        manager.exceeds_unsummarized_block_limit(
            history, covered_first_block
        )
        is False
    )
    # 空历史不再统计。
    assert manager.exceeds_unsummarized_block_limit((), None) is False


# ----------------------------------------------------------------------
# 大折叠摘要输出上限
# ----------------------------------------------------------------------


class _OutputLimitCapturingSummarizer(ContextSummarizer):
    def __init__(self) -> None:
        self.limits: list[int | None] = []

    async def summarize(
        self,
        previous_summary: RollingConversationSummary | None,
        messages: Sequence[Message],
        *,
        max_output_tokens: int | None = None,
    ) -> SummaryGenerationResult:
        self.limits.append(max_output_tokens)
        return SummaryGenerationResult(
            summary=RollingConversationSummary(current_objective="目标"),
            usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        )


def _flat_estimate(messages: Sequence[Message]) -> int:
    return sum(len(message.content or "") + 4 for message in messages)


@pytest.mark.asyncio
async def test_reducer_raises_summary_limit_for_large_fold() -> None:
    summarizer = _OutputLimitCapturingSummarizer()
    reducer = ConversationReducer(
        summarizer,
        keep_recent_conversation_blocks=1,
        keep_recent_tool_rounds=0,
        large_fold_span_tokens=1_000,
        large_fold_max_output_tokens=2_048,
    )
    history = _big_history(blocks=4)

    result = await reducer.reduce(
        raw_history=history,
        prepared_messages=history,
        current_messages=(),
        previous_state=None,
        # 跨度 = 5_000 − 1_000 = 4_000 ≥ 1_000：放宽到 2048。
        initial_estimated_input_tokens=5_000,
        target_tokens=1_000,
        estimate=_flat_estimate,
    )

    assert result.error is None
    assert summarizer.limits == [2_048]


@pytest.mark.asyncio
async def test_reducer_keeps_default_limit_for_small_fold() -> None:
    summarizer = _OutputLimitCapturingSummarizer()
    reducer = ConversationReducer(
        summarizer,
        keep_recent_conversation_blocks=1,
        keep_recent_tool_rounds=0,
        large_fold_span_tokens=1_000,
        large_fold_max_output_tokens=2_048,
    )
    history = _big_history(blocks=4)

    await reducer.reduce(
        raw_history=history,
        prepared_messages=history,
        current_messages=(),
        previous_state=None,
        # 跨度 = 1_400 − 1_000 = 400 < 1_000：不覆写。
        initial_estimated_input_tokens=1_400,
        target_tokens=1_000,
        estimate=_flat_estimate,
    )

    assert summarizer.limits == [None]


@pytest.mark.asyncio
async def test_reducer_without_large_fold_config_never_overrides() -> None:
    summarizer = _OutputLimitCapturingSummarizer()
    reducer = ConversationReducer(
        summarizer,
        keep_recent_conversation_blocks=1,
        keep_recent_tool_rounds=0,
    )
    history = _big_history(blocks=4)

    await reducer.reduce(
        raw_history=history,
        prepared_messages=history,
        current_messages=(),
        previous_state=None,
        initial_estimated_input_tokens=100_000,
        target_tokens=1_000,
        estimate=_flat_estimate,
    )

    assert summarizer.limits == [None]
