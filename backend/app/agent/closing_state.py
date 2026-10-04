"""Run Budget Closing 阶段的状态机（P2-15：从 Agent Loop 拆出）。

语义（与拆分前逐一对映，事件顺序不变）：
- Closing 最多保留**一次**交付工具轮（``mark_delivery_used``）；
- 交付轮之后的下一请求只负责汇报结果（``mark_reporting_used``）；
- 汇报轮之后再被要求 finalize 即视为硬超限（``reporting_exhausted``）；
- ``enter`` 只在首次进入 Closing 时返回 True（驱动 FINALIZING 事件）。

Loop 只按状态机查询/迁移，不直接维护布尔标志群。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BudgetClosingState:
    """一次 Run 的 Closing 阶段状态。"""

    started: bool = False
    delivery_used: bool = False
    reporting_used: bool = False

    def enter(self) -> bool:
        """首次进入 Closing 返回 True（调用方据此发 FINALIZING 事件）。"""

        if self.started:
            return False
        self.started = True
        return True

    def can_deliver(self, *, forces_final: bool, forced_without_budget: bool) -> bool:
        """当前请求是否可作为 Closing 的交付轮。"""

        return (
            forces_final
            and not self.delivery_used
            and not forced_without_budget
        )

    def mark_delivery_used(self) -> None:
        self.delivery_used = True

    def begin_reporting(self) -> bool:
        """交付轮已用后再次 finalize：进入唯一一次汇报轮。

        返回 True 表示本次是汇报轮；False 表示汇报轮也已用完（硬超限）。
        """

        if self.reporting_used:
            return False
        self.reporting_used = True
        return True

    @property
    def reporting_exhausted(self) -> bool:
        """交付与汇报轮都已用完：再要求 finalize 即硬超限。"""

        return self.delivery_used and self.reporting_used


__all__ = ["BudgetClosingState"]
