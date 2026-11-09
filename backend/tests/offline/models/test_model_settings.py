"""设置中心 V2 模型配置的离线测试。"""

from __future__ import annotations

import json
import select
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.model_settings import (
    ModelSettingsService,
    ModelSettingsStore,
    ModelSettingsUpdate,
    ProviderSettingsUpdate,
    load_effective_model_configuration,
)
from app.models.config import ModelSettings
from app.models.types import ApiStyle, ModelProvider


@dataclass
class FakeSecrets:
    values: dict[str, str] = field(default_factory=dict)
    reads: list[str] = field(default_factory=list)

    def get(self, provider: str) -> str | None:
        self.reads.append(provider)
        return self.values.get(provider)

    def set(self, provider: str, value: str) -> None:
        self.values[provider] = value

    def delete(self, provider: str) -> None:
        self.values.pop(provider, None)


@dataclass
class FailingSecrets(FakeSecrets):
    fail_on: str | None = None

    def set(self, provider: str, value: str) -> None:
        if provider == self.fail_on and value.startswith("secret-"):
            raise RuntimeError("injected Keychain failure")
        super().set(provider, value)


def _base_settings() -> ModelSettings:
    return ModelSettings(
        _env_file=None,
        model_default_provider=ModelProvider.OPENAI,
        openai_api_key=None,
        qwen_api_key=None,
        deepseek_api_key=None,
        anthropic_api_key=None,
    )


def _update() -> ModelSettingsUpdate:
    return ModelSettingsUpdate(
        default_provider=ModelProvider.QWEN,
        providers=(
            ProviderSettingsUpdate(
                provider=ModelProvider.OPENAI,
                model="gpt-test",
                api_style=ApiStyle.RESPONSES,
            ),
            ProviderSettingsUpdate(
                provider=ModelProvider.QWEN,
                model="qwen-test",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                api_style=ApiStyle.CHAT_COMPLETIONS,
                api_key="secret-qwen",
            ),
            ProviderSettingsUpdate(
                provider=ModelProvider.DEEPSEEK,
                model="deepseek-test",
                base_url="https://api.deepseek.com",
                api_style=ApiStyle.CHAT_COMPLETIONS,
            ),
            ProviderSettingsUpdate(
                provider=ModelProvider.ANTHROPIC,
                model="claude-test",
                api_style=ApiStyle.ANTHROPIC_MESSAGES,
            ),
        ),
        reflection={
            "enabled": True,
            "inherit_main": False,
            "provider": "qwen",
            "model": "qwen-small",
        },
        maintenance={
            "enabled": False,
            "inherit_main": False,
            "provider": "openai",
            "model": "gpt-small",
        },
        summary={
            "enabled": True,
            "inherit_main": False,
            "provider": "qwen",
            "model": "qwen-summary",
        },
    )


def test_save_keeps_api_key_out_of_json(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    secrets = FakeSecrets()
    service = ModelSettingsService(
        store=ModelSettingsStore(path),
        secrets=secrets,
        base_settings=_base_settings(),
    )

    service.save(_update())

    raw = path.read_text(encoding="utf-8")
    assert "secret-qwen" not in raw
    assert "api_key" not in raw
    assert secrets.values == {"qwen": "secret-qwen"}
    assert json.loads(raw)["default_provider"] == "qwen"


def test_settings_transaction_serializes_other_processes(tmp_path: Path) -> None:
    store = ModelSettingsStore(tmp_path / "models.json")
    script = (
        "import sys\n"
        "from app.model_settings.store import ModelSettingsStore\n"
        "print('ready', flush=True)\n"
        "with ModelSettingsStore(sys.argv[1]).transaction():\n"
        "    print('acquired', flush=True)\n"
    )
    with store.transaction():
        child = subprocess.Popen(
            [sys.executable, "-c", script, str(store.path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert child.stdout is not None
            assert child.stdout.readline().strip() == "ready"
            readable, _, _ = select.select([child.stdout], [], [], 0.2)
            assert readable == []
        except BaseException:
            child.kill()
            child.communicate(timeout=5)
            raise
    output, errors = child.communicate(timeout=5)
    assert child.returncode == 0, errors
    assert output.strip() == "acquired"


def test_keychain_failure_restores_earlier_keys(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    secrets = FailingSecrets(values={"qwen": "old-qwen"}, fail_on="deepseek")
    service = ModelSettingsService(
        store=ModelSettingsStore(path),
        secrets=secrets,
        base_settings=_base_settings(),
    )
    update = _update().model_copy(
        update={
            "providers": tuple(
                item.model_copy(update={"api_key": "secret-deepseek"})
                if item.provider is ModelProvider.DEEPSEEK else item
                for item in _update().providers
            )
        }
    )
    with pytest.raises(RuntimeError, match="injected Keychain failure"):
        service.save(update)
    assert secrets.values == {"qwen": "old-qwen"}
    assert not path.exists()


def test_settings_file_failure_removes_new_key(tmp_path: Path) -> None:
    class FailingStore(ModelSettingsStore):
        def save(self, settings) -> None:
            raise OSError("injected settings write failure")

    secrets = FakeSecrets()
    service = ModelSettingsService(
        store=FailingStore(tmp_path / "models.json"),
        secrets=secrets,
        base_settings=_base_settings(),
    )
    with pytest.raises(OSError, match="injected settings write failure"):
        service.save(_update())
    assert secrets.values == {}


def test_effective_configuration_merges_roles_and_keychain(tmp_path: Path) -> None:
    store = ModelSettingsStore(tmp_path / "models.json")
    secrets = FakeSecrets()
    service = ModelSettingsService(
        store=store,
        secrets=secrets,
        base_settings=_base_settings(),
    )
    service.save(_update())

    effective = load_effective_model_configuration(
        store=store,
        secrets=secrets,
        base_settings=_base_settings(),
    )

    assert effective.settings.model_default_provider is ModelProvider.QWEN
    assert effective.settings.qwen_model == "qwen-test"
    assert effective.settings.qwen_api_key == SecretStr("secret-qwen")
    assert effective.reflection is not None
    assert effective.reflection.provider == "qwen"
    assert effective.reflection.model == "qwen-small"
    assert effective.maintenance is not None
    assert effective.maintenance.enabled is False
    assert effective.summary is not None
    assert effective.summary.enabled is True
    assert effective.summary.provider == "qwen"
    assert effective.summary.model == "qwen-summary"


def test_view_compares_saved_and_current_model_roles(tmp_path: Path) -> None:
    service = ModelSettingsService(
        store=ModelSettingsStore(tmp_path / "models.json"),
        secrets=FakeSecrets(),
        base_settings=_base_settings(),
    )
    service.save(_update())
    active_roles = {
        "main": {"enabled": True, "provider": "qwen", "model": "qwen-test"},
        "summary": {
            "enabled": True,
            "provider": "qwen",
            "model": "qwen-summary",
        },
        "reflection": {
            "enabled": True,
            "provider": "qwen",
            "model": "qwen-small",
        },
        "maintenance": {
            "enabled": False,
            "provider": "openai",
            "model": "gpt-small",
        },
    }

    current = service.view(
        active_provider="qwen",
        active_model="qwen-test",
        active_roles=active_roles,
    )
    changed = service.view(
        active_provider="qwen",
        active_model="qwen-test",
        active_roles={
            **active_roles,
            "summary": {
                "enabled": True,
                "provider": "qwen",
                "model": "other-summary",
            },
        },
    )

    assert current["restart_required"] is False
    assert changed["restart_required"] is True
    assert current["active_roles"] == active_roles


def test_old_settings_without_summary_use_inherited_enabled_default(
    tmp_path: Path,
) -> None:
    path = tmp_path / "models.json"
    ModelSettingsService(
        store=ModelSettingsStore(path),
        secrets=FakeSecrets(),
        base_settings=_base_settings(),
    ).save(_update())
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("summary")
    path.write_text(json.dumps(payload), encoding="utf-8")

    stored = ModelSettingsStore(path).load()

    assert stored is not None
    assert stored.summary.enabled is True
    assert stored.summary.inherit_main is True


@pytest.mark.asyncio
async def test_connection_test_rejects_custom_endpoint_before_reading_key(
    tmp_path: Path,
) -> None:
    secrets = FakeSecrets(values={"openai": "must-not-be-read"})
    service = ModelSettingsService(
        store=ModelSettingsStore(tmp_path / "models.json"),
        secrets=secrets,
        base_settings=_base_settings(),
    )
    provider = ProviderSettingsUpdate(
        provider=ModelProvider.OPENAI,
        model="proxy-model",
        base_url="https://example.invalid/v1",
        api_style=ApiStyle.RESPONSES,
    )

    with pytest.raises(ValueError, match="official HTTPS endpoint"):
        await service.test(provider)

    assert secrets.reads == []


def test_default_provider_without_any_key_is_rejected(tmp_path: Path) -> None:
    update = _update().model_copy(
        update={
            "providers": tuple(
                item.model_copy(update={"api_key": None})
                for item in _update().providers
            )
        }
    )
    service = ModelSettingsService(
        store=ModelSettingsStore(tmp_path / "models.json"),
        secrets=FakeSecrets(),
        base_settings=_base_settings(),
    )

    with pytest.raises(ValueError, match="default provider requires an API key"):
        service.save(update)
