"""
Market Data Models - 市场数据模型

提供标准化的数据类，替代散乱的字典结构。

设计原则：
- 类型安全：使用 dataclass 提供类型提示
- 数据验证：提供验证方法
- 便捷方法：提供常用计算方法
- 向后兼容：提供 to_dict() 和 from_dict() 方法
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
import time


@dataclass
class OrderBook:
    """
    订单簿数据

    特性：
    - 类型安全：使用 dataclass 提供类型提示
    - 便捷方法：提供常用查询方法
    - 向后兼容：支持与字典互转

    使用示例：
        >>> order_book = OrderBook(
        ...     symbol='DOGE-USDT-SWAP',
        ...     bids=[(0.0849, 1000), (0.0848, 500)],
        ...     asks=[(0.0850, 1000), (0.0851, 500)],
        ...     timestamp=int(time.time() * 1000)
        ... )
        >>>
        >>> best_bid = order_book.get_best_bid()
        >>> best_ask = order_book.get_best_ask()
        >>> spread = order_book.get_spread()
    """

    symbol: str
    bids: List[Tuple[float, float]]  # [(price, size), ...]
    asks: List[Tuple[float, float]]
    timestamp: int

    def get_best_bid(self) -> float:
        """
        获取最佳买价（最高买价）

        Returns:
            float: 最佳买价，如果没有买单返回 0.0
        """
        return self.bids[0][0] if self.bids else 0.0

    def get_best_ask(self) -> float:
        """
        获取最佳卖价（最低卖价）

        Returns:
            float: 最佳卖价，如果没有卖单返回 0.0
        """
        return self.asks[0][0] if self.asks else 0.0

    def get_mid_price(self) -> float:
        """
        获取中间价

        Returns:
            float: (best_bid + best_ask) / 2，如果没有数据返回 0.0
        """
        if not self.bids or not self.asks:
            return 0.0
        return (self.get_best_bid() + self.get_best_ask()) / 2.0

    def get_spread(self) -> float:
        """
        获取点差（绝对值）

        Returns:
            float: 点差，如果没有数据返回 0.0
        """
        return self.get_best_ask() - self.get_best_bid()

    def get_spread_pct(self) -> float:
        """
        获取点差（百分比）

        Returns:
            float: 点差百分比，如果没有数据返回 0.0
        """
        mid_price = self.get_mid_price()
        if mid_price <= 0:
            return 0.0
        return self.get_spread() / mid_price

    def get_depth(self, side: str, levels: int = 3) -> float:
        """
        获取盘口深度

        Args:
            side: 方向（'buy' 或 'sell'）
            levels: 档位数（默认 3 档）

        Returns:
            float: 深度（USDT），如果没有数据返回 0.0
        """
        if side not in ['buy', 'sell']:
            raise ValueError(f"无效的方向: {side}，必须是 'buy' 或 'sell'")

        orders = self.bids if side == 'buy' else self.asks
        return sum(size for _, size in orders[:levels])

    def get_depth_at_price(self, side: str, price: float, levels: int = 5) -> float:
        """
        获取指定价格以下的盘口深度

        Args:
            side: 方向（'buy' 或 'sell'）
            price: 价格
            levels: 档位数

        Returns:
            float: 深度
        """
        if side not in ['buy', 'sell']:
            raise ValueError(f"无效的方向: {side}，必须是 'buy' 或 'sell'")

        orders = self.bids if side == 'buy' else self.asks
        if side == 'buy':
            # 买单：价格 >= price 的深度
            return sum(size for p, size in orders[:levels] if p >= price)
        else:
            # 卖单：价格 <= price 的深度
            return sum(size for p, size in orders[:levels] if p <= price)

    def is_valid(self) -> bool:
        """
        验证订单簿数据是否有效

        Returns:
            bool: 是否有效
        """
        return (
            len(self.symbol) > 0 and
            len(self.bids) > 0 and
            len(self.asks) > 0 and
            self.get_best_bid() > 0 and
            self.get_best_ask() > 0 and
            self.get_best_ask() > self.get_best_bid()  # 卖价必须高于买价
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（兼容旧代码）

        Returns:
            dict: 字典形式的数据
        """
        return {
            'symbol': self.symbol,
            'bids': self.bids,
            'asks': self.asks,
            'timestamp': self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OrderBook':
        """
        从字典创建（兼容旧代码）

        Args:
            data: 字典数据

        Returns:
            OrderBook: 订单簿对象
        """
        return cls(
            symbol=data.get('symbol', ''),
            bids=data.get('bids', []),
            asks=data.get('asks', []),
            timestamp=data.get('timestamp', 0)
        )

    def copy(self, **kwargs) -> 'OrderBook':
        """
        创建副本（支持部分字段更新）

        Args:
            **kwargs: 要更新的字段

        Returns:
            OrderBook: 新的订单簿对象
        """
        return OrderBook(
            symbol=kwargs.get('symbol', self.symbol),
            bids=kwargs.get('bids', self.bids.copy()),
            asks=kwargs.get('asks', self.asks.copy()),
            timestamp=kwargs.get('timestamp', self.timestamp)
        )


@dataclass
class TickData:
    """
    Tick 数据

    特性：
    - 类型安全：使用 dataclass 提供类型提示
    - 数据验证：提供验证方法
    - 便捷计算：自动计算交易价值

    使用示例：
        >>> tick = TickData(
        ...     symbol='DOGE-USDT-SWAP',
        ...     price=0.085,
        ...     size=1000,
        ...     side='buy',
        ...     timestamp=int(time.time() * 1000),
        ...     volume_usdt=85.0
        ... )
        >>>
        >>> tick_dict = tick.to_dict()
    """

    symbol: str
    price: float
    size: float
    side: str  # 'buy' or 'sell'
    timestamp: int
    volume_usdt: float
    order_book: Optional[OrderBook] = None

    def is_valid(self) -> bool:
        """
        验证 Tick 数据是否有效

        Returns:
            bool: 是否有效
        """
        return (
            len(self.symbol) > 0 and
            self.price > 0 and
            self.size > 0 and
            self.side in ['buy', 'sell'] and
            self.timestamp > 0 and
            self.volume_usdt >= 0
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（兼容旧代码）

        Returns:
            dict: 字典形式的数据
        """
        return {
            'symbol': self.symbol,
            'price': self.price,
            'size': self.size,
            'side': self.side,
            'timestamp': self.timestamp,
            'volume_usdt': self.volume_usdt,
            'order_book': self.order_book.to_dict() if self.order_book else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TickData':
        """
        从字典创建（兼容旧代码）

        Args:
            data: 字典数据

        Returns:
            TickData: Tick 数据对象
        """
        # 计算交易价值（如果未提供）
        price = float(data.get('price', 0))
        size = float(data.get('size', 0))
        volume_usdt = data.get('volume_usdt', price * size)

        # 转换订单簿（如果提供）
        order_book_dict = data.get('order_book')
        order_book = OrderBook.from_dict(order_book_dict) if order_book_dict else None

        return cls(
            symbol=data.get('symbol', ''),
            price=price,
            size=size,
            side=data.get('side', '').lower(),
            timestamp=data.get('timestamp', 0),
            volume_usdt=float(volume_usdt),
            order_book=order_book
        )


@dataclass
class Signal:
    """
    交易信号

    特性：
    - 类型安全：使用 dataclass 提供类型提示
    - 数据验证：提供验证方法
    - 扩展字段：支持任意元数据

    使用示例：
        >>> signal = Signal(
        ...     symbol='DOGE-USDT-SWAP',
        ...     direction='buy',
        ...     signal_ratio=10.0,
        ...     ema_boost=1.2,
        ...     trend='bullish',
        ...     timestamp=int(time.time() * 1000),
        ...     reason='强烈买入信号'
        ... )
        >>>
        >>> if signal.is_valid():
        ...     print(f"有效信号: {signal.direction}")
    """

    symbol: str
    direction: str  # 'buy' or 'sell'
    signal_ratio: float  # 不平衡比率
    ema_boost: float
    trend: str  # 'bullish', 'bearish', 'neutral'
    timestamp: int
    reason: str = ""  # 信号原因
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据

    def is_valid(self) -> bool:
        """
        验证信号有效性

        Returns:
            bool: 是否有效
        """
        return (
            len(self.symbol) > 0 and
            self.direction in ['buy', 'sell'] and
            self.signal_ratio > 0 and
            self.ema_boost > 0 and
            self.trend in ['bullish', 'bearish', 'neutral'] and
            self.timestamp > 0
        )

    def is_strong(self, threshold: float = 10.0) -> bool:
        """
        判断是否为强信号

        Args:
            threshold: 信号比率阈值（默认 10.0）

        Returns:
            bool: 是否为强信号
        """
        return self.signal_ratio >= threshold

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（兼容旧代码）

        Returns:
            dict: 字典形式的数据
        """
        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'signal_ratio': self.signal_ratio,
            'ema_boost': self.ema_boost,
            'trend': self.trend,
            'timestamp': self.timestamp,
            'reason': self.reason,
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Signal':
        """
        从字典创建（兼容旧代码）

        Args:
            data: 字典数据

        Returns:
            Signal: 信号对象
        """
        return cls(
            symbol=data.get('symbol', ''),
            direction=data.get('direction', '').lower(),
            signal_ratio=float(data.get('signal_ratio', 0)),
            ema_boost=float(data.get('ema_boost', 1.0)),
            trend=data.get('trend', 'neutral').lower(),
            timestamp=data.get('timestamp', 0),
            reason=data.get('reason', ''),
            metadata=data.get('metadata', {})
        )

    def copy(self, **kwargs) -> 'Signal':
        """
        创建副本（支持部分字段更新）

        Args:
            **kwargs: 要更新的字段

        Returns:
            Signal: 新的信号对象
        """
        return Signal(
            symbol=kwargs.get('symbol', self.symbol),
            direction=kwargs.get('direction', self.direction),
            signal_ratio=kwargs.get('signal_ratio', self.signal_ratio),
            ema_boost=kwargs.get('ema_boost', self.ema_boost),
            trend=kwargs.get('trend', self.trend),
            timestamp=kwargs.get('timestamp', self.timestamp),
            reason=kwargs.get('reason', self.reason),
            metadata=kwargs.get('metadata', self.metadata.copy())
        )


# ========== 便捷函数 ==========

def create_tick_from_raw(symbol: str, price: float, size: float, side: str,
                      timestamp: Optional[int] = None,
                      order_book: Optional[OrderBook] = None) -> TickData:
    """
    从原始数据创建 Tick（便捷函数）

    Args:
        symbol: 交易对
        price: 价格
        size: 数量
        side: 方向
        timestamp: 时间戳（可选，默认当前时间）
        order_book: 订单簿（可选）

    Returns:
        TickData: Tick 数据对象
    """
    if timestamp is None:
        timestamp = int(time.time() * 1000)

    volume_usdt = price * size

    return TickData(
        symbol=symbol,
        price=price,
        size=size,
        side=side.lower(),
        timestamp=timestamp,
        volume_usdt=volume_usdt,
        order_book=order_book
    )


def create_order_book_from_raw(symbol: str, bids: List[Tuple[float, float]],
                            asks: List[Tuple[float, float]],
                            timestamp: Optional[int] = None) -> OrderBook:
    """
    从原始数据创建订单簿（便捷函数）

    Args:
        symbol: 交易对
        bids: 买单 [(price, size), ...]
        asks: 卖单 [(price, size), ...]
        timestamp: 时间戳（可选，默认当前时间）

    Returns:
        OrderBook: 订单簿对象
    """
    if timestamp is None:
        timestamp = int(time.time() * 1000)

    return OrderBook(
        symbol=symbol,
        bids=bids,
        asks=asks,
        timestamp=timestamp
    )


# ========== 测试代码 ==========

if __name__ == '__main__':
    # 测试 OrderBook
    order_book = OrderBook(
        symbol='DOGE-USDT-SWAP',
        bids=[(0.0849, 1000), (0.0848, 500)],
        asks=[(0.0850, 1000), (0.0851, 500)],
        timestamp=int(time.time() * 1000)
    )

    print(f"最佳买价: {order_book.get_best_bid()}")
    print(f"最佳卖价: {order_book.get_best_ask()}")
    print(f"点差: {order_book.get_spread()}")
    print(f"点差百分比: {order_book.get_spread_pct()*100:.4f}%")
    print(f"买单深度（3档）: {order_book.get_depth('buy', 3)}")
    print(f"卖单深度（3档）: {order_book.get_depth('sell', 3)}")
    print(f"是否有效: {order_book.is_valid()}")

    # 测试 TickData
    tick = TickData(
        symbol='DOGE-USDT-SWAP',
        price=0.085,
        size=1000,
        side='buy',
        timestamp=int(time.time() * 1000),
        volume_usdt=85.0
    )

    print(f"\nTick 是否有效: {tick.is_valid()}")

    # 测试 Signal
    signal = Signal(
        symbol='DOGE-USDT-SWAP',
        direction='buy',
        signal_ratio=10.0,
        ema_boost=1.2,
        trend='bullish',
        timestamp=int(time.time() * 1000),
        reason='强烈买入信号'
    )

    print(f"\n信号是否有效: {signal.is_valid()}")
    print(f"是否强信号: {signal.is_strong()}")
