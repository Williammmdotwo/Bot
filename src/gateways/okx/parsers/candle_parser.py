"""
Candle Parser - 处理 K线数据

负责解析 OKX 的 Candle WebSocket 消息，推送到事件总线。
"""

import logging
from typing import Optional, Dict, Any
from ....core.event_types import Event, EventType

logger = logging.getLogger(__name__)


class CandleParser:
    """
    Candle 数据解析器

    负责：
    - 解析 Candle 数据
    - 推送 CANDLE_EVENT 事件到事件总线
    """

    def __init__(self, symbol: str, event_bus):
        """
        初始化 Candle Parser

        Args:
            symbol (str): 交易对
            event_bus: 事件总线实例
        """
        self.symbol = symbol
        self.event_bus = event_bus

    async def process(self, data: dict) -> Optional[Dict[str, Any]]:
        """
        处理 Candle 数据

        Args:
            data (dict): 解析后的 JSON 数据，格式：{"arg": {"channel": "candles", "instId": "BTC-USDT-SWAP"}, "data": [...]}

        Returns:
            Optional[Dict[str, Any]]: 处理后的数据，返回 None 或标准化的 Candle 数据
        """
        try:
            # 提取 candles 数据数组
            candles_data = data.get("data", [])

            if not isinstance(candles_data, list) or len(candles_data) == 0:
                logger.debug(f"Candle 数据为空或格式不正确: {candles_data}")
                return None

            # 处理每根 K 线（限制最多处理 50 根）
            for candle_item in candles_data[:50]:
                timestamp = None
                open_price = None
                high_price = None
                low_price = None
                close_price = None
                volume = None

                # 解析数组格式（OKX 旧格式）
                if isinstance(candle_item, list) and len(candle_item) >= 6:
                    timestamp = int(candle_item[0])
                    open_price = float(candle_item[1])
                    high_price = float(candle_item[2])
                    low_price = float(candle_item[3])
                    close_price = float(candle_item[4])
                    volume = float(candle_item[5])

                # 解析字典格式（OKX 新格式，如果有的话）
                elif isinstance(candle_item, dict):
                    timestamp = int(candle_item.get("ts", "0"))
                    open_price = float(candle_item.get("o", "0"))
                    high_price = float(candle_item.get("h", "0"))
                    low_price = float(candle_item.get("l", "0"))
                    close_price = float(candle_item.get("c", "0"))
                    volume = float(candle_item.get("vol", "0"))

                # 验证数据完整性
                if timestamp is None or open_price is None or close_price is None:
                    logger.warning(f"Candle 数据不完整: {candle_item}")
                    continue

                # 推送 CANDLE_EVENT 事件到事件总线
                if self.event_bus:
                    from ....core.event_types import Event

                    event = Event(
                        type=EventType.CANDLE_EVENT,
                        data={
                            'symbol': self.symbol,
                            'timestamp': timestamp,
                            'open': open_price,
                            'high': high_price,
                            'low': low_price,
                            'close': close_price,
                            'volume': volume
                        },
                        source="candle_parser"
                    )
                    await self.event_bus.put_nowait(event)

            logger.debug(f"已处理 {len(candles_data[:50])} 根 K 线数据")

        except Exception as e:
            logger.error(f"处理 Candle 数据异常: {e}", exc_info=True)
            return None
