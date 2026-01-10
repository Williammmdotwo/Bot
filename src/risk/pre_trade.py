"""
交易前检查 (Pre-Trade Check)

在下单前执行风险检查，防止异常交易。

核心职责：
- 检查单笔订单金额是否超过阈值
- 检查下单频率是否过高
- 拒绝不合规的订单
"""

import logging
import time
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PreTradeCheck:
    """
    交易前检查

    在下单前执行风险检查，防止异常交易。

    检查项：
    1. 单笔订单金额是否超过阈值（默认 2000 USDT）
    2. 下单频率限制（1 秒内 < 5 单）

    Example:
        >>> checker = PreTradeCheck(
        ...     max_order_amount=2000.0,
        ...     max_frequency=5
        ... )
        >>>
        >>> # 检查订单
        >>> order = {'symbol': 'BTC-USDT-SWAP', 'amount_usdt': 1000.0}
        >>> passed, reason = checker.check(order)
        >>> if passed:
        ...     print("订单通过风控")
        ... else:
        ...     print(f"订单被拒绝: {reason}")
    """

    def __init__(
        self,
        max_order_amount: float = 2000.0,
        max_frequency: int = 5,
        frequency_window: float = 1.0
    ):
        """
        初始化交易前检查

        Args:
            max_order_amount (float): 单笔订单最大金额（USDT）
            max_frequency (int): 频率限制（N 秒内最多 N 单）
            frequency_window (float): 频率时间窗口（秒）
        """
        self.max_order_amount = max_order_amount
        self.max_frequency = max_frequency
        self.frequency_window = frequency_window

        # 订单历史 {timestamp: order_id}
        self._order_history: Dict[float, str] = {}

        # 统计信息
        self._total_checks = 0
        self._total_rejections = 0

        logger.info(
            f"PreTradeCheck 初始化: max_amount={max_order_amount:.2f} USDT, "
            f"max_frequency={max_frequency}/{frequency_window}s"
        )

    def check(self, order: dict) -> tuple[bool, Optional[str]]:
        """
        检查订单是否符合风控要求

        Args:
            order (dict): 订单信息
                {
                    'symbol': str,
                    'side': str,
                    'size': float,
                    'price': float,
                    'amount_usdt': float  # 订单金额（USDT）
                }

        Returns:
            tuple: (是否通过, 拒绝原因)
                - True, None: 通过
                - False, "原因": 未通过
        """
        self._total_checks += 1

        # 1. 检查订单金额
        amount_usdt = order.get('amount_usdt', 0)
        if amount_usdt > self.max_order_amount:
            self._total_rejections += 1
            reason = (
                f"订单金额超限: {amount_usdt:.2f} USDT > "
                f"{self.max_order_amount:.2f} USDT"
            )
            logger.warning(f"风控拒绝: {reason}")
            return False, reason

        # 2. 检查下单频率
        current_time = time.time()
        self._clean_order_history(current_time)

        recent_count = len(self._order_history)
        if recent_count >= self.max_frequency:
            self._total_rejections += 1
            reason = (
                f"下单频率过高: {recent_count} 单 / "
                f"{self.frequency_window}s > {self.max_frequency} 单"
            )
            logger.warning(f"风控拒绝: {reason}")
            return False, reason

        # 3. 记录订单
        order_id = order.get('order_id', str(current_time))
        self._order_history[current_time] = order_id

        # 通过检查
        logger.debug(
            f"风控通过: symbol={order.get('symbol')}, "
            f"amount={amount_usdt:.2f} USDT"
        )
        return True, None

    def _clean_order_history(self, current_time: float):
        """
        清理过期的订单历史

        Args:
            current_time (float): 当前时间
        """
        expired_time = current_time - self.frequency_window
        expired_timestamps = [
            ts for ts in self._order_history.keys()
            if ts < expired_time
        ]

        for ts in expired_timestamps:
            del self._order_history[ts]

    def get_statistics(self) -> dict:
        """
        获取统计信息

        Returns:
            dict: 统计数据
        """
        current_time = time.time()
        self._clean_order_history(current_time)

        return {
            'total_checks': self._total_checks,
            'total_rejections': self._total_rejections,
            'rejection_rate': (
                self._total_rejections / self._total_checks
                if self._total_checks > 0 else 0.0
            ),
            'recent_orders': len(self._order_history),
            'max_order_amount': self.max_order_amount,
            'max_frequency': self.max_frequency,
            'frequency_window': self.frequency_window
        }

    def reset_statistics(self):
        """重置统计信息"""
        self._order_history.clear()
        self._total_checks = 0
        self._total_rejections = 0
        logger.info("PreTradeCheck 统计信息已重置")

    def update_config(
        self,
        max_order_amount: Optional[float] = None,
        max_frequency: Optional[int] = None,
        frequency_window: Optional[float] = None
    ):
        """
        更新配置

        Args:
            max_order_amount (float): 单笔订单最大金额（USDT）
            max_frequency (int): 频率限制
            frequency_window (float): 频率时间窗口（秒）
        """
        if max_order_amount is not None:
            self.max_order_amount = max_order_amount
            logger.info(f"max_order_amount 更新为 {max_order_amount:.2f} USDT")

        if max_frequency is not None:
            self.max_frequency = max_frequency
            logger.info(f"max_frequency 更新为 {max_frequency} 单")

        if frequency_window is not None:
            self.frequency_window = frequency_window
            logger.info(f"frequency_window 更新为 {frequency_window}s")
