"""
订单管理器 (Order Manager)

订单生命周期的大总管，负责下单、撤单和订单状态跟踪。

核心职责：
- 接收策略下单请求
- 风控检查
- 调用 Gateway 发单
- 追踪订单状态
- 自动撤单
- 硬止损执行（Hard Stop）

设计原则：
- 监听网关的订单推送
- 维护本地订单状态
- 提供统一的订单接口
- 订单成交后立即发送止损订单到交易所
"""

import logging
import time
from typing import Dict, Optional
from dataclasses import dataclass
from ..core.event_types import Event, EventType
from ..gateways.base_gateway import RestGateway
from ..risk.pre_trade import PreTradeCheck

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
    stop_loss_order_id: str = None  # 关联的止损订单 ID


class OrderManager:
    """
    订单管理器

    负责订单生命周期的管理，包括下单、撤单和状态跟踪。
    硬止损策略：订单成交后立即发送止损订单到交易所。

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
        event_bus=None,
        pre_trade_check: Optional[PreTradeCheck] = None
    ):
        """
        初始化订单管理器

        Args:
            rest_gateway (RestGateway): REST API 网关
            event_bus: 事件总线实例
            pre_trade_check (PreTradeCheck): 交易前检查器
        """
        self._rest_gateway = rest_gateway
        self._event_bus = event_bus
        self._pre_trade_check = pre_trade_check or PreTradeCheck()

        # 本地订单 {order_id: Order}
        self._orders: Dict[str, Order] = {}

        # Symbol -> OrderId 映射（用于快速查找）
        self._symbol_to_orders: Dict[str, Dict[str, Order]] = {}

        # 止损订单映射 {open_order_id: stop_loss_order_id}
        self._stop_loss_orders: Dict[str, str] = {}

        # 订阅事件
        if self._event_bus:
            self._event_bus.subscribe(EventType.ORDER_UPDATE, self.on_order_update)
            self._event_bus.subscribe(EventType.ORDER_FILLED, self.on_order_filled)
            self._event_bus.subscribe(EventType.ORDER_CANCELLED, self.on_order_cancelled)
            logger.debug("OrderManager 已订阅订单事件")

        logger.info("OrderManager 初始化")

    async def submit_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        size: float,
        price: Optional[float] = None,
        strategy_id: str = "default",
        stop_loss_price: Optional[float] = None,
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
            stop_loss_price (float): 止损价格（用于硬止损）
            **kwargs: 其他参数

        Returns:
            Order: 订单对象，失败返回 None
        """
        try:
            logger.info(
                f"收到下单请求: {symbol} {side} {order_type} "
                f"{size:.4f} @ {price if price else 'market'}"
            )

            # 1. 风控检查
            amount_usdt = price * size if price else 0
            if amount_usdt > 0:
                risk_passed, risk_reason = self._pre_trade_check.check({
                    'symbol': symbol,
                    'side': side,
                    'size': size,
                    'price': price if price else 0,
                    'amount_usdt': amount_usdt,
                    'order_id': f"{symbol}_{time.time()}"
                })

                if not risk_passed:
                    logger.error(f"风控拒绝下单: {risk_reason}")
                    return None

            # 2. 其他风控检查（待实现）
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
                stop_loss_price=stop_loss_price,
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

    async def cancel_all_stop_loss_orders(self, symbol: str) -> int:
        """
        撤销指定交易对的所有止损单（幽灵单防护）

        Args:
            symbol (str): 交易对

        Returns:
            int: 成功撤销的止损单数量

        注意：
            用于持仓归零时，撤销所有挂着的 reduce_only 止损单，
            防止止损单变成反向开仓单（幽灵单风险）。
        """
        try:
            logger.info(f"撤销所有止损单: symbol={symbol}")

            # 获取该交易对的所有订单
            orders = self._symbol_to_orders.get(symbol, {})
            if not orders:
                return 0

            # 筛选出所有止损单（order_type='stop_market'）
            stop_loss_orders_to_cancel = []
            for order in orders.values():
                if (order.status in ['pending', 'live'] and
                    order.order_type == 'stop_market'):
                    stop_loss_orders_to_cancel.append(order)

            # 撤销止损单
            success_count = 0
            for order in stop_loss_orders_to_cancel:
                success = await self.cancel_order(order.order_id, order.symbol)
                if success:
                    success_count += 1

            if success_count > 0:
                logger.info(
                    f"✅ 幽灵单防护: 撤销 {success_count} 个止损单 - {symbol}"
                )

            return success_count

        except Exception as e:
            logger.error(f"撤销止损单异常: {e}", exc_info=True)
            return 0

    async def on_order_update(self, event: Event):
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

    async def on_order_filled(self, event: Event):
        """
        监听订单成交事件（硬止损执行核心）

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

                # 硬止损执行：立即发送止损订单
                # 只有开仓订单（买入/卖出）才需要止损
                if order.order_id not in self._stop_loss_orders:
                    await self._place_stop_loss_order(order, data)

                # 清理已完成订单
                self._cleanup_order(order_id)

        except Exception as e:
            logger.error(f"处理订单成交事件失败: {e}", exc_info=True)

    async def _place_stop_loss_order(self, open_order: Order, fill_data: dict, retry_count: int = 3):
        """
        放置止损订单（硬止损核心 + 重试机制 + 紧急平仓）

        Args:
            open_order (Order): 已成交的开仓订单
            fill_data (dict): 成交数据，包含 stop_loss_price
            retry_count (int): 重试次数（默认3次）
        """
        import asyncio

        try:
            # 检查是否提供了止损价格
            stop_loss_price = fill_data.get('stop_loss_price')
            if not stop_loss_price or stop_loss_price <= 0:
                logger.warning(
                    f"订单 {open_order.order_id} 未提供止损价格，跳过止损"
                )
                return

            # 计算止损方向
            # 买入开仓 → 止损卖出
            # 卖出开仓 → 止损买入
            stop_side = 'sell' if open_order.side == 'buy' else 'buy'

            # 计算止损价格
            # 对于做多：止损价格 < 开仓价
            # 对于做空：止损价格 > 开仓价
            if open_order.side == 'buy':
                stop_price = stop_loss_price
            else:
                stop_price = stop_loss_price

            # 重试机制：尝试多次发送止损单
            last_exception = None
            for attempt in range(1, retry_count + 1):
                try:
                    # 调用 Gateway 下止损订单（服务器端 Stop Market）
                    response = await self._rest_gateway.place_order(
                        symbol=open_order.symbol,
                        side=stop_side,
                        order_type='stop_market',  # 标记为止损订单
                        size=open_order.filled_size,  # 使用实际成交数量
                        price=stop_price,  # 触发价格
                        strategy_id=open_order.strategy_id,
                        reduce_only=True  # 只减仓
                    )

                    if response:
                        # 成功！提取止损订单 ID
                        stop_loss_order_id = response.get('ordId')
                        if stop_loss_order_id:
                            # 记录止损订单映射
                            self._stop_loss_orders[open_order.order_id] = stop_loss_order_id

                            # 在原订单上标记止损订单 ID
                            open_order.stop_loss_order_id = stop_loss_order_id

                            # 创建止损订单对象
                            stop_loss_order = Order(
                                order_id=stop_loss_order_id,
                                symbol=open_order.symbol,
                                side=stop_side,
                                order_type='stop_market',
                                size=open_order.filled_size,
                                price=stop_price,
                                filled_size=0.0,
                                status='live',
                                strategy_id=open_order.strategy_id,
                                raw=response
                            )

                            # 保存止损订单
                            self._orders[stop_loss_order_id] = stop_loss_order

                            if stop_loss_order.symbol not in self._symbol_to_orders:
                                self._symbol_to_orders[stop_loss_order.symbol] = {}
                            self._symbol_to_orders[stop_loss_order.symbol][stop_loss_order_id] = stop_loss_order

                            logger.info(
                                f"✅ 硬止损已激活: {stop_loss_order_id} - "
                                f"{stop_loss_order.symbol} {stop_side} {stop_loss_order.size:.4f} @ {stop_price:.2f} "
                                f"(关联开仓单: {open_order.order_id}, 尝试次数: {attempt})"
                            )

                            # 推送止损订单事件
                            if self._event_bus:
                                event = Event(
                                    type=EventType.ORDER_SUBMITTED,
                                    data={
                                        'order_id': stop_loss_order_id,
                                        'symbol': stop_loss_order.symbol,
                                        'side': stop_side,
                                        'order_type': 'stop_market',
                                        'size': stop_loss_order.size,
                                        'price': stop_price,
                                        'strategy_id': open_order.strategy_id,
                                        'linked_order_id': open_order.order_id,
                                        'is_stop_loss': True,
                                        'raw': response
                                    },
                                    source="order_manager"
                                )
                                self._event_bus.put_nowait(event)
                            return  # 成功则退出

                except Exception as e:
                    last_exception = e
                    logger.warning(
                        f"止损订单提交失败（尝试 {attempt}/{retry_count}）: {e}"
                    )

                    # 如果不是最后一次尝试，等待后重试
                    if attempt < retry_count:
                        await asyncio.sleep(0.5)  # 间隔 0.5 秒

            # 所有重试都失败了，触发紧急平仓
            logger.error(
                f"🚨 所有重试失败！触发紧急平仓机制: {open_order.order_id} - "
                f"{open_order.symbol} {open_order.side} {open_order.filled_size:.4f}, "
                f"原因: {last_exception}"
            )

            # 立即发送市价平仓单
            await self._emergency_close_position(open_order)

        except Exception as e:
            logger.error(f"放置止损订单异常: {e}", exc_info=True)
            # 紧急平仓作为最后手段
            await self._emergency_close_position(open_order)

    async def _emergency_close_position(self, open_order: Order):
        """
        紧急平仓（止损单失败后的最后手段）

        Args:
            open_order (Order): 已成交的开仓订单
        """
        try:
            # 计算平仓方向
            close_side = 'sell' if open_order.side == 'buy' else 'buy'

            logger.warning(
                f"⚠️  执行紧急平仓: {open_order.symbol} {close_side} {open_order.filled_size:.4f} @ market"
            )

            # 发送市价平仓单
            response = await self._rest_gateway.place_order(
                symbol=open_order.symbol,
                side=close_side,
                order_type='market',  # 市价成交
                size=open_order.filled_size,
                price=0.0,  # 市价单不指定价格
                strategy_id=open_order.strategy_id,
                reduce_only=True,  # 只减仓
                is_emergency_close=True  # 标记为紧急平仓
            )

            if response:
                order_id = response.get('ordId')
                logger.info(
                    f"✅ 紧急平仓单已提交: {order_id} - "
                    f"{open_order.symbol} {close_side} {open_order.filled_size:.4f}"
                )

                # 推送紧急平仓事件
                if self._event_bus:
                    event = Event(
                        type=EventType.ORDER_SUBMITTED,
                        data={
                            'order_id': order_id,
                            'symbol': open_order.symbol,
                            'side': close_side,
                            'order_type': 'market',
                            'size': open_order.filled_size,
                            'price': 0.0,
                            'strategy_id': open_order.strategy_id,
                            'linked_order_id': open_order.order_id,
                            'is_emergency_close': True,
                            'raw': response
                        },
                        source="order_manager"
                    )
                    self._event_bus.put_nowait(event)
            else:
                logger.error(f"🚨 紧急平仓失败！仓位裸奔风险！: {open_order.symbol}")

        except Exception as e:
            logger.error(f"🚨 紧急平仓异常！仓位裸奔风险！: {e}", exc_info=True)

    async def on_order_cancelled(self, event: Event):
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

        # 清理止损订单映射（如果订单有关联的止损）
        if order_id in self._stop_loss_orders:
            stop_loss_order_id = self._stop_loss_orders[order_id]
            del self._stop_loss_orders[order_id]
            logger.debug(f"清理止损订单映射: {order_id} -> {stop_loss_order_id}")

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
        self._stop_loss_orders.clear()
        logger.info("订单管理器已重置")
