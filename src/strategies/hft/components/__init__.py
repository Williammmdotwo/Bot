"""
ScalperV1 策略组件模块

将策略逻辑拆分为独立、可测试的组件：
- SignalGenerator: 信号生成（EMA、Imbalance、Spread）
- ExecutionAlgo: 执行算法（挂单、插队、模拟盘适配）
- StateManager: 状态管理（持仓、订单、冷却、自愈）
- StopLossMonitor: 止损监控（追踪止损、时间止损、硬止损）
- OrderMonitor: 订单监控（追单、深度感知撤单）
"""

import logging

from .signal_generator import SignalGenerator
from .execution_algo import ExecutionAlgo
from .state_manager import StateManager
from .stop_loss_monitor import StopLossMonitor
from .order_monitor import OrderMonitor

__all__ = [
    'SignalGenerator',
    'ExecutionAlgo',
    'StateManager',
    'StopLossMonitor',
    'OrderMonitor',
]

logger = logging.getLogger(__name__)
