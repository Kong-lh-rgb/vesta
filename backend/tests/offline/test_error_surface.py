"""统一错误表面的不变量测试（P2-17）。

原则：不重构现有错误体系，验证已承诺的边界不回退：
1. AgentError.type 是稳定标识符（异常类名），CLI/Desktop 同源渲染；
2. Provider / Tool / Run Budget 的停止原因枚举互不重叠、语义清晰；
3. 错误消息不携带 API Key 等密钥材料；
4. Computer Runtime 错误码稳定（canonicalize 迁移映射闭合）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.result import AgentError, AgentStopReason
from app.computer import errors as computer_errors

pytestmark = pytest.mark.asyncio


def test_agent_error_type_is_stable_identifier() -> None:
    """AgentError.type 用异常类名作稳定码，同错误在 CLI/Desktop 同源。"""

    error = AgentError(type="ModelInvocationError", message="连接失败")

    assert error.type == "ModelInvocationError"
    # CLI 与 Desktop 都读同一 trace payload 的 type+message，无第二套映射。
    assert AgentError.model_validate_json(error.model_dump_json()) == error


def test_stop_reasons_are_distinct_and_exhaustive() -> None:
    """Run Budget / max_steps / tool rounds / cancel 的停止原因互不重叠。"""

    reasons = {reason.value for reason in AgentStopReason}
    # 三类预算相关停止原因必须可区分（前端据此渲染不同文案）。
    assert {
        "run_budget",
        "max_steps",
        "repeated_tool_call",
    } <= reasons
    assert len(reasons) == len(AgentStopReason)


def test_provider_error_message_hides_api_key() -> None:
    """Provider 适配器错误不回显密钥材料。"""

    from app.models.errors import ModelAdapterError

    secret = "sk-super-secret-key-123"
    # 模拟底层 SDK 常见行为：把 key 拼进异常消息。
    inner = RuntimeError(f"401 Unauthorized: invalid api_key {secret!r}")
    wrapped = ModelAdapterError(f"provider request failed: {inner}")

    assert secret not in str(wrapped)


async def test_tool_result_error_never_includes_env_secrets(monkeypatch) -> None:
    """工具执行错误不继承宿主敏感环境变量。"""

    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak-check")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leak")
    from app.sandbox import SandboxSupervisor
    from app.tools.builtin.shell import ShellCommandTool

    workspace = Path("/tmp/vesta-error-surface-ws")
    workspace.mkdir(exist_ok=True)
    tool = ShellCommandTool(
        workspace, sandbox_supervisor=SandboxSupervisor(workspace)
    )

    result = await tool.execute(
        {"command": "printenv OPENAI_API_KEY ANTHROPIC_API_KEY || echo none"}
    )

    payload = str(result)
    assert "sk-leak-check" not in payload
    assert "sk-ant-leak" not in payload


def test_computer_error_codes_are_closed_vocabulary() -> None:
    """Computer 错误码是闭合词汇表；legacy 码全部映射到规范码。"""

    canonical = {
        getattr(computer_errors, name)
        for name in dir(computer_errors)
        if name.isupper() and isinstance(getattr(computer_errors, name), str)
    }
    canonical -= {"LEGACY_TO_CANONICAL"}
    # 每个 legacy 码都映射到词汇表内的规范码。
    for legacy, mapped in computer_errors.LEGACY_TO_CANONICAL.items():
        assert mapped in canonical, f"legacy {legacy} 映射到未知码 {mapped}"
        assert computer_errors.canonicalize(legacy) == mapped
    # 未知码原样返回（前向兼容）。
    assert computer_errors.canonicalize("brand_new_code") == "brand_new_code"
    assert computer_errors.canonicalize(None) is None
