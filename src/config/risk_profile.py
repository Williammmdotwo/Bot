"""
风控配置文件 (Risk Profile)

策略级别的风控配置，实现策略与风控的解耦。

设计原则：
- 每个策略可以独立配置风控参数
- 支持不同策略类型的不同风险偏好
- 与全局 RiskConfig 配合，形成双层风控体系
"""

from enum import Enum
from dataclasses import dataclass


class StopLossType(Enum):
    """止损类型枚举"""
    HARD_PRICE = "hard_price"    # 硬价格止损（传统）
    TIME_BASED = "time_based"    # 时间止损（HFT 专用）
    TRAILING = "trailing"        # 移动止损（趋势专用）


@dataclass
class RiskProfile:
    """
    策略风控配置文件

    定义单个策略的风控参数，支持差异化风险控制。

    Example:
        >>> # HFT 策略的激进配置
        >>> hft_profile = RiskProfile(
        ...     strategy_id="sniper",
        ...     max_leverage=5.0,
        ...     stop_loss_type=StopLossType.TIME_BASED,
        ...     time_limit_seconds=10
        ... )
        >>>
        >>> # 趋势策略的保守配置
        >>> trend_profile = RiskProfile(
        ...     strategy_id="dual_ema",
        ...     max_leverage=1.5,
        ...     stop_loss_type=StopLossType.TRAILING
        ... )
    """
    # 策略标识
    strategy_id: str

    # ========== 杠杆限制 ==========
    # 该策略允许的最大真实杠杆
    max_leverage: float = 1.0

    # ========== 单笔风控 ==========
    # 单笔最大名义价值（USDT）
    max_order_size_usdt: float = 1000.0

    # 单笔最大亏损占总资金比例 (1% Rule)
    single_loss_cap_pct: float = 0.01

    # ========== 止损模式 ==========
    stop_loss_type: StopLossType = StopLossType.HARD_PRICE

    # ========== HFT 特有配置 ==========
    # 持仓最大时间（秒），0 为不限制
    time_limit_seconds: int = 0

    # ========== 每日熔断 ==========
    # 当日累计亏损超过此比例停止该策略
    max_daily_loss_pct: float = 0.05

    def __post_init__(self):
        """初始化后验证参数合理性"""
        if self.max_leverage <= 0:
            raise ValueError(f"max_leverage 必须大于 0: {self.max_leverage}")

        if self.max_order_size_usdt <= 0:
            raise ValueError(f"max_order_size_usdt 必须大于 0: {self.max_order_size_usdt}")

        if not (0 < self.single_loss_cap_pct < 0.1):
            raise ValueError(f"single_loss_cap_pct 必须在 0-10% 之间: {self.single_loss_cap_pct}")

        if not (0 < self.max_daily_loss_pct < 1.0):
            raise ValueError(f"max_daily_loss_pct 必须在 0-100% 之间: {self.max_daily_loss_pct}")

        if self.time_limit_seconds < 0:
            raise ValueError(f"time_limit_seconds 不能为负数: {self.time_limit_seconds}")

    def is_hft_style(self) -> bool:
        """
        判断是否为 HFT 风格配置

        Returns:
            bool: 是否使用时间止损
        """
        return self.stop_loss_type == StopLossType.TIME_BASED

    def is_trend_style(self) -> bool:
        """
        判断是否为趋势策略风格配置

        Returns:
            bool: 是否使用移动止损
        """
        return self.stop_loss_type == StopLossType.TRAILING

    def is_conservative(self) -> bool:
        """
        判断是否为保守配置

        Returns:
            bool: 杠杆是否较低（< 2x）
        """
        return self.max_leverage < 2.0


# 默认保守配置（用于未注册 Profile 的策略）
DEFAULT_CONSERVATIVE_PROFILE = RiskProfile(
    strategy_id="default",
    max_leverage=10.0,  # 🔥 [修复] 改为 10.0（匹配标准配置）
    max_order_size_usdt=1000.0,
    single_loss_cap_pct=0.01,
    stop_loss_type=StopLossType.HARD_PRICE,
    time_limit_seconds=0,
    max_daily_loss_pct=0.05
)
