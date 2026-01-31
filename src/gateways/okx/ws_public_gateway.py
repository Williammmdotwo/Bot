"""
OKX 公共 WebSocket 网关（Parser 版本）

提供实时市场数据流，推送标准 TICK 事件到事件总线。

关键特性：
- 继承 WsBaseGateway 基类（修复重连风暴）
- 使用独立 Parser 处理数据（Trade、Ticker、Book、Candle）
- 推送 TICK 事件到事件总线
- 自动重连机制（指数退避）
- 心跳保活
- 并发连接保护（asyncio.Lock）
- 资源清理机制

修复内容：
- 继承新的 WsBaseGateway，避免并发竞争
- 使用 Parser 分离数据处理逻辑，降低耦合度
- 防止 WebSocket 重连风暴（指数退避）
- 保留所有关键逻辑（看门狗、心跳保活等）
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import aiohttp
from aiohttp import ClientSession, WSMessage, ClientError, ClientWebSocketResponse

from src.core.event_types import Event, EventType
from src.gateways.okx.ws_base import WsBaseGateway

# 导入 Parser
from .parsers.trade_parser import TradeParser
from .parsers.ticker_parser import TickerParser
from .parsers.book_parser import BookParser
from .parsers.candle_parser import CandleParser

logger = logging.getLogger(__name__)


class OkxPublicWsGateway(WsBaseGateway):
    """
    OKX 公共 WebSocket 网关（Parser 版本）

    实时接收市场数据流，推送标准 TICK 事件到事件总线。
    使用独立 Parser 处理数据（Trade、Ticker、Book、Candle），降低耦合度。
    """

    # OKX Public WebSocket URL
    WS_URL_PRODUCTION = "wss://ws.okx.com:8443/ws/v5/public"

    def __init__(self, symbol: str, ws_url: Optional[str] = None, event_bus=None):
        """
        初始化公共 WebSocket 网关

        Args:
            symbol (str): 交易对
            ws_url (str): WebSocket URL
            event_bus: 事件总线（可选）
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

        # 初始化 Parser（无状态）
        self.trade_parser = TradeParser(symbol, event_bus)
        self.ticker_parser = TickerParser(symbol, event_bus)
        self.book_parser = BookParser(symbol, event_bus)
        self.candle_parser = CandleParser(symbol, event_bus)

        # 订单簿深度数据（用于 Maker 策略）
        self._order_book = {
            'bids': [],  # 买单 [[price, size, ...], ...]
            'asks': []   # 卖单 [[price, size, ...], ...]
        }

        logger.info(
            f"OkxPublicWsGateway 初始化: symbol={symbol}, url={final_url}"
        )

    async def connect(self) -> bool:
        """
        连接到 WebSocket（委托给基类）

        Returns:
            bool: 是否连接成功
        """
        return await super().connect()

    async def disconnect(self):
        """
        断开 WebSocket 连接（委托给基类）
        """
        await super().disconnect()

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
                elif channel == 'candles':
                    args.append({
                        "channel": "candles",
                        "instId": self.symbol,
                        "instType": "SPOT"
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
                "args": [self.symbol]
            }

            json_str = json.dumps(unsubscribe_msg, separators=(',', ':'))

            # 使用基类的 send_message 方法
            await self.send_message(json_str)

            logger.info(f"已发送取消订阅请求: {self.symbol}")

        except Exception as e:
            logger.error(f"取消订阅失败: {e}")

    # 重写基类的 _on_message 方法，使用 Parser 分发数据
    async def _on_message(self, message: WSMessage):
        """
        收到消息时的回调（基类调用）

        分发消息给对应的 Parser 处理
        """
        try:
            if message.type == aiohttp.WSMsgType.TEXT:
                logger.debug(f"收到文本消息: {message.data[:200]}...")
                data = json.loads(message.data)

                # 检查是否为订阅响应
                if "event" in data:
                    if data["event"] == "subscribe":
                        logger.info(f"订阅成功: {data.get('arg', {})}")
                    elif data["event"] == "error":
                        logger.error(f"OKX API 错误: {data}")
                    return

                # 分发数据给对应的 Parser
                if "data" in data:
                    # 获取 channel
                    arg_data = data.get("arg", {})
                    channel = arg_data.get("channel", "")

                    # 根据 channel 分发给对应的 Parser
                    if channel == "trades":
                        await self.trade_parser.process(data)
                    elif channel == "books":
                        await self.book_parser.process(data)
                    elif channel == "candles":
                        await self.candle_parser.process(data)

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

    # 重写基类的 _on_connected 方法，订阅频道
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
