"""Post-Run 后台任务管理器（轻量）。

只负责 post-run housekeeping（如 Memory Reflection）的提交与生命周期，
不是通用分布式 job queue。

- ``submit(job)``：创建 ``asyncio.Task`` 并持有引用；
- task 完成后自动移除（done callback）；
- 内部捕获异常并记录，绝不产生 unhandled task exception；
- ``close()``：先停止接收新任务，对 active 任务做有界 drain，超时后 cancel；
- ``active_count`` 供测试 / 诊断。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger("vesta.post_run")

PostRunJob = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class PostRunSubmitResult:
    """一次后台任务提交的结果。

    被拒绝时 ``accepted=False`` 且 ``reason`` 说明原因（``closed`` /
    ``saturated``）。调用方必须检查该结果：静默丢弃 Post-Run 任务会造
    成 Memory Reflection 等收口工作无声丢失。
    """

    accepted: bool
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.accepted


@dataclass(frozen=True, slots=True)
class _PostRunOwner:
    """后台任务的最小归属，用于会话删除时定向取消。"""

    conversation_id: str | None
    run_id: str | None


class PostRunProcessor:
    """管理 post-run 后台协程的生命周期，生命周期归 Application。"""

    def __init__(
        self,
        *,
        drain_timeout: float = 10.0,
        max_concurrency: int = 32,
    ) -> None:
        self._drain_timeout = drain_timeout
        self._max_concurrency = max_concurrency
        self._active: dict[asyncio.Task[None], _PostRunOwner] = {}
        self._closed = False

    @property
    def active_count(self) -> int:
        """当前活跃后台任务数（测试 / 诊断用）。"""
        return len(self._active)

    @property
    def closed(self) -> bool:
        return self._closed

    def submit(
        self,
        job: PostRunJob,
        *,
        conversation_id: str | None = None,
        run_id: str | None = None,
    ) -> PostRunSubmitResult:
        """提交一个后台协程。closed 或饱和时拒绝并返回原因（不静默丢弃）。"""
        if self._closed:
            logger.warning("post-run processor closed; dropping background job")
            return PostRunSubmitResult(accepted=False, reason="closed")
        if len(self._active) >= self._max_concurrency:
            logger.warning("post-run processor saturated; dropping background job")
            return PostRunSubmitResult(accepted=False, reason="saturated")
        task = asyncio.get_running_loop().create_task(self._run_job(job))
        self._active[task] = _PostRunOwner(
            conversation_id=conversation_id,
            run_id=run_id,
        )
        # 安全 pop：close()/clear() 可能已移除映射，缺失时不能抛 KeyError。
        task.add_done_callback(lambda done: self._active.pop(done, None))
        return PostRunSubmitResult(accepted=True)

    async def cancel_for_conversation(self, conversation_id: str) -> int:
        """取消会话仍在运行的 Post-Run 任务，防止删除后迟到写入。"""

        targets = [
            task
            for task, owner in self._active.items()
            if owner.conversation_id == conversation_id
        ]
        for task in targets:
            task.cancel()
        if targets:
            await asyncio.gather(*targets, return_exceptions=True)
        return len(targets)

    async def _run_job(self, job: PostRunJob) -> None:
        try:
            await job()
        except asyncio.CancelledError:
            raise
        except Exception:
            # 后台任务失败只进日志 / post-run 事件，绝不让 task exception 泄漏。
            logger.exception("post-run background job failed")

    async def close(self) -> None:
        """停止接收新任务；有界等待 active 任务，超时后 cancel 并等待结束。

        保证不会无限等待卡住的模型请求，也不会在 event loop 关闭时遗留
        pending task。
        """
        self._closed = True
        if not self._active:
            return
        tasks = list(self._active)
        _, pending = await asyncio.wait(tasks, timeout=self._drain_timeout)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for task in tasks:
            if task.done() and not task.cancelled() and task.exception() is not None:
                logger.error(
                    "post-run job raised unexpectedly",
                    exc_info=task.exception(),
                )
        self._active.clear()


__all__ = ["PostRunProcessor", "PostRunSubmitResult"]
