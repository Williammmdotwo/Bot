"""
持久化模块

提供多种持久化后端支持：
- JsonPersistenceAdapter: JSON 文件持久化（轻量级）
- 未来可扩展：Redis、SQLite 等其他后端
"""

from .persistence_adapter import PersistenceAdapter, JsonPersistenceAdapter

__all__ = [
    'PersistenceAdapter',
    'JsonPersistenceAdapter',
]
