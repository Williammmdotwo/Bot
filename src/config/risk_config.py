"""
风控配置 (Risk Configuration)

机构级资金管理系统的硬性参数配置。

设计原则：
- 所有关键风控参数集中管理
- 避免硬编码在业务逻辑中
- 支持动态调整
"""

from typing import Dict, Any
from dataclasses import dataclass, field


@dataclass
class RiskConfig:
    """
    风控配置类

    包含所有资金管理和风控的关键参数。
    """

    # ========== 单笔交易风险控制 ==========
    # 单笔交易最大亏损为总账户权益的百分比
    # 这是机构级风控的核心原则：每笔交易风险不超过总资金的1-2%
    RISK_PER_TRADE_PCT: float = 0.01

    # ========== 杠杆控制 ==========
    # 全局真实杠杆上限（绝对红线）
    # 真实杠杆 = 总持仓价值 / 账户权益
    MAX_GLOBAL_LEVERAGE: float = 3.0

    # ========== 回撤控制 ==========
    # 策略最大回撤熔断阈值
    # 超过此值，该策略将被强制停止
    MAX_DRAWDOWN_LIMIT: float = 0.15

    # 相关性敞口限制
    # 如 BTC+ETH 总持仓不超过本金的 2 倍
    CORRELATION_LIMIT: float = 2.0

    # ========== 止损保护 ==========
    # 默认止损百分比（当无法确定具体止损价时使用）
    DEFAULT_STOP_LOSS_PCT: float = 0.02

    # 最小止损价差保护（防止除以零）
    MIN_STOP_DISTANCE_PCT: float = 0.001  # 0.1%

    # ========== 波动率计算 ==========
    # ATR 计算的周期
    ATR_PERIOD: int = 14

    # EMA 的平滑因子（用于波动率估算）
    EMA_ALPHA: float = 0.2

    # ========== 敞口检查 ==========
    # 单一币种最大持仓比例
    # ✨ 修复：从 50% 提升到 2000%（20.0），允许超高杠杆交易
    MAX_SINGLE_SYMBOL_EXPOSURE: float = 20.0

    # 警告级别的杠杆比例（仅记录日志，不拒绝）
    WARNING_LEVERAGE_THRESHOLD: float = 2.0


# 默认配置实例
DEFAULT_RISK_CONFIG = RiskConfig()


def get_risk_config(custom_config: Dict[str, Any] = None) -> RiskConfig:
    """
    获取风控配置

    Args:
        custom_config (dict): 自定义配置，用于覆盖默认值

    Returns:
        RiskConfig: 风控配置实例
    """
    if custom_config:
        return RiskConfig(**custom_config)
    return DEFAULT_RISK_CONFIG


def validate_risk_config(config: RiskConfig) -> bool:
    """
    验证风控配置的合理性

    Args:
        config (RiskConfig): 风控配置

    Returns:
        bool: 配置是否有效

    Raises:
        ValueError: 配置不合理时抛出
    """
    # 验证百分比范围
    if not (0 < config.RISK_PER_TRADE_PCT < 0.1):
        raise ValueError(f"RISK_PER_TRADE_PCT 必须在 0-10% 之间: {config.RISK_PER_TRADE_PCT}")

    if not (0 < config.MAX_GLOBAL_LEVERAGE < 20):
        raise ValueError(f"MAX_GLOBAL_LEVERAGE 必须在 1-20 之间: {config.MAX_GLOBAL_LEVERAGE}")

    if not (0 < config.MAX_DRAWDOWN_LIMIT < 1.0):
        raise ValueError(f"MAX_DRAWDOWN_LIMIT 必须在 0-100% 之间: {config.MAX_DRAWDOWN_LIMIT}")

    if config.MIN_STOP_DISTANCE_PCT <= 0:
        raise ValueError(f"MIN_STOP_DISTANCE_PCT 必须大于 0: {config.MIN_STOP_DISTANCE_PCT}")

    # 验证逻辑一致性
    if config.WARNING_LEVERAGE_THRESHOLD >= config.MAX_GLOBAL_LEVERAGE:
        raise ValueError(
            f"WARNING_LEVERAGE_THRESHOLD ({config.WARNING_LEVERAGE_THRESHOLD}) "
            f"必须小于 MAX_GLOBAL_LEVERAGE ({config.MAX_GLOBAL_LEVERAGE})"
        )

    return True
