"""
ScalperV1 Micro-Reversion Sniper Strategy (V2 - Refactored)

基于组件架构的重构版本：
- 控制器模式：ScalperV1 类作为控制器，调用组件方法
- 信号生成：SignalGenerator 负责 EMA、Imbalance、Spread 计算
- 执行算法：ExecutionAlgo 负责挂单价格、插队逻辑、模拟盘适配
- 状态管理：StateManager 负责持仓、订单、冷却、自愈逻辑

策略核心逻辑（V2 - Micro-Reversion Sniper）:
1. 完全不看 K 线，只处理 on_tick (Trade Stream)
2. 趋势过滤：使用 EMA（50 ticks）判断趋势方向
3. 质量过滤：检查点差（< 0.05%）和流动性（> 5000 USDT）
4. 精准入场：
   - 仅做多模式
   - 趋势向上（Price > EMA）
   - 买卖失衡（买量 > 卖量 * 5.0）
   - 冷却检查通过
5. 智能退出：
   - 追踪止损（Trailing Stop）：0.1% 起动，回撤 0.05% 触发
   - 硬止损：1.0%
   - 时间止损：30 秒

优化特点：
- O(1) 时间复杂度：使用 deque 保存价格历史
- 零历史数据存储：不存储完整 K 线，只维护 100 个价格点
- 极速计算：每 tick 计算 EMA 和追踪止损
- 轻量级依赖：严禁使用 pandas，只使用原生 Python
- Maker 模式：开仓使用限价单，降低手续费
- 严格风控：保留所有安全机制（负持仓修复、冷却、TTL）

设计原则：
- 控制器（Controller）：只负责接收事件、调用组件方法、更新状态
- 组件（Components）：每个组件只负责一个功能领域
- 接口清晰：组件间通过清晰的接口通信
"""

import time
import asyncio
import logging
from typing import Dict, Any, Optional

from ...core.event_types import Event
from ...core.event_bus import EventBus
from ...oms.order_manager import OrderManager
from ...oms.capital_commander import CapitalCommander
from ...config.risk_profile import RiskProfile, StopLossType
from ...utils.volatility import VolatilityEstimator
from ..base_strategy import BaseStrategy

# 导入组件
from .components import SignalGenerator, ExecutionAlgo, StateManager
from .components.signal_generator import ScalperV1Config
from .components.execution_algo import ExecutionConfig

logger = logging.getLogger(__name__)


class ScalperV2(BaseStrategy):
    """
    ScalperV2 Micro-Reversion Sniper 策略

    基于组件架构的重构版本，使用独立的组件：
    - SignalGenerator: 信号生成（EMA、Imbalance、Spread）
    - ExecutionAlgo: 执行算法（挂单、插队、模拟盘适配）
    - StateManager: 状态管理（持仓、订单、冷却、自愈）

    设计原则：
    - 控制器（Controller）：只负责接收事件、调用组件方法、更新状态
    - 组件（Components）：每个组件只负责一个功能领域
    - 接口清晰：组件间通过清晰的接口通信
    """

    def __init__(
        self,
        event_bus: EventBus,
        order_manager: OrderManager,
        capital_commander: CapitalCommander,
        symbol: str = "DOGE-USDT-SWAP",
        imbalance_ratio: float = 5.0,
        min_flow_usdt: float = 5000.0,
        take_profit_pct: float = 0.002,
        stop_loss_pct: float = 0.01,
        time_limit_seconds: int = 30,
        position_size: Optional[float] = None,
        mode: str = "PRODUCTION",
        strategy_id: Optional[str] = None,
        cooldown_seconds: float = 0.1,
        maker_timeout_seconds: float = 3.0,
        # 容错参数（吃掉所有未定义的参数，防止崩溃）
        **kwargs
    ):
        """
        初始化 ScalperV1 策略（V2 - Refactored）

        Args:
            event_bus (EventBus): 事件总线
            order_manager (OrderManager): 订单管理器
            capital_commander (CapitalCommander): 资金指挥官
            symbol (str): 交易对
            imbalance_ratio (float): 买卖失衡比例（默认 5.0 = 买量是卖量的 5 倍）
            min_flow_usdt (float): 最小流速（USDT），过滤杂波（默认 5000）
            take_profit_pct (float): 止盈百分比（默认 0.002 = 0.2%，V2 使用追踪止损）
            stop_loss_pct (float): 硬止损百分比（默认 0.01 = 1%）
            time_limit_seconds (int): 时间止损（秒），默认 30 秒（V2 提高到 30）
            position_size (float): 仓位大小（None=基于风险计算）
            mode (str): 策略模式（PRODUCTION/DEV）
            strategy_id (str): 策略 ID
            cooldown_seconds (float): 交易冷却时间（秒）
        """
        super().__init__(
            event_bus=event_bus,
            order_manager=order_manager,
            capital_commander=capital_commander,
            symbol=symbol,
            mode=mode,
            strategy_id=strategy_id,
            cooldown_seconds=cooldown_seconds
        )

        # 容错：记录未识别的参数
        # 🔥 [修复] 这些参数通过 main.py 传递，不需要警告
        # 直接忽略 kwargs 即可
        pass

        # ========== 初始化组件 ==========

        # 1. 信号生成器配置
        signal_generator_config = ScalperV1Config(
            symbol=symbol,
            imbalance_ratio=imbalance_ratio,
            min_flow_usdt=min_flow_usdt,
            ema_period=50,
            spread_threshold_pct=0.0005  # 0.05%
        )
        self.signal_generator = SignalGenerator(signal_generator_config)

        # 2. 执行算法配置
        execution_config = ExecutionConfig(
            symbol=symbol,
            tick_size=0.0001,
            spread_threshold_pct=0.0005,
            is_paper_trading=False,  # 默认为实盘模式
            enable_chasing=True,
            min_chasing_distance_pct=0.0005,  # 0.05%
            max_chase_distance_pct=0.001,  # 0.1%
            min_order_life_seconds=2.0,
            aggressive_maker_spread_ticks=2.0,
            aggressive_maker_price_offset=1.0
        )
        self.execution_algo = ExecutionAlgo(execution_config)
        self.execution_config = execution_config  #  [修复] 保存为实例属性

        # 3. 状态管理器
        self.state_manager = StateManager(symbol)

        # ========== 保存配置为实例属性 ==========
        #  [修复] 创建 config 对象，保存所有配置参数
        self.config = type('Config', (), {
            'cooldown_seconds': cooldown_seconds,
            'position_size': position_size,
            'take_profit_pct': take_profit_pct,
            'stop_loss_pct': stop_loss_pct,
            'time_limit_seconds': time_limit_seconds
        })

        # ========== 保留的配置 ==========
        self.contract_val = 1.0  # 合约面值
        self.tick_size = 0.01  # Tick 大小
        self._instrument_synced = False
        self._start_time = 0.0
        self._orderbook_received = False

        # ========== 保留的变量 ==========
        self.vol_window_start = 0.0
        self.buy_vol = 0.0
        self.sell_vol = 0.0
        self._previous_price = 0.0

        logger.info(
            f"🚀 ScalperV2 初始化: symbol={symbol}, "
            f"imbalance_ratio={imbalance_ratio}, "
            f"min_flow={min_flow_usdt} USDT, "
            f"take_profit={take_profit_pct*100:.2f}%, "
            f"time_stop={time_limit_seconds}s"
        )

    def set_public_gateway(self, gateway):
        """
        注入公共网关（用于获取订单簿数据）

        Args:
            gateway: OkxPublicWsGateway 实例
        """
        self.public_gateway = gateway
        logger.info(f"公共网关已注入到策略 {self.strategy_id}")

    async def start(self):
        """
        策略启动
        """
        # 调用基类的 start 方法
        await super().start()

        # 记录启动时间
        self._start_time = time.time()

        # 同步 Instrument 详情
        await self._sync_instrument_details()

        logger.info(
            f"🚀 ScalperV2 启动: symbol={self.symbol}, "
            f"cooldown={self.config.cooldown_seconds}s, "
            f"mode=Sniper, "
            f"direction=LongOnly"
        )

    async def _sync_instrument_details(self):
        """
        同步 Instrument 详情（合约面值、Tick Size）
        """
        try:
            # 1. 检查是否有 REST gateway
            if not self._order_manager or not hasattr(self._order_manager, '_rest_gateway'):
                logger.error(
                    f"❌ [初始化] {self.symbol}: "
                    f"无法访问 REST gateway"
                )
                return

            rest_gateway = self._order_manager._rest_gateway

            # 2. 调用 Gateway 获取最新 Instrument 信息
            instrument = await rest_gateway.get_instrument_details(self.symbol)
            if not instrument:
                logger.error(f"❌ [初始化] {self.symbol}: 无法获取 Instrument 信息")
                return

            # OKX 返回的是列表或字典，兼容两种格式
            inst_data = instrument[0] if isinstance(instrument, list) else instrument

            # 3. 同步 Contract Value
            self.contract_val = float(inst_data.get('ctVal', 1.0))

            # 4. 同步 Tick Size
            self.tick_size = float(inst_data.get('tickSz', 0.01))

            # 5. 同步智能点差阈值
            # 🔥 [修复] 获取当前价格，优先使用 last，如果为 0 则尝试 markPrice 或 idxPx
            current_price_raw = inst_data.get('last') or inst_data.get('markPx') or inst_data.get('idxPx')

            # 🔥 [修复] 检查价格有效性（处理 None 和 0）
            if not current_price_raw or float(current_price_raw) <= 0:
                logger.warning(
                    f"⚠️ [配置警告] {self.symbol}: 无法获取当前价格 (last={inst_data.get('last')}, markPx={inst_data.get('markPx')}, idxPx={inst_data.get('idxPx')})，使用默认点差阈值"
                )
                # 使用配置文件的默认点差阈值（不使用 AutoSpread）
                final_spread = self.signal_generator.config.spread_threshold_pct
                # 🔥 [修复] 保持初始化时的 tick_size（0.1），不被覆盖
                logger.info(
                    f"✅ [智能配置] {self.symbol}: "
                    f"ctVal={self.contract_val}, "
                    f"TickSize={self.tick_size:.6f} (使用初始化值), "
                    f"Spread=Config({self.signal_generator.config.spread_threshold_pct:.4%})"
                )
            else:
                current_price = float(current_price_raw)

                # 🔥 [修复] tick_size 已经是正确的值（0.1），直接使用
                auto_spread = self.tick_size * 20  # 允许 20 跳的价差
                auto_spread_pct = auto_spread / current_price

                # 混合策略：取 Config 和 Auto 的最大值
                final_spread = max(self.signal_generator.config.spread_threshold_pct, auto_spread_pct)

                logger.info(
                    f"✅ [智能配置] {self.symbol}: "
                    f"ctVal={self.contract_val}, "
                    f"TickSize={self.tick_size:.6f}, "
                    f"AutoSpread={final_spread:.4%} (current_price={current_price:.2f})"
                )

            # 更新配置
            self.execution_config = ExecutionConfig(
                symbol=self.symbol,
                tick_size=self.tick_size,
                spread_threshold_pct=final_spread,
                is_paper_trading=self.execution_config.is_paper_trading,
                enable_chasing=self.execution_config.enable_chasing,
                min_chasing_distance_pct=self.execution_config.min_chasing_distance_pct,
                max_chase_distance_pct=self.execution_config.max_chase_distance_pct,
                min_order_life_seconds=self.execution_config.min_order_life_seconds,
                aggressive_maker_spread_ticks=self.execution_config.aggressive_maker_spread_ticks,
                aggressive_maker_price_offset=self.execution_config.aggressive_maker_price_offset
            )
            self.execution_algo = ExecutionAlgo(self.execution_config)

        except Exception as e:
            logger.error(
                f"❌ [初始化失败] 同步 Instrument 详情出错: {e}", exc_info=True
            )
            # 出错时的保守回退
            self.contract_val = 1.0
            self.tick_size = 0.01

    async def on_tick(self, event: Event):
        """
        处理 Tick 事件（策略核心逻辑 - 控制器模式）

        设计原则：
        - 控制器只负责接收事件、调用组件方法、更新状态
        - 不直接实现信号生成或执行逻辑
        - 所有业务逻辑都委托给组件

        Args:
            event (Event): TICK 事件
        """
        try:
            # 1. 解析 Tick 数据
            tick = event.data
            now = time.time()

            # 提取基础数据
            symbol = tick.get('symbol')
            price = float(tick.get('price', 0))
            size = float(tick.get('size', 0))
            side = tick.get('side', '').lower()

            # 计算交易价值
            usdt_val = price * size * self.contract_val

            # 检查交易对是否匹配
            if symbol != self.symbol:
                return

            # 2. 状态检查 - 全局冷却
            if self.state_manager.is_in_global_cooldown(self.config.cooldown_seconds):
                return

            # 3. 状态检查 - 持仓状态
            is_open = self.state_manager.is_position_open()
            local_pos_size = self.state_manager.get_local_pos_size()

            # 4. 更新成交量窗口
            # 🔥 [修复] 扩大时间窗口到 3 秒，更容易累积成交量
            if now - self.vol_window_start >= 3.0:
                self.vol_window_start = now
                self.buy_vol = 0.0
                self.sell_vol = 0.0

            # 累加成交量
            if side == 'buy':
                self.buy_vol += usdt_val
            elif side == 'sell':
                self.sell_vol += usdt_val

            # 5. 根据持仓状态决定执行路径
            if is_open:
                # 有持仓：检查退出条件
                total_vol = self.buy_vol + self.sell_vol

                # 调用状态管理器更新退出时间
                self.state_manager.update_close_time()

                # 检查挂单插队（如果有挂单）
                if self.state_manager.has_active_maker_order():
                    order_age = self.state_manager.get_maker_order_age()
                    await self._check_chasing_conditions(price, now, order_age)

            else:
                # 无持仓：检查入场条件
                total_vol = self.buy_vol + self.sell_vol

                # 使用信号生成器计算信号（带成交量）
                signal = self.signal_generator.compute_with_volumes(
                    symbol=symbol,
                    price=price,
                    buy_vol=self.buy_vol,
                    sell_vol=self.sell_vol,
                    total_vol=total_vol
                )

                # 🔥 [新增] 记录满足所有条件的大机会日志
                # 条件1：单笔金额 >= 100万 USDT（使用 SCALPER_MIN_FLOW）
                # 条件2：总量 >= 流量阈值
                # 条件3：趋势向上（Price > EMA）
                # 条件4：买卖失衡 >= 3倍
                if (usdt_val >= self.signal_generator.config.min_flow_usdt and
                    total_vol >= self.signal_generator.config.min_flow_usdt and
                    signal.is_valid and
                    signal.direction == 'bullish'):

                    imbalance_ratio = signal.imbalance_ratio
                    ema_value = signal.ema_value

                    logger.info(
                        f"🎯 [大机会] {self.symbol}: "
                        f"{side} {size:.4f} @ {price:.4f} = {usdt_val:,.0f} USDT | "
                        f"总量={total_vol:,.0f} USDT | "
                        f"失衡={imbalance_ratio:.2f}x | "
                        f"趋势=看涨 (Price>{ema_value:.4f})"
                    )

                # 如果信号有效，执行入场逻辑
                if signal.is_valid:
                    # 检查点差和 OrderBook 数据
                    best_bid, best_ask = self._get_order_book_best_prices(price)

                    # 如果 OrderBook 数据不可用，跳过本次开仓
                    if best_bid <= 0 or best_ask <= 0:
                        logger.warning("订单簿数据不可用，跳过本次开仓")
                        return

                    # 计算止损价格
                    stop_loss_price = self._calculate_stop_loss(price)

                    # 检查风控：计算仓位
                    if self.config.position_size is not None:
                        trade_size = max(1, int(self.config.position_size))
                        logger.debug(f"使用固定仓位: {trade_size}")
                    else:
                        # 基于风险计算仓位
                        trade_size = self._capital_commander.calculate_safe_quantity(
                            symbol=self.symbol,
                            entry_price=best_bid,  # 临时使用，后面会重新计算
                            stop_loss_price=stop_loss_price,
                            strategy_id=self.strategy_id,
                            contract_val=self.contract_val
                        )

                        # 如果风控返回 0 或负数，直接跳过开仓
                        if trade_size <= 0:
                            logger.warning(
                                f"🚫 [风控拒绝] {self.symbol}: "
                                f"计算仓位={trade_size:.4f} ≤ 0，跳过本次开仓"
                            )
                            return

                        trade_size = max(1, int(trade_size))
                        logger.debug(f"基于风险计算仓位: {trade_size}")

                    # 使用执行算法计算挂单价格
                    decision = self.execution_algo.calculate_maker_price(
                        side='buy',
                        best_bid=best_bid,
                        best_ask=best_ask,
                        order_age=0.0
                    )

                    # 提交挂单
                    success = await self._place_maker_order(
                        symbol=symbol,
                        price=decision.price,
                        stop_loss_price=stop_loss_price,
                        size=trade_size,
                        contract_val=self.contract_val
                    )

                    if success:
                        logger.info(
                            f"✅ [狙击挂单已提交] {self.symbol} @ {decision.price:.6f}, "
                            f"数量={trade_size}, 止损={stop_loss_price:.6f}, "
                            f"策略={decision.reason}"
                        )

        except Exception as e:
            logger.error(f"处理 Tick 事件失败: {e}", exc_info=True)

    async def on_order_filled(self, event: Event):
        """
        处理订单成交事件

        Args:
            event (Event): ORDER_FILLED 事件
        """
        try:
            data = event.data
            side = data.get('side', '').lower()
            filled_size = float(data.get('filled_size', 0))

            # 根据订单类型分发处理
            if side == 'buy':
                # 开仓成交：更新持仓状态
                entry_price = float(data.get('price', 0))
                self.state_manager.update_position(
                    size=filled_size,
                    entry_price=entry_price,
                    entry_time=time.time()
                )
                logger.info(f"✅ [开仓成交] {self.symbol}: 解锁开仓锁")
            elif side == 'sell':
                # 平仓成交：更新持仓状态并检查是否完全平仓
                self.state_manager.update_position(
                    size=-filled_size,  # 平仓减少持仓
                    entry_price=0.0,
                    entry_time=0.0
                )
                logger.info(f"✅ [平仓成交] {self.symbol}: 数量={filled_size}")

                if self.state_manager.is_position_closed():
                    await self._reset_position_state()

        except Exception as e:
            logger.error(f"处理订单成交事件失败: {e}", exc_info=True)

    async def _place_maker_order(
        self,
        symbol: str,
        price: float,
        stop_loss_price: float,
        size: float,
        contract_val: float = 1.0
    ) -> bool:
        """
        下 Maker 挂单（限价单）

        Args:
            symbol (str): 交易对
            price (float): 挂单价格
            stop_loss_price (float): 止损价格
            size (float): 数量
            contract_val (float): 合约面值

        Returns:
            bool: 下单是否成功
        """
        try:
            # 检查开仓锁
            if self.state_manager.has_active_maker_order():
                logger.debug(
                    f"🚫 [风控拦截] {self.symbol}: "
                    f"上一个开仓请求尚未结束，拒绝重复开仓"
                )
                return False

            # 计算实际下单价值
            order_value = price * size * contract_val
            logger.info(
                f"🚀 [尝试下单] {symbol} buy {size} 张 @ {price} "
                f"(价值: {order_value:.2f} USDT, ctVal={contract_val})"
            )

            # 下单
            success = await self.buy(
                symbol=symbol,
                entry_price=price,
                stop_loss_price=stop_loss_price,
                order_type='limit',
                size=size
            )

            if success:
                # 更新订单状态
                self.state_manager.set_maker_order(
                    order_id="pending",
                    price=price,
                    initial_price=price
                )
            else:
                logger.warning(f"🚫 [开仓失败] {self.symbol}: 下单失败，已重置开仓锁")

            return success
        except Exception as e:
            logger.error(f"❌ [Maker 挂单失败] {self.symbol}: 下单失败: {str(e)}")
            return False

    async def _check_chasing_conditions(
        self,
        current_price: float,
        now: float,
        order_age: float
    ):
        """
        检查追单条件（委托给执行算法）

        Args:
            current_price (float): 当前价格
            now (float): 当前时间戳
            order_age (float): 订单存活时间（秒）
        """
        try:
            # 获取当前挂单信息
            current_maker_price = self.state_manager.get_maker_order_price()
            maker_order_id = self.state_manager.get_maker_order_id()

            # 调用执行算法判断是否应该追单
            should_chase = self.execution_algo.should_chase(
                current_maker_price=current_maker_price,
                current_price=current_price,
                order_age=order_age
            )

            # 如果应该追单，执行插队逻辑
            if should_chase:
                logger.info(
                    f"🔄 [插队触发] {self.symbol}: "
                    f"原价格={current_maker_price:.6f}, "
                    f"新价格={current_price:.6f}"
                )
                await self._cancel_maker_order()
                await asyncio.sleep(0.1)

            # 重新计算挂单价格
            best_bid, best_ask = self._get_order_book_best_prices(current_price)
            if best_bid <= 0 or best_ask <= 0:
                logger.debug(f"🛑 [追单跳过] {self.symbol}: 订单簿数据无效")
                return

            decision = self.execution_algo.calculate_maker_price(
                side='buy',
                best_bid=best_bid,
                best_ask=best_ask,
                order_age=0.0
            )

            # 计算止损价格
            stop_loss_price = self._calculate_stop_loss(current_price)

            # 计算交易数量
            if self.config.position_size is not None:
                trade_size = max(1, int(self.config.position_size))
            else:
                trade_size = self._capital_commander.calculate_safe_quantity(
                    symbol=self.symbol,
                    entry_price=decision.price,
                    stop_loss_price=stop_loss_price,
                    strategy_id=self.strategy_id,
                    contract_val=self.contract_val
                )
                trade_size = max(1, int(trade_size))

            # 重新提交挂单
            success = await self._place_maker_order(
                symbol=self.symbol,
                price=decision.price,
                stop_loss_price=stop_loss_price,
                size=trade_size,
                contract_val=self.contract_val
            )

            if success:
                logger.info(
                    f"✅ [插队成功] {self.symbol} @ {decision.price:.6f}, "
                    f"数量={trade_size}, 止损={stop_loss_price:.6f}"
                )

        except Exception as e:
            logger.error(f"检查追单条件失败: {e}", exc_info=True)

    def _get_order_book_best_prices(self, current_price: float = 0.0) -> tuple:
        """
        获取订单簿最优买卖价（带降级策略）

        Args:
            current_price (float): 当前 Tick 的最新成交价（用于降级策略）

        Returns:
            tuple: (best_bid, best_ask)
        """
        try:
            # 检查是否已收到 OrderBook 数据
            if not self._orderbook_received:
                # 未收到 OrderBook 数据，降级使用 Last Price
                if current_price > 0:
                    logger.debug(
                        f"⚠️ [降级策略] {self.symbol}: "
                        f"订单簿数据不可用，使用 Last Price={current_price:.6f}"
                    )
                    return (current_price, current_price)
                else:
                    return (0.0, 0.0)

            # 已收到 OrderBook 数据，从公共网关获取
            if hasattr(self, 'public_gateway') and self.public_gateway:
                best_bid, best_ask = self.public_gateway.get_best_bid_ask()
                return (best_bid, best_ask)
            else:
                return (0.0, 0.0)

        except Exception as e:
            logger.error(f"获取订单簿价格失败: {e}", exc_info=True)
            return (0.0, 0.0)

    def _calculate_stop_loss(self, entry_price: float) -> float:
        """
        计算止损价格

        Args:
            entry_price (float): 入场价格

        Returns:
            float: 止损价格
        """
        # 基于波动率计算止损（简化版）
        stop_distance = entry_price * 0.01  # 1% 止损
        stop_loss = entry_price - stop_distance
        return stop_loss

    async def _reset_position_state(self):
        """
        重置持仓状态（平仓后）
        """
        # 重置持仓状态
        self.state_manager.close_position()

        # 重置订单状态
        self.state_manager.clear_maker_order()

        # 重置冷却状态
        self.state_manager.reset_cooldown()

        logger.info(f"✅ [持仓归零] {self.symbol}: 平仓完成，重置状态")

    async def on_order_cancelled(self, event: Event):
        """
        处理订单取消事件（解锁开仓锁）

        Args:
            event (Event): ORDER_CANCELLED 事件
        """
        try:
            data = event.data
            symbol = data.get('symbol', '')

            if symbol != self.symbol:
                return

            if self.state_manager.has_active_maker_order():
                logger.warning(f"🚫 [开仓失败] {self.symbol}: 订单被取消，解锁开仓锁")
                self.state_manager.clear_maker_order()
        except Exception as e:
            logger.error(f"处理订单取消事件失败: {e}", exc_info=True)

    async def on_signal(self, signal: Dict[str, Any]):
        """
        处理策略信号（ScalperV1 不使用此方法）

        Args:
            signal (dict): 策略信号
        """
        pass

    async def on_event(self, event: Event):
        """
        处理通用事件（监听 OrderBook 更新）

        Args:
            event (Event): 通用事件
        """
        try:
            from ...core.event_types import EventType

            # 监听 OrderBook 更新事件
            if event.type == EventType.ORDERBOOK_UPDATED:
                logger.debug(
                    f"📊 [OrderBook Updated] {self.symbol}: "
                    f"收到订单簿更新事件"
                )
                # 标记已接收
                self._orderbook_received = True
            elif event.type == EventType.ORDERBOOK_SNAPSHOT:
                logger.debug(
                    f"📊 [OrderBook Snapshot] {self.symbol}: "
                    f"收到订单簿快照事件"
                )
            else:
                logger.debug(
                    f"🔔 [Event Ignore] {self.symbol}: "
                    f"忽略事件类型={event.type}"
                )
        except Exception as e:
            logger.error(f"处理事件失败: {e}", exc_info=True)

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取策略统计信息

        Returns:
            dict: 统计数据
        """
        # 基础统计
        base_stats = super().get_statistics()

        # 胜率计算
        position_state = self.state_manager.get_position()
        total_trades = 0  # 简化版，暂不统计
        win_rate = 0.0

        base_stats.update({
            'strategy': 'ScalperV2',
            'mode': 'Sniper',
            'version': '2.0',
            'architecture': 'Controller-Components',
            'symbol': self.symbol,
            'is_position_open': position_state.is_open,
            'position_size': position_state.size,
            'has_maker_order': self.state_manager.has_active_maker_order(),
            'signal_generator': self.signal_generator.get_state(),
            'execution_algo': self.execution_algo.get_state(),
            'state_manager': self.state_manager.get_full_state()
        })

        return base_stats

    def update_config(self, **kwargs):
        """
        更新策略配置

        Args:
            **kwargs: 配置参数
        """
        if 'imbalance_ratio' in kwargs:
            self.signal_generator_config.imbalance_ratio = kwargs['imbalance_ratio']
            self.signal_generator = SignalGenerator(self.signal_generator_config)
            logger.info(f"imbalance_ratio 更新为 {kwargs['imbalance_ratio']:.2f}")

        if 'min_flow_usdt' in kwargs:
            self.signal_generator_config.min_flow_usdt = kwargs['min_flow_usdt']
            self.signal_generator = SignalGenerator(self.signal_generator_config)
            logger.info(f"min_flow_usdt 更新为 {kwargs['min_flow_usdt']:.0f} USDT")

        if 'is_paper_trading' in kwargs:
            self.execution_config.is_paper_trading = kwargs['is_paper_trading']
            self.execution_algo = ExecutionAlgo(self.execution_config)
            logger.info(f"is_paper_trading 更新为 {kwargs['is_paper_trading']}")

        # 更新更多配置...
        # （这里可以根据需要继续添加）

    def reset_statistics(self):
        """重置统计信息"""
        logger.info(f"重置统计信息: {self.symbol}")

    def reset_state(self):
        """重置策略状态（包括持仓）"""
        # 重置成交量窗口
        self.vol_window_start = 0.0
        self.buy_vol = 0.0
        self.sell_vol = 0.0

        # 重置状态
        self.state_manager.reset_all()

        # 重置订单簿接收标志
        self._orderbook_received = False

        logger.info(f"ScalperV2 状态已完全重置: {self.symbol}")

    # ========== 测试辅助方法 ==========
    # 这些方法仅供测试使用，用于设置组件状态

    def _set_price_history_for_testing(self, prices: list):
        """
        设置价格历史（仅用于测试）

        Args:
            prices (list): 价格列表
        """
        import collections
        self.signal_generator.price_history = collections.deque(prices, maxlen=100)
        # 重新计算 EMA
        if len(prices) >= self.signal_generator.config.ema_period:
            recent_prices = prices[-self.signal_generator.config.ema_period:]
            self.signal_generator.ema_value = sum(recent_prices) / len(recent_prices)

    def _get_ema_value(self) -> float:
        """
        获取当前 EMA 值（仅用于测试）

        Returns:
            float: EMA 值
        """
        return self.signal_generator.ema_value

    def _set_ema_value(self, value: float):
        """
        设置 EMA 值（仅用于测试）

        Args:
            value (float): EMA 值
        """
        self.signal_generator.ema_value = value
