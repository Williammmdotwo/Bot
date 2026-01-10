"""
策略引擎常量定义

此模块包含策略引擎中使用的所有常量参数，
便于统一管理和配置。

作者: Athena Trader Team
日期: 2025-12-19
"""

from enum import Enum
from typing import Dict, Any


class SignalType(str, Enum):
    """信号类型枚举"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WAIT = "WAIT"


class StrategyType(str, Enum):
    """策略类型枚举"""
    DUAL_EMA = "DUAL_EMA"
    MACD = "MACD"
    RSI = "RSI"
    BOLLINGER_BANDS = "BOLLINGER_BANDS"


class TimeFrame(str, Enum):
    """时间框架枚举"""
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    ONE_DAY = "1d"


# 双均线策略常量
DUAL_EMA_CONFIG = {
    "default_fast_period": 9,
    "default_slow_period": 21,
    "min_data_points": 21,
    "confidence_threshold": 0.6,
    "default_symbol": "BTC-USDT",
    "default_timeframe": "15m"
}

# EMA计算常量
EMA_CONFIG = {
    "smoothing_factor": 2.0,
    "min_periods": 1
}

# 信号置信度阈值
CONFIDENCE_THRESHOLDS = {
    "high": 0.8,
    "medium": 0.6,
    "low": 0.4
}

# 风险管理常量
RISK_MANAGEMENT = {
    "default_stop_loss_pct": 0.02,  # 2%
    "default_take_profit_pct": 0.04,  # 4%
    "max_position_size": 0.1,  # 10% of capital
    "min_position_size": 0.01  # 1% of capital
}

# 数据验证常量
DATA_VALIDATION = {
    "min_ohlcv_points": 10,
    "max_price_change_pct": 0.2,  # 20% max change
    "volume_threshold": 0.0
}

# 默认策略参数
DEFAULT_STRATEGY_PARAMS: Dict[str, Any] = {
    "dual_ema": {
        "fast_period": DUAL_EMA_CONFIG["default_fast_period"],
        "slow_period": DUAL_EMA_CONFIG["default_slow_period"],
        "confidence_threshold": DUAL_EMA_CONFIG["confidence_threshold"]
    },
    "timeframe": DUAL_EMA_CONFIG["default_timeframe"],
    "symbol": DUAL_EMA_CONFIG["default_symbol"]
}

# 日志级别配置
LOG_LEVELS = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50
}

# API配置常量
API_CONFIG = {
    "timeout_seconds": 30,
    "max_retries": 3,
    "retry_delay": 1.0
}

# 缓存配置
CACHE_CONFIG = {
    "ttl_seconds": 300,  # 5 minutes
    "max_size": 1000
}

# 市场状态常量
class MarketState(str, Enum):
    """市场状态枚举"""
    BULLISH = "BULLISH"  # 上涨
    BEARISH = "BEARISH"  # 下跌
    SIDEWAYS = "SIDEWAYS"  # 横盘
    VOLATILE = "VOLATILE"  # 高波动

# 技术指标阈值
TECHNICAL_THRESHOLDS = {
    "ema_cross_distance": 0.001,  # 0.1%
    "volume_surge_multiplier": 1.5,
    "price_volatility_threshold": 0.02  # 2%
}

# 错误消息常量
ERROR_MESSAGES = {
    "insufficient_data": "数据不足，无法计算指标",
    "invalid_parameters": "参数无效",
    "calculation_error": "指标计算错误",
    "network_error": "网络连接错误",
    "api_error": "API调用错误"
}

# 成功消息常量
SUCCESS_MESSAGES = {
    "signal_generated": "信号生成成功",
    "strategy_executed": "策略执行成功",
    "data_validated": "数据验证通过"
}
