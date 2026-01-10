"""
OKX 公共 WebSocket 网关 (Public WebSocket Gateway)

提供实时市场数据流，推送标准 TICK 事件到事件总线。

关键特性：
- 继承 WebSocketGateway 基类
- 推送 TICK 事件到事件总线
- 自动重连机制（指数退避）
- 高性能，低延迟

设计原则：
- 使用标准事件格式
- 集成事件总线
- 保持原有 TickStream 功能
"""

import asyncio
import json
import logging
from typing import Optional
import aiohttp
from aiohttp import ClientSession, WSMessage, ClientError
from ..base_gateway import WebSocketGateway
from ...core.event_types import Event, EventType
from .auth import OkxSigner

logger = logging.getLogger(__name__)


class OkxPublicWsGateway(WebSocketGateway):
    """
    OKX 公共 WebSocket 网关

    实时接收 trades 数据，推送 TICK 事件到事件总线。

    Example:
        >>> async with OkxPublicWsGateway(
        ...     symbol="BTC-USDT-SWAP",
        ...     event_bus=event_bus
        ... ) as gateway:
        ...     await gateway.connect()
        ...     await asyncio.sleep(60)
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
            use_demo (bool): 是否使用模拟盘
            ws_url (Optional[str]): WebSocket URL
            event_bus: 事件总线实例
        """
        super().__init__(
            name="okx_ws_public",
            event_bus=event_bus
        )

        self.symbol = symbol
        self.use_demo = use_demo

        # 始终使用实盘 URL 获取 Public 数据
        if ws_url:
            self.ws_url = ws_url
        else:
            self.ws_url = self.WS_URL_PRODUCTION

        # 连接状态
        self._session: Optional[ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._is_running = False
        self._reconnect_attempts = 0
        self._reconnect_enabled = True
        self._base_reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._max_reconnect_attempts = 10

        logger.info(
            f"OkxPublicWsGateway 初始化: symbol={symbol}, ws_url={self.ws_url}"
        )

    async def connect(self) -> bool:
        """
        连接 WebSocket

        Returns:
            bool: 连接是否成功
        """
        try:
            if self._session is None or self._session.closed:
                self._session = ClientSession()

            logger.info(f"正在连接 WebSocket: {self.ws_url}")

            self._ws = await self._session.ws_connect(
                self.ws_url,
                receive_timeout=30.0
            )

            self._connected = True
            self._reconnect_attempts = 0

            logger.info(f"WebSocket 连接成功: {self.symbol}")

            # 订阅 trades 频道
            await self.subscribe(['trades'])

            # 启动消息循环
            asyncio.create_task(self._message_loop())

            # 启动重连循环
            asyncio.create_task(self._reconnect_loop())

            return True

        except ClientError as e:
            logger.error(f"WebSocket 连接失败: {e}")
            return False
        except Exception as e:
            logger.error(f"WebSocket 连接异常: {e}")
            return False

    async def disconnect(self):
        """断开连接"""
        logger.info("停止 WebSocket...")
        self._is_running = False
        self._connected = False

        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.error(f"关闭 WebSocket 失败: {e}")
            self._ws = None

        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                logger.error(f"关闭 Session 失败: {e}")
            self._session = None

        logger.info("WebSocket 已停止")

    async def is_connected(self) -> bool:
        """
        检查连接状态

        Returns:
            bool: 是否已连接
        """
        return self._connected and self._ws and not self._ws.closed

    async def subscribe(self, channels: list, symbol: Optional[str] = None):
        """
        订阅频道

        Args:
            channels (list): 频道列表
            symbol (str): 交易对（可选）
        """
        try:
            subscribe_msg = {
                "op": "subscribe",
                "args": [{
                    "channel": "trades",
                    "instId": self.symbol
                }]
            }

            json_str = json.dumps(subscribe_msg, separators=(',', ':'))

            logger.info(f"发送订阅消息: {json_str}")

            await self._ws.send_str(json_str)

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

            await self._ws.send_str(json_str)

            logger.info(f"已发送取消订阅请求: {self.symbol}")

        except Exception as e:
            logger.error(f"取消订阅失败: {e}")

    async def on_message(self, message: WSMessage):
        """
        收到消息时的回调

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
                self._connected = False

            elif message.type == aiohttp.WSMsgType.CLOSED:
                logger.warning("WebSocket 连接已关闭")
                self._connected = False

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
                    code = data.get("code")
                    if code == "0":
                        logger.info(f"订阅成功: {data.get('arg', {})}")
                    else:
                        logger.error(f"订阅失败: {data}")
                elif data["event"] == "error":
                    logger.error(f"OKX API 错误: {data}")
                return

            # 处理交易数据
            if "data" in data and isinstance(data["data"], list):
                logger.debug(f"收到 {len(data['data'])} 笔交易数据")
                for trade_item in data["data"]:
                    await self._process_trade(trade_item)

        except Exception as e:
            logger.error(f"数据处理异常: {e}, 原始数据: {data}")

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

            logger.debug(f"收到成交: {price:.2f} x {size:.4f} = {usdt_value:.2f} USDT")

            # 推送 TICK 事件到事件总线
            if self._event_bus:
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
                self.publish_event(event)

        except Exception as e:
            logger.error(f"交易处理异常: {e}, 原始数据: {trade_item}", exc_info=True)

    async def _message_loop(self):
        """消息接收循环"""
        try:
            while self._connected and self._is_running:
                try:
                    msg = await asyncio.wait_for(
                        self._ws.receive(),
                        timeout=30.0
                    )
                    await self.on_message(msg)

                except asyncio.TimeoutError:
                    logger.warning("接收消息超时，可能连接已断开")
                    self._connected = False
                    break

        except Exception as e:
            logger.error(f"消息循环异常: {e}")
            self._connected = False

    async def _reconnect_loop(self):
        """自动重连循环"""
        self._is_running = True

        while self._is_running and self._reconnect_enabled:
            # 如果已连接，等待一段时间后检查
            if self._connected:
                await asyncio.sleep(10)
                continue

            # 检查是否超过最大重连次数
            if self._reconnect_attempts >= self._max_reconnect_attempts:
                logger.error(
                    f"重连次数超过限制 ({self._max_reconnect_attempts})，停止重连"
                )
                break

            # 计算重连延迟
            if self._reconnect_attempts == 0:
                delay = 1.0
            else:
                delay = self._base_reconnect_delay * (2 ** min(self._reconnect_attempts, 5))
            delay = min(delay, self._max_reconnect_delay)

            logger.info(
                f"等待 {delay:.1f} 秒后重连 "
                f"(尝试 {self._reconnect_attempts + 1}/{self._max_reconnect_attempts})"
            )

            await asyncio.sleep(delay)

            # 尝试重连
            self._reconnect_attempts += 1
            success = await self.connect()

            if success:
                logger.info(f"重连成功 (尝试 {self._reconnect_attempts})")
            else:
                logger.warning(f"重连失败 (尝试 {self._reconnect_attempts})")

    async def on_error(self, error: Exception):
        """
        错误回调

        Args:
            error (Exception): 错误对象
        """
        logger.error(f"WebSocket 错误: {error}")
        if self._event_bus:
            event = Event(
                type=EventType.ERROR,
                data={
                    'code': 'WS_ERROR',
                    'message': str(error),
                    'source': 'okx_ws_public'
                },
                source="okx_ws_public"
            )
            self.publish_event(event)

    async def on_close(self):
        """连接关闭回调"""
        logger.warning("WebSocket 连接已关闭")
        self._connected = False

    async def close(self):
        """关闭网关"""
        await self.disconnect()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()
