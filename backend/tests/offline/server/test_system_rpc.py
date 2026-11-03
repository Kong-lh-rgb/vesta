"""Host 系统控制 RPC 的离线测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.server.rpc.methods import system
from app.server.rpc.protocol import INVALID_STATE, JsonRpcError


class ImmediateLoop:
    def call_later(self, delay: float, callback) -> None:  # noqa: ANN001
        assert delay > 0
        callback()


class FakeRunManager:
    def __init__(self, active_run_ids: tuple[str, ...] = ()) -> None:
        self.active_run_ids = active_run_ids
        self.reserved = False

    async def stop_accepting_if_idle(self) -> tuple[str, ...]:
        self.reserved = not self.active_run_ids
        return self.active_run_ids


@pytest.mark.asyncio
async def test_restart_is_accepted_without_active_runs(monkeypatch) -> None:  # noqa: ANN001
    called: list[bool] = []
    run_manager = FakeRunManager()
    application = SimpleNamespace(
        run_manager=run_manager,
        host_restart_callback=lambda: called.append(True),
    )
    monkeypatch.setattr(system.asyncio, "get_running_loop", ImmediateLoop)

    result = await system.system_restart(
        {},
        SimpleNamespace(application=application),
    )

    assert result == {"accepted": True}
    assert called == [True]
    assert run_manager.reserved


@pytest.mark.asyncio
async def test_restart_rejects_active_runs() -> None:
    application = SimpleNamespace(
        run_manager=FakeRunManager(("run-1",)),
        host_restart_callback=lambda: None,
    )

    with pytest.raises(JsonRpcError) as caught:
        await system.system_restart(
            {},
            SimpleNamespace(application=application),
        )

    assert caught.value.code == INVALID_STATE
    assert caught.value.data == {"active_run_ids": ["run-1"]}


@pytest.mark.asyncio
async def test_restart_rejects_unsupported_entrypoint() -> None:
    application = SimpleNamespace(
        run_manager=FakeRunManager(),
        host_restart_callback=None,
    )

    with pytest.raises(JsonRpcError) as caught:
        await system.system_restart(
            {},
            SimpleNamespace(application=application),
        )

    assert caught.value.code == INVALID_STATE
