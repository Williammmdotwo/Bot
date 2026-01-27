"""
网关基类 (Base Gateway)

定义所有网关（REST、WebSocket）的统一接口。

设计原则：
- 统一接口，支持多交易所
- 抽象化，屏蔽底层实现细节
- 类型安全，使用标准事件格式
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from ..core.event_types import Event, EventType
from ..core.event_bus import EventPriority  # 🔥 [P0 修复] 导入优先级常量


class BaseGateway(ABC):
    """
    网关基类

    所有网关（REST、WebSocket）都必须继承此类并实现抽象方法。

    Example:
        >>> class MyOkxGateway(BaseGateway):
        ...     async def connect(self):
        ...         pass
        ...     async def disconnect(self):
        ...         pass
    """

    def __init__(self, name: str, event_bus=None):
        """
        初始化网关

        Args:
            name (str): 网关名称（如 "okx_rest", "okx_ws_public"）
            event_bus: 事件总线实例（可选）
        """
        self.name = name
        self._event_bus = event_bus
        self._connected = False

    @abstractmethod
    async def connect(self) -> bool:
        """
        连接网关

        Returns:
            bool: 连接是否成功
        """
        pass

    @abstractmethod
    async def disconnect(self):
        """断开连接"""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """
        检查连接状态

        Returns:
            bool: 是否已连接
        """
        pass

    async def publish_event(self, event: Event, priority: int = EventPriority.TICK):
        """
        发布事件到事件总线（支持优先级）

        Args:
            event (Event): 要发布的事件
            priority (int): 优先级（默认 TICK 优先级）
        """
        if self._event_bus:
            self._event_bus.put_nowait(event, priority=priority)

    def set_event_bus(self, event_bus):
        """
        设置事件总线

        Args:
            event_bus: 事件总线实例
        """
        self._event_bus = event_bus


class RestGateway(BaseGateway):
    """
    REST 网关基类

    定义 REST API 的标准接口。
    """

    @abstractmethod
    async def get_balance(self, currency: str = "USDT") -> Dict[str, Any]:
        """
        获取账户余额

        Args:
            currency (str): 货币符号（如 "USDT"）

        Returns:
            dict: 余额信息
        """
        pass

    @abstractmethod
    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取持仓信息

        Args:
            symbol (str): 交易对（可选，None 表示获取所有）

        Returns:
            list: 持仓列表
        """
        pass

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        size: float,
        price: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        下单

        Args:
            symbol (str): 交易对
            side (str): 方向（buy/sell）
            order_type (str): 订单类型（market/limit/ioc）
            size (float): 数量
            price (float): 价格（limit/ioc 订单必需）
            **kwargs: 其他参数

        Returns:
            dict: 订单响应
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """
        撤单

        Args:
            order_id (str): 订单 ID
            symbol (str): 交易对

        Returns:
            dict: 撤单响应
        """
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """
        查询订单状态

        Args:
            order_id (str): 订单 ID
            symbol (str): 交易对

        Returns:
            dict: 订单状态
        """
        pass

    @abstractmethod
    async def get_kline(
        self,
        symbol: str,
        interval: str = "1m",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取 K线数据

        Args:
            symbol (str): 交易对
            interval (str): 周期（1m, 5m, 1h, 1d）
            limit (int): 数量限制

        Returns:
            list: K线数据列表
        """
        pass

    @abstractmethod
    async def get_instruments(
        self,
        inst_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取交易对信息（动态加载交易对配置）

        Args:
            inst_type (str): 合约类型（如 "SWAP" 永续合约，None 表示全部）

        Returns:
            list: 交易对信息列表，每个元素包含：
                - instId: 交易对 ID（如 "BTC-USDT-SWAP"）
                - lotSz: 数量精度
                - minSz: 最小下单数量
                - tickSz: 价格精度
                - state: 交易状态（live, suspend, etc.）
        """
        pass


class WebSocketGateway(BaseGateway):
    """
    WebSocket 网关基类

    定义 WebSocket 的标准接口。
    """

    @abstractmethod
    async def subscribe(self, channels: List[str], symbol: Optional[str] = None):
        """
        订阅频道

        Args:
            channels (list): 频道列表（如 ["tick", "order", "position"]）
            symbol (str): 交易对（可选）
        """
        pass

    @abstractmethod
    async def unsubscribe(self, channels: List[str], symbol: Optional[str] = None):
        """
        取消订阅

        Args:
            channels (list): 频道列表
            symbol (str): 交易对（可选）
        """
        pass

    async def on_message(self, message: Dict[str, Any]):
        """
        收到消息时的回调（子类实现）

        Args:
            message (dict): WebSocket 消息
        """
        pass

    async def on_error(self, error: Exception):
        """
        错误回调（子类实现）

        Args:
            error (Exception): 错误对象
        """
        pass

    async def on_close(self):
        """连接关闭回调（子类实现）"""
        pass
