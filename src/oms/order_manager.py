"""
订单管理器
"""

import logging
import time
from typing import Dict, Optional
from dataclasses import dataclass
from ..core.event_types import Event, EventType
from ..gateways.base_gateway import RestGateway
from ..risk.pre_trade import PreTradeCheck
from ..risk.risk_guardian import RiskGuardian

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
    stop_loss_price: Optional[float] = None  # 🔥 修复：保存止损价格，防止成交回调中丢失


class OrderManager:
    """
    订单管理器

    负责订单生命周期的管理，包括下单、撤单和状态跟踪。
    硬止损策略：订单成交后立即发送止损订单到交易所。
    """

    def __init__(
        self,
        rest_gateway: RestGateway,
        event_bus=None,
        pre_trade_check: Optional[PreTradeCheck] = None,
        capital_commander=None,
        risk_guardian: Optional[RiskGuardian] = None
    ):
        """
        初始化订单管理器

        Args:
            rest_gateway (RestGateway): REST API 网关
            event_bus: 事件总线实例
            pre_trade_check (PreTradeCheck): 交易前检查器（已弃用，使用 risk_guardian）
            capital_commander: 资金指挥官（用于购买力检查）
            risk_guardian (RiskGuardian): 风控守卫（统一风控入口）
        """
        self._rest_gateway = rest_gateway
        self._event_bus = event_bus
        self._pre_trade_check = pre_trade_check or PreTradeCheck()  # 保留兼容性
        self._capital_commander = capital_commander
        self._risk_guardian = risk_guardian  # 🔥 新增：统一风控入口

        # 本地订单 {order_id: Order}
        self._orders: Dict[str, Order] = {}

        # Symbol -> OrderId 映射（用于快速查找）
        self._symbol_to_orders: Dict[str, Dict[str, Order]] = {}

        # 🔥 [P0 修复] clOrdId -> order_id 索引（O(1) 查找）
        self._clord_id_to_order_id: Dict[str, str] = {}

        # 止损订单映射 {open_order_id: stop_loss_order_id}
        self._stop_loss_orders: Dict[str, str] = {}

        # 订阅事件
        if self._event_bus:
            self._event_bus.register(EventType.ORDER_UPDATE, self.on_order_update)
            self._event_bus.register(EventType.ORDER_FILLED, self.on_order_filled)
            self._event_bus.register(EventType.ORDER_CANCELLED, self.on_order_cancelled)
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
        提交订单（已修复市价单日志崩溃问题）
        """
        # 🔥 修复：处理市价单的 price=None 问题（防止 NoneType 比较错误）
        # 1. 确定计算价值用的价格
        calc_price = price
        if calc_price is None or calc_price <= 0:
            # 如果是市价单(price=None)，尝试获取当前市场价格
            ticker = None
            try:
                if hasattr(self._rest_gateway, 'get_ticker'):
                    ticker = self._rest_gateway.get_ticker(symbol)
                if ticker:
                    calc_price = float(ticker.get('last', 0.0))
            except Exception as e:
                logger.debug(f"获取ticker失败: {e}")

        # 2. 如果还是获取不到价格，使用 0（市价单的风控依赖 bypass）
        if calc_price is None or calc_price <= 0:
            calc_price = 0.0

        # 3. 计算订单名义价值
        amount_usdt = calc_price * size if calc_price else 0

        # 4. 更新价格显示逻辑（使用计算后的价格）
        price_str = "MARKET"
        if calc_price and calc_price > 0:
            try:
                price_str = f"{calc_price:.5f}"
            except:
                price_str = str(calc_price)

        # 🔥 [P0 修复] 使用 RiskGuardian 统一风控入口
        if self._risk_guardian:
            # 判断是否为紧急平仓
            is_emergency_close = (
                order_type == 'market' or
                kwargs.get('is_emergency_close', False)
            )

            # 统一风控验证
            validation_result = self._risk_guardian.validate_order(
                symbol=symbol,
                side=side,
                size=size,
                price=price if price else calc_price,
                strategy_id=strategy_id,
                stop_loss_price=stop_loss_price,
                bypass=is_emergency_close
            )

            if not validation_result.is_passed:
                # 🔥 [修复] 风控拒绝改为 WARNING 级别，让用户能看到
                logger.warning(
                    f"🛑 [RiskGuardian] 风控拒绝下单: {validation_result.reason}"
                )
                return None

            # 🎉 风控通过，使用建议仓位（如果有调整）
            suggested_size = validation_result.suggested_size
            if suggested_size != size:
                logger.info(
                    f"💡 [RiskGuardian] 仓位调整: {size:.4f} -> {suggested_size:.4f}"
                )
                size = suggested_size
        else:
            # 🔥 兼容性：如果没有 RiskGuardian，使用旧的 PreTradeCheck
            if amount_usdt > 0:
                # 🔥 修复：判断是否为紧急平仓（市价单），传递bypass参数
                is_emergency_close = (order_type == 'market' or
                                      kwargs.get('is_emergency_close', False))

                risk_passed, risk_reason = self._pre_trade_check.check({
                    'symbol': symbol,
                    'side': side,
                    'size': size,
                    'price': price if price else 0,
                    'amount_usdt': amount_usdt,
                    'order_id': f"{symbol}_{time.time()}",
                    'bypass': is_emergency_close  # 🔥 传递bypass参数
                })

                if not risk_passed:
                    # 🔥 [修复] 风控拒绝改为 WARNING 级别，让用户能看到
                    logger.warning(f"🛑 [PreTradeCheck] 风控拒绝下单: {risk_reason}")
                    return None

            # 2. 🔥 [修复] 资金检查（CapitalCommander：购买力）
            # 在调用 Gateway 之前检查资金，避免订单被交易所拒绝
            if self._capital_commander and amount_usdt > 0:
                try:
                    # 注意：需要传入 symbol 和 side 以支持平仓检测
                    has_power = self._capital_commander.check_buying_power(
                        strategy_id=strategy_id,
                        amount_usdt=amount_usdt,
                        symbol=symbol,
                        side=side
                    )

                    if not has_power:
                        logger.warning(
                            f"🚫 资金检查未通过 [{strategy_id}]: "
                            f"{symbol} {side} {size:.4f}, "
                            f"amount={amount_usdt:.2f} USDT"
                        )
                        return None
                except Exception as e:
                    # 资金检查失败时，记录警告但继续尝试
                    logger.warning(
                        f"⚠️  资金检查异常，继续下单: {e} "
                        f"(strategy={strategy_id}, symbol={symbol})"
                    )

        # 3. 其他风控检查（待实现）
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
        # 🔥 修复：将stop_loss_price保存到Order对象和raw字段，防止成交回调中丢失
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
            stop_loss_price=stop_loss_price,  # 保存止损价格
            raw=response  # raw字段已经包含了完整数据
        )

        # 保存订单
        self._orders[order_id] = order

        if symbol not in self._symbol_to_orders:
            self._symbol_to_orders[symbol] = {}
        self._symbol_to_orders[symbol][order_id] = order

        # 🔥 [P0 修复] 建立 clOrdId -> order_id 映射（O(1) 查找）
        cl_ord_id = response.get('clOrdId')
        if cl_ord_id:
            self._clord_id_to_order_id[cl_ord_id] = order_id
            logger.debug(f"建立 clOrdId 映射: {cl_ord_id} -> {order_id}")

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
            self._event_bus.put_nowait(event, priority=5)  # ORDER_UPDATE 优先级

        return order

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
                self._event_bus.put_nowait(event, priority=5)  # ORDER_UPDATE 优先级

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

        🔥 [P0 修复] 使用 O(1) 字典查找替代 O(n) 遍历

        Args:
            event (Event): ORDER_FILLED 事件
        """
        try:
            data = event.data
            order_id = data.get('order_id')
            cl_ord_id = data.get('clOrdId')

            if not order_id and not cl_ord_id:
                return

            # 🔥 [P0 修复] O(1) 查找逻辑（替代原来的 O(n) 遍历）
            local_order = None

            # 优先使用 clOrdId 索引查找（O(1)）
            if cl_ord_id and cl_ord_id in self._clord_id_to_order_id:
                mapped_order_id = self._clord_id_to_order_id[cl_ord_id]
                local_order = self._orders.get(mapped_order_id)
                logger.debug(
                    f"通过 clOrdId 索引找到订单: {cl_ord_id} -> {mapped_order_id}"
                )
            # 降级到 order_id 直接查找（O(1)）
            elif order_id:
                local_order = self._orders.get(order_id)

            # 如果找到了订单，更新状态
            if local_order:
                local_order.filled_size = data.get('filled_size', local_order.filled_size)
                local_order.status = 'filled'

                logger.info(
                    f"订单成交: {order_id} - "
                    f"{local_order.symbol} {local_order.side} {local_order.filled_size:.4f}"
                )

                # 硬止损执行：立即发送止损订单
                # 只有开仓订单（买入/卖出）才需要止损
                if local_order.order_id not in self._stop_loss_orders:
                    await self._place_stop_loss_order(local_order, data)

                # 清理已完成订单
                self._cleanup_order(local_order.order_id)

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

            # 🔥 [Fix 3: 止损传播] 抑制平仓订单的警告
            # 平仓订单不需要止损，这是正常行为
            if not stop_loss_price or stop_loss_price <= 0:
                # 只有开仓订单（buy）才需要警告，平仓订单（sell）是正常的
                if open_order.side == 'buy':
                    logger.warning(
                        f"订单 {open_order.order_id} 未提供止损价格，跳过止损"
                    )
                else:
                    logger.debug(
                        f"订单 {open_order.order_id} 是平仓订单，无需止损"
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

                            # 🔧 修复 price=None 格式化错误：处理止损订单价格
                            stop_price_str = f"{stop_price:.2f}" if stop_price is not None else "0.00"
                            logger.info(
                                f"✅ 硬止损已激活: {stop_loss_order_id} - "
                                f"{stop_loss_order.symbol} {stop_side} {stop_loss_order.size:.4f} @ {stop_price_str} "
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
                                self._event_bus.put_nowait(event, priority=5)  # ORDER_UPDATE 优先级
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
                    self._event_bus.put_nowait(event, priority=0)  # EMERGENCY_CLOSE 优先级
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

        # 🔥 [P0 修复] 清理 clOrdId 索引（防止内存泄漏）
        if order.raw and 'clOrdId' in order.raw:
            cl_ord_id = order.raw['clOrdId']
            if cl_ord_id and cl_ord_id in self._clord_id_to_order_id:
                del self._clord_id_to_order_id[cl_ord_id]
                logger.debug(f"清理 clOrdId 索引: {cl_ord_id}")

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
