"""进程内 owner + flock 跨 Host 互斥的 Computer Machine Lease。"""

from __future__ import annotations

import fcntl
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

from app.tools.hooks import ToolExecutionContext, ToolHook, ToolHookDecision

if TYPE_CHECKING:
    from .session import ComputerSessionManager

logger = logging.getLogger("vesta.computer.lease")


class ComputerBusyError(RuntimeError):
    """电脑已被其它 Run 或 Host 占用。"""


@dataclass(frozen=True, slots=True)
class ComputerLeaseSnapshot:
    owner_run_id: str | None
    acquired_at: datetime | None
    process_id: int


class ComputerLeaseManager:
    """以 run_id 为 owner 的机器租约；仅回收已过期且不活跃的 owner。"""

    def __init__(
        self,
        lock_path: str | Path,
        *,
        ttl_seconds: float = 300.0,
        owner_active: Callable[[str], bool] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("computer lease TTL must be positive")
        self.lock_path = Path(lock_path).expanduser().resolve()
        self.ttl_seconds = ttl_seconds
        self._owner_active = owner_active
        self._guard = Lock()
        self._owner_run_id: str | None = None
        self._acquired_at: datetime | None = None
        self._lock_file = None
        self._last_touch: float | None = None
        self._quarantined = False

    def set_owner_active(self, predicate: Callable[[str], bool]) -> None:
        with self._guard:
            self._owner_active = predicate

    @property
    def snapshot(self) -> ComputerLeaseSnapshot:
        with self._guard:
            return ComputerLeaseSnapshot(
                owner_run_id=self._owner_run_id,
                acquired_at=self._acquired_at,
                process_id=os.getpid(),
            )

    def acquire(self, run_id: str) -> ComputerLeaseSnapshot:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("computer action requires run context")
        with self._guard:
            if self._quarantined:
                raise ComputerBusyError(
                    "computer helper cleanup was not confirmed; restart Host"
                )
            if self._owner_run_id == run_id:
                self._last_touch = time.monotonic()
                return self.snapshot_unlocked()
            if self._owner_run_id is not None:
                stale = (
                    self._last_touch is not None
                    and time.monotonic() - self._last_touch >= self.ttl_seconds
                    and self._owner_active is not None
                    and not self._owner_active(self._owner_run_id)
                )
                if stale:
                    logger.warning("releasing expired inactive computer lease")
                    self._release_unlocked()
                else:
                    logger.info("computer lease busy for run %s", run_id)
                    raise ComputerBusyError(
                        "computer is currently controlled by another run"
                    )

            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_file = self.lock_path.open("a+", encoding="utf-8")
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                lock_file.close()
                logger.info("computer lease busy in another host")
                raise ComputerBusyError(
                    "computer is currently controlled by another run"
                ) from exc

            acquired_at = datetime.now(UTC)
            lock_file.seek(0)
            lock_file.truncate()
            lock_file.write(
                f"pid={os.getpid()}\nrun_id={run_id}\n"
                f"acquired_at={acquired_at.isoformat()}\n"
            )
            lock_file.flush()
            self._lock_file = lock_file
            self._owner_run_id = run_id
            self._acquired_at = acquired_at
            self._last_touch = time.monotonic()
            logger.info("computer lease acquired by run %s", run_id)
            return self.snapshot_unlocked()

    def snapshot_unlocked(self) -> ComputerLeaseSnapshot:
        return ComputerLeaseSnapshot(
            owner_run_id=self._owner_run_id,
            acquired_at=self._acquired_at,
            process_id=os.getpid(),
        )

    def release(self, run_id: str) -> bool:
        with self._guard:
            if self._owner_run_id != run_id:
                return False
            self._release_unlocked()
            logger.info("computer lease released by run %s", run_id)
            return True

    def quarantine(self) -> None:
        """Refuse new owners after an unconfirmed native cleanup."""

        with self._guard:
            self._quarantined = True

    def close(self) -> None:
        with self._guard:
            self._release_unlocked()

    def _release_unlocked(self) -> None:
        lock_file = self._lock_file
        self._lock_file = None
        self._owner_run_id = None
        self._acquired_at = None
        self._last_touch = None
        if lock_file is not None:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            finally:
                lock_file.close()


class ComputerLeaseHook(ToolHook):
    """只拦截 computer_*，生产链缺 run_id 时 fail closed。

    acquire 成功后同时建立 Run-scoped ComputerSession（V2）：
    Lease 保证单 Run 控制 Computer，Session 负责把 target / snapshot 状态
    归属到该 Run，并在 Run 结束时清除。

    ``session_starter``：由 composition root 注入的异步 callable
    （MacOSComputerRuntime.begin_session_rpc），负责通知 Native helper 显式
    ``begin_session``。缺省时回退到 Python 侧同步 begin。
    """

    critical = True

    def __init__(
        self,
        manager: ComputerLeaseManager,
        session_manager: ComputerSessionManager | None = None,
        session_starter: Callable[[str], Awaitable[object] | object] | None = None,
    ) -> None:
        self.manager = manager
        self.session_manager = session_manager
        self.session_starter = session_starter

    async def before_execute(
        self, context: ToolExecutionContext
    ) -> ToolHookDecision | None:
        if not context.tool_call.name.startswith("computer_"):
            return None
        if not context.run_id:
            return ToolHookDecision(
                denied_reason="computer action requires run context"
            )
        try:
            self.manager.acquire(context.run_id)
        except ComputerBusyError as exc:
            return ToolHookDecision(denied_reason=str(exc))
        if self.session_starter is not None:
            await self.session_starter(context.run_id)
        elif self.session_manager is not None:
            self.session_manager.begin(context.run_id)
        return None


__all__ = [
    "ComputerBusyError",
    "ComputerLeaseHook",
    "ComputerLeaseManager",
    "ComputerLeaseSnapshot",
]
