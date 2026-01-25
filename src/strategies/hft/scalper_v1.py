"""
ScalperV1 Micro-Reversion Sniper Strategy (V2)

专门针对 1核 1G 内存、1ms 延迟环境优化的微观结构狙击策略。

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

Example:
    >>> scalper = ScalperV1(
    ...     event_bus=event_bus,
    ...     order_manager=order_manager,
    ...     capital_commander=capital_commander,
    ...     symbol="DOGE-USDT-SWAP",
    ...     imbalance_ratio=5.0,
    ...     min_flow_usdt=5000.0
    ... )
    >>> await scalper.start()
"""

import time
import asyncio
import logging
import collections
from typing import Dict, Any, Optional
from dataclasses import dataclass

from ...core.event_types import Event
from ...core.event_bus import EventBus
from ...oms.order_manager import OrderManager
from ...oms.capital_commander import CapitalCommander
from ...config.risk_profile import RiskProfile, StopLossType
from ...utils.volatility import VolatilityEstimator
from ..base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


@dataclass
class ScalperV1Config:
    """ScalperV1 策略配置（V2）"""
    symbol: str = "DOGE-USDT-SWAP"
    imbalance_ratio: float = 5.0          # 买量 > 卖量 * ratio 才触发（V2: 提高到 5.0）
    min_flow_usdt: float = 5000.0         # 最小流速（USDT），过滤杂波（V2: 提高到 5000）
    take_profit_pct: float = 0.002       # 止盈 0.2%（V2: 使用追踪止损）
    stop_loss_pct: float = 0.01          # 硬止损 1%
    time_limit_seconds: int = 30         # 时间止损 30 秒（V2: 提高到 30 秒）
    cooldown_seconds: float = 10.0       # 交易冷却（秒）
    position_size: Optional[float] = None  # 仓位大小（None=基于风险计算）
    maker_timeout_seconds: float = 2.0    # Maker 挂单超时时间（秒）
    # ✨ 追踪止损配置（V2 新增）
    trailing_stop_activation_pct: float = 0.001  # 追踪止损激活阈值 0.1%
    trailing_stop_callback_pct: float = 0.0005   # 追踪止损回调阈值 0.05%
    # ✨ 趋势过滤配置（V2 新增）
    ema_period: int = 50                 # EMA 周期（ticks）
    spread_threshold_pct: float = 0.0005  # 点差阈值 0.05%
    # ✨ 其他配置
    tick_size: float = 0.0001             # Tick 大小（用于追单计算）
    enable_chasing: bool = True            # 是否启用追单（🔥 [启用] 插队/追单模式）
    max_chase_distance_pct: float = 0.001  # 最大追单距离 0.1%


class ScalperV1(BaseStrategy):
    """
    ScalperV1 Micro-Reversion Sniper 策略（V2）

    基于微观结构失衡和趋势过滤的超短线狙击策略。

    策略逻辑（V2）:
    1. 趋势过滤：使用 EMA 判断方向（只做多）
    2. 质量过滤：检查点差和流动性
    3. 精准入场：买 >> 卖 + 趋势向上 + 冷却通过
    4. 智能退出：追踪止损 + 硬止损 + 时间止损

    优化特点：
    - O(1) 时间复杂度
    - 零历史数据存储（仅 100 个价格点）
    - 极速计算
    - Maker 模式：降低手续费
    - 严格风控：保留所有安全机制
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
        # ✨ HFT 策略应默认为极短冷却
        cooldown_seconds: float = 0.1,
        # ✨ 容错参数（吃掉所有未定义的参数，防止崩溃）
        **kwargs
    ):
        """
        初始化 ScalperV1 策略（V2）

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

        # 策略配置
        self.config = ScalperV1Config(
            symbol=symbol,
            imbalance_ratio=imbalance_ratio,
            min_flow_usdt=min_flow_usdt,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            time_limit_seconds=time_limit_seconds,
            position_size=position_size,
            cooldown_seconds=cooldown_seconds,
            maker_timeout_seconds=2.0,
            trailing_stop_activation_pct=0.001,  # V2: 0.1%
            trailing_stop_callback_pct=0.0005,   # V2: 0.05%
            ema_period=50,                        # V2: 50 ticks
            spread_threshold_pct=0.0005            # V2: 0.05%
        )

        # ✨ 容错：记录未识别的参数
        if kwargs:
            logger.warning(
                f"策略 {strategy_id} 收到未识别的参数: {list(kwargs.keys())}"
            )

        # ========== 极简状态变量（O(1) 访问）==========
        # 成交量窗口（1秒滑动窗口）
        self.vol_window_start = 0.0  # 窗口开始时间
        self.buy_vol = 0.0            # 买入成交量（USDT）
        self.sell_vol = 0.0           # 卖出成交量（USDT）
        self._previous_price = 0.0      # 上一笔成交价格（用于波动率计算）

        # 持仓状态
        self._entry_price = 0.0        # 入场价格
        self._entry_time = 0.0         # 入场时间戳
        self._position_opened = False   # 是否有持仓

        # [保留] 本地强持仓记录（不依赖 PositionManager）
        self.local_pos_size = 0.0

        # [保留] 冷却机制：防止平仓后立即重新开仓
        self._last_close_time = 0.0  # 上次平仓时间戳

        # [保留] 交易冷却：全局冷却
        self.last_exit_time = 0.0  # 上次平仓时间戳（全局冷却）

        # [保留] 开仓锁机制：防止重复开仓
        self._is_pending_open = False  # 是否有在途的开仓请求

        # [保留] 开仓锁超时保护（防止事件丢失导致死锁）
        self._pending_open_timeout = 60.0  # 60秒无响应则强制解锁

        # [保留] 平仓锁机制（防止"机枪平仓"重复下单）- 升级为超时锁
        self._last_close_time = 0.0  # 上次平仓时间戳（用于防止连发）
        self._close_lock_timeout = 10.0  # 平仓锁超时时间（秒）

        # [保留] 定时同步机制（防止仓位漂移）
        self._last_sync_time = 0.0  # 上次持仓同步时间
        self._sync_interval = 15.0  # 持仓同步间隔（秒）

        # [保留] Maker 挂单管理
        self._maker_order_id = None          # 当前挂单 ID
        self._maker_order_time = 0.0        # 挂单时间戳
        self._maker_order_price = 0.0        # 挂单价格
        self._maker_order_initial_price = 0.0  # 初始信号价格（用于追单风控）

        # ✨ [V2 新增] 趋势过滤器
        self.price_history = collections.deque(maxlen=100)  # 价格历史（100 个点）
        self.ema_value = 0.0  # EMA 值

        # ✨ [V2 新增] 追踪止损状态
        self.highest_pnl_pct = 0.0  # 最高未实现收益率

        # ✨ [新增] 合约面值（Contract Value）
        # 用于正确计算交易价值：trade_value = size * price * contract_val
        # 默认 1.0（适用于大多数币种），但某些币种如 DOGE 需要调整
        self.contract_val = 1.0

        # 波动率估算器（用于动态止损）
        self._volatility_estimator = VolatilityEstimator(
            alpha=0.2,
            min_volatility_floor=0.005  # 0.5% 波动率下限
        )

        # 统计信息
        self._total_trades = 0          # 总交易次数
        self._win_trades = 0            # 盈利次数
        self._loss_trades = 0           # 亏损次数
        self._max_imbalance_seen = 0.0   # 最大买卖失衡比

        # ========== 激进风控配置 ==========
        self.set_risk_profile(RiskProfile(
            strategy_id=self.strategy_id,
            max_leverage=5.0,                    # 允许 5 倍杠杆
            stop_loss_type=StopLossType.TIME_BASED, # 时间止损
            time_limit_seconds=time_limit_seconds,  # 30 秒强制平仓
            single_loss_cap_pct=0.02,             # 单笔最大亏损 2%
            max_order_size_usdt=500.0,            # HFT 快进快出，单笔较小
            max_daily_loss_pct=0.05                # 每日最大亏损 5%
        ))

        logger.info(
            f"🚀 ScalperV1 初始化（V2 - Micro-Reversion Sniper）: symbol={symbol}, "
            f"imbalance_ratio={imbalance_ratio}, "
            f"min_flow={min_flow_usdt} USDT, "
            f"take_profit={take_profit_pct*100:.2f}%, "
            f"time_stop={time_limit_seconds}s, "
            f"maker_timeout={2.0}s, "
            f"ema_period=50, "
            f"trailing_stop=0.1%/0.05%"
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

        # ✨ [新增] 同步合约面值（Contract Value）
        # 🔥 [修复] 改为 await，确保策略等待同步完成后再处理 tick
        # 避免竞态条件：使用默认值 1.0 计算交易价值
        await self._sync_contract_value()

        logger.info(
            f"🚀 ScalperV1 V2 启动: symbol={self.symbol}, "
            f"cooldown={self.config.cooldown_seconds}s, "
            f"mode=Sniper, "
            f"direction=LongOnly"
        )

    async def _sync_contract_value(self):
        """
        同步合约面值（Contract Value）

        从交易所获取交易对详情，提取 ctVal 字段。
        ctVal 用于正确计算交易价值：
        trade_value = size * price * ctVal

        错误处理：
        - 如果 API 调用失败，fallback 到 1.0
        - 如果 ctVal 缺失，fallback 到 1.0
        - 记录 WARN 级别日志
        """
        try:
            # 检查是否有 REST gateway
            if not self._order_manager or not hasattr(self._order_manager, '_rest_gateway'):
                logger.warning(
                    f"⚠️ [Contract Value] {self.symbol}: "
                    f"无法访问 REST gateway，使用默认值 1.0"
                )
                self.contract_val = 1.0
                return

            rest_gateway = self._order_manager._rest_gateway

            # 检查是否有 get_instrument_details 方法
            if not hasattr(rest_gateway, 'get_instrument_details'):
                logger.warning(
                    f"⚠️ [Contract Value] {self.symbol}: "
                    f"REST gateway 不支持 get_instrument_details，使用默认值 1.0"
                )
                self.contract_val = 1.0
                return

            # 获取交易对详情
            instrument_details = await rest_gateway.get_instrument_details(self.symbol)

            if instrument_details is None:
                logger.warning(
                    f"⚠️ [Contract Value] {self.symbol}: "
                    f"无法获取交易对详情，使用默认值 1.0"
                )
                self.contract_val = 1.0
                return

            # 提取 ctVal（合约面值）
            ct_val = instrument_details.get('ctVal', 1.0)

            # 验证 ctVal 有效性
            if ct_val is None or ct_val <= 0:
                logger.warning(
                    f"⚠️ [Contract Value] {self.symbol}: "
                    f"ctVal 无效或缺失 ({ct_val})，使用默认值 1.0"
                )
                self.contract_val = 1.0
            else:
                self.contract_val = ct_val
                logger.info(
                    f"🔍 [Metadata] Synced Contract Value for {self.symbol}: {ct_val}"
                )

        except Exception as e:
            logger.warning(
                f"⚠️ [Contract Value] {self.symbol}: "
                f"同步失败 ({str(e)})，使用默认值 1.0"
            )
            self.contract_val = 1.0

    def _is_cooling_down(self) -> bool:
        """
        检查是否处于冷却期

        Returns:
            bool: 是否处于冷却期
        """
        now = time.time()
        return now - self._last_close_time < self.config.cooldown_seconds

    def _update_ema(self, current_price: float):
        """
        更新 EMA 值（V2 新增）

        Args:
            current_price (float): 当前价格
        """
        # 添加到价格历史
        self.price_history.append(current_price)

        # 计算简单移动平均（SMA）作为 EMA 的近似
        # 使用最后 N 个价格的平均值
        if len(self.price_history) >= self.config.ema_period:
            # 取最后 N 个价格的平均值
            recent_prices = list(self.price_history)[-self.config.ema_period:]
            self.ema_value = sum(recent_prices) / len(recent_prices)
        elif len(self.price_history) > 0:
            # 数据不足时，使用所有数据的平均值
            self.ema_value = sum(self.price_history) / len(self.price_history)
        else:
            # 初始化
            self.ema_value = current_price

    def _get_trend_bias(self) -> str:
        """
        获取趋势偏置（V2 新增）

        Returns:
            str: "bullish" (看涨) / "bearish" (看跌) / "neutral" (中性)
        """
        if len(self.price_history) < self.config.ema_period:
            return "neutral"

        current_price = self.price_history[-1]
        if current_price > self.ema_value:
            return "bullish"
        elif current_price < self.ema_value:
            return "bearish"
        else:
            return "neutral"

    async def on_tick(self, event: Event):
        """
        处理 Tick 事件（策略核心逻辑 - V2）

        每秒滑动窗口，累加买卖量，更新 EMA，检测趋势和失衡并触发交易。

        Args:
            event (Event): TICK 事件
                data: {
                    'symbol': str,
                    'price': float,
                    'size': float,
                    'side': str,  # 'buy' or 'sell'
                    'usdt_value': float,
                    'timestamp': int
                }
        """
        try:
            # 0. 检查策略是否启用
            if not self.is_enabled():
                return

            now = time.time()

            # 🔥 [保留] 使用配置的冷却时间
            # 如果上次平仓后未满冷却时间，禁止开仓
            if now - self.last_exit_time < self.config.cooldown_seconds:
                return

            # 🔥 [保留] 强制状态对齐（防止幽灵仓位累积）
            if not self._position_opened and abs(self.local_pos_size) > 0.0001:
                logger.warning(
                    f"⚠️ [状态校准] {self.symbol}: "
                    f"策略处于空仓状态，但检测到残留仓位 {self.local_pos_size:.4f}，强制归零"
                )
                self.local_pos_size = 0.0

            # 🔥 [保留] 实现 REST API 强制同步
            if now - self._last_sync_time > self._sync_interval:
                self._last_sync_time = now

                real_position = 0.0
                try:
                    if self._order_manager and hasattr(self._order_manager, '_rest_gateway'):
                        rest_gateway = self._order_manager._rest_gateway
                        if hasattr(rest_gateway, 'get_positions'):
                            positions = await rest_gateway.get_positions(symbol=self.symbol)

                            if positions and len(positions) > 0:
                                pos = positions[0]
                                real_position = float(pos.get('size', 0))
                                logger.debug(
                                    f"📊 [REST API 持仓] {self.symbol}: "
                                    f"size={real_position:.4f}, "
                                    f"entry={pos.get('entry_price', 0):.2f}, "
                                    f"pnl={pos.get('unrealized_pnl', 0):.2f}"
                                )
                except Exception as sync_error:
                    logger.error(
                        f"❌ [持仓同步失败] {self.symbol}: "
                        f"{str(sync_error)}"
                    )

                position_diff = abs(real_position - self.local_pos_size)
                if position_diff > 0.1:
                    logger.error(
                        f"⚠️ [账本偏差] {self.symbol}: "
                        f"发现偏差！本地={self.local_pos_size:.4f}, "
                        f"交易所={real_position:.4f}, "
                        f"偏差={position_diff:.4f}。强制同步..."
                    )

                    self.local_pos_size = real_position
                    self._position_opened = (abs(self.local_pos_size) > 0.001)

                    if abs(self.local_pos_size) < 0.001:
                        logger.warning(
                            f"🔄 [强制重置] {self.symbol}: "
                            f"交易所显示空仓，强制重置所有状态"
                        )
                        self._position_opened = False
                        self._entry_price = 0.0
                        self._entry_time = 0.0
                        self._maker_order_id = None
                        self._maker_order_time = 0.0
                        self._maker_order_price = 0.0
                        self._maker_order_initial_price = 0.0
                        self._is_pending_open = False

                    logger.info(
                        f"✅ [同步完成] {self.symbol}: "
                        f"Local已强制更新为 {self.local_pos_size:.4f}, "
                        f"Status={'开仓' if self._position_opened else '空仓'}"
                    )
                else:
                    logger.info(
                        f"🔍 [持仓监控] {self.symbol}: "
                        f"Local={self.local_pos_size:.4f}, "
                        f"REST={real_position:.4f}, "
                        f"偏差={position_diff:.4f}, "
                        f"Status={'开仓' if self._position_opened else '空仓'}, "
                        f"HasOrder={'是' if self._maker_order_id else '否'}"
                    )

            # 🔥 [保留] 强制对账逻辑
            if abs(self.local_pos_size) > 4.0:
                logger.warning(
                    f"⚠️ [持仓异常] {self.symbol}: "
                    f"本地持仓异常 ({self.local_pos_size:.2f})，强制重置为 0"
                )
                self.local_pos_size = 0.0
                self._position_opened = False
                return

            # [保留] 如果在冷却中，直接静默跳过
            if self._is_cooling_down():
                return

            # 🔥 [保留] 开仓锁超时保护
            if self._is_pending_open and self._maker_order_time is not None and self._maker_order_time > 0:
                time_locked = now - self._maker_order_time
                if time_locked > self._pending_open_timeout:
                    logger.error(
                        f"🚨 [死锁解除] {self.symbol}: "
                        f"开仓锁已卡住 {time_locked:.1f}s (可能是事件丢失)，强制重置状态！"
                    )
                    self._is_pending_open = False
                    self._maker_order_id = None
                    self.local_pos_size = 0.0
                    self._position_opened = False

            # 🔥 [保留] Layer 3: 订单 TTL (10秒安全网)
            if (self._maker_order_id is not None and
                self._maker_order_id != "pending" and
                self._maker_order_time is not None and
                self._maker_order_time > 0):

                order_age = now - self._maker_order_time

                if order_age > 10.0:
                    logger.warning(
                        f"🚨 [订单 TTL 触发] {self.symbol}: "
                        f"订单 {self._maker_order_id} 已超时 {order_age:.1f}s，"
                        f"可能系统冻结，强制执行安全措施！"
                    )

                    try:
                        if (self._order_manager and
                            hasattr(self._order_manager, '_rest_gateway')):
                            rest_gateway = self._order_manager._rest_gateway
                            if hasattr(rest_gateway, 'get_order_status'):
                                order_status = await rest_gateway.get_order_status(
                                    order_id=self._maker_order_id,
                                    symbol=self.symbol
                                )

                                if order_status:
                                    state = order_status.get('state', '').lower()

                                    if state == 'filled':
                                        logger.warning(
                                            f"⚠️ [幽灵成交] {self.symbol}: "
                                            f"订单 {self._maker_order_id} 在超时后实际已成交！"
                                        )

                                        fill_event_data = {
                                            'order_id': self._maker_order_id,
                                            'symbol': self.symbol,
                                            'filled_size': float(order_status.get('fillSz', 0)),
                                            'price': float(order_status.get('avgPx', 0)),
                                            'side': 'buy',
                                            'stop_loss_price': self._maker_order_price
                                        }

                                        from ...core.event_types import Event, EventType
                                        fill_event = Event(
                                            type=EventType.ORDER_FILLED,
                                            data=fill_event_data,
                                            source="strategy_ttl_check"
                                        )

                                        await self.on_order_filled(fill_event)

                                    elif state in ['live', 'partially_filled']:
                                        logger.error(
                                            f"🚨 [强制取消] {self.symbol}: "
                                            f"订单 {self._maker_order_id} 状态={state}，"
                                            f"强制取消防止幽灵成交！"
                                        )

                                        await rest_gateway.cancel_order(
                                            order_id=self._maker_order_id,
                                            symbol=self.symbol
                                        )

                                        from ...core.event_types import Event, EventType
                                        cancel_event = Event(
                                            type=EventType.ORDER_CANCELLED,
                                            data={
                                                'order_id': self._maker_order_id,
                                                'symbol': self.symbol,
                                                'reason': 'ttl_force_cancel'
                                            },
                                            source="strategy_ttl_check"
                                        )
                                        await self.on_order_cancelled(cancel_event)

                                    else:
                                        logger.info(
                                            f"🧹 [订单清理] {self.symbol}: "
                                            f"订单 {self._maker_order_id} 状态={state}，"
                                            f"清理本地状态"
                                        )
                                        self._is_pending_open = False
                                        self._maker_order_id = None
                                        self._maker_order_time = 0.0

                    except Exception as ttl_error:
                        logger.error(
                            f"❌ [TTL 检查失败] {self.symbol}: "
                            f"{str(ttl_error)}，强制重置状态"
                        )
                        self._is_pending_open = False
                        self._maker_order_id = None
                        self._maker_order_time = 0.0

            # [保留] 检查挂单超时
            if self._maker_order_id is not None:
                if now - self._maker_order_time >= self.config.maker_timeout_seconds:
                    logger.warning(
                        f"⏰ [Maker 超时] {self.symbol} 挂单 {self._maker_order_id} "
                        f"未成交，超时 {self.config.maker_timeout_seconds}s，撤单"
                    )
                    await self._cancel_maker_order()

            # [保留] 窗口重置（每秒重置一次）
            if now - self.vol_window_start >= 1.0:
                self.buy_vol = 0.0
                self.sell_vol = 0.0
                self.vol_window_start = now

            # 解析 Tick 数据
            data = event.data
            symbol = data.get('symbol')
            price = float(data.get('price', 0))
            size = float(data.get('size', 0))
            side = data.get('side', '').lower()

            # ✨ [新增] 使用合约面值计算交易价值
            # trade_value = size * price * contract_val
            # 对于 DOGE 等币种，1 contract != 1 coin，需要使用 ctVal 修正
            usdt_val = float(data.get('usdt_value', price * size * self.contract_val))

            # 检查交易对是否匹配
            if symbol != self.symbol:
                return

            # 增加 Tick 计数
            self._increment_ticks()

            # 🔥 [新增] 检查是否仍在使用默认值（同步失败）
            # 如果 ctVal 仍然是 1.0，说明同步可能失败或未完成
            # 添加 WARNING 日志提醒开发者
            if self.contract_val == 1.0:
                logger.warning(
                    f"⚠️ [Contract Value] {self.symbol}: "
                    f"仍在使用默认 ctVal=1.0，可能导致交易价值计算错误！"
                )

            # 累加成交量
            if side == 'buy':
                self.buy_vol += usdt_val
                logger.debug(
                    f"💰 [Tick Buy] {self.symbol}: "
                    f"size={size}, price={price:.6f}, "
                    f"ctVal={self.contract_val}, value={usdt_val:.2f} USDT"
                )
            elif side == 'sell':
                self.sell_vol += usdt_val
                logger.debug(
                    f"💰 [Tick Sell] {self.symbol}: "
                    f"size={size}, price={price:.6f}, "
                    f"ctVal={self.contract_val}, value={usdt_val:.2f} USDT"
                )

            # 更新波动率估算器
            if self._previous_price > 0:
                self._volatility_estimator.update_volatility(
                    current_price=price,
                    previous_close=self._previous_price
                )
            self._previous_price = price

            # ✨ [V2 新增] 更新 EMA（趋势过滤）
            self._update_ema(price)

            # 🔥 [保留] 单向模式 - 有持仓时绝对禁止开新仓
            if abs(self.local_pos_size) > 0.001:
                # 只有平仓逻辑能继续执行
                if self._position_opened:
                    await self._check_exit_conditions(price, now)

                # 检查追单条件（V2 暂时保留，但可能不使用）
                if self._maker_order_id is not None:
                    await self._check_chasing_conditions(price, now)
            else:
                # ✨ [V2 新增] 只有空仓时才允许检查开仓信号
                if not self._position_opened and self._maker_order_id is None:
                    await self._check_entry_conditions(price, now)

        except Exception as e:
            logger.error(f"处理 Tick 事件失败: {e}", exc_info=True)

    async def on_signal(self, signal: Dict[str, Any]):
        """
        处理策略信号（ScalperV1 不使用此方法）

        Args:
            signal (dict): 策略信号
        """
        pass

    async def on_order_filled(self, event: Event):
        """
        处理订单成交事件（解锁开仓锁）

        🔥 [保留] 精确状态跟踪：使用增量更新，避免盲目重置状态

        Args:
            event (Event): ORDER_FILLED 事件
        """
        try:
            data = event.data
            symbol = data.get('symbol', '')

            if symbol != self.symbol:
                return

            side = data.get('side', '').lower()
            filled_size = float(data.get('filled_size', 0))

            # 🔥 [保留] 处理开仓订单成交（买入）
            if self._is_pending_open and side == 'buy':
                logger.info(f"✅ [开仓成交] {self.symbol}: 解锁开仓锁")
                self._is_pending_open = False
                self._maker_order_id = None

                # 🔥 [保留] 增量更新：使用 +=
                self.local_pos_size += filled_size

                self._position_opened = True
                self._entry_price = float(data.get('price', 0))
                self._entry_time = time.time()

                # ✨ [V2 新增] 重置追踪止损
                self.highest_pnl_pct = 0.0

                logger.info(
                    f"📊 [开仓成功] {self.symbol} @ {self._entry_price:.2f}, "
                    f"数量={filled_size:.4f}, 本地持仓={self.local_pos_size:.4f}, "
                    f"追踪止损已重置"
                )

            # 🔥 [保留] 处理平仓订单成交（卖出）
            elif side == 'sell':
                # 🔥 [保留] 增量更新：使用 -=
                self.local_pos_size -= filled_size

                logger.info(
                    f"📊 [平仓成交] {self.symbol}: 数量={filled_size:.4f}, "
                    f"本地持仓={self.local_pos_size:.4f}"
                )

                # 🔥 [保留] 浮点数精度安全检查
                if abs(self.local_pos_size) < 0.0001:
                    self.local_pos_size = 0.0

                # 🔥 [保留] 只在持仓接近0时重置标志
                if abs(self.local_pos_size) < 0.001:
                    logger.info(f"✅ [持仓归零] {self.symbol}: 平仓完成，重置状态")
                    self._position_opened = False
                    self._entry_price = 0.0
                    self._entry_time = 0.0

                    # ✨ [V2 新增] 重置追踪止损
                    self.highest_pnl_pct = 0.0

                    # 🔥 [保留] 只在平仓成交时更新冷却时间
                    self.last_exit_time = time.time()
                else:
                    logger.debug(
                        f"⚠️ [持仓未归零] {self.symbol}: "
                        f"本地持仓={self.local_pos_size:.4f}，保留开仓状态"
                    )
        except Exception as e:
            logger.error(f"处理订单成交事件失败: {e}", exc_info=True)

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

            if self._is_pending_open:
                logger.warning(f"🚫 [开仓失败] {self.symbol}: 订单被取消，解锁开仓锁")
                self._is_pending_open = False
        except Exception as e:
            logger.error(f"处理订单取消事件失败: {e}", exc_info=True)

    async def _check_entry_conditions(self, price: float, now: float):
        """
        检查入场条件（V2 - Sniper Mode）

        ✨ V2 新增：
        - 趋势过滤：Price > EMA
        - 质量过滤：Spread < 0.05%, Volume > 5000 USDT

        Args:
            price (float): 当前价格
            now (float): 当前时间戳
        """
        # 1. 检查当前窗口（1秒）内的总活跃度
        total_vol = self.buy_vol + self.sell_vol
        if total_vol < self.config.min_flow_usdt:
            return

        # 2. ✨ [V2] 趋势过滤：只做多（Price > EMA）
        trend_bias = self._get_trend_bias()
        if trend_bias != "bullish":
            logger.debug(
                f"📊 [趋势过滤] {self.symbol}: "
                f"Trend={trend_bias}, Price={price:.6f}, "
                f"EMA={self.ema_value:.6f}, 不满足看涨条件"
            )
            return

        # 3. 检查买卖失衡
        if self.buy_vol > self.sell_vol * self.config.imbalance_ratio:
            # 记录最大失衡比
            imbalance = 0.0
            if self.sell_vol > 0:
                imbalance = self.buy_vol / self.sell_vol
                self._max_imbalance_seen = max(self._max_imbalance_seen, imbalance)

            logger.info(
                f"🎯 [失衡触发] {self.symbol}: "
                f"买={self.buy_vol:.0f} USDT, "
                f"卖={self.sell_vol:.0f} USDT, "
                f"失衡比={imbalance:.2f}x, "
                f"价格={price:.6f}, "
                f"趋势={trend_bias}"
            )

            # 4. ✨ [V2] 获取订单簿数据（质量过滤）
            best_bid, best_ask = self._get_order_book_best_prices(price)

            # 🛡️ 保护：如果拿不到价格，绝对不要开仓
            if best_bid <= 0 or best_ask <= 0:
                logger.warning("订单簿数据不可用，跳过本次开仓")
                return

            # 5. ✨ [V2] 质量过滤：点差检查
            spread_pct = (best_ask - best_bid) / best_bid
            if spread_pct > self.config.spread_threshold_pct:
                logger.warning(
                    f"🛑 [点差过滤] {self.symbol}: "
                    f"Spread={spread_pct*100:.4f}% > "
                    f"阈值={self.config.spread_threshold_pct*100:.4f}%, "
                    f"跳过本次开仓"
                )
                return

            # 6. 计算 Maker 挂单价格（插队机制）
            # 使用 Best Bid（V2: 更激进，直接在 Best Bid 挂单）
            maker_price = best_bid

            logger.info(
                f"📊 [狙击挂单] {self.symbol}: "
                f"Best Bid={best_bid:.6f}, Best Ask={best_ask:.6f}, "
                f"Spread={spread_pct*100:.4f}%, "
                f"挂单价格={maker_price:.6f}"
            )

            # 7. 计算止损价格（基于波动率）
            stop_loss_price = self._calculate_stop_loss(price)

            logger.debug(
                f"🛡️ [止损计算] entry={price:.6f}, "
                f"stop={stop_loss_price:.6f}, "
                f"距离={abs(price - stop_loss_price):.6f}"
            )

            # 8. 计算交易数量（强制整数，至少 1）
            if self.config.position_size is not None:
                trade_size = max(1, int(self.config.position_size))
                logger.debug(f"使用固定仓位: {trade_size}")
            else:
                # 基于风险计算仓位，但确保至少为 1
                risk_amount = (self._capital_commander.get_total_equity() *
                             self._capital_commander._risk_config.RISK_PER_TRADE_PCT)
                price_distance = abs(maker_price - stop_loss_price)
                base_quantity = risk_amount / price_distance
                trade_size = max(1, int(base_quantity))
                logger.debug(f"基于风险计算仓位: {trade_size} (base: {base_quantity:.4f})")

            # 🔥 [修复] 传递 contract_val 参数给资金计算
            # 9. Maker 挂单（限价单）
            success = await self._place_maker_order(
                symbol=self.symbol,
                price=maker_price,
                stop_loss_price=stop_loss_price,
                size=trade_size,
                contract_val=self.contract_val  # 🔥 [修复] 传递合约面值
            )

            if success:
                self._increment_signals()
                logger.info(
                    f"✅ [狙击挂单已提交] {self.symbol} @ {maker_price:.6f}, "
                    f"数量={trade_size}, 止损={stop_loss_price:.6f}, "
                    f"趋势={trend_bias}, 失衡比={imbalance:.2f}x"
                )

    async def _place_maker_order(
        self,
        symbol: str,
        price: float,
        stop_loss_price: float,
        size: float
    ) -> bool:
        """
        下 Maker 挂单（限价单）

        Args:
            symbol (str): 交易对
            price (float): 挂单价格（Best Bid）
            stop_loss_price (float): 止损价格
            size (float): 数量

        Returns:
            bool: 下单是否成功
        """
        if self._is_pending_open:
            logger.warning(
                f"🚫 [风控拦截] {self.symbol}: 上一个开仓请求尚未结束，拒绝重复开仓"
            )
            return False

        try:
            self._is_pending_open = True

            success = await self.buy(
                symbol=symbol,
                entry_price=price,
                stop_loss_price=stop_loss_price,
                order_type='limit',
                size=size
            )

            if success:
                self._maker_order_id = "pending"
                self._maker_order_time = time.time()
                self._maker_order_price = price
                self._maker_order_initial_price = price
            else:
                self._is_pending_open = False

            return success
        except Exception as e:
            self._is_pending_open = False
            logger.error(f"❌ [Maker 挂单失败] {self.symbol}: 下单失败: {str(e)}")
            return False

    async def _check_chasing_conditions(self, current_price: float, now: float):
        """
        检查追单条件（V2: 插队追单模式）

        Args:
            current_price (float): 当前价格
            now (float): 当前时间戳
        """
        # V2 暂时禁用追单机制
        if not self.config.enable_chasing:
            return

        if self._maker_order_id is None or self._maker_order_price <= 0:
            return

        # 🔥 保留 Pre-Check
        if self._position_opened or abs(self.local_pos_size) > 0.001:
            logger.warning(
                f"🛑 [追单拦截] {self.symbol}: "
                f"检测到已有持仓 ({self.local_pos_size:.4f})，停止追单"
            )
            self._maker_order_id = None
            self._maker_order_price = 0.0
            return

        best_bid, best_ask = self._get_order_book_best_prices()

        if best_bid <= 0:
            return

        if best_bid > self._maker_order_price:
            chase_distance = abs(best_bid - self._maker_order_initial_price) / self._maker_order_initial_price

            if chase_distance > self.config.max_chase_distance_pct:
                logger.warning(
                    f"🛑 [追单放弃] {self.symbol}: "
                    f"追单距离={chase_distance*100:.2f}% > "
                    f"最大限制={self.config.max_chase_distance_pct*100:.2f}%, "
                    f"撤单并放弃"
                )
                await self._cancel_maker_order()
                return

            aggressive_bid = best_bid + self.config.tick_size
            conservative_ask = best_ask - self.config.tick_size
            new_price = min(aggressive_bid, conservative_ask)

            logger.info(
                f"🔄 [插队触发] {self.symbol}: "  # 🔥 [修复] 更新日志描述
                f"原价格={self._maker_order_price:.6f}, "
                f"新Best Bid={best_bid:.6f}, "
                f"新价格={new_price:.6f}, "
                f"插队距离={chase_distance*100:.2f}%, "
                f"合约面值={self.contract_val}"  # 🔥 [修复] 显示合约面值
            )

            await self._cancel_maker_order()
            await asyncio.sleep(0.1)

            # 🔥 保留 Double-Check
            if self._position_opened or abs(self.local_pos_size) > 0.001:
                logger.warning(
                    f"🛑 [插队拦截] {self.symbol}: "
                    f"撤单期间订单已成交 (持仓={self.local_pos_size:.4f})，取消发送新单"
                )
                return

            if self.config.position_size is not None:
                trade_size = max(1, int(self.config.position_size))
            else:
                stop_loss_price = self._calculate_stop_loss(current_price)
                risk_amount = (self._capital_commander.get_total_equity() *
                             self._capital_commander._risk_config.RISK_PER_TRADE_PCT)
                price_distance = abs(new_price - stop_loss_price)
                base_quantity = risk_amount / (price_distance * self.contract_val)  # 🔥 [修复] 考虑合约面值
                trade_size = max(1, int(base_quantity))

            success = await self._place_maker_order(
                symbol=self.symbol,
                price=new_price,
                stop_loss_price=self._calculate_stop_loss(current_price),
                size=trade_size
            )

            if success:
                logger.info(
                    f"✅ [插队成功] {self.symbol} @ {new_price:.6f}, "
                    f"数量={trade_size}, 合约面值={self.contract_val}"  # 🔥 [修复] 显示合约面值
                )

    async def _cancel_maker_order(self):
        """
        撤销 Maker 挂单

        🔥 保留撤单失败时查询订单真实状态，防止幽灵仓位
        """
        try:
            logger.info(f"🔄 撤销 Maker 挂单: {self.symbol}")

            if self._order_manager:
                try:
                    await self._order_manager.cancel_all_orders(symbol=self.symbol)
                except Exception as cancel_error:
                    error_msg = str(cancel_error)
                    logger.warning(
                        f"⚠️ [撤单异常] {self.symbol}: "
                        f"{error_msg}，正在核实订单真实状态..."
                    )

                    if self._maker_order_id and self._maker_order_id != "pending":
                        try:
                            if hasattr(self._order_manager, '_rest_gateway'):
                                rest_gateway = self._order_manager._rest_gateway
                                if hasattr(rest_gateway, 'get_order_status'):
                                    order_status = await rest_gateway.get_order_status(
                                        order_id=self._maker_order_id,
                                        symbol=self.symbol
                                    )

                                    if order_status:
                                        state = order_status.get('state', '').lower()
                                        if state == 'filled':
                                            logger.warning(
                                                f"🚨 [订单实际已成交] {self.symbol}: "
                                                f"订单 {self._maker_order_id} 在撤单失败后实际已成交！"
                                            )

                                            fill_event_data = {
                                                'order_id': self._maker_order_id,
                                                'symbol': self.symbol,
                                                'filled_size': float(order_status.get('fillSz', 0)),
                                                'price': float(order_status.get('avgPx', 0)),
                                                'side': 'buy',
                                                'stop_loss_price': self._maker_order_price
                                            }

                                            from ...core.event_types import Event, EventType
                                            fill_event = Event(
                                                type=EventType.ORDER_FILLED,
                                                data=fill_event_data,
                                                source="strategy_manual_sync"
                                            )

                                            await self.on_order_filled(fill_event)
                                            return
                        except Exception as sync_error:
                            logger.error(
                                f"❌ [订单状态查询失败] {self.symbol}: "
                                f"{str(sync_error)}"
                            )

            self._maker_order_id = None
            self._maker_order_time = 0.0

        except Exception as e:
            logger.error(f"撤单失败: {e}", exc_info=True)

    def _get_order_book_best_prices(self, current_price: float = 0.0) -> tuple:
        """
        获取订单簿最优买卖价（带降级策略）

        Args:
            current_price (float): 当前 Tick 的最新成交价（用于降级策略）

        Returns:
            tuple: (best_bid, best_ask) 如果没有数据返回 (0.0, 0.0)
        """
        try:
            if hasattr(self, 'public_gateway') and self.public_gateway:
                best_bid, best_ask = self.public_gateway.get_best_bid_ask()

                if best_bid is None or best_ask is None or best_bid <= 0 or best_ask <= 0:
                    if current_price > 0:
                        logger.warning(
                            f"⚠️ [降级策略] {self.symbol}: 订单簿数据不可用， "
                            f"使用 Last Price={current_price:.6f} 作为基准价格"
                        )
                        best_bid = current_price - self.config.tick_size
                        best_ask = current_price + self.config.tick_size
                    else:
                        return (0.0, 0.0)

                return (best_bid, best_ask)
            return (0.0, 0.0)
        except Exception as e:
            logger.error(f"获取订单簿价格失败: {e}", exc_info=True)
            return (0.0, 0.0)

    async def _check_exit_conditions(self, current_price: float, now: float):
        """
        检查出场条件（V2 - Trailing Stop）

        ✨ V2 新增：
        - 追踪止损：0.1% 起动，回撤 0.05% 触发
        - 时间止损：30 秒

        🔥 保留：
        - 硬止损：1.0%
        - None 检查（防止除零/None比较错误）

        Args:
            current_price (float): 当前价格
            now (float): 当前时间戳
        """
        # 🔥 保留：必须先检查 _entry_price 不为 None
        if self._entry_price is None or self._entry_price <= 0:
            return

        # 🔥 保留：计算盈亏百分比（防止除零错误）
        try:
            unrealized_pnl_pct = (current_price - self._entry_price) / self._entry_price
        except ZeroDivisionError:
            logger.error(
                f"🚨 [除零错误] {self.symbol}: "
                f"_entry_price={self._entry_price}, 跳过盈亏计算"
            )
            return

        # ✨ [V2] 追踪止损逻辑
        if unrealized_pnl_pct > self.config.trailing_stop_activation_pct:
            # 收益率超过激活阈值，更新最高收益率
            self.highest_pnl_pct = max(self.highest_pnl_pct, unrealized_pnl_pct)
            logger.debug(
                f"📈 [追踪止损] {self.symbol}: "
                f"PnL={unrealized_pnl_pct*100:.3f}%, "
                f"最高={self.highest_pnl_pct*100:.3f}%"
            )

        # ✨ [V2] 追踪止损触发：回撤超过阈值
        if (self.highest_pnl_pct > self.config.trailing_stop_activation_pct and
            unrealized_pnl_pct < (self.highest_pnl_pct - self.config.trailing_stop_callback_pct)):
            logger.info(
                f"🎯 [追踪止损触发] {self.symbol}: "
                f"entry={self._entry_price:.6f}, "
                f"current={current_price:.6f}, "
                f"pnl={unrealized_pnl_pct*100:+.3f}%, "
                f"最高={self.highest_pnl_pct*100:.3f}%, "
                f"回撤={self.highest_pnl_pct*100 - unrealized_pnl_pct*100:.3f}%"
            )
            await self._close_position(current_price, "trailing_stop")
            return

        # 2. 硬止损：-1% 立即走人（市价单）
        if unrealized_pnl_pct <= -self.config.stop_loss_pct:
            logger.warning(
                f"🛑 [硬止损离场] {self.symbol}: "
                f"entry={self._entry_price:.6f}, "
                f"current={current_price:.6f}, "
                f"loss={unrealized_pnl_pct*100:+.3f}%"
            )
            await self._close_position(current_price, "stop_loss")
            return

        # 3. ✨ [V2] 时间止损：30 秒不涨立即走人（市价单）
        # 🔥 保留：检查 _entry_time 不为 None
        if self._entry_time is None or self._entry_time <= 0:
            logger.warning(
                f"⚠️ [时间检查异常] {self.symbol}: "
                f"_entry_time={self._entry_time}, 跳过时间止损"
            )
            return

        time_elapsed = now - self._entry_time
        if time_elapsed >= self.config.time_limit_seconds:
            logger.info(
                f"⏱️ [时间止损] {self.symbol}: "
                f"entry={self._entry_price:.6f}, "
                f"current={current_price:.6f}, "
                f"耗时={time_elapsed:.2f}s, "
                f"pnl={unrealized_pnl_pct*100:+.3f}%"
            )
            await self._close_position(current_price, "time_stop")
            return

    async def _close_position(self, price: float, reason: str):
        """
        平仓（市价单）

        🔥 保留：
        - 从 OMS 获取真实持仓数量
        - 添加平仓锁机制（超时锁）
        - 添加异常保护

        🔥 保留 Negative Position Fix：不在 _check_exit_conditions 中重置 local_pos_size
        状态更新只依赖 on_order_filled

        Args:
            price (float): 平仓价格
            reason (str): 平仓原因（take_profit/stop_loss/time_stop/trailing_stop）
        """
        now = time.time()

        # 🔥 保留：超时锁机制
        if now - self._last_close_time < self._close_lock_timeout:
            remaining = self._close_lock_timeout - (now - self._last_close_time)
            logger.warning(
                f"🚫 [平仓锁] {self.symbol}: 正在平仓冷却中 "
                f"(剩余 {remaining:.1f}s)，拒绝重复平仓请求"
            )
            return

        if not self._position_opened:
            return

        # 🔥 保留：更新上锁时间
        self._last_close_time = now

        # 计算盈亏
        if self._entry_price > 0:
            pnl_pct = (price - self._entry_price) / self._entry_price

            # 更新统计
            self._total_trades += 1
            if pnl_pct > 0:
                self._win_trades += 1
            else:
                self._loss_trades += 1

        try:
            # 🔥 保留：使用 BaseStrategy 提供的 get_position 方法
            real_position = self.get_position(self.symbol)

            if real_position:
                real_pos_size = abs(real_position.size)
                logger.debug(
                    f"📊 [真实持仓] {self.symbol}: 本地={self.local_pos_size:.4f}, "
                    f"真实={real_pos_size:.4f}"
                )
            else:
                real_pos_size = self.local_pos_size
                logger.warning(
                    f"⚠️ [持仓回退] {self.symbol}: 无法获取真实持仓， "
                    f"使用本地记录={real_pos_size:.4f}"
                )

            # 🔥 保留：平仓（市价单，确保快速退出）
            success = await self.sell(
                symbol=self.symbol,
                entry_price=price,
                stop_loss_price=0,
                order_type='market',
                size=real_pos_size
            )

            if success:
                # 🔥 [保留 Negative Position Fix] 不在这里更新 local_pos_size
                # 状态更新必须只依赖 on_order_filled
                # 下单成功不代表成交，提前更新会导致负持仓问题
                logger.info(
                    f"🔄 [平仓下单成功] {self.symbol} @ {price:.6f}, "
                    f"reason={reason}, 数量={real_pos_size:.4f}, "
                    f"等待成交事件更新状态"
                )
        except Exception as e:
            # 🔥 保留：异常处理：立即释放锁，防止死锁
            logger.error(f"❌ [平仓失败] {self.symbol}: 下单失败: {str(e)}", exc_info=True)

            self._last_close_time = 0.0
            logger.warning(
                f"🔓 [平仓锁释放] {self.symbol}: 平仓异常，已立即释放锁，允许下次重试"
            )

    def _calculate_stop_loss(self, entry_price: float) -> float:
        """
        计算止损价格（基于波动率）

        Args:
            entry_price (float): 入场价格

        Returns:
            float: 止损价格
        """
        stop_loss = self._volatility_estimator.calculate_atr_based_stop(
            entry_price=entry_price,
            atr_multiplier=1.5
        )
        return stop_loss

    def update_config(self, **kwargs):
        """
        更新策略配置

        Args:
            **kwargs: 配置参数
        """
        if 'imbalance_ratio' in kwargs:
            self.config.imbalance_ratio = kwargs['imbalance_ratio']
            logger.info(f"imbalance_ratio 更新为 {kwargs['imbalance_ratio']:.2f}")

        if 'min_flow_usdt' in kwargs:
            self.config.min_flow_usdt = kwargs['min_flow_usdt']
            logger.info(f"min_flow_usdt 更新为 {kwargs['min_flow_usdt']:.0f} USDT")

        if 'take_profit_pct' in kwargs:
            self.config.take_profit_pct = kwargs['take_profit_pct']
            logger.info(f"take_profit_pct 更新为 {kwargs['take_profit_pct']*100:.2f}%")

        if 'stop_loss_pct' in kwargs:
            self.config.stop_loss_pct = kwargs['stop_loss_pct']
            logger.info(f"stop_loss_pct 更新为 {kwargs['stop_loss_pct']*100:.2f}%")

        if 'time_limit_seconds' in kwargs:
            self.config.time_limit_seconds = kwargs['time_limit_seconds']
            logger.info(f"time_limit_seconds 更新为 {kwargs['time_limit_seconds']}s")

        if 'position_size' in kwargs:
            self.config.position_size = kwargs['position_size']
            logger.info(f"position_size 更新为 {kwargs['position_size']:.4f}")

        if 'maker_timeout_seconds' in kwargs:
            self.config.maker_timeout_seconds = kwargs['maker_timeout_seconds']
            logger.info(f"maker_timeout_seconds 更新为 {kwargs['maker_timeout_seconds']}s")

        # ✨ V2 新增配置
        if 'trailing_stop_activation_pct' in kwargs:
            self.config.trailing_stop_activation_pct = kwargs['trailing_stop_activation_pct']
            logger.info(
                f"trailing_stop_activation_pct 更新为 "
                f"{kwargs['trailing_stop_activation_pct']*100:.3f}%"
            )

        if 'trailing_stop_callback_pct' in kwargs:
            self.config.trailing_stop_callback_pct = kwargs['trailing_stop_callback_pct']
            logger.info(
                f"trailing_stop_callback_pct 更新为 "
                f"{kwargs['trailing_stop_callback_pct']*100:.3f}%"
            )

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取策略统计信息

        Returns:
            dict: 统计数据
        """
        base_stats = super().get_statistics()

        win_rate = (
            self._win_trades / self._total_trades * 100
            if self._total_trades > 0 else 0.0
        )

        base_stats.update({
            'strategy': 'ScalperV1',
            'mode': 'Sniper V2',  # 标识为 Sniper 模式
            'version': '2.0',
            'config': {
                'imbalance_ratio': self.config.imbalance_ratio,
                'min_flow_usdt': self.config.min_flow_usdt,
                'take_profit_pct': self.config.take_profit_pct * 100,
                'stop_loss_pct': self.config.stop_loss_pct * 100,
                'time_limit_seconds': self.config.time_limit_seconds,
                'maker_timeout_seconds': self.config.maker_timeout_seconds,
                # ✨ V2 新增
                'trailing_stop_activation_pct': self.config.trailing_stop_activation_pct * 100,
                'trailing_stop_callback_pct': self.config.trailing_stop_callback_pct * 100,
                'ema_period': self.config.ema_period,
                'spread_threshold_pct': self.config.spread_threshold_pct * 100
            },
            'trading': {
                'total_trades': self._total_trades,
                'win_trades': self._win_trades,
                'loss_trades': self._loss_trades,
                'win_rate': win_rate
            },
            'microstructure': {
                'buy_vol_current': self.buy_vol,
                'sell_vol_current': self.sell_vol,
                'imbalance_current': (
                    self.buy_vol / self.sell_vol
                    if self.sell_vol > 0 else 0.0
                ),
                'max_imbalance_seen': self._max_imbalance_seen
            },
            # ✨ V2 新增
            'trend': {
                'ema_value': self.ema_value,
                'trend_bias': self._get_trend_bias(),
                'price_history_len': len(self.price_history)
            },
            'position': {
                'is_open': self._position_opened,
                'has_maker_order': self._maker_order_id is not None,
                'entry_price': self._entry_price,
                'entry_time': self._entry_time,
                'hold_time': (
                    time.time() - self._entry_time
                    if self._position_opened and self._entry_time > 0 else 0.0
                ),
                # ✨ V2 新增
                'highest_pnl_pct': self.highest_pnl_pct * 100
            },
            'volatility': {
                'current': self._volatility_estimator.get_volatility() * 100,
                'samples': self._volatility_estimator.samples_count
            }
        })

        return base_stats

    def reset_statistics(self):
        """重置统计信息"""
        # 重置 V2 统计信息
        self._total_trades = 0
        self._win_trades = 0
        self._loss_trades = 0
        self._max_imbalance_seen = 0.0

        # ✨ V2 新增：重置追踪止损
        self.highest_pnl_pct = 0.0

        logger.info(
            f"ScalperV1 V2 统计信息已重置 "
            f"(total_trades={self._total_trades}, win_trades={self._win_trades})"
        )

    def reset_state(self):
        """重置策略状态（包括持仓）"""
        # 重置成交量窗口
        self.vol_window_start = 0.0
        self.buy_vol = 0.0
        self.sell_vol = 0.0

        # 重置持仓状态
        self._entry_price = 0.0
        self._entry_time = 0.0
        self._position_opened = False

        # 重置 Maker 挂单状态
        self._maker_order_id = None
        self._maker_order_time = 0.0

        # 重置本地持仓记录
        self.local_pos_size = 0.0

        # 重置统计
        self._total_trades = 0
        self._win_trades = 0
        self._loss_trades = 0
        self._max_imbalance_seen = 0.0

        # ✨ V2 新增：重置趋势和追踪止损
        self.price_history.clear()
        self.ema_value = 0.0
        self.highest_pnl_pct = 0.0

        # 重置波动率估算器
        self._volatility_estimator.reset()

        logger.info(f"ScalperV1 V2 状态已完全重置")
