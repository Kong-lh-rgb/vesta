"""工具在不同 Agent 模式下的能力边界。"""

from __future__ import annotations

from collections.abc import Collection

from app.models.types import AgentMode

PLAN_MODE_ALLOWED_TOOLS = frozenset(
    {
        "read_file",
        "list_files",
        "web_search",
        "get_current_time",
        # 兼容离线测试或第三方注册的旧工具名。
        "current_time",
        "memory_read",
        "memory_search",
        "history_search",
        "history_read",
        "evidence_search",
        "evidence_read",
        "task_create",
        "task_update",
        "task_get",
        "task_list",
    }
)


class ToolAvailabilityPolicy:
    """集中决定模式白名单与延迟工具可见性。"""

    def __init__(
        self,
        *,
        plan_allowed_tools: Collection[str] = PLAN_MODE_ALLOWED_TOOLS,
    ) -> None:
        self._plan_allowed_tools = frozenset(plan_allowed_tools)

    def allowed_names(
        self,
        mode: AgentMode,
        *,
        registered_names: Collection[str],
    ) -> frozenset[str]:
        if mode is AgentMode.PLAN:
            return self._plan_allowed_tools
        return frozenset(registered_names)

    def is_available(
        self,
        name: str,
        mode: AgentMode,
        *,
        deferred_names: Collection[str],
        activated_names: Collection[str],
    ) -> bool:
        """判断延迟工具是否已对当前模式开放。"""

        if name not in deferred_names or name in activated_names:
            return True
        # Plan 白名单已经是只读硬边界，其中的延迟检索工具可直接使用。
        return mode is AgentMode.PLAN and name in self._plan_allowed_tools


__all__ = ["PLAN_MODE_ALLOWED_TOOLS", "ToolAvailabilityPolicy"]
