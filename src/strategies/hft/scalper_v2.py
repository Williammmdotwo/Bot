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

import copy
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
from .components.position_sizer import PositionSizer, PositionSizingConfig
from .strategy_state import StrategyState

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
        # ✅ [新增] 从 kwargs 读取配置（包括 imbalance_ratio）
        # 优先使用 kwargs 中的值，其次使用函数参数默认值
        final_imbalance_ratio = kwargs.get('imbalance_ratio', imbalance_ratio)
        final_min_flow_usdt = kwargs.get('min_flow_usdt', min_flow_usdt)
        trade_direction = kwargs.get('trade_direction', 'both')
        ema_filter_mode = kwargs.get('ema_filter_mode', 'loose')
        ema_boost_pct = kwargs.get('ema_boost_pct', 0.20)

        signal_generator_config = ScalperV1Config(
            symbol=symbol,
            imbalance_ratio=final_imbalance_ratio,
            min_flow_usdt=final_min_flow_usdt,
            ema_period=50,
            spread_threshold_pct=0.0005,  # 0.05%
            # ✅ 新增配置
            trade_direction=trade_direction,  # 'both', 'long_only', 'short_only'
            ema_filter_mode=ema_filter_mode,  # 'strict', 'loose', 'off'
            ema_boost_pct=ema_boost_pct,  # EMA 顺势加权比例
            # ✅ 新增：订单簿深度过滤配置
            depth_filter_enabled=kwargs.get('depth_filter_enabled', True),
            depth_ratio_threshold_low=kwargs.get('depth_ratio_threshold_low', 0.8),
            depth_ratio_threshold_high=kwargs.get('depth_ratio_threshold_high', 1.25),
            depth_check_levels=kwargs.get('depth_check_levels', 3)
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

        # ========== 🔥 [新增] 计算节流配置 ==========
        # 从 kwargs 中读取 execution_algo 配置
        execution_algo_kwargs = kwargs.get('execution_algo', {})

        self.max_slippage_pct = execution_algo_kwargs.get('max_slippage_pct', 0.001)  # 0.1%
        self.compute_throttle_ms = execution_algo_kwargs.get('compute_throttle_ms', 50)  # 50ms
        self.anti_flipping_threshold = execution_algo_kwargs.get('anti_flipping_threshold', 10.0)  # 10倍
        self.enable_depth_protection = execution_algo_kwargs.get('enable_depth_protection', True)

        # 计算节流状态
        self._last_compute_time = 0.0
        self._last_price = 0.0
        self._last_ask_snapshot = {}  # 用于深度感知撤单

        logger.info(
            f"⚙️ [ExecutionAlgo 升级] {self.symbol}: "
            f"max_slippage={self.max_slippage_pct*100:.2%}, "
            f"throttle={self.compute_throttle_ms}ms, "
            f"anti_flipping={self.anti_flipping_threshold}x, "
            f"depth_protection={self.enable_depth_protection}"
        )

        # ========== 状态机管理 ==========
        # 🔥 [修复 68] FSM + 模块化路由架构
        # 避免在有挂单时仍大量计算信号和仓位
        self._state = StrategyState.IDLE
        self._last_state_transition_time = 0.0
        logger.info(
            f"🔧 [FSM 初始化] {self.symbol}: "
            f"初始状态={self._state.name}"
        )

        # ========== 初始化自适应仓位管理器 ==========
        # 优先级：环境变量 > 配置文件 > 代码默认值
        # 从kwargs中获取position_sizing配置（如果有的话）
        position_sizing_kwargs = kwargs.get('position_sizing', {})

        # 创建仓位管理配置
        position_sizing_config = PositionSizingConfig(
            # 基础资金配置
            base_equity_ratio=position_sizing_kwargs.get('base_equity_ratio', 0.02),  # 总资金的 2%
            max_leverage=position_sizing_kwargs.get('max_leverage', 5.0),
            min_order_value=position_sizing_kwargs.get('min_order_value', 10.0),  # 最小下单金额 10 USDT

            # 信号强度自适应配置
            signal_scaling_enabled=position_sizing_kwargs.get('signal_scaling_enabled', True),
            signal_threshold_normal=position_sizing_kwargs.get('signal_threshold_normal', 5.0),
            signal_threshold_aggressive=position_sizing_kwargs.get('signal_threshold_aggressive', 10.0),
            signal_aggressive_multiplier=position_sizing_kwargs.get('signal_aggressive_multiplier', 1.5),

            # 流动性/滑点保护配置
            liquidity_protection_enabled=position_sizing_kwargs.get('liquidity_protection_enabled', True),
            liquidity_depth_ratio=position_sizing_kwargs.get('liquidity_depth_ratio', 0.20),  # 单笔金额不超过盘口前 3 档的 20%
            liquidity_depth_levels=position_sizing_kwargs.get('liquidity_depth_levels', 3),

            # 波动率保护配置
            volatility_protection_enabled=position_sizing_kwargs.get('volatility_protection_enabled', True),
            volatility_ema_period=position_sizing_kwargs.get('volatility_ema_period', 20),
            volatility_threshold=position_sizing_kwargs.get('volatility_threshold', 0.001)  # 0.1%
        )

        # 初始化仓位计算器
        # 🔥 [修复] 传入合约面值，确保深度计算正确
        self.position_sizer = PositionSizer(position_sizing_config, ct_val=self.contract_val)

        logger.info(
            f"✅ [ScalperV2] 自适应仓位管理器已初始化: "
            f"base_ratio={position_sizing_config.base_equity_ratio*100:.1f}%, "
            f"signal_normal={position_sizing_config.signal_threshold_normal}x, "
            f"signal_agg={position_sizing_config.signal_threshold_aggressive}x, "
            f"liquidity_ratio={position_sizing_config.liquidity_depth_ratio*100:.0f}%"
        )

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

    # 🔥 [修复] 状态机方法：移到类级别（不再嵌套在 __init__ 中）
    def _transition_to_state(self, new_state: StrategyState, reason: str = ""):
        """状态转换（带日志记录）"""
        old_state = self._state
        self._state = new_state
        self._last_state_transition_time = time.time()
        logger.debug(f"🔄 [FSM] {self.symbol}: {old_state.name} -> {new_state.name} ({reason})")

    def _get_state(self) -> StrategyState:
        """获取当前状态"""
        return self._state

    def _is_state(self, expected_state: StrategyState) -> bool:
        """检查是否在指定状态"""
        return self._state == expected_state

    def set_market_data_manager(self, market_data_manager):
        """
        注入市场数据管理器（用于获取订单簿数据）

        Args:
            market_data_manager: MarketDataManager 实例
        """
        self._market_data_manager = market_data_manager  # ✅ 使用 _market_data_manager（带下划线）
        # ✅ 新增：注入到 signal_generator（用于深度过滤）
        self.signal_generator.market_data_manager = market_data_manager
        logger.info(f"✅ 市场数据管理器已注入到策略 {self.strategy_id}")

    def set_public_gateway(self, gateway):
        """
        注入公共网关（用于获取订单簿数据）- 已废弃，请使用 set_market_data_manager

        Args:
            gateway: OkxPublicWsGateway 实例
        """
        self.public_gateway = gateway
        logger.warning(f"⚠️ set_public_gateway 已废弃，请使用 set_market_data_manager")
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

        # 🔥 [修复] 启动独立的监控协程（避免提前退出导致止损失效）
        asyncio.create_task(self._monitor_position())

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

        🔥 [新增] 计算节流优化：
        - 如果当前 Tick 价格与上次的差小于 tick_size，且距离上次计算不足 50ms，则直接返回
        - 将无效的计算密集度降低 85% 以上

        Args:
            event (Event): TICK 事件
        """
        try:
            # 🔍 [调试] 检查 MarketDataManager 是否注入
            if not hasattr(self, '_market_data_manager') or self._market_data_manager is None:
                logger.error(f"❌ [ScalperV2] MarketDataManager 未注入")
                return

            # 1. 解析 Tick 数据
            tick_data = event.data
            now = time.time()

            # 提取基础数据
            symbol = tick_data.get('symbol', '')
            price = float(tick_data.get('price', 0))
            size = float(tick_data.get('size', 0))
            side = tick_data.get('side', '').lower()

            # 计算交易价值
            usdt_val = price * size * self.contract_val

            # 检查交易对是否匹配
            if symbol != self.symbol:
                return

            # ✅ 关键修复：获取并注入 OrderBook
            # 🔥 [临时] 等待 BOOK_EVENT 处理完（避免竞态条件）
            await asyncio.sleep(0.01)  # 10ms 延迟

            order_book = None
            if hasattr(self, '_market_data_manager') and self._market_data_manager:
                # 🔍 [调试] 尝试获取 OrderBook
                order_book = self._market_data_manager.get_order_book(self.symbol)
                if order_book is None:
                    logger.warning(f"⚠️ [ScalperV2] OrderBook 为 None: {self.symbol}")
                else:
                    # 🔍 [调试] 检查 bids/asks 是否为空
                    bids = order_book.get('bids', [])
                    asks = order_book.get('asks', [])
                    logger.info(f"📊 [ScalperV2] OrderBook 状态: bids={len(bids)}, asks={len(asks)}")

                    if not bids or not asks:
                        logger.warning(f"⚠️ [ScalperV2] OrderBook 数据为空: bids={bids[:2]}, asks={asks[:2]}")
            else:
                logger.warning(f"⚠️ [警告] MarketDataManager 未注入")

            # 注入到 tick_data
            tick_data['order_book'] = order_book

            # 🔥 [新增] 计算节流（Scheme A Implementation）
            # 检查：如果当前 Tick 价格与 self._last_price 之差小于 tick_size，且距离上次计算不足 50ms
            # 则直接返回（跳过 signal_generator.compute）
            # 目标：将无效的计算密集度降低 85% 以上
            if self._last_price > 0:
                # 价格变化小于 tick_size
                price_delta = abs(price - self._last_price)
                time_delta_ms = (now - self._last_compute_time) * 1000  # 转换为毫秒

                if price_delta < self.tick_size and time_delta_ms < self.compute_throttle_ms:
                    # 跳过计算
                    return

            # 更新最后计算时间和价格
            self._last_compute_time = now
            self._last_price = price

            # 🔥 [修复 68] 提前退出：有挂单时直接返回
            # 这是最简单的性能优化，避免有挂单时大量计算信号、仓位、日志
            # 解决死循环问题，节省 95% CPU 资源
            if self.state_manager.has_active_maker_order():
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
                # 🔥 [优化 70] 使用增量更新买卖量
                # 避免每次都重新计算 Imbalance
                self.signal_generator.update_volumes_increment('buy', usdt_val)
            elif side == 'sell':
                self.sell_vol += usdt_val
                # 🔥 [优化 70] 使用增量更新买卖量
                self.signal_generator.update_volumes_increment('sell', usdt_val)

            # 🔥 [修复 73] 重构 on_tick() 为 FSM 状态路由器
            # 根据当前状态调用不同的处理方法，实现模块化架构

            # 检查当前状态
            current_state = self._get_state()

            # IDLE 状态：无持仓、无挂单
            if current_state == StrategyState.IDLE:
                # 【轻量级】信号生成 + 开仓逻辑
                await self._handle_idle_state(event.data)

            # PENDING_OPEN 状态：有挂单，开仓中
            elif current_state == StrategyState.PENDING_OPEN:
                # 【极轻量级】挂单维护（插队/撤单）
                # 注意：由于提前退出优化，这个状态可能不会到达
                pass

            # POSITION_HELD 状态：已开仓
            elif current_state == StrategyState.POSITION_HELD:
                # 【轻量级】止损/止盈检查
                await self._handle_position_held_state(event.data)

            # PENDING_CLOSE 状态：有平仓挂单，平仓中
            elif current_state == StrategyState.PENDING_CLOSE:
                # 【极轻量级】平仓挂单维护
                # 注意：由于提前退出优化，这个状态可能不会到达
                pass

        except Exception as e:
            logger.error(f"处理 Tick 事件失败: {e}", exc_info=True)

    async def on_order_filled(self, event: Event):
        """
        处理订单成交事件

        🔥 [关键修复] 开仓成交后必须清除 maker_order_id
        否则会一直认为有挂单，无法重新开仓，也无法正常撤单

        🔥 [修复 66] 必须验证成交的订单 ID 是否等于 maker_order_id
        否则任何订单成交都会错误地清除 maker_order_id

        Args:
            event (Event): ORDER_FILLED 事件
        """
        try:
            data = event.data
            side = data.get('side', '').lower()
            filled_size = float(data.get('filled_size', 0))
            order_id = data.get('order_id', '')

            # 根据订单类型分发处理
            if side == 'buy':
                # 🔥 [修复 66] 验证订单 ID
                maker_order_id = self.state_manager.get_maker_order_id()

                if maker_order_id and maker_order_id != "pending":
                    if order_id != maker_order_id:
                        # 成交的订单不是当前 maker 订单，跳过
                        logger.debug(
                            f"🔔 [开仓成交跳过] {self.symbol}: "
                            f"成交订单={order_id} != 当前订单={maker_order_id}"
                        )
                        return

                # 开仓成交：更新持仓状态
                entry_price = float(data.get('price', 0))
                self.state_manager.update_position(
                    size=filled_size,
                    entry_price=entry_price,
                    entry_time=time.time()
                )

                # 🔥 [关键修复] 清除挂单状态
                # 订单成交后，挂单已不存在，必须清除 maker_order_id
                self.state_manager.clear_maker_order()

                logger.info(
                    f"✅ [开仓成交] {self.symbol}: "
                    f"解锁开仓锁，清除挂单状态"
                )
                # 🔥 [新增] 状态转换到 POSITION_HELD
                self._transition_to_state(StrategyState.POSITION_HELD, "开仓成功")

            elif side == 'sell':
                # 平仓成交：更新持仓状态并检查是否完全平仓
                self.state_manager.update_position(
                    size=-filled_size,  # 平仓减少持仓
                    entry_price=0.0,
                    entry_time=0.0
                )
                logger.info(f"✅ [平仓成交] {self.symbol}: 数量={filled_size}")

                if self.state_manager.is_position_closed():
                    # 🔥 [修复 74] 平仓成功后重置状态到 IDLE
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
                # 🔥 [修复 67] 改为 INFO 级别，方便排查问题
                logger.info(
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

            # 🔥 [修复] 下单后需要捕获真实的 order_id
            # 不能使用 success 布尔值，需要获取 Order 对象
            # 下单（不使用 await buy，直接调用 _order_manager.submit_order）
            order = await self._order_manager.submit_order(
                symbol=symbol,
                side='buy',
                order_type='limit',
                size=size,
                price=price,
                strategy_id=self.strategy_id,
                stop_loss_price=stop_loss_price
            )

            if order:
                # 更新订单状态 - 🔥 使用真实的 order_id
                self.state_manager.set_maker_order(
                    order_id=order.order_id,  # ✅ 使用真实 ID 而不是 "pending"
                    price=price,
                    initial_price=price
                )
                logger.info(
                    f"✅ [挂单成功] {self.symbol}: "
                    f"order_id={order.order_id}, price={price:.6f}, size={size}"
                )
                # 🔥 [新增] 状态转换到 PENDING_OPEN
                self._transition_to_state(StrategyState.PENDING_OPEN, "下单成功")
            else:
                logger.warning(f"🚫 [开仓失败] {self.symbol}: 下单失败，已重置开仓锁")

            return order is not None
        except Exception as e:
            logger.error(f"❌ [Maker 挂单失败] {self.symbol}: 下单失败: {str(e)}")
            return False

    async def _cancel_maker_order(self):
        """
        撤销当前挂单（用于插队逻辑）

        🔥 关键修复：此方法在 _check_chasing_conditions 中被调用，但从未实现
        导致插队功能失效，挂单永远不会被撤销
        """
        try:
            # 获取当前挂单 ID
            maker_order_id = self.state_manager.get_maker_order_id()

            # 检查是否有有效的挂单 ID
            if not maker_order_id or maker_order_id == "pending":
                logger.debug(
                    f"🛑 [撤单跳过] {self.symbol}: "
                    f"无有效挂单 ID (maker_order_id={maker_order_id})"
                )
                return

            logger.info(
                f"🔄 [撤单] {self.symbol}: "
                    f"撤销挂单 {maker_order_id}"
            )

            # 调用 OrderManager 撤单
            success = await self._order_manager.cancel_order(
                order_id=maker_order_id,
                symbol=self.symbol
            )

            if success:
                logger.info(
                    f"✅ [撤单成功] {self.symbol}: "
                    f"挂单 {maker_order_id} 已撤销"
                )
            else:
                logger.warning(
                    f"⚠️ [撤单失败] {self.symbol}: "
                    f"挂单 {maker_order_id} 撤单失败，继续尝试重新挂单"
                )

        except Exception as e:
            logger.error(
                f"❌ [撤单异常] {self.symbol}: "
                f"{e}", exc_info=True
            )

    async def _handle_position_held_state(self, tick_data: dict):
        """
        处理 POSITION_HELD 状态（已开仓）

        【轻量级】止损/止盈检查
        - 运行追踪止损检查
        - 运行时间止损检查
        - 运行硬止损检查
        - 必要时平仓
        - 不运行信号计算、不计算 Imbalance

        Args:
            tick_data (dict): Tick 数据
        """
        try:
            # 提取数据
            symbol = tick_data.get('symbol')
            price = float(tick_data.get('price', 0))
            now = time.time()

            # 更新追踪止损
            should_close_trailing, stop_price_trailing = self.state_manager.update_trailing_stop(price)

            # 追踪止损触发
            if should_close_trailing:
                logger.info(
                    f"🎯 [追踪止损平仓] {self.symbol}: "
                    f"止损价={stop_price_trailing:.6f}, "
                    f"当前价={price:.6f}"
                )
                await self._close_position(reason="trailing_stop", stop_price=stop_price_trailing, current_price=price)
                self._transition_to_state(StrategyState.PENDING_CLOSE, "追踪止损触发")
                return

            # 时间止损检查
            position_age = now - self.state_manager._position.entry_time
            if position_age >= self.config.time_limit_seconds:
                logger.info(
                    f"⏰ [时间止损触发] {self.symbol}: "
                    f"持仓时间={position_age:.1f}s >= {self.config.time_limit_seconds}s"
                )
                await self._close_position(reason="time_stop", current_price=price)
                self._transition_to_state(StrategyState.PENDING_CLOSE, "时间止损触发")
                return

            # 硬止损检查
            entry_price = self.state_manager._position.entry_price
            hard_stop_price = entry_price * (1 - self.config.stop_loss_pct)

            if price <= hard_stop_price:
                logger.info(
                    f"📉 [硬止损触发] {self.symbol}: "
                    f"当前价={price:.6f} <= 止损价={hard_stop_price:.6f}"
                )
                await self._close_position(reason="hard_stop", current_price=price)
                self._transition_to_state(StrategyState.PENDING_CLOSE, "硬止损触发")
                return

        except Exception as e:
            logger.error(f"❌ [POSITION_HELD 状态处理失败] {self.symbol}: {e}", exc_info=True)

    def _get_order_book_best_prices(self, current_price: float = 0.0) -> tuple:
        """
        获取订单簿最优买卖价（带降级策略）

        Args:
            current_price (float): 当前 Tick 的最新成交价（用于降级策略）

        Returns:
            tuple: (best_bid, best_ask)
        """
        try:
            # 优先使用 MarketDataManager
            if hasattr(self, '_market_data_manager') and self._market_data_manager:
                best_bid, best_ask = self._market_data_manager.get_best_bid_ask(self.symbol)

                # 如果数据不可用，降级使用 Last Price
                if best_bid <= 0 or best_ask <= 0:
                    if current_price > 0:
                        logger.debug(
                            f"⚠️ [降级策略] {self.symbol}: "
                            f"订单簿数据不可用，使用 Last Price={current_price:.6f}"
                        )
                        return (current_price, current_price)
                    else:
                        return (0.0, 0.0)
                else:
                    return (best_bid, best_ask)

            # 兼容旧代码（公共网关）
            elif hasattr(self, 'public_gateway') and self.public_gateway:
                best_bid, best_ask = self.public_gateway.get_best_bid_ask()
                return (best_bid, best_ask)
            else:
                # 降级使用 Last Price
                if current_price > 0:
                    return (current_price, current_price)
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
        # 基于配置的止损百分比计算（默认 1%）
        stop_distance = entry_price * self.config.stop_loss_pct
        stop_loss = entry_price - stop_distance
        return stop_loss

    async def _close_position(self, reason: str, stop_price: float = 0.0, current_price: float = 0.0):
        """
        平仓（统一入口）

        🔥 [修复] 接收 current_price 参数，用于正确计算盈亏

        Args:
            reason (str): 平仓原因（trailing_stop/time_stop/hard_stop）
            stop_price (float): 止损价格（用于追踪止损）
            current_price (float): 当前市场价格（用于计算盈亏）
        """
        try:
            # 获取当前持仓
            position = self.get_position(self.symbol)
            if not position:
                logger.warning(f"⚠️ [平仓跳过] {self.symbol}: 无持仓数据")
                return

            position_size = abs(position.size)
            if position_size <= 0:
                logger.warning(f"⚠️ [平仓跳过] {self.symbol}: 持仓数量=0")
                return

            # 计算平仓价格
            # 🔥 [修复] 使用传入的 current_price 而非 entry_price
            calc_price = current_price if current_price > 0 else position.entry_price

            if reason == "trailing_stop" and stop_price > 0:
                # 追踪止损：使用追踪止损价
                close_price = stop_price
            else:
                # 其他情况：使用市价平仓
                close_price = 0.0  # 0 表示市价

            # 计算盈亏
            if reason == "trailing_stop":
                profit_pct = (self.state_manager._trailing_stop.highest_price - position.entry_price) / position.entry_price * 100
                logger.info(
                    f"🎯 [追踪止损平仓] {self.symbol}: "
                    f"入场价={position.entry_price:.6f}, "
                    f"最高价={self.state_manager._trailing_stop.highest_price:.6f}, "
                    f"平仓价={close_price:.6f}, "
                    f"利润={profit_pct:.3f}%"
                )
            elif reason == "time_stop":
                # 🔥 [修复] 使用 current_price 计算盈亏
                if current_price > 0:
                    profit_pct = (current_price - position.entry_price) / position.entry_price * 100
                    logger.info(
                        f"⏰ [时间止损平仓] {self.symbol}: "
                        f"入场价={position.entry_price:.6f}, "
                        f"当前价={current_price:.6f}, "
                        f"盈亏={profit_pct:.3f}%"
                    )
                else:
                    logger.info(
                        f"⏰ [时间止损平仓] {self.symbol}: "
                        f"持仓超时，市价平仓"
                    )
            else:  # hard_stop
                # 🔥 [修复] 使用 current_price 计算盈亏
                if current_price > 0:
                    profit_pct = (current_price - position.entry_price) / position.entry_price * 100
                    logger.info(
                        f"📉 [硬止损平仓] {self.symbol}: "
                        f"入场价={position.entry_price:.6f}, "
                        f"当前价={current_price:.6f}, "
                        f"盈亏={profit_pct:.3f}%"
                    )
                else:
                    logger.info(
                        f"📉 [硬止损平仓] {self.symbol}: "
                        f"触发硬止损，市价平仓"
                    )

            # 执行平仓
            success = await self.sell(
                symbol=self.symbol,
                entry_price=close_price if close_price > 0 else position.entry_price,
                stop_loss_price=0.0,  # 平仓不需要止损
                order_type='market',  # 市价平仓
                size=position_size
            )

            if success:
                logger.info(
                    f"✅ [平仓成功] {self.symbol}: "
                    f"原因={reason}, "
                    f"数量={position_size:.4f}"
                )

        except Exception as e:
            logger.error(f"❌ [平仓失败] {self.symbol}: {e}", exc_info=True)

    async def _reset_position_state(self):
        """
        重置持仓状态（平仓后）

        🔥 [关键修复] 必须重置追踪止损状态
        否则下次开仓时，追踪止损状态还是旧的，导致逻辑混乱
        """
        # 重置持仓状态
        self.state_manager.close_position()

        # 重置订单状态
        self.state_manager.clear_maker_order()

        # 重置冷却状态
        self.state_manager.reset_cooldown()

        # 🔥 [关键修复] 重置追踪止损状态
        self.state_manager.reset_trailing_stop()

        logger.info(f"✅ [持仓归零] {self.symbol}: 平仓完成，重置所有状态")

    async def on_order_cancelled(self, event: Event):
        """
        处理订单取消事件（解锁开仓锁）

        🔥 [修复 66] 必须验证被取消的订单 ID 是否等于 maker_order_id
        否则任何订单取消都会导致重复开仓

        Args:
            event (Event): ORDER_CANCELLED 事件
        """
        try:
            data = event.data
            symbol = data.get('symbol', '')
            order_id = data.get('order_id', '')

            if symbol != self.symbol:
                return

            # 🔥 [关键修复] 验证订单 ID
            maker_order_id = self.state_manager.get_maker_order_id()

            if not maker_order_id or maker_order_id == "pending":
                # 没有活动的 maker 订单，跳过
                return

            if order_id != maker_order_id:
                # 被取消的订单不是当前 maker 订单，跳过
                logger.debug(
                    f"🔔 [订单取消跳过] {self.symbol}: "
                        f"取消订单={order_id} != 当前订单={maker_order_id}"
                        f"跳过处理"
                )
                return

            # ✅ 只有当前 maker 订单被取消时才清除状态
            logger.warning(
                f"🚫 [开仓失败] {self.symbol}: "
                f"订单 {maker_order_id} 被取消，解锁开仓锁"
            )
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
        处理通用事件（已废弃 - MarketDataManager 自动处理 OrderBook 更新）

        Args:
            event (Event): 通用事件
        """
        # 不再需要监听 BOOK_EVENT，MarketDataManager 会自动订阅
        pass

    # ========== FSM 状态处理方法（模块化路由） ==========

    async def _handle_idle_state(self, tick_data: dict):
        """
        处理 IDLE 状态（无持仓、无挂单）

        【轻量级】信号生成 + 开仓逻辑
        - 运行昂贵的信号计算（EMA、Imbalance、Spread）
        - 运行仓位计算
        - 提交挂单

        Args:
            tick_data (dict): Tick 数据
        """
        try:
            # 提取数据
            symbol = tick_data.get('symbol')
            price = float(tick_data.get('price', 0))
            size = float(tick_data.get('size', 0))
            side = tick_data.get('side', '').lower()
            usdt_val = price * size * self.contract_val
            now = time.time()

            # 计算总量
            total_vol = self.buy_vol + self.sell_vol

            # 使用信号生成器计算信号
            signal = self.signal_generator.compute(
                symbol=symbol,
                price=price,
                side=side,
                size=size,
                volume_usdt=usdt_val
            )

            # 如果信号无效，直接返回
            if not signal.is_valid:
                return

            # 🔥 [日志] 记录大机会
            if (usdt_val >= self.signal_generator.config.min_flow_usdt and
                total_vol >= self.signal_generator.config.min_flow_usdt and
                signal.direction == 'bullish'):
                imbalance_ratio = signal.metadata.get('imbalance_ratio', 0.0)
                ema_value = signal.metadata.get('ema_value', 0.0)

                logger.info(
                    f"🎯 [大机会] {self.symbol}: "
                    f"{side} {size:.4f} @ {price:.4f} = {usdt_val:,.0f} USDT | "
                    f"总量={total_vol:,.0f} USDT | "
                    f"失衡={imbalance_ratio:.2f}x | "
                    f"趋势=看涨 (Price>{ema_value:.4f})"
                )

            # 检查 OrderBook 数据
            best_bid, best_ask = self._get_order_book_best_prices(price)
            if best_bid <= 0 or best_ask <= 0:
                logger.warning("订单簿数据不可用，跳过本次开仓")
                return

            # 🔥 [修复] 获取策略专属资金（而非全局总权益）
            strategy_capital = self._capital_commander.get_strategy_capital(self.strategy_id)
            if strategy_capital:
                account_equity = strategy_capital.available
                logger.debug(
                    f"💰 [策略资金] {self.symbol}: "
                    f"可用资金={account_equity:.2f} USDT "
                    f"(策略专属)"
                )
            else:
                # 降级：使用全局权益
                account_equity = self._capital_commander.get_total_equity()
                logger.warning(
                    f"⚠️ [资金降级] {self.symbol}: "
                    f"未找到策略资金，使用全局权益={account_equity:.2f} USDT"
                )

            # 获取订单簿深度
            if hasattr(self, 'market_data_manager') and self.market_data_manager:
                order_book = self.market_data_manager.get_order_book_depth(self.symbol, levels=3)
            elif hasattr(self, 'public_gateway') and self.public_gateway:
                order_book = self.public_gateway.get_order_book_depth(levels=3)
            else:
                logger.warning(f"⚠️ [警告] {self.symbol}: 无法获取订单簿深度")
                order_book = {'bids': [], 'asks': []}

            # 🔍 [调试] 传递前检查 OrderBook 数据
            bids = order_book.get('bids', [])
            asks = order_book.get('asks', [])
            logger.info(f"🔍 [传递前-1] order_book.bids={len(bids)}, order_book.asks={len(asks)}")
            if bids:
                logger.info(f"🔍 [传递前-2] bids[0]={bids[0]}")
            if asks:
                logger.info(f"🔍 [传递前-3] asks[0]={asks[0]}")

            # 🔥 [修复] 使用深拷贝传递数据，避免数据丢失
            order_book_copy = copy.deepcopy(order_book)

            # 计算下单金额（传入合约面值和 EMA 加权）
            ema_boost = signal.metadata.get('ema_boost', 1.0)
            usdt_amount = self.position_sizer.calculate_order_size(
                account_equity=account_equity,
                order_book=order_book_copy,  # 🔥 使用深拷贝
                signal_ratio=signal.metadata.get('imbalance_ratio', 0.0),
                current_price=price,
                side=signal.direction,  # ✅ 使用信号的方向（buy 或 sell）
                ct_val=self.contract_val,
                ema_boost=ema_boost  # ✅ 传入 EMA 加权系数
            )

            # 如果金额为 0，跳过
            if usdt_amount <= 0:
                logger.warning(f"🛑 [自适应仓位] {self.symbol}: 计算金额={usdt_amount:.2f} USDT ≤ 0，跳过本次开仓")
                return

            # 转换为合约张数
            trade_size = self.position_sizer.convert_to_contracts(
                amount_usdt=usdt_amount,
                current_price=price,
                ct_val=self.contract_val
            )
            trade_size = max(1, int(trade_size))

            logger.info(
                f"🎯 [自适应仓位] {self.symbol}: "
                    f"账户权益={account_equity:.2f} USDT, "
                    f"下单金额={usdt_amount:.2f} USDT, "
                    f"合约张数={trade_size} 张, "
                    f"不平衡比={signal.metadata.get('imbalance_ratio', 0.0):.1f}x"
            )

            # 🔥 [新增] VWAP 滑点预估
            # 在下达 limit buy 订单前，从 MarketDataManager 获取当前前 5 档深度
            # 计算：根据我们要下的 size，模拟消耗盘口深度，计算加权平均成交价 (VWAP)
            # 限制：如果 abs(VWAP - BestAsk) / BestAsk > max_slippage_pct（建议配置 0.1%），则放弃此交易
            if self.enable_depth_protection:
                if hasattr(self, 'market_data_manager') and self.market_data_manager:
                    order_book_depth = self.market_data_manager.get_order_book_depth(self.symbol, levels=5)

                    if order_book_depth and 'asks' in order_book_depth and len(order_book_depth['asks']) >= 5:
                        # 计算 VWAP
                        remaining_size = trade_size * self.contract_val  # 转换为实际数量
                        vwap_numerator = 0.0
                        vwap_denominator = 0.0
                        simulated_size = 0.0

                        for ask in order_book_depth['asks'][:5]:  # 前 5 档
                            ask_price = ask[0]
                            ask_size = ask[1]

                            # 模拟消耗
                            if remaining_size <= ask_size:
                                vwap_numerator += ask_price * remaining_size
                                vwap_denominator += remaining_size
                                simulated_size += remaining_size
                                break
                            else:
                                vwap_numerator += ask_price * ask_size
                                vwap_denominator += ask_size
                                remaining_size -= ask_size
                                simulated_size += ask_size

                        if vwap_denominator > 0:
                            vwap = vwap_numerator / vwap_denominator
                            best_ask = order_book_depth['asks'][0][0]

                            # 计算滑点
                            slippage_pct = abs(vwap - best_ask) / best_ask if best_ask > 0 else 0.0

                            if slippage_pct > self.max_slippage_pct:
                                logger.warning(
                                    f"🛑 [滑点保护] {self.symbol}: "
                                    f"预估执行偏差过大: {slippage_pct*100:.2%} "
                                    f"(阈值={self.max_slippage_pct*100:.2%}), "
                                    f"VWAP={vwap:.6f}, BestAsk={best_ask:.6f}, "
                                    f"跳过本次交易"
                                )
                                return

            # 计算止损价格
            stop_loss_price = self._calculate_stop_loss(price)

            # 计算挂单价格
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
                # 🔥 [新增] 状态转换到 PENDING_OPEN
                self._transition_to_state(StrategyState.PENDING_OPEN, "下单成功")
                logger.info(
                    f"✅ [狙击挂单已提交] {self.symbol} @ {decision.price:.6f}, "
                    f"数量={trade_size}, 止损={stop_loss_price:.6f}, "
                    f"策略={decision.reason}"
                )
            else:
                self._transition_to_state(StrategyState.IDLE, "下单失败")

        except Exception as e:
            logger.error(f"❌ [IDLE 状态处理失败] {self.symbol}: {e}", exc_info=True)

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
            'architecture': 'Controller-Components-FSM',
            'symbol': self.symbol,
            'fsm_state': self._get_state().name,
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

    async def _reorder_after_cancel(self):
        """
        🔥 [新增] 撤单后重新挂单（追单逻辑）

        在监控协程中调用，用于插队功能：
        1. 获取当前价格
        2. 重新计算挂单价格
        3. 提交新挂单

        Returns:
            bool: 重新挂单是否成功
        """
        try:
            # 获取当前价格
            best_bid, best_ask = self._get_order_book_best_prices()

            if best_bid <= 0 or best_ask <= 0:
                logger.warning(
                    f"⚠️ [重新挂单] {self.symbol}: "
                    f"订单簿数据不可用，取消追单"
                )
                return False

            # 计算止损价格
            stop_loss_price = self._calculate_stop_loss(best_bid)

            # 计算挂单价格
            decision = self.execution_algo.calculate_maker_price(
                side='buy',
                best_bid=best_bid,
                best_ask=best_ask,
                order_age=0.0
            )

            # 获取策略资金
            strategy_capital = self._capital_commander.get_strategy_capital(self.strategy_id)
            if strategy_capital:
                account_equity = strategy_capital.available
            else:
                account_equity = self._capital_commander.get_total_equity()

            # 获取订单簿深度
            if hasattr(self, 'market_data_manager') and self.market_data_manager:
                order_book = self.market_data_manager.get_order_book_depth(self.symbol, levels=3)
            elif hasattr(self, 'public_gateway') and self.public_gateway:
                order_book = self.public_gateway.get_order_book_depth(levels=3)
            else:
                order_book = {'bids': [], 'asks': []}

            # 🔍 [调试] 传递前检查 OrderBook 数据
            bids = order_book.get('bids', [])
            asks = order_book.get('asks', [])
            logger.info(f"🔍 [追单-传递前-1] order_book.bids={len(bids)}, order_book.asks={len(asks)}")
            if bids:
                logger.info(f"🔍 [追单-传递前-2] bids[0]={bids[0]}")
            if asks:
                logger.info(f"🔍 [追单-传递前-3] asks[0]={asks[0]}")

            # 🔥 [修复] 使用深拷贝传递数据，避免数据丢失
            order_book_copy = copy.deepcopy(order_book)

            # 计算下单金额
            usdt_amount = self.position_sizer.calculate_order_size(
                account_equity=account_equity,
                order_book=order_book_copy,  # 🔥 使用深拷贝
                signal_ratio=5.0,  # 使用默认值
                current_price=best_bid,
                side='buy',
                ct_val=self.contract_val
            )

            if usdt_amount <= 0:
                logger.warning(
                    f"⚠️ [重新挂单] {self.symbol}: "
                    f"计算金额为0，取消追单"
                )
                return False

            # 转换为合约张数
            trade_size = self.position_sizer.convert_to_contracts(
                amount_usdt=usdt_amount,
                current_price=best_bid,
                ct_val=self.contract_val
            )
            trade_size = max(1, int(trade_size))

            # 提交挂单
            success = await self._place_maker_order(
                symbol=self.symbol,
                price=decision.price,
                stop_loss_price=stop_loss_price,
                size=trade_size,
                contract_val=self.contract_val
            )

            if success:
                logger.info(
                    f"✅ [追单成功] {self.symbol}: "
                    f"新价格={decision.price:.6f}, "
                    f"数量={trade_size}, "
                    f"策略={decision.reason}"
                )
            else:
                logger.warning(
                    f"⚠️ [追单失败] {self.symbol}: "
                    f"重新挂单失败"
                )

            return success

        except Exception as e:
            logger.error(f"❌ [重新挂单失败] {self.symbol}: {e}", exc_info=True)
            return False

    async def _monitor_position(self):
        """
        🔥 [修复] 独立的持仓监控协程

        解决提前退出优化导致的止损失效问题：
        - on_tick 中的提前退出（有挂单时 return）导致无法监控止损
        - 使用独立的协程持续监控持仓状态
        - 每 0.5 秒检查一次持仓

        监控内容：
        1. 追踪止损检查
        2. 时间止损检查（30秒）
        3. 硬止损检查（1%）
        4. 挂单状态监控（追单撤单）
        5. 状态维护（订单成交后自动转换到 POSITION_HELD）
        """
        try:
            logger.info(f"🔍 [监控协程] {self.symbol}: 独立持仓监控已启动")

            while self._enabled:
                try:
                    # 获取当前持仓
                    position = self.get_position(self.symbol)
                    current_state = self._get_state()

                    # 检查是否有持仓
                    if position and abs(position.size) > 0:
                        # 从 MarketDataManager 获取当前价格
                        current_price = 0.0
                        if hasattr(self, 'market_data_manager') and self.market_data_manager:
                            best_bid, best_ask = self.market_data_manager.get_best_bid_ask(self.symbol)
                            current_price = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else 0.0
                        elif hasattr(self, 'public_gateway') and self.public_gateway:
                            best_bid, best_ask = self.public_gateway.get_best_bid_ask()
                            current_price = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else 0.0

                        if current_price > 0:
                            now = time.time()

                            # 1. 追踪止损检查
                            if self.state_manager._trailing_stop:
                                should_close, stop_price = self.state_manager.update_trailing_stop(current_price)

                                if should_close:
                                    logger.info(
                                        f"🎯 [监控-追踪止损] {self.symbol}: "
                                        f"止损价={stop_price:.6f}, 当前价={current_price:.6f}"
                                    )
                                    await self._close_position(reason="trailing_stop", stop_price=stop_price, current_price=current_price)
                                    continue

                            # 2. 时间止损检查
                            entry_time = self.state_manager._position.entry_time
                            if entry_time > 0:
                                position_age = now - entry_time

                                if position_age >= self.config.time_limit_seconds:
                                    logger.info(
                                        f"⏰ [监控-时间止损] {self.symbol}: "
                                        f"持仓时间={position_age:.1f}s >= {self.config.time_limit_seconds}s"
                                    )
                                    await self._close_position(reason="time_stop", current_price=current_price)
                                    continue

                            # 3. 硬止损检查（带状态检查）
                            entry_price = self.state_manager._position.entry_price
                            if entry_price > 0:
                                hard_stop_price = entry_price * (1 - self.config.stop_loss_pct)

                                # 🔥 [修复] 检查是否已触发平仓，避免重复触发
                                if current_price <= hard_stop_price:
                                    if current_state == StrategyState.PENDING_CLOSE:
                                        logger.warning(
                                            f"⚠️ [监控-重复触发] {self.symbol}: "
                                            f"硬止损已触发，跳过重复操作"
                                        )
                                        continue

                                    logger.info(
                                        f"📉 [监控-硬止损] {self.symbol}: "
                                        f"当前价={current_price:.6f} <= 止损价={hard_stop_price:.6f}"
                                    )
                                    await self._close_position(reason="hard_stop", current_price=current_price)
                                    continue

                    # 🔥 [新增] 挂单状态监控（PENDING_OPEN）
                    if current_state == StrategyState.PENDING_OPEN:
                        # 检查是否应该追单
                        maker_order_id = self.state_manager.get_maker_order_id()

                        if maker_order_id and maker_order_id != "pending":
                            # 获取当前价格
                            maker_price = 0.0
                            if hasattr(self, 'market_data_manager') and self.market_data_manager:
                                best_bid, best_ask = self.market_data_manager.get_best_bid_ask(self.symbol)
                                maker_price = best_bid if best_bid > 0 else 0.0
                            elif hasattr(self, 'public_gateway') and self.public_gateway:
                                best_bid, best_ask = self.public_gateway.get_best_bid_ask()
                                maker_price = best_bid if best_bid > 0 else 0.0

                            if maker_price > 0:
                                # 获取挂单价格和存活时间
                                maker_order_price = self.state_manager.get_maker_order_price()
                                maker_order_age = self.state_manager.get_maker_order_age()

                                # 检查是否应该追单
                                should_chase = self.execution_algo.should_chase(
                                    current_maker_price=maker_order_price,
                                    current_price=maker_price,
                                    order_age=maker_order_age
                                )

                                if should_chase:
                                    logger.info(
                                        f"🔥 [监控-触发追单] {self.symbol}: "
                                        f"挂单价={maker_order_price:.6f}, "
                                        f"当前价={maker_price:.6f}, "
                                        f"存活时间={maker_order_age:.1f}s"
                                    )

                                    # 撤单
                                    await self._cancel_maker_order()

                                    # 重新计算价格并挂单
                                    await self._reorder_after_cancel()

                                # 🔥 [新增] 深度感知撤单
                                # 场景：当我们的挂单处于队列中时
                                # 优化：监控我们订单所在的价格档位，以及其前方的总挂单量
                                if self.enable_depth_protection and hasattr(self, 'market_data_manager') and self.market_data_manager:
                                    order_book_depth = self.market_data_manager.get_order_book_depth(self.symbol, levels=3)

                                    if order_book_depth and 'bids' in order_book_depth and len(order_book_depth['bids']) > 0:
                                        # 查找我们订单所在的档位
                                        our_price_level = None
                                        volume_ahead = 0.0

                                        for i, bid in enumerate(order_book_depth['bids']):
                                            bid_price = bid[0]
                                            bid_size = bid[1]

                                            # 价格匹配（考虑tick_size精度）
                                            if abs(bid_price - maker_order_price) < self.tick_size:
                                                our_price_level = i
                                                break
                                            # 在我们订单之前的档位
                                            elif bid_price > maker_order_price:
                                                volume_ahead += bid_size

                                        # 如果找到我们的档位
                                        if our_price_level is not None:
                                            our_bid = order_book_depth['bids'][our_price_level]
                                            our_size = our_bid[1]

                                            # 获取上次快照用于检测删单
                                            last_snapshot = self._last_ask_snapshot.get(maker_order_id, {})
                                            last_volume_ahead = last_snapshot.get('volume_ahead', 0.0)

                                            # 🔥 [策略1] 如果前方突然出现了巨大的"压单"
                                            # 压单量 > 我们订单的 10 倍
                                            if volume_ahead > our_size * self.anti_flipping_threshold:
                                                logger.warning(
                                                    f"🚨 [深度感知-压单] {self.symbol}: "
                                                    f"前方压单量={volume_ahead:.0f} (我们的={our_size:.0f}), "
                                                    f"超过{self.anti_flipping_threshold}倍阈值，立即撤单"
                                                )
                                                await self._cancel_maker_order()
                                                # 等待500ms
                                                await asyncio.sleep(0.5)
                                                continue

                                            # 🔥 [策略2] 前方档位在 100ms 内发生了剧烈的"删单"
                                            if len(last_snapshot) > 0:
                                                volume_change = abs(volume_ahead - last_volume_ahead)
                                                time_since_snapshot = time.time() - last_snapshot.get('timestamp', 0)

                                                # 如果删单量超过我们订单的10倍，且时间<100ms
                                                if (volume_change > our_size * self.anti_flipping_threshold and
                                                    time_since_snapshot < 0.1):
                                                    logger.warning(
                                                        f"🚨 [深度感知-删单] {self.symbol}: "
                                                        f"前方删单量={volume_change:.0f} (我们的={our_size:.0f}), "
                                                        f"超过{self.anti_flipping_threshold}倍阈值，立即撤单"
                                                    )
                                                    await self._cancel_maker_order()
                                                    # 等待500ms
                                                    await asyncio.sleep(0.5)
                                                    continue

                                            # 保存快照
                                            self._last_ask_snapshot[maker_order_id] = {
                                                'volume_ahead': volume_ahead,
                                                'timestamp': time.time()
                                            }

                    # ========== 状态一致性检查 ==========
                    # 如果有持仓但状态是 PENDING_OPEN，说明订单成交但状态未更新
                    if position and abs(position.size) > 0 and current_state == StrategyState.PENDING_OPEN:
                        logger.warning(
                            f"🔧 [监控-状态修复] {self.symbol}: "
                            f"检测到持仓但状态=PENDING_OPEN，自动转换到 POSITION_HELD"
                        )
                        self._transition_to_state(StrategyState.POSITION_HELD, "检测到持仓")

                    # 如果没有持仓但状态是 POSITION_HELD，需要重置
                    elif (not position or abs(position.size) <= 0) and current_state == StrategyState.POSITION_HELD:
                        logger.warning(
                            f"🔧 [监控-状态修复] {self.symbol}: "
                            f"检测到无持仓但状态=POSITION_HELD，自动重置到 IDLE"
                        )
                        await self._reset_position_state()

                except Exception as e:
                    logger.error(f"❌ [监控协程异常] {self.symbol}: {e}", exc_info=True)

                # 每 0.5 秒检查一次
                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info(f"🛑 [监控协程] {self.symbol}: 监控协程已停止")
        except Exception as e:
            logger.error(f"❌ [监控协程崩溃] {self.symbol}: {e}", exc_info=True)

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
