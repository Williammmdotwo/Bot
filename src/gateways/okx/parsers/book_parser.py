"""
Book Parser - 处理 Order Book 数据

负责解析 OKX 的 Book WebSocket 消息，推送到事件总线。

🔥 [防御性解析] 使用 Pydantic 模型验证数据格式
- 即使 OKX API 增加额外字段，也不会崩溃
- 自动类型转换和范围检查
- 清晰的验证错误信息
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from ....core.event_types import Event, EventType
from ..models import BookLevelModel, BookDataModel

logger = logging.getLogger(__name__)


class BookParser:
    """
    Order Book 数据解析器（Pydantic 版本）

    负责：
    - 解析 Order Book 数据（使用 Pydantic 验证）
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
        处理 Order Book 数据（Pydantic 验证版本）

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

            # 🔥 [防御性解析] 使用 Pydantic 验证
            try:
                # 将原始数据转换为 Pydantic 模型
                book_model = BookDataModel(
                    asks=book.get('asks', []),
                    bids=book.get('bids', []),
                    timestamp=book.get('ts', '')
                )
            except Exception as e:
                # Pydantic 验证失败，记录警告但继续处理
                logger.warning(f"⚠️ [BookParser] Pydantic 验证失败: {e}, 原始数据: {book}")
                return None

            # 提取已验证的数据
            bids = book_model.bids[:5]  # 只保留前5档
            asks = book_model.asks[:5]  # 只保留前5档

            # 转换为标准化格式 [[price, size], ...]
            standardized_bids: List[Tuple[float, float]] = []
            standardized_asks: List[Tuple[float, float]] = []

            for level in bids:
                standardized_bids.append((level.price, level.size))

            for level in asks:
                standardized_asks.append((level.price, level.size))

            # 买一价（买单第一档的价格）
            best_bid = standardized_bids[0][0] if standardized_bids else 0.0
            # 卖一价（卖单第一档的价格）
            best_ask = standardized_asks[0][0] if standardized_asks else 0.0

            # 高频订单簿数据不记录详细日志
            logger.debug(
                f"Order Book: best_bid={best_bid:.6f}, best_ask={best_ask:.6f}, "
                f"bids={len(standardized_bids)}, asks={len(standardized_asks)}"
            )

            # 推送 BOOK_EVENT 事件到事件总线（标准化后的数据）
            if self.event_bus:
                from ....core.event_types import Event, EventType

                event = Event(
                    type=EventType.BOOK_EVENT,
                    data={
                        'symbol': self.symbol,
                        'best_bid': best_bid,
                        'best_ask': best_ask,
                        'bids': standardized_bids,  # ✅ 标准化格式：[(price_float, size_float), ...]
                        'asks': standardized_asks   # ✅ 标准化格式：[(price_float, size_float), ...]
                    },
                    source="book_parser"
                )
                self.event_bus.put_nowait(event)

        except Exception as e:
            logger.error(f"Book 处理异常: {e}, 原始数据: {data}", exc_info=True)
            return None
