"""
ScalperV1 极速剥头皮策略 (ScalperV1 - Micro-Imbalance Strategy)

专门针对 1核 1G 内存、1ms 延迟环境优化的微观结构剥头皮策略。

策略核心逻辑：
1. 完全不看 K 线，只处理 on_tick (Trade Stream)
2. 极速计算：使用原生 Python float 累加成交量
3. 动量触发：当 1秒内买入量 > 卖出量 * 3 且买入量 > 阈值时，立即市价买入
4. 光速离场：
   - 止盈：+0.2% 立即走人
   - 止损：+5秒不涨立即走人 (Time Stop)

优化特点：
- O(1) 时间复杂度：只维护累加器，不做任何列表操作
- 零历史数据：不存储 Ticks，只维护当前秒的成交量
- 极速计算：每秒重置窗口，比 deque 快得多
- 轻量级依赖：严禁使用 pandas，只使用原生 Python

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
    position_size: Optional[float] = None  # 仓位大小（None=基于风险计算）


class ScalperV1(BaseStrategy):
    """
    ScalperV1 极速剥头皮策略

    基于微观结构失衡的超短线剥头皮策略。

    策略逻辑：
    1. 监听 Trade Stream（每笔成交）
    2. 累加 1 秒窗口内的买卖量
    3. 检测买卖失衡（买 >> 卖）
    4. 立即开仓，光速离场

    优化特点：
    - O(1) 时间复杂度
    - 零历史数据存储
    - 极速计算
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
        strategy_id: Optional[str] = None
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
            strategy_id=strategy_id
        )

        # 策略配置
        self.config = ScalperV1Config(
            symbol=symbol,
            imbalance_ratio=imbalance_ratio,
            min_flow_usdt=min_flow_usdt,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            time_limit_seconds=time_limit_seconds,
            position_size=position_size
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
            f"🚀 ScalperV1 初始化: symbol={symbol}, "
            f"imbalance_ratio={imbalance_ratio}, "
            f"min_flow={min_flow_usdt} USDT, "
            f"take_profit={take_profit_pct*100:.2f}%, "
            f"time_stop={time_limit_seconds}s"
        )

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

            # 1. 窗口重置（每秒重置一次，比 deque 快得多）
            now = time.time()
            if now - self.vol_window_start >= 1.0:
                self.buy_vol = 0.0
                self.sell_vol = 0.0
                self.vol_window_start = now

            # 2. 解析 Tick 数据（极速提取）
            data = event.data
            symbol = data.get('symbol')
            price = float(data.get('price', 0))
            size = float(data.get('size', 0))
            side = data.get('side', '').lower()
            usdt_val = price * size

            # 3. 检查交易对是否匹配
            if symbol != self.symbol:
                return

            # 4. 增加 Tick 计数
            self._increment_ticks()

            # 5. 累加成交量（只做加法，极快）
            if side == 'buy':
                self.buy_vol += usdt_val
            elif side == 'sell':
                self.sell_vol += usdt_val

            # 6. 更新波动率估算器（用于动态止损）
            if self._previous_price > 0:
                self._volatility_estimator.update_volatility(
                    current_price=price,
                    previous_close=self._previous_price
                )
            self._previous_price = price

            # 7. 持仓管理（检查止盈/止损/时间止损）
            if self._position_opened:
                await self._check_exit_conditions(price, now)

            # 8. 触发逻辑（仅空仓时检查）
            if not self._position_opened:
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

    async def _check_entry_conditions(self, price: float, now: float):
        """
        检查入场条件（买卖失衡触发）

        Args:
            price (float): 当前价格
            now (float): 当前时间戳
        """
        # 初始化变量，防止 UnboundLocalError
        imbalance = 0.0

        # 1. 检查是否有足够的买入量
        if self.buy_vol < self.config.min_flow_usdt:
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

            # 3. 计算止损价格（基于波动率）
            stop_loss_price = self._calculate_stop_loss(price)

            logger.debug(
                f"🛡️  [止损计算] entry={price:.2f}, "
                f"stop={stop_loss_price:.2f}, "
                f"距离={abs(price - stop_loss_price):.2f}"
            )

            # 4. 立即开仓！
            success = await self.buy(
                symbol=self.symbol,
                entry_price=price,
                stop_loss_price=stop_loss_price,
                order_type='market',
                size=self.config.position_size  # None=基于风险计算
            )

            if success:
                # 记录入场状态
                self._entry_price = price
                self._entry_time = now
                self._position_opened = True
                self._increment_signals()
                logger.info(
                    f"✅ [开仓成功] {self.symbol} @ {price:.2f}, "
                    f"止损={stop_loss_price:.2f}"
                )

    async def _check_exit_conditions(self, current_price: float, now: float):
        """
        检查出场条件（止盈/止损/时间止损）

        Args:
            current_price (float): 当前价格
            now (float): 当前时间戳
        """
        # 计算盈亏百分比
        if self._entry_price <= 0:
            return

        pnl_pct = (current_price - self._entry_price) / self._entry_price

        # 1. 止盈：+0.2% 立即走人
        if pnl_pct >= self.config.take_profit_pct:
            logger.info(
                f"💰 [止盈离场] {self.symbol}: "
                f"entry={self._entry_price:.2f}, "
                f"current={current_price:.2f}, "
                f"profit={pnl_pct*100:+.2f}%"
            )
            await self._close_position(current_price, "take_profit")
            return

        # 2. 硬止损：-1% 立即走人
        if pnl_pct <= -self.config.stop_loss_pct:
            logger.warning(
                f"🛑 [止损离场] {self.symbol}: "
                f"entry={self._entry_price:.2f}, "
                f"current={current_price:.2f}, "
                f"loss={pnl_pct*100:+.2f}%"
            )
            await self._close_position(current_price, "stop_loss")
            return

        # 3. 时间止损：5 秒不涨立即走人
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
        平仓

        Args:
            price (float): 平仓价格
            reason (str): 平仓原因（take_profit/stop_loss/time_stop）
        """
        if not self._position_opened:
            return

        # 计算盈亏
        if self._entry_price > 0:
            pnl_pct = (price - self._entry_price) / self._entry_price

            # 更新统计
            self._total_trades += 1
            if pnl_pct > 0:
                self._win_trades += 1
            else:
                self._loss_trades += 1

        # 平仓
        success = await self.sell(
            symbol=self.symbol,
            entry_price=price,  # 平仓时的价格
            stop_loss_price=0,   # 无需止损
            order_type='market',
            size=None  # 平仓全部
        )

        if success:
            self._position_opened = False
            self._entry_price = 0.0
            self._entry_time = 0.0
            logger.info(
                f"🔄 [平仓完成] {self.symbol} @ {price:.2f}, "
                f"reason={reason}"
            )

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
            'config': {
                'imbalance_ratio': self.config.imbalance_ratio,
                'min_flow_usdt': self.config.min_flow_usdt,
                'take_profit_pct': self.config.take_profit_pct * 100,
                'stop_loss_pct': self.config.stop_loss_pct * 100,
                'time_limit_seconds': self.config.time_limit_seconds
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

        # 重置统计
        self._total_trades = 0
        self._win_trades = 0
        self._loss_trades = 0
        self._max_imbalance_seen = 0.0

        # 重置波动率估算器
        self._volatility_estimator.reset()

        logger.info(f"ScalperV1 状态已完全重置")
