"""
OKX 数据模型

使用 Pydantic 进行数据验证和类型安全
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class TradeModel(BaseModel):
    """交易数据模型"""
    instId: str = Field(..., description="交易对")
    tradeId: str = Field(..., description="交易ID")
    price: float = Field(..., gt=0, description="成交价格")
    size: float = Field(..., gt=0, description="成交数量")
    side: str = Field(..., description="买卖方向")
    timestamp: int = Field(..., ge=0, description="时间戳")

    class Config:
        extra = 'allow'  # 允许额外字段（向下兼容）


class BookLevelModel(BaseModel):
    """订单簿档位模型"""
    price: float = Field(..., gt=0)
    size: float = Field(..., gt=0)
    orders: int = Field(default=0, ge=0, description="订单数量")
    depth: int = Field(default=0, ge=0, description="深度档位")


class BookDataModel(BaseModel):
    """订单簿数据模型"""
    asks: List[BookLevelModel] = Field(default_factory=list)
    bids: List[BookLevelModel] = Field(default_factory=list)
    timestamp: str = Field(default="")

    @validator('asks', 'bids', pre=True)
    def validate_book_levels(cls, v):
        """验证订单簿档位"""
        if not isinstance(v, list):
            logger.warning(f"⚠️ [BookParser] 订单簿必须是列表，实际类型: {type(v)}")
            return []
        return v


class TickerModel(BaseModel):
    """行情数据模型"""
    instId: str = Field(..., description="交易对")
    last: str = Field(..., description="最新价")
    bid: str = Field(default="")
    ask: str = Field(default="")
    open24h: str = Field(default="")
    high24h: str = Field(default="")
    low24h: str = Field(default="")
    vol24h: str = Field(default="")
    volCcy24h: str = Field(default="")

    class Config:
        extra = 'allow'  # 允许额外字段


class CandleModel(BaseModel):
    """K线数据模型"""
    instId: str = Field(..., description="交易对")
    candle: List[str] = Field(..., description="[ts, o, h, l, c, vol, volCcy]")

    @validator('candle')
    def validate_candle_length(cls, v):
        """验证 K线数据长度"""
        if not isinstance(v, list) or len(v) < 6:
            logger.warning(f"⚠️ [CandleParser] K线数据格式错误: {v}")
            return []
        return v
