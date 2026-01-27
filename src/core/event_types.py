"""
事件类型定义 (Event Types)

定义系统中所有标准事件类型和数据格式。

设计原则：
- 标准化事件格式，确保模块间通信一致
- 类型安全，使用枚举和类定义
- 轻量级，避免序列化开销
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime


class EventType(Enum):
    """事件类型枚举"""

    # 市场数据事件
    TICK = "tick"                    # 单笔交易 Tick
    BAR = "bar"                      # K线数据（OHLCV）
    DEPTH = "depth"                   # 订单簿深度
    BOOK_EVENT = "book_event"         # 订单簿事件
    CANDLE_EVENT = "candle_event"     # K线事件

    # 账户事件
    POSITION_UPDATE = "position_update"   # 持仓更新
    BALANCE_UPDATE = "balance_update"     # 余额更新
    ORDER_UPDATE = "order_update"       # 订单状态更新
    ORDER_FILLED = "order_filled"       # 订单成交
    ORDER_CANCELLED = "order_cancelled"   # 订单取消
    ORDER_SUBMITTED = "order_submitted"   # 订单提交

    # 策略事件
    SIGNAL_BUY = "signal_buy"         # 买入信号
    SIGNAL_SELL = "signal_sell"       # 卖出信号
    SIGNAL_EXIT = "signal_exit"       # 出场信号

    # 系统事件
    ERROR = "error"                    # 错误事件
    WARNING = "warning"                # 警告事件
    INFO = "info"                     # 信息事件
    SHUTDOWN = "shutdown"              # 关闭事件


@dataclass
class Event:
    """
    标准事件格式

    所有模块间通信都使用此格式。

    Attributes:
        type (EventType): 事件类型
        data (dict): 事件数据（具体内容取决于事件类型）
        timestamp (datetime): 事件时间戳
        source (str): 事件来源（如 "ws_public", "rest_api", "strategy_vulture"）

    Example:
        >>> event = Event(
        ...     type=EventType.TICK,
        ...     data={'price': 50000.0, 'size': 0.1, 'side': 'buy'},
        ...     source="ws_public"
        ... )
    """
    type: EventType
    data: dict
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "unknown"


@dataclass
class TickEvent:
    """
    Tick 事件数据

    Attributes:
        symbol (str): 交易对
        price (float): 价格
        size (float): 数量
        side (str): 方向（buy/sell）
        trade_id (str): 交易 ID
        timestamp (datetime): 时间戳
    """
    symbol: str
    price: float
    size: float
    side: str
    trade_id: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class BarEvent:
    """
    K线事件数据

    Attributes:
        symbol (str): 交易对
        interval (str): 周期（1m, 5m, 1h, 1d）
        open (float): 开盘价
        high (float): 最高价
        low (float): 最低价
        close (float): 收盘价
        volume (float): 成交量
        timestamp (datetime): 时间戳
    """
    symbol: str
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: Optional[datetime] = None


@dataclass
class PositionEvent:
    """
    持仓更新事件

    Attributes:
        symbol (str): 交易对
        size (float): 持仓数量（正为多，负为空）
        entry_price (float): 开仓均价
        unrealized_pnl (float): 未实现盈亏
        leverage (int): 杠杆倍数
        timestamp (datetime): 时间戳
    """
    symbol: str
    size: float
    entry_price: float
    unrealized_pnl: float = 0.0
    leverage: int = 1
    timestamp: Optional[datetime] = None


@dataclass
class OrderEvent:
    """
    订单事件

    Attributes:
        order_id (str): 订单 ID
        symbol (str): 交易对
        side (str): 方向（buy/sell）
        order_type (str): 订单类型（market/limit/ioc）
        price (float): 价格
        size (float): 数量
        filled_size (float): 成交数量
        status (str): 状态（live/partially_filled/filled/cancelled）
        timestamp (datetime): 时间戳
    """
    order_id: str
    symbol: str
    side: str
    order_type: str
    price: float
    size: float
    filled_size: float = 0.0
    status: str = "live"
    timestamp: Optional[datetime] = None


@dataclass
class SignalEvent:
    """
    策略信号事件

    Attributes:
        strategy (str): 策略名称（如 "vulture", "sniper", "scalper_v1"）
        signal (str): 信号类型（BUY/SELL/EXIT）
        symbol (str): 交易对
        price (float): 触发价格
        size (float): 建议数量
        order_type (str): 建议订单类型（market/limit/ioc）
        stop_loss (Optional[float]): 止损价格
        take_profit (Optional[float]): 止盈价格
        confidence (float): 信号置信度（0.0-1.0）
        reasoning (str): 信号理由
        timestamp (datetime): 时间戳
    """
    strategy: str
    signal: str
    symbol: str
    price: float
    size: float
    order_type: str = "limit"
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    confidence: float = 1.0
    reasoning: str = ""
    timestamp: Optional[datetime] = None


@dataclass
class ErrorEvent:
    """
    错误事件

    Attributes:
        code (str): 错误码
        message (str): 错误消息
        source (str): 错误来源
        severity (str): 严重程度（error/warning/info）
        timestamp (datetime): 时间戳
        details (dict): 额外详情
    """
    code: str
    message: str
    source: str = "unknown"
    severity: str = "error"
    timestamp: Optional[datetime] = None
    details: dict = field(default_factory=dict)
