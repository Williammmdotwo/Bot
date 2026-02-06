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
    ema_enabled: bool = True  # 🔥 [新增] EMA 过滤开关


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
        self.config = config

        # 价格历史（用于 EMA 计算）
        self.price_history = collections.deque(maxlen=100)
        self.ema_value = 0.0

        # 🔥 [优化 69] Imbalance 增量计算
        # 避免每次都从 OrderBook 重新计算，改为增量更新
        self.buy_vol_increment = 0.0
        self.sell_vol_increment = 0.0

        # 🔧 [调试] 验证 min_flow_usdt 配置
        logger.info(f"🔧 [配置验证] SignalGenerator 初始化:")
        logger.info(f"   config.min_flow_usdt = {config.min_flow_usdt:.0f}")
        logger.info(f"   self.config.min_flow_usdt = {self.config.min_flow_usdt:.0f}")
        logger.info(f"   对象 = {config}")

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
        计算交易信号

        Args:
            symbol (str): 交易对
            price (float): 当前价格
            side (str): 交易方向
            size (float): 成交数量
            volume_usdt (float): 成交金额（USDT）

        Returns:
            Signal: 交易信号对象
        """
        # 1. 更新 EMA（趋势过滤）
        self._update_ema(price)

        # 2. 初始化信号对象
        signal = Signal()

        # 3. 趋势过滤：只做多（Price > EMA）
        # 🔥 [新增] 如果 EMA 过滤被禁用，跳过趋势检查
        if self.config.ema_enabled:
            trend_bias = self.get_trend_bias()
            if trend_bias != "bullish":
                signal.is_valid = False
                signal.direction = "neutral"
                signal.reason = f"trend_filter:{trend_bias}"
                signal.metadata = {
                    'ema_value': self.ema_value,
                    'current_price': price
                }
                logger.debug(
                    f"[SignalGenerator] {symbol}: "
                    f"趋势过滤: Trend={trend_bias}, "
                    f"Price={price:.6f}, EMA={self.ema_value:.6f} "
                    f"(不满足看涨条件)"
                )
                return signal

        # 4. 检查流动性：最小流速（USDT）
        if volume_usdt < self.config.min_flow_usdt:
            signal.is_valid = False
            signal.direction = "neutral"
            signal.reason = f"volume_filter:volume_too_low"
            signal.metadata = {
                'volume_usdt': volume_usdt,
                'min_flow': self.config.min_flow_usdt
            }
            logger.debug(
                f"[SignalGenerator] {symbol}: "
                f"流动性过滤: Volume={volume_usdt:.0f} USDT < "
                f"MinFlow={self.config.min_flow_usdt:.0f} USDT"
            )
            return signal

        # 5. 计算买卖失衡
        imbalance = 0.0
        if self.sell_vol_increment > 0:
            imbalance = self.buy_vol_increment / self.sell_vol_increment
        elif self.buy_vol_increment > 0:
            # 卖量为0，买量>0 -> 极度看多
            imbalance = 999.0
            logger.debug(
                f"[SignalGenerator] {symbol}: "
                f"极端失衡: 卖={self.sell_vol_increment:.0f} USDT, "
                f"买={self.buy_vol_increment:.0f} USDT, 失衡比=∞"
            )

        # 检查是否满足失衡阈值
        if imbalance < self.config.imbalance_ratio:
            signal.is_valid = False
            signal.direction = "neutral"
            signal.reason = f"imbalance_filter:ratio_too_low"
            signal.metadata = {
                'buy_vol': self.buy_vol_increment,
                'sell_vol': self.sell_vol_increment,
                'imbalance_ratio': imbalance,
                'threshold': self.config.imbalance_ratio
            }
            logger.debug(
                f"[SignalGenerator] {symbol}: "
                f"失衡过滤: Imbalance={imbalance:.2f}x < "
                f"阈值={self.config.imbalance_ratio:.2f}x"
            )
            return signal

        # 6. 信号有效
        signal.is_valid = True
        signal.direction = "bullish"
        signal.strength = min(imbalance / self.config.imbalance_ratio, 1.0)
        signal.reason = "imbalance_triggered"
        signal.metadata = {
            'ema_value': self.ema_value,
            'trend_bias': trend_bias,
            'buy_vol': self.buy_vol_increment,
            'sell_vol': self.sell_vol_increment,
            'imbalance_ratio': imbalance,
            'total_vol': self.buy_vol_increment + self.sell_vol_increment
        }

        logger.info(
            f"[SignalGenerator] {symbol}: "
            f"生成有效信号: Direction={signal.direction}, "
            f"Strength={signal.strength:.3f}, "
            f"Reason={signal.reason}, "
            f"Imbalance={imbalance:.2f}x"
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
