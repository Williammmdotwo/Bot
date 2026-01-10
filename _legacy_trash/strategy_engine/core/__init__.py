"""
策略引擎 - 核心业务逻辑模块

此模块包含策略引擎的核心业务逻辑，不包含网络调用
- data_merger: 数据合并逻辑
- signal_generator: 信号生成逻辑
- risk_optimizer: 风险优化逻辑
"""

from .data_merger import merge_historical_with_current
from .signal_generator import (
    generate_fallback_signal,
    generate_fallback_signal_with_details,
    generate_emergency_hold_signal
)
from .risk_optimizer import (
    optimize_signal_with_risk,
    apply_conservative_adjustment,
    get_volatility_metrics
)

__all__ = [
    'merge_historical_with_current',
    'generate_fallback_signal',
    'generate_fallback_signal_with_details',
    'generate_emergency_hold_signal',
    'optimize_signal_with_risk',
    'apply_conservative_adjustment',
    'get_volatility_metrics'
]
