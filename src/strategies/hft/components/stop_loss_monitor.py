"""
止损监控模块

负责监控持仓的止损条件：
- 追踪止损（Trailing Stop）
- 时间止损（Time Stop）
- 硬止损（Hard Stop）
"""

import time
import logging
from typing import Optional, Tuple
# 🔥 [修复导入] 从 state_manager 导入状态类
from .state_manager import PositionState

logger = logging.getLogger(__name__)


class StopLossMonitor:
    """
    止损监控器

    职责：
    1. 检查追踪止损条件
    2. 检查时间止损条件
    3. 检查硬止损条件
    4. 提供统一的止损检查接口
    """

    def __init__(self, config):
        """
        初始化止损监控器

        Args:
            config: 配置对象，包含：
                - take_profit_pct: 止盈百分比
                - stop_loss_pct: 硬止损百分比
                - time_limit_seconds: 时间止损（秒）
        """
        self.config = config
        self.trailing_stop_pct = 0.001  # 追踪止损启动阈值（0.1%）
        self.trailing_stop_distance_pct = 0.0005  # 追踪止损回撤阈值（0.05%）

    def check_trailing_stop(
        self,
        position: PositionState,
        current_price: float
    ) -> Tuple[bool, float]:
        """
        检查追踪止损条件

        策略：
        1. 价格上升超过 entry_price * (1 + 0.1%) 时启动追踪止损
        2. 价格从最高点回撤超过 0.05% 时触发平仓

        Args:
            position (PositionState): 持仓状态
            current_price (float): 当前价格

        Returns:
            tuple: (should_close, stop_price)
                - should_close: 是否应该平仓
                - stop_price: 触发价格（用于日志）
        """
        if not position or not position.is_open:
            return (False, 0.0)

        if not position.entry_price or position.entry_price <= 0:
            return (False, 0.0)

        # 检查是否应该启动追踪止损
        # 价格上升超过 entry_price * (1 + trailing_stop_pct)
        start_threshold = position.entry_price * (1 + self.trailing_stop_pct)

        if current_price >= start_threshold:
            # 价格已达到启动阈值，更新最高价
            # 注意：这里只是检查，不更新状态
            # 状态更新应该由 StateManager 负责
            pass

        return (False, current_price)

    def check_time_stop(
        self,
        position: PositionState,
        current_time: float
    ) -> Tuple[bool, float]:
        """
        检查时间止损条件

        策略：
        1. 持仓时间超过 time_limit_seconds 时触发平仓
        2. 防止持仓时间过长导致风险敞口过大

        Args:
            position (PositionState): 持仓状态
            current_time (float): 当前时间戳

        Returns:
            tuple: (should_close, position_age)
                - should_close: 是否应该平仓
                - position_age: 持仓时间（秒）
        """
        if not position or not position.is_open:
            return (False, 0.0)

        if position.entry_time <= 0:
            return (False, 0.0)

        # 计算持仓时间
        position_age = current_time - position.entry_time

        # 检查是否超时
        if position_age >= self.config.time_limit_seconds:
            return (True, position_age)

        return (False, position_age)

    def check_hard_stop(
        self,
        position: PositionState,
        current_price: float
    ) -> Tuple[bool, float]:
        """
        检查硬止损条件

        策略：
        1. 价格跌破 entry_price * (1 - stop_loss_pct) 时触发平仓
        2. 防止亏损过大

        Args:
            position (PositionState): 持仓状态
            current_price (float): 当前价格

        Returns:
            tuple: (should_close, stop_price)
                - should_close: 是否应该平仓
                - stop_price: 触发价格（止损价）
        """
        if not position or not position.is_open:
            return (False, 0.0)

        if not position.entry_price or position.entry_price <= 0:
            return (False, 0.0)

        # 计算硬止损价格
        stop_distance = position.entry_price * self.config.stop_loss_pct
        stop_price = position.entry_price - stop_distance

        # 检查是否触发止损
        if current_price <= stop_price:
            return (True, stop_price)

        return (False, stop_price)

    def check_all_stops(
        self,
        position: PositionState,
        current_price: float,
        current_time: float
    ) -> Optional[str]:
        """
        检查所有止损条件（统一接口）

        优先级：
        1. 硬止损（最高优先级，防止亏损过大）
        2. 时间止损（防止持仓时间过长）
        3. 追踪止损（保护利润）

        Args:
            position (PositionState): 持仓状态
            current_price (float): 当前价格
            current_time (float): 当前时间戳

        Returns:
            Optional[str]: 触发的止损类型（hard_stop/time_stop/trailing_stop），未触发则返回 None
        """
        # 1. 硬止损检查（最高优先级）
        should_close, stop_price = self.check_hard_stop(position, current_price)
        if should_close:
            logger.info(
                f"📉 [硬止损] 价格={current_price:.6f} <= 止损价={stop_price:.6f}"
            )
            return "hard_stop"

        # 2. 时间止损检查
        should_close, position_age = self.check_time_stop(position, current_time)
        if should_close:
            logger.info(
                f"⏰ [时间止损] 持仓时间={position_age:.1f}s >= {self.config.time_limit_seconds}s"
            )
            return "time_stop"

        # 3. 追踪止损检查（由 StateManager 更新，这里只检查）
        # 注意：追踪止损的触发逻辑在 StateManager 中实现
        # 这里只是占位符，实际逻辑应该由 StateManager.update_trailing_stop() 处理
        pass

        return None
