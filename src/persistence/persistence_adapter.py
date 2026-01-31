"""
持久化适配器接口

支持多种持久化后端（JSON、SQLite、Redis）
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import asyncio
import logging

logger = logging.getLogger(__name__)


class PersistenceAdapter(ABC):
    """持久化适配器抽象基类"""

    @abstractmethod
    async def save(self, key: str, value: Any) -> bool:
        """保存键值对"""
        pass

    @abstractmethod
    async def load(self, key: str) -> Optional[Any]:
        """加载键值"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除键"""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        pass


class JsonPersistenceAdapter(PersistenceAdapter):
    """JSON 文件持久化适配器（轻量级，适合单机部署）"""

    def __init__(self, storage_path: str = "data/state.json"):
        """
        初始化 JSON 持久化适配器

        Args:
            storage_path: 存储文件路径
        """
        self.storage_path = storage_path
        self._lock = asyncio.Lock()
        self._data: Dict[str, Any] = {}
        self._load_from_file()

        logger.info(f"💾 [Persistence] JSON 适配器初始化: {storage_path}")

    def _load_from_file(self):
        """从文件加载数据"""
        try:
            from pathlib import Path
            import json

            path = Path(self.storage_path)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
                logger.info(f"💾 [Persistence] 从文件加载状态: {len(self._data)} 个键")
            else:
                logger.debug(f"💾 [Persistence] 文件不存在，使用空状态: {storage_path}")
        except Exception as e:
            logger.error(f"💾 [Persistence] 加载文件失败: {e}")
            self._data = {}

    def _save_to_file(self):
        """保存数据到文件"""
        try:
            from pathlib import Path
            import json

            path = Path(self.storage_path)
            # 确保目录存在
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"💾 [Persistence] 保存文件失败: {e}")

    async def save(self, key: str, value: Any) -> bool:
        """保存键值对"""
        async with self._lock:
            self._data[key] = value
            self._save_to_file()
            return True

    async def load(self, key: str) -> Optional[Any]:
        """加载键值"""
        async with self._lock:
            return self._data.get(key)

    async def delete(self, key: str) -> bool:
        """删除键"""
        async with self._lock:
            if key in self._data:
                del self._data[key]
                self._save_to_file()
                return True
            return False

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        async with self._lock:
            return key in self._data
