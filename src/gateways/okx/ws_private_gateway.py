"""
OKX 私有 WebSocket 网关 (Private WebSocket Gateway)

提供实时私有数据流，推送持仓和订单更新事件到事件总线。

关键特性：
- 继承 WsBaseGateway 基类（修复重连风暴）
- 推送 POSITION_UPDATE 和 ORDER_UPDATE 事件
- 自动重连机制（指数退避）
- 签名鉴权
- 登录确认机制（修复订阅失败问题）

设计原则：
- 使用标准事件格式
- 集成事件总线
- 保持原有 UserStream 功能

🔥 修复内容：
- 继承新的 WsBaseGateway，避免并发竞争
- 使用基类的自动重连和资源清理机制
- 防止 WebSocket 重连风暴
"""

import asyncio
import json
import logging
from typing import Optional
from aiohttp import WSMessage, ClientError
from ...core.event_types import Event, EventType
from .ws_base import WsBaseGateway
from .auth import OkxSigner

logger = logging.getLogger(__name__)


class OkxPrivateWsGateway(WsBaseGateway):
    """
    OKX 私有 WebSocket 网关（修复版）

    实时接收持仓和订单推送，推送标准事件到事件总线。
    继承自 WsBaseGateway，自动获得：
    - 并发连接保护（asyncio.Lock）
    - 指数退避重连机制
    - 资源自动清理
    - 心跳保活

    Example:
        >>> gateway = OkxPrivateWsGateway(
        ...     api_key="your_api_key",
        ...     secret_key="your_secret",
        ...     passphrase="your_passphrase",
        ...     use_demo=True,
        ...     event_bus=event_bus
        ... )
        >>> await gateway.connect()
        >>> await asyncio.sleep(60)
        >>> await gateway.disconnect()
    """

    # OKX Private WebSocket URL
    WS_URL_PRODUCTION = "wss://ws.okx.com:8443/ws/v5/private"
    # ⚠️ 修复：移除 ?brokerId=9999 参数，使用标准模拟盘 URL
    # 旧的: "wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999"
    # 新的 (标准模拟盘): "wss://wspap.okx.com:8443/ws/v5/private"
    WS_URL_DEMO = "wss://wspap.okx.com:8443/ws/v5/private"

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
        # 根据 env 选择 URL
        if ws_url:
            final_url = ws_url
        else:
            if use_demo:
                final_url = self.WS_URL_DEMO
            else:
                final_url = self.WS_URL_PRODUCTION

        # 调用父类初始化
        super().__init__(
            name="okx_ws_private",
            ws_url=final_url,
            event_bus=event_bus
        )

        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.use_demo = use_demo

        # 登录和订阅状态
        self._is_logged_in = False
        self._login_completed = False
        self._subscribe_completed = False

        logger.info(
            f"OkxPrivateWsGateway 初始化: use_demo={use_demo}, "
            f"ws_url={final_url}"
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
        logger.info("⏹ 停止私有 WebSocket...")
        # 委托给基类（自动清理所有资源）
        await super().disconnect()

    # is_connected() 已由基类实现，无需重写

    # subscribe() 已由 _subscribe_channels 实现，无需重写

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

                # 使用基类的 send_message 方法
                await self.send_message(json.dumps(unsubscribe_msg, separators=(',', ':')))

                logger.info(f"🔕 已取消订阅: {channel}")

        except Exception as e:
            logger.error(f"取消订阅失败: {e}")

    # _wait_for_login 已废弃，登录确认在 _on_message 中处理

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

            logger.info(f"🔐 发送登录包 (Unix TS={timestamp})")

            # 使用基类的 send_message 方法
            await self.send_message(json.dumps(login_msg, separators=(',', ':')))

            logger.info("✅ 登录包已发送，等待服务器确认...")

        except Exception as e:
            logger.error(f"❌ 发送登录包失败: {e}")
            raise

    async def _subscribe_channels(self):
        """
        登录成功后订阅频道
        """
        try:
            logger.info("📡 准备订阅私有频道...")

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

            # 使用基类的 send_message 方法
            await self.send_message(json.dumps(positions_subscribe_msg, separators=(',', ':')))
            logger.info("✅ [订阅请求] positions 频道订阅请求已发送")

            await self.send_message(json.dumps(orders_subscribe_msg, separators=(',', ':')))
            logger.info("✅ [订阅请求] orders 频道订阅请求已发送")

        except Exception as e:
            logger.error(f"❌ 订阅频道失败: {e}", exc_info=True)
            raise

    # 🔥 重写基类的 _on_message 方法
    async def _on_message(self, message: WSMessage):
        """
        收到消息时的回调（基类调用）

        Args:
            message (WSMessage): WebSocket 消息
        """
        try:
            if message.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(message.data)
                await self._process_data(data)

            elif message.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"❌ 私有 WebSocket 错误: {message.data}")

            elif message.type == aiohttp.WSMsgType.CLOSED:
                logger.warning("⚠️ 私有 WebSocket 连接已关闭")
                self._is_logged_in = False
                self._login_completed = False
                self._subscribe_completed = False

            else:
                logger.debug(f"未处理的消息类型: {message.type}")

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 解析失败: {e}")
        except Exception as e:
            logger.error(f"❌ 消息处理异常: {e}")

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
                    msg = data.get("msg", "")
                    if code == "0":
                        logger.info(f"✅ [登录成功] 服务器确认登录完成")
                        self._is_logged_in = True
                        self._login_completed = True
                        # 登录成功后订阅频道
                        await self._subscribe_channels()
                    else:
                        logger.error(f"❌ [登录失败] code={code}, msg={msg}")
                        self._is_logged_in = False
                        self._login_completed = False

                elif data["event"] == "subscribe":
                    channel = data.get("arg", {}).get("channel")
                    code = data.get("code")
                    if code == "0":
                        logger.info(f"✅ [订阅确认] 频道 '{channel}' 订阅成功")
                        self._subscribe_completed = True
                    else:
                        logger.error(f"❌ [订阅失败] 频道 '{channel}' 订阅失败: code={code}")

                elif data["event"] == "error":
                    logger.error(f"❌ [WebSocket 错误] {data}")

            # 处理持仓推送
            if "data" in data and "arg" in data:
                arg = data["arg"]
                channel = arg.get("channel")

                if channel == "positions":
                    positions = data.get("data", [])
                    logger.debug(f"📊 收到持仓推送: {len(positions)} 个")

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
                    logger.debug(f"📋 收到订单推送: {len(orders)} 个")

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
            logger.error(f"❌ 数据处理异常: {e}, 原始数据: {data}", exc_info=True)

    # 🔥 新增：重写 _on_connected 钩子，连接成功后自动登录和订阅
    async def _on_connected(self):
        """
        连接成功后的钩子（自动登录和订阅）
        """
        logger.info("✅ WebSocket 连接成功，准备登录...")
        try:
            # 发送登录包
            await self._send_login()
        except Exception as e:
            logger.error(f"❌ 登录失败: {e}")

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
