"""
Ticker Parser - 处理 Ticker 数据

负责解析 OKX 的 Ticker WebSocket 消息，推送到事件总线。
"""

import logging
from typing import Optional, Dict, Any
from ....core.event_types import Event, EventType

logger = logging.getLogger(__name__)


class TickerParser:
    """
    Ticker 数据解析器

    负责：
    - 解析 Ticker 数据
    - 推送 TICK 事件到事件总线
    """

    def __init__(self, symbol: str, event_bus):
        """
        初始化 Ticker Parser

        Args:
            symbol (str): 交易对
            event_bus: 事件总线实例
        """
        self.symbol = symbol
        self.event_bus = event_bus

    async def process(self, data: dict) -> Optional[Dict[str, Any]]:
        """
        处理 Ticker 数据

        Args:
            data (dict): 解析后的 JSON 数据

        Returns:
            Optional[Dict[str, Any]]: 处理后的数据，返回 None 或标准化的 Ticker 数据
        """
        try:
            # 提取 ticker 数据
            ticker_data = data.get("data", {})

            if not ticker_data:
                logger.debug(f"Ticker 数据为空: {data}")
                return None

            # 解析价格、成交量等
            price = None
            volume = None
            timestamp = None

            if isinstance(ticker_data, dict):
                price = float(ticker_data.get("last", "0"))
                volume = float(ticker_data.get("volCcy24h", "0"))
                timestamp = int(ticker_data.get("ts", "0"))

            # 验证数据完整性
            if price <= 0:
                logger.error(f"Ticker 价格无效: {price}")
                return None

            if timestamp <= 0:
                logger.error(f"Ticker 时间戳无效: {timestamp}")
                return None

            # 推送 TICK 事件到事件总线
            if self.event_bus:
                from ....core.event_types import Event, EventType

                event = Event(
                    type=EventType.TICK,
                    data={
                        'symbol': self.symbol,
                        'price': price,
                        'size': volume,
                        'timestamp': timestamp
                    },
                    source="ticker_parser"
                )
                await self.event_bus.put_nowait(event)

            logger.debug(f"已处理 Ticker 数据: price={price:.4f}, volume={volume:.2f}")

        except Exception as e:
            logger.error(f"处理 Ticker 数据异常: {e}", exc_info=True)
            return None
