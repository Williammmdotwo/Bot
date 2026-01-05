"""
WebSocket Tick 数据流处理器

本模块提供实时市场数据流处理功能，用于高频交易场景。

核心功能：
- 使用 aiohttp 连接 OKX Public WebSocket
- 订阅 trades 频道，实时接收成交数据
- 自动过滤小单（< 5000 USDT）
- 自动重连机制（指数退避）

设计原则：
- 不使用 ccxt 或 websockets 库，直接使用 aiohttp
- 高性能，避免不必要的对象拷贝
- 完整的错误处理和日志记录
"""

import asyncio
import json
import logging
from typing import Optional, Callable
import aiohttp
from aiohttp import ClientSession, WSMessage, ClientError
from .memory_state import MarketState

logger = logging.getLogger(__name__)


class TickStream:
    """
    WebSocket Tick 数据流处理器

    使用 aiohttp 连接 OKX Public WebSocket，实时接收 trades 数据，
    并更新 MarketState。

    Example:
        >>> market_state = MarketState()
        >>> stream = TickStream(
        ...     symbol="BTC-USDT-SWAP",
        ...     market_state=market_state
        ... )
        >>> await stream.start()
        >>> await asyncio.sleep(60)  # 运行 60 秒
        >>> await stream.stop()
    """

    # OKX Public WebSocket URL
    WS_URL_PRODUCTION = "wss://ws.okx.com:8443/ws/v5/public"
    WS_URL_DEMO = "wss://wspap.okx.com:8443/ws/v5/public"

    # 大单阈值（USDT）
    WHALE_THRESHOLD = 5000.0

    def __init__(
        self,
        symbol: str,
        market_state: MarketState,
        use_demo: bool = False,
        ws_url: Optional[str] = None,
        reconnect_enabled: bool = True,
        base_reconnect_delay: float = 1.0,
        max_reconnect_delay: float = 60.0,
        max_reconnect_attempts: int = 10
    ):
        """
        初始化 Tick 流处理器

        Args:
            symbol (str): 交易对（如：BTC-USDT-SWAP）
            market_state (MarketState): 市场状态管理器
            use_demo (bool): 是否使用模拟盘环境，默认为 False
            ws_url (Optional[str]): WebSocket URL，默认根据环境自动选择
            reconnect_enabled (bool): 是否启用自动重连，默认为 True
            base_reconnect_delay (float): 基础重连延迟（秒），默认为 1.0
            max_reconnect_delay (float): 最大重连延迟（秒），默认为 60.0
            max_reconnect_attempts (int): 最大重连次数，默认为 10
        """
        self.symbol = symbol
        self.market_state = market_state
        self.use_demo = use_demo

        # 根据环境选择 WebSocket URL
        if ws_url:
            self.ws_url = ws_url
        else:
            self.ws_url = self.WS_URL_DEMO if use_demo else self.WS_URL_PRODUCTION

        self.reconnect_enabled = reconnect_enabled
        self.base_reconnect_delay = base_reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts

        # 连接状态
        self._session: Optional[ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._is_connected = False
        self._is_running = False
        self._reconnect_attempts = 0

        # 回调函数（可选）
        self._on_trade: Optional[Callable] = None
        self._on_whale: Optional[Callable] = None

        logger.info(
            f"TickStream 初始化: symbol={symbol}, ws_url={self.ws_url}, "
            f"环境={'模拟盘' if self.use_demo else '实盘'}"
        )

    def set_trade_callback(self, callback: Callable):
        """
        设置交易回调函数

        Args:
            callback (Callable): 交易回调函数，签名为 (price, size, side, timestamp)
        """
        self._on_trade = callback
        logger.debug("交易回调函数已设置")

    def set_whale_callback(self, callback: Callable):
        """
        设置大单回调函数

        Args:
            callback (Callable): 大单回调函数，签名为 (price, size, side, timestamp, usdt_value)
        """
        self._on_whale = callback
        logger.debug("大单回调函数已设置")

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

            logger.info(f"正在连接 WebSocket: {self.ws_url}")

            # 建立连接
            self._ws = await session.ws_connect(
                self.ws_url,
                receive_timeout=30.0  # 接收超时 30 秒
            )

            self._is_connected = True
            self._reconnect_attempts = 0

            logger.info(f"WebSocket 连接成功: {self.symbol}")

            # 订阅 trades 频道
            await self._subscribe_trades()

            return True

        except ClientError as e:
            logger.error(f"WebSocket 连接失败: {e}")
            return False
        except Exception as e:
            logger.error(f"WebSocket 连接异常: {e}")
            return False

    async def _subscribe_trades(self):
        """
        订阅 trades 频道

        发送订阅消息到 OKX WebSocket 服务器。
        """
        try:
            # 构造订阅消息
            subscribe_msg = {
                "op": "subscribe",
                "args": [{
                    "channel": "trades",
                    "instId": self.symbol
                }]
            }

            # 转换为 JSON 字符串（紧凑格式）
            json_str = json.dumps(subscribe_msg, separators=(',', ':'))

            # 添加调试日志
            logger.info(f"发送订阅消息: {json_str}")

            # 发送订阅消息
            await self._ws.send_str(json_str)

            logger.info(f"已发送订阅请求: {self.symbol}")

        except Exception as e:
            logger.error(f"订阅 trades 频道失败: {e}")
            raise

    async def _handle_message(self, message: WSMessage):
        """
        处理接收到的消息

        Args:
            message (WSMessage): WebSocket 消息对象
        """
        try:
            # 处理文本消息
            if message.type == aiohttp.WSMsgType.TEXT:
                # 添加调试日志
                logger.debug(f"收到文本消息: {message.data[:200]}...")
                data = json.loads(message.data)
                await self._process_data(data)

            # 处理错误消息
            elif message.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket 错误: {message.data}")
                self._is_connected = False

            # 处理关闭消息
            elif message.type == aiohttp.WSMsgType.CLOSED:
                logger.warning("WebSocket 连接已关闭")
                self._is_connected = False

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
            # 处理订阅响应
            if "event" in data:
                if data["event"] == "subscribe":
                    code = data.get("code")
                    # 添加完整的订阅响应日志
                    logger.info(f"收到订阅响应: {data}")
                    if code == "0":
                        logger.info(f"订阅成功: {data.get('arg', {})}")
                    elif code == "51000":
                        logger.error(f"订阅失败: 参数错误 - {data}")
                    else:
                        # 其他代码码可能是警告或信息，不视为失败
                        logger.warning(f"订阅响应: code={code}, msg={data.get('msg', '')}")
                elif data["event"] == "error":
                    logger.error(f"OKX API 错误: {data}")
                return

            # 处理交易数据
            if "data" in data and isinstance(data["data"], list):
                for trade_item in data["data"]:
                    self._process_trade(trade_item)

        except Exception as e:
            logger.error(f"数据处理异常: {e}")

    def _process_trade(self, trade_item: list):
        """
        处理单笔交易数据

        OKX trades 数据格式：
        [
            price,      # [0] 价格
            size,       # [1] 数量
            trade_id,    # [2] 交易ID
            timestamp,   # [3] 时间戳（毫秒）
            side         # [4] 方向（"buy" 或 "sell"）
        ]

        Args:
            trade_item (list): 交易数据数组
        """
        try:
            # 验证数据格式
            if not isinstance(trade_item, list) or len(trade_item) < 5:
                logger.debug(f"交易数据格式错误: {trade_item}")
                return

            # 解析数据
            price = float(trade_item[0])
            size = float(trade_item[1])
            timestamp = int(trade_item[3])
            side = trade_item[4]

            # 验证 side
            if side not in ["buy", "sell"]:
                logger.debug(f"无效的交易方向: {side}")
                return

            # 计算交易金额（USDT）
            usdt_value = price * size

            # 过滤小单
            if usdt_value < self.WHALE_THRESHOLD:
                logger.debug(
                    f"过滤小单: price={price}, size={size}, "
                    f"usdt={usdt_value:.2f}"
                )
                return

            # 更新市场状态
            self.market_state.update_trade(price, size, side, timestamp)

            # 调用回调函数
            if self._on_trade:
                try:
                    self._on_trade(price, size, side, timestamp)
                except Exception as e:
                    logger.error(f"交易回调函数异常: {e}")

            # 调用大单回调
            if self._on_whale and usdt_value >= self.WHALE_THRESHOLD:
                try:
                    self._on_whale(price, size, side, timestamp, usdt_value)
                except Exception as e:
                    logger.error(f"大单回调函数异常: {e}")

            # 记录大单
            if usdt_value >= self.WHALE_THRESHOLD:
                logger.info(
                    f"大单: price={price}, size={size}, "
                    f"side={side}, usdt={usdt_value:.2f}"
                )

        except (ValueError, IndexError) as e:
            logger.error(f"交易数据解析失败: {e}, data={trade_item}")
        except Exception as e:
            logger.error(f"交易处理异常: {e}")

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
        启动 Tick 流

        Example:
            >>> await stream.start()
            >>> await asyncio.sleep(60)
        """
        if self._is_running:
            logger.warning("Tick 流已在运行")
            return

        self._is_running = True
        logger.info("启动 Tick 流...")

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

        logger.info("Tick 流已启动")

    async def stop(self):
        """
        停止 Tick 流

        Example:
            >>> await stream.stop()
        """
        if not self._is_running:
            logger.warning("Tick 流未运行")
            return

        logger.info("停止 Tick 流...")
        self._is_running = False
        self._is_connected = False

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

        logger.info("Tick 流已停止")

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
            'symbol': self.symbol,
            'connected': self._is_connected,
            'running': self._is_running,
            'reconnect_attempts': self._reconnect_attempts,
            'ws_url': self.ws_url,
            'reconnect_enabled': self.reconnect_enabled
        }
