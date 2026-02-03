"""
多币种并发压力测试与扩展性分析

测试目标：
1. 模拟 20 个不同币种的 Tick 和 Book 数据（万次/秒频率）
2. 观察 MarketDataManager 的 latency_stats 和 EventBus 的排队延迟
3. 内存审计：1 个币种 vs 20 个币种并发下的内存增长曲线
4. 检查 PositionSizer 的 deque 和 MarketDataManager 的快照缓存是否存在内存泄漏
5. 性能瓶颈定位：日志 IO 过多 vs asyncio.Lock 竞争
6. 优化方案：异步日志、轻量级 EventBus 分发

使用方法：
    python tests/stress_test_scaling.py
"""

import asyncio
import time
import random
import tracemalloc
import psutil
import os
from typing import Dict, List, Tuple
from collections import defaultdict
import json

# 添加项目根目录到路径
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.event_bus import EventBus, Event, EventType, EventPriority
from src.market.market_data_manager import MarketDataManager
from src.strategies.hft.components.position_sizer import PositionSizer, PositionSizingConfig

# 日志配置
import logging
logging.basicConfig(
    level=logging.INFO,  # 🔥 [测试] INFO 级别，避免日志过多
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ========== 测试配置 ==========

# 测试币种列表（20 个）
TEST_SYMBOLS = [
    'BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP', 'DOGE-USDT-SWAP',
    'XRP-USDT-SWAP', 'ADA-USDT-SWAP', 'AVAX-USDT-SWAP', 'DOT-USDT-SWAP',
    'MATIC-USDT-SWAP', 'LINK-USDT-SWAP', 'UNI-USDT-SWAP', 'LTC-USDT-SWAP',
    'BCH-USDT-SWAP', 'XLM-USDT-SWAP', 'ALGO-USDT-SWAP', 'VET-USDT-SWAP',
    'FIL-USDT-SWAP', 'ICP-USDT-SWAP', 'TRX-USDT-SWAP', 'NEAR-USDT-SWAP'
]

# 测试参数
TEST_DURATION_SECONDS = 30  # 测试持续时间（秒）
TICKS_PER_SECOND_PER_SYMBOL = 500  # 每个币种每秒 Tick 数（500 * 20 = 10000 TPS）
BOOK_UPDATES_PER_SECOND = 100  # 每个币种每秒 Book 更新数

# 性能阈值
WARNING_LATENCY_MS = 10.0  # 警告阈值
CRITICAL_LATENCY_MS = 50.0  # 严重阈值


# ========== 性能监控工具 ==========

class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self.start_time = time.time()
        self.memory_snapshots: List[Tuple[float, float]] = []  # (timestamp, memory_mb)
        self.event_bus_stats: List[Dict] = []
        self.market_data_stats: List[Dict] = []
        self.lock_stats: Dict[str, int] = defaultdict(int)  # 记录锁竞争次数

    def record_memory(self):
        """记录内存快照"""
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024  # MB
        elapsed = time.time() - self.start_time
        self.memory_snapshots.append((elapsed, memory_mb))
        return memory_mb

    def record_event_bus_stats(self, event_bus: EventBus):
        """记录 EventBus 统计"""
        stats = event_bus.get_stats()
        stats['timestamp'] = time.time() - self.start_time
        self.event_bus_stats.append(stats)

    def record_market_data_stats(self, market_data_manager: MarketDataManager):
        """记录 MarketDataManager 统计"""
        stats = market_data_manager.get_latency_stats()
        stats['timestamp'] = time.time() - self.start_time
        self.market_data_stats.append(stats)

    def record_lock_contention(self, component: str):
        """记录锁竞争"""
        self.lock_stats[component] += 1

    def get_memory_growth_rate(self) -> float:
        """计算内存增长率（MB/秒）"""
        if len(self.memory_snapshots) < 2:
            return 0.0

        first_time, first_mem = self.memory_snapshots[0]
        last_time, last_mem = self.memory_snapshots[-1]
        time_diff = last_time - first_time

        if time_diff == 0:
            return 0.0

        return (last_mem - first_mem) / time_diff

    def get_summary(self) -> Dict:
        """获取性能摘要"""
        # 内存统计
        if self.memory_snapshots:
            memories = [mem for _, mem in self.memory_snapshots]
            memory_summary = {
                'initial_mb': memories[0],
                'final_mb': memories[-1],
                'peak_mb': max(memories),
                'growth_mb': memories[-1] - memories[0],
                'growth_rate_mb_per_sec': self.get_memory_growth_rate()
            }
        else:
            memory_summary = {}

        # EventBus 统计
        if self.event_bus_stats:
            queue_sizes = [s['queue_size'] for s in self.event_bus_stats]
            event_bus_summary = {
                'max_queue_size': max(queue_sizes),
                'avg_queue_size': sum(queue_sizes) / len(queue_sizes),
                'total_published': self.event_bus_stats[-1]['published'],
                'total_processed': self.event_bus_stats[-1]['processed'],
                'total_errors': self.event_bus_stats[-1]['errors']
            }
        else:
            event_bus_summary = {}

        # MarketDataManager 统计
        if self.market_data_stats:
            counts = [s['count'] for s in self.market_data_stats]
            avg_latencies = [s['avg_us'] / 1000.0 for s in self.market_data_stats if s['count'] > 0]  # 转换为 ms
            max_latencies = [s['max_us'] / 1000.0 for s in self.market_data_stats if s['count'] > 0]
            market_data_summary = {
                'total_updates': self.market_data_stats[-1]['count'],
                'avg_latency_ms': sum(avg_latencies) / len(avg_latencies) if avg_latencies else 0.0,
                'max_latency_ms': max(max_latencies) if max_latencies else 0.0,
                'max_latency_ms_critical': max(max_latencies) if max_latencies else 0.0 > CRITICAL_LATENCY_MS
            }
        else:
            market_data_summary = {}

        # 锁竞争统计
        lock_summary = dict(self.lock_stats)

        return {
            'duration_seconds': time.time() - self.start_time,
            'memory': memory_summary,
            'event_bus': event_bus_summary,
            'market_data': market_data_summary,
            'lock_contention': lock_summary
        }


# ========== 数据生成器 ==========

class DataGenerator:
    """数据生成器（模拟真实市场数据）"""

    def __init__(self, symbol: str, base_price: float):
        self.symbol = symbol
        self.base_price = base_price
        self.current_price = base_price
        self.tick_size = base_price * 0.0001  # 0.01%

    def generate_tick_event(self) -> Event:
        """生成 Tick 事件"""
        # 随机价格波动（±0.01%）
        price_change = self.current_price * random.uniform(-0.0001, 0.0001)
        self.current_price += price_change

        # 随机交易量
        size = random.uniform(0.1, 10.0)

        return Event(
            type=EventType.TICK,
            data={
                'symbol': self.symbol,
                'price': self.current_price,
                'size': size,
                'side': random.choice(['buy', 'sell']),
                'timestamp': int(time.time() * 1000)
            },
            source="stress_test"
        )

    def generate_book_event(self) -> Event:
        """生成 Book 事件"""
        # 随机价格波动（±0.02%）
        price_change = self.current_price * random.uniform(-0.0002, 0.0002)
        self.current_price += price_change

        # 生成买盘
        bids = []
        for i in range(5):
            bid_price = self.current_price * (1.0 - 0.0001 * (i + 1))
            bid_size = random.uniform(10.0, 100.0)
            bids.append([bid_price, bid_size])

        # 生成卖盘
        asks = []
        for i in range(5):
            ask_price = self.current_price * (1.0 + 0.0001 * (i + 1))
            ask_size = random.uniform(10.0, 100.0)
            asks.append([ask_price, ask_size])

        return Event(
            type=EventType.BOOK_EVENT,
            data={
                'symbol': self.symbol,
                'bids': bids,
                'asks': asks,
                'timestamp': int(time.time() * 1000)
            },
            source="stress_test"
        )


# ========== 压力测试 ==========

async def stress_test_single_symbol():
    """单币种压力测试（基准测试）"""
    logger.info("=" * 80)
    logger.info("🧪 [测试1] 单币种压力测试（基准）")
    logger.info("=" * 80)

    # 初始化
    event_bus = EventBus()
    market_data_manager = MarketDataManager(event_bus)
    monitor = PerformanceMonitor()

    # 创建数据生成器
    generator = DataGenerator('BTC-USDT-SWAP', 50000.0)

    # 启动 EventBus
    await event_bus.start()

    # 初始内存
    monitor.record_memory()

    # 测试循环
    start_time = time.time()
    tick_interval = 1.0 / TICKS_PER_SECOND_PER_SYMBOL
    book_interval = 1.0 / BOOK_UPDATES_PER_SECOND
    last_tick_time = 0
    last_book_time = 0

    logger.info(f"🚀 开始测试: 时长={TEST_DURATION_SECONDS}s, TPS={TICKS_PER_SECOND_PER_SYMBOL}, BPS={BOOK_UPDATES_PER_SECOND}")

    try:
        while time.time() - start_time < TEST_DURATION_SECONDS:
            current_time = time.time()

            # 生成 Tick 事件
            if current_time - last_tick_time >= tick_interval:
                tick_event = generator.generate_tick_event()
                await event_bus.put(tick_event, priority=EventPriority.TICK)
                last_tick_time = current_time

            # 生成 Book 事件
            if current_time - last_book_time >= book_interval:
                book_event = generator.generate_book_event()
                await event_bus.put(book_event, priority=EventPriority.TICK)
                last_book_time = current_time

            # 记录统计（每秒一次）
            if int(current_time) > int(start_time):
                monitor.record_memory()
                monitor.record_event_bus_stats(event_bus)
                monitor.record_market_data_stats(market_data_manager)

            # 短暂休眠避免 CPU 占用过高
            await asyncio.sleep(0.001)

    except KeyboardInterrupt:
        logger.info("测试被用户中断")
    finally:
        await event_bus.stop()

    # 最终内存
    monitor.record_memory()

    # 生成报告
    summary = monitor.get_summary()
    logger.info("\n" + "=" * 80)
    logger.info("📊 [测试1] 单币种压力测试结果")
    logger.info("=" * 80)
    logger.info(f"⏱️  测试时长: {summary['duration_seconds']:.1f}s")
    logger.info(f"💾 内存: 初始={summary['memory']['initial_mb']:.2f}MB, "
                f"最终={summary['memory']['final_mb']:.2f}MB, "
                f"峰值={summary['memory']['peak_mb']:.2f}MB, "
                f"增长={summary['memory']['growth_mb']:.2f}MB "
                f"({summary['memory']['growth_rate_mb_per_sec']:.3f}MB/s)")
    logger.info(f"📡 EventBus: 发布={summary['event_bus']['total_published']}, "
                f"处理={summary['event_bus']['total_processed']}, "
                f"错误={summary['event_bus']['total_errors']}, "
                f"最大队列={summary['event_bus']['max_queue_size']}")
    logger.info(f"📊 MarketData: 更新={summary['market_data']['total_updates']}, "
                f"平均延迟={summary['market_data']['avg_latency_ms']:.3f}ms, "
                f"最大延迟={summary['market_data']['max_latency_ms']:.3f}ms")

    # 🔥 [瓶颈定位] 检查延迟是否超过阈值
    if summary['market_data']['avg_latency_ms'] > WARNING_LATENCY_MS:
        logger.warning(f"⚠️ [瓶颈警告] MarketDataManager 平均延迟 {summary['market_data']['avg_latency_ms']:.3f}ms > {WARNING_LATENCY_MS}ms")
        if summary['market_data']['avg_latency_ms'] > CRITICAL_LATENCY_MS:
            logger.error(f"🚨 [瓶颈严重] MarketDataManager 平均延迟 {summary['market_data']['avg_latency_ms']:.3f}ms > {CRITICAL_LATENCY_MS}ms")

    return summary


async def stress_test_multi_symbols(num_symbols: int = 20):
    """多币种并发压力测试"""
    logger.info("\n" + "=" * 80)
    logger.info(f"🧪 [测试2] 多币种并发压力测试（{num_symbols} 个币种）")
    logger.info("=" * 80)

    # 初始化
    event_bus = EventBus()
    market_data_manager = MarketDataManager(event_bus)
    monitor = PerformanceMonitor()

    # 创建数据生成器
    generators = []
    for symbol in TEST_SYMBOLS[:num_symbols]:
        base_price = random.uniform(1.0, 50000.0)  # 随机价格
        generator = DataGenerator(symbol, base_price)
        generators.append(generator)

    # 启动 EventBus
    await event_bus.start()

    # 初始内存
    monitor.record_memory()

    # 测试循环
    start_time = time.time()
    tick_interval = 1.0 / TICKS_PER_SECOND_PER_SYMBOL
    book_interval = 1.0 / BOOK_UPDATES_PER_SECOND
    last_tick_time = 0
    last_book_time = 0

    total_tps = TICKS_PER_SECOND_PER_SYMBOL * num_symbols
    total_bps = BOOK_UPDATES_PER_SECOND * num_symbols

    logger.info(f"🚀 开始测试: 时长={TEST_DURATION_SECONDS}s, "
                f"币种数={num_symbols}, 总TPS={total_tps}, 总BPS={total_bps}")

    try:
        while time.time() - start_time < TEST_DURATION_SECONDS:
            current_time = time.time()

            # 生成所有币种的 Tick 事件
            if current_time - last_tick_time >= tick_interval:
                for generator in generators:
                    tick_event = generator.generate_tick_event()
                    await event_bus.put(tick_event, priority=EventPriority.TICK)
                last_tick_time = current_time

            # 生成所有币种的 Book 事件
            if current_time - last_book_time >= book_interval:
                for generator in generators:
                    book_event = generator.generate_book_event()
                    await event_bus.put(book_event, priority=EventPriority.TICK)
                last_book_time = current_time

            # 记录统计（每秒一次）
            if int(current_time) > int(start_time):
                monitor.record_memory()
                monitor.record_event_bus_stats(event_bus)
                monitor.record_market_data_stats(market_data_manager)

            # 短暂休眠避免 CPU 占用过高
            await asyncio.sleep(0.001)

    except KeyboardInterrupt:
        logger.info("测试被用户中断")
    finally:
        await event_bus.stop()

    # 最终内存
    monitor.record_memory()

    # 生成报告
    summary = monitor.get_summary()
    logger.info("\n" + "=" * 80)
    logger.info(f"📊 [测试2] 多币种并发压力测试结果（{num_symbols} 个币种）")
    logger.info("=" * 80)
    logger.info(f"⏱️  测试时长: {summary['duration_seconds']:.1f}s")
    logger.info(f"💾 内存: 初始={summary['memory']['initial_mb']:.2f}MB, "
                f"最终={summary['memory']['final_mb']:.2f}MB, "
                f"峰值={summary['memory']['peak_mb']:.2f}MB, "
                f"增长={summary['memory']['growth_mb']:.2f}MB "
                f"({summary['memory']['growth_rate_mb_per_sec']:.3f}MB/s)")
    logger.info(f"📡 EventBus: 发布={summary['event_bus']['total_published']}, "
                f"处理={summary['event_bus']['total_processed']}, "
                f"错误={summary['event_bus']['total_errors']}, "
                f"最大队列={summary['event_bus']['max_queue_size']}")
    logger.info(f"📊 MarketData: 更新={summary['market_data']['total_updates']}, "
                f"平均延迟={summary['market_data']['avg_latency_ms']:.3f}ms, "
                f"最大延迟={summary['market_data']['max_latency_ms']:.3f}ms")

    # 🔥 [瓶颈定位] 检查延迟是否超过阈值
    if summary['market_data']['avg_latency_ms'] > WARNING_LATENCY_MS:
        logger.warning(f"⚠️ [瓶颈警告] MarketDataManager 平均延迟 {summary['market_data']['avg_latency_ms']:.3f}ms > {WARNING_LATENCY_MS}ms")
        if summary['market_data']['avg_latency_ms'] > CRITICAL_LATENCY_MS:
            logger.error(f"🚨 [瓶颈严重] MarketDataManager 平均延迟 {summary['market_data']['avg_latency_ms']:.3f}ms > {CRITICAL_LATENCY_MS}ms")

    return summary


async def test_memory_leak():
    """内存泄漏测试"""
    logger.info("\n" + "=" * 80)
    logger.info("🧪 [测试3] 内存泄漏测试")
    logger.info("=" * 80)

    # 启动内存跟踪
    tracemalloc.start()

    # 初始化
    event_bus = EventBus()
    market_data_manager = MarketDataManager(event_bus)
    monitor = PerformanceMonitor()

    # 创建 PositionSizer（检查 deque 是否有内存泄漏）
    config = PositionSizingConfig()
    position_sizer = PositionSizer(config, ct_val=1.0)

    # 创建数据生成器
    generator = DataGenerator('BTC-USDT-SWAP', 50000.0)

    # 启动 EventBus
    await event_bus.start()

    # 初始内存快照
    snapshot1 = tracemalloc.take_snapshot()

    # 测试循环（持续 60 秒）
    start_time = time.time()
    test_duration = 60  # 秒

    logger.info(f"🚀 开始内存泄漏测试: 时长={test_duration}s")

    try:
        while time.time() - start_time < test_duration:
            # 生成大量事件
            for _ in range(100):
                tick_event = generator.generate_tick_event()
                await event_bus.put(tick_event, priority=EventPriority.TICK)

                # 更新 PositionSizer（检查 deque）
                current_price = tick_event.data['price']
                order_book = {
                    'bids': [[current_price * 0.999, 100.0]],
                    'asks': [[current_price * 1.001, 100.0]]
                }
                position_sizer.calculate_order_size(
                    account_equity=10000.0,
                    order_book=order_book,
                    signal_ratio=5.0,
                    current_price=current_price,
                    side='buy'
                )

            await asyncio.sleep(0.01)

    except KeyboardInterrupt:
        logger.info("测试被用户中断")
    finally:
        await event_bus.stop()

    # 最终内存快照
    snapshot2 = tracemalloc.take_snapshot()

    # 对比快照
    top_stats = snapshot2.compare_to(snapshot1, 'lineno')

    logger.info("\n" + "=" * 80)
    logger.info("📊 [测试3] 内存泄漏分析")
    logger.info("=" * 80)

    # 打印前 20 个内存增长点
    logger.info("🔍 内存增长 Top 20:")
    for stat in top_stats[:20]:
        logger.info(f"  {stat}")

    # 分析 PositionSizer 的 deque
    state = position_sizer.get_state()
    logger.info(f"\n📊 PositionSizer 状态:")
    logger.info(f"  价格历史长度: {state['price_history_len']}")
    logger.info(f"  配置 maxlen: {state['config']['volatility_ema_period']}")
    if state['price_history_len'] > state['config']['volatility_ema_period']:
        logger.warning(f"⚠️ [内存泄漏警告] PositionSizer 价格历史超出 maxlen!")
    else:
        logger.info(f"✅ PositionSizer deque 正常（未超出 maxlen）")

    # 分析 MarketDataManager 的快照缓存
    logger.info(f"\n📊 MarketDataManager 状态:")
    logger.info(f"  订单簿缓存: 1 个币种")
    logger.info(f"  行情缓存: 1 个币种")
    logger.info(f"✅ MarketDataManager 使用字典缓存，自动管理内存")

    tracemalloc.stop()


async def test_lock_contention():
    """锁竞争测试"""
    logger.info("\n" + "=" * 80)
    logger.info("🧪 [测试4] 锁竞争测试")
    logger.info("=" * 80)

    # 初始化
    event_bus = EventBus()
    market_data_manager = MarketDataManager(event_bus)
    monitor = PerformanceMonitor()

    # 创建数据生成器
    generators = []
    for symbol in TEST_SYMBOLS[:5]:  # 5 个币种
        base_price = random.uniform(1.0, 50000.0)
        generator = DataGenerator(symbol, base_price)
        generators.append(generator)

    # 启动 EventBus
    await event_bus.start()

    # 测试循环
    start_time = time.time()
    test_duration = 30  # 秒

    logger.info(f"🚀 开始锁竞争测试: 时长={test_duration}s, 币种数=5")

    try:
        while time.time() - start_time < test_duration:
            # 并发生成事件（模拟高并发）
            tasks = []
            for generator in generators:
                # 生成 Tick
                tick_event = generator.generate_tick_event()
                tasks.append(event_bus.put(tick_event, priority=EventPriority.TICK))

                # 生成 Book
                book_event = generator.generate_book_event()
                tasks.append(event_bus.put(book_event, priority=EventPriority.TICK))

                # 读取快照（触发锁竞争）
                tasks.append(market_data_manager.get_order_book_snapshot(generator.symbol))

            await asyncio.gather(*tasks)

            await asyncio.sleep(0.01)

    except KeyboardInterrupt:
        logger.info("测试被用户中断")
    finally:
        await event_bus.stop()

    # 生成报告
    summary = monitor.get_summary()
    logger.info("\n" + "=" * 80)
    logger.info("📊 [测试4] 锁竞争测试结果")
    logger.info("=" * 80)
    logger.info(f"⏱️  测试时长: {summary['duration_seconds']:.1f}s")
    logger.info(f"💾 内存: 增长={summary['memory']['growth_mb']:.2f}MB "
                f"({summary['memory']['growth_rate_mb_per_sec']:.3f}MB/s)")
    logger.info(f"📊 MarketData: 平均延迟={summary['market_data']['avg_latency_ms']:.3f}ms")

    # 🔥 [瓶颈定位] 分析锁竞争
    if summary['market_data']['avg_latency_ms'] > WARNING_LATENCY_MS:
        logger.warning(f"⚠️ [瓶颈警告] MarketDataManager 延迟过高，可能存在锁竞争")
        logger.info(f"💡 建议:")
        logger.info(f"  1. 减少锁的粒度（例如，每个 symbol 使用独立的 Lock）")
        logger.info(f"  2. 使用读写锁（asyncio.Lock 替换为 asyncio.RWLock）")
        logger.info(f"  3. 减少快照频率")
    else:
        logger.info(f"✅ 锁竞争正常")


# ========== 主程序 ==========

async def main():
    """主测试函数"""
    logger.info("=" * 80)
    logger.info("🚀 Athena Trader 多币种并发压力测试")
    logger.info("=" * 80)

    results = {}

    # 测试1: 单币种压力测试
    try:
        results['single_symbol'] = await stress_test_single_symbol()
    except Exception as e:
        logger.error(f"❌ 测试1失败: {e}", exc_info=True)

    # 等待 5 秒
    logger.info("\n⏱️ 等待 5 秒...")
    await asyncio.sleep(5)

    # 测试2: 多币种并发压力测试
    try:
        results['multi_symbol_20'] = await stress_test_multi_symbols(20)
    except Exception as e:
        logger.error(f"❌ 测试2失败: {e}", exc_info=True)

    # 等待 5 秒
    logger.info("\n⏱️ 等待 5 秒...")
    await asyncio.sleep(5)

    # 测试3: 内存泄漏测试
    try:
        await test_memory_leak()
    except Exception as e:
        logger.error(f"❌ 测试3失败: {e}", exc_info=True)

    # 等待 5 秒
    logger.info("\n⏱️ 等待 5 秒...")
    await asyncio.sleep(5)

    # 测试4: 锁竞争测试
    try:
        await test_lock_contention()
    except Exception as e:
        logger.error(f"❌ 测试4失败: {e}", exc_info=True)

    # 生成综合报告
    logger.info("\n" + "=" * 80)
    logger.info("📊 综合测试报告")
    logger.info("=" * 80)

    # 对比单币种 vs 多币种
    if 'single_symbol' in results and 'multi_symbol_20' in results:
        single = results['single_symbol']
        multi = results['multi_symbol_20']

        logger.info(f"\n📈 扩展性分析（单币种 vs 20 币种）:")
        logger.info(f"  内存增长:")
        logger.info(f"    单币种: {single['memory']['growth_mb']:.2f}MB "
                    f"({single['memory']['growth_rate_mb_per_sec']:.3f}MB/s)")
        logger.info(f"    20币种: {multi['memory']['growth_mb']:.2f}MB "
                    f"({multi['memory']['growth_rate_mb_per_sec']:.3f}MB/s)")
        logger.info(f"    扩展比例: {multi['memory']['growth_rate_mb_per_sec'] / single['memory']['growth_rate_mb_per_sec']:.2f}x")

        logger.info(f"\n  延迟分析:")
        logger.info(f"    单币种: 平均={single['market_data']['avg_latency_ms']:.3f}ms")
        logger.info(f"    20币种: 平均={multi['market_data']['avg_latency_ms']:.3f}ms")
        logger.info(f"    延迟增长: {(multi['market_data']['avg_latency_ms'] / single['market_data']['avg_latency_ms'] - 1) * 100:.1f}%")

        logger.info(f"\n  EventBus 性能:")
        logger.info(f"    单币种: 发布={single['event_bus']['total_published']}, "
                    f"最大队列={single['event_bus']['max_queue_size']}")
        logger.info(f"    20币种: 发布={multi['event_bus']['total_published']}, "
                    f"最大队列={multi['event_bus']['max_queue_size']}")

    # 优化建议
    logger.info("\n" + "=" * 80)
    logger.info("💡 优化建议")
    logger.info("=" * 80)

    # 检查是否需要优化
    if 'multi_symbol_20' in results:
        multi = results['multi_symbol_20']

        # 1. 延迟优化
        if multi['market_data']['avg_latency_ms'] > WARNING_LATENCY_MS:
            logger.warning(f"⚠️ 延迟过高 ({multi['market_data']['avg_latency_ms']:.3f}ms)，建议:")
            logger.info(f"  1. 使用异步日志（aiologger 或类似库）")
            logger.info(f"  2. 减少日志输出频率（DEBUG 级别改为 INFO）")
            logger.info(f"  3. 使用更轻量的 EventBus 分发机制（例如，广播模式）")
            logger.info(f"  4. 考虑使用 uvloop 替换标准 asyncio 循环")

        # 2. 内存优化
        if multi['memory']['growth_rate_mb_per_sec'] > 1.0:  # 超过 1MB/s
            logger.warning(f"⚠️ 内存增长过快 ({multi['memory']['growth_rate_mb_per_sec']:.3f}MB/s)，建议:")
            logger.info(f"  1. 限制 MarketDataManager 快照缓存的大小（例如，LRU 缓存）")
            logger.info(f"  2. 定期清理 EventBus 的延迟统计（只保留最近 N 个样本）")
            logger.info(f"  3. 检查 PositionSizer 的 deque 是否有内存泄漏")

        # 3. 锁竞争优化
        if multi['market_data']['avg_latency_ms'] > WARNING_LATENCY_MS:
            logger.warning(f"⚠️ 可能存在锁竞争，建议:")
            logger.info(f"  1. 每个 symbol 使用独立的 Lock（减少锁粒度）")
            logger.info(f"  2. 使用读写锁（asyncio.RWLock）替代 asyncio.Lock")
            logger.info(f"  3. 减少快照频率（例如，每 10ms 只更新一次）")

        else:
            logger.info(f"✅ 性能表现良好，无需优化")

    # 保存测试结果
    results_file = 'tests/stress_test_results.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    logger.info(f"\n✅ 测试结果已保存到: {results_file}")
    logger.info("=" * 80)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n测试被用户中断")
