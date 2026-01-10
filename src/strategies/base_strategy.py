"""
策略基类 (Base Strategy)

定义所有策略的通用接口和基础功能。

设计原则：
- 策略只负责交易逻辑，不关心数据源
- 通过事件总线接收市场数据
- 纯粹的策略实现，不包含网络通信
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """
    策略基类

    所有策略都必须继承此类并实现抽象方法。

    Attributes:
        symbol (str): 交易对
        mode (str): 策略模式（PRODUCTION/DEV）

    Example:
        >>> class MyStrategy(BaseStrategy):
        ...     async def on_tick(self, price, size, side, timestamp):
        ...         # 策略逻辑
        ...         if price > 100:
        ...             await self.buy()
    """

    def __init__(self, symbol: str, mode: str = "PRODUCTION"):
        """
        初始化策略

        Args:
            symbol (str): 交易对
            mode (str): 策略模式（PRODUCTION/DEV）
        """
        self.symbol = symbol
        self.mode = mode.upper()
        self._enabled = True

    @abstractmethod
    async def on_tick(self, price: float, size: float = 0.0, side: str = "", timestamp: int = 0):
        """
        处理 Tick 数据

        这是策略的核心方法，每个 Tick 都会调用。

        Args:
            price (float): 当前价格
            size (float): 交易数量
            side (str): 交易方向
            timestamp (int): 时间戳（毫秒）
        """
        pass

    @abstractmethod
    async def on_signal(self, signal: Dict[str, Any]):
        """
        处理策略信号

        Args:
            signal (dict): 策略信号，包含信号类型、数量等
        """
        pass

    def enable(self):
        """启用策略"""
        self._enabled = True
        logger.info(f"策略 {self.__class__.__name__} 已启用")

    def disable(self):
        """禁用策略"""
        self._enabled = False
        logger.info(f"策略 {self.__class__.__name__} 已禁用")

    def is_enabled(self) -> bool:
        """检查策略是否启用"""
        return self._enabled

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取策略统计信息

        Returns:
            dict: 统计数据
        """
        return {
            'strategy': self.__class__.__name__,
            'symbol': self.symbol,
            'mode': self.mode,
            'enabled': self._enabled
        }

    def reset_statistics(self):
        """重置统计信息"""
        pass
