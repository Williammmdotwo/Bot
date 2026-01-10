"""
秃鹫策略 (Vulture Strategy)

闪崩接针策略：在价格偏离 EMA 时发送 IOC 限价单抢反弹。

触发条件：
- PRODUCTION 模式：price <= ema_fast * 0.99（严格暴跌 1%）
- DEV 模式：price <= ema_fast * 0.997（放宽到 0.3%）

动作：下达 IOC 买单（带滑点）
"""

import logging
import time
from typing import Optional, Dict, Any
from ..base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class VultureStrategy(BaseStrategy):
    """
    秃鹫策略 (Vulture)

    在价格闪崩时逆势接针，抢反弹。

    Attributes:
        ema_period (int): EMA 周期（默认 9）
        slippage_pct (float): 滑点百分比（默认 0.002 = 0.2%）
        threshold (float): 价格阈值（根据模式自动设置）

    Example:
        >>> strategy = VultureStrategy(
        ...     symbol="BTC-USDT-SWAP",
        ...     mode="PRODUCTION",
        ...     ema_period=9
        ... )
        >>> await strategy.on_tick(price=50000.0, timestamp=1234567890000)
    """

    def __init__(
        self,
        symbol: str,
        mode: str = "PRODUCTION",
        ema_period: int = 9,
        slippage_pct: float = 0.002
    ):
        """
        初始化秃鹫策略

        Args:
            symbol (str): 交易对
            mode (str): 策略模式（PRODUCTION/DEV）
            ema_period (int): EMA 周期（默认 9）
            slippage_pct (float): 滑点百分比（默认 0.002 = 0.2%）
        """
        super().__init__(symbol, mode)

        self.ema_period = ema_period
        self.slippage_pct = slippage_pct

        # 根据模式设置阈值
        if self.mode == "DEV":
            self.price_drop_threshold = 0.997  # 跌幅 0.3%
            self.mode_suffix = " [DEV MODE]"
        else:
            self.price_drop_threshold = 0.99  # 跌幅 1%
            self.mode_suffix = ""

        # EMA 状态
        self.ema: Optional[float] = None

        # 统计信息
        self.trigger_count = 0
        self.trade_executions = 0

        # 冷却时间
        self.last_trigger_time = 0.0

        logger.info(
            f"秃鹫策略初始化: symbol={symbol}, mode={mode}, "
            f"ema_period={ema_period}, threshold={self.price_drop_threshold}"
        )

    def _calculate_ema(self, price: float) -> float:
        """
        计算 EMA（指数移动平均）

        使用递归公式：EMA = (price - EMA_prev) * alpha + EMA_prev
        alpha = 2 / (period + 1)

        Args:
            price (float): 当前价格

        Returns:
            float: 计算后的 EMA 值
        """
        if self.ema is None:
            # 第一次，直接返回价格
            return price

        # 计算平滑系数 alpha
        alpha = 2.0 / (self.ema_period + 1)

        # 递归计算 EMA
        ema = (price - self.ema) * alpha + self.ema

        return ema

    async def on_tick(self, price: float, size: float = 0.0, side: str = "", timestamp: int = 0):
        """
        处理 Tick 数据

        Args:
            price (float): 当前价格
            size (float): 交易数量
            side (str): 交易方向
            timestamp (int): 时间戳（毫秒）
        """
        if not self.is_enabled():
            return

        # 更新 EMA
        self.ema = self._calculate_ema(price)

        # 检查触发条件
        if self.ema is not None and price <= self.ema * self.price_drop_threshold:
            await self._check_and_execute(price, self.ema)

    async def _check_and_execute(self, price: float, ema: float):
        """
        检查并执行交易

        Args:
            price (float): 当前价格
            ema (float): EMA 值
        """
        # 检查冷却时间
        current_time = time.time()
        if current_time - self.last_trigger_time < 5.0:  # 冷却 5 秒
            logger.debug(f"秃鹫策略冷却中，跳过")
            return

        self.trigger_count += 1
        self.last_trigger_time = current_time

        logger.info(
            f"秃鹫策略触发{self.mode_suffix}: price={price}, ema={ema}, "
            f"threshold={ema * self.price_drop_threshold}, trigger_count={self.trigger_count}"
        )

        # 生成买入信号
        signal = {
            'strategy': 'vulture',
            'signal': 'BUY',
            'symbol': self.symbol,
            'price': price,
            'type': 'ioc',  # IOC 订单
            'slippage_pct': self.slippage_pct,
            'timestamp': int(time.time() * 1000)
        }

        await self.on_signal(signal)

    async def on_signal(self, signal: Dict[str, Any]):
        """
        处理策略信号

        Args:
            signal (dict): 策略信号
        """
        if signal.get('signal') == 'BUY':
            self.trade_executions += 1
            logger.info(f"秃鹫策略信号: {signal}")
        # 实际的订单执行由 OMS 处理

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取策略统计信息

        Returns:
            dict: 统计数据
        """
        stats = super().get_statistics()
        stats.update({
            'ema_period': self.ema_period,
            'trigger_count': self.trigger_count,
            'trade_executions': self.trade_executions,
            'ema': self.ema
        })
        return stats

    def reset_statistics(self):
        """重置统计信息"""
        old_triggers = self.trigger_count
        old_trades = self.trade_executions

        self.trigger_count = 0
        self.trade_executions = 0
        self.ema = None

        logger.info(
            f"秃鹫策略重置统计: triggers={old_triggers}, trades={old_trades}"
        )
