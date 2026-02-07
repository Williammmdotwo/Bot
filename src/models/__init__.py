"""
Models - 数据模型包

提供标准化的数据类，替代散乱的字典结构。
"""

from .market_data import OrderBook, TickData, Signal

__all__ = [
    'OrderBook',
    'TickData',
    'Signal',
]
