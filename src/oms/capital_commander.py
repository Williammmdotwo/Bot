"""
资金指挥官 (Capital Commander)

全局资金的大管家，负责资金分配和风险控制。

核心职责：
- 管理总资金池
- 分配策略资金
- 追踪策略盈亏
- 实时更新资金状态

设计原则：
- 集中管理，避免资金冲突
- 监听订单成交事件，自动更新
- 提供资金检查接口
"""

import logging
from typing import Dict, Optional
from dataclasses import dataclass
from ..core.event_types import Event, EventType

logger = logging.getLogger(__name__)


@dataclass
class StrategyCapital:
    """策略资金信息"""
    allocated: float  # 分配资金
    used: float       # 已使用资金
    profit: float     # 累计盈亏
    available: float  # 可用资金 (allocated - used + profit)


class CapitalCommander:
    """
    资金指挥官

    全局资金管理器，负责分配和追踪各策略的资金使用情况。

    Example:
        >>> commander = CapitalCommander(total_capital=10000.0)
        >>>
        >>> # 分配资金给策略
        >>> commander.allocate_strategy("vulture", 2000.0)
        >>>
        >>> # 检查购买力
        >>> has_power = commander.check_buying_power("vulture", 1000.0)
        >>> print(has_power)
        True
        >>>
        >>> # 记录盈亏
        >>> commander.record_profit("vulture", 150.0)
    """

    def __init__(
        self,
        total_capital: float = 10000.0,
        event_bus=None
    ):
        """
        初始化资金指挥官

        Args:
            total_capital (float): 总资金（USDT）
            event_bus: 事件总线实例
        """
        self.total_capital = total_capital
        self._event_bus = event_bus

        # 策略资金池 {strategy_id: StrategyCapital}
        self._strategies: Dict[str, StrategyCapital] = {}

        # 全局未分配资金
        self._unallocated = total_capital

        logger.info(
            f"CapitalCommander 初始化: total_capital={total_capital:.2f} USDT"
        )

    def allocate_strategy(
        self,
        strategy_id: str,
        amount: float
    ) -> bool:
        """
        为策略分配资金

        Args:
            strategy_id (str): 策略 ID
            amount (float): 分配金额（USDT）

        Returns:
            bool: 分配是否成功
        """
        if amount <= 0:
            logger.error(f"分配金额必须大于 0: {amount}")
            return False

        if amount > self._unallocated:
            logger.error(
                f"未分配资金不足: 需要 {amount:.2f}, 可用 {self._unallocated:.2f}"
            )
            return False

        # 检查是否已分配
        if strategy_id in self._strategies:
            logger.warning(f"策略 {strategy_id} 已存在，追加资金")
            self._strategies[strategy_id].allocated += amount
        else:
            self._strategies[strategy_id] = StrategyCapital(
                allocated=amount,
                used=0.0,
                profit=0.0,
                available=amount
            )

        self._unallocated -= amount

        logger.info(
            f"为策略 {strategy_id} 分配资金: {amount:.2f} USDT, "
            f"剩余未分配: {self._unallocated:.2f} USDT"
        )

        return True

    def check_buying_power(
        self,
        strategy_id: str,
        amount_usdt: float
    ) -> bool:
        """
        检查策略是否有足够的购买力

        Args:
            strategy_id (str): 策略 ID
            amount_usdt (float): 需要的金额（USDT）

        Returns:
            bool: 是否有足够的购买力
        """
        if strategy_id not in self._strategies:
            logger.error(f"策略 {strategy_id} 未分配资金")
            return False

        capital = self._strategies[strategy_id]

        # 检查可用资金
        has_power = capital.available >= amount_usdt

        if not has_power:
            logger.warning(
                f"策略 {strategy_id} 购买力不足: "
                f"需要 {amount_usdt:.2f} USDT, 可用 {capital.available:.2f} USDT"
            )

        return has_power

    def reserve_capital(
        self,
        strategy_id: str,
        amount_usdt: float
    ) -> bool:
        """
        预留资金（下单前调用）

        Args:
            strategy_id (str): 策略 ID
            amount_usdt (float): 预留金额（USDT）

        Returns:
            bool: 预留是否成功
        """
        if not self.check_buying_power(strategy_id, amount_usdt):
            return False

        capital = self._strategies[strategy_id]
        capital.used += amount_usdt
        capital.available = capital.allocated - capital.used + capital.profit

        logger.info(
            f"策略 {strategy_id} 预留资金: {amount_usdt:.2f} USDT, "
            f"剩余可用: {capital.available:.2f} USDT"
        )

        return True

    def release_capital(
        self,
        strategy_id: str,
        amount_usdt: float
    ):
        """
        释放资金（订单取消或失败后调用）

        Args:
            strategy_id (str): 策略 ID
            amount_usdt (float): 释放金额（USDT）
        """
        if strategy_id not in self._strategies:
            logger.error(f"策略 {strategy_id} 未分配资金")
            return

        capital = self._strategies[strategy_id]
        capital.used -= amount_usdt
        capital.available = capital.allocated - capital.used + capital.profit

        logger.info(
            f"策略 {strategy_id} 释放资金: {amount_usdt:.2f} USDT, "
            f"剩余可用: {capital.available:.2f} USDT"
        )

    def record_profit(
        self,
        strategy_id: str,
        profit_usdt: float
    ):
        """
        记录策略盈亏

        Args:
            strategy_id (str): 策略 ID
            profit_usdt (float): 盈亏金额（正为盈，负为亏）
        """
        if strategy_id not in self._strategies:
            logger.error(f"策略 {strategy_id} 未分配资金")
            return

        capital = self._strategies[strategy_id]
        capital.profit += profit_usdt
        capital.available = capital.allocated - capital.used + capital.profit

        logger.info(
            f"策略 {strategy_id} 记录盈亏: {profit_usdt:+.2f} USDT, "
            f"累计盈亏: {capital.profit:+.2f} USDT, "
            f"可用资金: {capital.available:.2f} USDT"
        )

    def get_strategy_capital(
        self,
        strategy_id: str
    ) -> Optional[StrategyCapital]:
        """
        获取策略资金信息

        Args:
            strategy_id (str): 策略 ID

        Returns:
            StrategyCapital: 资金信息，如果策略不存在返回 None
        """
        return self._strategies.get(strategy_id)

    def get_all_capitals(self) -> Dict[str, StrategyCapital]:
        """
        获取所有策略的资金信息

        Returns:
            dict: {strategy_id: StrategyCapital}
        """
        return self._strategies.copy()

    def get_summary(self) -> dict:
        """
        获取资金汇总信息

        Returns:
            dict: 汇总信息
        """
        total_allocated = sum(c.allocated for c in self._strategies.values())
        total_used = sum(c.used for c in self._strategies.values())
        total_profit = sum(c.profit for c in self._strategies.values())
        total_available = sum(c.available for c in self._strategies.values())

        return {
            'total_capital': self.total_capital,
            'unallocated': self._unallocated,
            'total_allocated': total_allocated,
            'total_used': total_used,
            'total_profit': total_profit,
            'total_available': total_available,
            'strategy_count': len(self._strategies)
        }

    def on_order_filled(self, event: Event):
        """
        监听订单成交事件，自动更新资金

        Args:
            event (Event): ORDER_FILLED 事件
        """
        try:
            data = event.data
            strategy_id = data.get('strategy_id', 'default')

            # 计算成交金额
            price = data.get('price', 0)
            filled_size = data.get('filled_size', 0)
            side = data.get('side')

            if price <= 0 or filled_size <= 0:
                return

            amount_usdt = price * filled_size

            # 买入：释放预留资金
            if side == 'buy':
                self.release_capital(strategy_id, amount_usdt)

            # 卖出：记录盈亏（简化处理）
            elif side == 'sell':
                # 实际盈亏需要根据开仓价计算，这里简化处理
                # 可以在 PositionManager 中计算，然后调用 record_profit
                pass

        except Exception as e:
            logger.error(f"处理订单成交事件失败: {e}")

    def reset(self):
        """重置所有资金状态"""
        self._strategies.clear()
        self._unallocated = self.total_capital
        logger.info("资金指挥官已重置")
