"""Vesta CLI 的启动页与首次模型配置流程。"""

from __future__ import annotations

import getpass
from collections.abc import Callable, Sequence
from typing import Any

from app.model_settings import (
    ModelSettingsService,
    ModelSettingsUpdate,
    ProviderSettingsUpdate,
)
from app.model_settings.models import ModelRoleSettings
from app.models.types import ModelProvider

_PROVIDER_LABELS = {
    ModelProvider.OPENAI: "OpenAI",
    ModelProvider.QWEN: "Qwen",
    ModelProvider.DEEPSEEK: "DeepSeek",
    ModelProvider.ANTHROPIC: "Claude",
}


def print_banner() -> None:
    """输出紧凑、无外部依赖的 CLI 标题。"""

    print()
    print("┌──────────────────────────────────────────────────────────┐")
    print("│  Vesta CLI                                               │")
    print("│  Build agents that remember, continue, and learn.        │")
    print("└──────────────────────────────────────────────────────────┘")


def print_startup_status(
    rows: Sequence[tuple[str, str]],
    *,
    notices: Sequence[str] = (),
) -> None:
    """按固定列宽展示启动状态，避免能力信息堆成多段日志。"""

    print()
    for label, value in rows:
        print(f"  {label:<8} {value}")
    for notice in notices:
        print(f"  提醒      {notice}")
    print()
    print("  输入任务开始工作 · /help 查看命令 · /new 新建会话 · /exit 退出")


async def run_setup(
    *,
    service: ModelSettingsService | None = None,
    input_fn: Callable[[str], str] = input,
    secret_fn: Callable[[str], str] = getpass.getpass,
    output_fn: Callable[[str], Any] = print,
) -> bool:
    """交互配置主模型；返回是否应在保存后直接进入聊天。"""

    resolved = service or ModelSettingsService()
    view = resolved.view(active_provider="", active_model="")
    providers = tuple(view["providers"])

    print_banner()
    output_fn("首次设置 · 密钥保存到 macOS Keychain，非敏感配置保存到 .vesta。")
    output_fn("")
    try:
        selected = _choose_provider(
            providers,
            default_provider=str(view["default_provider"]),
            input_fn=input_fn,
            output_fn=output_fn,
        )
        current = next(
            item for item in providers if item["provider"] == selected.value
        )
        model = input_fn(f"模型名称 [{current['model']}]：").strip()
        model = model or str(current["model"])
        current_base_url = current.get("base_url") or ""
        base_url = input_fn(
            f"API 地址 [{current_base_url or 'Provider 默认地址'}]："
        ).strip()
        base_url = base_url or current_base_url or None

        configured = bool(current.get("configured"))
        key_hint = "回车保留现有密钥" if configured else "必填，输入不会回显"
        api_key = secret_fn(f"API Key（{key_hint}）：").strip() or None
        if not configured and api_key is None:
            output_fn("未提供 API Key，设置已取消。")
            return False

        selected_update = ProviderSettingsUpdate(
            provider=selected,
            model=model,
            base_url=base_url,
            api_style=current["api_style"],
            api_key=api_key,
        )
        updates = tuple(
            selected_update
            if item["provider"] == selected.value
            else ProviderSettingsUpdate(
                provider=item["provider"],
                model=item["model"],
                base_url=item.get("base_url"),
                api_style=item["api_style"],
            )
            for item in providers
        )
        snapshot = ModelSettingsUpdate(
            default_provider=selected,
            providers=updates,
            reflection=ModelRoleSettings.model_validate(view["reflection"]),
            maintenance=ModelRoleSettings.model_validate(view["maintenance"]),
            summary=ModelRoleSettings.model_validate(view["summary"]),
        )

        output_fn("")
        output_fn("将保存以下配置：")
        output_fn(f"  Provider  {_PROVIDER_LABELS[selected]}")
        output_fn(f"  Model     {model}")
        output_fn(f"  Endpoint  {base_url or 'Provider 默认地址'}")
        if not _confirm("确认保存？[Y/n] ", input_fn):
            output_fn("设置已取消。")
            return False
        try:
            resolved.save(snapshot)
        except Exception as exc:
            output_fn(f"保存失败：{type(exc).__name__}: {exc}")
            output_fn("也可以在 backend/.env 中配置 Provider 后重新启动。")
            return False
        output_fn("配置已保存，API Key 未写入项目文件。")

        if _confirm("立即测试连接？[Y/n] ", input_fn):
            output_fn("正在测试模型连接...")
            try:
                result = await resolved.test(selected_update)
            except Exception as exc:
                output_fn(f"连接测试失败：{type(exc).__name__}: {exc}")
                output_fn("配置已保留，可稍后重新运行 --setup 调整。")
            else:
                output_fn(
                    "连接成功："
                    f"{result['provider']}/{result['model']} · "
                    f"{result['duration_ms']:.0f}ms"
                )
        return _confirm("现在进入 Vesta？[Y/n] ", input_fn)
    except (EOFError, KeyboardInterrupt):
        output_fn("\n设置已取消。")
        return False


def _choose_provider(
    providers: Sequence[dict[str, Any]],
    *,
    default_provider: str,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], Any],
) -> ModelProvider:
    output_fn("选择主模型 Provider：")
    for index, item in enumerate(providers, 1):
        provider = ModelProvider(item["provider"])
        markers = []
        if provider.value == default_provider:
            markers.append("当前默认")
        if item.get("configured"):
            markers.append("已配置")
        suffix = f" · {' / '.join(markers)}" if markers else ""
        output_fn(f"  {index}. {_PROVIDER_LABELS[provider]}{suffix}")

    default_index = next(
        (
            index
            for index, item in enumerate(providers, 1)
            if item["provider"] == default_provider
        ),
        1,
    )
    while True:
        raw = input_fn(f"请选择 [{default_index}]：").strip()
        if not raw:
            return ModelProvider(providers[default_index - 1]["provider"])
        if raw.isdigit() and 1 <= int(raw) <= len(providers):
            return ModelProvider(providers[int(raw) - 1]["provider"])
        normalized = raw.lower()
        try:
            return ModelProvider(normalized)
        except ValueError:
            output_fn("请输入列表编号或 provider 名称。")


def _confirm(prompt: str, input_fn: Callable[[str], str]) -> bool:
    return input_fn(prompt).strip().lower() not in {"n", "no", "否"}


__all__ = ["print_banner", "print_startup_status", "run_setup"]
