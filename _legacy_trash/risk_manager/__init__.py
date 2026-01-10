"""
风险管理模块
提供交易风险控制、仓位管理和合规检查功能
"""

from .config import get_config, Config, RiskLimits
from .checks import is_order_rational, validate_order_size
from .actions import emergency_close_position
from .interface import check_order, trigger_emergency_close, health_check

__all__ = [
    'get_config',
    'Config',
    'RiskLimits',
    'is_order_rational',
    'validate_order_size',
    'emergency_close_position',
    'check_order',
    'trigger_emergency_close',
    'health_check'
]
