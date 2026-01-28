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
- 实现 1% Rule：每笔交易风险不超过总资金的 1%

🔥 [修复2] 高精度计算：
- 使用 decimal 模块避免浮点数误差
- 模拟盘优化：降低精度要求以提升回测速度
"""

import logging
import math
from typing import Dict, Optional, TYPE_CHECKING
from dataclasses import dataclass
from decimal import Decimal, getcontext, ROUND_DOWN

from ..core.event_types import Event, EventType
from ..config.risk_config import RiskConfig, DEFAULT_RISK_CONFIG
from ..config.risk_profile import RiskProfile, DEFAULT_CONSERVATIVE_PROFILE

if TYPE_CHECKING:
    from ..oms.position_manager import PositionManager

logger = logging.getLogger(__name__)

# 🔥 [新增] Decimal 精度配置
# 设置高精度计算
getcontext().prec = 28  # 28位精度（足够处理金融计算）
getcontext().rounding = ROUND_DOWN  # 向下取整（保守计算）


@dataclass
class ExchangeInstrument:
    """交易所交易对配置"""
    symbol: str
    lot_size: float        # 数量精度（例如 0.01）
    min_order_size: float # 最小下单数量
    min_notional: float   # 最小下单金额（USDT）
    ct_val: float = 1.0   # 🔥 [修复] 合约面值（1 contract = ctVal coins）
    tick_size: float = 0.0001   # 🔥 [Fix 41] 最小价格变动单位


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

        # 🔥 [新增] 模拟盘标志
        self._is_paper_trading = False  # 是否为模拟盘（优化精度要求）

        # 交易所交易对配置（精度控制）
        self._instruments: Dict[str, ExchangeInstrument] = {}

        # 策略风控配置文件 {strategy_id: RiskProfile}
        self._strategy_profiles: Dict[str, RiskProfile] = {}

        logger.info(
            f"CapitalCommander 初始化: total_capital={total_capital:.2f} USDT, "
            f"risk_per_trade={self._risk_config.RISK_PER_TRADE_PCT * 100:.1f}%, "
            f"precision={getcontext().prec}位 (Decimal高精度)"
        )

    def set_paper_trading(self, is_paper: bool):
        """🔥 [新增] 设置模拟盘模式"""
        self._is_paper_trading = is_paper
        logger.info(f"模拟盘模式设置: {is_paper}")
        if is_paper:
            # 模拟盘降低精度要求，提升回测速度
            getcontext().prec = 16  # 16位精度足够
            getcontext().rounding = ROUND_DOWN
        else:
            # 实盘使用高精度
            getcontext().prec = 28  # 28位精度
            getcontext().rounding = ROUND_DOWN

    def register_instrument(
        self,
        symbol: str,
        lot_size: float,
        min_order_size: float,
        min_notional: float,
        ct_val: float = 1.0,  # 🔥 [修复] 添加合约面值参数
        tick_size: float = 0.0001  # 🔥 [Fix 41] 添加 tick_size 参数
    ):
        """
        注册交易所交易对配置

        Args:
            symbol (str): 交易对
            lot_size (float): 数量精度
            min_order_size (float): 最小下单数量
            min_notional (float): 最小下单金额（USDT）
            ct_val (float): 合约面值（1 contract = ctVal coins）  # 🔥 [修复]
            tick_size (float): 最小价格变动单位  # 🔥 [Fix 41]
        """
        self._instruments[symbol] = ExchangeInstrument(
            symbol=symbol,
            lot_size=lot_size,
            min_order_size=min_order_size,
            min_notional=min_notional,
            ct_val=ct_val,  # 🔥 [修复] 保存合约面值
            tick_size=tick_size  # 🔥 [Fix 41] 保存 tick_size
        )
        logger.info(
            f"注册交易对配置: {symbol} lot_size={lot_size}, "
            f"min_order_size={min_order_size}, "
            f"min_notional={min_notional:.2f} USDT, "
            f"ctVal={ct_val}, "  # 🔥 [修复] 显示合约面值
            f"tickSize={tick_size}"  # 🔥 [Fix 41] 显示 tick_size
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

    def _get_effective_leverage(self, strategy_id: str) -> float:
        """
        内部辅助方法：获取策略的有效计算杠杆
        逻辑：min(策略最大杠杆, 全局最大杠杆)，且不小于 1.0
        """
        profile = self.get_strategy_profile(strategy_id)
        leverage = 1.0
        if profile:
            leverage = min(profile.max_leverage, self._risk_config.MAX_GLOBAL_LEVERAGE)

        # 确保杠杆至少为 1.0
        return max(1.0, leverage)

    def check_buying_power(
        self,
        strategy_id: str,
        amount_usdt: float,
        symbol: str = None,
        side: str = None
    ) -> bool:
        """
        检查策略是否有足够的购买力
        [FIX]: 支持合约杠杆逻辑，检查保证金(Margin)而非全额(Nominal)
        [FIX]: 判断平仓场景，跳过保证金检查（修复平仓死锁）

        Args:
            strategy_id (str): 策略 ID
            amount_usdt (float): 订单金额（USDT）
            symbol (str): 交易对（可选，用于判断平仓）
            side (str): 订单方向 buy/sell（可选，用于判断平仓）

        Returns:
            bool: 是否有足够的购买力
        """
        if strategy_id not in self._strategies:
            logger.error(f"策略 {strategy_id} 未分配资金")
            return False

        cap = self._strategies[strategy_id]

        # 🔥 核心修复：判断是否为平仓操作（Reduce Only）
        # 平仓操作应该释放保证金，不需要检查可用资金
        if symbol and side and self._position_manager:
            try:
                # 获取当前持仓（从 PositionManager）
                position = self._position_manager.get_position(symbol)

                if position and position.size != 0:
                    # 判断订单方向是否与持仓方向相反
                    is_reducing_position = False

                    if position.size > 0 and side == 'sell':
                        # 多头平仓：持仓为正，订单为卖出
                        is_reducing_position = True
                        logger.debug(
                            f"🔍 [平仓检测] {symbol} Long → Sell, "
                            f"跳过保证金检查"
                        )
                    elif position.size < 0 and side == 'buy':
                        # 空头平仓：持仓为负，订单为买入
                        is_reducing_position = True
                        logger.debug(
                            f"🔍 [平仓检测] {symbol} Short → Buy, "
                            f"跳过保证金检查"
                        )

                    # 如果是减少持仓的操作，直接通过
                    if is_reducing_position:
                        logger.info(
                            f"✅ 购买力检查通过 [{strategy_id}]: "
                            f"平仓操作 (symbol={symbol}, side={side}), "
                            f"跳过保证金检查"
                        )
                        return True
            except Exception as e:
                # 获取持仓失败时，继续使用原有逻辑
                logger.warning(f"获取持仓信息失败: {e}，使用默认检查")

        # 1. 计算有效杠杆
        leverage = self._get_effective_leverage(strategy_id)

        # 2. 计算所需保证金 (Margin Requirement)
        # 例如: 下单 30,000U, 杠杆 3x -> 仅需 10,000U 保证金
        required_margin = amount_usdt / leverage

        # 3. 检查可用资金 (保留 1% 缓冲以应对滑点或费率波动)
        has_funds = cap.available >= (required_margin * 0.99)

        if not has_funds:
            logger.warning(
                f"🚫 购买力不足 [{strategy_id}]: "
                f"下单名义价值=${amount_usdt:.0f}, "
                f"杠杆={leverage}x, "
                f"需保证金=${required_margin:.0f}, "
                f"可用=${cap.available:.0f}"
            )
        else:
            logger.debug(
                f"✅ 购买力检查通过 [{strategy_id}]: "
                f"需保证金=${required_margin:.2f} (可用=${cap.available:.2f}, 杠杆={leverage}x)"
            )

        return has_funds

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
        strategy_id: str,
        contract_val: float = None,  # 🔥 [修复] 改为 None，默认值从 instrument_info 获取
        # 🔥 [新增] 模拟盘模式标志
        is_paper_trading: bool = False
    ) -> float:
        """
        基于风险计算安全仓位大小（机构级风控核心）

        🔥 [修复] 计算精度对齐：
        - 使用 decimal 模块进行高精度计算
        - 防止浮点数累积误差
        - 模拟盘优化：降低精度要求以提升回测速度

        计算逻辑：
        1. 计算单笔愿意承担的最大亏损额 (Risk Capital)
           risk_amount = account_equity * RISK_PER_TRADE_PCT

        2. 计算止损价差 (Distance to Stop)
           price_distance = abs(entry_price - stop_loss_price)

        3. 计算基础仓位（高精度）
           [FIX] quantity = risk_amount / (price_distance * contract_val)
           考虑合约面值，确保计算正确

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
            contract_val (float): 合约面值 (1 contract = ctVal coins)  # 🔥 [修复]
            is_paper_trading (bool): 🔥 [新增] 是否为模拟盘（优化精度）

        Returns:
            float: 安全仓位数量（如果触发风控则返回 0）
        """
        try:
            # 🔥 [新增] 模拟盘优化：切换精度上下文
            old_prec = getcontext().prec
            old_rounding = getcontext().rounding

            if is_paper_trading or self._is_paper_trading:
                # 模拟盘：降低精度要求，提升速度
                getcontext().prec = 16
                getcontext().rounding = ROUND_DOWN
                logger.debug(f"🧪 [模拟盘模式] 切换到 16 位精度")
            else:
                # 实盘：使用高精度
                getcontext().prec = 28
                getcontext().rounding = ROUND_DOWN
                logger.debug(f"📊 [实盘模式] 切换到 28 位精度")

            # 0. 🔥 [修复] 确定合约面值
            # 优先使用传入的值，否则从 instrument_info 获取
            if contract_val is None or contract_val <= 0:
                instrument = self._instruments.get(symbol)
                if instrument and hasattr(instrument, 'ct_val'):
                    contract_val = float(instrument.ct_val)
                    logger.info(
                        f"💰 [合约面值] {symbol}: "
                        f"从 instrument_info 获取 ctVal={contract_val}"
                    )
                else:
                    contract_val = 1.0
                    logger.warning(
                        f"⚠️  [合约面值] {symbol}: "
                        f"未找到 ctVal，使用默认值 1.0（可能导致仓位计算错误！）"
                    )
            else:
                # 🔥 [修复] 验证传入的 contract_val
                instrument = self._instruments.get(symbol)
                if instrument and hasattr(instrument, 'ct_val'):
                    if abs(contract_val - float(instrument.ct_val)) > 0.001:
                        logger.warning(
                            f"⚠️  [合约面值不一致] {symbol}: "
                            f"传入 ctVal={contract_val}, "
                            f"instrument_info ctVal={instrument.ct_val}, "
                            f"使用传入值"
                        )

            # 🔥 [新增] 使用 Decimal 进行高精度计算
            try:
                entry_price_dec = Decimal(str(entry_price))
                stop_loss_price_dec = Decimal(str(stop_loss_price))
                contract_val_dec = Decimal(str(contract_val))
                risk_per_trade_pct_dec = Decimal(str(self._risk_config.RISK_PER_TRADE_PCT))
                min_stop_distance_pct_dec = Decimal(str(self._risk_config.MIN_STOP_DISTANCE_PCT))
                max_leverage_dec = Decimal(str(self._risk_config.MAX_GLOBAL_LEVERAGE))
            except Exception as e:
                logger.error(f"🔥 [精度转换失败] {e}，回退到浮点计算")
                entry_price_dec = Decimal(str(entry_price))
                stop_loss_price_dec = Decimal(str(stop_loss_price))
                contract_val_dec = Decimal(str(contract_val))
                risk_per_trade_pct_dec = Decimal(str(self._risk_config.RISK_PER_TRADE_PCT))
                min_stop_distance_pct_dec = Decimal(str(self._risk_config.MIN_STOP_DISTANCE_PCT))
                max_leverage_dec = Decimal(str(self._risk_config.MAX_GLOBAL_LEVERAGE))

            # 🔥 [新增] 打印最终使用的合约面值
            logger.info(
                f"💰 [仓位计算] {symbol}: "
                f"使用 ctVal={contract_val}, "
                f"entry_price={entry_price:.6f}, "
                f"精度={getcontext().prec}位"
            )

            # 0.5 基本验证
            if entry_price <= 0 or stop_loss_price <= 0:
                logger.error(f"价格参数无效: entry={entry_price}, stop={stop_loss_price}")
                return 0.0

            # 1. 检查 1：回撤熔断检查
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
            account_equity_dec = Decimal(str(self.get_total_equity()))
            logger.debug(f"账户权益: {account_equity_dec:.2f} USDT")

            # 3. 🔥 [新增] 使用 Decimal 计算最大风险金额（1% Rule）
            max_risk_amount_dec = account_equity_dec * risk_per_trade_pct_dec
            logger.debug(f"最大风险金额: {max_risk_amount_dec:.2f} USDT (1% Rule)")

            # 4. 🔥 [新增] 使用 Decimal 计算止损价差
            price_distance_dec = abs(entry_price_dec - stop_loss_price_dec)

            # 最小价差保护（防止除以零）
            min_distance_dec = entry_price_dec * min_stop_distance_pct_dec
            if price_distance_dec < min_distance_dec:
                logger.warning(
                    f"止损价差过小: {price_distance_dec:.2f} < {min_distance_dec:.2f}, "
                    f"使用最小价差保护"
                )
                price_distance_dec = min_distance_dec

            logger.debug(
                f"止损价差: {price_distance_dec:.2f} "
                f"({entry_price:.6f} -> {stop_loss_price:.6f})"
            )

            # 5. 🔥 [新增] 使用 Decimal 计算基础仓位
            # [FIX] quantity = risk_amount / (price_distance * contract_val) / leverage
            # 🔥 [严重修复] 必须除以杠杆，否则仓位计算错误
            leverage_dec = self._get_effective_leverage(strategy_id)
            # 🔥 [修复] 将 float 转换为 Decimal，避免类型错误
            leverage_dec = Decimal(str(leverage_dec))
            base_quantity_dec = max_risk_amount_dec / (price_distance_dec * contract_val_dec * leverage_dec)
            base_quantity = float(base_quantity_dec)

            logger.debug(
                f"💰 [基础仓位] {symbol}: "
                f"quantity={base_quantity:.4f}, "
                f"risk={max_risk_amount_dec:.2f} USDT, "
                f"price_distance={price_distance_dec:.6f}, "
                f"ctVal={contract_val}, "
                f"leverage={float(leverage_dec):.2f}x"  # 🔥 [新增] 显示杠杆
            )

            # 6. 检查 2：名义价值检查（杠杆限制）
            # 🔥 [严重修复] 必须乘以 contract_val，否则名义价值计算错误
            nominal_value_dec = base_quantity_dec * entry_price_dec * contract_val_dec
            nominal_value = float(nominal_value_dec)

            current_exposure = 0.0
            if self._position_manager:
                current_exposure = self._position_manager.get_total_exposure()

            total_exposure_dec = Decimal(str(current_exposure)) + nominal_value_dec
            total_exposure = float(total_exposure_dec)

            # 🔥 [新增] 使用 Decimal 计算真实杠杆
            real_leverage_dec = total_exposure_dec / account_equity_dec
            real_leverage = float(real_leverage_dec)

            logger.debug(
                f"杠杆检查: current_exposure={current_exposure:.2f}, "
                f"new_exposure={nominal_value:.2f}, "
                f"total={total_exposure:.2f}, "
                f"leverage={real_leverage:.2f}x, "
                f"contract_val={contract_val}"
            )

            # 如果超过杠杆上限，缩减仓位
            if real_leverage > float(max_leverage_dec):
                # 🔥 [新增] 使用 Decimal 计算允许的最大持仓价值
                max_exposure_dec = account_equity_dec * max_leverage_dec
                max_new_exposure_dec = max_exposure_dec - Decimal(str(current_exposure))
                max_new_exposure = float(max_new_exposure_dec)

                if max_new_exposure > 0:
                    # 🔥 [严重修复] 必须除以 contract_val，否则 quantity 计算错误
                    # 🔥 [新增] 使用 Decimal 计算
                    adjusted_quantity_dec = max_new_exposure_dec / (entry_price_dec * contract_val_dec)
                    adjusted_quantity = float(adjusted_quantity_dec)
                    logger.warning(
                        f"⚠️  杠杆限制触发: 缩减仓位 "
                        f"from {base_quantity:.4f} to {adjusted_quantity:.4f} "
                        f"(杠杆从 {real_leverage:.2f}x 降至 "
                        f"{float(max_leverage_dec):.2f}x)"
                    )
                    base_quantity = adjusted_quantity

                    # 🔥 [严重修复] 重新计算削减后的 nominal_value
                    # 必须使用削减后的 base_quantity，否则敞口检查会误报
                    nominal_value_dec = Decimal(str(base_quantity)) * entry_price_dec * contract_val_dec
                    nominal_value = float(nominal_value_dec)
                else:
                    logger.warning(
                        f"🛑 杠杆已达上限: {real_leverage:.2f}x > "
                        f"{float(max_leverage_dec):.2f}x, "
                        f"禁止开仓"
                    )
                    return 0.0

            # 警告级别（仅记录日志）
            warning_leverage_dec = Decimal(str(self._risk_config.WARNING_LEVERAGE_THRESHOLD))
            if real_leverage > float(warning_leverage_dec):
                logger.warning(
                    f"⚠️  杠杆接近上限: {real_leverage:.2f}x "
                    f"(警告阈值: {float(warning_leverage_dec):.2f}x)"
                )

            # 7. 检查 3：单一币种敞口限制
            # 🔥 [严重修复] 使用削减后的 nominal_value 进行检查
            symbol_exposure = 0.0
            if self._position_manager:
                symbol_exposure = self._position_manager.get_symbol_exposure(symbol)

            total_symbol_exposure = symbol_exposure + nominal_value
            # 🔥 [修复] 将 total_symbol_exposure 转换为 Decimal，避免类型不匹配
            total_symbol_exposure_dec = Decimal(str(total_symbol_exposure))
            symbol_exposure_ratio = float(total_symbol_exposure_dec / account_equity_dec) if account_equity_dec > 0 else 0

            # ✨ 调试日志：打印当前使用的 limit 值
            logger.debug(
                f"🛡️ [敞口检查] {symbol}: "
                f"当前敞口={symbol_exposure_ratio * 100:.1f}%, "
                f"限制={self._risk_config.MAX_SINGLE_SYMBOL_EXPOSURE * 100:.1f}%"
            )

            max_single_exposure_dec = Decimal(str(self._risk_config.MAX_SINGLE_SYMBOL_EXPOSURE))
            if symbol_exposure_ratio > float(max_single_exposure_dec):
                logger.warning(
                    f"🛑 单一币种敞口超限: {symbol} "
                    f"ratio={symbol_exposure_ratio * 100:.1f}% > "
                    f"limit={float(max_single_exposure_dec) * 100:.1f}%, "
                    f"禁止开仓"
                )
                return 0.0

            # 8. 交易所精度控制
            instrument = self._instruments.get(symbol)
            if instrument:
                # 8a. 根据 lot_size 向下取整
                lot_size = instrument.lot_size
                if lot_size > 0:
                    # 🔥 [新增] 使用 Decimal 向下取整
                    lot_size_dec = Decimal(str(lot_size))
                    base_quantity_dec = Decimal(str(base_quantity))
                    rounded_quantity_dec = (base_quantity_dec / lot_size_dec).to_integral_value(rounding=ROUND_DOWN) * lot_size_dec
                    rounded_quantity = float(rounded_quantity_dec)
                    logger.debug(
                        f"精度调整: {base_quantity:.4f} -> {rounded_quantity:.4f} "
                        f"(lot_size={lot_size}, rounding=ROUND_DOWN)"
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
                # 🔥 [严重修复] 必须乘以 contract_val，否则 notional 计算错误
                # 🔥 [新增] 使用 Decimal 计算
                contract_val_dec = Decimal(str(contract_val))
                entry_price_dec = Decimal(str(entry_price))
                base_quantity_dec = Decimal(str(base_quantity))
                final_notional_dec = base_quantity_dec * entry_price_dec * contract_val_dec
                final_notional = float(final_notional_dec)

                if final_notional < instrument.min_notional:
                    logger.warning(
                        f"🛑 订单金额过小: {final_notional:.2f} USDT < "
                        f"min_notional={instrument.min_notional:.2f} USDT, "
                        f"Skipped: Size too small"
                    )
                    return 0.0
            else:
                logger.warning(f"未找到交易对 {symbol} 的精度配置，跳过精度控制")

            # 🔥 [严重修复] 打印校准日志
            # 🔥 [新增] 使用 Decimal 计算真实价值
            base_quantity_dec = Decimal(str(base_quantity))
            entry_price_dec = Decimal(str(entry_price))
            contract_val_dec = Decimal(str(contract_val))
            real_value_dec = base_quantity_dec * entry_price_dec * contract_val_dec
            real_value = float(real_value_dec)

            logger.info(
                f"💰 [仓位校准] {symbol}: "
                f"计算quantity={base_quantity:.2f} 张, "
                f"实际价值={real_value:.2f} USDT, "
                f"ctVal={contract_val}, "
                f"杠杆={real_leverage:.2f}x, "
                f"精度={getcontext().prec}位"
            )

            logger.info(
                f"✅ 安全仓位计算完成: {symbol} quantity={base_quantity:.4f}, "
                f"nominal_value={real_value:.2f} USDT, "
                f"leverage={real_leverage:.2f}x, "
                f"contract_val={contract_val}"  # 🔥 [修复] 显示使用的合约面值
            )

            # 🔥 [新增] 恢复原始精度上下文
            getcontext().prec = old_prec
            getcontext().rounding = old_rounding

            return base_quantity

        except ZeroDivisionError as e:
            logger.error(f"🚨 [除零错误] 仓位计算: {e}")
            return 0.0
        except Exception as e:
            logger.error(f"❌ [仓位计算异常] {e}", exc_info=True)
            return 0.0

    def reserve_capital(
        self,
        strategy_id: str,
        amount_usdt: float
    ) -> bool:
        """
        预留资金（下单前）
        [FIX]: 预留保证金，而非全额名义价值
        """
        # 复用检查逻辑
        if not self.check_buying_power(strategy_id, amount_usdt):
            return False

        # 计算并扣除保证金
        leverage = self._get_effective_leverage(strategy_id)
        margin_to_reserve = amount_usdt / leverage

        self._strategies[strategy_id].used += margin_to_reserve

        logger.info(
            f"🔒 预留资金 [{strategy_id}]: "
            f"锁定保证金 ${margin_to_reserve:.2f} "
            f"(名义价值 ${amount_usdt:.2f}, 杠杆 {leverage}x)"
        )
        return True

    def release_capital(
        self,
        strategy_id: str,
        amount_usdt: float
    ):
        """
        释放资金（撤单或拒绝后）
        [FIX]: 释放保证金，而非全额名义价值
        """
        if strategy_id not in self._strategies:
            return

        # 计算并释放保证金
        leverage = self._get_effective_leverage(strategy_id)
        margin_to_release = amount_usdt / leverage

        # 确保 used 不为负数
        self._strategies[strategy_id].used = max(
            0.0,
            self._strategies[strategy_id].used - margin_to_release
        )

        logger.info(
            f"🔓 释放资金 [{strategy_id}]: "
            f"释放保证金 ${margin_to_release:.2f} "
            f"(名义价值 ${amount_usdt:.2f})"
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
