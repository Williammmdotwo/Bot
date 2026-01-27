"""
ExecutionAlgo - 执行算法

负责 ScalperV1 策略的订单执行逻辑：
- 挂单价格计算（Aggressive Maker / Conservative Maker）
- 插队逻辑判断（Chasing Conditions）
- 模拟盘价格适配（Paper Trading Price Adjustment）

设计原则：
- 单一职责：只负责价格计算和插队决策，不涉及信号生成
- 无状态：不维护任何持久化状态
- 可测试：独立的输入输出，易于单元测试
"""

import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExecutionConfig:
    """执行算法配置"""
    symbol: str = "DOGE-USDT-SWAP"
    tick_size: float = 0.0001
    spread_threshold_pct: float = 0.0005
    is_paper_trading: bool = False
    enable_chasing: bool = True
    min_chasing_distance_pct: float = 0.0005
    max_chase_distance_pct: float = 0.001
    min_order_life_seconds: float = 2.0
    aggressive_maker_spread_ticks: float = 2.0
    aggressive_maker_price_offset: float = 1.0


@dataclass
class ExecutionDecision:
    """
    执行决策对象

    属性：
        price (float): 挂单价格
        reason (str): 决策原因（maker/aggressive/chasing/skip）
        side (str): 交易方向 'buy' 或 'sell'
        metadata (dict): 额外元数据（spread_ticks, chasing_distance等）
    """
    price: float = 0.0
    reason: str = ""
    side: str = "buy"
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ExecutionAlgo:
    """
    执行算法（ScalperV1 策略）

    职责：
    1. 挂单价格计算（Aggressive Maker / Conservative Maker）
    2. 插队逻辑判断（Chasing Conditions）
    3. 模拟盘价格适配（Paper Trading Price Adjustment）
    4. 防抖动保护（最小订单存活时间）

    设计原则：
    - 单一职责：只负责价格计算和插队决策
    - 无状态：不维护任何持久化状态
    - 可测试：独立的输入输出，易于单元测试
    """

    def __init__(self, config: ExecutionConfig):
        """
        初始化执行算法

        Args:
            config (ExecutionConfig): 执行配置
        """
        self.config = config

        logger.info(
            f"⚙️ [ExecutionAlgo] 初始化: "
            f"symbol={config.symbol}, "
            f"tick_size={config.tick_size}, "
            f"is_paper_trading={config.is_paper_trading}, "
            f"enable_chasing={config.enable_chasing}"
        )

    def calculate_maker_price(
        self,
        side: str,
        best_bid: float,
        best_ask: float,
        order_age: float = 0.0
    ) -> ExecutionDecision:
        """
        计算挂单价格（Maker Price）

        根据 Spread 和交易对动态调整挂单价格：
        - 模拟盘：Mid Price（中间价）
        - 实盘 Spread > 2 Ticks：Aggressive Maker (Best Bid + 1 Tick)
        - 实盘 Spread <= 2 Ticks：Conservative Maker (Best Bid)

        Args:
            side (str): 交易方向 'buy' 或 'sell'
            best_bid (float): 最优买价
            best_ask (float): 最优卖价
            order_age (float): 订单存活时间（秒）

        Returns:
            ExecutionDecision: 执行决策对象
        """
        decision = ExecutionDecision()
        decision.side = side

        # 🔥 [模拟盘特权模式] 激进执行策略
        if self.config.is_paper_trading:
            if side == 'buy':
                decision.price = best_ask
                decision.reason = "paper_trading_aggressive"
                decision.metadata = {
                    'mode': 'paper_trading',
                    'strategy': 'aggressive_feed',
                    'target': 'best_ask',
                    'value': best_ask
                }
                logger.info(
                    f"🎯 [模拟盘喂单] {self.config.symbol}: "
                    f"买方激进吃单，挂 BestAsk={best_ask:.6f}"
                )
            else:
                decision.price = best_bid
                decision.reason = "paper_trading_aggressive"
                decision.metadata = {
                    'mode': 'paper_trading',
                    'strategy': 'aggressive_feed',
                    'target': 'best_bid',
                    'value': best_bid
                }
                logger.info(
                    f"🎯 [模拟盘喂单] {self.config.symbol}: "
                    f"卖方激进吃单，挂 BestBid={best_bid:.6f}"
                )
        else:
            # 🔥 [实盘标准模式] Maker 逻辑
            # 计算 Spread（点差）
            spread = best_ask - best_bid if best_ask > 0 and best_bid > 0 else 0.0
            spread_ticks = spread / self.config.tick_size if self.config.tick_size > 0 else 0.0

            # 🔥 [Aggressive Maker] 检查 Spread 是否 > 2 Ticks
            if spread_ticks > self.config.aggressive_maker_spread_ticks:
                # Spread 较大，使用 Aggressive 策略：Best Bid + 1 Tick
                if side == 'buy':
                    decision.price = best_bid + self.config.aggressive_maker_price_offset * self.config.tick_size
                    decision.reason = "aggressive_maker"
                    decision.metadata = {
                        'mode': 'production',
                        'strategy': 'aggressive_maker',
                        'spread_ticks': spread_ticks,
                        'offset_ticks': self.config.aggressive_maker_price_offset,
                        'best_bid': best_bid,
                        'new_price': decision.price
                    }
                    logger.info(
                        f"⚡ [Aggressive Maker] {self.config.symbol}: "
                        f"Spread={spread_ticks:.1f} Ticks > {self.config.aggressive_maker_spread_ticks}, "
                        f"挂在 Best Bid+{self.config.aggressive_maker_price_offset}={decision.price:.6f}"
                    )
                else:
                    decision.price = best_ask - self.config.aggressive_maker_price_offset * self.config.tick_size
                    decision.reason = "aggressive_maker"
                    logger.info(
                        f"⚡ [Aggressive Maker] {self.config.symbol}: "
                        f"Spread={spread_ticks:.1f} Ticks > {self.config.aggressive_maker_spread_ticks}, "
                        f"挂在 Best Ask-{self.config.aggressive_maker_price_offset}={decision.price:.6f}"
                    )
            else:
                # Spread 较小，使用 Conservative 策略：Best Bid/Ask
                if side == 'buy':
                    decision.price = best_bid
                    decision.reason = "conservative_maker"
                    decision.metadata = {
                        'mode': 'production',
                        'strategy': 'conservative_maker',
                        'spread_ticks': spread_ticks,
                        'best_bid': best_bid,
                        'new_price': decision.price
                    }
                    logger.info(
                        f"🛡️ [Conservative Maker] {self.config.symbol}: "
                        f"Spread={spread_ticks:.1f} Ticks <= {self.config.aggressive_maker_spread_ticks}, "
                        f"挂在 Best Bid={decision.price:.6f}"
                    )
                else:
                    decision.price = best_ask
                    decision.reason = "conservative_maker"
                    logger.info(
                        f"🛡️ [Conservative Maker] {self.config.symbol}: "
                        f"Spread={spread_ticks:.1f} Ticks <= {self.config.aggressive_maker_spread_ticks}, "
                        f"挂在 Best Ask={decision.price:.6f}"
                    )

        return decision

    def should_chase(
        self,
        current_maker_price: float,
        current_price: float,
        order_age: float
    ) -> bool:
        """
        判断是否应该插队

        防抖动保护：
        1. 最小订单存活时间检查（防止频繁撤单重挂）
        2. 价格偏差阈值检查

        Args:
            current_maker_price (float): 当前挂单价格
            current_price (float): 当前市场价格
            order_age (float): 订单存活时间（秒）

        Returns:
            bool: 是否应该插队
        """
        # 1. 检查是否启用追单
        if not self.config.enable_chasing:
            logger.debug(f"🛑 [ExecutionAlgo] {self.config.symbol}: 追单功能已禁用")
            return False

        # 2. 🔥 [防抖动] 最小订单存活时间检查
        # 如果订单存活时间 < 最小值（2秒），禁止撤单重挂
        if order_age < self.config.min_order_life_seconds:
            logger.debug(
                f"🛑 [ExecutionAlgo] {self.config.symbol}: "
                f"订单存活时间={order_age:.2f}s < 最小值 {self.config.min_order_life_seconds}s，"
                f"禁止频繁撤单重挂"
            )
            return False

        # 3. 🔥 [防抖动] 最小插队距离检查
        # 只在价格偏差 > tick_size * 5 时才触发插队
        min_chasing_distance = self.config.tick_size * 5
        if current_maker_price <= 0:
            logger.debug(f"🛑 [ExecutionAlgo] {self.config.symbol}: 无有效挂单价格")
            return False

        if current_price > current_maker_price:
            chase_distance = (current_price - current_maker_price) / current_maker_price

            # 如果距离太小，跳过插队
            if chase_distance < self.config.min_chasing_distance_pct:
                logger.debug(
                    f"🛑 [ExecutionAlgo] {self.config.symbol}: "
                    f"价格偏差={chase_distance*100:.3f}% "
                    f"< 最小阈值 {self.config.min_chasing_distance_pct*100:.3f}%，"
                    f"避免微小波动无效撤单重挂"
                )
                return False

            # 检查最大距离限制
            if chase_distance > self.config.max_chase_distance_pct:
                logger.debug(
                    f"🛑 [ExecutionAlgo] {self.config.symbol}: "
                    f"价格偏差={chase_distance*100:.2f}% "
                    f"> 最大限制 {self.config.max_chasing_distance_pct*100:.2f}%，"
                    f"放弃插队"
                )
                return False

            logger.debug(
                f"🔍 [ExecutionAlgo] {self.config.symbol}: "
                f"应该插队: Price moved, "
                f"Distance={chase_distance*100:.3f}%"
            )
            return True

        logger.debug(
            f"🛑 [ExecutionAlgo] {self.config.symbol}: "
            f"价格未向有利方向变动，不需要插队"
        )
        return False

    def should_skip_execution(
        self,
        best_bid: float,
        best_ask: float,
        current_price: float
    ) -> tuple:
        """
        判断是否应该跳过执行

        检查条件：
        1. OrderBook 数据是否有效
        2. 启动缓冲期检查

        Args:
            best_bid (float): 最优买价
            best_ask (float): 最优卖价
            current_price (float): 当前价格

        Returns:
            tuple: (should_skip: bool, reason: str)
        """
        # 1. OrderBook 数据有效性检查
        if best_bid <= 0 or best_ask <= 0:
            return (True, "orderbook_data_invalid")

        # 2. 启动缓冲期检查（由外部传入当前价格）
        # 这里的逻辑需要从外部获取启动时间，暂时简化
        if current_price <= 0:
            return (True, "current_price_invalid")

        # 3. 点差检查
        spread = (best_ask - best_bid) / best_bid if best_bid > 0 else 0.0
        if spread > self.config.spread_threshold_pct:
            return (True, f"spread_too_large:{spread*100:.4f}%")

        # 所有检查通过
        return (False, "")

    def get_state(self) -> dict:
        """
        获取当前状态（用于调试和监控）

        Returns:
            dict: 当前状态信息
        """
        return {
            'config': {
                'symbol': self.config.symbol,
                'tick_size': self.config.tick_size,
                'is_paper_trading': self.config.is_paper_trading,
                'enable_chasing': self.config.enable_chasing,
                'min_chasing_distance_pct': self.config.min_chasing_distance_pct * 100,
                'max_chasing_distance_pct': self.config.max_chasing_distance_pct * 100,
                'aggressive_maker_spread_ticks': self.config.aggressive_maker_spread_ticks,
                'aggressive_maker_price_offset': self.config.aggressive_maker_price_offset
            },
            'mode': 'paper_trading' if self.config.is_paper_trading else 'production'
        }
