"""
Data Manager - 工具类模块

此模块包含数据管理的辅助工具类
- cache_manager: 缓存管理
- service_degradation: 服务降级处理
"""

from .cache_manager import CacheManager
from .service_degradation import ServiceDegradationHandler

__all__ = [
    'CacheManager',
    'ServiceDegradationHandler'
]
