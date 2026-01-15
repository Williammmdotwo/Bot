"""
策略基类 (Base Strategy)

定义所有策略的通用接口和基础功能。

设计原则：
- 策略只负责交易逻辑，不关心数据源
- 通过事件总线接收市场数据
- 纯粹的策略实现，不包含网络通信
- 强制止损机制（机构级风控）
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass

from ..core.event_bus import EventBus
from ..core.event_types import Event, EventType
from ..oms.order_manager import OrderManager
from ..oms.capital_commander import CapitalCommander
from ..config.risk_config import DEFAULT_RISK_CONFIG
from ..config.risk_profile import RiskProfile, StopLossType, DEFAULT_CONSERVATIVE_PROFILE

logger = logging.getLogger(__name__)


@dataclass
class OrderRequest:
    """订单请求"""
    symbol: str
    side: str           # "buy" or "sell"
    order_type: str      # "market", "limit", "ioc"
    size: float
    price: Optional[float] = None
    strategy_id: str = "default"


class BaseStrategy(ABC):
    """
    策略基类

    所有策略都必须继承此类并实现抽象方法。

    Attributes:
        strategy_id (str): 策略 ID
        symbol (str): 交易对
        mode (str): 策略模式（PRODUCTION/DEV）
        event_bus (EventBus): 事件总线
        order_manager (OrderManager): 订单管理器
        capital_commander (CapitalCommander): 资金指挥官

    Example:
        >>> class MyStrategy(BaseStrategy):
        ...     async def on_tick(self, event: Event):
        ...         data = event.data
        ...         if data['price'] > 100:
        ...             await self.buy('BTC-USDT-SWAP', 0.1)
    """

    def __init__(
        self,
        event_bus: EventBus,
        order_manager: Optional[OrderManager] = None,
        capital_commander: Optional[CapitalCommander] = None,
        position_manager=None,
        symbol: str = "BTC-USDT-SWAP",
        mode: str = "PRODUCTION",
        strategy_id: Optional[str] = None,
        cooldown_seconds: float = 5.0  # [FIX] 冷却时间参数
    ):
        """
        初始化策略

        Args:
            event_bus (EventBus): 事件总线实例
            order_manager (OrderManager): 订单管理器
            capital_commander (CapitalCommander): 资金指挥官
            position_manager: 持仓管理器（可选）
            symbol (str): 交易对
            mode (str): 策略模式（PRODUCTION/DEV）
            strategy_id (str): 策略 ID（可选，默认为类名小写）
        """
        # 使用显式传入的 strategy_id，如果没有则使用类名小写
        self.strategy_id = (
            strategy_id if strategy_id else self.__class__.__name__.lower()
        )
        self.symbol = symbol
        self.mode = mode.upper()
        self._enabled = True

        # 依赖注入
        self._event_bus = event_bus
        self._order_manager = order_manager
        self._capital_commander = capital_commander
        self._position_manager = position_manager

        # 策略风控配置（默认保守配置）
        self.risk_profile = RiskProfile(
            strategy_id=self.strategy_id,
            max_leverage=1.0,
            stop_loss_type=StopLossType.HARD_PRICE
        )

        # 策略统计
        self._ticks_received = 0
        self._signals_generated = 0
        self._orders_submitted = 0
        self._last_trade_time = 0.0

        # [FIX] 冷却时间参数（默认 5.0 秒，可通过子类覆盖）
        self._cooldown_period = cooldown_seconds

        logger.info(
            f"策略初始化: {self.strategy_id}, symbol={symbol}, mode={mode}, cooldown={cooldown_seconds}s"
        )

    @abstractmethod
    async def on_tick(self, event: Event):
        """
        处理 Tick 事件

        这是策略的核心方法，每个 TICK 事件都会调用。

        Args:
            event (Event): TICK 事件对象
                data: {
                    'symbol': str,
                    'price': float,
                    'size': float,
                    'side': str,
                    'usdt_value': float,
                    'timestamp': int
                }
        """
        pass

    @abstractmethod
    async def on_signal(self, signal: Dict[str, Any]):
        """
        处理策略信号

        Args:
            signal (dict): 策略信号，包含信号类型、数量等
                {
                    'type': 'BUY' | 'SELL',
                    'symbol': str,
                    'size': float,
                    'price': float | None
                }
        """
        pass

    async def buy(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        order_type: str = "market",
        size: Optional[float] = None
    ) -> bool:
        """
        买入（便捷方法，强制要求止损价）

        新的买入方法强制要求止损价，用于机构级风控。
        如果没有明确止损价，策略应使用波动率计算默认止损。

        Args:
            symbol (str): 交易对
            entry_price (float): 入场价格（必需）
            stop_loss_price (float): 止损价格（必需）
            order_type (str): 订单类型（market/limit/ioc）
            size (float): 数量（可选，如果不提供则基于风险计算）

        Returns:
            bool: 下单是否成功
        """
        return await self._submit_order(
            symbol=symbol,
            side="buy",
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            order_type=order_type,
            size=size
        )

    async def sell(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        order_type: str = "market",
        size: Optional[float] = None
    ) -> bool:
        """
        卖出（便捷方法，强制要求止损价）

        新的卖出方法强制要求止损价，用于机构级风控。
        如果没有明确止损价，策略应使用波动率计算默认止损。

        Args:
            symbol (str): 交易对
            entry_price (float): 入场价格（必需）
            stop_loss_price (float): 止损价格（必需）
            order_type (str): 订单类型（market/limit/ioc）
            size (float): 数量（可选，如果不提供则基于风险计算）

        Returns:
            bool: 下单是否成功
        """
        return await self._submit_order(
            symbol=symbol,
            side="sell",
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            order_type=order_type,
            size=size
        )

    async def _submit_order(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss_price: float,
        order_type: str = "market",
        size: Optional[float] = None
    ) -> bool:
        """
        统一内部下单逻辑（最终修复版：支持 size=None 自动全平）

        Args:
            symbol (str): 交易对
            side (str): 方向
            entry_price (float): 入场价格（必需）
            stop_loss_price (float): 止损价格（必需）
            order_type (str): 订单类型
            size (float): 数量（可选）

        Returns:
            bool: 下单是否成功
        """
        # 0. 参数验证
        # 🔧 修复市价平仓死循环：市价单允许 stop_loss_price=0
        if entry_price <= 0:
            logger.error(
                f"策略 {self.strategy_id} 入场价格无效: "
                f"entry={entry_price}"
            )
            return False

        # 对于市价单，允许止损价为 0（如时间止损平仓时）
        if stop_loss_price <= 0 and order_type != 'market':
            logger.error(
                f"策略 {self.strategy_id} 止损价格无效: "
                f"stop={stop_loss_price} (非市价单必须提供止损价)"
            )
            return False

        # === [新增：自动补全 size（应对策略端持仓数据丢失）] ===
        if size is None:
            if order_type == "market":
                # 尝试获取当前持仓
                pos = self.get_position(symbol)
                if pos:
                    size = abs(pos.size)
                    logger.warning(
                        f"策略 {self.strategy_id} 未指定数量，自动使用当前持仓全平: {size:.4f}"
                    )
                else:
                    logger.error(
                        f"策略 {self.strategy_id} 无法自动获取持仓数量，且传入 size=None"
                    )
                    return False
            else:
                logger.error(f"策略 {self.strategy_id} 限价单必须指定 size")
                return False
        # === [自动补全结束] ===

        # 1. 冷却检查
        current_time = time.time()
        if current_time - self._last_trade_time < self._cooldown_period:
            # 仅在非市价单时检查冷却（市价平仓通常比较急）
            if order_type != "market":
                logger.warning(
                    f"策略 {self.strategy_id} 冷却中，跳过下单 "
                    f"(剩余: {self._cooldown_period - (current_time - self._last_trade_time):.1f}s)"
                )
                return False

        # 2. 注入检查
        if not self._order_manager:
            logger.error(f"策略 {self.strategy_id} OrderManager 未注入，无法下单")
            return False

        # === [核心修复：风控检查逻辑] ===
        # 关键 1：默认 safe_size 等于传入的 size (防止后续变成 None)
        safe_size = size

        # 关键 2：执行风控计算
        if self._capital_commander:
            if order_type == "market":
                # 市价单：跳过复杂风控，强制使用原始 size
                logger.warning(
                    f"策略 {self.strategy_id} 市价单跳过风控计算: "
                    f"信任策略判断（用于紧急平仓）"
                )
                safe_size = size
            else:
                # 限价单：调用 CapitalCommander 计算
                safe_quantity = self._capital_commander.calculate_safe_quantity(
                    symbol=symbol,
                    entry_price=entry_price,
                    stop_loss_price=stop_loss_price,
                    strategy_id=self.strategy_id
                )

                if safe_quantity <= 0:
                    logger.warning(
                        f"策略 {self.strategy_id} 安全仓位计算为 0，跳过下单"
                    )
                    return False

                safe_size = safe_quantity
                logger.info(
                    f"策略 {self.strategy_id} 使用风险计算仓位: {safe_size:.4f}"
                )

        # 关键 3：最终有效性拦截
        if safe_size is None or safe_size <= 0:
            logger.error(
                f"策略 {self.strategy_id} 最终下单数量无效: "
                f"safe_size={safe_size}, 原始size={size}"
            )
            return False
        # === [修复结束] ===

        # 3. 检查购买力（如果 safe_size 有效）
        if self._capital_commander and safe_size is not None:
            amount_usdt = entry_price * safe_size
            if not self._capital_commander.check_buying_power(
                self.strategy_id,
                amount_usdt
            ):
                logger.error(
                    f"策略 {self.strategy_id} 资金不足，无法下单"
                )
                return False

        # 4. 提交订单
        order = await self._order_manager.submit_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            size=safe_size,  # 使用经过确认的 safe_size
            price=entry_price,
            strategy_id=self.strategy_id
        )

        if order:
            self._orders_submitted += 1
            self._last_trade_time = current_time

            # 🔧 修复 stop_loss_price=0 格式化错误：处理市价单
            stop_str = f"{stop_loss_price:.2f}" if stop_loss_price > 0 else "0.00 (市价)"
            # 🔧 修复：确保 safe_size 在格式化前有效
            size_str = f"{safe_size:.4f}" if safe_size is not None else "None"
            logger.info(
                f"策略 {self.strategy_id} 下单成功: "
                f"{symbol} {side} {size_str} @ {entry_price:.2f}, "
                f"stop={stop_str}"
            )
            return True
        else:
            logger.error(f"策略 {self.strategy_id} 下单失败")
            return False

    async def start(self):
        """
        启动策略

        注册 TICK 事件处理器和风控配置
        """
        if not self._event_bus:
            logger.error("EventBus 未注入，无法启动")
            return

        # 注册风控配置到 CapitalCommander
        if self._capital_commander and hasattr(self, 'risk_profile'):
            self._capital_commander.register_risk_profile(self.risk_profile)
            logger.info(
                f"策略 {self.strategy_id} 风控配置已注册: "
                f"max_leverage={self.risk_profile.max_leverage}x, "
                f"stop_loss_type={self.risk_profile.stop_loss_type.value}"
            )

        # 注册 TICK 事件处理器
        self._event_bus.register(EventType.TICK, self.on_tick)
        logger.info(f"策略 {self.strategy_id} 已启动")

    async def stop(self):
        """
        停止策略

        注销 TICK 事件处理器
        """
        if not self._event_bus:
            return

        # 注销 TICK 事件处理器
        # TODO: 实现 EventBus.unregister 方法
        logger.info(f"策略 {self.strategy_id} 已停止")

    def enable(self):
        """启用策略"""
        self._enabled = True
        logger.info(f"策略 {self.strategy_id} 已启用")

    def disable(self):
        """禁用策略"""
        self._enabled = False
        logger.info(f"策略 {self.strategy_id} 已禁用")

    def is_enabled(self) -> bool:
        """检查策略是否启用"""
        return self._enabled

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取策略统计信息

        Returns:
            dict: 统计数据
        """
        return {
            'strategy_id': self.strategy_id,
            'symbol': self.symbol,
            'mode': self.mode,
            'enabled': self._enabled,
            'ticks_received': self._ticks_received,
            'signals_generated': self._signals_generated,
            'orders_submitted': self._orders_submitted
        }

    def reset_statistics(self):
        """重置统计信息"""
        self._ticks_received = 0
        self._signals_generated = 0
        self._orders_submitted = 0
        self._last_trade_time = 0.0
        logger.info(f"策略 {self.strategy_id} 统计信息已重置")

    def _increment_ticks(self):
        """增加 Tick 计数"""
        self._ticks_received += 1

    def _increment_signals(self):
        """增加信号计数"""
        self._signals_generated += 1

    def get_position(self, symbol: str):
        """
        获取当前持仓（安全访问）

        Args:
            symbol (str): 交易对

        Returns:
            Position: 持仓对象，如果不存在返回 None
        """
        if not self._position_manager:
            logger.warning(f"策略 {self.strategy_id} PositionManager 未注入")
            return None
        return self._position_manager.get_position(symbol)

    def set_position_manager(self, position_manager):
        """
        注入 PositionManager

        Args:
            position_manager: 持仓管理器实例
        """
        self._position_manager = position_manager
        logger.debug(f"策略 {self.strategy_id} PositionManager 已注入")

    def set_risk_profile(self, profile: RiskProfile):
        """
        设置策略风控配置

        子类可以在 __init__ 中调用此方法覆盖默认配置。

        Args:
            profile (RiskProfile): 风控配置
        """
        self.risk_profile = profile
        logger.info(
            f"策略 {self.strategy_id} 风控配置已更新: "
            f"max_leverage={profile.max_leverage}x, "
            f"stop_loss_type={profile.stop_loss_type.value}"
        )
