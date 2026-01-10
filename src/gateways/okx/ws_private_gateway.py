"""
OKX 私有 WebSocket 网关 (Private WebSocket Gateway)

提供实时私有数据流，推送持仓和订单更新事件到事件总线。

关键特性：
- 继承 WebSocketGateway 基类
- 推送 POSITION_UPDATE 和 ORDER_UPDATE 事件
- 自动重连机制（指数退避）
- 签名鉴权

设计原则：
- 使用标准事件格式
- 集成事件总线
- 保持原有 UserStream 功能
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


class OkxPrivateWsGateway(WebSocketGateway):
    """
    OKX 私有 WebSocket 网关

    实时接收持仓和订单推送，推送标准事件到事件总线。

    Example:
        >>> async with OkxPrivateWsGateway(
        ...     api_key="your_api_key",
        ...     secret_key="your_secret",
        ...     passphrase="your_passphrase",
        ...     use_demo=True,
        ...     event_bus=event_bus
        ... ) as gateway:
        ...     await gateway.connect()
        ...     await asyncio.sleep(60)
    """

    # OKX Private WebSocket URL
    WS_URL_PRODUCTION = "wss://ws.okx.com:8443/ws/v5/private"
    WS_URL_DEMO = "wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999"

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        use_demo: bool = False,
        ws_url: Optional[str] = None,
        event_bus=None
    ):
        """
        初始化私有 WebSocket 网关

        Args:
            api_key (str): OKX API Key
            secret_key (str): OKX Secret Key
            passphrase (str): OKX Passphrase
            use_demo (bool): 是否使用模拟盘
            ws_url (Optional[str]): WebSocket URL
            event_bus: 事件总线实例
        """
        super().__init__(
            name="okx_ws_private",
            event_bus=event_bus
        )

        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.use_demo = use_demo

        # 根据 env 选择 URL
        if ws_url:
            self.ws_url = ws_url
        else:
            if use_demo:
                self.ws_url = self.WS_URL_DEMO
            else:
                self.ws_url = self.WS_URL_PRODUCTION

        # 连接状态
        self._session: Optional[ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._is_running = False
        self._reconnect_attempts = 0
        self._is_logged_in = False
        self._reconnect_enabled = True
        self._base_reconnect_delay = 3.0 if use_demo else 1.0
        self._max_reconnect_delay = 120.0 if use_demo else 60.0
        self._max_reconnect_attempts = 10

        logger.info(
            f"OkxPrivateWsGateway 初始化: use_demo={use_demo}, "
            f"ws_url={self.ws_url}"
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

            logger.info(f"正在连接私有 WebSocket: {self.ws_url}")

            self._ws = await self._session.ws_connect(
                self.ws_url,
                receive_timeout=30.0
            )

            self._connected = True
            self._reconnect_attempts = 0
            self._is_logged_in = False

            logger.info(f"私有 WebSocket 连接成功")

            # 发送登录包
            await self._send_login()

            # 启动消息循环
            asyncio.create_task(self._message_loop())

            # 启动重连循环
            asyncio.create_task(self._reconnect_loop())

            return True

        except ClientError as e:
            logger.error(f"私有 WebSocket 连接失败: {e}")
            return False
        except Exception as e:
            logger.error(f"私有 WebSocket 连接异常: {e}")
            return False

    async def disconnect(self):
        """断开连接"""
        logger.info("停止私有 WebSocket...")
        self._is_running = False
        self._connected = False
        self._is_logged_in = False

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

        logger.info("私有 WebSocket 已停止")

    async def is_connected(self) -> bool:
        """
        检查连接状态

        Returns:
            bool: 是否已连接
        """
        return self._connected and self._ws and not self._ws.closed

    async def subscribe(self, channels: list, symbol: Optional[str] = None):
        """
        订阅频道（登录后自动调用）

        Args:
            channels (list): 频道列表
            symbol (str): 交易对（可选）
        """
        # 私有 WebSocket 在登录成功后自动订阅
        pass

    async def unsubscribe(self, channels: list, symbol: Optional[str] = None):
        """
        取消订阅

        Args:
            channels (list): 频道列表
            symbol (str): 交易对（可选）
        """
        try:
            for channel in channels:
                unsubscribe_msg = {
                    "op": "unsubscribe",
                    "args": [{
                        "channel": channel,
                        "instType": "SWAP"
                    }]
                }

                await self._ws.send_str(
                    json.dumps(unsubscribe_msg, separators=(',', ':'))
                )

                logger.info(f"已取消订阅: {channel}")

        except Exception as e:
            logger.error(f"取消订阅失败: {e}")

    async def _send_login(self):
        """
        发送登录包
        """
        try:
            # 使用 Unix Epoch 时间戳
            timestamp = OkxSigner.get_timestamp(mode='unix')

            # 生成签名
            sign = OkxSigner.sign(
                timestamp,
                "GET",
                "/users/self/verify",
                "",
                self.secret_key
            )

            login_msg = {
                "op": "login",
                "args": [{
                    "apiKey": self.api_key,
                    "passphrase": self.passphrase,
                    "timestamp": timestamp,
                    "sign": sign
                }]
            }

            logger.info(f"发送登录包 (Unix TS={timestamp})")

            await self._ws.send_json(login_msg)

            logger.info("登录包已发送")

        except Exception as e:
            logger.error(f"发送登录包失败: {e}")
            raise

    async def _subscribe_channels(self):
        """
        登录成功后订阅频道
        """
        try:
            # 订阅持仓频道
            positions_subscribe_msg = {
                "op": "subscribe",
                "args": [{
                    "channel": "positions",
                    "instType": "SWAP"
                }]
            }

            # 订阅订单频道
            orders_subscribe_msg = {
                "op": "subscribe",
                "args": [{
                    "channel": "orders",
                    "instType": "SWAP"
                }]
            }

            await self._ws.send_str(
                json.dumps(positions_subscribe_msg, separators=(',', ':'))
            )
            logger.info("已订阅 positions 频道")

            await self._ws.send_str(
                json.dumps(orders_subscribe_msg, separators=(',', ':'))
            )
            logger.info("已订阅 orders 频道")

        except Exception as e:
            logger.error(f"订阅频道失败: {e}")
            raise

    async def on_message(self, message: WSMessage):
        """
        收到消息时的回调

        Args:
            message (WSMessage): WebSocket 消息
        """
        try:
            if message.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(message.data)
                await self._process_data(data)

            elif message.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"私有 WebSocket 错误: {message.data}")
                self._connected = False

            elif message.type == aiohttp.WSMsgType.CLOSED:
                logger.warning("私有 WebSocket 连接已关闭")
                self._connected = False
                self._is_logged_in = False

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
            # 处理登录响应
            if "event" in data:
                if data["event"] == "login":
                    code = data.get("code")
                    if code == "0":
                        logger.info("✅ 登录成功")
                        self._is_logged_in = True
                        # 登录成功后订阅频道
                        await self._subscribe_channels()
                    else:
                        logger.error(f"❌ 登录失败: {data}")
                        self._is_logged_in = False

                elif data["event"] == "subscribe":
                    channel = data.get("arg", {}).get("channel")
                    logger.info(f"✅ 频道订阅成功: {channel}")

                elif data["event"] == "error":
                    logger.error(f"❌ WebSocket 错误: {data}")

            # 处理持仓推送
            if "data" in data and "arg" in data:
                arg = data["arg"]
                channel = arg.get("channel")

                if channel == "positions":
                    positions = data.get("data", [])
                    logger.debug(f"收到持仓推送: {len(positions)} 个")

                    # 推送 POSITION_UPDATE 事件
                    if self._event_bus and positions:
                        for pos in positions:
                            event = Event(
                                type=EventType.POSITION_UPDATE,
                                data={
                                    'symbol': pos.get('instId'),
                                    'size': float(pos.get('pos', 0)),
                                    'entry_price': float(pos.get('avgPx', 0)) if pos.get('avgPx') else 0.0,
                                    'unrealized_pnl': float(pos.get('upl', 0)) if pos.get('upl') else 0.0,
                                    'leverage': int(pos.get('lever', 1)) if pos.get('lever') else 1,
                                    'raw': pos
                                },
                                source="okx_ws_private"
                            )
                            await self.publish_event(event)

                elif channel == "orders":
                    orders = data.get("data", [])
                    logger.debug(f"收到订单推送: {len(orders)} 个")

                    # 推送 ORDER_UPDATE 事件
                    if self._event_bus and orders:
                        for order in orders:
                            # 判断订单类型
                            event_type = EventType.ORDER_UPDATE
                            if order.get('state') == 'filled':
                                event_type = EventType.ORDER_FILLED
                            elif order.get('state') == 'canceled':
                                event_type = EventType.ORDER_CANCELLED

                            event = Event(
                                type=event_type,
                                data={
                                    'order_id': order.get('ordId'),
                                    'symbol': order.get('instId'),
                                    'side': order.get('side'),
                                    'order_type': order.get('ordType'),
                                    'price': float(order.get('px', 0)) if order.get('px') else 0.0,
                                    'size': float(order.get('sz', 0)),
                                    'filled_size': float(order.get('fillSz', 0)),
                                    'status': order.get('state'),
                                    'raw': order
                                },
                                source="okx_ws_private"
                            )
                            await self.publish_event(event)

        except Exception as e:
            logger.error(f"数据处理异常: {e}, 原始数据: {data}")

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
        logger.error(f"私有 WebSocket 错误: {error}")
        if self._event_bus:
            event = Event(
                type=EventType.ERROR,
                data={
                    'code': 'WS_PRIVATE_ERROR',
                    'message': str(error),
                    'source': 'okx_ws_private'
                },
                source="okx_ws_private"
            )
            await self.publish_event(event)

    async def on_close(self):
        """连接关闭回调"""
        logger.warning("私有 WebSocket 连接已关闭")
        self._connected = False
        self._is_logged_in = False

    async def close(self):
        """关闭网关"""
        await self.disconnect()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()
