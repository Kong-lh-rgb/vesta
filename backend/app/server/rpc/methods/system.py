"""system RPC methods。"""

from __future__ import annotations

import asyncio
from typing import Any

from app.server.version import __version__

from ..dispatcher import RpcContext, RpcDispatcher
from ..protocol import INVALID_STATE, JsonRpcError


async def system_info(params: dict[str, Any], ctx: RpcContext) -> dict[str, Any]:
    """Host 基础信息（Settings / 开发环境判断用）。"""

    application = ctx.application
    return {
        "status": "ok",
        "provider": application.provider,
        "model": application.model,
        "version": __version__,
        "database": str(application.database),
    }


async def system_restart(
    params: dict[str, Any], ctx: RpcContext
) -> dict[str, Any]:
    """在无活跃Run时请求入口监督循环优雅重启Host。"""

    application = ctx.application
    active_run_ids = application.run_manager.active_run_ids
    if active_run_ids:
        raise JsonRpcError(
            INVALID_STATE,
            "存在正在执行的 Run，暂时不能重启 Host",
            {"active_run_ids": list(active_run_ids)},
        )
    callback = application.host_restart_callback
    if callback is None:
        raise JsonRpcError(
            INVALID_STATE,
            "当前 Host 启动方式不支持应用内重启",
        )
    asyncio.get_running_loop().call_later(0.25, callback)
    return {"accepted": True}


def register(dispatcher: RpcDispatcher) -> None:
    dispatcher.register("system.info", system_info)
    dispatcher.register("system.restart", system_restart)
