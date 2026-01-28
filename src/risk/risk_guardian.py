"""
风控守卫 (Risk Guardian)

统一的风控入口，整合 PreTradeCheck、CapitalCommander 和 OrderManager 的风控逻辑。

核心职责：
- 统一风控入口：validate_order()
- 整合所有风控检查：金额、频率、敞口、杠杆、保证金、仓位
- 提供统一返回值：(is_passed, reason, suggested_size)
- 优化性能：避免重复计算

设计原则：
- 单一职责：专注风控
- 统一接口：简化调用方逻辑
- 性能优化：缓存计算结果
"""

import logging
import time
from typing import Dict, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from ..oms.position_manager import PositionManager
    from ..oms.capital_commander import CapitalCommander
    from ..config.risk_config import RiskConfig

logger = logging.getLogger(__name__)


@dataclass
class RiskValidationResult:
    """风控验证结果"""
    is_passed: bool              # 是否通过
    reason: Optional[str]         # 拒绝原因（如果未通过）
    suggested_size: float         # 建议仓位大小（如果通过）

    def to_tuple(self) -> Tuple[bool, Optional[str], float]:
        """转换为元组"""
        return (self.is_passed, self.reason, self.suggested_size)


class RiskGuardian:
    """
    风控守卫

    整合所有风控检查，提供统一的验证接口。

    检查项（按优先级排序）：
    1. Bypass 检查：紧急平仓跳过所有风控
    2. 回撤熔断：策略回撤超限则禁止开仓
    3. 频率限制：防止高频下单
    4. 单笔金额限制：防止过大单笔订单
    5. 策略合规性：策略级别的风控
    6. 全局敞口检查：防止总杠杆超限
    7. 购买力检查：确保有足够保证金
    8. 仓位计算：基于风险计算安全仓位

    Example:
        >>> guardian = RiskGuardian(
        ...     position_manager=pm,
        ...     capital_commander=cc,
        ...     risk_config=risk_config
        ... )
        >>>
        >>> # 统一风控检查
        >>> result = guardian.validate_order(
        ...     symbol='BTC-USDT-SWAP',
        ...     side='buy',
        ...     size=1.0,
        ...     price=50000.0,
        ...     strategy_id='vulture',
        ...     stop_loss_price=49500.0
        ... )
        >>>
        >>> if result.is_passed:
        ...     print(f"通过，建议仓位: {result.suggested_size}")
        ... else:
        ...     print(f"拒绝: {result.reason}")
    """

    def __init__(
        self,
        position_manager: 'PositionManager',
        capital_commander: 'CapitalCommander',
        risk_config: 'RiskConfig',
        max_order_amount: float = 2000.0,
        max_frequency: int = 5,
        frequency_window: float = 1.0
    ):
        """
        初始化风控守卫

        Args:
            position_manager (PositionManager): 持仓管理器
            capital_commander (CapitalCommander): 资金指挥官
            risk_config (RiskConfig): 风控配置
            max_order_amount (float): 单笔订单最大金额（USDT）
            max_frequency (int): 频率限制（N 秒内最多 N 单）
            frequency_window (float): 频率时间窗口（秒）
        """
        self._position_manager = position_manager
        self._capital_commander = capital_commander
        self._risk_config = risk_config

        # 频率限制配置
        self.max_order_amount = max_order_amount
        self.max_frequency = max_frequency
        self.frequency_window = frequency_window

        # 订单历史 {timestamp: order_id}
        self._order_history: Dict[float, str] = {}

        # 统计信息
        self._total_checks = 0
        self._total_rejections = 0

        # 缓存优化：避免重复计算
        self._cache_timeout = 1.0  # 缓存超时时间（秒）
        self._cache: Dict[str, Tuple[float, float]] = {}

        logger.info(
            f"RiskGuardian 初始化: max_amount={max_order_amount:.2f} USDT, "
            f"max_frequency={max_frequency}/{frequency_window}s, "
            f"risk_per_trade={risk_config.RISK_PER_TRADE_PCT * 100:.1f}%"
        )

    def validate_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float,
        strategy_id: str,
        stop_loss_price: float = None,
        bypass: bool = False
    ) -> RiskValidationResult:
        """
        统一风控验证入口

        执行所有风控检查，返回统一的验证结果。

        Args:
            symbol (str): 交易对
            side (str): 订单方向（buy/sell）
            size (float): 订单数量
            price (float): 订单价格
            strategy_id (str): 策略 ID
            stop_loss_price (float): 止损价格（用于仓位计算）
            bypass (bool): 是否跳过风控检查（用于紧急平仓）

        Returns:
            RiskValidationResult: 验证结果
                - is_passed: 是否通过
                - reason: 拒绝原因（如果未通过）
                - suggested_size: 建议仓位大小
        """
        self._total_checks += 1

        # 🔥 检查 1：Bypass 检查（紧急平仓）
        if bypass:
            logger.debug(
                f"🔓 [Bypass 风控] 紧急平仓跳过所有检查: "
                f"symbol={symbol}, side={side}, size={size:.4f}"
            )
            return RiskValidationResult(
                is_passed=True,
                reason=None,
                suggested_size=size
            )

        # 计算订单金额
        amount_usdt = size * price

        # 🔥 检查 2：回撤熔断（仅对开仓订单）
        if self._is_circuit_breaker_triggered(strategy_id, side, symbol):
            reason = f"策略 {strategy_id} 回撤熔断触发，禁止开仓"
            self._total_rejections += 1
            logger.warning(f"🛑 [风控拒绝] {reason}")  # 🔥 [修复] 改为 WARNING
            return RiskValidationResult(
                is_passed=False,
                reason=reason,
                suggested_size=0.0
            )

        # 🔥 检查 3：频率限制
        if not self._check_frequency(symbol, side, size):
            recent_count = len(self._order_history)
            reason = (
                f"下单频率过高: {recent_count} 单 / "
                f"{self.frequency_window}s > {self.max_frequency} 单"
            )
            self._total_rejections += 1
            logger.warning(f"🛑 [风控拒绝] {reason}")  # 🔥 [修复] 改为 WARNING
            return RiskValidationResult(
                is_passed=False,
                reason=reason,
                suggested_size=0.0
            )

        # 🔥 检查 4：单笔金额限制
        if amount_usdt > self.max_order_amount:
            reason = (
                f"订单金额超限: {amount_usdt:.2f} USDT > "
                f"{self.max_order_amount:.2f} USDT"
            )
            self._total_rejections += 1
            logger.warning(f"🛑 [风控拒绝] {reason}")  # 🔥 [修复] 改为 WARNING
            return RiskValidationResult(
                is_passed=False,
                reason=reason,
                suggested_size=0.0
            )

        # 🔥 检查 5：策略合规性
        policy_passed, policy_reason = self._capital_commander.check_policy_compliance(
            strategy_id=strategy_id,
            amount_usdt=amount_usdt,
            entry_price=price
        )
        if not policy_passed:
            self._total_rejections += 1
            logger.warning(f"🛑 [风控拒绝] {policy_reason}")  # 🔥 [修复] 改为 WARNING
            return RiskValidationResult(
                is_passed=False,
                reason=policy_reason,
                suggested_size=0.0
            )

        # 🔥 检查 6：全局敞口检查（防止总杠杆超限）
        exposure_passed, exposure_reason = self._check_global_exposure(
            symbol=symbol,
            size=size,
            price=price
        )
        if not exposure_passed:
            self._total_rejections += 1
            # 全局杠杆超限是严重风险，保持 WARNING
            if "Global Leverage Limit Exceeded" in exposure_reason:
                logger.warning(f"🚨 [风险警报] {exposure_reason}")
            else:
                logger.debug(f"风控拒绝: {exposure_reason}")
            return RiskValidationResult(
                is_passed=False,
                reason=exposure_reason,
                suggested_size=0.0
            )

        # 🔥 检查 7：购买力检查（保证金）
        has_power = self._capital_commander.check_buying_power(
            strategy_id=strategy_id,
            amount_usdt=amount_usdt,
            symbol=symbol,
            side=side
        )
        if not has_power:
            reason = (
                f"购买力不足 [{strategy_id}]: "
                f"amount={amount_usdt:.2f} USDT"
            )
            self._total_rejections += 1
            logger.warning(f"🛑 [风控拒绝] {reason}")  # 🔥 [修复] 改为 WARNING
            return RiskValidationResult(
                is_passed=False,
                reason=reason,
                suggested_size=0.0
            )

        # 🔥 检查 8：仓位计算（基于风险计算安全仓位）
        # 只有提供了止损价格才进行仓位计算
        suggested_size = size
        if stop_loss_price and stop_loss_price > 0:
            suggested_size = self._calculate_safe_quantity(
                symbol=symbol,
                entry_price=price,
                stop_loss_price=stop_loss_price,
                strategy_id=strategy_id
            )

            # 如果计算出的建议仓位为 0，说明触发了风控
            if suggested_size <= 0:
                reason = "仓位计算风控触发，建议仓位为 0"
                self._total_rejections += 1
                logger.warning(f"🛑 [风控拒绝] {reason}")  # 🔥 [修复] 改为 WARNING
                return RiskValidationResult(
                    is_passed=False,
                    reason=reason,
                    suggested_size=0.0
                )
        else:
            # 如果没有止损价格，使用原始仓位
            suggested_size = size

        # 🎉 所有检查通过
        logger.debug(
            f"✅ 风控通过: symbol={symbol}, side={side}, "
            f"size={size:.4f}, suggested={suggested_size:.4f}, "
            f"amount={amount_usdt:.2f} USDT"
        )
        return RiskValidationResult(
            is_passed=True,
            reason=None,
            suggested_size=suggested_size
        )

    def _is_circuit_breaker_triggered(
        self,
        strategy_id: str,
        side: str,
        symbol: str
    ) -> bool:
        """
        检查策略是否触发回撤熔断

        🔥 仅对开仓订单进行检查（避免阻止平仓）

        Args:
            strategy_id (str): 策略 ID
            side (str): 订单方向
            symbol (str): 交易对

        Returns:
            bool: 是否触发熔断
        """
        # 判断是否为平仓操作
        is_reducing = False
        position = self._position_manager.get_position(symbol)

        if position and position.size != 0:
            if position.size > 0 and side == 'sell':
                # 多头平仓
                is_reducing = True
            elif position.size < 0 and side == 'buy':
                # 空头平仓
                is_reducing = True

        # 平仓操作不检查熔断
        if is_reducing:
            return False

        # 检查策略熔断
        return self._capital_commander.is_strategy_circuit_breaker_triggered(strategy_id)

    def _check_frequency(
        self,
        symbol: str,
        side: str,
        size: float
    ) -> bool:
        """
        检查下单频率

        Args:
            symbol (str): 交易对
            side (str): 订单方向
            size (float): 订单数量

        Returns:
            bool: 是否通过
        """
        current_time = time.time()
        self._clean_order_history(current_time)

        recent_count = len(self._order_history)
        if recent_count >= self.max_frequency:
            return False

        # 记录订单
        order_id = f"{symbol}_{side}_{size:.4f}"
        self._order_history[current_time] = order_id

        return True

    def _check_global_exposure(
        self,
        symbol: str,
        size: float,
        price: float
    ) -> Tuple[bool, Optional[str]]:
        """
        检查全局敞口（防止总杠杆超限）

        Args:
            symbol (str): 交易对
            size (float): 订单数量
            price (float): 订单价格

        Returns:
            tuple: (是否通过, 拒绝原因)
        """
        try:
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

    def _calculate_safe_quantity(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        strategy_id: str
    ) -> float:
        """
        计算安全仓位大小（委托给 CapitalCommander）

        Args:
            symbol (str): 交易对
            entry_price (float): 入场价格
            stop_loss_price (float): 止损价格
            strategy_id (str): 策略 ID

        Returns:
            float: 安全仓位数量
        """
        return self._capital_commander.calculate_safe_quantity(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            strategy_id=strategy_id
        )

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

    def get_statistics(self) -> Dict:
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
        self._cache.clear()
        logger.info("RiskGuardian 统计信息已重置")

    def update_config(
        self,
        max_order_amount: Optional[float] = None,
        max_frequency: Optional[int] = None,
        frequency_window: Optional[float] = None
    ) -> None:
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
