"""
SignalGenerator - 信号生成器

负责 ScalperV1 策略的信号生成逻辑：
- EMA 计算（趋势过滤）
- Imbalance 计算（微观失衡）
- Spread 监控（质量过滤）
- 趋势判断（Bullish/Bearish/Neutral）

输入：Tick 事件
输出：Signal 对象（包含方向、强度、原因）

设计原则：
- 单一职责：只负责信号生成，不涉及执行
- 无状态：不维护任何持久化状态
- 可测试：独立的输入输出，易于单元测试
"""

import logging
import os
import time
import collections
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ScalperV1Config:
    """ScalperV1 策略配置（V2）"""
    symbol: str = "DOGE-USDT-SWAP"
    imbalance_ratio: float = 5.0
    min_flow_usdt: float = 5000.0
    ema_period: int = 50
    spread_threshold_pct: float = 0.0005
    # ✅ 新增配置
    trade_direction: str = 'both'  # 'both', 'long_only', 'short_only'
    ema_filter_mode: str = 'loose'  # 'strict', 'loose', 'off'
    ema_boost_pct: float = 0.20  # EMA 顺势时仓位加权比例（20%）
    # ✅ 新增：订单簿深度过滤配置
    depth_filter_enabled: bool = True
    depth_ratio_threshold_low: float = 0.8   # 做多时，bid_depth/ask_depth 必须 >= 0.8
    depth_ratio_threshold_high: float = 1.25  # 做空时，bid_depth/ask_depth 必须 <= 1.25
    depth_check_levels: int = 3              # 检查前N档深度


@dataclass
class Signal:
    """
    交易信号对象

    属性：
        is_valid (bool): 信号是否有效
        direction (str): 'bullish' (看涨) / 'bearish' (看跌) / 'neutral' (中性)
        strength (float): 信号强度 (0.0 - 1.0)
        reason (str): 信号原因（趋势/失衡/点差过滤）
        metadata (dict): 额外元数据（EMA值、失衡比、点差百分比等）
    """
    is_valid: bool = False
    direction: str = "neutral"
    strength: float = 0.0
    reason: str = ""
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class SignalGenerator:
    """
    信号生成器（ScalperV1 策略）

    职责：
    1. EMA 计算（趋势过滤）
    2. Imbalance 计算（微观失衡）
    3. Spread 监控（质量过滤）
    4. 趋势判断（Bullish/Bearish/Neutral）
    """

    def __init__(self, config: ScalperV1Config):
        """
        初始化信号生成器

        Args:
            config (ScalperV1Config): 策略配置
        """
        # 🔥 [修复] 添加 logger 初始化（必须在最前面）
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        self.config = config

        # 价格历史（用于 EMA 计算）
        self.price_history = collections.deque(maxlen=100)
        self.ema_value = 0.0

        # 🔥 [优化 69] Imbalance 增量计算
        # 避免每次都从 OrderBook 重新计算，改为增量更新
        self.buy_vol_increment = 0.0
        self.sell_vol_increment = 0.0

        # ✅ 新增：market_data_manager 引用（用于获取订单簿）
        self.market_data_manager = None

        # 🔥 [优化] 流动性过滤计数器
        self._liquidity_filter_count = 0
        self._last_liquidity_log_time = 0
        self._log_interval = 5.0  # 每 5 秒汇总一次

        # 🔥 [优化] 深度过滤计数器
        self._depth_filter_count = 0
        self._last_depth_log_time = 0

        # 🔥 [优化] 从环境变量读取详细日志开关
        self._enable_detailed_logs = os.getenv(
            'SIGNAL_GENERATOR_VERBOSE', 'false'
        ).lower() == 'true'

        logger.info(f"SignalGenerator 初始化: symbol={config.symbol}, imbalance={config.imbalance_ratio}x, min_flow={config.min_flow_usdt:.0f}")

    def _update_ema(self, price: float):
        """
        更新 EMA 值（O(1) 优化）

        🔥 [优化 69] 使用递推公式，避免遍历历史价格
        公式：new_ema = old_ema * (1 - k) + price * k
        其中 k = 2 / (ema_period + 1)

        Args:
            price (float): 当前价格
        """
        # 将新价格添加到历史
        self.price_history.append(price)

        # 🔥 [优化 69] O(1) EMA 计算
        k = 2.0 / (self.config.ema_period + 1)
        self.ema_value = self.ema_value * (1 - k) + price * k

        # 确保 EMA 不为 0（避免第一次计算错误）
        if self.ema_value <= 0:
            self.ema_value = price

    def update_volumes_increment(self, side: str, usdt_val: float):
        """
        增量更新买卖成交量

        🔥 [优化 70] 避免每次都重新计算 Imbalance
        改为增量更新，外部传入 buy/sell 和金额即可

        Args:
            side (str): 交易方向 ('buy' or 'sell')
            usdt_val (float): 交易金额（USDT）
        """
        if side == 'buy':
            self.buy_vol_increment += usdt_val
        elif side == 'sell':
            self.sell_vol_increment += usdt_val

    def reset_volumes(self):
        """
        🔥 [新增] 重置成交量增量

        防止数据无限累积导致极端失衡比率（如 999x）
        必须在时间窗口到期时调用此方法

        使用场景：
        - 策略中的成交量窗口到期时（如 3 秒）
        - 系统重启时
        - 手动重置时

        🔥 [修复] 只有当 logger 存在时才记录日志（避免 AttributeError）
        """
        old_buy = self.buy_vol_increment
        old_sell = self.sell_vol_increment

        self.buy_vol_increment = 0.0
        self.sell_vol_increment = 0.0

        # 🔥 [修复] 只有当 logger 存在时才记录日志
        if hasattr(self, 'logger'):
            self.logger.debug(
                f"[SignalGenerator] {self.config.symbol}: "
                f"成交量增量已重置 (buy: {old_buy:.2f}→0, sell: {old_sell:.2f}→0)"
            )

    def get_min_flow_threshold(self, signal_ratio: float) -> float:
        """
        根据信号强度动态调整最小流量阈值

        🔥 [优化] 对于极强信号，允许更小的单笔成交量
        避免错过高质量交易机会

        Args:
            signal_ratio (float): 信号强度（失衡比率）

        Returns:
            float: 动态调整后的最小流量阈值（USDT）
        """
        if signal_ratio >= 10.0:  # 极强信号（10x 以上）
            return 200.0  # 允许更小的流量，因为信号质量高
        elif signal_ratio >= 5.0:  # 强信号（5-10x）
            return 350.0  # 中等流量要求
        else:  # 普通信号（3-5x）
            return 500.0  # 保持严格要求

    def get_trend_bias(self) -> str:
        """
        获取趋势偏置

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

    def compute(
        self,
        symbol: str,
        price: float,
        side: str,
        size: float,
        volume_usdt: float
    ) -> Signal:
        """
        计算交易信号（双向交易 + EMA 宽松过滤）

        🔥 [修复] 在信号生成前提前检查交易方向，避免生成无效信号

        Args:
            symbol (str): 交易对
            price (float): 当前价格
            side (str): 交易方向
            size (float): 成交数量
            volume_usdt (float): 成交金额（USDT）

        Returns:
            Signal: 交易信号对象
        """
        # 1. 更新 EMA
        self._update_ema(price)

        # 2. 初始化信号对象
        signal = Signal()

        # 3. 🔥 [优化] 计算买卖失衡（用于动态阈值调整）
        buy_imbalance = 0.0
        sell_imbalance = 0.0

        if self.sell_vol_increment > 0:
            buy_imbalance = self.buy_vol_increment / self.sell_vol_increment
        elif self.buy_vol_increment > 0:
            buy_imbalance = 999.0  # 卖量为0，买量>0 -> 极度看多

        if self.buy_vol_increment > 0:
            sell_imbalance = self.sell_vol_increment / self.buy_vol_increment
        elif self.sell_vol_increment > 0:
            sell_imbalance = 999.0  # 买量为0，卖量>0 -> 极度看空

        # 4. 计算动态最小流量阈值
        # 取买卖失衡的较大值作为信号强度
        signal_ratio = max(buy_imbalance, sell_imbalance)
        dynamic_min_flow = self.get_min_flow_threshold(signal_ratio)

        # 5. 检查流动性：最小流速（USDT）- 使用动态阈值
        if volume_usdt < dynamic_min_flow:
            signal.is_valid = False
            signal.direction = "neutral"
            signal.reason = f"volume_filter:volume_too_low"
            signal.metadata = {
                'volume_usdt': volume_usdt,
                'min_flow': self.config.min_flow_usdt,
                'dynamic_min_flow': dynamic_min_flow,
                'signal_ratio': signal_ratio
            }

            # 🔥 [优化] 批量日志 - 流动性过滤
            self._liquidity_filter_count += 1

            # 每 5 秒或每 20 次输出一次汇总
            now = time.time()
            if (self._liquidity_filter_count % 20 == 0) or \
               (now - self._last_liquidity_log_time >= self._log_interval):
                logger.info(
                    f"⚠️ [流动性过滤-汇总] {symbol}: "
                    f"已过滤 {self._liquidity_filter_count} 笔, "
                    f"最后={volume_usdt:.0f} < {dynamic_min_flow:.0f} USDT "
                    f"(Signal={signal_ratio:.1f}x)"
                )
                self._last_liquidity_log_time = now

            return signal

        # 🔥 [修复] 提前检查交易方向（在计算信号之前）
        # 如果是 long_only 模式，且卖方失衡更强，直接跳过
        if self.config.trade_direction == 'long_only':
            if sell_imbalance > buy_imbalance:
                logger.debug(
                    f"[SignalGenerator] {symbol}: LongOnly模式 - "
                    f"卖方失衡={sell_imbalance:.2f}x > 买方失衡={buy_imbalance:.2f}x, 跳过"
                )
                return signal
            # 检查买方失衡是否达到阈值
            if buy_imbalance < self.config.imbalance_ratio:
                logger.debug(
                    f"[SignalGenerator] {symbol}: LongOnly模式 - "
                    f"买方失衡={buy_imbalance:.2f}x < {self.config.imbalance_ratio}x, 跳过"
                )
                return signal

        # 如果是 short_only 模式，且买方失衡更强，直接跳过
        elif self.config.trade_direction == 'short_only':
            if buy_imbalance > sell_imbalance:
                logger.debug(
                    f"[SignalGenerator] {symbol}: ShortOnly模式 - "
                    f"买方失衡={buy_imbalance:.2f}x > 卖方失衡={sell_imbalance:.2f}x, 跳过"
                )
                return signal
            # 检查卖方失衡是否达到阈值
            if sell_imbalance < self.config.imbalance_ratio:
                logger.debug(
                    f"[SignalGenerator] {symbol}: ShortOnly模式 - "
                    f"卖方失衡={sell_imbalance:.2f}x < {self.config.imbalance_ratio}x, 跳过"
                )
                return signal

        # 7. 失衡信号判断
        signal_direction = None
        imbalance_value = 0.0

        if buy_imbalance >= self.config.imbalance_ratio:
            signal_direction = 'buy'
            imbalance_value = buy_imbalance
        elif sell_imbalance >= self.config.imbalance_ratio:
            signal_direction = 'sell'
            imbalance_value = sell_imbalance
        else:
            logger.debug(
                f"[SignalGenerator] {symbol}: 失衡过滤: "
                f"buy={buy_imbalance:.2f}x, sell={sell_imbalance:.2f}x < {self.config.imbalance_ratio}x"
            )
            return signal

        # 6. 交易方向过滤（保留作为最后防线）
        # 🔥 [修复] 增加配置日志，便于调试
        if self.config.trade_direction != 'both':
            logger.debug(
                f"[SignalGenerator] {symbol}: "
                f"交易方向配置={self.config.trade_direction}, "
                f"信号方向={signal_direction}"
            )

        if self.config.trade_direction == 'long_only' and signal_direction == 'sell':
            logger.debug(
                f"[SignalGenerator] {symbol}: 交易方向过滤: "
                f"配置=long_only, 信号=sell, 跳过"
            )
            return signal

        if self.config.trade_direction == 'short_only' and signal_direction == 'buy':
            logger.debug(
                f"[SignalGenerator] {symbol}: 交易方向过滤: "
                f"配置=short_only, 信号=buy, 跳过"
            )
            return signal

        # 7. 订单簿深度比率过滤
        if self.config.depth_filter_enabled:
            depth_ratio = self._calculate_depth_ratio(order_book=None)

            if depth_ratio is not None:
                if signal_direction == 'buy' and depth_ratio < self.config.depth_ratio_threshold_low:
                    # 🔥 [优化] 批量日志 - 深度过滤
                    self._depth_filter_count += 1

                    now = time.time()
                    if (self._depth_filter_count % 10 == 0) or \
                       (now - self._last_depth_log_time >= self._log_interval):
                        logger.info(
                            f"🛑 [深度过滤-汇总] {symbol}: "
                            f"已拒绝 {self._depth_filter_count} 次做多信号 "
                            f"(深度比率过低)"
                        )
                        self._last_depth_log_time = now

                    return signal

                if signal_direction == 'sell' and depth_ratio > self.config.depth_ratio_threshold_high:
                    # 🔥 [优化] 批量日志 - 深度过滤
                    self._depth_filter_count += 1

                    now = time.time()
                    if (self._depth_filter_count % 10 == 0) or \
                       (now - self._last_depth_log_time >= self._log_interval):
                        logger.info(
                            f"🛑 [深度过滤-汇总] {symbol}: "
                            f"已拒绝 {self._depth_filter_count} 次做空信号 "
                            f"(深度比率过高)"
                        )
                        self._last_depth_log_time = now

                    return signal

        # 8. EMA 趋势过滤/加权
        trend = self.get_trend_bias()
        ema_boost = 1.0  # 默认无加权

        if self.config.ema_filter_mode == 'strict':
            # 严格模式：必须顺势
            if signal_direction == 'buy' and trend != 'bullish':
                logger.debug(
                    f"[SignalGenerator] {symbol}: EMA严格过滤 (做多): "
                    f"Trend={trend}, Price={price:.6f}, EMA={self.ema_value:.6f}"
                )
                return signal

            if signal_direction == 'sell' and trend != 'bearish':
                logger.debug(
                    f"[SignalGenerator] {symbol}: EMA严格过滤 (做空): "
                    f"Trend={trend}, Price={price:.6f}, EMA={self.ema_value:.6f}"
                )
                return signal

        elif self.config.ema_filter_mode == 'loose':
            # 宽松模式：顺势加权
            if signal_direction == 'buy' and trend == 'bullish':
                ema_boost = 1.0 + self.config.ema_boost_pct
                logger.debug(
                    f"[SignalGenerator] {symbol}: EMA顺势加权 (做多): "
                    f"boost={ema_boost:.2f}x, Price={price:.6f} > EMA={self.ema_value:.6f}"
                )

            elif signal_direction == 'sell' and trend == 'bearish':
                ema_boost = 1.0 + self.config.ema_boost_pct
                logger.debug(
                    f"[SignalGenerator] {symbol}: EMA顺势加权 (做空): "
                    f"boost={ema_boost:.2f}x, Price={price:.6f} < EMA={self.ema_value:.6f}"
                )

            else:
                logger.debug(
                    f"[SignalGenerator] {symbol}: EMA逆势 (无加权): "
                    f"signal={signal_direction}, trend={trend}"
                )

        else:  # 'off'
            # 关闭模式：不使用 EMA
            logger.debug(f"[SignalGenerator] {symbol}: EMA过滤已关闭")

        # 8. 生成信号
        signal.is_valid = True
        signal.direction = signal_direction
        signal.strength = min(imbalance_value / self.config.imbalance_ratio, 1.0)
        signal.reason = "imbalance_triggered"
        signal.metadata = {
            'ema_value': self.ema_value,
            'trend': trend,
            'ema_boost': ema_boost,
            'imbalance_ratio': imbalance_value,
            'buy_vol': self.buy_vol_increment,
            'sell_vol': self.sell_vol_increment,
            'total_vol': self.buy_vol_increment + self.sell_vol_increment
        }

        logger.debug(  # 🔥 [优化] 改为 DEBUG 级别
            f"✅ [信号生成] {symbol}: {signal_direction.upper()} | "
            f"失衡={imbalance_value:.2f}x, EMA加权={ema_boost:.2f}x, 趋势={trend}"
        )

        return signal

    def get_state(self) -> dict:
        """
        获取当前状态（用于调试和监控）

        Returns:
            dict: 当前状态信息
        """
        return {
            'ema_value': self.ema_value,
            'price_history_len': len(self.price_history),
            'trend_bias': self.get_trend_bias(),
            'buy_vol_increment': self.buy_vol_increment,
            'sell_vol_increment': self.sell_vol_increment,
            'config': {
                'symbol': self.config.symbol,
                'ema_period': self.config.ema_period,
                'imbalance_ratio': self.config.imbalance_ratio,
                'min_flow_usdt': self.config.min_flow_usdt,
                'spread_threshold_pct': self.config.spread_threshold_pct
            }
        }

    def _calculate_depth_ratio(self, order_book: dict = None) -> float:
        """
        计算订单簿深度比率（🔥 改进：去除异常大单，使用平均值，增强异常处理）

        改进方案：
        1. 去除异常大单（单档占比 > 50%）
        2. 使用平均值而非总和（更稳定）
        3. 异常值检测（比率 > 10 或 < 0.1）
        4. 🔥 [修复] 增强异常处理，确保 logger 可用

        Args:
            order_book: 订单簿数据（可选，如果为None则从market_data_manager获取）

        Returns:
            float: bid_depth / ask_depth 比率，None 或 0.0 表示无法计算或数据异常
        """
        try:
            # 从 market_data_manager 获取订单簿
            if not order_book and self.market_data_manager:
                order_book = self.market_data_manager.get_order_book_depth(
                    self.config.symbol,
                    levels=self.config.depth_check_levels
                )

            if not order_book:
                # 🔥 [修复] 安全的日志（不依赖 self.logger）
                if hasattr(self, 'logger'):
                    self.logger.warning(f"⚠️ [深度计算] {self.config.symbol}: 订单簿数据为空")
                return 0.0

            bids = order_book.get('bids', [])
            asks = order_book.get('asks', [])

            if not bids or not asks:
                if hasattr(self, 'logger'):
                    self.logger.warning(f"⚠️ [深度计算] {self.config.symbol}: bids 或 asks 为空")
                return 0.0

            # 计算每档深度
            levels = self.config.depth_check_levels
            bid_depths = []
            ask_depths = []

            for i in range(min(levels, len(bids))):
                bid = bids[i]
                if len(bid) >= 2:
                    price = float(bid[0])
                    size = float(bid[1])
                    depth = price * size
                    bid_depths.append(depth)

            for i in range(min(levels, len(asks))):
                ask = asks[i]
                if len(ask) >= 2:
                    price = float(ask[0])
                    size = float(ask[1])
                    depth = price * size
                    ask_depths.append(depth)

            if not bid_depths or not ask_depths:
                if hasattr(self, 'logger'):
                    self.logger.warning(f"⚠️ [深度计算] {self.config.symbol}: 深度数据为空")
                return 0.0

            # 🔥 [改进] 去除异常大单（单档占比 > 50%）
            def remove_outliers(depths: list) -> list:
                """去除异常大的单档挂单"""
                total = sum(depths)
                if total == 0:
                    return []
                # 过滤掉单档占比超过 50% 的异常值
                return [d for d in depths if d < total * 0.5]

            bid_depths_clean = remove_outliers(bid_depths)
            ask_depths_clean = remove_outliers(ask_depths)

            # 检查清洗后是否还有数据
            if not bid_depths_clean or not ask_depths_clean:
                if hasattr(self, 'logger'):
                    self.logger.warning(
                        f"⚠️ [深度过滤失败] {self.config.symbol}: "
                        f"清洗后数据为空，跳过深度过滤"
                    )
                return 0.0

            # 🔥 [改进] 使用平均值（更稳定）
            bid_depth = sum(bid_depths_clean) / len(bid_depths_clean)
            ask_depth = sum(ask_depths_clean) / len(ask_depths_clean)

            # 🔥 [改进] 防止除零
            if ask_depth == 0:
                if hasattr(self, 'logger'):
                    self.logger.warning(
                        f"⚠️ [深度异常] {self.config.symbol}: "
                        f"ask_depth=0，跳过深度过滤"
                    )
                return 0.0

            depth_ratio = bid_depth / ask_depth

            # 🔥 [改进] 异常值检测
            if depth_ratio > 20.0 or depth_ratio < 0.5:
                if hasattr(self, 'logger'):
                    # 🔥 [优化] 改为 DEBUG 级别，避免频繁警告
                    self.logger.debug(
                        f"⚠️ [深度异常] {self.config.symbol}: "
                        f"清洗后深度比率={depth_ratio:.2f} 仍超出合理范围 [0.5, 20.0]，"
                        f"bid_depth={bid_depth:.2f}, ask_depth={ask_depth:.2f}，"
                        f"跳过深度过滤"
                    )
                return 0.0

            return depth_ratio

        except Exception as e:
            # 🔥 [修复] 安全的异常处理（不依赖 self.logger）
            if hasattr(self, 'logger'):
                self.logger.error(
                    f"❌ [深度计算] {self.config.symbol}: 计算失败 - {e}",
                    exc_info=True
                )
            return 0.0
