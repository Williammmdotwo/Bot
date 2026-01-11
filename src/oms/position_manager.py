"""
持仓管理器 (Position Manager)

维护"此时此刻"的准确持仓和 PnL，并处理期望持仓与实际持仓的同步。

核心职责：
- 实时维护本地持仓状态
- 计算持仓盈亏
- 处理期望持仓与实际持仓的同步 (Shadow Ledger 逻辑)
- 幽灵单风险防护：持仓归零时自动撤销止损单

设计原则：
- 监听 POSITION_UPDATE 和 ORDER_FILLED 事件
- 支持持仓对账 (Reconcile)
- 实时计算 PnL
"""

import time
import asyncio
import logging
from typing import Dict, Optional
from dataclasses import dataclass
from ..core.event_types import Event, EventType

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    side: str           # "long" or "short"
    size: float         # 持仓数量
    entry_price: float  # 开仓均价
    unrealized_pnl: float = 0.0  # 未实现盈亏
    leverage: int = 1
    raw: dict = None    # 原始 API 数据

    @property
    def signed_size(self) -> float:
        """有符号持仓大小 (long=正, short=负)"""
        return self.size if self.side == 'long' else -self.size


class PositionManager:
    """
    持仓管理器

    实时维护持仓状态，计算盈亏，并处理期望持仓与实际持仓的同步。
    集成幽灵单风险防护：持仓归零时自动撤销止损单。

    Example:
        >>> pm = PositionManager(event_bus)
        >>>
        >>> # 更新持仓
        >>> event = Event(
        ...     type=EventType.POSITION_UPDATE,
        ...     data={'symbol': 'BTC-USDT-SWAP', 'size': 1.0, ...}
        ... )
        >>> pm.update_from_event(event)
        >>>
        >>> # 获取持仓
        >>> pos = pm.get_position('BTC-USDT-SWAP')
        >>> print(f"Size: {pos.size}, PnL: {pos.unrealized_pnl}")
    """

    def __init__(
        self,
        event_bus=None,
        order_manager=None,
        sync_threshold_pct: float = 0.10,
        cooldown_seconds: int = 60
    ):
        """
        初始化持仓管理器

        Args:
            event_bus: 事件总线实例
            order_manager: 订单管理器实例（用于幽灵单防护）
            sync_threshold_pct: 触发同步的差异阈值（默认 10%）
            cooldown_seconds: 同步操作的冷却时间（秒）
        """
        self._event_bus = event_bus
        self._order_manager = order_manager

        # 本地持仓 {symbol: Position}
        self._positions: Dict[str, Position] = {}

        # 策略期望持仓 {symbol: {"side": "long", "size": 1.5, "timestamp": ...}}
        self._target_positions: Dict[str, Dict] = {}

        # 同步冷却时间
        self._last_sync_time: Dict[str, float] = {}
        self._sync_threshold = sync_threshold_pct
        self._sync_cooldown = cooldown_seconds

        logger.info(
            f"PositionManager 初始化: sync_threshold={sync_threshold_pct*100}%, "
            f"cooldown={cooldown_seconds}s"
        )

    def update_from_event(self, event: Event):
        """
        根据事件更新持仓

        Args:
            event (Event): POSITION_UPDATE 或 ORDER_FILLED 事件
        """
        try:
            if event.type == EventType.POSITION_UPDATE:
                self._update_position(event.data)

            elif event.type == EventType.ORDER_FILLED:
                self._update_position_from_order(event.data)

            else:
                logger.warning(f"不支持的事件类型: {event.type}")

        except Exception as e:
            logger.error(f"更新持仓失败: {e}")

    def _update_position(self, api_position: dict):
        """
        从 API 持仓更新本地状态（对账逻辑）

        Args:
            api_position (dict): API 返回的持仓数据
        """
        symbol = api_position.get('symbol')
        if not symbol:
            return

        size = api_position.get('size', 0)
        entry_price = api_position.get('entry_price', 0)
        unrealized_pnl = api_position.get('unrealized_pnl', 0)
        leverage = api_position.get('leverage', 1)

        # 判断持仓方向
        if size > 0:
            side = 'long'
        elif size < 0:
            side = 'short'
        else:
            # 持仓为 0，移除
            if symbol in self._positions:
                logger.info(f"持仓已平仓: {symbol}")
                del self._positions[symbol]

                # 幽灵单防护：撤销所有止损单
                # 当持仓归零时，如果还有挂着的止损单，可能会变成反向开仓单
                if self._order_manager:
                    asyncio.create_task(
                        self._cancel_stop_loss_orders(symbol)
                    )

            return

        # 更新持仓
        self._positions[symbol] = Position(
            symbol=symbol,
            side=side,
            size=abs(size),
            entry_price=entry_price,
            unrealized_pnl=unrealized_pnl,
            leverage=leverage,
            raw=api_position
        )

        logger.debug(
            f"持仓更新: {symbol} {side} {abs(size):.4f} @ {entry_price:.2f}, "
            f"PnL: {unrealized_pnl:+.2f}"
        )

    def _update_position_from_order(self, order_filled: dict):
        """
        从订单成交更新持仓（本地预计算）

        Args:
            order_filled (dict): 订单成交数据
        """
        symbol = order_filled.get('symbol')
        side = order_filled.get('side')
        filled_size = order_filled.get('filled_size', 0)
        price = order_filled.get('price', 0)

        if not symbol or filled_size <= 0:
            return

        # 获取当前持仓
        current_pos = self._positions.get(symbol)

        if side == 'buy':
            # 买入：增加多头持仓或减少空头持仓
            if current_pos:
                if current_pos.side == 'short':
                    # 减少空头
                    current_pos.size -= filled_size
                    current_pos.unrealized_pnl = self._calculate_pnl(
                        current_pos, price
                    )
                    if current_pos.size <= 0:
                        del self._positions[symbol]
                else:
                    # 增加多头，重新计算均价
                    total_value = (current_pos.size * current_pos.entry_price +
                                filled_size * price)
                    current_pos.size += filled_size
                    current_pos.entry_price = total_value / current_pos.size
                    current_pos.unrealized_pnl = self._calculate_pnl(
                        current_pos, price
                    )
            else:
                # 新开多头
                self._positions[symbol] = Position(
                    symbol=symbol,
                    side='long',
                    size=filled_size,
                    entry_price=price,
                    unrealized_pnl=0.0
                )

        elif side == 'sell':
            # 卖出：增加空头持仓或减少多头持仓
            if current_pos:
                if current_pos.side == 'long':
                    # 减少多头
                    current_pos.size -= filled_size
                    current_pos.unrealized_pnl = self._calculate_pnl(
                        current_pos, price
                    )
                    if current_pos.size <= 0:
                        # 计算已实现盈亏
                        realized_pnl = self._calculate_pnl(current_pos, price)
                        del self._positions[symbol]
                        logger.info(
                            f"平仓已实现盈亏: {symbol} {realized_pnl:+.2f} USDT"
                        )
                        # TODO: 推送 REALIZED_PNL 事件
                else:
                    # 增加空头，重新计算均价
                    total_value = (current_pos.size * current_pos.entry_price +
                                filled_size * price)
                    current_pos.size += filled_size
                    current_pos.entry_price = total_value / current_pos.size
                    current_pos.unrealized_pnl = self._calculate_pnl(
                        current_pos, price
                    )
            else:
                # 新开空头
                self._positions[symbol] = Position(
                    symbol=symbol,
                    side='short',
                    size=filled_size,
                    entry_price=price,
                    unrealized_pnl=0.0
                )

        logger.debug(
            f"订单成交更新持仓: {symbol} {side} {filled_size:.4f} @ {price:.2f}"
        )

    def _calculate_pnl(self, position: Position, current_price: float) -> float:
        """
        计算持仓盈亏

        Args:
            position (Position): 持仓对象
            current_price (float): 当前价格

        Returns:
            float: 未实现盈亏（USDT）
        """
        if position.side == 'long':
            # 多头: (当前价 - 开仓价) * 数量
            return (current_price - position.entry_price) * position.size
        else:
            # 空头: (开仓价 - 当前价) * 数量
            return (position.entry_price - current_price) * position.size

    def update_target_position(self, symbol: str, side: str, size: float):
        """
        更新策略期望的持仓（由策略调用）

        Args:
            symbol (str): 交易对
            side (str): 方向（long/short）
            size (float): 目标数量
        """
        self._target_positions[symbol] = {
            'side': side.lower(),
            'size': float(size),
            'timestamp': time.time()
        }
        logger.debug(f"更新目标持仓: {symbol} {side} {size:.4f}")

    def _reconcile(self, api_position: dict) -> Optional[dict]:
        """
        对账逻辑（Shadow Ledger 核心逻辑）

        检查期望持仓与实际持仓的差异，计算需要同步的操作。

        Args:
            api_position (dict): API 返回的实际持仓数据

        Returns:
            dict: 同步计划（如果需要同步），None 则不需要
        """
        symbol = api_position.get('symbol')
        if not symbol:
            return None

        target = self._target_positions.get(symbol)

        # 1. 如果策略没有设定目标，暂不处理
        if not target or target['size'] <= 0:
            return None

        # 2. 冷却时间检查
        last_sync = self._last_sync_time.get(symbol, 0)
        if time.time() - last_sync < self._sync_cooldown:
            return None

        # 3. 计算实际持仓（有符号）
        actual_size = api_position.get('size', 0)
        actual_signed_size = actual_size  # OKX API: long=正, short=负

        # 4. 计算目标持仓（有符号）
        target_signed_size = (
            target['size'] if target['side'] == 'long' else -target['size']
        )

        # 5. 计算差额
        delta = target_signed_size - actual_signed_size

        # 6. 计算偏差百分比
        if abs(target_signed_size) > 0:
            diff_pct = abs(delta) / abs(target_signed_size)
        else:
            diff_pct = 0.0 if abs(actual_signed_size) == 0 else 1.0

        # 7. 判断是否触发阈值
        if diff_pct > self._sync_threshold:
            action_side = 'buy' if delta > 0 else 'sell'
            action_amount = abs(delta)

            return {
                'symbol': symbol,
                'type': 'RESYNC',
                'side': action_side,
                'amount': action_amount,
                'reason': (
                    f"持仓差异: 目标 {target_signed_size:.2f} vs "
                    f"实际 {actual_signed_size:.2f} (差异: {diff_pct*100:.1f}%)"
                )
            }

        return None

    def check_sync_needed(self, symbol: str) -> Optional[dict]:
        """
        检查是否需要同步持仓

        Args:
            symbol (str): 交易对

        Returns:
            dict: 同步计划（如果需要同步），None 则不需要
        """
        # 获取当前持仓
        position = self._positions.get(symbol)
        if not position:
            return None

        # 构造 API 持仓数据格式
        api_position = {
            'symbol': symbol,
            'size': position.signed_size
        }

        # 执行对账
        sync_plan = self._reconcile(api_position)

        if sync_plan:
            # 标记已同步
            self._last_sync_time[symbol] = time.time()
            logger.info(f"检测到持仓差异，需要同步: {sync_plan}")

        return sync_plan

    def get_position(self, symbol: str) -> Optional[Position]:
        """
        获取指定交易对的持仓

        Args:
            symbol (str): 交易对

        Returns:
            Position: 持仓对象，如果不存在返回 None
        """
        return self._positions.get(symbol)

    def get_all_positions(self) -> Dict[str, Position]:
        """
        获取所有持仓

        Returns:
            dict: {symbol: Position}
        """
        return self._positions.copy()

    def get_summary(self) -> dict:
        """
        获取持仓汇总信息

        Returns:
            dict: 汇总信息
        """
        total_pnl = sum(p.unrealized_pnl for p in self._positions.values())
        long_count = sum(1 for p in self._positions.values() if p.side == 'long')
        short_count = sum(1 for p in self._positions.values() if p.side == 'short')

        return {
            'total_pnl': total_pnl,
            'position_count': len(self._positions),
            'long_count': long_count,
            'short_count': short_count
        }

    def get_total_exposure(self) -> float:
        """
        获取所有持仓的总敞口价值

        敞口 = sum(abs(持仓数量 * 当前价格))
        用于计算真实杠杆

        Returns:
            float: 总敞口价值（USDT）
        """
        total_exposure = 0.0

        for position in self._positions.values():
            # 假设 raw 中有当前价格，如果没有则使用开仓价
            current_price = position.entry_price
            if position.raw and 'current_price' in position.raw:
                current_price = float(position.raw['current_price'])

            exposure = abs(position.size * current_price)
            total_exposure += exposure

        return total_exposure

    def get_symbol_exposure(self, symbol: str) -> float:
        """
        获取指定币种的敞口价值

        Args:
            symbol (str): 交易对

        Returns:
            float: 该币种的敞口价值（USDT）
        """
        position = self._positions.get(symbol)
        if not position:
            return 0.0

        # 假设 raw 中有当前价格，如果没有则使用开仓价
        current_price = position.entry_price
        if position.raw and 'current_price' in position.raw:
            current_price = float(position.raw['current_price'])

        return abs(position.size * current_price)

    def update_current_price(self, symbol: str, current_price: float):
        """
        更新持仓的当前价格（用于实时计算敞口）

        Args:
            symbol (str): 交易对
            current_price (float): 当前价格
        """
        position = self._positions.get(symbol)
        if position:
            if not position.raw:
                position.raw = {}
            position.raw['current_price'] = current_price

            # 重新计算未实现盈亏
            position.unrealized_pnl = self._calculate_pnl(position, current_price)

            logger.debug(
                f"更新持仓价格: {symbol} {current_price:.2f}, "
                f"未实现盈亏: {position.unrealized_pnl:+.2f}"
            )

    async def _cancel_stop_loss_orders(self, symbol: str):
        """
        幽灵单防护：撤销指定交易对的所有止损单

        当持仓归零时，如果还有挂着的止损单，可能会变成反向开仓单（幽灵单）。
        此方法会异步撤销所有止损单，防止这种风险。

        Args:
            symbol (str): 交易对
        """
        try:
            if not self._order_manager:
                return

            # 调用 OrderManager 撤销所有止损单
            cancelled_count = await self._order_manager.cancel_all_stop_loss_orders(symbol)

            if cancelled_count > 0:
                logger.info(
                    f"✅ 幽灵单防护已触发: 撤销 {cancelled_count} 个止损单 - {symbol}"
                )
                # TODO: 推送 GHOST_ORDER_CLEANUP 事件
            else:
                logger.debug(f"无止损单需要撤销: {symbol}")

        except Exception as e:
            logger.error(f"幽灵单防护失败: {e}", exc_info=True)

    def reset(self):
        """重置所有持仓状态"""
        self._positions.clear()
        self._target_positions.clear()
        self._last_sync_time.clear()
        logger.info("持仓管理器已重置")
