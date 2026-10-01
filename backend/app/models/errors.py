"""模型适配层抛出的错误。"""

from __future__ import annotations

import re

# 常见密钥材料形态：sk-… / sk-ant-… / Bearer token。底层 SDK 异常可能
# 把 Authorization 内容拼进消息；错误面向模型、Trace 与前端，必须脱敏。
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{8,}", flags=re.IGNORECASE),
)
_REDACTED = "<redacted>"


def redact_secrets(message: str) -> str:
    """把消息中疑似密钥材料的片段替换为 <redacted>。"""

    redacted = message
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    return redacted


class ModelAdapterError(RuntimeError):
    """模型提供商配置和调用失败的基础错误。

    消息在构造时脱敏：底层 SDK 异常可能携带 Authorization 凭据，错误会
    进入 Trace 与前端展示，不能回显密钥材料。
    """

    def __init__(self, message: str) -> None:
        super().__init__(redact_secrets(message))


class ProviderNotConfiguredError(ModelAdapterError):
    def __init__(self, provider: str, environment_variable: str) -> None:
        super().__init__(
            f"Provider '{provider}' is not configured. "
            f"Set {environment_variable} in the environment."
        )


class UnsupportedProviderError(ModelAdapterError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"No model adapter is registered for provider '{provider}'.")


class UnsupportedMessageError(ModelAdapterError):
    """消息无法转换为模型提供商 API 格式时抛出。"""
