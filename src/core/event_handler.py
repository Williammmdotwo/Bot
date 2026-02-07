"""
EventHandler - 事件处理器抽象基类

职责：
- 提供统一的事件处理接口
- 管理事件处理器注册
- 统一事件分发逻辑

设计原则：
- 模板方法模式：子类实现具体的事件处理器
- 注册模式：在初始化时自动注册所有处理器
- 类型安全：使用 EventType 确保事件类型正确
"""

from abc import ABC, abstractmethod
from typing import Callable, Dict, Optional
import logging

from .event_types import Event, EventType

logger = logging.getLogger(__name__)


class EventHandler(ABC):
    """
    事件处理器抽象基类

    所有需要处理事件的类都应该继承此类。

    特性：
    - 自动注册：在 __init__ 时调用 _register_handlers() 自动注册所有处理器
    - 统一分发：通过 handle() 方法统一分发事件
    - 灵活扩展：子类可以覆盖 register() 方法自定义注册逻辑

    使用示例：
        >>> class MyEventHandler(EventHandler):
        >>>     def _register_handlers(self):
        >>>         self.register(EventType.TICK, self.on_tick)
        >>>         self.register(EventType.ORDER_FILLED, self.on_order_filled)
        >>>
        >>>     async def on_tick(self, event: Event):
        >>>         pass
        >>>
        >>>     async def on_order_filled(self, event: Event):
        >>>         pass
    """

    def __init__(self):
        """
        初始化事件处理器

        自动调用 _register_handlers() 注册所有事件处理器
        """
        self._handlers: Dict[EventType, Callable] = {}
        self._register_handlers()

        # 记录已注册的处理器
        logger.debug(
            f"EventHandler 初始化完成: "
            f"已注册 {len(self._handlers)} 个处理器"
        )

    @abstractmethod
    def _register_handlers(self):
        """
        注册事件处理器（子类必须实现）

        子类应该在此方法中调用 self.register() 注册所有需要的事件处理器。

        使用示例：
            >>> def _register_handlers(self):
            >>>     self.register(EventType.TICK, self.on_tick)
            >>>     self.register(EventType.ORDER_FILLED, self.on_order_filled)
        """
        pass

    def register(self, event_type: EventType, handler: Optional[Callable]):
        """
        注册事件处理器

        Args:
            event_type: 事件类型
            handler: 处理器函数（async function）

        使用示例：
            >>> self.register(EventType.TICK, self.on_tick)
        """
        if handler is None:
            logger.warning(
                f"事件处理器为 None: {event_type.value}，跳过注册"
            )
            return

        self._handlers[event_type] = handler
        logger.debug(
            f"✅ 注册事件处理器: {event_type.value} -> {handler.__name__}"
        )

    def unregister(self, event_type: EventType):
        """
        注销事件处理器

        Args:
            event_type: 事件类型

        使用示例：
            >>> self.unregister(EventType.TICK)
        """
        if event_type in self._handlers:
            del self._handlers[event_type]
            logger.debug(
                f"❌ 注销事件处理器: {event_type.value}"
            )

    def has_handler(self, event_type: EventType) -> bool:
        """
        检查是否注册了指定事件的处理器

        Args:
            event_type: 事件类型

        Returns:
            bool: 是否已注册

        使用示例：
            >>> if handler.has_handler(EventType.TICK):
            ...     print("已注册 TICK 处理器")
        """
        return event_type in self._handlers

    def get_handler(self, event_type: EventType) -> Optional[Callable]:
        """
        获取指定事件的处理器

        Args:
            event_type: 事件类型

        Returns:
            Callable: 处理器函数，如果未注册返回 None

        使用示例：
            >>> handler = self.get_handler(EventType.TICK)
            >>> if handler:
            ...     print(f"处理器名称: {handler.__name__}")
        """
        return self._handlers.get(event_type)

    def list_handlers(self) -> Dict[EventType, Callable]:
        """
        列出所有已注册的事件处理器

        Returns:
            Dict[EventType, Callable]: 事件类型到处理器的映射

        使用示例：
            >>> handlers = self.list_handlers()
            >>> for event_type, handler in handlers.items():
            ...     print(f"{event_type.value} -> {handler.__name__}")
        """
        return self._handlers.copy()

    async def handle(self, event: Event):
        """
        统一处理入口

        根据事件类型自动分发到对应的处理器。

        Args:
            event: 事件对象

        使用示例：
            >>> await handler.handle(event)
        """
        event_type = event.type

        # 查找处理器
        handler = self._handlers.get(event_type)

        if not handler:
            logger.debug(
                f"⚠️ 未找到处理器: {event_type.value}"
            )
            return

        try:
            # 调用处理器
            await handler(event)

        except Exception as e:
            logger.error(
                f"❌ 事件处理器异常: {event_type.value}, "
                f"handler={handler.__name__}, error={e}",
                exc_info=True
            )

    async def handle_with_fallback(self, event: Event, fallback: Optional[Callable] = None):
        """
        处理事件（带降级策略）

        如果未找到处理器，调用 fallback 函数。

        Args:
            event: 事件对象
            fallback: 降级处理器（可选）

        使用示例：
            >>> async def on_unknown(event):
            ...     print(f"未知事件: {event.type.value}")
            >>>
            >>> await handler.handle_with_fallback(event, on_unknown)
        """
        event_type = event.type
        handler = self._handlers.get(event_type)

        if handler:
            # 有处理器，正常处理
            await handler(event)
        elif fallback:
            # 无处理器，调用降级函数
            await fallback(event)
        else:
            # 无处理器，也无降级函数
            logger.debug(
                f"⚠️ 未找到处理器（无降级）: {event_type.value}"
            )

    def clear_handlers(self):
        """
        清空所有事件处理器

        警告：此方法会清空所有已注册的处理器，谨慎使用！

        使用示例：
            >>> handler.clear_handlers()
        """
        self._handlers.clear()
        logger.warning("⚠️ 所有事件处理器已清空")


# ========== 便捷函数 ==========

def register_handler(event_type: EventType):
    """
    便捷装饰器：注册事件处理器

    与 EventHandler.register 功能相同，提供装饰器形式。

    使用示例：
        >>> class MyEventHandler(EventHandler):
        >>>     @register_handler(EventType.TICK)
        >>>     async def on_tick(self, event: Event):
        >>>         pass
    """
    def decorator(handler_func):
        def wrapper(self, *args, **kwargs):
            self.register(event_type, handler_func)
            return handler_func
        return wrapper
    return decorator


# ========== 测试代码 ==========

if __name__ == '__main__':
    # 测试事件处理器

    class TestEventHandler(EventHandler):
        def _register_handlers(self):
            self.register(EventType.TICK, self.on_tick)
            self.register(EventType.ORDER_FILLED, self.on_order_filled)

        async def on_tick(self, event: Event):
            print(f"处理 TICK 事件: {event.data}")

        async def on_order_filled(self, event: Event):
            print(f"处理 ORDER_FILLED 事件: {event.data}")

    # 创建事件处理器
    handler = TestEventHandler()

    # 列出所有处理器
    print("\n已注册的处理器:")
    for event_type, handler_func in handler.list_handlers().items():
        print(f"  - {event_type.value} -> {handler_func.__name__}")

    # 测试事件处理
    import asyncio

    async def test():
        # 创建测试事件
        tick_event = Event(
            type=EventType.TICK,
            data={'symbol': 'DOGE-USDT-SWAP', 'price': 0.085}
        )

        fill_event = Event(
            type=EventType.ORDER_FILLED,
            data={'order_id': '12345', 'filled_size': 100}
        )

        # 处理事件
        await handler.handle(tick_event)
        await handler.handle(fill_event)

    asyncio.run(test())
