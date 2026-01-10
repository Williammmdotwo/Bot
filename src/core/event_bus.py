"""
事件总线 (Event Bus)

轻量级异步事件总线，实现模块间的 Pub/Sub 通信。

设计原则：
- 轻量级，零依赖
- 异步设计，支持高并发
- 类型安全，使用标准事件格式
- 解耦模块间依赖
"""

import asyncio
import logging
from typing import Callable, Dict, List, Any, Optional
from collections import defaultdict
from .event_types import Event, EventType

logger = logging.getLogger(__name__)


class EventBus:
    """
    事件总线

    实现发布-订阅模式，用于模块间异步通信。

    Example:
        >>> event_bus = EventBus()
        >>>
        >>> # 订阅事件
        >>> async def on_tick(event: Event):
        ...     print(f"收到 Tick: {event.data}")
        >>> event_bus.register(EventType.TICK, on_tick)
        >>>
        >>> # 发布事件
        >>> event_bus.put(Event(
        ...     type=EventType.TICK,
        ...     data={'price': 50000.0},
        ...     source="test"
        ... ))
    """

    def __init__(self):
        """初始化事件总线"""
        self._handlers: Dict[EventType, List[Callable]] = defaultdict(list)
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._stats = {
            'published': 0,
            'processed': 0,
            'errors': 0
        }

    def register(self, event_type: EventType, handler: Callable):
        """
        注册事件处理器

        Args:
            event_type (EventType): 事件类型
            handler (Callable): 处理函数，签名：async def handler(event: Event)

        Example:
            >>> async def on_tick(event: Event):
            ...     print(event)
            >>> event_bus.register(EventType.TICK, on_tick)
        """
        self._handlers[event_type].append(handler)
        logger.debug(f"注册处理器: {event_type} -> {handler.__name__}")

    def unregister(self, event_type: EventType, handler: Callable):
        """
        取消注册事件处理器

        Args:
            event_type (EventType): 事件类型
            handler (Callable): 处理函数
        """
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
            logger.debug(f"取消注册处理器: {event_type} -> {handler.__name__}")

    async def put(self, event: Event):
        """
        发布事件（异步）

        将事件放入队列，由后台任务处理。

        Args:
            event (Event): 要发布的事件

        Example:
            >>> await event_bus.put(Event(
            ...     type=EventType.TICK,
            ...     data={'price': 50000.0},
            ...     source="test"
            ... ))
        """
        try:
            await self._queue.put(event)
            self._stats['published'] += 1

            # 只在 DEBUG 级别记录详细日志
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"发布事件: {event.type.value} from {event.source}")

        except asyncio.QueueFull:
            logger.error(f"事件队列已满，丢弃事件: {event.type}")
            self._stats['errors'] += 1

    def put_nowait(self, event: Event):
        """
        发布事件（非阻塞）

        Args:
            event (Event): 要发布的事件
        """
        try:
            self._queue.put_nowait(event)
            self._stats['published'] += 1

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"发布事件(非阻塞): {event.type.value} from {event.source}")

        except asyncio.QueueFull:
            logger.error(f"事件队列已满，丢弃事件: {event.type}")
            self._stats['errors'] += 1

    async def start(self):
        """启动事件总线（开始后台处理任务）"""
        if self._running:
            logger.warning("事件总线已在运行")
            return

        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("事件总线已启动")

    async def stop(self):
        """停止事件总线"""
        if not self._running:
            return

        self._running = False

        # 等待队列处理完成
        while not self._queue.empty():
            await asyncio.sleep(0.1)

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("事件总线已停止")

    async def _process_loop(self):
        """后台处理循环"""
        while self._running:
            try:
                # 获取事件（超时 1 秒，以便检查 _running 标志）
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._process_event(event)

            except asyncio.TimeoutError:
                continue

            except Exception as e:
                logger.error(f"事件处理循环错误: {e}", exc_info=True)

    async def _process_event(self, event: Event):
        """
        处理单个事件

        调用所有注册的处理器。

        Args:
            event (Event): 要处理的事件
        """
        handlers = self._handlers.get(event.type, [])

        if not handlers:
            logger.debug(f"无处理器注册: {event.type}")
            return

        # 调用所有处理器
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)

                self._stats['processed'] += 1

            except Exception as e:
                logger.error(
                    f"处理器错误 ({handler.__name__}): {e}",
                    exc_info=True
                )
                self._stats['errors'] += 1

                # 发布错误事件（避免无限循环）
                if event.type != EventType.ERROR:
                    error_event = Event(
                        type=EventType.ERROR,
                        data={
                            'original_event': event,
                            'handler': handler.__name__,
                            'error': str(e)
                        },
                        source="event_bus"
                    )
                    self.put_nowait(error_event)

    def get_stats(self) -> Dict[str, int]:
        """
        获取统计信息

        Returns:
            dict: 统计数据
        """
        return {
            'published': self._stats['published'],
            'processed': self._stats['processed'],
            'errors': self._stats['errors'],
            'queue_size': self._queue.qsize(),
            'handlers': sum(len(handlers) for handlers in self._handlers.values())
        }

    def reset_stats(self):
        """重置统计信息"""
        self._stats = {
            'published': 0,
            'processed': 0,
            'errors': 0
        }
        logger.info("事件总线统计已重置")

    def clear_handlers(self, event_type: Optional[EventType] = None):
        """
        清除处理器

        Args:
            event_type (Optional[EventType]): 要清除的事件类型，None 表示清除所有
        """
        if event_type:
            self._handlers[event_type].clear()
            logger.info(f"已清除 {event_type} 的处理器")
        else:
            self._handlers.clear()
            logger.info("已清除所有处理器")

    def is_running(self) -> bool:
        """检查事件总线是否运行中"""
        return self._running


# 全局单例（可选）
_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """
    获取全局事件总线单例

    Returns:
        EventBus: 全局事件总线
    """
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


async def shutdown_event_bus():
    """关闭全局事件总线"""
    global _global_event_bus
    if _global_event_bus:
        await _global_event_bus.stop()
        _global_event_bus = None
