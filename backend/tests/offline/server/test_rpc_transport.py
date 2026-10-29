"""传输层健壮性：广播背压隔离与发送序列化兜底。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from app.server.rpc.hub import RpcHub


class FakeRpcConnection:
    """最小连接桩：可编程的 send_notification 行为。"""

    def __init__(
        self,
        *,
        delay: float = 0.0,
        fail: bool = False,
    ) -> None:
        self.delay = delay
        self.fail = fail
        self.notifications: list[tuple[str, Any]] = []
        self.closed = False

    async def send_notification(self, method: str, params: Any) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("connection broken")
        self.notifications.append((method, params))

    def mark_closed(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_broadcast_does_not_wait_for_slow_connection() -> None:
    """慢客户端不能拖停广播：超时连接被标记关闭，其余连接正常收到。"""

    hub = RpcHub(broadcast_timeout_seconds=0.05)
    slow = FakeRpcConnection(delay=5.0)
    healthy = FakeRpcConnection()
    await hub.register(slow)
    await hub.register(healthy)

    await asyncio.wait_for(
        hub.broadcast("run.status", {"run_id": "r1", "status": "running"}),
        timeout=1.0,
    )

    assert healthy.notifications == [
        ("run.status", {"run_id": "r1", "status": "running"})
    ]
    assert slow.closed is True


@pytest.mark.asyncio
async def test_broadcast_survives_failing_connection() -> None:
    """失败连接不影响其余连接的广播。"""

    hub = RpcHub(broadcast_timeout_seconds=0.05)
    broken = FakeRpcConnection(fail=True)
    healthy = FakeRpcConnection()
    await hub.register(broken)
    await hub.register(healthy)

    await hub.broadcast("agent.event", {"sequence": 1})

    assert healthy.notifications == [("agent.event", {"sequence": 1})]
    assert broken.closed is True


@pytest.mark.asyncio
async def test_broadcast_without_connections_returns() -> None:
    hub = RpcHub()
    await hub.broadcast("agent.event", {})


# ---------------------------------------------------------------------------
# 发送序列化兜底：不可 JSON 化的载荷不再让请求悬挂
# ---------------------------------------------------------------------------


class RecordingWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(text)


@pytest.mark.asyncio
async def test_send_serializes_non_jsonable_payloads_with_default() -> None:
    """载荷含 datetime 等不可 JSON 化值时 default=str 兜底，不抛异常。"""

    from app.server.rpc.connection import RpcConnection

    websocket = RecordingWebSocket()
    connection = RpcConnection(websocket, None, None, RpcHub())  # type: ignore[arg-type]

    await connection.send_response(
        1,
        {"at": datetime(2026, 1, 1, tzinfo=UTC), "path": None},
    )

    assert len(websocket.sent) == 1
    assert '"at": "2026-01-01 00:00:00+00:00"' in websocket.sent[0]
