"""
数据管理模块
提供市场数据获取、技术指标计算和数据处理功能

模块化架构：
- clients/: 网络客户端（REST, WebSocket）
- core/: 核心业务逻辑（数据获取、技术指标）
- utils/: 工具类（缓存、服务降级）
"""

from .main import DataHandler
from .clients import RESTClient, WebSocketClient
from .core import MarketDataFetcher, TechnicalIndicators
from .utils import CacheManager, ServiceDegradationManager

__all__ = [
    # 主类
    'DataHandler',

    # 网络客户端
    'RESTClient',
    'WebSocketClient',

    # 核心业务逻辑
    'MarketDataFetcher',
    'TechnicalIndicators',

    # 工具类
    'CacheManager',
    'ServiceDegradationManager'
]
