"""默认 system prompt 行为约束测试（最小）。

验证 DEFAULT_SYSTEM_PROMPT 包含 Artifact 使用规则：
- 有用户交付物（文件 / 结果链接）时在最终回答前调用 artifact_publish；
- 普通中间 / 临时 / Trace / Screenshot 不要发布；
- 没有实际交付物时不要形式化调用。
"""

from __future__ import annotations

from app.application import DEFAULT_SYSTEM_PROMPT, Application
from app.models.config import ModelSettings
from app.models.registry import ModelAdapterRegistry


def test_default_system_prompt_mentions_artifact_publish() -> None:
    assert "artifact_publish" in DEFAULT_SYSTEM_PROMPT


def test_default_system_prompt_publish_before_final_answer() -> None:
    assert "最终回答前" in DEFAULT_SYSTEM_PROMPT
    assert "artifact_publish" in DEFAULT_SYSTEM_PROMPT


def test_default_system_prompt_excludes_non_deliverables() -> None:
    # 中间文件 / 临时文件 / Trace / Screenshot 不应发布为 Artifact。
    assert "不要发布为 Artifact" in DEFAULT_SYSTEM_PROMPT
    assert "Trace" in DEFAULT_SYSTEM_PROMPT
    assert "Computer Screenshot" in DEFAULT_SYSTEM_PROMPT


def test_default_system_prompt_no_formal_publish_without_deliverable() -> None:
    assert "没有实际交付物时不要调用" in DEFAULT_SYSTEM_PROMPT


def test_system_prompt_defines_task_granularity() -> None:
    assert "一个用户整体目标通常只创建一个 Task" in DEFAULT_SYSTEM_PROMPT
    assert "拆为该 Task 的 Steps" in DEFAULT_SYSTEM_PROMPT
    assert "彼此独立" in DEFAULT_SYSTEM_PROMPT


def test_system_prompt_requires_a_real_need_before_using_tools() -> None:
    assert "确实依赖实时或外部信息" in DEFAULT_SYSTEM_PROMPT
    assert "普通知识问答、能力说明" in DEFAULT_SYSTEM_PROMPT
    assert "请求的工具不存在时直接如实回答" in DEFAULT_SYSTEM_PROMPT
    assert "不要为了试探或确认" in DEFAULT_SYSTEM_PROMPT


def test_application_uses_default_system_prompt_when_omitted() -> None:
    application = Application(
        provider="fake",
        model="fake-model",
        registry=ModelAdapterRegistry(ModelSettings(_env_file=None)),
    )

    assert application.system_prompt == DEFAULT_SYSTEM_PROMPT


def test_application_allows_explicitly_disabling_system_prompt() -> None:
    application = Application(
        provider="fake",
        model="fake-model",
        system_prompt="",
        registry=ModelAdapterRegistry(ModelSettings(_env_file=None)),
    )

    assert application.system_prompt == ""
