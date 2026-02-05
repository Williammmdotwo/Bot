"""
OKX 数据模型

使用 Pydantic 进行数据验证和类型安全
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class TradeModel(BaseModel):
    """交易数据模型"""
    model_config = ConfigDict(extra='allow')  # 允许额外字段（向下兼容）
    instId: str = Field(..., description="交易对")
    tradeId: str = Field(..., description="交易ID")
    price: float = Field(..., gt=0, description="成交价格")
    size: float = Field(..., gt=0, description="成交数量")
    side: str = Field(..., description="买卖方向")
    timestamp: int = Field(..., ge=0, description="时间戳")


class BookLevelModel(BaseModel):
    """订单簿档位模型

    OKX 订单簿中 size 可以为 0（表示已成交的档位）
    """
    model_config = ConfigDict(extra='allow')  # 允许额外字段
    price: float = Field(..., gt=0, description="价格")
    size: float = Field(..., ge=0, description="数量（可以为 0，表示已成交）")
    orders: int = Field(default=0, ge=0, description="订单数量")
    depth: int = Field(default=0, ge=0, description="深度档位")


class BookDataModel(BaseModel):
    """订单簿数据模型"""
    asks: List[BookLevelModel] = Field(default_factory=list)
    bids: List[BookLevelModel] = Field(default_factory=list)
    timestamp: str = Field(default="")

    @field_validator('asks', 'bids', mode='before')
    @classmethod
    def validate_book_levels(cls, v):
        """
        验证并转换订单簿档位数据

        OKX WebSocket 返回格式: [[price_str, size_str, orders_str, depth_str], ...]
        需要转换为: [{"price": float, "size": float, "orders": int, "depth": int}, ...]
        """
        if not isinstance(v, list):
            logger.warning(f"⚠️ [BookParser] 订单簿必须是列表，实际类型: {type(v)}")
            return []

        converted_levels = []
        for item in v:
            try:
                # 处理列表格式: [price, size, orders, depth]
                if isinstance(item, list) and len(item) >= 2:
                    price = float(item[0]) if item[0] else 0.0
                    size = float(item[1]) if item[1] else 0.0
                    orders = int(item[2]) if len(item) > 2 and item[2] else 0
                    depth = int(item[3]) if len(item) > 3 and item[3] else 0

                    converted_levels.append({
                        'price': price,
                        'size': size,
                        'orders': orders,
                        'depth': depth
                    })
                # 处理字典格式（兼容其他可能的格式）
                elif isinstance(item, dict):
                    converted_levels.append(item)
            except (ValueError, TypeError, IndexError) as e:
                logger.debug(f"⚠️ [BookParser] 订单簿档位转换失败: {item}, 错误: {e}")
                continue

        return converted_levels


class TickerModel(BaseModel):
    """行情数据模型"""
    model_config = ConfigDict(extra='allow')  # 允许额外字段
    instId: str = Field(..., description="交易对")
    last: str = Field(..., description="最新价")
    bid: str = Field(default="")
    ask: str = Field(default="")
    open24h: str = Field(default="")
    high24h: str = Field(default="")
    low24h: str = Field(default="")
    vol24h: str = Field(default="")
    volCcy24h: str = Field(default="")


class CandleModel(BaseModel):
    """K线数据模型"""
    instId: str = Field(..., description="交易对")
    candle: List[str] = Field(..., description="[ts, o, h, l, c, vol, volCcy]")

    @field_validator('candle')
    @classmethod
    def validate_candle_length(cls, v):
        """验证 K线数据长度"""
        if not isinstance(v, list) or len(v) < 6:
            logger.warning(f"⚠️ [CandleParser] K线数据格式错误: {v}")
            return []
        return v
