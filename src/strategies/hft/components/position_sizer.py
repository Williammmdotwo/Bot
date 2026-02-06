"""
PositionSizer - 自适应仓位大小计算器

HFT策略的核心组件，负责动态调整单笔下单金额。

核心职责：
1. 信号强度自适应（5x/10x买卖不平衡）
2. 流动性/滑点保护（盘口深度限制）
3. 波动率保护（市场剧烈波动时减仓）

设计原则：
- 轻量化：O(1)时间复杂度，使用deque
- 无状态：不维护持久化数据
- 可配置：所有参数可通过环境变量调整
"""

import logging
import collections
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PositionSizingConfig:
    """仓位管理配置"""
    # 基础资金配置
    base_equity_ratio: float = 0.02      # 基础仓位：总资金的2%
    max_leverage: float = 5.0             # 最大杠杆倍数限制
    min_order_value: float = 10.0           # 最小下单金额 (USDT)

    # 信号强度自适应配置
    signal_scaling_enabled: bool = True
    signal_threshold_normal: float = 5.0      # 5x不平衡 -> 1.0倍
    signal_threshold_aggressive: float = 10.0 # 10x不平衡 -> 1.5倍
    signal_aggressive_multiplier: float = 1.5

    # 流动性/滑点保护配置
    liquidity_protection_enabled: bool = True
    liquidity_depth_ratio: float = 0.20          # 单笔金额不超过盘口前N档的20%
    liquidity_depth_levels: int = 3            # 监控前3档深度

    # 波动率保护配置
    volatility_protection_enabled: bool = True
    volatility_ema_period: int = 20             # 波动率EMA周期
    volatility_threshold: float = 0.001        # 波动率阈值(0.1%)


class PositionSizer:
    """
    自适应仓位大小计算器

    核心职责：
    1. 信号强度自适应（5x/10x不平衡）- 简化凯利公式
    2. 流动性保护（盘口深度限制）- 防止滑点
    3. 波动率保护（市场剧烈波动时减仓）- 防止损误触
    """

    def __init__(self, config: PositionSizingConfig, ct_val: float = 1.0):
        """
        初始化仓位计算器

        Args:
            config (PositionSizingConfig): 仓位管理配置
            ct_val (float): 合约面值（1张=ct_val个币）
        """
        self.cfg = config
        self.ct_val = ct_val  # 🔥 [新增] 保存合约面值

        # 波动率历史（用于标准差计算）
        self._price_history = collections.deque(maxlen=config.volatility_ema_period)
        self._volatility_value = 0.0

        logger.info(
            f"📊 [PositionSizer] 初始化: "
            f"base_ratio={config.base_equity_ratio*100:.1f}%, "
            f"signal_normal={config.signal_threshold_normal}x, "
            f"signal_agg={config.signal_threshold_aggressive}x, "
            f"liq_ratio={config.liquidity_depth_ratio*100:.0f}%, "
            f"volatility={config.volatility_threshold*100:.3f}%, "
            f"ctVal={ct_val}"  # 🔥 [新增] 显示合约面值
        )

    def calculate_order_size(
        self,
        account_equity: float,
        order_book: Dict[str, Any],
        signal_ratio: float,
        current_price: float,
        side: str = 'buy',  # 交易方向 'buy' 或 'sell'
        ct_val: float = None,  # 合约面值
        ema_boost: float = 1.0  # ✅ 新增：EMA 加权系数
    ) -> float:
        """
        自适应计算单笔下单金额 (USDT)

        Args:
            account_equity: 账户权益 (USDT)
            order_book: 订单簿快照 {'bids': [...], 'asks': [...]}
            signal_ratio: 当前买卖量不平衡比率 (例如 5.2, 8.5)
            current_price: 当前价格
            side: 交易方向 'buy' 或 'sell'（决定使用哪方深度）
            ct_val: 合约面值（1张=ct_val个币），如果为 None 则使用 self.ct_val
            ema_boost: EMA 顺势加权系数（默认 1.0）

        Returns:
            float: 下单金额 (USDT)
        """
        # 🔥 [修复] 如果未传入 ct_val，使用初始化时的值
        if ct_val is None:
            ct_val = self.ct_val
        else:
            # 确保 ct_val 是 float 类型
            ct_val = float(ct_val)

        # --- 1. 基础资金限制 ---
        base_amount = account_equity * self.cfg.base_equity_ratio

        logger.debug(
            f"💰 [基础仓位] 账户权益={account_equity:.2f} USDT, "
            f"基础金额={base_amount:.2f} USDT ({self.cfg.base_equity_ratio*100:.1f}%)"
        )

        # --- 2. 信号强度自适应 ---
        multiplier = 1.0
        if self.cfg.signal_scaling_enabled:
            if signal_ratio >= self.cfg.signal_threshold_aggressive:
                multiplier = self.cfg.signal_aggressive_multiplier
                logger.info(
                    f"🎯 [信号强度] 极度不平衡 {signal_ratio:.1f}x "
                    f">= {self.cfg.signal_threshold_aggressive}x, "
                    f"仓位放大 {multiplier:.1f}倍"
                )
            elif signal_ratio < self.cfg.signal_threshold_normal:
                multiplier = 0.0
                logger.warning(
                    f"🛑 [信号强度] 不足 {signal_ratio:.1f}x < "
                    f"{self.cfg.signal_threshold_normal}x, 跳过交易"
                )
                return 0.0
            else:
                logger.debug(
                    f"✅ [信号强度] 正常不平衡 {signal_ratio:.1f}x, "
                    f"使用基础仓位"
                )

        signal_adjusted_amount = base_amount * multiplier

        # ✅ 新增：EMA 加权（顺势时增加仓位）
        if ema_boost > 1.0:
            logger.info(
                f"📈 [EMA加权] 顺势交易，仓位加权 {ema_boost:.2f}x"
            )

        ema_adjusted_amount = signal_adjusted_amount * ema_boost

        # --- 3. 波动率保护（标准差计算）---
        volatility_factor = 1.0
        if self.cfg.volatility_protection_enabled:
            self._update_volatility(current_price)

            # 如果波动率超过阈值，减小仓位
            if self._volatility_value > self.cfg.volatility_threshold:
                # 波动率越大，仓位缩减越多
                # 例如：波动率0.2% > 0.1%阈值，超限0.1%，缩减10%
                volatility_factor = 1.0 - (
                    (self._volatility_value - self.cfg.volatility_threshold) * 10
                )
                volatility_factor = max(0.5, volatility_factor)  # 最小保留50%

                logger.warning(
                    f"📉 [波动率保护] 当前波动率={self._volatility_value:.4%}, "
                    f"阈值={self.cfg.volatility_threshold:.4%}, "
                    f"仓位缩减为{volatility_factor:.1%}"
                )
            else:
                logger.debug(
                    f"✅ [波动率正常] 当前={self._volatility_value:.4%} "
                    f"< 阈值{self.cfg.volatility_threshold:.4%}, 不调整"
                )

        volatility_adjusted_amount = ema_adjusted_amount * volatility_factor

        # --- 4. 流动性/滑点保护（单向深度）---
        liquidity_limit = float('inf')
        if self.cfg.liquidity_protection_enabled:
            # 🔥 [修复] 使用传入的 ct_val 而非 self.ct_val
            depth_value = self._calculate_depth_value(
                order_book,
                self.cfg.liquidity_depth_levels,
                side,
                ct_val  # 🔥 [修复] 使用传入的合约面值参数
            )

            liquidity_limit = depth_value * self.cfg.liquidity_depth_ratio

            side_name = "卖方" if side == 'buy' else "买方"
            logger.debug(
                f"📊 [流动性保护] {side_name}盘口前{self.cfg.liquidity_depth_levels}档 "
                f"总额={depth_value:.2f} USDT, "
                f"限制={liquidity_limit:.2f} USDT "
                f"({self.cfg.liquidity_depth_ratio*100:.0f}%)"
            )

        # --- 5. 最终决策 ---
        # 取波动调整后的金额和流动性限制的最小值
        final_amount = min(volatility_adjusted_amount, liquidity_limit)

        # 硬性最小值检查
        if final_amount < self.cfg.min_order_value:
            logger.warning(
                f"🛑 [订单过小] {final_amount:.2f} USDT < "
                f"最小值 {self.cfg.min_order_value:.2f} USDT, 跳过"
            )
            return 0.0

        logger.info(
            f"✅ [仓位决策] "
            f"基础={base_amount:.2f} USDT, "
            f"信号系数={multiplier:.1f}x, "
            f"波动系数={volatility_factor:.1%}, "
            f"流动性限制={liquidity_limit:.2f} USDT, "
            f"最终={final_amount:.2f} USDT"
        )

        return final_amount

    def _update_volatility(self, price: float):
        """
        更新波动率指标（使用标准差）

        Args:
            price (float): 当前价格
        """
        self._price_history.append(price)

        if len(self._price_history) >= self.cfg.volatility_ema_period:
            # 计算价格的标准差（波动率）
            prices = list(self._price_history)
            mean = sum(prices) / len(prices)

            # 标准差 = sqrt(sum((x - mean)^2) / n)
            variance = sum((p - mean) ** 2 for p in prices) / len(prices)
            std_dev = variance ** 0.5

            # 标准差 / 均值 = 波动率
            self._volatility_value = std_dev / mean if mean > 0 else 0.0

            logger.debug(
                f"📈 [波动率更新] 均值={mean:.6f}, "
                f"标准差={std_dev:.6f}, "
                f"波动率={self._volatility_value:.4%}"
            )

    def _calculate_depth_value(self, order_book: Dict[str, Any], levels: int, side: str, ct_val: float = 1.0) -> float:
        """
        计算盘口前N档的总金额（🔥 关键：单向深度）

        Args:
            order_book: {'bids': [...], 'asks': [...]}
            levels: 档位数量
            side: 交易方向 'buy' 或 'sell'
            ct_val: 合约面值（1张=ct_val个币）

        Returns:
            float: 总金额 (USDT)
        """
        try:
            # 🔥 关键：根据交易方向使用对应方深度
            # 做多（buy）看卖方深度（asks）
            # 做空（sell）看买方深度（bids）
            if side == 'buy':
                depth_orders = order_book.get('asks', [])
                side_name = "卖方"
            else:
                depth_orders = order_book.get('bids', [])
                side_name = "买方"

            total_value = 0.0

            # 🔥 关键修复：正确处理 OrderBook 数据格式
            # BookParser 已标准化为 [[price_float, size_float], ...]
            # 🔥 [严重修复] 必须乘以 ct_val，因为订单簿中的 size 是币的数量
            # 例如：DOGE-USDT-SWAP 的 ctVal=10，size=10 实际价值 = price * size * 10
            for i in range(min(levels, len(depth_orders))):
                order = depth_orders[i]
                # 确保有 2 个元素（price 和 size）
                if len(order) >= 2:
                    price = float(order[0])
                    size = float(order[1])
                    total_value += price * size * ct_val  # 🔥 [修复] 乘以合约面值

            logger.debug(
                f"📊 [深度计算] {side_name}盘口前{levels}档 "
                f"总金额={total_value:.2f} USDT (ctVal={ct_val})"
            )

            return total_value

        except Exception as e:
            logger.error(f"❌ [深度计算失败] {e}", exc_info=True)
            return 0.0

    def convert_to_contracts(
        self,
        amount_usdt: float,
        current_price: float,
        ct_val: float = 1.0
    ) -> int:
        """
        将USDT金额转换为合约张数

        🔥 [修复] 使用四舍五入而非截断，避免计算误差

        Args:
            amount_usdt: USDT金额
            current_price: 当前价格
            ct_val: 合约面值 (1张=ct_val个币)

        Returns:
            int: 合约张数
        """
        if current_price <= 0 or ct_val <= 0:
            logger.error(f"❌ [合约转换失败] 价格或ct_val无效: price={current_price}, ct_val={ct_val}")
            return 0

        # 计算每张合约的价值
        contract_value = current_price * ct_val

        # 🔥 [修复] 使用四舍五入，避免int()截断导致的误差
        # 例如：450 / 822.52 = 0.547，int()会得到0，round()会得到1
        contracts = round(amount_usdt / contract_value)

        # 确保至少返回1张（如果计算结果>=0.5）
        # 这样可以避免因为浮点精度问题导致的0张
        if contracts >= 0.5:
            contracts = max(1, contracts)
        else:
            contracts = 0

        logger.debug(
            f"💰 [合约转换] {amount_usdt:.2f} USDT / "
            f"({current_price:.6f} × {ct_val}) = {contracts} 张 (每张价值={contract_value:.2f} USDT)"
        )

        return contracts

    def get_state(self) -> dict:
        """
        获取当前状态（用于调试和监控）

        Returns:
            dict: 当前状态信息
        """
        return {
            'config': {
                'base_equity_ratio': self.cfg.base_equity_ratio,
                'signal_scaling_enabled': self.cfg.signal_scaling_enabled,
                'signal_threshold_normal': self.cfg.signal_threshold_normal,
                'signal_threshold_aggressive': self.cfg.signal_threshold_aggressive,
                'signal_aggressive_multiplier': self.cfg.signal_aggressive_multiplier,
                'liquidity_protection_enabled': self.cfg.liquidity_protection_enabled,
                'liquidity_depth_ratio': self.cfg.liquidity_depth_ratio,
                'liquidity_depth_levels': self.cfg.liquidity_depth_levels,
                'volatility_protection_enabled': self.cfg.volatility_protection_enabled,
                'volatility_threshold': self.cfg.volatility_threshold
            },
            'current_volatility': self._volatility_value,
            'price_history_len': len(self._price_history)
        }
