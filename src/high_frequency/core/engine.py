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
import time
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
        sniper_min_net_volume: float = 10000.0,
        strategy_mode: str = "PRODUCTION",
        risk_ratio: float = 0.2,
        leverage: int = 10
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
            strategy_mode (str): 策略模式（"PRODUCTION" 或 "DEV"），默认 "PRODUCTION"
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

        # 策略模式（PRODUCTION = 堡垒模式，DEV = 激进模式）
        self.strategy_mode = strategy_mode.upper()

        # [新增] 动态资金管理配置
        self.risk_ratio = risk_ratio  # 风险比例（如 0.2 表示使用 20% 的余额）
        self.leverage = leverage  # 杠杆倍数（如 10 表示 10 倍杠杆）

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

        # [新增] 当前持仓数量 (正为多/负为空/0为无)
        self.current_position = 0.0
        self.last_sync_time = 0.0  # [新增] 上次持仓同步时间戳

        # [新增] 持仓详细信息（用于实时私有流）
        self.entry_price: Optional[float] = None  # 开仓均价
        self.entry_time: Optional[int] = None  # 开仓时间（毫秒）

        # [新增] 出场引擎状态
        self.highest_price: Optional[float] = None  # 持仓后的最高价格（用于追踪止盈）

        logger.info(
            f"HybridEngine 初始化: symbol={symbol}, mode={mode}, "
            f"order_size={order_size}, ema_fast={ema_fast_period}, ema_slow={ema_slow_period}, "
            f"strategy_mode={self.strategy_mode}"
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
                count +=1

        return count

    async def _calculate_dynamic_size(self, price: float) -> int:
        """
        [新增] 动态资金管理 - 计算下单数量

        基于风险比例和杠杆计算仓位大小：
        1. 获取当前 USDT 余额
        2. 计算目标仓位价值：Target_Value = Balance * risk_ratio * leverage
        3. 计算张数：Size = int(Target_Value / price)
        4. 兜底：如果 Size < 1，返回 0（资金不足）或 1（最小测试）

        Args:
            price (float): 当前价格

        Returns:
            int: 下单数量（张数，整数）

        Example:
            >>> balance = 10000.0  # 10000 USDT
            >>> risk_ratio = 0.2  # 使用 20% 的余额
            >>> leverage = 10  # 10 倍杠杆
            >>> price = 50000.0  # BTC 价格
            >>> size = await _calculate_dynamic_size(price)
            >>> print(size)
            4  # 10000 * 0.2 * 10 / 50000 = 4 张
        """
        try:
            # 1. 获取当前 USDT 余额
            balance = await self.executor.get_usdt_balance()

            if balance <= 0:
                logger.warning(f"💰 余额不足: {balance:.2f} USDT，无法开仓")
                return 0

            # 2. 计算目标仓位价值
            # Target_Value = Balance * risk_ratio * leverage
            target_value = balance * self.risk_ratio * self.leverage

            # 3. 计算张数
            # Size = int(Target_Value / price)
            size = int(target_value / price)

            # 4. 兜底：最小 1 张
            if size < 1:
                size = 1
                logger.warning(
                    f"⚠️  计算出的仓位不足 1 张，调整为 1 张（最小测试）"
                )

            logger.info(
                f"💰 动态仓位计算: balance={balance:.2f}, risk_ratio={self.risk_ratio}, "
                f"leverage={self.leverage}x, target_value={target_value:.2f}, "
                f"price={price:.2f}, size={size}"
            )

            return size

        except Exception as e:
            logger.error(f"❌ 动态仓位计算失败: {e}")
            # 异常时使用固定仓位
            return int(self.order_size)

    async def _vulture_strategy(self, price: float, ema_fast: float):
        """
        秃鹫模式 (Vulture)：闪崩接针策略

        触发条件：
        - PRODUCTION 模式：price <= ema_fast * 0.99（严格暴跌）
        - DEV 模式：price <= ema_fast * 0.997（放宽 70%，即跌幅从 1% 降到 0.3%）

        动作：下达 IOC 买单（带滑点）

        Args:
            price (float): 当前价格
            ema_fast (float): 快速 EMA 值
        """
        # 根据策略模式计算阈值
        if self.strategy_mode == "DEV":
            # DEV 模式：跌幅要求降低 70%（从 1% 降到 0.3%）
            price_drop_threshold = 0.997
            mode_suffix = " [DEV MODE TRIGGER]"
        else:
            # PRODUCTION 模式：保持严格逻辑
            price_drop_threshold = 0.99
            mode_suffix = ""

        # 检查触发条件
        if price <= ema_fast * price_drop_threshold:
            self.vulture_triggers +=1

            logger.info(
                f"秃鹫模式触发{mode_suffix}: price={price}, ema_fast={ema_fast}, "
                f"threshold={ema_fast * price_drop_threshold}, trigger_count={self.vulture_triggers}"
            )

            # 风控检查
            if not self.risk_guard.can_trade():
                logger.warning("风控拒绝交易（秃鹫模式）")
                return

            # 下达 IOC 买单（应用滑点）
            try:
                # [新增] 动态仓位计算
                dynamic_size = await self._calculate_dynamic_size(price)
                if dynamic_size == 0:
                    logger.warning("💰 余额不足，跳过秃鹫订单")
                    return

                # 买入时：limit_price = current_price * (1 + ioc_slippage_pct)
                limit_price = price * (1 + self.ioc_slippage_pct)

                logger.info(
                    f"下达秃鹫买单: current_price={price}, limit_price={limit_price:.2f}, "
                    f"slippage={self.ioc_slippage_pct*100:.2f}%, size={dynamic_size}"
                )

                response = await self.executor.place_ioc_order(
                    symbol=self.symbol,
                    side="buy",
                    price=limit_price,
                    size=dynamic_size
                )

                self.trade_executions += 1
                logger.info(f"秃鹫订单已提交: {response}")

                # 🛑 [修复] 乐观更新持仓状态 (Optimistic Update)
                # 防止在等待 WS 推送的间隙重复触发下单信号
                # 假设成交成功，立即修改本地状态
                self.current_position = float(dynamic_size)  # 标记为已持仓
                self.entry_price = price  # 临时记录开仓价
                self.entry_time = timestamp  # 记录开仓时间（毫秒）
                self.highest_price = price

                logger.info(
                    f"🔒 [乐观锁] 本地状态已更新，暂停开仓，等待 PMS 确认... "
                    f"(type=秃鹫, price={price}, size={dynamic_size})"
                )

            except Exception as e:
                logger.error(f"秃鹫订单执行失败: {e}")

    async def _sniper_strategy(self, price: float, current_time: int):
        """
        狙击模式 (Sniper)：大单追涨策略（升级版）

        触发条件：
        1. 最近 3 秒内交易笔数 >= sniper_min_trades（默认 20）
        2. 最近 3 秒内净流量（买入-卖出）>= sniper_min_net_volume（默认 10000 USDT）

        PRODUCTION 模式：price > resistance（严格突破）
        DEV 模式：price > resistance * 0.9995（放宽阻力位，允许在阻力位下方 0.05% 抢跑）

        动作：下达 IOC 买单（模拟市价单，带滑点）

        Args:
            price (float): 当前价格
            current_time (int): 当前时间戳（毫秒）
        """
        # 计算流量压力
        net_volume, trade_count, intensity = self.market_state.calculate_flow_pressure(
            window_seconds=self.sniper_flow_window
        )

        # 根据策略模式计算价格条件
        if self.strategy_mode == "DEV":
            # DEV 模式：放宽阻力位限制，允许在阻力位下方 0.05% 抢跑
            price_condition = price > (self.resistance * 0.9995)
            mode_suffix = " [DEV MODE TRIGGER]"
            resistance_log_str = f"{self.resistance * 0.9995:.4f} (放宽 0.05%)"
        else:
            # PRODUCTION 模式：严格突破阻力位
            price_condition = price > self.resistance
            mode_suffix = ""
            resistance_log_str = f"{self.resistance:.4f}"

        # [新增] 调试日志：看看差多少触发（只输出到文件，不输出到终端）
        if net_volume >= self.sniper_min_net_volume:
            logger.debug(
                f"👀 发现大单! 净量:{net_volume:.0f} | 价格:{price:.2f} vs 阻力:{resistance_log_str} | "
                f"满足价格条件? {price_condition} | 交易笔数:{trade_count}"
            )

        # 检查触发条件
        if (trade_count >= self.sniper_min_trades and
            net_volume >= self.sniper_min_net_volume and
            price_condition):

            self.sniper_triggers +=1

            logger.info(
                f"狙击模式触发{mode_suffix}: trade_count={trade_count}, net_volume={net_volume:.2f}, "
                f"intensity={intensity:.2f}, price={price}, "
                f"resistance={self.resistance}, trigger_count={self.sniper_triggers}"
            )

            # 风控检查
            if not self.risk_guard.can_trade():
                logger.warning("风控拒绝交易（狙击模式）")
                return

            # 下达 IOC 买单（模拟市价单，应用滑点）
            try:
                # [新增] 动态仓位计算
                dynamic_size = await self._calculate_dynamic_size(price)
                if dynamic_size == 0:
                    logger.warning("💰 余额不足，跳过狙击订单")
                    return

                # 买入时：limit_price = current_price * (1 + ioc_slippage_pct)
                limit_price = price * (1 + self.ioc_slippage_pct)

                logger.info(
                    f"下达狙击买单: current_price={price}, limit_price={limit_price:.2f}, "
                    f"slippage={self.ioc_slippage_pct*100:.2f}%, size={dynamic_size}, "
                    f"trade_count={trade_count}, net_volume={net_volume:.2f}, "
                    f"resistance={self.resistance}"
                )

                response = await self.executor.place_ioc_order(
                    symbol=self.symbol,
                    side="buy",
                    price=limit_price,
                    size=dynamic_size
                )

                self.trade_executions += 1
                logger.info(f"狙击订单已提交: {response}")

                # 🛑 [修复] 乐观更新持仓状态 (Optimistic Update)
                # 防止在等待 WS 推送的间隙重复触发下单信号
                # 假设成交成功，立即修改本地状态
                self.current_position = float(dynamic_size)  # 标记为已持仓
                self.entry_price = price  # 临时记录开仓价
                self.entry_time = timestamp  # 记录开仓时间（毫秒）
                self.highest_price = price

                logger.info(
                    f"🔒 [乐观锁] 本地状态已更新，暂停开仓，等待 PMS 确认... "
                    f"(type=狙击, price={price}, size={dynamic_size})"
                )

            except Exception as e:
                logger.error(f"狙击订单执行失败: {e}")

    async def _check_exit_signals(self, current_price: float, timestamp: int):
        """
        [新增] 主动出场引擎 - 检查出场信号

        包含三种出场逻辑：
        1. 硬止损（Hard Stop）：亏损 1%
        2. 追踪止盈（Trailing Stop）：最高点回撤 0.5%
        3. 时间止损（Time Stop）：持仓超过 15 秒且浮盈 < 0.1%

        Args:
            current_price (float): 当前价格
            timestamp (int): 当前时间戳（毫秒）
        """
        # 前置检查：无持仓直接返回
        if self.current_position == 0:
            return

        # 前置检查：缺少开仓信息
        if self.entry_price is None or self.entry_time is None:
            logger.warning("⚠️  缺少开仓信息，跳过出场检查")
            return

        # 更新最高价（用于追踪止盈）
        if self.highest_price is None or current_price > self.highest_price:
            self.highest_price = current_price
            logger.debug(f"📈 更新最高价: {self.highest_price}")

        # 计算当前盈亏
        pnl_pct = (current_price - self.entry_price) / self.entry_price

        # 计算持仓时间（秒）
        hold_time_seconds = (timestamp - self.entry_time) / 1000.0

        # 逻辑 A - 硬止损（Hard Stop）
        # 触发条件：亏损 1%
        if current_price < self.entry_price * 0.99:
            logger.warning(
                f"🛑 硬止损触发: entry={self.entry_price:.2f}, "
                f"current={current_price:.2f}, loss={pnl_pct*100:.2f}%"
            )
            await self._execute_exit("hard_stop")
            return

        # 逻辑 B - 追踪止盈（Trailing Stop）
        # 触发条件：最高点回撤 0.5% 且当前盈利
        if (self.highest_price is not None and
            current_price < self.highest_price * 0.995 and
            current_price > self.entry_price):

            highest_pnl_pct = (self.highest_price - self.entry_price) / self.entry_price
            logger.warning(
                f"📉 追踪止盈触发: highest={self.highest_price:.2f}, "
                f"current={current_price:.2f}, drawdown=0.5%, "
                f"max_pnl={highest_pnl_pct*100:.2f}%"
            )
            await self._execute_exit("trailing_stop")
            return

        # 逻辑 C - 时间止损（Time Stop）
        # 触发条件：持仓超过 15 秒且浮盈 < 0.1%
        if hold_time_seconds > 15 and pnl_pct < 0.001:
            logger.warning(
                f"⏰ 时间止损触发: hold_time={hold_time_seconds:.1f}s, "
                f"pnl={pnl_pct*100:.2f}% (<0.1%)"
            )
            await self._execute_exit("time_stop")
            return

    async def _execute_exit(self, exit_type: str):
        """
        [新增] 执行平仓

        Args:
            exit_type (str): 出场类型（hard_stop, trailing_stop, time_stop）
        """
        try:
            # 使用市价单平仓（立即成交）
            size = abs(self.current_position)  # 平仓数量（绝对值）

            logger.info(
                f"🔄 执行平仓: type={exit_type}, "
                f"symbol={self.symbol}, size={size}, "
                f"entry_price={self.entry_price}"
            )

            # 调用 executor 的 close_position 方法
            response = await self.executor.close_position(
                symbol=self.symbol,
                size=size,
                direction="sell"
            )

            logger.info(f"✅ 平仓完成: {response}")

            # 重置持仓状态
            self.current_position = 0.0
            self.entry_price = None
            self.entry_time = None
            self.highest_price = None

        except Exception as e:
            logger.error(f"❌ 平仓失败: {e}")

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

        # 🆕 [优先] 主动出场检查（在策略判断之前）
        await self._check_exit_signals(price, timestamp)

        # 🔥 调试日志：确认 on_tick 被调用
        logger.debug(f"Engine 收到 Tick: price={price}, size={size}, side={side}, timestamp={timestamp}")

        #1. 更新 EMA（每次 Tick 都更新）
        self.ema_fast = self._calculate_ema(price, self.ema_fast, self.ema_fast_period)
        self.ema_slow = self._calculate_ema(price, self.ema_slow, self.ema_slow_period)

        if self.tick_count % 1000 == 0:  # 🔥 性能优化：改为每 1000 个 tick 记录一次
            logger.info(
                f"Tick #{self.tick_count}: price={price}, "
                f"ema_fast={self.ema_fast}, ema_slow={self.ema_slow}"
            )

        #2. 更新阻力位
        self._update_resistance(price)

        # 🆕 [修复版] 持仓同步逻辑 (先更新时间戳，防止死循环)
        current_ts = time.time()
        # 🔥 [改造] 低频校准机制：60 秒校准一次（而非 5 秒）
        # WebSocket 推送作为主数据源，REST API 用于长期一致性校准
        if current_ts - self.last_sync_time > 60.0:
            # 关键：先更新时间，无论后续成功与否，都强制冷却 60 秒
            self.last_sync_time = current_ts

            # 使用 create_task 异步执行，完全不阻塞 Tick 处理
            asyncio.create_task(self._safe_update_position())

        #3. 秃鹫模式：闪崩接针
        if self.mode in ["hybrid", "vulture"]:
            if self.ema_fast is not None:
                await self._vulture_strategy(price, self.ema_fast)

        #4. 狙击模式：大单追涨
        if self.mode in ["hybrid", "sniper"]:
            await self._sniper_strategy(price, timestamp)

    async def update_position_state(self, positions: list):
        """
        [改造] 从私有 WebSocket 推送更新持仓状态（主数据源）

        数据流治理：
        - WebSocket 推送作为主数据源（实时更新）
        - REST API 用于 60 秒周期性校准
        - 如果两者不一致，REST API 会覆盖 WebSocket 状态

        Args:
            positions (list): 持仓数据列表
        """
        if not positions:
            self.current_position = 0.0
            self.entry_price = None
            self.entry_time = None
            logger.debug("📡 [WebSocket 主数据源] 持仓推送: 无持仓")
            return

        # 只取当前交易对的持仓
        for pos in positions:
            if pos.get('instId') == self.symbol:
                # 更新持仓量（兼容字符串）
                pos_val = pos.get('pos', '0')
                self.current_position = float(pos_val) if isinstance(pos_val, str) else float(pos_val)

                # 更新开仓均价
                avg_px = pos.get('avgPx')
                self.entry_price = float(avg_px) if avg_px else None

                # 更新开仓时间
                c_time = pos.get('cTime')
                self.entry_time = int(c_time) if c_time else None

                logger.info(
                    f"📡 [WebSocket 主数据源] 持仓更新: symbol={self.symbol}, "
                    f"pos={self.current_position}, avgPx={self.entry_price}, "
                    f"entryTime={self.entry_time}"
                )
                return

        # 如果没找到当前交易对的持仓
        self.current_position = 0.0
        self.entry_price = None
        self.entry_time = None
        logger.debug(f"📡 [WebSocket 主数据源] 持仓推送: {self.symbol} 无持仓")

    async def _safe_update_position(self):
        """
        [改造] 安全的异步持仓更新 - 低频校准机制

        数据流治理：
        - WebSocket 推送作为主数据源（实时）
        - REST API 查询结果用于覆盖 WebSocket 的状态（如果两者不一致，以 REST 为准）
        - 确保 60 秒周期性的数据一致性校准

        执行频率：每 60 秒一次（低频校准）
        """
        try:
            # 1. 保存 WebSocket 推送的值（用于对比）
            ws_position = self.current_position
            ws_entry_price = self.entry_price
            ws_entry_time = self.entry_time

            # 2. 查询 REST API（校准数据源）
            positions = await self.executor.get_positions(self.symbol)

            if positions:
                # 兼容直接返回列表的情况
                pos_data = positions[0] if isinstance(positions, list) else positions.get('data', [{}])[0]

                # 获取 REST API 的持仓数据
                rest_position = float(pos_data.get('pos', 0.0))
                rest_avg_px = pos_data.get('avgPx')
                rest_entry_price = float(rest_avg_px) if rest_avg_px else None
                rest_c_time = pos_data.get('cTime')
                rest_entry_time = int(rest_c_time) if rest_c_time else None

                # 3. 数据一致性校验
                # 比较 WebSocket 和 REST API 的持仓量
                if abs(ws_position - rest_position) > 0.001:  # 浮点数比较
                    logger.warning(
                        f"🔧 [校准] 持仓不一致: "
                        f"WebSocket={ws_position}, REST={rest_position}, "
                        f"以 REST 为准，更新持仓状态"
                    )

                    # 以 REST 为准，覆盖 WebSocket 的状态
                    self.current_position = rest_position
                    self.entry_price = rest_entry_price
                    self.entry_time = rest_entry_time

                    # 重新初始化最高价
                    if rest_position > 0 and rest_entry_price:
                        self.highest_price = rest_entry_price
                    else:
                        self.highest_price = None
                else:
                    # 数据一致，静默通过
                    logger.debug(
                        f"✅ [校准] 持仓一致: WebSocket={ws_position}, REST={rest_position}"
                    )
            else:
                # REST API 返回无持仓
                if ws_position != 0:
                    logger.warning(
                        f"🔧 [校准] WebSocket 显示有持仓 ({ws_position})，但 REST 显示无持仓，"
                        f"以 REST 为准，清空持仓状态"
                    )
                    self.current_position = 0.0
                    self.entry_price = None
                    self.entry_time = None
                    self.highest_price = None
                else:
                    # 都是无持仓，一致
                    logger.debug("✅ [校准] 持仓一致: 无持仓")

        except Exception as e:
            # 发生 401 或网络错误时，保持 WebSocket 状态
            logger.error(f"❌ [校准] REST API 查询失败，保持 WebSocket 状态: {e}")
            pass

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
        self.tick_count = 0
