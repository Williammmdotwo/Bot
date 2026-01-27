"""
Book Parser - 处理 Order Book 数据

负责解析 OKX 的 Book WebSocket 消息，推送到事件总线。
"""

import logging
from typing import Optional, Dict, Any
from ....core.event_types import Event, EventType

logger = logging.getLogger(__name__)


class BookParser:
    """
    Order Book 数据解析器

    负责：
    - 解析 Order Book 数据
    - 推送 BOOK_EVENT 事件到事件总线
    """

    def __init__(self, symbol: str, event_bus):
        """
        初始化 Book Parser

        Args:
            symbol (str): 交易对
            event_bus: 事件总线实例
        """
        self.symbol = symbol
        self.event_bus = event_bus

    async def process(self, data: dict) -> Optional[Dict[str, Any]]:
        """
        处理 Order Book 数据

        Args:
            data (dict): 解析后的 JSON 数据，格式：{"arg": {"channel": "books", "instId": "BTC-USDT-SWAP"}, "data": [...]}

        Returns:
            Optional[Dict[str, Any]]: 处理后的数据，返回 None 或标准化的 Order Book 数据
        """
        try:
            # 取 book 数据
            book_data = data.get("data", [])

            if not isinstance(book_data, list) or len(book_data) == 0:
                logger.debug(f"Book 数据为空或格式不正确: {book_data}")
                return None

            # 取最新的订单簿数据
            book = book_data[0]  # OKX 返回的是数组，取第一个

            # 更新买单和卖单
            bids = book.get('bids', [])
            asks = book.get('asks', [])

            # 只保留前5档（足够用于 Maker 策略）
            best_bid = 0.0
            best_ask = 0.0

            # 买一价（买单第一档的价格）
            if bids and len(bids) > 0:
                best_bid = float(bids[0][0])

            # 卖一价（卖单第一档的价格）
            if asks and len(asks) > 0:
                best_ask = float(asks[0][0])

            # 高频订单簿数据不记录详细日志
            logger.debug(
                f"Order Book: best_bid={best_bid:.6f}, best_ask={best_ask:.6f}, "
                f"bids={len(bids)}, asks={len(asks)}"
            )

            # 推送 BOOK_EVENT 事件到事件总线
            if self.event_bus:
                from ....core.event_types import Event, EventType

                event = Event(
                    type=EventType.BOOK_EVENT,
                    data={
                        'symbol': self.symbol,
                        'best_bid': best_bid,
                        'best_ask': best_ask,
                        'bids': bids[:5] if bids else [],
                        'asks': asks[:5] if asks else []
                    },
                    source="book_parser"
                )
                await self.event_bus.put_nowait(event)

        except Exception as e:
            logger.error(f"Book 处理异常: {e}, 原始数据: {data}", exc_info=True)
            return None
