"""
策略基类 (Base Strategy)

定义所有策略的通用接口和基础功能。

设计原则：
- 策略只负责交易逻辑，不关心数据源
- 通过事件总线接收市场数据
- 纯粹的策略实现，不包含网络通信
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
        size: float,
        order_type: str = "market",
        price: Optional[float] = None
    ) -> bool:
        """
        买入（便捷方法）

        Args:
            symbol (str): 交易对
            size (float): 数量
            order_type (str): 订单类型（market/limit/ioc）
            price (float): 价格（限价单必需）

        Returns:
            bool: 下单是否成功
        """
        return await self._submit_order(
            symbol=symbol,
            side="buy",
            size=size,
            order_type=order_type,
            price=price
        )

    async def sell(
        self,
        symbol: str,
        size: float,
        order_type: str = "market",
        price: Optional[float] = None
    ) -> bool:
        """
        卖出（便捷方法）

        Args:
            symbol (str): 交易对
            size (float): 数量
            order_type (str): 订单类型（market/limit/ioc）
            price (float): 价格（限价单必需）

        Returns:
            bool: 下单是否成功
        """
        return await self._submit_order(
            symbol=symbol,
            side="sell",
            size=size,
            order_type=order_type,
            price=price
        )

    async def _submit_order(
        self,
        symbol: str,
        side: str,
        size: float,
        order_type: str = "market",
        price: Optional[float] = None
    ) -> bool:
        """
        提交订单（内部方法）

        Args:
            symbol (str): 交易对
            side (str): 方向
            size (float): 数量
            order_type (str): 订单类型
            price (float): 价格

        Returns:
            bool: 下单是否成功
        """
        try:
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

            # 3. 检查 CapitalCommander 是否注入
            if self._capital_commander:
                # 计算订单金额
                amount_usdt = price * size if price else 0
                # 简化处理：实际应该从 tick 获取当前价
                if amount_usdt == 0:
                    logger.warning(
                        f"无法计算订单金额，跳过资金检查"
                    )
                else:
                    # 检查购买力
                    if not self._capital_commander.check_buying_power(
                        self.strategy_id,
                        amount_usdt
                    ):
                        logger.error(
                            f"策略 {self.strategy_id} 资金不足，无法下单"
                        )
                        return False

            # 4. 提交订单
            order = await self._order_manager.submit_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                size=size,
                price=price,
                strategy_id=self.strategy_id
            )

            if order:
                self._last_trade_time = time.time()
                self._orders_submitted += 1
                logger.info(
                    f"策略 {self.strategy_id} 下单成功: "
                    f"{symbol} {side} {size:.4f}"
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
