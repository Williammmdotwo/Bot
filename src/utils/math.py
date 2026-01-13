"""
轻量级数学工具模块
Lightweight Math Utilities for Athena Trader

此模块仅包含轻量级、无重型依赖的工具类。
所有 HFT 策略应使用本模块的工具，避免使用 pandas/numpy。
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class VolatilityEstimator:
    """
    波动率估算器（基于 EMA 的轻量级实现）

    用于在无法存储完整 K 线历史时，实时估算波动率。
    适用于 HFT 策略，只需上一根 K 线的 close 价格即可更新。

    设计原则：
    - 零重型依赖：不使用 pandas/numpy
    - O(1) 时间复杂度：只维护累加器
    - 内存友好：不存储历史数据
    """

    def __init__(self, alpha: float = 0.2, initial_price: float = 0.0, min_volatility_floor: float = 0.005):
        """
        初始化波动率估算器

        Args:
            alpha (float): EMA 平滑因子，默认 0.2（相当于 5 周期 EMA）
            initial_price (float): 初始价格（可选）
            min_volatility_floor (float): 波动率下限（默认 0.5%），防止在横盘市场中计算过大的杠杆
        """
        self.alpha = alpha
        self.previous_close = initial_price
        self.ema_volatility = 0.0
        self.samples_count = 0
        self.min_volatility_floor = min_volatility_floor

        logger.debug(
            f"VolatilityEstimator 初始化: alpha={alpha}, "
            f"initial_price={initial_price}, "
            f"min_volatility_floor={min_volatility_floor*100:.2f}%"
        )

    def update_volatility(self, current_price: float, previous_close: float = None) -> float:
        """
        更新波动率估算

        使用简化的波动率计算：基于价格变化的 EMA

        Args:
            current_price (float): 当前价格
            previous_close (float): 上一根 K 线收盘价（可选，默认使用上一次的）

        Returns:
            float: 当前波动率估算值（百分比）
        """
        # 使用传入的 previous_close 或默认使用内部保存的
        prev_close = previous_close if previous_close is not None else self.previous_close

        if prev_close <= 0:
            logger.warning("previous_close 无效，跳过波动率更新")
            return self.ema_volatility

        # 计算价格变化百分比
        try:
            price_change_pct = (current_price - prev_close) / prev_close
        except ZeroDivisionError:
            logger.warning("previous_close 为 0，跳过波动率更新")
            return self.ema_volatility

        # 计算绝对变化（波动率）
        volatility = abs(price_change_pct)

        # 更新 EMA 波动率
        # EMA_formula: EMA = alpha * current + (1 - alpha) * previous_EMA
        if self.ema_volatility == 0.0:
            # 首次更新，直接使用当前值
            self.ema_volatility = volatility
        else:
            self.ema_volatility = (
                self.alpha * volatility +
                (1 - self.alpha) * self.ema_volatility
            )

        # 波动率下限保护：防止在横盘市场中波动率过小
        if self.ema_volatility < self.min_volatility_floor:
            logger.debug(
                f"波动率低于下限: {self.ema_volatility*100:.3f}% < "
                f"{self.min_volatility_floor*100:.2f}%, 使用下限值"
            )
            self.ema_volatility = self.min_volatility_floor

        # 更新内部状态
        self.previous_close = current_price
        self.samples_count += 1

        logger.debug(
            f"波动率更新: price={current_price:.2f}, "
            f"change={price_change_pct*100:+.3f}%, "
            f"volatility={self.ema_volatility*100:.3f}%"
        )

        return self.ema_volatility

    def get_volatility(self) -> float:
        """
        获取当前波动率

        Returns:
            float: 波动率（百分比）
        """
        return self.ema_volatility

    def calculate_atr_based_stop(
        self,
        entry_price: float,
        atr_multiplier: float = 2.0,
        atr: float = None
    ) -> float:
        """
        基于波动率计算止损价

        如果提供了 ATR，使用 ATR；否则使用内部波动率估算

        Args:
            entry_price (float): 入场价格
            atr_multiplier (float): ATR 倍数（默认 2.0）
            atr (float): ATR 值（可选）

        Returns:
            float: 止损价格
        """
        if atr and atr > 0:
            # 使用 ATR 计算止损
            stop_distance = atr * atr_multiplier
            stop_loss_price = entry_price - stop_distance
            logger.debug(
                f"ATR 止损: entry={entry_price:.2f}, "
                f"atr={atr:.2f}, multiplier={atr_multiplier}, "
                f"stop={stop_loss_price:.2f}"
            )
        else:
            # 使用内部波动率估算
            volatility = self.get_volatility()

            if volatility <= 0:
                # 没有波动率数据，使用默认 2%
                stop_distance = entry_price * 0.02
            else:
                # 使用波动率的 2 倍作为止损距离
                stop_distance = entry_price * volatility * 2

            stop_loss_price = entry_price - stop_distance
            logger.debug(
                f"波动率止损: entry={entry_price:.2f}, "
                f"volatility={volatility*100:.3f}%, "
                f"stop={stop_loss_price:.2f}"
            )

        return stop_loss_price

    def get_volatility_percentile(self, percentile: float = 0.95) -> float:
        """
        获取波动率的百分位值（简化估计）

        基于 EMA 的假设：波动率服从指数分布

        Args:
            percentile (float): 百分位数（0-1），默认 0.95

        Returns:
            float: 百分位波动率值
        """
        if self.ema_volatility <= 0:
            return 0.0

        # 使用对数转换估算百分位
        # P(X <= x) = 1 - exp(-lambda * x)
        # x = -ln(1 - P) / lambda
        # 这里 lambda 近似为 1/ema_volatility

        if percentile <= 0 or percentile >= 1:
            return self.ema_volatility

        try:
            import math
            adjusted_volatility = self.ema_volatility * (
                -math.log(1 - percentile) if 0 < percentile < 1
                else 1.0
            )
            return max(adjusted_volatility, self.ema_volatility)
        except:
            # 计算出错，返回当前值
            return self.ema_volatility

    def reset(self):
        """重置波动率估算器"""
        self.ema_volatility = 0.0
        self.samples_count = 0
        logger.debug("VolatilityEstimator 已重置")


# ============================================================================
# 历史说明
# ============================================================================
#
# 本模块曾经包含 TechnicalIndicators 类，该类使用了 pandas 和 numpy 进行
# 技术指标计算（RSI、MACD、布林带等）。
#
# 2026年1月14日 - 移除 TechnicalIndicators 类
# 原因：
#   1. 项目已全面转向 HFT 策略，不需要完整的技术指标计算
#   2. pandas 依赖占用 200-300MB 内存，不适合 1G 内存环境
#   3. 所有活跃策略（ScalperV1）都使用轻量级的 VolatilityEstimator
#
# 如果未来需要技术指标计算，建议：
#   - 使用原生 Python 实现轻量级版本
#   - 或者使用专门的指标库（如 talib），但需评估内存占用
# ============================================================================
