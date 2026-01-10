"""
订单管理器 (Order Manager)

订单生命周期的大总管，负责下单、撤单和订单状态跟踪。

核心职责：
- 接收策略下单请求
- 风控检查
- 调用 Gateway 发单
- 追踪订单状态
- 自动撤单

设计原则：
- 监听网关的订单推送
- 维护本地订单状态
- 提供统一的订单接口
"""

import logging
from typing import Dict, Optional
from dataclasses import dataclass
from ..core.event_types import Event, EventType
from ..gateways.base_gateway import RestGateway

logger = logging.getLogger(__name__)


@dataclass
class Order:
    """订单信息"""
    order_id: str
    symbol: str
    side: str           # "buy" or "sell"
    order_type: str      # "market", "limit", "ioc"
    size: float
    price: float
    filled_size: float = 0.0
    status: str = "pending"  # pending, live, filled, cancelled, rejected
    strategy_id: str = "default"
    raw: dict = None


class OrderManager:
    """
    订单管理器

    负责订单生命周期的管理，包括下单、撤单和状态跟踪。

    Example:
        >>> om = OrderManager(
        ...     rest_gateway=gateway,
        ...     event_bus=event_bus
        ... )
        >>>
        >>> # 下单
        >>> order = await om.submit_order(
        ...     symbol="BTC-USDT-SWAP",
        ...     side="buy",
        ...     order_type="market",
        ...     size=0.1,
        ...     strategy_id="vulture"
        ... )
        >>>
        >>> # 撤单
        >>> await om.cancel_order(order.order_id, order.symbol)
    """

    def __init__(
        self,
        rest_gateway: RestGateway,
        event_bus=None
    ):
        """
        初始化订单管理器

        Args:
            rest_gateway (RestGateway): REST API 网关
            event_bus: 事件总线实例
        """
        self._rest_gateway = rest_gateway
        self._event_bus = event_bus

        # 本地订单 {order_id: Order}
        self._orders: Dict[str, Order] = {}

        # Symbol -> OrderId 映射（用于快速查找）
        self._symbol_to_orders: Dict[str, Dict[str, Order]] = {}

        logger.info("OrderManager 初始化")

    async def submit_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        size: float,
        price: Optional[float] = None,
        strategy_id: str = "default",
        **kwargs
    ) -> Optional[Order]:
        """
        提交订单

        Args:
            symbol (str): 交易对
            side (str): 方向（buy/sell）
            order_type (str): 订单类型（market/limit/ioc）
            size (float): 数量
            price (float): 价格（限价单必需）
            strategy_id (str): 策略 ID
            **kwargs: 其他参数

        Returns:
            Order: 订单对象，失败返回 None
        """
        try:
            logger.info(
                f"收到下单请求: {symbol} {side} {order_type} "
                f"{size:.4f} @ {price if price else 'market'}"
            )

            # TODO: 风控检查
            # - 检查策略资金是否充足
            # - 检查持仓限制
            # - 检查风险参数

            # 调用 Gateway 下单
            response = await self._rest_gateway.place_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                size=size,
                price=price,
                strategy_id=strategy_id,
                **kwargs
            )

            if not response:
                logger.error(f"下单失败: {symbol} {side} {size:.4f}")
                return None

            # 提取订单 ID
            order_id = response.get('ordId')
            if not order_id:
                logger.error(f"订单响应缺少 ordId: {response}")
                return None

            # 创建本地订单对象
            order = Order(
                order_id=order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                size=size,
                price=price if price else 0.0,
                filled_size=float(response.get('fillSz', 0)),
                status='live',
                strategy_id=strategy_id,
                raw=response
            )

            # 保存订单
            self._orders[order_id] = order

            if symbol not in self._symbol_to_orders:
                self._symbol_to_orders[symbol] = {}
            self._symbol_to_orders[symbol][order_id] = order

            logger.info(
                f"订单提交成功: {order_id} - {symbol} {side} {size:.4f}"
            )

            # 推送订单事件
            if self._event_bus:
                event = Event(
                    type=EventType.ORDER_SUBMITTED,
                    data={
                        'order_id': order_id,
                        'symbol': symbol,
                        'side': side,
                        'order_type': order_type,
                        'size': size,
                        'price': price if price else 0.0,
                        'strategy_id': strategy_id,
                        'raw': response
                    },
                    source="order_manager"
                )
                self._event_bus.put_nowait(event)

            return order

        except Exception as e:
            logger.error(f"下单异常: {e}")
            return None

    async def cancel_order(
        self,
        order_id: str,
        symbol: str
    ) -> bool:
        """
        撤销订单

        Args:
            order_id (str): 订单 ID
            symbol (str): 交易对

        Returns:
            bool: 撤单是否成功
        """
        try:
            logger.info(f"收到撤单请求: {order_id} - {symbol}")

            # 检查订单是否存在
            order = self._orders.get(order_id)
            if not order:
                logger.error(f"订单不存在: {order_id}")
                return False

            # 检查订单状态
            if order.status in ['filled', 'cancelled']:
                logger.warning(
                    f"订单已{order.status}，无法撤单: {order_id}"
                )
                return False

            # 调用 Gateway 撤单
            response = await self._rest_gateway.cancel_order(
                order_id=order_id,
                symbol=symbol
            )

            if not response:
                logger.error(f"撤单失败: {order_id}")
                return False

            # 更新订单状态
            order.status = 'cancelled'
            logger.info(f"订单已撤销: {order_id}")

            # 推送撤单事件
            if self._event_bus:
                event = Event(
                    type=EventType.ORDER_CANCELLED,
                    data={
                        'order_id': order_id,
                        'symbol': symbol,
                        'raw': response
                    },
                    source="order_manager"
                )
                self._event_bus.put_nowait(event)

            return True

        except Exception as e:
            logger.error(f"撤单异常: {e}")
            return False

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """
        撤销所有订单

        Args:
            symbol (str): 交易对（可选），None 表示撤销所有订单

        Returns:
            int: 成功撤销的订单数量
        """
        try:
            logger.info(f"撤销所有订单: symbol={symbol or 'all'}")

            # 获取待撤销的订单
            orders_to_cancel = []

            if symbol:
                # 撤销指定交易对的订单
                orders = self._symbol_to_orders.get(symbol, {})
                for order in orders.values():
                    if order.status in ['pending', 'live']:
                        orders_to_cancel.append(order)
            else:
                # 撤销所有订单
                for order in self._orders.values():
                    if order.status in ['pending', 'live']:
                        orders_to_cancel.append(order)

            # 撤销订单
            success_count = 0
            for order in orders_to_cancel:
                success = await self.cancel_order(order.order_id, order.symbol)
                if success:
                    success_count += 1

            logger.info(f"撤销订单完成: 成功 {success_count}/{len(orders_to_cancel)}")
            return success_count

        except Exception as e:
            logger.error(f"撤销所有订单异常: {e}")
            return 0

    def on_order_update(self, event: Event):
        """
        监听订单更新事件

        Args:
            event (Event): ORDER_UPDATE 事件
        """
        try:
            data = event.data
            order_id = data.get('order_id')

            if not order_id:
                return

            # 查找订单
            order = self._orders.get(order_id)

            if not order:
                # 新订单，创建记录
                order = Order(
                    order_id=order_id,
                    symbol=data.get('symbol'),
                    side=data.get('side'),
                    order_type=data.get('order_type'),
                    size=data.get('size', 0),
                    price=data.get('price', 0),
                    filled_size=data.get('filled_size', 0),
                    status=data.get('status', 'pending'),
                    raw=data
                )
                self._orders[order_id] = order

                symbol = order.symbol
                if symbol not in self._symbol_to_orders:
                    self._symbol_to_orders[symbol] = {}
                self._symbol_to_orders[symbol][order_id] = order

            else:
                # 更新现有订单
                order.filled_size = data.get('filled_size', order.filled_size)
                order.status = data.get('status', order.status)
                order.raw = data

            logger.debug(
                f"订单更新: {order_id} - status={order.status}, "
                f"filled={order.filled_size:.4f}/{order.size:.4f}"
            )

        except Exception as e:
            logger.error(f"处理订单更新事件失败: {e}")

    def on_order_filled(self, event: Event):
        """
        监听订单成交事件

        Args:
            event (Event): ORDER_FILLED 事件
        """
        try:
            data = event.data
            order_id = data.get('order_id')

            if not order_id:
                return

            # 更新订单状态
            order = self._orders.get(order_id)
            if order:
                order.filled_size = data.get('filled_size', order.filled_size)
                order.status = 'filled'

                logger.info(
                    f"订单成交: {order_id} - "
                    f"{order.symbol} {order.side} {order.filled_size:.4f}"
                )

                # 清理已完成订单
                self._cleanup_order(order_id)

        except Exception as e:
            logger.error(f"处理订单成交事件失败: {e}")

    def on_order_cancelled(self, event: Event):
        """
        监听订单取消事件

        Args:
            event (Event): ORDER_CANCELLED 事件
        """
        try:
            data = event.data
            order_id = data.get('order_id')

            if not order_id:
                return

            # 更新订单状态
            order = self._orders.get(order_id)
            if order:
                order.status = 'cancelled'
                logger.info(f"订单已取消: {order_id}")

                # 清理已完成订单
                self._cleanup_order(order_id)

        except Exception as e:
            logger.error(f"处理订单取消事件失败: {e}")

    def _cleanup_order(self, order_id: str):
        """
        清理已完成订单

        Args:
            order_id (str): 订单 ID
        """
        order = self._orders.get(order_id)
        if not order:
            return

        # 从 symbol 映射中移除
        symbol_orders = self._symbol_to_orders.get(order.symbol)
        if symbol_orders and order_id in symbol_orders:
            del symbol_orders[order_id]

            # 如果没有订单了，清理 symbol
            if not symbol_orders:
                del self._symbol_to_orders[order.symbol]

    def get_order(self, order_id: str) -> Optional[Order]:
        """
        获取订单

        Args:
            order_id (str): 订单 ID

        Returns:
            Order: 订单对象，如果不存在返回 None
        """
        return self._orders.get(order_id)

    def get_orders_by_symbol(self, symbol: str) -> Dict[str, Order]:
        """
        获取指定交易对的所有订单

        Args:
            symbol (str): 交易对

        Returns:
            dict: {order_id: Order}
        """
        return self._symbol_to_orders.get(symbol, {}).copy()

    def get_all_orders(self) -> Dict[str, Order]:
        """
        获取所有订单

        Returns:
            dict: {order_id: Order}
        """
        return self._orders.copy()

    def get_summary(self) -> dict:
        """
        获取订单汇总信息

        Returns:
            dict: 汇总信息
        """
        pending_count = sum(
            1 for o in self._orders.values()
            if o.status == 'pending'
        )
        live_count = sum(
            1 for o in self._orders.values()
            if o.status == 'live'
        )
        filled_count = sum(
            1 for o in self._orders.values()
            if o.status == 'filled'
        )
        cancelled_count = sum(
            1 for o in self._orders.values()
            if o.status == 'cancelled'
        )

        return {
            'total_orders': len(self._orders),
            'pending_count': pending_count,
            'live_count': live_count,
            'filled_count': filled_count,
            'cancelled_count': cancelled_count
        }

    def reset(self):
        """重置所有订单状态"""
        self._orders.clear()
        self._symbol_to_orders.clear()
        logger.info("订单管理器已重置")
