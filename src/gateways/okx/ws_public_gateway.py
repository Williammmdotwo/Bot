"""
OKX 公共 WebSocket 网关 (Public WebSocket Gateway)

提供实时市场数据流，推送标准 TICK 事件到事件总线。

关键特性：
- 继承 WsBaseGateway 基类（修复重连风暴）
- 推送 TICK 事件到事件总线
- 自动重连机制（指数退避）
- 高性能，低延迟

设计原则：
- 使用标准事件格式
- 集成事件总线
- 保持原有 TickStream 功能

🔥 修复内容：
- 继承新的 WsBaseGateway，避免并发竞争
- 使用基类的自动重连和资源清理机制
- 防止 WebSocket 重连风暴
"""

import asyncio
import json
import logging
from typing import Optional
import aiohttp
from aiohttp import WSMessage, ClientError
from ...core.event_types import Event, EventType
from .ws_base import WsBaseGateway

logger = logging.getLogger(__name__)


class OkxPublicWsGateway(WsBaseGateway):
    """
    OKX 公共 WebSocket 网关（修复版）

    实时接收 trades 数据，推送 TICK 事件到事件总线。
    继承自 WsBaseGateway，自动获得：
    - 并发连接保护（asyncio.Lock）
    - 指数退避重连机制
    - 资源自动清理
    - 心跳保活

    Example:
        >>> gateway = OkxPublicWsGateway(
        ...     symbol="BTC-USDT-SWAP",
        ...     event_bus=event_bus
        ... )
        >>> await gateway.connect()
        >>> await asyncio.sleep(60)
        >>> await gateway.disconnect()
    """

    # OKX Public WebSocket URL
    WS_URL_PRODUCTION = "wss://ws.okx.com:8443/ws/v5/public"
    WS_URL_DEMO = "wss://wspap.okx.com:8443/ws/v5/public"

    # 大单阈值（USDT）
    WHALE_THRESHOLD = 10000.0

    def __init__(
        self,
        symbol: str,
        use_demo: bool = False,
        ws_url: Optional[str] = None,
        event_bus=None
    ):
        """
        初始化公共 WebSocket 网关

        Args:
            symbol (str): 交易对
            use_demo (bool): 是否使用模拟盘（公共数据始终使用实盘 URL）
            ws_url (Optional[str]): WebSocket URL
            event_bus: 事件总线实例
        """
        # 确定 WebSocket URL（公共数据始终使用实盘 URL）
        if ws_url:
            final_url = ws_url
        else:
            final_url = self.WS_URL_PRODUCTION

        # 调用父类初始化
        super().__init__(
            name="okx_ws_public",
            ws_url=final_url,
            event_bus=event_bus
        )

        self.symbol = symbol
        self.use_demo = use_demo

        # 订单簿深度数据（用于 Maker 策略）
        self._order_book = {
            'bids': [],  # 买单 [[price, size, ...], ...]
            'asks': []   # 卖单 [[price, size, ...], ...]
        }

        logger.info(
            f"OkxPublicWsGateway 初始化: symbol={symbol}, ws_url={final_url}"
        )

    async def connect(self) -> bool:
        """
        连接 WebSocket（委托给基类）

        Returns:
            bool: 连接是否成功
        """
        # 委托给基类的 connect 方法（自动处理并发、重连、资源清理）
        return await super().connect()

    async def disconnect(self):
        """
        断开连接（委托给基类）
        """
        logger.info("停止 WebSocket...")
        # 委托给基类（自动清理所有资源）
        await super().disconnect()

    # is_connected() 已由基类实现，无需重写

    async def subscribe(self, channels: list, symbol: Optional[str] = None):
        """
        订阅频道

        Args:
            channels (list): 频道列表
            symbol (str): 交易对（可选）
        """
        try:
            args = []
            for channel in channels:
                if channel == 'trades':
                    args.append({
                        "channel": "trades",
                        "instId": self.symbol
                    })
                elif channel == 'books':
                    args.append({
                        "channel": "books",
                        "instId": self.symbol
                    })

            subscribe_msg = {
                "op": "subscribe",
                "args": args
            }

            json_str = json.dumps(subscribe_msg, separators=(',', ':'))

            logger.info(f"发送订阅消息: {json_str}")

            # 使用基类的 send_message 方法
            await self.send_message(json_str)

            logger.info(f"已发送订阅请求: {self.symbol}")

        except Exception as e:
            logger.error(f"订阅频道失败: {e}")
            raise

    async def unsubscribe(self, channels: list, symbol: Optional[str] = None):
        """
        取消订阅

        Args:
            channels (list): 频道列表
            symbol (str): 交易对（可选）
        """
        try:
            unsubscribe_msg = {
                "op": "unsubscribe",
                "args": [{
                    "channel": "trades",
                    "instId": self.symbol
                }]
            }

            json_str = json.dumps(unsubscribe_msg, separators=(',', ':'))

            # 使用基类的 send_message 方法
            await self.send_message(json_str)

            logger.info(f"已发送取消订阅请求: {self.symbol}")

        except Exception as e:
            logger.error(f"取消订阅失败: {e}")

    # 🔥 重写基类的 _on_message 方法
    async def _on_message(self, message: WSMessage):
        """
        收到消息时的回调（基类调用）

        Args:
            message (WSMessage): WebSocket 消息
        """
        try:
            if message.type == aiohttp.WSMsgType.TEXT:
                logger.debug(f"收到文本消息: {message.data[:200]}...")
                data = json.loads(message.data)
                await self._process_data(data)

            elif message.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket 错误: {message.data}")

            elif message.type == aiohttp.WSMsgType.CLOSED:
                logger.debug("WebSocket 连接已关闭")

            else:
                logger.debug(f"未处理的消息类型: {message.type}")

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
        except Exception as e:
            logger.error(f"消息处理异常: {e}")

    async def _process_data(self, data: dict):
        """
        处理解析后的数据

        Args:
            data (dict): 解析后的 JSON 数据
        """
        try:
            # 处理订阅响应
            if "event" in data:
                if data["event"] == "subscribe":
                    # OKX 订阅成功响应没有 code 字段
                    logger.info(f"订阅成功: {data.get('arg', {})}")
                elif data["event"] == "error":
                    logger.error(f"OKX API 错误: {data}")
                return

            # 处理订单簿数据（books 频道）
            if "data" in data and isinstance(data["data"], list):
                channel = data.get("arg", {}).get("channel", "")

                if channel == "books":
                    logger.debug(f"收到订单簿数据")
                    await self._process_orderbook(data["data"])
                elif channel == "trades":
                    # 📉 优化：高频数据流不记录详细日志，仅保留错误日志
                    for trade_item in data["data"]:
                        await self._process_trade(trade_item)

        except Exception as e:
            logger.error(f"数据处理异常: {e}, 原始数据: {data}")

    async def _process_orderbook(self, book_data):
        """
        处理订单簿数据，更新 Best Bid/Ask

        Args:
            book_data: 订单簿数据
        """
        try:
            # 取最新的订单簿数据
            if isinstance(book_data, list) and len(book_data) > 0:
                book = book_data[0]  # OKX 返回的是数组，取第一个

                # 更新买单和卖单
                bids = book.get('bids', [])
                asks = book.get('asks', [])

                # 只保留前5档（足够用于 Maker 策略）
                self._order_book['bids'] = bids[:5] if bids else []
                self._order_book['asks'] = asks[:5] if asks else []

                # 📉 优化：高频订单簿数据不记录详细日志

        except Exception as e:
            logger.error(f"订单簿处理异常: {e}", exc_info=True)

    async def _process_trade(self, trade_item):
        """
        处理单笔交易数据，推送 TICK 事件

        Args:
            trade_item: 交易数据
        """
        try:
            price = None
            size = None
            timestamp = None
            side = None

            # 解析字典格式（新格式）
            if isinstance(trade_item, dict):
                price = float(trade_item.get("px", "0"))
                size = float(trade_item.get("sz", "0"))
                timestamp = int(trade_item.get("ts", "0"))
                side = trade_item.get("side", "")

            # 解析数组格式（旧格式）
            elif isinstance(trade_item, list):
                if len(trade_item) < 5:
                    logger.debug(f"交易数据格式错误: {trade_item}")
                    return
                price = float(trade_item[0])
                size = float(trade_item[1])
                timestamp = int(trade_item[3])
                side = str(trade_item[4])

            # 验证数据
            if price is None or size is None or timestamp is None or side is None:
                logger.error(f"交易数据不完整: {trade_item}")
                return

            if side not in ["buy", "sell"]:
                logger.error(f"无效的交易方向: {side}")
                return

            # 计算交易金额
            usdt_value = price * size

            # 📉 优化：高频成交数据不记录详细日志，仅保留错误日志
            if usdt_value >= self.WHALE_THRESHOLD:
                logger.info(
                    f"🐋 [大单] {price:.2f} x {size:.4f} = {usdt_value:.2f} USDT"
                )

            # 推送 TICK 事件到事件总线
            if self._event_bus:
                from ...core.event_types import Event
                event = Event(
                    type=EventType.TICK,
                    data={
                        'symbol': self.symbol,
                        'price': price,
                        'size': size,
                        'side': side,
                        'usdt_value': usdt_value,
                        'timestamp': timestamp
                    },
                    source="okx_ws_public"
                )
                await self.publish_event(event)

        except Exception as e:
            logger.error(f"交易处理异常: {e}, 原始数据: {trade_item}", exc_info=True)

    # 🔥 新增：重写 _on_connected 钩子，连接成功后自动订阅
    async def _on_connected(self):
        """
        连接成功后的钩子（自动订阅频道）
        """
        logger.info("WebSocket 连接成功，准备订阅频道...")
        try:
            # 订阅 trades 和 order_book 频道
            await self.subscribe(['trades', 'books'])
        except Exception as e:
            logger.error(f"订阅频道失败: {e}")

    def get_best_bid_ask(self) -> tuple:
        """
        获取最优买一价和卖一价

        Returns:
            tuple: (best_bid, best_ask) 如果没有数据返回 (0.0, 0.0)
        """
        try:
            bids = self._order_book.get('bids', [])
            asks = self._order_book.get('asks', [])

            best_bid = 0.0
            best_ask = 0.0

            # 买一价（买单第一档的价格）
            if bids and len(bids) > 0:
                best_bid = float(bids[0][0])

            # 卖一价（卖单第一档的价格）
            if asks and len(asks) > 0:
                best_ask = float(asks[0][0])

            return (best_bid, best_ask)

        except Exception as e:
            logger.error(f"获取最佳买卖价失败: {e}", exc_info=True)
            return (0.0, 0.0)

    # 消息循环已由基类实现，无需重写

    # 重连机制已由基类实现（指数退避），无需重写

    # 错误处理已由基类实现，可选重写

    # 连接关闭处理已由基类实现，无需重写

    # 兼容性方法
    async def close(self):
        """关闭网关（兼容性）"""
        await self.disconnect()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.disconnect()
