"""
资金指挥官 (Capital Commander)

全局资金的大管家，负责资金分配和风险控制。

核心职责：
- 管理总资金池
- 分配策略资金
- 追踪策略盈亏
- 实时更新资金状态
- 基于风险的仓位计算（机构级风控）
- 交易所精度控制（lot_size, min_order_size, min_notional）

设计原则：
- 集中管理，避免资金冲突
- 监听订单成交事件，自动更新
- 提供资金检查接口
- 实现 1% Rule：每笔交易风险不超过总资金的1%
"""

import logging
import math
from typing import Dict, Optional, TYPE_CHECKING
from dataclasses import dataclass
from ..core.event_types import Event, EventType
from ..config.risk_config import RiskConfig, DEFAULT_RISK_CONFIG
from ..config.risk_profile import RiskProfile, DEFAULT_CONSERVATIVE_PROFILE

if TYPE_CHECKING:
    from ..oms.position_manager import PositionManager

logger = logging.getLogger(__name__)


@dataclass
class ExchangeInstrument:
    """交易所交易对配置"""
    symbol: str
    lot_size: float        # 数量精度（例如 0.01）
    min_order_size: float  # 最小下单数量
    min_notional: float   # 最小下单金额（USDT）


@dataclass
class StrategyCapital:
    """策略资金信息"""
    allocated: float  # 分配资金
    used: float       # 已使用资金
    profit: float     # 累计盈亏
    available: float  # 可用资金 (allocated - used + profit)

    # 风控指标
    peak_profit: float = 0.0  # 历史最高盈利
    max_drawdown_pct: float = 0.0  # 最大回撤百分比

    def update_drawdown(self):
        """更新最大回撤"""
        if self.profit > self.peak_profit:
            self.peak_profit = self.profit
            self.max_drawdown_pct = 0.0
        else:
            # 计算从峰值到当前值的回撤
            if self.peak_profit > 0:
                drawdown = (self.peak_profit - self.profit) / self.allocated
                self.max_drawdown_pct = max(self.max_drawdown_pct, drawdown)


class CapitalCommander:
    """
    资金指挥官

    全局资金管理器，负责分配和追踪各策略的资金使用情况。

    Example:
        >>> commander = CapitalCommander(total_capital=10000.0)
        >>>
        >>> # 分配资金给策略
        >>> commander.allocate_strategy("vulture", 2000.0)
        >>>
        >>> # 检查购买力
        >>> has_power = commander.check_buying_power("vulture", 1000.0)
        >>> print(has_power)
        True
        >>>
        >>> # 记录盈亏
        >>> commander.record_profit("vulture", 150.0)
    """

    def __init__(
        self,
        total_capital: float = 10000.0,
        event_bus=None,
        risk_config: Optional[RiskConfig] = None
    ):
        """
        初始化资金指挥官

        Args:
            total_capital (float): 总资金（USDT）
            event_bus: 事件总线实例
            risk_config (RiskConfig): 风控配置
        """
        self.total_capital = total_capital
        self._event_bus = event_bus
        self._risk_config = risk_config or DEFAULT_RISK_CONFIG

        # 策略资金池 {strategy_id: StrategyCapital}
        self._strategies: Dict[str, StrategyCapital] = {}

        # 全局未分配资金
        self._unallocated = total_capital

        # PositionManager 引用（用于全局敞口检查）
        self._position_manager: Optional['PositionManager'] = None

        # 交易所交易对配置（精度控制）
        self._instruments: Dict[str, ExchangeInstrument] = {}

        # 策略风控配置文件 {strategy_id: RiskProfile}
        self._strategy_profiles: Dict[str, RiskProfile] = {}

        logger.info(
            f"CapitalCommander 初始化: total_capital={total_capital:.2f} USDT, "
            f"risk_per_trade={self._risk_config.RISK_PER_TRADE_PCT * 100:.1f}%"
        )

    def register_instrument(
        self,
        symbol: str,
        lot_size: float,
        min_order_size: float,
        min_notional: float
    ):
        """
        注册交易所交易对配置

        Args:
            symbol (str): 交易对
            lot_size (float): 数量精度
            min_order_size (float): 最小下单数量
            min_notional (float): 最小下单金额（USDT）
        """
        self._instruments[symbol] = ExchangeInstrument(
            symbol=symbol,
            lot_size=lot_size,
            min_order_size=min_order_size,
            min_notional=min_notional
        )
        logger.info(
            f"注册交易对配置: {symbol} lot_size={lot_size}, "
            f"min_order_size={min_order_size}, "
            f"min_notional={min_notional:.2f} USDT"
        )

    def allocate_strategy(
        self,
        strategy_id: str,
        amount: float
    ) -> bool:
        """
        为策略分配资金

        Args:
            strategy_id (str): 策略 ID
            amount (float): 分配金额（USDT）

        Returns:
            bool: 分配是否成功
        """
        if amount <= 0:
            logger.error(f"分配金额必须大于 0: {amount}")
            return False

        if amount > self._unallocated:
            logger.error(
                f"未分配资金不足: 需要 {amount:.2f}, 可用 {self._unallocated:.2f}"
            )
            return False

        # 检查是否已分配
        if strategy_id in self._strategies:
            logger.warning(f"策略 {strategy_id} 已存在，追加资金")
            self._strategies[strategy_id].allocated += amount
        else:
            self._strategies[strategy_id] = StrategyCapital(
                allocated=amount,
                used=0.0,
                profit=0.0,
                available=amount
            )

        self._unallocated -= amount

        logger.info(
            f"为策略 {strategy_id} 分配资金: {amount:.2f} USDT, "
            f"剩余未分配: {self._unallocated:.2f} USDT"
        )

        return True

    def check_buying_power(
        self,
        strategy_id: str,
        amount_usdt: float
    ) -> bool:
        """
        检查策略是否有足够的购买力

        Args:
            strategy_id (str): 策略 ID
            amount_usdt (float): 需要的金额（USDT）

        Returns:
            bool: 是否有足够的购买力
        """
        if strategy_id not in self._strategies:
            logger.error(f"策略 {strategy_id} 未分配资金")
            return False

        capital = self._strategies[strategy_id]

        # 检查可用资金
        has_power = capital.available >= amount_usdt

        if not has_power:
            logger.warning(
                f"策略 {strategy_id} 购买力不足: "
                f"需要 {amount_usdt:.2f} USDT, 可用 {capital.available:.2f} USDT"
            )

        return has_power

    def set_position_manager(self, position_manager: 'PositionManager'):
        """
        设置 PositionManager 引用（用于全局敞口检查）

        Args:
            position_manager (PositionManager): 持仓管理器实例
        """
        self._position_manager = position_manager
        logger.debug("PositionManager 引用已设置")

    def get_total_equity(self) -> float:
        """
        获取账户总权益

        Returns:
            float: 总权益 = 总资金 + 总盈亏
        """
        total_profit = sum(c.profit for c in self._strategies.values())
        return self.total_capital + total_profit

    def calculate_safe_quantity(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        strategy_id: str
    ) -> float:
        """
        基于风险计算安全仓位大小（机构级风控核心）

        计算逻辑：
        1. 计算单笔愿意承担的最大亏损额 (Risk Capital)
           risk_amount = account_equity * RISK_PER_TRADE_PCT

        2. 计算止损价差 (Distance to Stop)
           price_distance = abs(entry_price - stop_loss_price)

        3. 计算基础仓位
           quantity = risk_amount / price_distance

        4. 双重熔断检查：
           a. 名义价值检查：防止真实杠杆超过上限
           b. 回撤检查：策略回撤超过阈值则禁止开仓

        5. 交易所精度控制：
           a. 根据 lot_size 向下取整
           b. 检查 min_order_size 和 min_notional

        Args:
            symbol (str): 交易对
            entry_price (float): 入场价格
            stop_loss_price (float): 止损价格
            strategy_id (str): 策略 ID

        Returns:
            float: 安全仓位数量（如果触发风控则返回 0）
        """
        try:
            # 0. 基本验证
            if entry_price <= 0 or stop_loss_price <= 0:
                logger.error(f"价格参数无效: entry={entry_price}, stop={stop_loss_price}")
                return 0.0

            # 1. 检查1：回撤熔断检查
            if strategy_id in self._strategies:
                capital = self._strategies[strategy_id]
                capital.update_drawdown()

                if capital.max_drawdown_pct > self._risk_config.MAX_DRAWDOWN_LIMIT:
                    logger.warning(
                        f"🛑 策略 {strategy_id} 回撤熔断触发: "
                        f"drawdown={capital.max_drawdown_pct * 100:.2f}% > "
                        f"limit={self._risk_config.MAX_DRAWDOWN_LIMIT * 100:.1f}%, "
                        f"禁止开仓"
                    )
                    return 0.0

            # 2. 计算账户权益
            account_equity = self.get_total_equity()
            logger.debug(f"账户权益: {account_equity:.2f} USDT")

            # 3. 计算最大风险金额（1% Rule）
            max_risk_amount = account_equity * self._risk_config.RISK_PER_TRADE_PCT
            logger.debug(f"最大风险金额: {max_risk_amount:.2f} USDT (1% Rule)")

            # 4. 计算止损价差
            price_distance = abs(entry_price - stop_loss_price)

            # 最小价差保护（防止除以零）
            min_distance = entry_price * self._risk_config.MIN_STOP_DISTANCE_PCT
            if price_distance < min_distance:
                logger.warning(
                    f"止损价差过小: {price_distance:.2f} < {min_distance:.2f}, "
                    f"使用最小价差保护"
                )
                price_distance = min_distance

            logger.debug(
                f"止损价差: {price_distance:.2f} "
                f"({entry_price} -> {stop_loss_price})"
            )

            # 5. 计算基础仓位
            base_quantity = max_risk_amount / price_distance
            logger.debug(f"基础仓位: {base_quantity:.4f}")

            # 6. 检查2：名义价值检查（杠杆限制）
            nominal_value = base_quantity * entry_price
            current_exposure = 0.0

            # 获取当前总持仓价值
            if self._position_manager:
                current_exposure = self._position_manager.get_total_exposure()

            total_exposure = current_exposure + nominal_value
            real_leverage = total_exposure / account_equity if account_equity > 0 else 0

            logger.debug(
                f"杠杆检查: current_exposure={current_exposure:.2f}, "
                f"new_exposure={nominal_value:.2f}, "
                f"total={total_exposure:.2f}, "
                f"leverage={real_leverage:.2f}x"
            )

            # 如果超过杠杆上限，缩减仓位
            if real_leverage > self._risk_config.MAX_GLOBAL_LEVERAGE:
                # 计算允许的最大持仓价值
                max_exposure = account_equity * self._risk_config.MAX_GLOBAL_LEVERAGE
                max_new_exposure = max_exposure - current_exposure

                if max_new_exposure > 0:
                    adjusted_quantity = max_new_exposure / entry_price
                    logger.warning(
                        f"⚠️  杠杆限制触发: 削减仓位 "
                        f"from {base_quantity:.4f} to {adjusted_quantity:.4f} "
                        f"(杠杆从 {real_leverage:.2f}x 降至 "
                        f"{self._risk_config.MAX_GLOBAL_LEVERAGE}x)"
                    )
                    base_quantity = adjusted_quantity
                else:
                    logger.warning(
                        f"🛑 杠杆已达上限: {real_leverage:.2f}x > "
                        f"{self._risk_config.MAX_GLOBAL_LEVERAGE}x, "
                        f"禁止开仓"
                    )
                    return 0.0

            # 警告级别（仅记录日志）
            elif real_leverage > self._risk_config.WARNING_LEVERAGE_THRESHOLD:
                logger.warning(
                    f"⚠️  杠杆接近上限: {real_leverage:.2f}x "
                    f"(警告阈值: {self._risk_config.WARNING_LEVERAGE_THRESHOLD}x)"
                )

            # 7. 检查3：单一币种敞口限制
            symbol_exposure = 0.0
            if self._position_manager:
                symbol_exposure = self._position_manager.get_symbol_exposure(symbol)

            total_symbol_exposure = symbol_exposure + nominal_value
            symbol_exposure_ratio = total_symbol_exposure / account_equity

            if symbol_exposure_ratio > self._risk_config.MAX_SINGLE_SYMBOL_EXPOSURE:
                logger.warning(
                    f"🛑 单一币种敞口超限: {symbol} "
                    f"ratio={symbol_exposure_ratio * 100:.1f}% > "
                    f"limit={self._risk_config.MAX_SINGLE_SYMBOL_EXPOSURE * 100:.1f}%, "
                    f"禁止开仓"
                )
                return 0.0

            # 8. 交易所精度控制
            instrument = self._instruments.get(symbol)
            if instrument:
                # 8a. 根据 lot_size 向下取整
                lot_size = instrument.lot_size
                if lot_size > 0:
                    rounded_quantity = math.floor(base_quantity / lot_size) * lot_size
                    logger.debug(
                        f"精度调整: {base_quantity:.4f} -> {rounded_quantity:.4f} "
                        f"(lot_size={lot_size})"
                    )
                    base_quantity = rounded_quantity
                else:
                    logger.warning(f"交易对 {symbol} lot_size 无效: {lot_size}")

                # 8b. 检查 min_order_size（最小数量）
                if base_quantity < instrument.min_order_size:
                    logger.warning(
                        f"🛑 仓位数量过小: {base_quantity:.4f} < "
                        f"min_order_size={instrument.min_order_size:.4f}, "
                        f"Skipped: Size too small"
                    )
                    return 0.0

                # 8c. 检查 min_notional（最小金额）
                final_notional = base_quantity * entry_price
                if final_notional < instrument.min_notional:
                    logger.warning(
                        f"🛑 订单金额过小: {final_notional:.2f} USDT < "
                        f"min_notional={instrument.min_notional:.2f} USDT, "
                        f"Skipped: Size too small"
                    )
                    return 0.0
            else:
                logger.warning(f"未找到交易对 {symbol} 的精度配置，跳过精度控制")

            logger.info(
                f"✅ 安全仓位计算完成: {symbol} quantity={base_quantity:.4f}, "
                f"nominal_value={base_quantity * entry_price:.2f} USDT, "
                f"leverage={real_leverage:.2f}x"
            )

            return base_quantity

        except ZeroDivisionError as e:
            logger.error(f"仓位计算除零错误: {e}")
            return 0.0
        except Exception as e:
            logger.error(f"仓位计算异常: {e}", exc_info=True)
            return 0.0

    def reserve_capital(
        self,
        strategy_id: str,
        amount_usdt: float
    ) -> bool:
        """
        预留资金（下单前调用）

        Args:
            strategy_id (str): 策略 ID
            amount_usdt (float): 预留金额（USDT）

        Returns:
            bool: 预留是否成功
        """
        if not self.check_buying_power(strategy_id, amount_usdt):
            return False

        capital = self._strategies[strategy_id]
        capital.used += amount_usdt
        capital.available = capital.allocated - capital.used + capital.profit

        logger.info(
            f"策略 {strategy_id} 预留资金: {amount_usdt:.2f} USDT, "
            f"剩余可用: {capital.available:.2f} USDT"
        )

        return True

    def release_capital(
        self,
        strategy_id: str,
        amount_usdt: float
    ):
        """
        释放资金（订单取消或失败后调用）

        Args:
            strategy_id (str): 策略 ID
            amount_usdt (float): 释放金额（USDT）
        """
        if strategy_id not in self._strategies:
            logger.error(f"策略 {strategy_id} 未分配资金")
            return

        capital = self._strategies[strategy_id]
        capital.used -= amount_usdt
        capital.available = capital.allocated - capital.used + capital.profit

        logger.info(
            f"策略 {strategy_id} 释放资金: {amount_usdt:.2f} USDT, "
            f"剩余可用: {capital.available:.2f} USDT"
        )

    def record_profit(
        self,
        strategy_id: str,
        profit_usdt: float
    ):
        """
        记录策略盈亏

        Args:
            strategy_id (str): 策略 ID
            profit_usdt (float): 盈亏金额（正为盈，负为亏）
        """
        if strategy_id not in self._strategies:
            logger.error(f"策略 {strategy_id} 未分配资金")
            return

        capital = self._strategies[strategy_id]
        capital.profit += profit_usdt
        capital.available = capital.allocated - capital.used + capital.profit

        logger.info(
            f"策略 {strategy_id} 记录盈亏: {profit_usdt:+.2f} USDT, "
            f"累计盈亏: {capital.profit:+.2f} USDT, "
            f"可用资金: {capital.available:.2f} USDT"
        )

    def get_strategy_capital(
        self,
        strategy_id: str
    ) -> Optional[StrategyCapital]:
        """
        获取策略资金信息

        Args:
            strategy_id (str): 策略 ID

        Returns:
            StrategyCapital: 资金信息，如果策略不存在返回 None
        """
        return self._strategies.get(strategy_id)

    def get_all_capitals(self) -> Dict[str, StrategyCapital]:
        """
        获取所有策略的资金信息

        Returns:
            dict: {strategy_id: StrategyCapital}
        """
        return self._strategies.copy()

    def get_summary(self) -> dict:
        """
        获取资金汇总信息

        Returns:
            dict: 汇总信息
        """
        total_allocated = sum(c.allocated for c in self._strategies.values())
        total_used = sum(c.used for c in self._strategies.values())
        total_profit = sum(c.profit for c in self._strategies.values())
        total_available = sum(c.available for c in self._strategies.values())

        return {
            'total_capital': self.total_capital,
            'unallocated': self._unallocated,
            'total_allocated': total_allocated,
            'total_used': total_used,
            'total_profit': total_profit,
            'total_available': total_available,
            'strategy_count': len(self._strategies)
        }

    def on_order_filled(self, event: Event):
        """
        监听订单成交事件，自动更新资金

        Args:
            event (Event): ORDER_FILLED 事件
        """
        try:
            data = event.data
            strategy_id = data.get('strategy_id', 'default')

            # 计算成交金额
            price = data.get('price', 0)
            filled_size = data.get('filled_size', 0)
            side = data.get('side')

            if price <= 0 or filled_size <= 0:
                return

            amount_usdt = price * filled_size

            # 买入：释放预留资金
            if side == 'buy':
                self.release_capital(strategy_id, amount_usdt)

            # 卖出：记录盈亏（简化处理）
            elif side == 'sell':
                # 实际盈亏需要根据开仓价计算，这里简化处理
                # 可以在 PositionManager 中计算，然后调用 record_profit
                pass

            # 更新回撤指标
            if strategy_id in self._strategies:
                self._strategies[strategy_id].update_drawdown()

        except Exception as e:
            logger.error(f"处理订单成交事件失败: {e}")

    def reset(self):
        """重置所有资金状态"""
        self._strategies.clear()
        self._unallocated = self.total_capital
        logger.info("资金指挥官已重置")

    def get_all_instruments(self) -> Dict[str, ExchangeInstrument]:
        """
        获取所有注册的交易对

        Returns:
            dict: {symbol: ExchangeInstrument}
        """
        return self._instruments.copy()

    def register_risk_profile(self, profile: RiskProfile):
        """
        注册策略风控配置

        Args:
            profile (RiskProfile): 风控配置
        """
        self._strategy_profiles[profile.strategy_id] = profile
        logger.info(
            f"注册风控配置: {profile.strategy_id}, "
            f"max_leverage={profile.max_leverage}x, "
            f"stop_loss_type={profile.stop_loss_type.value}"
        )

    def get_strategy_profile(self, strategy_id: str) -> RiskProfile:
        """
        获取策略风控配置

        Args:
            strategy_id (str): 策略 ID

        Returns:
            RiskProfile: 风控配置，如果未注册返回默认保守配置
        """
        profile = self._strategy_profiles.get(strategy_id)

        if profile is None:
            logger.warning(
                f"未找到策略 {strategy_id} 的风控配置，使用默认保守配置"
            )
            return DEFAULT_CONSERVATIVE_PROFILE

        return profile

    def check_policy_compliance(
        self,
        strategy_id: str,
        amount_usdt: float,
        entry_price: float
    ) -> tuple[bool, str]:
        """
        检查策略风控合规性

        检查维度：
        1. 策略最大杠杆限制
        2. 单笔订单金额限制

        Args:
            strategy_id (str): 策略 ID
            amount_usdt (float): 订单金额（USDT）
            entry_price (float): 入场价格

        Returns:
            tuple: (是否合规, 原因说明)
        """
        # 获取策略风控配置，如果不存在则使用默认保守配置
        profile = self._strategy_profiles.get(strategy_id, DEFAULT_CONSERVATIVE_PROFILE)

        # 1. 检查单笔订单金额限制
        if amount_usdt > profile.max_order_size_usdt:
            return False, (
                f"单笔订单金额超限: {amount_usdt:.2f} USDT > "
                f"{profile.max_order_size_usdt:.2f} USDT"
            )

        # 2. 检查策略最大杠杆
        if strategy_id in self._strategies:
            current_exposure = 0.0
            if self._position_manager:
                current_exposure = self._position_manager.get_strategy_exposure(strategy_id)

            allocated_capital = self._strategies[strategy_id].allocated
            new_exposure = current_exposure + amount_usdt
            new_leverage = new_exposure / allocated_capital if allocated_capital > 0 else 0

            if new_leverage > profile.max_leverage:
                return False, (
                    f"策略杠杆超限: {new_leverage:.2f}x > "
                    f"{profile.max_leverage}x (策略限制)"
                )

        return True, "OK"

    def is_strategy_circuit_breaker_triggered(self, strategy_id: str) -> bool:
        """
        检查策略是否触发回撤熔断

        Args:
            strategy_id (str): 策略 ID

        Returns:
            bool: 是否触发熔断
        """
        if strategy_id not in self._strategies:
            return False

        capital = self._strategies[strategy_id]
        capital.update_drawdown()

        return capital.max_drawdown_pct > self._risk_config.MAX_DRAWDOWN_LIMIT
