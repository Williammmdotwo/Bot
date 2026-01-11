"""
策略基类 (Base Strategy)

定义所有策略的通用接口和基础功能。

设计原则：
- 策略只负责交易逻辑，不关心数据源
- 通过事件总线接收市场数据
- 纯粹的策略实现，不包含网络通信
- 强制止损机制（机构级风控）
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass

from ..core.event_bus import EventBus
from ..core.event_types import Event, EventType
from ..oms.order_manager import OrderManager
from ..oms.capital_commander import CapitalCommander
from ..config.risk_config import DEFAULT_RISK_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class OrderRequest:
    """订单请求"""
    symbol: str
    side: str           # "buy" or "sell"
    order_type: str      # "market", "limit", "ioc"
    size: float
    price: Optional[float] = None
    strategy_id: str = "default"


class BaseStrategy(ABC):
    """
    策略基类

    所有策略都必须继承此类并实现抽象方法。

    Attributes:
        strategy_id (str): 策略 ID
        symbol (str): 交易对
        mode (str): 策略模式（PRODUCTION/DEV）
        event_bus (EventBus): 事件总线
        order_manager (OrderManager): 订单管理器
        capital_commander (CapitalCommander): 资金指挥官

    Example:
        >>> class MyStrategy(BaseStrategy):
        ...     async def on_tick(self, event: Event):
        ...         data = event.data
        ...         if data['price'] > 100:
        ...             await self.buy('BTC-USDT-SWAP', 0.1)
    """

    def __init__(
        self,
        event_bus: EventBus,
        order_manager: Optional[OrderManager] = None,
        capital_commander: Optional[CapitalCommander] = None,
        symbol: str = "BTC-USDT-SWAP",
        mode: str = "PRODUCTION",
        strategy_id: Optional[str] = None
    ):
        """
        初始化策略

        Args:
            event_bus (EventBus): 事件总线实例
            order_manager (OrderManager): 订单管理器
            capital_commander (CapitalCommander): 资金指挥官
            symbol (str): 交易对
            mode (str): 策略模式（PRODUCTION/DEV）
            strategy_id (str): 策略 ID（可选，默认为类名小写）
        """
        # 使用显式传入的 strategy_id，如果没有则使用类名小写
        self.strategy_id = (
            strategy_id if strategy_id else self.__class__.__name__.lower()
        )
        self.symbol = symbol
        self.mode = mode.upper()
        self._enabled = True

        # 依赖注入
        self._event_bus = event_bus
        self._order_manager = order_manager
        self._capital_commander = capital_commander

        # 策略统计
        self._ticks_received = 0
        self._signals_generated = 0
        self._orders_submitted = 0
        self._last_trade_time = 0.0

        logger.info(
            f"策略初始化: {self.strategy_id}, symbol={symbol}, mode={mode}"
        )

    @abstractmethod
    async def on_tick(self, event: Event):
        """
        处理 Tick 事件

        这是策略的核心方法，每个 TICK 事件都会调用。

        Args:
            event (Event): TICK 事件对象
                data: {
                    'symbol': str,
                    'price': float,
                    'size': float,
                    'side': str,
                    'usdt_value': float,
                    'timestamp': int
                }
        """
        pass

    @abstractmethod
    async def on_signal(self, signal: Dict[str, Any]):
        """
        处理策略信号

        Args:
            signal (dict): 策略信号，包含信号类型、数量等
                {
                    'type': 'BUY' | 'SELL',
                    'symbol': str,
                    'size': float,
                    'price': float | None
                }
        """
        pass

    async def buy(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        order_type: str = "market",
        size: Optional[float] = None
    ) -> bool:
        """
        买入（便捷方法，强制要求止损价）

        新的买入方法强制要求止损价，用于机构级风控。
        如果没有明确止损价，策略应使用波动率计算默认止损。

        Args:
            symbol (str): 交易对
            entry_price (float): 入场价格（必需）
            stop_loss_price (float): 止损价格（必需）
            order_type (str): 订单类型（market/limit/ioc）
            size (float): 数量（可选，如果不提供则基于风险计算）

        Returns:
            bool: 下单是否成功
        """
        return await self._submit_order(
            symbol=symbol,
            side="buy",
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            order_type=order_type,
            size=size
        )

    async def sell(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        order_type: str = "market",
        size: Optional[float] = None
    ) -> bool:
        """
        卖出（便捷方法，强制要求止损价）

        新的卖出方法强制要求止损价，用于机构级风控。
        如果没有明确止损价，策略应使用波动率计算默认止损。

        Args:
            symbol (str): 交易对
            entry_price (float): 入场价格（必需）
            stop_loss_price (float): 止损价格（必需）
            order_type (str): 订单类型（market/limit/ioc）
            size (float): 数量（可选，如果不提供则基于风险计算）

        Returns:
            bool: 下单是否成功
        """
        return await self._submit_order(
            symbol=symbol,
            side="sell",
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            order_type=order_type,
            size=size
        )

    async def _submit_order(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss_price: float,
        order_type: str = "market",
        size: Optional[float] = None
    ) -> bool:
        """
        提交订单（内部方法，机构级风控核心）

        1% Rule 实现：
        - 如果没有提供 size，则基于风险计算安全仓位
        - 如果提供了 size，则进行敞口检查

        Args:
            symbol (str): 交易对
            side (str): 方向
            entry_price (float): 入场价格（必需）
            stop_loss_price (float): 止损价格（必需）
            order_type (str): 订单类型
            size (float): 数量（可选，如果不提供则基于风险计算）

        Returns:
            bool: 下单是否成功
        """
        try:
            # 0. 参数验证
            if entry_price <= 0 or stop_loss_price <= 0:
                logger.error(
                    f"策略 {self.strategy_id} 价格参数无效: "
                    f"entry={entry_price}, stop={stop_loss_price}"
                )
                return False

            # 1. 冷却检查
            current_time = time.time()
            if current_time - self._last_trade_time < 5.0:
                logger.warning(
                    f"策略 {self.strategy_id} 冷却中，跳过下单 "
                    f"(剩余: {5.0 - (current_time - self._last_trade_time):.1f}s)"
                )
                return False

            # 2. 检查 OrderManager 是否注入
            if not self._order_manager:
                logger.error(f"OrderManager 未注入，无法下单")
                return False

            # 3. 计算安全仓位（如果未提供）
            final_size = size

            if size is None or size <= 0:
                # 使用 CapitalCommander 计算基于风险的安全仓位
                if self._capital_commander:
                    safe_quantity = self._capital_commander.calculate_safe_quantity(
                        symbol=symbol,
                        entry_price=entry_price,
                        stop_loss_price=stop_loss_price,
                        strategy_id=self.strategy_id
                    )

                    if safe_quantity <= 0:
                        logger.warning(
                            f"策略 {self.strategy_id} 安全仓位计算为 0，跳过下单"
                        )
                        return False

                    final_size = safe_quantity
                    logger.info(
                        f"策略 {self.strategy_id} 使用风险计算仓位: {final_size:.4f}"
                    )
                else:
                    logger.error(f"CapitalCommander 未注入，无法计算安全仓位")
                    return False
            else:
                # 使用策略提供的仓位，但记录警告
                logger.info(
                    f"策略 {self.strategy_id} 使用固定仓位: {final_size:.4f} "
                    f"(跳过风险计算)"
                )

            # 4. 检查购买力（如果使用风险计算的仓位）
            if self._capital_commander:
                amount_usdt = entry_price * final_size
                if not self._capital_commander.check_buying_power(
                    self.strategy_id,
                    amount_usdt
                ):
                    logger.error(
                        f"策略 {self.strategy_id} 资金不足，无法下单"
                    )
                    return False

            # 5. 提交订单
            order = await self._order_manager.submit_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                size=final_size,
                price=entry_price,
                strategy_id=self.strategy_id
            )

            if order:
                self._last_trade_time = time.time()
                self._orders_submitted += 1
                logger.info(
                    f"策略 {self.strategy_id} 下单成功: "
                    f"{symbol} {side} {final_size:.4f} @ {entry_price:.2f}, "
                    f"stop={stop_loss_price:.2f}"
                )
                return True
            else:
                logger.error(f"策略 {self.strategy_id} 下单失败")
                return False

        except Exception as e:
            logger.error(f"策略 {self.strategy_id} 下单异常: {e}")
            return False

    async def start(self):
        """
        启动策略

        注册 TICK 事件处理器
        """
        if not self._event_bus:
            logger.error("EventBus 未注入，无法启动")
            return

        # 注册 TICK 事件处理器
        self._event_bus.register(EventType.TICK, self.on_tick)
        logger.info(f"策略 {self.strategy_id} 已启动")

    async def stop(self):
        """
        停止策略

        注销 TICK 事件处理器
        """
        if not self._event_bus:
            return

        # 注销 TICK 事件处理器
        # TODO: 实现 EventBus.unregister 方法
        logger.info(f"策略 {self.strategy_id} 已停止")

    def enable(self):
        """启用策略"""
        self._enabled = True
        logger.info(f"策略 {self.strategy_id} 已启用")

    def disable(self):
        """禁用策略"""
        self._enabled = False
        logger.info(f"策略 {self.strategy_id} 已禁用")

    def is_enabled(self) -> bool:
        """检查策略是否启用"""
        return self._enabled

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取策略统计信息

        Returns:
            dict: 统计数据
        """
        return {
            'strategy_id': self.strategy_id,
            'symbol': self.symbol,
            'mode': self.mode,
            'enabled': self._enabled,
            'ticks_received': self._ticks_received,
            'signals_generated': self._signals_generated,
            'orders_submitted': self._orders_submitted
        }

    def reset_statistics(self):
        """重置统计信息"""
        self._ticks_received = 0
        self._signals_generated = 0
        self._orders_submitted = 0
        self._last_trade_time = 0.0
        logger.info(f"策略 {self.strategy_id} 统计信息已重置")

    def _increment_ticks(self):
        """增加 Tick 计数"""
        self._ticks_received += 1

    def _increment_signals(self):
        """增加信号计数"""
        self._signals_generated += 1
