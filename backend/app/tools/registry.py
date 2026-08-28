"""本地工具注册表。"""

from __future__ import annotations

import re
from collections.abc import Collection

from app.models.types import AgentMode, ToolDefinition

from .availability import ToolAvailabilityPolicy
from .base import BaseTool

_VALID_NAME = re.compile(r"^[a-zA-Z0-9_]+$")

class ToolRegistry:
    def __init__(
        self,
        *,
        availability_policy: ToolAvailabilityPolicy | None = None,
    ) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._deferred_names: set[str] = set()
        self._availability_policy = (
            availability_policy or ToolAvailabilityPolicy()
        )

    def register(self, tool: BaseTool, *, deferred: bool = False) -> None:
        """注册工具；延迟工具只在当前 Run 被激活后暴露完整定义。"""

        name = tool.definition.name
        if not name:
            raise ValueError("Tool name cannot be empty.")
        if not _VALID_NAME.fullmatch(name):
            raise ValueError(
                "Tool name must use dot-separated letters, digits, or underscores: "
                f"{name!r}"
            )
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered.")
        self._tools[name] = tool
        if deferred:
            self._deferred_names.add(name)

    def unregister(self, name: str) -> BaseTool:
        """注销工具并返回被移除的工具；不存在时抛 KeyError。"""
        try:
            tool = self._tools.pop(name)
        except KeyError:
            raise KeyError(f"Tool '{name}' is not registered.") from None
        self._deferred_names.discard(name)
        return tool

    def get(self, name: str) -> BaseTool:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"Tool '{name}' is not registered.") from None

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def deferred_names(self) -> tuple[str, ...]:
        """返回按名称稳定排序的延迟加载工具名。"""

        return tuple(sorted(self._deferred_names))

    def is_deferred(self, name: str) -> bool:
        return name in self._deferred_names

    def is_available_for_mode(
        self,
        name: str,
        mode: AgentMode,
        *,
        activated_names: Collection[str] = (),
    ) -> bool:
        """工具是否已对当前模式开放。

        Plan 白名单本身就是严格的只读能力边界，因此其中的延迟检索工具可以
        直接使用；Normal 仍必须先通过 tool_search 激活，避免常驻 Schema。
        """

        return self._availability_policy.is_available(
            name,
            mode,
            deferred_names=self._deferred_names,
            activated_names=activated_names,
        )

    def model_definitions(
        self,
        *,
        activated_names: Collection[str] = (),
    ) -> tuple[ToolDefinition, ...]:
        """返回当前 Run 可见定义：常驻工具加已激活的延迟工具。"""

        activated = set(activated_names)
        return tuple(
            self._tools[name].definition
            for name in sorted(self._tools)
            if self._tools[name].definition.permission.model_visible()
            and (name not in self._deferred_names or name in activated)
        )

    def allowed_names_for_mode(self, mode: AgentMode) -> frozenset[str]:
        """返回该模式下允许执行的工具名集合。

        - NORMAL：注册表中的全部工具；
        - PLAN：只读 / 搜索 / 规划工具白名单。
        """

        return self._availability_policy.allowed_names(
            mode,
            registered_names=self._tools,
        )

    def is_allowed_for_mode(self, name: str, mode: AgentMode) -> bool:
        """工具是否允许在该模式执行（执行层的硬性能力过滤）。"""

        return name in self.allowed_names_for_mode(mode)

    def is_allowed_during_closing(self, name: str, mode: AgentMode) -> bool:
        """工具是否可在预算 Closing 阶段执行。"""

        if not self.is_allowed_for_mode(name, mode):
            return False
        tool = self._tools.get(name)
        return tool is not None and tool.definition.closing_allowed

    def model_definitions_for_mode(
        self,
        mode: AgentMode,
        *,
        activated_names: Collection[str] = (),
    ) -> tuple[ToolDefinition, ...]:
        """返回该模式可见的工具定义（PLAN 模式隐藏副作用工具）。"""

        allowed = self.allowed_names_for_mode(mode)
        activated = set(activated_names)
        return tuple(
            self._tools[name].definition
            for name in sorted(self._tools)
            if name in allowed
            and self._tools[name].definition.permission.model_visible()
            and self.is_available_for_mode(
                name,
                mode,
                activated_names=activated,
            )
        )

    def closing_definitions_for_mode(
        self,
        mode: AgentMode,
        *,
        activated_names: Collection[str] = (),
    ) -> tuple[ToolDefinition, ...]:
        """返回预算 Closing 阶段可见的交付工具定义。"""

        return tuple(
            definition
            for definition in self.model_definitions_for_mode(
                mode,
                activated_names=activated_names,
            )
            if definition.closing_allowed
        )

    def definitions(
        self,
        *,
        for_model: bool = True,
    ) -> tuple[ToolDefinition, ...]:
        """返回工具定义。

        ``for_model=True`` 时排除 FORBIDDEN 档位的工具（严格禁止模型执行）。
        """
        if not for_model:
            return tuple(tool.definition for tool in self._tools.values())
        return tuple(
            tool.definition
            for tool in self._tools.values()
            if tool.definition.permission.model_visible()
        )
