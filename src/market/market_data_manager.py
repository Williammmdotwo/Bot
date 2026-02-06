"""
MarketDataManager - 统一行情数据管理中心

职责：
- 订阅 BOOK_EVENT 和 TICK_EVENT
- 维护全局最新的 L2 OrderBook 和 Ticker 状态
- 提供只读快照给策略和组件
- 线程安全（asyncio.Lock）
- 🔥 [新增] 微秒级延迟监控
"""

import asyncio
import time
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
import time as time_module

from src.core.event_bus import EventBus
from src.core.event_types import Event, EventType
import logging

logger = logging.getLogger(__name__)


@dataclass
class OrderBookSnapshot:
    """订单簿快照（不可变）"""
    symbol: str
    bids: Tuple[Tuple[float, float]]  # [(price, size), ...]
    asks: Tuple[Tuple[float, float]]
    best_bid: float
    best_ask: float
    timestamp: float


@dataclass
class TickerSnapshot:
    """行情快照（不可变）"""
    symbol: str
    last_price: float
    bid_price: float
    ask_price: float
    volume_24h: float
    timestamp: float


class MarketDataManager:
    """
    市场数据管理器（单一数据源）

    设计原则：
    - 单向数据流：只从 EventBus 订阅，不发送事件
    - 线程安全：使用 asyncio.Lock 保护状态
    - 不可变快照：返回的快照对象不可修改
    - 🔥 [新增] 微秒级延迟监控
    """

    def __init__(self, event_bus: EventBus):
        """
        初始化市场数据管理器

        Args:
            event_bus: 事件总线
        """
        self._event_bus = event_bus
        self._lock = asyncio.Lock()

        # 订单簿状态（按 symbol 索引）
        self._order_books: Dict[str, Dict] = {}  # {symbol: {'bids': ..., 'asks': ...}}

        # 行情状态（按 symbol 索引）
        self._tickers: Dict[str, Dict] = {}  # {symbol: {...}}

        # 🔥 [新增] 延迟统计（微秒级）
        self._book_update_latency_stats = {
            'count': 0,
            'total_us': 0,
            'max_us': 0,
            'min_us': float('inf')
        }

        # 订阅事件
        self._subscribe_to_events()

        logger.info("📊 MarketDataManager 初始化完成")

    def _subscribe_to_events(self):
        """订阅 BOOK_EVENT 和 TICK"""
        self._event_bus.register(EventType.BOOK_EVENT, self._on_book_event)
        self._event_bus.register(EventType.TICK, self._on_tick_event)
        logger.info("📊 MarketDataManager 已订阅 BOOK_EVENT 和 TICK")

    async def _on_book_event(self, event: Event):
        """
        处理订单簿事件（内部更新）

        🔥 [新增] 微秒级延迟监控：从 Parser 解析完成到快照更新完成的耗时

        Args:
            event: BOOK_EVENT
        """
        # 🔥 [新增] 微秒级计时（使用 time.perf_counter 精度更高）
        start_time = time_module.perf_counter()

        data = event.data
        symbol = data.get('symbol')

        if not symbol:
            logger.warning("⚠️ [MarketDataManager] BOOK_EVENT 缺少 symbol")
            return

        # 🔥 [调试] 显示数据
        logger.info(f"🔍 [调试] on_book_event: symbol={symbol}, bids={len(data.get('bids', []))}, asks={len(data.get('asks', []))}")

        async with self._lock:
            # 更新订单簿
            self._order_books[symbol] = {
                'bids': data.get('bids', []),
                'asks': data.get('asks', []),
                'best_bid': data.get('best_bid', 0.0),
                'best_ask': data.get('best_ask', 0.0),
                'timestamp': time.time()
            }

        # 🔥 [调试] 验证更新成功
        logger.debug(f"   ✅ OrderBook 已更新到缓存: {symbol}")
        logger.debug(f"   缓存键列表: {list(self._order_books.keys())}")

        # 🔥 [新增] 计算延迟（微秒）
        end_time = time_module.perf_counter()
        latency_us = (end_time - start_time) * 1_000_000  # 转换为微秒

        # 更新统计
        stats = self._book_update_latency_stats
        stats['count'] += 1
        stats['total_us'] += latency_us
        stats['max_us'] = max(stats['max_us'], latency_us)
        stats['min_us'] = min(stats['min_us'], latency_us)

        logger.debug(f"📊 [MarketDataManager] 更新 OrderBook: {symbol}, 延迟={latency_us:.2f}μs")

    async def _on_tick_event(self, event: Event):
        """
        处理 Tick 事件（更新 Ticker）

        Args:
            event: TICK_EVENT
        """
        async with self._lock:
            data = event.data
            symbol = data.get('symbol')

            if not symbol:
                return

            # 更新 Ticker
            self._tickers[symbol] = {
                'last_price': float(data.get('price', 0)),
                'timestamp': data.get('timestamp', 0) / 1000.0
            }

            logger.debug(f"📊 [MarketDataManager] 更新 Ticker: {symbol}")

    def get_order_book_snapshot(self, symbol: str) -> Optional[OrderBookSnapshot]:
        """
        获取订单簿快照（只读，不可变）

        Args:
            symbol: 交易对

        Returns:
            OrderBookSnapshot: 订单簿快照，如果不存在返回 None
        """
        # 🔥 [修复] 移除锁：同步方法不能使用 asyncio.Lock，且 dict 读取是原子操作
        order_book = self._order_books.get(symbol)

        if not order_book:
            return None

        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])

        # 提取最佳买卖价
        best_bid = float(bids[0][0]) if bids and len(bids) > 0 else 0.0
        best_ask = float(asks[0][0]) if asks and len(asks) > 0 else 0.0

        # 转换为不可变元组
        bids_tuple = tuple((float(b[0]), float(b[1])) for b in bids)
        asks_tuple = tuple((float(a[0]), float(a[1])) for a in asks)

        return OrderBookSnapshot(
            symbol=symbol,
            bids=bids_tuple,
            asks=asks_tuple,
            best_bid=best_bid,
            best_ask=best_ask,
            timestamp=time.time()
        )

    def get_ticker_snapshot(self, symbol: str) -> Optional[TickerSnapshot]:
        """
        获取行情快照（只读，不可变）

        Args:
            symbol: 交易对

        Returns:
            TickerSnapshot: 行情快照，如果不存在返回 None
        """
        # 🔥 [修复] 移除锁：同步方法不能使用 asyncio.Lock，且 dict 读取是原子操作
        ticker = self._tickers.get(symbol)

        if not ticker:
            return None

        return TickerSnapshot(
            symbol=symbol,
            last_price=ticker['last_price'],
            bid_price=ticker.get('bid_price', ticker['last_price']),
            ask_price=ticker.get('ask_price', ticker['last_price']),
            volume_24h=ticker.get('volume_24h', 0.0),
            timestamp=ticker['timestamp']
        )

    def get_best_bid_ask(self, symbol: str) -> Tuple[float, float]:
        """
        获取最优买卖价（便捷方法）

        Args:
            symbol: 交易对

        Returns:
            Tuple[float, float]: (best_bid, best_ask)
        """
        snapshot = self.get_order_book_snapshot(symbol)

        if snapshot:
            return (snapshot.best_bid, snapshot.best_ask)
        else:
            return (0.0, 0.0)

    def get_order_book(self, symbol: str) -> dict:
        """
        获取订单簿数据（直接从缓存获取，不转换格式）

        Args:
            symbol: 交易对

        Returns:
            dict: {'bids': [...], 'asks': [...], 'best_bid': ..., 'best_ask': ...} 或 None
        """
        # 🔥 [调试 1] 方法被调用
        logger.debug(f"🔍 [调试] MarketDataManager.get_order_book 被调用: symbol={symbol}")

        # 🔥 [调试 2] 显示缓存状态
        logger.debug(f"   _order_books.keys()={list(self._order_books.keys())}")
        logger.debug(f"   _order_books 长度={len(self._order_books)}")

        # 直接读取，dict 读取是原子操作，不需要锁
        order_book = self._order_books.get(symbol)

        # 🔥 [调试 3] 显示结果
        if order_book:
            logger.debug(
                f"   ✅ 找到 OrderBook: "
                f"bids={len(order_book.get('bids', []))}, "
                f"asks={len(order_book.get('asks', []))}"
            )
        else:
            logger.warning(f"   ❌ 未找到 OrderBook: symbol={symbol}")
            logger.warning(f"   可用键列表: {list(self._order_books.keys())}")

        return order_book.copy() if order_book else None

    def get_order_book_depth(self, symbol: str, levels: int = 3) -> Dict:
        """
        获取订单簿深度（用于流动性保护）

        Args:
            symbol: 交易对
            levels: 档位数量

        Returns:
            Dict: {'bids': [...], 'asks': [...]}
        """
        # 🔥 [调试 1] 方法被调用
        logger.info(f"🔍 [调试] get_order_book_depth 被调用")
        logger.info(f"   参数: symbol={symbol}, levels={levels}")

        # 🔥 [调试 2] 检查缓存
        logger.info(f"   _order_books 缓存键: {list(self._order_books.keys())}")

        snapshot = self.get_order_book_snapshot(symbol)

        if not snapshot:
            logger.warning(f"⚠️ [调试] {symbol}: OrderBook 快照为空")
            logger.info(f"   _order_books 完整内容: {self._order_books}")
            return {'bids': [], 'asks': []}

        # 🔥 [调试 3] 显示快照结构
        logger.info(f"   snapshot 类型: {type(snapshot)}")
        logger.info(f"   bids 长度: {len(snapshot.bids)}")
        logger.info(f"   asks 长度: {len(snapshot.asks)}")

        # 截取指定档位
        bids = snapshot.bids[:levels]
        asks = snapshot.asks[:levels]

        # 🔥 [调试 4] 显示档位数据
        if bids:
            logger.info(f"   bids 第一档: {bids[0]}")
        if asks:
            logger.info(f"   asks 第一档: {asks[0]}")

        # 🔥 [调试 5] 构造返回结果
        result = {
            'bids': [(p, s) for p, s in bids],
            'asks': [(p, s) for p, s in asks]
        }

        # 🔥 [调试 6] 最终结果
        logger.info(f"🔍 [调试] 返回深度: bids={len(result['bids'])}, asks={len(result['asks'])}")
        if result['bids']:
            logger.info(f"   bids[0]: {result['bids'][0]}")
        if result['asks']:
            logger.info(f"   asks[0]: {result['asks'][0]}")

        return result

    def get_latency_stats(self) -> Dict:
        """
        🔥 [新增] 获取订单簿更新延迟统计

        Returns:
            Dict: 延迟统计信息
        """
        stats = self._book_update_latency_stats
        if stats['count'] == 0:
            return {
                'count': 0,
                'avg_us': 0,
                'max_us': 0,
                'min_us': 0,
                'total_us': 0
            }

        return {
            'count': stats['count'],
            'avg_us': stats['total_us'] / stats['count'],
            'max_us': stats['max_us'],
            'min_us': stats['min_us'],
            'total_us': stats['total_us']
        }

    def reset_latency_stats(self):
        """🔥 [新增] 重置延迟统计"""
        self._book_update_latency_stats = {
            'count': 0,
            'total_us': 0,
            'max_us': 0,
            'min_us': float('inf')
        }
        logger.info("📊 [MarketDataManager] 延迟统计已重置")
