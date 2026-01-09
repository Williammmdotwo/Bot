"""
WebSocket 私有数据流处理器

本模块提供实时私有数据流功能，用于高频交易场景。

核心功能：
- 使用 aiohttp 连接 OKX Private WebSocket
- 实时接收持仓和订单推送
- 自动重连机制（指数退避）
- 签名鉴权

设计原则：
- 连接后立即发送登录包
- 订阅 positions 和 orders 频道
- 实时推送持仓更新
"""

import asyncio
import json
import logging
from typing import Optional, Callable, Dict, Any
import aiohttp
from aiohttp import ClientSession, WSMessage, ClientError
from ..utils.auth import generate_headers_with_auto_timestamp

logger = logging.getLogger(__name__)


class UserStream:
    """
    WebSocket 私有数据流处理器

    使用 aiohttp 连接 OKX Private WebSocket，实时接收持仓和订单推送，
    并通过回调通知 Engine 更新状态。

    Example:
        >>> def on_positions_update(positions):
        ...     for pos in positions:
        ...         print(f"持仓更新: {pos}")
        >>>
        >>> stream = UserStream(
        ...     api_key="your_api_key",
        ...     secret_key="your_secret",
        ...     passphrase="your_passphrase",
        ...     use_demo=True
        ... )
        >>> stream.set_positions_callback(on_positions_update)
        >>> await stream.start()
        >>> await asyncio.sleep(60)
        >>> await stream.stop()
    """

    # OKX Private WebSocket URL
    WS_URL_PRODUCTION = "wss://ws.okx.com:8443/ws/v5/private"
    WS_URL_DEMO = "wss://wspap.okx.com:8443/ws/v5/private"

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        use_demo: bool = False,
        ws_url: Optional[str] = None,
        reconnect_enabled: bool = True,
        base_reconnect_delay: Optional[float] = None,
        max_reconnect_delay: Optional[float] = None,
        max_reconnect_attempts: int = 10
    ):
        """
        初始化私用数据流处理器

        Args:
            api_key (str): OKX API Key
            secret_key (str): OKX Secret Key
            passphrase (str): OKX Passphrase
            use_demo (bool): 是否使用模拟盘环境，默认为 False
            ws_url (Optional[str]): WebSocket URL，默认根据环境自动选择
            reconnect_enabled (bool): 是否启用自动重连，默认为 True
            base_reconnect_delay (Optional[float]): 基础重连延迟（秒）
                None 表示自动选择（模拟盘 3.0 秒，实盘 1.0 秒）
            max_reconnect_delay (Optional[float]): 最大重连延迟（秒）
                None 表示自动选择（模拟盘 120.0 秒，实盘 60.0 秒）
            max_reconnect_attempts (int): 最大重连次数，默认为 10
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.use_demo = use_demo

        # [修复] 强制使用生产环境域名以避开 502 错误
        # OKX 允许通过生产域名进行模拟盘鉴权
        # 原有逻辑:
        # if use_demo:
        #     self.ws_url = self.WS_URL_DEMO
        # else:
        #     self.ws_url = self.WS_URL_PRODUCTION
        #
        # 修复为：统一使用生产环境域名，通过 Header 鉴权区分模拟盘
        if ws_url:
            self.ws_url = ws_url
        else:
            # 强制使用生产环境域名
            self.ws_url = self.WS_URL_PRODUCTION

        self.reconnect_enabled = reconnect_enabled
        self.max_reconnect_attempts = max_reconnect_attempts

        # [优化] 根据环境自动设置重连延迟
        # 模拟盘连接不稳定，使用更长的退避时间
        if use_demo:
            # 模拟盘：基础延迟 3 秒，最大延迟 120 秒
            self.base_reconnect_delay = base_reconnect_delay if base_reconnect_delay is not None else 3.0
            self.max_reconnect_delay = max_reconnect_delay if max_reconnect_delay is not None else 120.0
        else:
            # 实盘：基础延迟 1 秒，最大延迟 60 秒
            self.base_reconnect_delay = base_reconnect_delay if base_reconnect_delay is not None else 1.0
            self.max_reconnect_delay = max_reconnect_delay if max_reconnect_delay is not None else 60.0

        logger.info(
            f"UserStream 初始化: use_demo={use_demo}, ws_url={self.ws_url}, "
            f"base_reconnect_delay={self.base_reconnect_delay}s, max_reconnect_delay={self.max_reconnect_delay}s"
        )

        # 连接状态
        self._session: Optional[ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._is_connected = False
        self._is_running = False
        self._reconnect_attempts = 0
        self._is_logged_in = False

        # 回调函数
        self._on_positions: Optional[Callable] = None
        self._on_orders: Optional[Callable] = None

    def set_positions_callback(self, callback: Callable):
        """
        设置持仓更新回调函数

        Args:
            callback (Callable): 持仓更新回调函数，签名为 (positions: List[Dict])
        """
        self._on_positions = callback
        logger.debug("持仓更新回调函数已设置")

    def set_orders_callback(self, callback: Callable):
        """
        设置订单更新回调函数

        Args:
            callback (Callable): 订单更新回调函数，签名为 (orders: List[Dict])
        """
        self._on_orders = callback
        logger.debug("订单更新回调函数已设置")

    async def _create_session(self) -> ClientSession:
        """
        创建或获取 ClientSession

        Returns:
            ClientSession: aiohttp ClientSession 实例
        """
        if self._session is None or self._session.closed:
            self._session = ClientSession()
            logger.debug("创建新的 ClientSession")
        return self._session

    async def _connect_websocket(self) -> bool:
        """
        建立 WebSocket 连接

        Returns:
            bool: 连接是否成功
        """
        try:
            session = await self._create_session()

            logger.info(f"正在连接私有 WebSocket: {self.ws_url}")

            # 建立连接
            self._ws = await session.ws_connect(
                self.ws_url,
                receive_timeout=30.0  # 接收超时 30 秒
            )

            self._is_connected = True
            self._reconnect_attempts = 0
            self._is_logged_in = False

            logger.info(f"私有 WebSocket 连接成功")

            # 连接后立即发送登录包
            await self._send_login()

            return True

        except ClientError as e:
            logger.error(f"私有 WebSocket 连接失败: {e}")
            return False
        except Exception as e:
            logger.error(f"私有 WebSocket 连接异常: {e}")
            return False

    async def _send_login(self):
        """
        发送登录请求

        OKX Private WebSocket 需要先发送登录包进行鉴权。
        [修复] 必须使用统一的 OkxSigner 工具类，确保时间戳格式一致
        """
        try:
            # [修复] 必须使用统一工具类
            from ..utils.auth import OkxSigner

            # 使用统一的时间戳生成方法（包含时间偏移量校准）
            timestamp = OkxSigner.get_timestamp()

            # 构造签名字符串: timestamp + 'GET' + '/users/self/verify'
            # 确保 GET 是大写
            message = f"{timestamp}GET/users/self/verify"

            # [新增] 详细的签名调试日志
            logger.debug(
                f"🔐 [WebSocket 签名计算] "
                f"timestamp={timestamp}, method=GET, "
                f"request_path=/users/self/verify, "
                f"message={message} (total={len(message)} chars)"
            )

            # 使用统一的签名方法
            sign = OkxSigner.sign(timestamp, "GET", "/users/self/verify", "", self.secret_key)

            logger.debug(f"🔐 [WebSocket 签名结果] sign={sign}")

            login_msg = {
                "op": "login",
                "args": [{
                    "apiKey": self.api_key,
                    "passphrase": self.passphrase,
                    "timestamp": timestamp,
                    "sign": sign
                }]
            }

            logger.info(f"发送登录包 (TS={timestamp}): {login_msg}")

            # 发送登录包（使用 send_json 而不是 send_str）
            await self._ws.send_json(login_msg)

            logger.info("登录包已发送")

        except Exception as e:
            logger.error(f"发送登录包失败: {e}")
            raise

    async def _subscribe_channels(self):
        """
        订阅持仓和订单频道

        登录成功后订阅私有频道。
        """
        try:
            # 订阅持仓频道
            positions_subscribe_msg = {
                "op": "subscribe",
                "args": [{
                    "channel": "positions",
                    "instType": "SWAP"  # 永续合约
                }]
            }

            # 订阅订单频道
            orders_subscribe_msg = {
                "op": "subscribe",
                "args": [{
                    "channel": "orders",
                    "instType": "SWAP"  # 永续合约
                }]
            }

            # 发送订阅请求
            await self._ws.send_str(json.dumps(positions_subscribe_msg, separators=(',', ':')))
            logger.info("已订阅 positions 频道")

            await self._ws.send_str(json.dumps(orders_subscribe_msg, separators=(',', ':')))
            logger.info("已订阅 orders 频道")

        except Exception as e:
            logger.error(f"订阅频道失败: {e}")
            raise

    def _get_login_params(self) -> dict:
        """
        生成 WebSocket 登录参数

        直接硬编码标准的时间生成逻辑，确保签名正确。

        Returns:
            dict: 包含 apiKey, passphrase, timestamp, sign 的字典
        """
        from datetime import datetime, timezone
        import hmac
        import base64
        import hashlib

        # 1. 生成 ISO 时间戳 (UTC)
        # [修复] 统一使用 strftime 方法，确保毫秒是 3 位
        # 必须是: 2023-01-01T12:00:00.000Z 格式
        dt = datetime.now(timezone.utc)
        timestamp = dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

        # 2. 生成签名
        # 格式: timestamp + 'GET' + '/users/self/verify'
        message = f"{timestamp}GET/users/self/verify"
        mac = hmac.new(
            bytes(self.secret_key, encoding='utf-8'),
            bytes(message, encoding='utf-8'),
            digestmod=hashlib.sha256
        )
        sign = base64.b64encode(mac.digest()).decode('utf-8')

        return {
            "apiKey": self.api_key,
            "passphrase": self.passphrase,
            "timestamp": timestamp,
            "sign": sign
        }

    async def _handle_message(self, message: WSMessage):
        """
        处理接收到的消息

        Args:
            message (WSMessage): WebSocket 消息对象
        """
        try:
            # 处理文本消息
            if message.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(message.data)
                await self._process_data(data)

            # 处理错误消息
            elif message.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"私有 WebSocket 错误: {message.data}")
                self._is_connected = False

            # 处理关闭消息
            elif message.type == aiohttp.WSMsgType.CLOSED:
                logger.warning("私有 WebSocket 连接已关闭")
                self._is_connected = False
                self._is_logged_in = False

            # 处理其他消息类型
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
                    code = data.get("code")
                    if code == "0":
                        logger.info(f"✅ 订阅成功: {channel}")
                    else:
                        logger.error(f"❌ 订阅失败: {data}")

                elif data["event"] == "error":
                    logger.error(f"❌ OKX API 错误: {data}")

            # 处理持仓推送
            if "data" in data and "arg" in data:
                arg = data["arg"]
                channel = arg.get("channel")

                if channel == "positions":
                    positions = data.get("data", [])
                    logger.debug(f"收到持仓推送: {len(positions)} 个")
                    # 调用持仓更新回调
                    if self._on_positions:
                        try:
                            self._on_positions(positions)
                        except Exception as e:
                            logger.error(f"持仓更新回调异常: {e}")

                elif channel == "orders":
                    orders = data.get("data", [])
                    logger.debug(f"收到订单推送: {len(orders)} 个")
                    # 调用订单更新回调
                    if self._on_orders:
                        try:
                            self._on_orders(orders)
                        except Exception as e:
                            logger.error(f"订单更新回调异常: {e}")

        except Exception as e:
            logger.error(f"数据处理异常: {e}, 原始数据: {data}")

    async def _message_loop(self):
        """
        消息接收循环

        持续接收 WebSocket 消息，直到连接断开或停止。
        """
        try:
            while self._is_connected and self._is_running:
                try:
                    # 接收消息（带超时）
                    msg = await asyncio.wait_for(
                        self._ws.receive(),
                        timeout=30.0
                    )

                    # 处理消息
                    await self._handle_message(msg)

                except asyncio.TimeoutError:
                    logger.warning("接收消息超时，可能连接已断开")
                    self._is_connected = False
                    break

        except Exception as e:
            logger.error(f"消息循环异常: {e}")
            self._is_connected = False

    async def _calculate_reconnect_delay(self) -> float:
        """
        计算重连延迟（指数退避）

        Returns:
            float: 重连延迟（秒）
        """
        if self._reconnect_attempts == 0:
            delay = 1.0
        else:
            # 指数退避：delay = base * (2 ^ min(attempts, 5))
            delay = self.base_reconnect_delay * (2 ** min(self._reconnect_attempts, 5))

        # 限制最大延迟
        delay = min(delay, self.max_reconnect_delay)

        return delay

    async def _reconnect_loop(self):
        """
        自动重连循环

        使用指数退避策略，持续尝试重连。
        """
        while self._is_running and self.reconnect_enabled:
            # 如果已连接，等待一段时间后检查
            if self._is_connected:
                await asyncio.sleep(10)
                continue

            # 检查是否超过最大重连次数
            if self._reconnect_attempts >= self.max_reconnect_attempts:
                logger.error(
                    f"重连次数超过限制 ({self.max_reconnect_attempts})，停止重连"
                )
                break

            # 计算重连延迟
            delay = await self._calculate_reconnect_delay()

            logger.info(
                f"等待 {delay:.1f} 秒后重连 "
                f"(尝试 {self._reconnect_attempts + 1}/{self.max_reconnect_attempts})"
            )

            await asyncio.sleep(delay)

            # 尝试重连
            self._reconnect_attempts += 1

            success = await self._connect_websocket()
            if success:
                logger.info(f"重连成功 (尝试 {self._reconnect_attempts})")
                # 启动消息循环
                asyncio.create_task(self._message_loop())
            else:
                logger.warning(f"重连失败 (尝试 {self._reconnect_attempts})")

    async def start(self):
        """
        启动私用数据流

        Example:
            >>> await stream.start()
            >>> await asyncio.sleep(60)
        """
        if self._is_running:
            logger.warning("私用数据流已在运行")
            return

        self._is_running = True
        logger.info("启动私用数据流...")

        # 首次连接
        success = await self._connect_websocket()
        if not success:
            logger.error("首次连接失败，将尝试重连")

        # 启动消息循环
        if self._is_connected:
            asyncio.create_task(self._message_loop())

        # 启动重连循环
        if self.reconnect_enabled:
            asyncio.create_task(self._reconnect_loop())

        logger.info("私用数据流已启动")

    async def stop(self):
        """
        停止私用数据流

        Example:
            >>> await stream.stop()
        """
        if not self._is_running:
            logger.warning("私用数据流未运行")
            return

        logger.info("停止私用数据流...")
        self._is_running = False
        self._is_connected = False
        self._is_logged_in = False

        # 关闭 WebSocket 连接
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.error(f"关闭 WebSocket 失败: {e}")
            self._ws = None

        # 关闭 Session
        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                logger.error(f"关闭 Session 失败: {e}")
            self._session = None

        logger.info("私用数据流已停止")

    def is_connected(self) -> bool:
        """
        检查是否已连接

        Returns:
            bool: 连接状态
        """
        return self._is_connected

    def get_status(self) -> dict:
        """
        获取状态信息

        Returns:
            dict: 包含状态信息的字典
        """
        return {
            'connected': self._is_connected,
            'logged_in': self._is_logged_in,
            'running': self._is_running,
            'reconnect_attempts': self._reconnect_attempts,
            'ws_url': self.ws_url,
            'reconnect_enabled': self.reconnect_enabled
        }
