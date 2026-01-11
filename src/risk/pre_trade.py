"""
交易前检查 (Pre-Trade Check)

在下单前执行风险检查，防止异常交易。

核心职责：
- 检查单笔订单金额是否超过阈值
- 检查下单频率是否过高
- 全局敞口检查（防止总杠杆超限）
- 拒绝不合规的订单
"""

import logging
import time
from typing import Dict, Optional, TYPE_CHECKING
from dataclasses import dataclass
from ..config.risk_config import RiskConfig, DEFAULT_RISK_CONFIG

if TYPE_CHECKING:
    from ..oms.position_manager import PositionManager
    from ..oms.capital_commander import CapitalCommander

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
        frequency_window: float = 1.0,
        risk_config: Optional[RiskConfig] = None
    ):
        """
        初始化交易前检查

        Args:
            max_order_amount (float): 单笔订单最大金额（USDT）
            max_frequency (int): 频率限制（N 秒内最多 N 单）
            frequency_window (float): 频率时间窗口（秒）
            risk_config (RiskConfig): 风控配置
        """
        self.max_order_amount = max_order_amount
        self.max_frequency = max_frequency
        self.frequency_window = frequency_window
        self._risk_config = risk_config or DEFAULT_RISK_CONFIG

        # 订单历史 {timestamp: order_id}
        self._order_history: Dict[float, str] = {}

        # 统计信息
        self._total_checks = 0
        self._total_rejections = 0

        # 外部依赖（用于全局敞口检查）
        self._position_manager: Optional['PositionManager'] = None
        self._capital_commander: Optional['CapitalCommander'] = None

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

        # 4. 全局敞口检查（如果配置了 PositionManager 和 CapitalCommander）
        global_exposure_passed, exposure_reason = self._check_global_exposure(order)
        if not global_exposure_passed:
            self._total_rejections += 1
            logger.warning(f"风控拒绝: {exposure_reason}")
            return False, exposure_reason

        # 通过检查
        logger.debug(
            f"风控通过: symbol={order.get('symbol')}, "
            f"amount={amount_usdt:.2f} USDT"
        )
        return True, None

    def _check_global_exposure(self, order: dict) -> tuple[bool, Optional[str]]:
        """
        检查全局敞口（防止总杠杆超限）

        Args:
            order (dict): 订单信息

        Returns:
            tuple: (是否通过, 拒绝原因)
        """
        # 如果没有配置相关依赖，跳过此检查
        if not self._position_manager or not self._capital_commander:
            return True, None

        try:
            # 获取订单信息
            symbol = order.get('symbol')
            size = order.get('size', 0)
            price = order.get('price', 0)

            if size <= 0 or price <= 0:
                return False, "订单数量或价格无效"

            # 计算新订单的敞口
            new_order_exposure = size * price

            # 获取当前总持仓敞口
            current_total_exposure = self._position_manager.get_total_exposure()

            # 获取账户总权益
            total_equity = self._capital_commander.get_total_equity()

            if total_equity <= 0:
                return False, "账户权益无效"

            # 计算总敞口和真实杠杆
            total_exposure = current_total_exposure + new_order_exposure
            real_leverage = total_exposure / total_equity

            # 检查是否超过全局杠杆上限
            if real_leverage > self._risk_config.MAX_GLOBAL_LEVERAGE:
                reason = (
                    f"REJECT: Global Leverage Limit Exceeded (Risk of Ruin) - "
                    f"leverage={real_leverage:.2f}x > "
                    f"limit={self._risk_config.MAX_GLOBAL_LEVERAGE}x"
                )
                return False, reason

            # 检查单一币种敞口限制
            symbol_exposure = self._position_manager.get_symbol_exposure(symbol)
            total_symbol_exposure = symbol_exposure + new_order_exposure
            symbol_exposure_ratio = total_symbol_exposure / total_equity

            if symbol_exposure_ratio > self._risk_config.MAX_SINGLE_SYMBOL_EXPOSURE:
                reason = (
                    f"REJECT: Single Symbol Exposure Limit Exceeded - "
                    f"{symbol} ratio={symbol_exposure_ratio * 100:.1f}% > "
                    f"limit={self._risk_config.MAX_SINGLE_SYMBOL_EXPOSURE * 100:.1f}%"
                )
                return False, reason

            # 通过检查
            logger.debug(
                f"全局敞口检查通过: leverage={real_leverage:.2f}x, "
                f"symbol_ratio={symbol_exposure_ratio * 100:.1f}%"
            )
            return True, None

        except Exception as e:
            logger.error(f"全局敞口检查异常: {e}", exc_info=True)
            # 出错时保守处理：拒绝订单
            return False, f"敞口检查异常: {e}"

    def set_position_manager(self, position_manager: 'PositionManager'):
        """
        设置 PositionManager 引用（用于全局敞口检查）

        Args:
            position_manager (PositionManager): 持仓管理器实例
        """
        self._position_manager = position_manager
        logger.debug("PositionManager 引用已设置")

    def set_capital_commander(self, capital_commander: 'CapitalCommander'):
        """
        设置 CapitalCommander 引用（用于全局敞口检查）

        Args:
            capital_commander (CapitalCommander): 资金指挥官实例
        """
        self._capital_commander = capital_commander
        logger.debug("CapitalCommander 引用已设置")

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
