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


@pytest.mark.asyncio
async def test_restart_is_accepted_without_active_runs(monkeypatch) -> None:  # noqa: ANN001
    called: list[bool] = []
    application = SimpleNamespace(
        run_manager=SimpleNamespace(active_run_ids=()),
        host_restart_callback=lambda: called.append(True),
    )
    monkeypatch.setattr(system.asyncio, "get_running_loop", ImmediateLoop)

    result = await system.system_restart(
        {},
        SimpleNamespace(application=application),
    )

    assert result == {"accepted": True}
    assert called == [True]


@pytest.mark.asyncio
async def test_restart_rejects_active_runs() -> None:
    application = SimpleNamespace(
        run_manager=SimpleNamespace(active_run_ids=("run-1",)),
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
        run_manager=SimpleNamespace(active_run_ids=()),
        host_restart_callback=None,
    )

    with pytest.raises(JsonRpcError) as caught:
        await system.system_restart(
            {},
            SimpleNamespace(application=application),
        )

    assert caught.value.code == INVALID_STATE
