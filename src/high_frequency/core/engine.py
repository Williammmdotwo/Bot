"""
HFT 混合交易引擎

本模块提供高频交易的核心逻辑，整合市场状态、订单执行和风控。

核心功能：
- EMA 计算（不使用 Pandas）
- 秃鹫模式 (Vulture)：闪崩接针策略
- 狙击模式 (Sniper)：大单追涨策略
- 风控整合：所有交易前检查 RiskGuard

设计原则：
- 不使用 Pandas
- EMA 使用递归计算
- 异步设计，低延迟
"""

import asyncio
import logging
from typing import Optional, List
from ..data.memory_state import MarketState, Trade
from ..execution.executor import OrderExecutor
from ..execution.circuit_breaker import RiskGuard

logger = logging.getLogger(__name__)


class HybridEngine:
    """
    HFT 混合交易引擎

    整合市场状态、订单执行和风控，实现两种交易策略：
    1. 秃鹫模式 (Vulture)：闪崩接针
    2. 狙击模式 (Sniper)：大单追涨

    Example:
        >>> market_state = MarketState()
        >>> executor = OrderExecutor(...)
        >>> risk_guard = RiskGuard()
        >>>
        >>> engine = HybridEngine(
        ...     market_state=market_state,
        ...     executor=executor,
        ...     risk_guard=risk_guard,
        ...     symbol="BTC-USDT-SWAP",
        ...     mode="hybrid"
        ... )
        >>>
        >>> # 处理每个 Tick
        >>> await engine.on_tick(price=50000.0, timestamp=1234567890000)
    """

    def __init__(
        self,
        market_state: MarketState,
        executor: OrderExecutor,
        risk_guard: RiskGuard,
        symbol: str,
        mode: str = "hybrid",
        order_size: float = 0.01,
        ema_fast_period: int = 9,
        ema_slow_period: int = 21,
        ioc_slippage_pct: float = 0.002,
        sniper_flow_window: float = 3.0,
        sniper_min_trades: int = 20,
        sniper_min_net_volume: float = 10000.0
    ):
        """
        初始化混合引擎

        Args:
            market_state (MarketState): 市场状态管理器
            executor (OrderExecutor): 订单执行器
            risk_guard (RiskGuard): 风控熔断器
            symbol (str): 交易对
            mode (str): 交易模式（"hybrid", "vulture", "sniper"）
            order_size (float): 订单数量
            ema_fast_period (int): 快速 EMA 周期（默认 9）
            ema_slow_period (int): 慢速 EMA 周期（默认 21）
            ioc_slippage_pct (float): IOC 订单滑点百分比（默认 0.002 = 0.2%）
            sniper_flow_window (float): 狙击模式流量分析窗口（秒），默认 3.0
            sniper_min_trades (int): 狙击模式最小交易笔数，默认 20
            sniper_min_net_volume (float): 狙击模式最小净流量（USDT），默认 10000.0
        """
        self.market_state = market_state
        self.executor = executor
        self.risk_guard = risk_guard
        self.symbol = symbol
        self.mode = mode.lower()
        self.order_size = order_size
        self.ema_fast_period = ema_fast_period
        self.ema_slow_period = ema_slow_period
        self.ioc_slippage_pct = ioc_slippage_pct
        self.sniper_flow_window = sniper_flow_window
        self.sniper_min_trades = sniper_min_trades
        self.sniper_min_net_volume = sniper_min_net_volume

        # EMA 状态
        self.ema_fast: Optional[float] = None
        self.ema_slow: Optional[float] = None

        # 阻力位
        self.resistance: float = 0.0
        self._price_history: List[float] = []
        self._resistance_window = 50  # 阻力位窗口大小

        # 统计信息
        self.tick_count = 0
        self.vulture_triggers = 0
        self.sniper_triggers = 0
        self.trade_executions = 0

        logger.info(
            f"HybridEngine 初始化: symbol={symbol}, mode={mode}, "
            f"order_size={order_size}, ema_fast={ema_fast_period}, ema_slow={ema_slow_period}"
        )

    def _calculate_ema(
        self,
        price: float,
        prev_ema: Optional[float],
        period: int
    ) -> float:
        """
        计算 EMA（指数移动平均）

        使用递归公式：EMA = (price - EMA_prev) * alpha + EMA_prev
        alpha = 2 / (period + 1)

        Args:
            price (float): 当前价格
            prev_ema (Optional[float]): 之前的 EMA 值
            period (int): EMA 周期

        Returns:
            float: 计算后的 EMA 值
        """
        if prev_ema is None:
            # 第一次，直接返回价格
            return price

        # 计算平滑系数 alpha
        alpha = 2.0 / (period + 1)

        # 递归计算 EMA
        ema = (price - prev_ema) * alpha + prev_ema

        return ema

    def _update_resistance(self, price: float):
        """
        更新阻力位

        阻力位定义为最近 50 笔交易中的最高价。

        Args:
            price (float): 当前价格
        """
        # 添加价格到历史记录
        self._price_history.append(price)

        # 只保留最近 N 个价格
        if len(self._price_history) > self._resistance_window:
            self._price_history.pop(0)

        # 更新阻力位（最大值）
        self.resistance = max(self._price_history)

        logger.debug(f"更新阻力位: {self.resistance}")

    def _get_recent_whales(
        self,
        current_time: int,
        window_ms: int = 2000
    ) -> int:
        """
        获取最近指定时间窗口内的大单数量

        Args:
            current_time (int): 当前时间戳（毫秒）
            window_ms (int): 时间窗口（毫秒），默认 2000（2 秒）

        Returns:
            int: 大单数量
        """
        count = 0

        for whale in self.market_state.whale_orders:
            time_diff = current_time - whale.timestamp

            if time_diff <= window_ms:
                count += 1

        return count

    async def _vulture_strategy(self, price: float, ema_fast: float):
        """
        秃鹫模式 (Vulture)：闪崩接针策略

        触发条件：price <= ema_fast * 0.99
        动作：下达 IOC 买单（带滑点）

        Args:
            price (float): 当前价格
            ema_fast (float): 快速 EMA 值
        """
        # 检查触发条件
        if price <= ema_fast * 0.99:
            self.vulture_triggers += 1

            logger.info(
                f"秃鹫模式触发: price={price}, ema_fast={ema_fast}, "
                f"threshold={ema_fast * 0.99}, trigger_count={self.vulture_triggers}"
            )

            # 风控检查
            if not self.risk_guard.can_trade():
                logger.warning("风控拒绝交易（秃鹫模式）")
                return

            # 下达 IOC 买单（应用滑点）
            try:
                # 买入时：limit_price = current_price * (1 + ioc_slippage_pct)
                limit_price = price * (1 + self.ioc_slippage_pct)

                logger.info(
                    f"下达秃鹫买单: current_price={price}, limit_price={limit_price:.2f}, "
                    f"slippage={self.ioc_slippage_pct*100:.2f}%, size={self.order_size}"
                )

                response = await self.executor.place_ioc_order(
                    symbol=self.symbol,
                    side="buy",
                    price=limit_price,
                    size=self.order_size
                )

                self.trade_executions += 1
                logger.info(f"秃鹫订单已提交: {response}")

            except Exception as e:
                logger.error(f"秃鹫订单执行失败: {e}")

    async def _sniper_strategy(self, price: float, current_time: int):
        """
        狙击模式 (Sniper)：大单追涨策略（升级版）

        触发条件：
        1. 最近 3 秒内交易笔数 >= sniper_min_trades（默认 20）
        2. 最近 3 秒内净流量（买入-卖出）>= sniper_min_net_volume（默认 10000 USDT）
        3. price > resistance（突破阻力位）

        动作：下达 IOC 买单（模拟市价单，带滑点）

        Args:
            price (float): 当前价格
            current_time (int): 当前时间戳（毫秒）
        """
        # 计算流量压力
        net_volume, trade_count, intensity = self.market_state.calculate_flow_pressure(
            window_seconds=self.sniper_flow_window
        )

        # 检查触发条件
        if (trade_count >= self.sniper_min_trades and
            net_volume >= self.sniper_min_net_volume and
            price > self.resistance):

            self.sniper_triggers += 1

            logger.info(
                f"狙击模式触发: trade_count={trade_count}, net_volume={net_volume:.2f}, "
                f"intensity={intensity:.2f}, price={price}, "
                f"resistance={self.resistance}, trigger_count={self.sniper_triggers}"
            )

            # 风控检查
            if not self.risk_guard.can_trade():
                logger.warning("风控拒绝交易（狙击模式）")
                return

            # 下达 IOC 买单（模拟市价单，应用滑点）
            try:
                # 买入时：limit_price = current_price * (1 + ioc_slippage_pct)
                limit_price = price * (1 + self.ioc_slippage_pct)

                logger.info(
                    f"下达狙击买单: current_price={price}, limit_price={limit_price:.2f}, "
                    f"slippage={self.ioc_slippage_pct*100:.2f}%, size={self.order_size}, "
                    f"trade_count={trade_count}, net_volume={net_volume:.2f}, "
                    f"resistance={self.resistance}"
                )

                response = await self.executor.place_ioc_order(
                    symbol=self.symbol,
                    side="buy",
                    price=limit_price,
                    size=self.order_size
                )

                self.trade_executions += 1
                logger.info(f"狙击订单已提交: {response}")

            except Exception as e:
                logger.error(f"狙击订单执行失败: {e}")

    async def on_tick(self, price: float, size: float = 0.0, side: str = "", timestamp: int = 0):
        """
        处理每个 Tick 数据

        这是引擎的核心方法，每个 WebSocket Tick 都会调用此方法。

        Args:
            price (float): 当前价格
            size (float): 交易数量（可选，默认 0.0）
            side (str): 交易方向（可选，默认 ""）
            timestamp (int): 时间戳（毫秒，可选，默认 0）

        Example:
            >>> # 在 TickStream 回调中调用
            >>> async def on_trade(price, size, side, timestamp):
            ...     await engine.on_tick(price, size, side, timestamp)
        """
        self.tick_count += 1

        #1. 更新 EMA（每次 Tick 都更新）
        self.ema_fast = self._calculate_ema(price, self.ema_fast, self.ema_fast_period)
        self.ema_slow = self._calculate_ema(price, self.ema_slow, self.ema_slow_period)

        if self.tick_count % 100 == 0:  # 每 100 个 tick 记录一次
            logger.info(
                f"Tick #{self.tick_count}: price={price}, "
                f"ema_fast={self.ema_fast}, ema_slow={self.ema_slow}"
            )

        #2. 更新阻力位
        self._update_resistance(price)

        #3. 秃鹫模式：闪崩接针
        if self.mode in ["hybrid", "vulture"]:
            if self.ema_fast is not None:
                await self._vulture_strategy(price, self.ema_fast)

        #4. 狙击模式：大单追涨
        if self.mode in ["hybrid", "sniper"]:
            await self._sniper_strategy(price, timestamp)

    def get_statistics(self) -> dict:
        """
        获取引擎统计信息

        Returns:
            dict: 包含各项统计数据的字典

        Example:
            >>> stats = engine.get_statistics()
            >>> print(f"Tick 数量: {stats['tick_count']}")
            >>> print(f"秃鹫触发: {stats['vulture_triggers']}")
            >>> print(f"狙击触发: {stats['sniper_triggers']}")
        """
        return {
            'symbol': self.symbol,
            'mode': self.mode,
            'tick_count': self.tick_count,
            'vulture_triggers': self.vulture_triggers,
            'sniper_triggers': self.sniper_triggers,
            'trade_executions': self.trade_executions,
            'ema_fast': self.ema_fast,
            'ema_slow': self.ema_slow,
            'resistance': self.resistance,
            'order_size': self.order_size
        }

    def reset_statistics(self):
        """
        重置统计信息

        Example:
            >>> engine.reset_statistics()
        """
        old_vulture = self.vulture_triggers
        old_sniper = self.sniper_triggers
        old_trades = self.trade_executions

        self.tick_count = 0
        self.vulture_triggers = 0
        self.sniper_triggers = 0
        self.trade_executions = 0

        logger.info(
            f"重置统计: vulture={old_vulture}, sniper={old_sniper}, trades={old_trades}"
        )
