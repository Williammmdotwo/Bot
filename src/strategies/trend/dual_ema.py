"""
双均线突破策略 (Dual EMA Crossover Strategy) - v3.0 重构版
使用 9 周期 EMA 和 21 周期 EMA 的交叉信号生成交易信号

架构升级：
- 继承 BaseStrategy
- 使用 RiskProfile 配置风控
- 移除 pandas 依赖（使用原生 Python）
- 移除 _legacy_trash 依赖
"""

import logging
import time
import collections
from typing import Dict, Any, Optional

from ...core.event_types import Event
from ...core.event_bus import EventBus
from ...oms.order_manager import OrderManager
from ...oms.capital_commander import CapitalCommander
from ...config.risk_profile import RiskProfile, StopLossType
from ..base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class DualEMAStrategy(BaseStrategy):
    """
    双均线突破策略（v3.0 重构版）

    使用 EMA 交叉信号生成交易信号：
    - 金叉：快线从下往上穿过慢线 → 买入信号
    - 死叉：快线从上往下穿过慢线 → 卖出信号

    Example:
        >>> strategy = DualEMAStrategy(
        ...     event_bus=event_bus,
        ...     order_manager=order_manager,
        ...     capital_commander=capital_commander,
        ...     symbol="BTC-USDT-SWAP",
        ...     timeframe_minutes=15,
        ...     ema_fast=9,
        ...     ema_slow=21
        ... )
        >>> await strategy.start()
    """

    def __init__(
        self,
        event_bus: EventBus,
        order_manager: OrderManager,
        capital_commander: CapitalCommander,
        symbol: str = "BTC-USDT-SWAP",
        timeframe_minutes: int = 15,
        ema_fast: int = 9,
        ema_slow: int = 21,
        atr_multiplier: float = 2.0,
        mode: str = "PRODUCTION",
        strategy_id: Optional[str] = None
    ):
        """
        初始化双均线策略

        Args:
            event_bus (EventBus): 事件总线
            order_manager (OrderManager): 订单管理器
            capital_commander (CapitalCommander): 资金指挥官
            symbol (str): 交易对
            timeframe_minutes (int): K 线时间周期（分钟）
            ema_fast (int): 快线 EMA 周期
            ema_slow (int): 慢线 EMA 周期
            atr_multiplier (float): ATR 倍数（用于止损）
            mode (str): 策略模式（PRODUCTION/DEV）
            strategy_id (str): 策略 ID
        """
        super().__init__(
            event_bus=event_bus,
            order_manager=order_manager,
            capital_commander=capital_commander,
            symbol=symbol,
            mode=mode,
            strategy_id=strategy_id
        )

        # 策略参数
        self.timeframe_minutes = timeframe_minutes
        self.ema_fast_period = ema_fast
        self.ema_slow_period = ema_slow
        self.atr_multiplier = atr_multiplier

        # 价格缓冲区（使用 collections.deque 限制大小）
        self.closes = collections.deque(maxlen=100)
        self.current_price = 0.0
        self.last_kline_time = 0

        # 交叉状态
        self.previous_ema_fast = None
        self.previous_ema_slow = None
        self.last_signal = None  # 'BUY' or 'SELL'

        # 配置趋势策略风控参数（保守型）
        self.set_risk_profile(RiskProfile(
            strategy_id=self.strategy_id,
            max_leverage=1.5,              # 允许 1.5 倍杠杆
            stop_loss_type=StopLossType.TRAILING,  # 移动止损
            max_order_size_usdt=2000.0,      # 单笔最大 2000 USDT
            single_loss_cap_pct=0.015,       # 单笔最大亏损 1.5%
            max_daily_loss_pct=0.03           # 每日最大亏损 3%
        ))

        logger.info(
            f"双均线策略初始化: symbol={symbol}, "
            f"timeframe={timeframe_minutes}m, "
            f"EMA_fast={ema_fast}, EMA_slow={ema_slow}, "
            f"atr_multiplier={atr_multiplier}"
        )

    async def on_tick(self, event: Event):
        """
        处理 Tick 事件（策略核心逻辑）

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

            # 2. 解析 Tick 数据
            data = event.data
            symbol = data.get('symbol')
            price = data.get('price', 0)
            timestamp = data.get('timestamp', int(time.time()))

            # 3. 检查交易对是否匹配
            if symbol != self.symbol:
                return

            # 4. 增加 Tick 计数
            self._increment_ticks()

            # 5. 更新当前价格
            self.current_price = price

            # 6. K 线合成（简化版）
            current_time = timestamp
            timeframe_seconds = self.timeframe_minutes * 60

            # 如果这是新的 K 线周期
            if current_time - self.last_kline_time >= timeframe_seconds:
                # 将当前价格添加到收盘价列表
                self.closes.append(price)
                self.last_kline_time = current_time

                logger.debug(
                    f"[K线更新] {symbol} 时间={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time))}, "
                    f"价格={price:.2f}, 缓冲区大小={len(self.closes)}"
                )

                # 7. 检查是否有足够的数据计算 EMA
                min_candles = self.ema_slow_period + 1
                if len(self.closes) < min_candles:
                    logger.info(
                        f"⏳ [数据加载中] {symbol}: 当前 {len(self.closes)} / 需要 {min_candles}"
                    )
                    return

                # 8. 计算当前 EMA 值
                current_ema_fast = self._calculate_ema(
                    list(self.closes),
                    self.ema_fast_period
                )
                current_ema_slow = self._calculate_ema(
                    list(self.closes),
                    self.ema_slow_period
                )

                # 9. 计算上一时刻的 EMA 值（去掉最后一根 K 线）
                if len(self.closes) >= min_candles:
                    prev_closes = list(self.closes)[:-1]
                    if len(prev_closes) >= self.ema_slow_period:
                        prev_ema_fast = self._calculate_ema(
                            prev_closes,
                            self.ema_fast_period
                        )
                        prev_ema_slow = self._calculate_ema(
                            prev_closes,
                            self.ema_slow_period
                        )
                    else:
                        # 如果数据不够，使用当前值作为前一个值
                        prev_ema_fast = current_ema_fast
                        prev_ema_slow = current_ema_slow
                else:
                    prev_ema_fast = current_ema_fast
                    prev_ema_slow = current_ema_slow

                # 10. 检测交叉信号
                await self._detect_crossover(
                    current_ema_fast, current_ema_slow,
                    prev_ema_fast, prev_ema_slow,
                    price
                )

                # 11. 更新历史状态
                self.previous_ema_fast = current_ema_fast
                self.previous_ema_slow = current_ema_slow

        except Exception as e:
            logger.error(f"处理 Tick 事件失败: {e}", exc_info=True)

    async def on_signal(self, signal: Dict[str, Any]):
        """
        处理策略信号（双均线策略不使用此方法）

        Args:
            signal (dict): 策略信号
        """
        pass

    def _calculate_ema(self, prices: list, period: int) -> float:
        """
        计算 EMA（指数移动平均线）- 使用原生 Python

        算法：
        EMA(t) = Price(t) * k + EMA(t-1) * (1 - k)
        k = 2 / (N + 1)

        Args:
            prices (list): 价格列表
            period (int): EMA 周期

        Returns:
            float: EMA 值
        """
        if len(prices) < period:
            # 数据不足，返回简单平均
            return sum(prices) / len(prices) if prices else 0.0

        # 计算 EMA
        multiplier = 2.0 / (period + 1)
        ema = prices[0]

        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1.0 - multiplier))

        return ema

    async def _detect_crossover(
        self,
        current_fast: float,
        current_slow: float,
        prev_fast: float,
        prev_slow: float,
        current_price: float
    ):
        """
        检测 EMA 交叉信号

        Args:
            current_fast (float): 当前快线 EMA 值
            current_slow (float): 当前慢线 EMA 值
            prev_fast (float): 前一时刻快线 EMA 值
            prev_slow (float): 前一时刻慢线 EMA 值
            current_price (float): 当前价格
        """
        # 金叉：快线从下往上穿过慢线
        if (current_fast > current_slow and
            prev_fast <= prev_slow and
            self.last_signal != "BUY"):

            logger.info(
                f"🟢 [金叉] {self.symbol}: "
                f"EMA_{self.ema_fast_period} ({current_fast:.2f}) > "
                f"EMA_{self.ema_slow_period} ({current_slow:.2f})"
            )

            # 计算止损价格（基于 ATR，这里简化为固定比例）
            stop_loss_price = current_price * 0.98  # 2% 止损

            # 执行买入
            success = await self.buy(
                symbol=self.symbol,
                entry_price=current_price,
                stop_loss_price=stop_loss_price,
                order_type="market",
                size=None  # 基于风险计算
            )

            if success:
                self.last_signal = "BUY"
                self._increment_signals()
                logger.info(
                    f"✅ [买入执行] {self.symbol} @ {current_price:.2f}, "
                    f"止损={stop_loss_price:.2f}"
                )

        # 死叉：快线从上往下穿过慢线
        elif (current_fast < current_slow and
              prev_fast >= prev_slow and
              self.last_signal != "SELL"):

            logger.info(
                f"🔴 [死叉] {self.symbol}: "
                f"EMA_{self.ema_fast_period} ({current_fast:.2f}) < "
                f"EMA_{self.ema_slow_period} ({current_slow:.2f})"
            )

            # 计算止损价格（基于 ATR，这里简化为固定比例）
            stop_loss_price = current_price * 1.02  # 2% 止损

            # 执行卖出
            success = await self.sell(
                symbol=self.symbol,
                entry_price=current_price,
                stop_loss_price=stop_loss_price,
                order_type="market",
                size=None  # 基于风险计算
            )

            if success:
                self.last_signal = "SELL"
                self._increment_signals()
                logger.info(
                    f"✅ [卖出执行] {self.symbol} @ {current_price:.2f}, "
                    f"止损={stop_loss_price:.2f}"
                )

        # 无交叉，但记录当前状态
        else:
            if len(self.closes) >= self.ema_slow_period + 1:
                logger.debug(
                    f"[监控中] {self.symbol} 价格={current_price:.2f} | "
                    f"快线={current_fast:.2f} | 慢线={current_slow:.2f} | "
                    f"差值={(current_fast - current_slow):.4f}"
                )

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取策略统计信息

        Returns:
            dict: 统计数据
        """
        base_stats = super().get_statistics()

        base_stats.update({
            'ema_fast': self.ema_fast_period,
            'ema_slow': self.ema_slow_period,
            'timeframe_minutes': self.timeframe_minutes,
            'atr_multiplier': self.atr_multiplier,
            'candles_count': len(self.closes),
            'last_signal': self.last_signal,
            'current_ema_fast': self.previous_ema_fast,
            'current_ema_slow': self.previous_ema_slow,
            'current_price': self.current_price
        })

        return base_stats

    def reset_state(self):
        """重置策略状态"""
        self.closes.clear()
        self.current_price = 0.0
        self.last_kline_time = 0
        self.previous_ema_fast = None
        self.previous_ema_slow = None
        self.last_signal = None
        logger.info(f"双均线策略状态已重置")
