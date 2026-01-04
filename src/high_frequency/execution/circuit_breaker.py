"""
风控熔断器

本模块提供风险控制功能，用于 HFT 场景。

核心功能：
- 冷却期控制（防止过度交易）
- 当日亏损监控（保护资金）
- 单例模式（全局统一管理）

设计原则：
- 线程安全
- 快速判断（不阻塞交易流程）
- 清晰的风控规则
"""

import time
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class RiskGuard:
    """
    风控熔断器（单例类）

    维护交易冷却期和当日亏损监控，提供风险判断接口。

    风控规则：
    1. 冷却期：两次交易之间至少间隔 60 秒
    2. 亏损限制：当日亏损不能超过初始余额的 3%

    Example:
        >>> # 获取单例实例
        >>> risk_guard = RiskGuard()
        >>>
        >>> # 设置余额
        >>> risk_guard.set_balances(initial=10000.0, current=9850.0)
        >>>
        >>> # 检查是否可以交易
        >>> if risk_guard.can_trade():
        ...     print("允许交易")
        ... else:
        ...     print("风控拒绝交易")
    """

    # 单例实例
    _instance = None
    _lock = threading.Lock()

    # 风控参数
    COOLDOWN_PERIOD = 60.0  # 冷却期（秒）
    MAX_LOSS_PERCENT = 0.03  # 最大亏损比例（3%）

    def __new__(cls):
        """
        单例模式实现

        Returns:
            RiskGuard: 单例实例
        """
        if cls._instance is None:
            with cls._lock:
                # 双重检查，防止多线程创建多个实例
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        初始化风控熔断器

        由于使用单例模式，确保只初始化一次。
        """
        # 检查是否已初始化
        if not hasattr(self, 'initialized'):
            # 累计亏损
            self.daily_loss = 0.0

            # 最后交易时间
            self.last_trade_time = 0.0

            # 余额信息
            self.initial_balance: Optional[float] = None
            self.current_balance: Optional[float] = None

            # 标记已初始化
            self.initialized = True

            logger.info("RiskGuard 初始化完成（单例模式）")

    def set_balances(self, initial: float, current: float):
        """
        设置余额信息

        Args:
            initial (float): 初始余额
            current (float): 当前余额

        Raises:
            ValueError: 如果余额无效

        Example:
            >>> risk_guard = RiskGuard()
            >>> risk_guard.set_balances(initial=10000.0, current=9850.0)
        """
        if initial <= 0:
            raise ValueError(f"初始余额无效: {initial}，必须大于 0")

        if current < 0:
            raise ValueError(f"当前余额无效: {current}，不能小于 0")

        self.initial_balance = initial
        self.current_balance = current

        # 计算当前亏损比例
        loss_percent = self._calculate_loss_percent()

        logger.info(
            f"设置余额: initial={initial:.2f}, current={current:.2f}, "
            f"loss_percent={loss_percent * 100:.2f}%"
        )

    def _calculate_loss_percent(self) -> float:
        """
        计算当前亏损比例

        Returns:
            float: 亏损比例（0.0 ~ 1.0）
        """
        if not self.initial_balance or self.initial_balance == 0:
            return 0.0

        if not self.current_balance:
            return 0.0

        loss = self.initial_balance - self.current_balance
        loss_percent = loss / self.initial_balance

        return max(0.0, loss_percent)

    def can_trade(self) -> bool:
        """
        检查是否允许交易

        风控检查：
        1. 冷却期检查：距离上次交易是否超过 60 秒
        2. 亏损检查：当日亏损是否超过 3%

        Returns:
            bool: True 表示允许交易，False 表示拒绝交易

        Example:
            >>> if risk_guard.can_trade():
            ...     # 执行交易
            ...     pass
            ... else:
            ...     logger.warning("风控拒绝交易")
        """
        current_time = time.time()

        # 1. 检查冷却期
        time_since_last_trade = current_time - self.last_trade_time

        if self.last_trade_time > 0 and time_since_last_trade < self.COOLDOWN_PERIOD:
            remaining_time = self.COOLDOWN_PERIOD - time_since_last_trade
            logger.warning(
                f"风控拒绝: 在冷却期 ({time_since_last_trade:.1f}s < {self.COOLDOWN_PERIOD}s), "
                f"还需等待 {remaining_time:.1f}s"
            )
            return False

        # 2. 检查亏损限制
        loss_percent = self._calculate_loss_percent()

        if loss_percent > self.MAX_LOSS_PERCENT:
            logger.critical(
                f"风控拒绝: 当日亏损超过阈值 "
                f"({loss_percent * 100:.2f}% > {self.MAX_LOSS_PERCENT * 100:.2f}%), "
                f"停止交易"
            )
            return False

        logger.debug("风控检查通过，允许交易")
        return True

    def record_trade(self, pnl: float):
        """
        记录交易盈亏

        更新累计亏损和最后交易时间。

        Args:
            pnl (float): 交易盈亏（正数为盈利，负数为亏损）

        Example:
            >>> # 记录盈利
            >>> risk_guard.record_trade(pnl=100.0)
            >>>
            >>> # 记录亏损
            >>> risk_guard.record_trade(pnl=-50.0)
        """
        # 更新累计亏损
        if pnl < 0:
            loss = abs(pnl)
            self.daily_loss += loss
            logger.warning(
                f"记录亏损: {pnl:.2f}, 累计亏损: {self.daily_loss:.2f}"
            )
        else:
            logger.info(f"记录盈利: {pnl:.2f}")

        # 更新最后交易时间
        self.last_trade_time = time.time()

    def reset_daily_loss(self):
        """
        重置当日亏损

        通常在每日开始时调用。

        Example:
            >>> # 每日开始时重置
            >>> risk_guard.reset_daily_loss()
        """
        old_loss = self.daily_loss
        self.daily_loss = 0.0

        logger.info(f"重置当日亏损: {old_loss:.2f} -> 0.00")

    def get_status(self) -> dict:
        """
        获取风控状态信息

        Returns:
            dict: 包含风控状态的字典

        Example:
            >>> status = risk_guard.get_status()
            >>> print(f"累计亏损: {status['daily_loss']}")
            >>> print(f"冷却剩余: {status['cooldown_remaining']}s")
        """
        current_time = time.time()

        # 计算冷却剩余时间
        time_since_last_trade = current_time - self.last_trade_time
        cooldown_remaining = max(0.0, self.COOLDOWN_PERIOD - time_since_last_trade)

        # 计算亏损比例
        loss_percent = self._calculate_loss_percent()

        return {
            'daily_loss': self.daily_loss,
            'loss_percent': loss_percent,
            'max_loss_percent': self.MAX_LOSS_PERCENT,
            'initial_balance': self.initial_balance,
            'current_balance': self.current_balance,
            'last_trade_time': self.last_trade_time,
            'cooldown_period': self.COOLDOWN_PERIOD,
            'cooldown_remaining': cooldown_remaining,
            'can_trade': self.can_trade()
        }

    def get_remaining_cooldown(self) -> float:
        """
        获取冷却剩余时间

        Returns:
            float: 冷却剩余时间（秒）

        Example:
            >>> remaining = risk_guard.get_remaining_cooldown()
            >>> if remaining > 0:
            ...     print(f"还需等待 {remaining:.1f} 秒")
        """
        current_time = time.time()
        time_since_last_trade = current_time - self.last_trade_time

        remaining = max(0.0, self.COOLDOWN_PERIOD - time_since_last_trade)

        return remaining

    def is_loss_limit_exceeded(self) -> bool:
        """
        检查是否超过亏损限制

        Returns:
            bool: True 表示超过亏损限制
        """
        loss_percent = self._calculate_loss_percent()
        return loss_percent > self.MAX_LOSS_PERCENT

    def update_current_balance(self, balance: float):
        """
        更新当前余额

        Args:
            balance (float): 当前余额

        Example:
            >>> risk_guard.update_current_balance(9900.0)
        """
        if balance < 0:
            raise ValueError(f"当前余额无效: {balance}，不能小于 0")

        self.current_balance = balance

        logger.debug(f"更新当前余额: {balance:.2f}")
