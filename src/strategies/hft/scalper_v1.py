"""
ScalperV1 极速剥头皮策略 (ScalperV1 - Micro-Imbalance Strategy)

专门针对 1核 1G 内存、1ms 延迟环境优化的微观结构剥头皮策略。

策略核心逻辑：
1. 完全不看 K 线，只处理 on_tick (Trade Stream)
2. 极速计算：使用原生 Python float 累加成交量
3. 动量触发：当 1秒内买入量 > 卖出量 * 3 且买入量 > 阈值时，立即限价挂单（Maker模式）
4. 光速离场：
   - 止盈：+0.2% 立即走人（市价单）
   - 止损：+5秒不涨立即走人 (Time Stop，市价单）

优化特点：
- O(1) 时间复杂度：只维护累加器，不做任何列表操作
- 零历史数据：不存储 Ticks，只维护当前秒的成交量
- 极速计算：每秒重置窗口，比 deque 快得多
- 轻量级依赖：严禁使用 pandas，只使用原生 Python
- Maker 模式：开仓使用限价单，降低手续费，平仓使用市价单

Example:
    >>> scalper = ScalperV1(
    ...     event_bus=event_bus,
    ...     order_manager=order_manager,
    ...     capital_commander=capital_commander,
    ...     symbol="BTC-USDT-SWAP",
    ...     imbalance_ratio=3.0,
    ...     min_flow_usdt=1000.0
    ... )
    >>> await scalper.start()
"""

import time
import asyncio
import logging
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
    """ScalperV1 策略配置"""
    symbol: str = "BTC-USDT-SWAP"
    imbalance_ratio: float = 3.0          # 买量 > 卖量 * ratio 才触发
    min_flow_usdt: float = 1000.0        # 最小流速（USDT），过滤杂波
    take_profit_pct: float = 0.002       # 止盈 0.2%
    stop_loss_pct: float = 0.01          # 硬止损 1%
    time_limit_seconds: int = 5          # 时间止损 5 秒
    cooldown_seconds: int = 10          # 交易冷却（秒）
    position_size: Optional[float] = None  # 仓位大小（None=基于风险计算）
    maker_timeout_seconds: float = 2.0    # [新增] Maker 挂单超时时间（秒）
    # ✨ 新增：插队和追单配置
    tick_size: float = 0.01              # 最小价格跳动单位（默认 0.01 USDT）
    max_chase_distance_pct: float = 0.001 # 最大追单距离（默认 0.1%），防止无限追高
    enable_chasing: bool = True          # 是否启用追单机制（默认启用）


class ScalperV1(BaseStrategy):
    """
    ScalperV1 极速剥头皮策略（Maker 模式）

    基于微观结构失衡的超短线剥头皮策略。

    策略逻辑：
    1. 监听 Trade Stream（每笔成交）
    2. 累加 1 秒窗口内的买卖量
    3. 检测买卖失衡（买 >> 卖）
    4. 开仓：使用限价单挂单（Maker 模式）
    5. 平仓：使用市价单（确保快速退出）

    优化特点：
    - O(1) 时间复杂度
    - 零历史数据存储
    - 极速计算
    - Maker 模式：降低手续费
    """

    def __init__(
        self,
        event_bus: EventBus,
        order_manager: OrderManager,
        capital_commander: CapitalCommander,
        symbol: str = "BTC-USDT-SWAP",
        imbalance_ratio: float = 3.0,
        min_flow_usdt: float = 1000.0,
        take_profit_pct: float = 0.002,
        stop_loss_pct: float = 0.01,
        time_limit_seconds: int = 5,
        position_size: Optional[float] = None,
        mode: str = "PRODUCTION",
        strategy_id: Optional[str] = None,
        # ✨ 新增参数（HFT 策略应默认为极短冷却）
        cooldown_seconds: float = 0.1,
        # ✨ 容错参数（吃掉所有未定义的参数，防止崩溃）
        **kwargs
    ):
        """
        初始化 ScalperV1 策略

        Args:
            event_bus (EventBus): 事件总线
            order_manager (OrderManager): 订单管理器
            capital_commander (CapitalCommander): 资金指挥官
            symbol (str): 交易对
            imbalance_ratio (float): 买卖失衡比例（默认 3.0 = 买量是卖量的 3 倍）
            min_flow_usdt (float): 最小流速（USDT），过滤杂波
            take_profit_pct (float): 止盈百分比（默认 0.002 = 0.2%）
            stop_loss_pct (float): 硬止损百分比（默认 0.01 = 1%）
            time_limit_seconds (int): 时间止损（秒），默认 5 秒
            position_size (float): 仓位大小（None=基于风险计算）
            mode (str): 策略模式（PRODUCTION/DEV）
            strategy_id (str): 策略 ID
        """
        super().__init__(
            event_bus=event_bus,
            order_manager=order_manager,
            capital_commander=capital_commander,
            symbol=symbol,
            mode=mode,
            strategy_id=strategy_id,
            cooldown_seconds=cooldown_seconds  # [FIX] 传递冷却时间给基类
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
            cooldown_seconds=0,  # [FIX] HFT 策略强制无冷却
            maker_timeout_seconds=2.0  # 默认2秒超时
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

        # [新增] 本地强持仓记录（不依赖 PositionManager）
        self.local_pos_size = 0.0

        # [新增] 冷却机制：防止平仓后立即重新开仓
        self._last_close_time = 0.0  # 上次平仓时间戳

        # [新增] 开仓锁机制：防止重复开仓
        self._is_pending_open = False  # 是否有在途的开仓请求

        # 🔥 新增：开仓锁超时保护（防止事件丢失导致死锁）
        self._pending_open_timeout = 60.0  # 60秒无响应则强制解锁

        # 🔥 新增：平仓锁机制（防止"机枪平仓"重复下单）- 升级为超时锁
        self._last_close_time = 0.0  # 上次平仓时间戳（用于防止连发）
        self._close_lock_timeout = 10.0  # 平仓锁超时时间（秒）

        # [新增] Maker 挂单管理
        self._maker_order_id = None          # 当前挂单 ID
        self._maker_order_time = 0.0        # 挂单时间戳
        self._maker_order_price = 0.0        # 挂单价格
        self._maker_order_initial_price = 0.0  # 初始信号价格（用于追单风控）

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
            time_limit_seconds=time_limit_seconds,  # 5 秒强制平仓
            single_loss_cap_pct=0.02,             # 单笔最大亏损 2%
            max_order_size_usdt=500.0,            # HFT 快进快出，单笔较小
            max_daily_loss_pct=0.05                # 每日最大亏损 5%
        ))

        logger.info(
            f"🚀 ScalperV1 初始化（Maker 模式）: symbol={symbol}, "
            f"imbalance_ratio={imbalance_ratio}, "
            f"min_flow={min_flow_usdt} USDT, "
            f"take_profit={take_profit_pct*100:.2f}%, "
            f"time_stop={time_limit_seconds}s, "
            f"maker_timeout={2.0}s"
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

        [FIX] 强制重置冷却时间，确保 HFT 逻辑不被拦截
        """
        # 调用基类的 start 方法
        await super().start()

        # [FIX] 强制移除冷却，确保 HFT 逻辑不被拦截
        self.config.cooldown_seconds = 0
        logger.info("🚀 [HFT 模式] ScalperV1 冷却时间已强制设为 0s")

    def _is_cooling_down(self) -> bool:
        """
        检查是否处于冷却期

        Returns:
            bool: 是否处于冷却期
        """
        now = time.time()
        return now - self._last_close_time < self.config.cooldown_seconds

    async def on_tick(self, event: Event):
        """
        处理 Tick 事件（策略核心逻辑）

        每秒滑动窗口，累加买卖量，检测失衡并触发交易。

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

            # 🔥 修复：强制对账逻辑 - 检查本地持仓是否异常
            # 假设每次开仓是2.0手，超过4.0肯定不对
            if abs(self.local_pos_size) > 4.0:
                self.logger.warning(
                    f"⚠️  [持仓异常] {self.symbol}: "
                    f"本地持仓异常 ({self.local_pos_size:.2f})，强制重置为 0"
                )
                self.local_pos_size = 0.0
                self._position_opened = False
                # 可选：尝试调用一次 API 同步
                return

            # [FIX] 如果在冷却中，直接静默跳过，节省 CPU 和日志空间
            if self._is_cooling_down():
                return

            now = time.time()

            # 🔥 修复 1：时间计算必须先检查 self._entry_time 不为 None
            # 🔥 修复 2：开仓锁超时保护必须先检查 self._maker_order_time 不为 None
            # 防止打印"卡住 50 年"的错误日志，以及除零/None比较错误

            # 🔥 新增：开仓锁超时保护（防止事件丢失导致死锁）
            if self._is_pending_open and self._maker_order_time is not None:  # 🔥 关键：先检查不为 None
                time_locked = now - self._maker_order_time
                if time_locked > self._pending_open_timeout:
                    logger.error(
                        f"🚨 [死锁解除] {self.symbol}: "
                        f"开仓锁已卡住 {time_locked:.1f}s (可能是事件丢失)，强制重置状态！"
                    )
                    # 强制重置状态
                    self._is_pending_open = False
                    self._maker_order_id = None
                    # 🔥 修复：重置本地记录，防止残余仓位累积
                    self.local_pos_size = 0.0
                    self._position_opened = False

            # 1. 检查挂单超时（Maker 挂单管理）
            if self._maker_order_id is not None:
                if now - self._maker_order_time >= self.config.maker_timeout_seconds:
                    # 超时，撤单
                    logger.warning(
                        f"⏰ [Maker 超时] {self.symbol} 挂单 {self._maker_order_id} "
                        f"未成交，超时 {self.config.maker_timeout_seconds}s，撤单"
                    )
                    await self._cancel_maker_order()

            # 2. 窗口重置（每秒重置一次，比 deque 快得多）
            if now - self.vol_window_start >= 1.0:
                self.buy_vol = 0.0
                self.sell_vol = 0.0
                self.vol_window_start = now

            # 3. 解析 Tick 数据（极速提取）
            data = event.data
            symbol = data.get('symbol')
            price = float(data.get('price', 0))
            size = float(data.get('size', 0))
            side = data.get('side', '').lower()
            usdt_val = price * size

            # 4. 检查交易对是否匹配
            if symbol != self.symbol:
                return

            # 5. 增加 Tick 计数
            self._increment_ticks()

            # 6. 累加成交量（只做加法，极快）
            if side == 'buy':
                self.buy_vol += usdt_val
            elif side == 'sell':
                self.sell_vol += usdt_val

            # 7. 更新波动率估算器（用于动态止损）
            if self._previous_price > 0:
                self._volatility_estimator.update_volatility(
                    current_price=price,
                    previous_close=self._previous_price
                )
            self._previous_price = price

            # 8. 持仓管理（检查止盈/止损/时间止损）
            if self._position_opened:
                await self._check_exit_conditions(price, now)

            # 9. 追单机制（监控已挂订单）
            if self._maker_order_id is not None:
                await self._check_chasing_conditions(price, now)

            # 10. 触发逻辑（仅空仓且无挂单时检查）
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

        Args:
            event (Event): ORDER_FILLED 事件
        """
        try:
            data = event.data
            symbol = data.get('symbol', '')

            # 只处理当前交易对的订单
            if symbol != self.symbol:
                return

            # 🔥 修复：防御性解锁（防止事件丢失）
            # 只要检测到本策略的成交事件，都尝试解锁
            if self._is_pending_open:
                logger.info(f"✅ [开仓成交] {self.symbol}: 解锁开仓锁")
                self._is_pending_open = False
                self._maker_order_id = None  # 清理挂单ID

                # 记录持仓信息
                side = data.get('side', '').lower()
                filled_size = float(data.get('filled_size', 0))

                if side == 'buy':
                    self._position_opened = True
                    self._entry_price = float(data.get('price', 0))
                    self._entry_time = time.time()
                    self.local_pos_size = filled_size

                    logger.info(
                        f"📊 [开仓成功] {self.symbol} @ {self._entry_price:.2f}, "
                        f"数量={filled_size:.4f}"
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

            # 只处理当前交易对的订单
            if symbol != self.symbol:
                return

            # 检查是否是我们的开仓订单被取消
            if self._is_pending_open:
                logger.warning(f"🚫 [开仓失败] {self.symbol}: 订单被取消，解锁开仓锁")
                self._is_pending_open = False
        except Exception as e:
            logger.error(f"处理订单取消事件失败: {e}", exc_info=True)

    async def _check_entry_conditions(self, price: float, now: float):
        """
        检查入场条件（买卖失衡触发）- Maker 模式

        Args:
            price (float): 当前价格
            now (float): 当前时间戳
        """
        # 初始化变量，防止 UnboundLocalError
        imbalance = 0.0

        # 1. 检查当前窗口（1秒）内的总活跃度
        # 使用总成交量（买入+卖出）来判断市场活跃度，而不是只检查买入量
        total_vol = self.buy_vol + self.sell_vol
        if total_vol < self.config.min_flow_usdt:
            return

        # 2. 检查买卖失衡
        # 买量 > 卖量 * ratio 才触发
        if self.buy_vol > self.sell_vol * self.config.imbalance_ratio:
            # 记录最大失衡比
            if self.sell_vol > 0:
                imbalance = self.buy_vol / self.sell_vol
                self._max_imbalance_seen = max(self._max_imbalance_seen, imbalance)

            logger.info(
                f"🎯 [失衡触发] {self.symbol}: "
                f"买={self.buy_vol:.0f} USDT, "
                f"卖={self.sell_vol:.0f} USDT, "
                f"失衡比={imbalance:.2f}x, "
                f"价格={price:.2f}"
            )

            # 3. 获取订单簿数据（Best Bid/Ask）- 带降级策略
            best_bid, best_ask = self._get_order_book_best_prices(price)

            # 🛡️ 保护：如果拿不到价格，绝对不要开仓
            if best_bid <= 0 or best_ask <= 0:
                logger.warning("订单簿数据不可用，跳过本次开仓")
                return

            # 4. 计算 Maker 挂单价格（插队机制）
            # 使用 min(Best Bid + Tick, Best Ask - Tick)
            # 在买一价基础上加一个最小跳动单位，抢占第一排位，但绝不直接吃掉卖单（保持 Maker 身份）
            aggressive_bid = best_bid + self.config.tick_size
            conservative_ask = best_ask - self.config.tick_size
            maker_price = min(aggressive_bid, conservative_ask)

            logger.info(
                f"📊 [插队挂单] {self.symbol}: "
                f"Best Bid={best_bid:.2f}, Best Ask={best_ask:.2f}, "
                f"挂单价格={maker_price:.2f} (插队+{self.config.tick_size})"
            )

            # 5. 计算止损价格（基于波动率）
            stop_loss_price = self._calculate_stop_loss(price)

            logger.debug(
                f"🛡️  [止损计算] entry={price:.2f}, "
                f"stop={stop_loss_price:.2f}, "
                f"距离={abs(price - stop_loss_price):.2f}"
            )

            # 6. 计算交易数量（强制整数，至少 1）
            if self.config.position_size is not None:
                # 使用固定仓位，但确保至少为 1
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

            # 7. Maker 挂单（限价单）
            success = await self._place_maker_order(
                symbol=self.symbol,
                price=maker_price,
                stop_loss_price=stop_loss_price,
                size=trade_size
            )

            if success:
                self._increment_signals()
                logger.info(
                    f"✅ [Maker 挂单已提交] {self.symbol} @ {maker_price:.2f}, "
                    f"数量={trade_size}, 止损={stop_loss_price:.2f}"
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
        # 1. 【新增】检查是否已经有在途的开仓请求
        if self._is_pending_open:
            logger.warning(
                f"🚫 [风控拦截] {self.symbol}: 上一个开仓请求尚未结束，拒绝重复开仓"
            )
            return False

        try:
            # 2. 【新增】上锁
            self._is_pending_open = True

            # 调用基类下单方法，限价单
            success = await self.buy(
                symbol=symbol,
                entry_price=price,
                stop_loss_price=stop_loss_price,
                order_type='limit',  # Maker 模式使用限价单
                size=size
            )

            if success:
                # 记录挂单信息（用于追单机制）
                self._maker_order_id = "pending"  # 临时标记
                self._maker_order_time = time.time()
                self._maker_order_price = price  # 记录挂单价格
                self._maker_order_initial_price = price  # 记录初始信号价格
            else:
                # 下单失败，解锁
                self._is_pending_open = False

            return success
        except Exception as e:
            # 异常解锁
            self._is_pending_open = False
            logger.error(f"❌ [Maker 挂单失败] {self.symbol}: 下单失败: {str(e)}")
            return False

    async def _check_chasing_conditions(self, current_price: float, now: float):
        """
        检查追单条件（追单机制）

        如果发现 Market Best Bid 已经超过了 My Order Price（说明我被挤下去了），
        且时间未到超时时间，则立即撤销当前订单并重新挂单。

        🔥 修复：增加持仓检查，防止追单竞态条件导致重复开仓

        Args:
            current_price (float): 当前价格
            now (float): 当前时间戳
        """
        # 检查是否启用追单机制
        if not self.config.enable_chasing:
            return

        # 检查挂单是否存在
        if self._maker_order_id is None or self._maker_order_price <= 0:
            return

        # 🔥 修复 1: Pre-Check - 在进入追单逻辑前，检查是否已有持仓
        # 防止：Maker Order 刚成交，检测到价格变化触发追单，导致重复开仓
        if self._position_opened or abs(self.local_pos_size) > 0.001:
            logger.warning(
                f"🛑 [追单拦截] {self.symbol}: "
                f"检测到已有持仓 ({self.local_pos_size:.4f})，停止追单"
            )
            # 重置挂单状态，防止后续误判
            self._maker_order_id = None
            self._maker_order_price = 0.0
            return

        # 获取当前订单簿数据
        best_bid, best_ask = self._get_order_book_best_prices()

        # 🛡️ 保护：如果拿不到价格，不进行追单
        if best_bid <= 0:
            return

        # 判断是否需要追单
        # 如果 Market Best Bid > My Order Price，说明我被挤到队列后面了
        if best_bid > self._maker_order_price:
            # 计算追单距离（风控保护）
            chase_distance = abs(best_bid - self._maker_order_initial_price) / self._maker_order_initial_price

            # 🛡️ 风控：如果追单距离超过最大限制，放弃追单
            if chase_distance > self.config.max_chase_distance_pct:
                logger.warning(
                    f"🛑 [追单放弃] {self.symbol}: "
                    f"追单距离={chase_distance*100:.2f}% > "
                    f"最大限制={self.config.max_chase_distance_pct*100:.2f}%, "
                    f"撤单并放弃"
                )
                await self._cancel_maker_order()
                return

            # 计算新的挂单价格（插队机制）
            aggressive_bid = best_bid + self.config.tick_size
            conservative_ask = best_ask - self.config.tick_size
            new_price = min(aggressive_bid, conservative_ask)

            logger.info(
                f"🔄 [追单触发] {self.symbol}: "
                f"原价格={self._maker_order_price:.2f}, "
                f"新Best Bid={best_bid:.2f}, "
                f"新价格={new_price:.2f} "
                f"(追单距离={chase_distance*100:.2f}%)"
            )

            # 撤销旧订单
            await self._cancel_maker_order()

            # 等待一小段时间确保撤单完成（避免订单冲突）
            await asyncio.sleep(0.1)

            # 🔥 修复 2: Double-Check - 撤单后，在下新单前再次检查持仓
            # 防止：撤单期间订单已成交，导致重复开仓
            if self._position_opened or abs(self.local_pos_size) > 0.001:
                logger.warning(
                    f"🛑 [追单拦截] {self.symbol}: "
                    f"撤单期间订单已成交 (持仓={self.local_pos_size:.4f})，取消发送新单"
                )
                return

            # 重新挂单（使用新价格）
            # 注意：这里需要重新计算交易数量，保持一致性
            if self.config.position_size is not None:
                trade_size = max(1, int(self.config.position_size))
            else:
                # 基于风险计算仓位
                stop_loss_price = self._calculate_stop_loss(current_price)
                risk_amount = (self._capital_commander.get_total_equity() *
                             self._capital_commander._risk_config.RISK_PER_TRADE_PCT)
                price_distance = abs(new_price - stop_loss_price)
                base_quantity = risk_amount / price_distance
                trade_size = max(1, int(base_quantity))

            # 重新挂单
            success = await self._place_maker_order(
                symbol=self.symbol,
                price=new_price,
                stop_loss_price=self._calculate_stop_loss(current_price),
                size=trade_size
            )

            if success:
                logger.info(
                    f"✅ [追单成功] {self.symbol} @ {new_price:.2f}, "
                    f"数量={trade_size}"
                )

    async def _cancel_maker_order(self):
        """
        撤销 Maker 挂单

        注意：由于我们没有记录真实的订单 ID，这里只能通过 CancelAll 实现
        """
        try:
            logger.info(f"🔄 撤销 Maker 挂单: {self.symbol}")

            # 撤销所有挂单（简化处理）
            if self._order_manager:
                await self._order_manager.cancel_all_orders(symbol=self.symbol)

            # 重置挂单状态
            self._maker_order_id = None
            self._maker_order_time = 0.0

        except Exception as e:
            logger.error(f"撤单失败: {e}", exc_info=True)

    def _get_order_book_best_prices(self, current_price: float = 0.0) -> tuple:
        """
        获取订单簿最优买卖价（带降级策略）

        当订单簿数据不可用时，使用当前 Tick 的最新成交价作为临时基准价格：
        - 临时 Bid = Last Price - TickSize
        - 临时 Ask = Last Price + TickSize

        Args:
            current_price (float): 当前 Tick 的最新成交价（用于降级策略）

        Returns:
            tuple: (best_bid, best_ask) 如果没有数据返回 (0.0, 0.0)
        """
        try:
            if hasattr(self, 'public_gateway') and self.public_gateway:
                best_bid, best_ask = self.public_gateway.get_best_bid_ask()

                # 🛡️ 降级策略：订单簿数据不可用时使用 Last Price
                if best_bid is None or best_ask is None or best_bid <= 0 or best_ask <= 0:
                    if current_price > 0:
                        logger.warning(
                            f"⚠️ [降级策略] {self.symbol}: 订单簿数据不可用， "
                            f"使用 Last Price={current_price:.2f} 作为基准价格"
                        )
                        # 临时 Bid = Last Price - TickSize
                        best_bid = current_price - self.config.tick_size
                        # 临时 Ask = Last Price + TickSize
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
        检查出场条件（止盈/止损/时间止损）

        🔥 修复：添加 None 检查，防止除零/None比较错误
        Args:
            current_price (float): 当前价格
            now (float): 当前时间戳
        """
        # 🔥 修复 1：必须先检查 _entry_price 不为 None
        if self._entry_price is None or self._entry_price <= 0:
            return

        # 🔥 修复 2：计算盈亏百分比（防止除零错误）
        try:
            pnl_pct = (current_price - self._entry_price) / self._entry_price
        except ZeroDivisionError:
            logger.error(
                f"🚨 [除零错误] {self.symbol}: "
                f"_entry_price={self._entry_price}, 跳过盈亏计算"
            )
            return

        # 1. 止盈：+0.2% 立即走人（市价单）
        if pnl_pct >= self.config.take_profit_pct:
            logger.info(
                f"💰 [止盈离场] {self.symbol}: "
                f"entry={self._entry_price:.2f}, "
                f"current={current_price:.2f}, "
                f"profit={pnl_pct*100:+.2f}%"
            )
            await self._close_position(current_price, "take_profit")
            return

        # 2. 硬止损：-1% 立即走人（市价单）
        if pnl_pct <= -self.config.stop_loss_pct:
            logger.warning(
                f"🛑 [止损离场] {self.symbol}: "
                f"entry={self._entry_price:.2f}, "
                f"current={current_price:.2f}, "
                f"loss={pnl_pct*100:+.2f}%"
            )
            await self._close_position(current_price, "stop_loss")
            return

        # 3. 时间止损：5 秒不涨立即走人（市价单）
        # 🔥 修复 3：检查 _entry_time 不为 None，防止 None 比较错误
        if self._entry_time is None or self._entry_time <= 0:
            logger.warning(
                f"⚠️  [时间检查异常] {self.symbol}: "
                f"_entry_time={self._entry_time}, 跳过时间止损"
            )
            return

        time_elapsed = now - self._entry_time
        if time_elapsed >= self.config.time_limit_seconds:
            logger.info(
                f"⏱️  [时间止损] {self.symbol}: "
                f"entry={self._entry_price:.2f}, "
                f"current={current_price:.2f}, "
                f"耗时={time_elapsed:.2f}s, "
                f"pnl={pnl_pct*100:+.2f}%"
            )
            await self._close_position(current_price, "time_stop")
            return

    async def _close_position(self, price: float, reason: str):
        """
        平仓（市价单）

        🔥 修复：从 OMS 获取真实持仓数量，避免残余持仓
        🔥 修复：添加平仓锁机制（超时锁），防止重复下单（防止"机枪平仓"）
        🔥 修复：添加异常保护，防止下单失败导致死锁

        Args:
            price (float): 平仓价格
            reason (str): 平仓原因（take_profit/stop_loss/time_stop）
        """
        now = time.time()

        # 🔥 1. 超时锁机制：检查是否在冷却期内
        if now - self._last_close_time < self._close_lock_timeout:
            remaining = self._close_lock_timeout - (now - self._last_close_time)
            logger.warning(
                f"🚫 [平仓锁] {self.symbol}: 正在平仓冷却中 "
                f"(剩余 {remaining:.1f}s)，拒绝重复平仓请求"
            )
            return

        if not self._position_opened:
            return

        # 🔥 2. 更新上锁时间
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
            # 🔥 修复：使用 BaseStrategy 提供的 get_position 方法
            # 不再依赖本地记录的 self.local_pos_size，避免漏单导致残余持仓
            real_position = self.get_position(self.symbol)

            if real_position:
                real_pos_size = abs(real_position.size)
                logger.debug(
                    f"📊 [真实持仓] {self.symbol}: 本地={self.local_pos_size:.4f}, "
                    f"真实={real_pos_size:.4f}"
                )
            else:
                # 如果获取不到持仓，回退到本地记录
                real_pos_size = self.local_pos_size
                logger.warning(
                    f"⚠️ [持仓回退] {self.symbol}: 无法获取真实持仓， "
                    f"使用本地记录={real_pos_size:.4f}"
                )

            # 🔥 3. 平仓（市价单，确保快速退出）
            success = await self.sell(
                symbol=self.symbol,
                entry_price=price,  # 平仓时的价格
                stop_loss_price=0,   # 无需止损
                order_type='market',  # 市价单快速退出
                size=real_pos_size  # 🔥 使用真实持仓数量
            )

            if success:
                self._position_opened = False
                self._entry_price = 0.0
                self._entry_time = 0.0

                # 平仓后重置本地记录
                self.local_pos_size = 0.0

                # 🔥 修复：重置 Maker 挂单状态
                self._maker_order_id = None
                self._maker_order_time = 0.0
                self._maker_order_price = 0.0
                self._maker_order_initial_price = 0.0
                self._is_pending_open = False  # 确保开仓锁被清除

                logger.info(
                    f"🔄 [平仓完成] {self.symbol} @ {price:.2f}, "
                    f"reason={reason}, 数量={real_pos_size:.4f}, "
                    f"状态已完全重置"
                )
        except Exception as e:
            # 🔥 4. 异常处理：立即释放锁，防止死锁
            logger.error(f"❌ [平仓失败] {self.symbol}: 下单失败: {str(e)}", exc_info=True)

            # 🔥 关键修复：立即重置锁，允许下一帧重试
            self._last_close_time = 0.0
            logger.warning(
                f"🔓 [平仓锁释放] {self.symbol}: 平仓异常，已立即释放锁，允许下次重试"
            )

            # 注意：即使平仓失败，也不重置持仓状态，等待下次尝试

    def _calculate_stop_loss(self, entry_price: float) -> float:
        """
        计算止损价格（基于波动率）

        Args:
            entry_price (float): 入场价格

        Returns:
            float: 止损价格
        """
        # 使用波动率估算器计算止损
        stop_loss = self._volatility_estimator.calculate_atr_based_stop(
            entry_price=entry_price,
            atr_multiplier=1.5  # 保守的 1.5 倍
        )
        return stop_loss

    def update_config(self, **kwargs):
        """
        更新策略配置

        Args:
            **kwargs: 配置参数
                - imbalance_ratio: float
                - min_flow_usdt: float
                - take_profit_pct: float
                - stop_loss_pct: float
                - time_limit_seconds: int
                - position_size: float
                - maker_timeout_seconds: float
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

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取策略统计信息

        Returns:
            dict: 统计数据
        """
        base_stats = super().get_statistics()

        # 计算胜率
        win_rate = (
            self._win_trades / self._total_trades * 100
            if self._total_trades > 0 else 0.0
        )

        base_stats.update({
            'strategy': 'ScalperV1',
            'mode': 'Maker',  # 标识为 Maker 模式
            'config': {
                'imbalance_ratio': self.config.imbalance_ratio,
                'min_flow_usdt': self.config.min_flow_usdt,
                'take_profit_pct': self.config.take_profit_pct * 100,
                'stop_loss_pct': self.config.stop_loss_pct * 100,
                'time_limit_seconds': self.config.time_limit_seconds,
                'maker_timeout_seconds': self.config.maker_timeout_seconds
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
            'position': {
                'is_open': self._position_opened,
                'has_maker_order': self._maker_order_id is not None,
                'entry_price': self._entry_price,
                'entry_time': self._entry_time,
                'hold_time': (
                    time.time() - self._entry_time
                    if self._position_opened and self._entry_time > 0 else 0.0
                )
            },
            'volatility': {
                'current': self._volatility_estimator.get_volatility() * 100,
                'samples': self._volatility_estimator.samples_count
            }
        })

        return base_stats

    def reset_statistics(self):
        """重置统计信息"""
        super().reset_statistics()

        self._total_trades = 0
        self._win_trades = 0
        self._loss_trades = 0
        self._max_imbalance_seen = 0.0

        # 不重置持仓状态，因为可能有持仓
        logger.info(
            f"ScalperV1 统计信息已重置 "
            f"(total_trades={self._total_trades}, win_trades={self._win_trades})"
        )

    def reset_state(self):
        """重置策略状态（包括持仓）"""
        super().reset_state()

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

        # 重置波动率估算器
        self._volatility_estimator.reset()

        logger.info(f"ScalperV1 状态已完全重置")
