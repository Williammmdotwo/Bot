"""
WebSocket Tick 数据流处理器

本模块提供实时市场数据流处理功能，用于高频交易场景。

核心功能：
- 使用 aiohttp 连接 OKX Public WebSocket
- 订阅 trades 频道，实时接收成交数据
- 自动过滤小单（可配置阈值）
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

    # 合约面值（永续合约，1 张 = 1 币）
    CONTRACT_VAL = 1.0

    # 大单阈值（USDT）- 提高到 10000 USDT
    WHALE_THRESHOLD = 10000.0

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

        # 始终使用实盘 URL 获取 Public 数据（trades 频道）
        # 原因：OKX 模拟盘的 Public WebSocket 数据极少或断流
        # 只在 Private 数据（下单）时才区分实盘/模拟盘
        if ws_url:
            self.ws_url = ws_url
        else:
            self.ws_url = self.WS_URL_PRODUCTION  # 始终使用实盘 URL

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
                logger.debug(f"收到 {len(data['data'])} 笔交易数据")
                for trade_item in data["data"]:
                    self._process_trade(trade_item)
            else:
                logger.debug(f"未处理的数据格式: {list(data.keys())}")

        except Exception as e:
            logger.error(f"数据处理异常: {e}, 原始数据: {data}")

    def _process_trade(self, trade_item):
        """
        处理单笔交易数据

        OKX trades 数据格式（两种格式）：

        格式 1（数组格式）：
        [
            price,      # [0] 价格
            size,       # [1] 数量（张数）
            trade_id,    # [2] 交易ID
            timestamp,   # [3] 时间戳（毫秒）
            side         # [4] 方向（"buy" 或 "sell"）
        ]

        格式 2（字典格式）：
        {
            "px": "234.56",      # 价格
            "sz": "0.5",         # 数量（张数）
            "tradeId": "...",       # 交易ID
            "ts": "17044864000000", # 时间戳（毫秒）
            "side": "buy"          # 方向（"buy" 或 "sell"）
        }

        Args:
            trade_item: 交易数据（list 或 dict）
        """
        try:
            price = None
            size = None
            timestamp = None
            side = None

            # 尝试解析为字典格式（新格式）
            if isinstance(trade_item, dict):
                try:
                    # 强制转换为 float 类型（避免字符串比较问题）
                    price = float(trade_item.get("px", "0"))
                    size = float(trade_item.get("sz", "0"))
                    timestamp = int(trade_item.get("ts", "0"))
                    side = trade_item.get("side", "")
                except (ValueError, TypeError) as e:
                    logger.error(f"字典格式解析失败: {e}, data={trade_item}")
                    return

            # 尝试解析为数组格式（旧格式）
            elif isinstance(trade_item, list):
                if len(trade_item) < 5:
                    logger.debug(f"交易数据格式错误（数组长度不足）: {trade_item}")
                    return
                try:
                    # 强制转换为 float/int 类型
                    price = float(trade_item[0])
                    size = float(trade_item[1])
                    timestamp = int(trade_item[3])
                    side = str(trade_item[4])
                except (ValueError, IndexError, TypeError) as e:
                    logger.error(f"数组格式解析失败: {e}, data={trade_item}")
                    return
            else:
                logger.error(f"未知交易数据格式: {type(trade_item)}, data={trade_item}")
                return

            # 验证数据完整性
            if price is None or size is None or timestamp is None or side is None:
                logger.error(f"交易数据不完整: price={price}, size={size}, timestamp={timestamp}, side={side}")
                return

            # 验证 side
            if side not in ["buy", "sell"]:
                logger.error(f"无效的交易方向: {side}, data={trade_item}")
                return

            # 计算交易金额（USDT）- 使用合约面值
            # SOL-USDT-SWAP: 1 张 = 1 SOL
            usdt_value = price * size * self.CONTRACT_VAL

            # 添加每笔交易的日志（DEBUG 级别）
            logger.debug(f"收到成交: {price:.2f} x {size:.4f} = {usdt_value:.2f} USDT")

            # 过滤小单（只记录 DEBUG 日志）
            if usdt_value < self.WHALE_THRESHOLD:
                logger.debug(
                    f"过滤小单: price={price:.2f}, size={size:.4f}, "
                    f"usdt={usdt_value:.2f}"
                )

            # 更新市场状态（所有交易）
            self.market_state.update_trade(price, size, side, timestamp)

            # 调用交易回调（所有交易都会调用，用于更新 EMA）
            # 🔥 修复：必须 await 异步回调！
            if self._on_trade:
                try:
                    logger.debug("触发 Engine 回调")
                    # 🔥 关键修复：使用 asyncio.create_task 包装异步回调
                    asyncio.create_task(self._on_trade(price, size, side, timestamp))
                except Exception as e:
                    logger.error(f"交易回调函数异常: {e}")

            # 调用大单回调（只有大单才调用）
            if self._on_whale and usdt_value >= self.WHALE_THRESHOLD:
                try:
                    self._on_whale(price, size, side, timestamp, usdt_value)
                except Exception as e:
                    logger.error(f"大单回调函数异常: {e}")

            # 记录大单日志（只有超过 10000 USDT 才打印 INFO）
            if usdt_value >= self.WHALE_THRESHOLD:
                logger.info(
                    f"大单: price={price:.2f}, size={size:.4f}, "
                    f"side={side}, usdt={usdt_value:.2f}"
                )

        except Exception as e:
            logger.error(f"交易处理异常: {e}, 原始数据: {trade_item}", exc_info=True)

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

                    # 添加原始数据心跳打印（调试用）
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        print(f"DEBUG RAW: {msg.data[:200]}")

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
