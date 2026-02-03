"""
事件总线 (Event Bus)

轻量级异步事件总线，实现模块间的 Pub/Sub 通信。

设计原则：
- 轻量级，零依赖
- 异步设计，支持高并发
- 类型安全，使用标准事件格式
- 解耦模块间依赖
- 🔥 [P0 修复] 支持优先级队列，确保紧急事件实时处理
"""

import asyncio
import logging
from typing import Callable, Dict, List, Any, Optional
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import count
from .event_types import Event, EventType

logger = logging.getLogger(__name__)


# 🔥 [P0 修复] 定义事件优先级常量
class EventPriority:
    """
    事件优先级定义

    数值越小，优先级越高（priority queue 默认行为）
    """
    EMERGENCY_CLOSE = 0  # 紧急平仓（最高优先级）
    ORDER_FILLED = 1     # 订单成交（需立即触发止损）
    RISK_ALERT = 2       # 风控警报
    POSITION_UPDATE = 3    # 持仓更新
    ORDER_UPDATE = 5      # 订单状态更新
    TICK = 10            # 行情数据（最低优先级）


# 🔥 [修复] 引入全局计数器，确保相同优先级事件按 FIFO 顺序处理
_event_counter = count()


@dataclass(order=False)
class PriorityEvent:
    """
    优先级事件包装器

    支持比较（__lt__），以便在 PriorityQueue 中排序

    🔥 [修复] 添加计数器字段，确保相同优先级事件按 FIFO 处理

    比较顺序：
    1. priority (数值越小优先级越高)
    2. counter (确保 FIFO 顺序)
    """
    priority: int  # 优先级（数值越小优先级越高）
    event: Event    # 实际事件对象
    counter: int = field(default_factory=lambda: next(_event_counter))  # 🔥 [修复] 确保相同优先级按 FIFO 处理

    def __lt__(self, other: 'PriorityEvent') -> bool:
        """
        比较方法，用于 PriorityQueue 排序

        比较逻辑：
        1. 先比较 priority（数值越小优先级越高）
        2. 如果 priority 相同，比较 counter（数值越小越先处理，即 FIFO）
        """
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.counter < other.counter


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
        # 🔥 [P0 修复] 替换为优先级队列
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=10000)
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._stats = {
            'published': 0,
            'processed': 0,
            'errors': 0
        }
        # 🔥 [新增] 性能监控
        self._latency_stats: Dict[str, List[float]] = {}
        self._max_latency_samples = 1000  # 最多保留 1000 个延迟样本
        self.WARNING_LATENCY_MS = 10.0
        self.CRITICAL_LATENCY_MS = 50.0
        logger.info("EventBus 初始化（优先级队列模式 + 性能监控）")

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

    async def put(self, event: Event, priority: int = EventPriority.TICK):
        """
        发布事件（异步，支持优先级）

        将事件放入优先级队列，由后台任务处理。

        Args:
            event (Event): 要发布的事件
            priority (int): 优先级（默认 TICK 优先级）
                        使用 EventPriority 常量，例如 EventPriority.ORDER_FILLED

        Example:
            >>> await event_bus.put(Event(
            ...     type=EventType.TICK,
            ...     data={'price': 50000.0},
            ...     source="test"
            ... ))
            >>>
            >>> # 高优先级事件（订单成交）
            >>> await event_bus.put(Event(
            ...     type=EventType.ORDER_FILLED,
            ...     data={'order_id': '12345'},
            ...     source="order_manager"
            ... ), priority=EventPriority.ORDER_FILLED)
        """
        try:
            # 🔥 [P0 修复] 包装为 PriorityEvent
            priority_event = PriorityEvent(priority=priority, event=event)
            await self._queue.put(priority_event)
            self._stats['published'] += 1

            # 只在 DEBUG 级别记录详细日志
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"发布事件: {event.type.value} (优先级={priority}) from {event.source}")

        except asyncio.QueueFull:
            logger.error(f"事件队列已满，丢弃事件: {event.type}")
            self._stats['errors'] += 1

    def put_nowait(self, event: Event, priority: int = EventPriority.TICK):
        """
        发布事件（非阻塞，支持优先级）

        Args:
            event (Event): 要发布的事件
            priority (int): 优先级（默认 TICK 优先级）
        """
        try:
            # 🔥 [P0 修复] 包装为 PriorityEvent
            priority_event = PriorityEvent(priority=priority, event=event)
            self._queue.put_nowait(priority_event)
            self._stats['published'] += 1

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"发布事件(非阻塞): {event.type.value} (优先级={priority}) from {event.source}")

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
                # 🔥 [P0 修复] 获取 PriorityEvent 并解包
                priority_event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._process_event(priority_event.event)

            except asyncio.TimeoutError:
                continue

            except asyncio.CancelledError:
                # 🔥 [修复] 处理取消异常，正常退出循环
                logger.debug("事件处理循环被取消")
                break

            except Exception as e:
                # 🔥 [修复] 增强异常处理，确保单个事件处理失败不会让整个循环退出
                logger.error(f"事件处理循环错误: {e}", exc_info=True)
                # 继续循环，不退出
                continue

    async def _process_event(self, event: Event):
        """
        处理单个事件（带性能监控）

        调用所有注册的处理器。

        Args:
            event (Event): 要处理的事件（已从 PriorityEvent 解包）
        """
        # 🔥 [新增] 开始计时
        import time
        start_time = time.perf_counter()

        # 🔥 [P0 修复] 处理的是解包后的 Event 对象
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

            # 🔥 [修复] 无论成功还是失败，都增加 processed 计数
            self._stats['processed'] += 1

        # 🔥 [新增] 计算并记录延迟
        processing_time_ms = (time.perf_counter() - start_time) * 1000.0

        # 记录延迟统计
        event_type_str = event.type.value
        if event_type_str not in self._latency_stats:
            self._latency_stats[event_type_str] = []

        self._latency_stats[event_type_str].append(processing_time_ms)

        # 🔥 [优化] 只保留最近 1000 个样本，避免内存无限增长
        if len(self._latency_stats[event_type_str]) > self._max_latency_samples:
            self._latency_stats[event_type_str] = self._latency_stats[event_type_str][-self._max_latency_samples:]

        # 检查是否超时
        if processing_time_ms > self.CRITICAL_LATENCY_MS:
            logger.error(
                f"⚠️ [EventBus] 事件处理延迟过高: "
                f"{event_type_str}={processing_time_ms:.2f}ms > {self.CRITICAL_LATENCY_MS}ms"
            )
        elif processing_time_ms > self.WARNING_LATENCY_MS:
            logger.warning(
                f"⚠️ [EventBus] 事件处理延迟: "
                f"{event_type_str}={processing_time_ms:.2f}ms > {self.WARNING_LATENCY_MS}ms"
            )

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

    # 🔥 [新增] 性能监控方法

    def get_latency_stats(self, event_type: Optional[str] = None) -> Dict:
        """
        获取延迟统计信息

        Args:
            event_type: 事件类型，None 表示全部

        Returns:
            Dict: 统计信息
        """
        if event_type:
            latencies = self._latency_stats.get(event_type, [])
            if not latencies:
                return {}

            return {
                'event_type': event_type,
                'count': len(latencies),
                'avg_ms': sum(latencies) / len(latencies),
                'max_ms': max(latencies),
                'min_ms': min(latencies),
                'p99_ms': sorted(latencies)[int(len(latencies) * 0.99)] if len(latencies) > 0 else 0.0
            }
        else:
            # 返回所有事件类型的统计
            return {
                etype: self.get_latency_stats(etype)
                for etype in self._latency_stats.keys()
            }

    def reset_latency_stats(self, event_type: Optional[str] = None):
        """
        重置延迟统计信息

        Args:
            event_type: 事件类型，None 表示重置全部
        """
        if event_type:
            self._latency_stats.pop(event_type, None)
            logger.info(f"📊 [EventBus] 已重置 {event_type} 的延迟统计")
        else:
            self._latency_stats.clear()
            logger.info("📊 [EventBus] 已重置所有延迟统计")


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
