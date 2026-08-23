"""模型设置 RPC：读取、保存与官方端点连接测试。"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.model_settings import ModelSettingsUpdate, ProviderSettingsUpdate
from app.models.errors import ModelAdapterError

from ..dispatcher import RpcContext, RpcDispatcher
from ..protocol import INVALID_STATE, JsonRpcError, RpcErrorCode


def _invalid_params(exc: ValueError) -> JsonRpcError:
    return JsonRpcError(RpcErrorCode.INVALID_PARAMS, str(exc))


def _view(application: Any) -> dict[str, Any]:
    result = application.model_settings_service.view(
        active_provider=application.provider,
        active_model=application.model,
        active_roles=application.active_model_roles,
    )
    active_run_ids = application.run_manager.active_run_ids
    result.update(
        {
            "restart_supported": application.host_restart_callback is not None,
            "restart_blocked_by_run_ids": list(active_run_ids),
            "can_restart": (
                application.host_restart_callback is not None
                and not active_run_ids
            ),
        }
    )
    return result


async def model_settings_get(
    params: dict[str, Any], ctx: RpcContext
) -> dict[str, Any]:
    application = ctx.application
    return _view(application)


async def model_settings_update(
    params: dict[str, Any], ctx: RpcContext
) -> dict[str, Any]:
    try:
        update = ModelSettingsUpdate.model_validate(params)
        ctx.application.model_settings_service.save(update)
    except (ValidationError, ValueError) as exc:
        raise _invalid_params(exc) from exc
    result = _view(ctx.application)
    result["restart_required"] = True
    return result


async def model_settings_test(
    params: dict[str, Any], ctx: RpcContext
) -> dict[str, Any]:
    try:
        provider = ProviderSettingsUpdate.model_validate(params)
        return await ctx.application.model_settings_service.test(provider)
    except (ValidationError, ValueError) as exc:
        raise _invalid_params(exc) from exc
    except ModelAdapterError as exc:
        raise JsonRpcError(INVALID_STATE, f"模型连接失败：{exc}") from exc


def register(dispatcher: RpcDispatcher) -> None:
    dispatcher.register("model_settings.get", model_settings_get)
    dispatcher.register("model_settings.update", model_settings_update)
    dispatcher.register("model_settings.test", model_settings_test)
