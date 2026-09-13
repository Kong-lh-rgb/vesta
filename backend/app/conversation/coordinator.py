"""会话级并发协调：让执行、恢复与删除遵守同一把锁。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager


class ConversationOperationCoordinator:
    """串行化同一会话的执行，并在删除期间拒绝新的工作。"""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._deleting: set[str] = set()

    def _lock_for(self, conversation_id: str) -> asyncio.Lock:
        lock = self._locks.get(conversation_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[conversation_id] = lock
        return lock

    @asynccontextmanager
    async def execution(
        self,
        conversation_id: str | None,
    ) -> AsyncIterator[None]:
        """进入会话执行临界区；删除开始后不再接受新执行。"""

        if conversation_id is None:
            yield
            return
        if conversation_id in self._deleting:
            raise KeyError(f"会话正在删除：{conversation_id}")
        async with self._lock_for(conversation_id):
            # 等锁期间删除可能已经开始，因此进入临界区后再次检查。
            if conversation_id in self._deleting:
                raise KeyError(f"会话正在删除：{conversation_id}")
            yield

    @asynccontextmanager
    async def deletion(
        self,
        conversation_id: str,
        *,
        stop_active_work: Callable[[], Awaitable[None]],
    ) -> AsyncIterator[None]:
        """阻止新执行，停止当前工作，再独占会话完成删除。"""

        if conversation_id in self._deleting:
            raise RuntimeError(f"会话删除已在进行：{conversation_id}")
        self._deleting.add(conversation_id)
        try:
            # 当前 dispatch 可能正持有会话锁。先取消其 Run，让它完成取消写回，
            # 再等待同一把锁，避免删除后又被迟到的 dispatch 重新写入。
            await stop_active_work()
            async with self._lock_for(conversation_id):
                yield
        finally:
            self._deleting.discard(conversation_id)
            lock = self._locks.get(conversation_id)
            if lock is not None and not lock.locked():
                self._locks.pop(conversation_id, None)


__all__ = ["ConversationOperationCoordinator"]
