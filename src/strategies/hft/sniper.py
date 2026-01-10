"""
HFT 狙击策略 (HFT Sniper Strategy)

大单狙击策略：检测大单并跟随交易。

策略逻辑：
- 监听 TICK 事件
- 检测单笔交易金额超过阈值（默认 5000 USDT）
- 买入方向跟随大单
- 设置冷却时间（默认 5 秒）防止重复触发

风险控制：
- 冷却机制：5 秒内不重复触发
- 资金检查：确保资金充足
"""

import logging
import time
from typing import Dict, Any
from dataclasses import dataclass

from ...core.event_types import Event
from ...core.event_bus import EventBus
from ...oms.order_manager import OrderManager
from ...oms.capital_commander import CapitalCommander
from ..base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


@dataclass
class SniperConfig:
    """狙击策略配置"""
    symbol: str = "BTC-USDT-SWAP"
    position_size: float = 0.1      # 每次下单数量
    cooldown_seconds: float = 5.0   # 冷却时间（秒）
    order_type: str = "market"      # 订单类型
    min_big_order_usdt: float = 5000.0  # 大单阈值（USDT）


class SniperStrategy(BaseStrategy):
    """
    HFT 狙击策略

    检测大单并跟随交易。

    Example:
        >>> sniper = SniperStrategy(
        ...     event_bus=event_bus,
        ...     order_manager=order_manager,
        ...     capital_commander=capital_commander,
        ...     symbol="BTC-USDT-SWAP",
        ...     position_size=0.1
        ... )
        >>> await sniper.start()
    """

    def __init__(
        self,
        event_bus: EventBus,
        order_manager: OrderManager,
        capital_commander: CapitalCommander,
        symbol: str = "BTC-USDT-SWAP",
        position_size: float = 0.1,
        cooldown_seconds: float = 5.0,
        order_type: str = "market",
        min_big_order_usdt: float = 5000.0,
        mode: str = "PRODUCTION"
    ):
        """
        初始化狙击策略

        Args:
            event_bus (EventBus): 事件总线
            order_manager (OrderManager): 订单管理器
            capital_commander (CapitalCommander): 资金指挥官
            symbol (str): 交易对
            position_size (float): 每次下单数量
            cooldown_seconds (float): 冷却时间（秒）
            order_type (str): 订单类型
            min_big_order_usdt (float): 大单阈值（USDT）
            mode (str): 策略模式
        """
        super().__init__(
            event_bus=event_bus,
            order_manager=order_manager,
            capital_commander=capital_commander,
            symbol=symbol,
            mode=mode
        )

        # 策略配置
        self.config = SniperConfig(
            symbol=symbol,
            position_size=position_size,
            cooldown_seconds=cooldown_seconds,
            order_type=order_type,
            min_big_order_usdt=min_big_order_usdt
        )

        # 策略状态
        self._big_orders_detected = 0
        self._big_order_amount_total = 0.0

        logger.info(
            f"狙击策略配置: symbol={symbol}, "
            f"position_size={position_size}, "
            f"cooldown={cooldown_seconds}s, "
            f"min_big_order={min_big_order_usdt} USDT"
        )

    async def on_tick(self, event: Event):
        """
        处理 Tick 事件（策略核心逻辑）

        检测大单并跟随交易。

        Args:
            event (Event): TICK 事件
                data: {
                    'symbol': str,
                    'price': float,
                    'size': float,
                    'side': str,
                    'usdt_value': float,
                    'timestamp': int
                }
        """
        try:
            # 1. 检查策略是否启用
            if not self.is_enabled():
                return

            # 2. 检查冷却时间
            current_time = time.time()
            if current_time - self._last_trade_time < self.config.cooldown_seconds:
                return

            # 3. 解析 Tick 数据
            data = event.data
            symbol = data.get('symbol')
            price = data.get('price', 0)
            size = data.get('size', 0)
            side = data.get('side', '').lower()
            usdt_value = data.get('usdt_value', 0)

            # 4. 检查交易对是否匹配
            if symbol != self.symbol:
                return

            # 5. 增加 Tick 计数
            self._increment_ticks()

            # 6. 检测大单
            if self._is_big_order(usdt_value):
                self._big_orders_detected += 1
                self._big_order_amount_total += usdt_value

                logger.info(
                    f"🎯 检测到大单: {symbol} {side.upper()} "
                    f"{size:.4f} @ {price:.2f} = {usdt_value:.2f} USDT"
                )

                # 7. 跟随交易
                # 强制取整：OKX SWAP 合约的 sz 必须是整数
                position_size_int = int(self.config.position_size)
                if position_size_int < 1:
                    logger.warning(
                        f"⚠️  position_size {self.config.position_size} 小于 1，"
                        f"强制设为 1"
                    )
                    position_size_int = 1

                if side == 'buy':
                    # 大单买入 → 我们也买入
                    await self.buy(
                        symbol=self.symbol,
                        size=position_size_int,
                        order_type=self.config.order_type,
                        price=price  # 传入价格，用于资金检查
                    )
                    self._increment_signals()

                elif side == 'sell':
                    # 大单卖出 → 我们也卖出
                    await self.sell(
                        symbol=self.symbol,
                        size=position_size_int,
                        order_type=self.config.order_type,
                        price=price  # 传入价格，用于资金检查
                    )
                    self._increment_signals()

        except Exception as e:
            logger.error(f"处理 Tick 事件失败: {e}", exc_info=True)

    async def on_signal(self, signal: Dict[str, Any]):
        """
        处理策略信号（狙击策略不使用此方法）

        Args:
            signal (dict): 策略信号
        """
        pass

    def _is_big_order(self, usdt_value: float) -> bool:
        """
        判断是否为大单

        Args:
            usdt_value (float): 交易金额（USDT）

        Returns:
            bool: 是否为大单
        """
        return usdt_value >= self.config.min_big_order_usdt

    def update_config(self, **kwargs):
        """
        更新策略配置

        Args:
            **kwargs: 配置参数
                - position_size: float
                - cooldown_seconds: float
                - order_type: str
                - min_big_order_usdt: float
        """
        if 'position_size' in kwargs:
            self.config.position_size = kwargs['position_size']
            logger.info(f"position_size 更新为 {kwargs['position_size']:.4f}")

        if 'cooldown_seconds' in kwargs:
            self.config.cooldown_seconds = kwargs['cooldown_seconds']
            logger.info(f"cooldown_seconds 更新为 {kwargs['cooldown_seconds']}s")

        if 'order_type' in kwargs:
            self.config.order_type = kwargs['order_type']
            logger.info(f"order_type 更新为 {kwargs['order_type']}")

        if 'min_big_order_usdt' in kwargs:
            self.config.min_big_order_usdt = kwargs['min_big_order_usdt']
            logger.info(
                f"min_big_order_usdt 更新为 {kwargs['min_big_order_usdt']:.2f} USDT"
            )

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取策略统计信息

        Returns:
            dict: 统计数据
        """
        base_stats = super().get_statistics()

        base_stats.update({
            'big_orders_detected': self._big_orders_detected,
            'big_order_amount_total': self._big_order_amount_total,
            'avg_big_order_amount': (
                self._big_order_amount_total / self._big_orders_detected
                if self._big_orders_detected > 0 else 0.0
            ),
            'config': {
                'position_size': self.config.position_size,
                'cooldown_seconds': self.config.cooldown_seconds,
                'order_type': self.config.order_type,
                'min_big_order_usdt': self.config.min_big_order_usdt
            }
        })

        return base_stats

    def reset_statistics(self):
        """重置统计信息"""
        super().reset_statistics()
        self._big_orders_detected = 0
        self._big_order_amount_total = 0.0
        logger.info(f"狙击策略统计信息已重置")
