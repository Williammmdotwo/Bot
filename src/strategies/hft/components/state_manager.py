"""
StateManager - 状态管理器

负责 ScalperV1 策略的状态管理：
- 本地持仓（Local Position）
- 活动订单（Active Orders）
- 冷却锁（Cooldowns）
- 自愈逻辑（Self-Healing）

设计原则：
- 单一职责：只负责状态管理，不涉及信号生成或执行
- 无状态：不维护任何持久化状态
- 可测试：独立的接口，易于单元测试
"""

import logging
import time
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PositionState:
    """持仓状态"""
    size: float = 0.0
    entry_price: float = 0.0
    entry_time: float = 0.0
    is_open: bool = False


@dataclass
class OrderState:
    """订单状态"""
    maker_order_id: Optional[str] = None
    maker_order_time: float = 0.0
    maker_order_price: float = 0.0
    maker_order_initial_price: float = 0.0


@dataclass
class CooldownState:
    """冷却状态"""
    last_close_time: float = 0.0
    last_exit_time: float = 0.0
    close_lock_timeout: float = 10.0


@dataclass
class SelfHealingState:
    """自愈状态"""
    consecutive_exit_failures: int = 0
    last_exit_attempt_reason: Optional[str] = None
    last_exit_attempt_time: float = 0.0
    healing_threshold: int = 3


class StateManager:
    """
    状态管理器（ScalperV1 策略）

    职责：
    1. 持仓管理（Local Position）
    2. 活动订单管理（Active Orders）
    3. 冷却锁管理（Cooldowns）
    4. 自愈逻辑（Self-Healing）

    设计原则：
    - 单一职责：只负责状态管理，不涉及信号生成或执行
    - 无状态：不维护任何持久化状态
    - 可测试：独立的接口，易于单元测试
    """

    def __init__(self, symbol: str):
        """
        初始化状态管理器

        Args:
            symbol (str): 交易对
        """
        self.symbol = symbol

        # 持仓状态
        self._position = PositionState()
        self._local_pos_size = 0.0

        # 订单状态
        self._order = OrderState()

        # 冷却状态
        self._cooldown = CooldownState()

        # 自愈状态
        self._healing = SelfHealingState()

        logger.info(f"📊 [StateManager] 初始化: symbol={symbol}")

    # ========== 持仓管理 ==========

    def update_position(self, size: float, entry_price: float, entry_time: float):
        """
        更新持仓状态

        Args:
            size (float): 持仓数量
            entry_price (float): 入场价格
            entry_time (float): 入场时间戳
        """
        self._position.size = size
        self._position.entry_price = entry_price
        self._position.entry_time = entry_time
        self._position.is_open = (abs(size) > 0.001)

        logger.debug(
            f"📊 [StateManager] {self.symbol}: "
            f"更新持仓: size={size:.4f}, "
            f"entry_price={entry_price:.6f}, "
            f"is_open={self._position.is_open}"
        )

    def get_position(self) -> PositionState:
        """
        获取当前持仓状态

        Returns:
            PositionState: 持仓状态
        """
        return self._position

    def get_local_pos_size(self) -> float:
        """
        获取本地持仓数量

        Returns:
            float: 本地持仓数量
        """
        return self._local_pos_size

    def is_position_open(self) -> bool:
        """
        检查是否有持仓

        Returns:
            bool: 是否有持仓
        """
        return self._position.is_open

    def close_position(self):
        """
        平仓（重置持仓状态）
        """
        self._position.size = 0.0
        self._position.entry_price = 0.0
        self._position.entry_time = 0.0
        self._position.is_open = False

        logger.info(f"📊 [StateManager] {self.symbol}: 平仓")

    # ========== 订单管理 ==========

    def set_maker_order(
        self,
        order_id: str,
        price: float,
        initial_price: float = 0.0
    ):
        """
        设置 Maker 订单

        Args:
            order_id (str): 订单 ID
            price (float): 挂单价格
            initial_price (float): 初始信号价格（默认等于 price）
        """
        self._order.maker_order_id = order_id
        self._order.maker_order_time = time.time()
        self._order.maker_order_price = price
        self._order.maker_order_initial_price = initial_price

        logger.debug(
            f"📊 [StateManager] {self.symbol}: "
            f"设置 Maker 订单: id={order_id}, "
            f"price={price:.6f}"
        )

    def get_maker_order_id(self) -> Optional[str]:
        """
        获取 Maker 订单 ID

        Returns:
            Optional[str]: 订单 ID
        """
        return self._order.maker_order_id

    def get_maker_order_age(self) -> float:
        """
        获取 Maker 订单存活时间（秒）

        Returns:
            float: 订单存活时间
        """
        return time.time() - self._order.maker_order_time if self._order.maker_order_time > 0 else 0.0

    def get_maker_order_price(self) -> float:
        """
        获取 Maker 订单价格

        Returns:
            float: 订单价格
        """
        return self._order.maker_order_price

    def has_active_maker_order(self) -> bool:
        """
        检查是否有活动的 Maker 订单

        Returns:
            bool: 是否有活动的订单
        """
        return self._order.maker_order_id is not None and self._order.maker_order_id != "pending"

    def clear_maker_order(self):
        """
        清除 Maker 订单状态
        """
        self._order.maker_order_id = None
        self._order.maker_order_time = 0.0
        self._order.maker_order_price = 0.0
        self._order.maker_order_initial_price = 0.0

        logger.debug(f"📊 [StateManager] {self.symbol}: 清除 Maker 订单")

    # ========== 冷却锁管理 ==========

    def update_close_time(self):
        """
        更新平仓时间（冷却时间）

        🔥 [Fix 39] 优先级反转：先检查插队，再检查超时
        确保平仓逻辑正确执行
        """
        self._cooldown.last_close_time = time.time()
        self._cooldown.last_exit_time = time.time()

        logger.debug(f"📊 [StateManager] {self.symbol}: 更新冷却时间")

    def get_last_close_time(self) -> float:
        """
        获取上次平仓时间

        Returns:
            float: 上次平仓时间戳
        """
        return self._cooldown.last_close_time

    def is_in_cooldown(self, cooldown_seconds: float) -> bool:
        """
        检查是否在冷却期

        Args:
            cooldown_seconds (float): 冷却时间（秒）

        Returns:
            bool: 是否在冷却期
        """
        return (time.time() - self._cooldown.last_close_time) < cooldown_seconds

    def update_exit_time(self):
        """
        更新退出时间（全局冷却）

        Args:
            None

        Returns:
            None
        """
        self._cooldown.last_exit_time = time.time()

        logger.debug(f"📊 [StateManager] {self.symbol}: 更新退出时间")

    def get_last_exit_time(self) -> float:
        """
        获取上次退出时间

        Returns:
            float: 上次退出时间戳
        """
        return self._cooldown.last_exit_time

    def is_in_global_cooldown(self, cooldown_seconds: float) -> bool:
        """
        检查是否在全局冷却期

        Args:
            cooldown_seconds (float): 冷却时间（秒）

        Returns:
            bool: 是否在全局冷却期
        """
        return (time.time() - self._cooldown.last_exit_time) < cooldown_seconds

    def reset_cooldown(self):
        """
        重置冷却状态

        Args:
            None

        Returns:
            None
        """
        self._cooldown.last_close_time = 0.0
        self._cooldown.last_exit_time = 0.0

        logger.info(f"📊 [StateManager] {self.symbol}: 重置冷却状态")

    # ========== 自愈逻辑 ==========

    def increment_exit_failure(self):
        """
        增加退出失败计数（自愈逻辑）

        🔥 [Fix 26 - Self-Healing]
        连续检测到多次相同的风控信号触发但未能成功发送订单时，
        立即调用持仓同步（不等待 15 秒），解决幽灵仓位循环。

        Args:
            None

        Returns:
            None
        """
        self._healing.consecutive_exit_failures += 1

        logger.debug(
            f"🚨 [StateManager] {self.symbol}: "
            f"退出失败计数: {self._healing.consecutive_exit_failures}"
        )

    def record_exit_attempt(self, reason: str):
        """
        记录平仓尝试

        Args:
            reason (str): 平仓原因
        """
        self._healing.last_exit_attempt_reason = reason
        self._healing.last_exit_attempt_time = time.time()

        logger.debug(
            f"📊 [StateManager] {self.symbol}: "
            f"记录平仓尝试: reason={reason}"
        )

    def should_trigger_healing(self) -> bool:
        """
        判断是否应该触发自愈

        🔥 [Fix 26 - Self-Healing]
        当连续检测到多次相同的风控信号触发但未能成功发送订单时，
        立即调用持仓同步（不等待 15 秒），解决幽灵仓位循环。

        Returns:
            bool: 是否应该触发自愈
        """
        return self._healing.consecutive_exit_failures >= self._healing.healing_threshold

    def reset_exit_failures(self):
        """
        重置退出失败计数

        Args:
            None

        Returns:
            None
        """
        self._healing.consecutive_exit_failures = 0
        self._healing.last_exit_attempt_reason = None
        self._healing.last_exit_attempt_time = 0.0

        logger.info(f"📊 [StateManager] {self.symbol}: 重置退出失败计数")

    def get_healing_state(self) -> SelfHealingState:
        """
        获取自愈状态

        Returns:
            SelfHealingState: 自愈状态
        """
        return self._healing

    # ========== 获取完整状态 ==========

    def get_full_state(self) -> dict:
        """
        获取完整状态（用于调试和监控）

        Returns:
            dict: 完整状态信息
        """
        return {
            'symbol': self.symbol,
            'position': {
                'size': self._position.size,
                'entry_price': self._position.entry_price,
                'entry_time': self._position.entry_time,
                'is_open': self._position.is_open
            },
            'order': {
                'maker_order_id': self._order.maker_order_id,
                'maker_order_age': self.get_maker_order_age(),
                'maker_order_price': self._order.maker_order_price,
                'has_active_order': self.has_active_maker_order()
            },
            'cooldown': {
                'last_close_time': self._cooldown.last_close_time,
                'last_exit_time': self._cooldown.last_exit_time,
                'is_in_cooldown': self.is_in_cooldown(10.0)
            },
            'healing': {
                'consecutive_exit_failures': self._healing.consecutive_exit_failures,
                'last_exit_attempt_reason': self._healing.last_exit_attempt_reason,
                'healing_threshold': self._healing.healing_threshold
            }
        }

    def reset_all(self):
        """
        重置所有状态

        Args:
            None

        Returns:
            None
        """
        self.close_position()
        self.clear_maker_order()
        self.reset_cooldown()
        self.reset_exit_failures()

        logger.info(f"🔄 [StateManager] {self.symbol}: 重置所有状态")
