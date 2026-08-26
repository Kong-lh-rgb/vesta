from __future__ import annotations

from typing import Any

import pytest

from app.cli_ui import print_banner, print_startup_status, run_setup
from app.model_settings import ModelSettingsUpdate, ProviderSettingsUpdate
from app.models.config import ModelSettings
from app.models.types import ModelProvider


class StubModelSettingsService:
    def __init__(self) -> None:
        self.saved: ModelSettingsUpdate | None = None
        self.tested: ProviderSettingsUpdate | None = None

    def view(self, **_: str) -> dict[str, Any]:
        settings = ModelSettings()
        providers = []
        for provider in ModelProvider:
            prefix = provider.value
            providers.append(
                {
                    "provider": provider.value,
                    "model": getattr(settings, f"{prefix}_model"),
                    "base_url": getattr(settings, f"{prefix}_base_url"),
                    "api_style": (
                        "anthropic_messages"
                        if provider is ModelProvider.ANTHROPIC
                        else getattr(settings, f"{prefix}_api_style").value
                    ),
                    "configured": False,
                }
            )
        role = {
            "enabled": True,
            "inherit_main": True,
            "provider": None,
            "model": None,
        }
        return {
            "default_provider": "openai",
            "providers": providers,
            "reflection": role,
            "maintenance": role,
            "summary": role,
        }

    def save(self, update: ModelSettingsUpdate) -> None:
        self.saved = update

    async def test(self, item: ProviderSettingsUpdate) -> dict[str, Any]:
        self.tested = item
        return {
            "provider": item.provider.value,
            "model": item.model,
            "duration_ms": 12.0,
        }


def test_cli_banner_and_status_are_compact(capsys: pytest.CaptureFixture[str]) -> None:
    print_banner()
    print_startup_status(
        (("主模型", "deepseek/deepseek-chat"), ("会话", "已创建 abc123")),
        notices=("存在 MCP 启动失败",),
    )

    output = capsys.readouterr().out
    assert "Vesta CLI" in output
    assert "deepseek/deepseek-chat" in output
    assert "存在 MCP 启动失败" in output
    assert "/help 查看命令" in output


@pytest.mark.asyncio
async def test_setup_saves_selected_provider_without_echoing_secret(
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = StubModelSettingsService()
    answers = iter(
        (
            "3",  # DeepSeek
            "deepseek-chat",
            "",
            "",  # 确认保存
            "n",  # 跳过连接测试
            "n",  # 不立即进入聊天
        )
    )
    messages: list[str] = []

    should_start = await run_setup(
        service=service,  # type: ignore[arg-type]
        input_fn=lambda _: next(answers),
        secret_fn=lambda _: "sk-private-test",
        output_fn=messages.append,
    )

    assert should_start is False
    assert service.saved is not None
    assert service.saved.default_provider is ModelProvider.DEEPSEEK
    selected = next(
        item
        for item in service.saved.providers
        if item.provider is ModelProvider.DEEPSEEK
    )
    assert selected.api_key == "sk-private-test"
    assert "sk-private-test" not in "\n".join(messages)
    assert "sk-private-test" not in capsys.readouterr().out
