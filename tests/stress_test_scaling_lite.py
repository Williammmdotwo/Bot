"""
轻量级压力测试（用于快速验证优化效果）

测试目标：
1. 单币种基准测试（30秒）
2. 5币种并发测试（30秒）
3. 对比优化前后的结果

使用方法：
    python tests/stress_test_scaling_lite.py
"""

import asyncio
import time
import random
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

# 日志配置
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ========== 测试配置 ==========

# 测试币种列表（使用前 5 个）
TEST_SYMBOLS = [
    'BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP', 'DOGE-USDT-SWAP',
    'XRP-USDT-SWAP'
]

# 测试参数
TEST_DURATION_SECONDS = 30  # 测试持续时间（秒）
TICKS_PER_SECOND_PER_SYMBOL = 100  # 🔥 [降低] 从 500 降到 100
BOOK_UPDATES_PER_SECOND = 20  # 🔥 [降低] 从 100 降到 20

# 性能阈值
WARNING_LATENCY_MS = 10.0
CRITICAL_LATENCY_MS = 50.0


# ========== 性能监控工具 ==========

class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self.start_time = time.time()
        self.memory_snapshots: List[Tuple[float, float]] = []
        self.event_bus_stats: List[Dict] = []
        self.market_data_stats: List[Dict] = []

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
            avg_latencies = [s['avg_us'] / 1000.0 for s in self.market_data_stats if s['count'] > 0]
            max_latencies = [s['max_us'] / 1000.0 for s in self.market_data_stats if s['count'] > 0]
            market_data_summary = {
                'total_updates': self.market_data_stats[-1]['count'],
                'avg_latency_ms': sum(avg_latencies) / len(avg_latencies) if avg_latencies else 0.0,
                'max_latency_ms': max(max_latencies) if max_latencies else 0.0
            }
        else:
            market_data_summary = {}

        return {
            'duration_seconds': time.time() - self.start_time,
            'memory': memory_summary,
            'event_bus': event_bus_summary,
            'market_data': market_data_summary
        }


# ========== 数据生成器 ==========

class DataGenerator:
    """数据生成器（模拟真实市场数据）"""

    def __init__(self, symbol: str, base_price: float):
        self.symbol = symbol
        self.base_price = base_price
        self.current_price = base_price

    def generate_tick_event(self) -> Event:
        """生成 Tick 事件"""
        price_change = self.current_price * random.uniform(-0.0001, 0.0001)
        self.current_price += price_change
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
        price_change = self.current_price * random.uniform(-0.0002, 0.0002)
        self.current_price += price_change

        bids = []
        for i in range(5):
            bid_price = self.current_price * (1.0 - 0.0001 * (i + 1))
            bid_size = random.uniform(10.0, 100.0)
            bids.append([bid_price, bid_size])

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
    start_time = time.perf_counter()
    tick_interval = 1.0 / TICKS_PER_SECOND_PER_SYMBOL
    book_interval = 1.0 / BOOK_UPDATES_PER_SECOND
    next_tick_time = start_time
    next_book_time = start_time

    expected_ticks = TICKS_PER_SECOND_PER_SYMBOL * TEST_DURATION_SECONDS
    expected_books = BOOK_UPDATES_PER_SECOND * TEST_DURATION_SECONDS
    total_expected = expected_ticks + expected_books

    logger.info(f"🚀 开始测试: 时长={TEST_DURATION_SECONDS}s, "
                f"TPS={TICKS_PER_SECOND_PER_SYMBOL}, BPS={BOOK_UPDATES_PER_SECOND}")
    logger.info(f"📊 预期事件: {expected_ticks} Tick + {expected_books} Book = {total_expected}")

    try:
        while time.perf_counter() - start_time < TEST_DURATION_SECONDS:
            current_time = time.perf_counter()

            # 生成 Tick 事件
            if current_time >= next_tick_time:
                tick_event = generator.generate_tick_event()
                await event_bus.put(tick_event, priority=EventPriority.TICK)
                next_tick_time += tick_interval

            # 生成 Book 事件
            if current_time >= next_book_time:
                book_event = generator.generate_book_event()
                await event_bus.put(book_event, priority=EventPriority.TICK)
                next_book_time += book_interval

            # 记录统计（每秒一次）
            if int(current_time) > int(start_time):
                monitor.record_memory()
                monitor.record_event_bus_stats(event_bus)
                monitor.record_market_data_stats(market_data_manager)

            await asyncio.sleep(0.0001)

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
    logger.info(f"📡 EventBus: 发布={summary['event_bus']['total_published']} "
                f"(预期={total_expected}), "
                f"处理={summary['event_bus']['total_processed']}, "
                f"错误={summary['event_bus']['total_errors']}, "
                f"最大队列={summary['event_bus']['max_queue_size']}")
    logger.info(f"📊 MarketData: 更新={summary['market_data']['total_updates']} "
                f"(预期={expected_books}), "
                f"平均延迟={summary['market_data']['avg_latency_ms']:.3f}ms, "
                f"最大延迟={summary['market_data']['max_latency_ms']:.3f}ms")

    # 检查是否达标
    logger.info("\n🎯 达标检查:")
    logger.info(f"  内存增长率 < 0.5MB/s: {'✅' if summary['memory']['growth_rate_mb_per_sec'] < 0.5 else '❌'} "
                f"({summary['memory']['growth_rate_mb_per_sec']:.3f}MB/s)")
    logger.info(f"  事件生成 = {total_expected}: {'✅' if summary['event_bus']['total_published'] == total_expected else '❌'} "
                f"({summary['event_bus']['total_published']})")
    logger.info(f"  Book 更新 = {expected_books}: {'✅' if summary['market_data']['total_updates'] == expected_books else '❌'} "
                f"({summary['market_data']['total_updates']})")
    logger.info(f"  平均延迟 < 1ms: {'✅' if summary['market_data']['avg_latency_ms'] < 1.0 else '❌'} "
                f"({summary['market_data']['avg_latency_ms']:.3f}ms)")

    return summary


async def stress_test_multi_symbols(num_symbols: int = 5):
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
        base_price = random.uniform(1.0, 50000.0)
        generator = DataGenerator(symbol, base_price)
        generators.append(generator)

    # 启动 EventBus
    await event_bus.start()

    # 初始内存
    monitor.record_memory()

    # 测试循环
    start_time = time.perf_counter()
    tick_interval = 1.0 / TICKS_PER_SECOND_PER_SYMBOL
    book_interval = 1.0 / BOOK_UPDATES_PER_SECOND
    next_tick_time = start_time
    next_book_time = start_time

    expected_ticks = TICKS_PER_SECOND_PER_SYMBOL * num_symbols * TEST_DURATION_SECONDS
    expected_books = BOOK_UPDATES_PER_SECOND * num_symbols * TEST_DURATION_SECONDS
    total_expected = expected_ticks + expected_books
    total_tps = TICKS_PER_SECOND_PER_SYMBOL * num_symbols
    total_bps = BOOK_UPDATES_PER_SECOND * num_symbols

    logger.info(f"🚀 开始测试: 时长={TEST_DURATION_SECONDS}s, "
                f"币种数={num_symbols}, 总TPS={total_tps}, 总BPS={total_bps}")
    logger.info(f"📊 预期事件: {expected_ticks} Tick + {expected_books} Book = {total_expected}")

    try:
        while time.perf_counter() - start_time < TEST_DURATION_SECONDS:
            current_time = time.perf_counter()

            # 生成所有币种的 Tick 事件
            if current_time >= next_tick_time:
                for generator in generators:
                    tick_event = generator.generate_tick_event()
                    await event_bus.put(tick_event, priority=EventPriority.TICK)
                next_tick_time += tick_interval

            # 生成所有币种的 Book 事件
            if current_time >= next_book_time:
                for generator in generators:
                    book_event = generator.generate_book_event()
                    await event_bus.put(book_event, priority=EventPriority.TICK)
                next_book_time += book_interval

            # 记录统计（每秒一次）
            if int(current_time) > int(start_time):
                monitor.record_memory()
                monitor.record_event_bus_stats(event_bus)
                monitor.record_market_data_stats(market_data_manager)

            await asyncio.sleep(0.0001)

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
    logger.info(f"📡 EventBus: 发布={summary['event_bus']['total_published']} "
                f"(预期={total_expected}), "
                f"处理={summary['event_bus']['total_processed']}, "
                f"错误={summary['event_bus']['total_errors']}, "
                f"最大队列={summary['event_bus']['max_queue_size']}")
    logger.info(f"📊 MarketData: 更新={summary['market_data']['total_updates']} "
                f"(预期={expected_books}), "
                f"平均延迟={summary['market_data']['avg_latency_ms']:.3f}ms, "
                f"最大延迟={summary['market_data']['max_latency_ms']:.3f}ms")

    # 检查是否达标
    logger.info("\n🎯 达标检查:")
    logger.info(f"  内存增长率 < 0.5MB/s: {'✅' if summary['memory']['growth_rate_mb_per_sec'] < 0.5 else '❌'} "
                f"({summary['memory']['growth_rate_mb_per_sec']:.3f}MB/s)")
    logger.info(f"  事件生成 = {total_expected}: {'✅' if summary['event_bus']['total_published'] == total_expected else '❌'} "
                f"({summary['event_bus']['total_published']})")
    logger.info(f"  Book 更新 = {expected_books}: {'✅' if summary['market_data']['total_updates'] == expected_books else '❌'} "
                f"({summary['market_data']['total_updates']})")
    logger.info(f"  平均延迟 < 1ms: {'✅' if summary['market_data']['avg_latency_ms'] < 1.0 else '❌'} "
                f"({summary['market_data']['avg_latency_ms']:.3f}ms)")

    return summary


# ========== 主程序 ==========

async def main():
    """主测试函数"""
    logger.info("=" * 80)
    logger.info("🚀 Athena Trader 轻量级压力测试")
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
        results['multi_symbol_5'] = await stress_test_multi_symbols(5)
    except Exception as e:
        logger.error(f"❌ 测试2失败: {e}", exc_info=True)

    # 生成综合报告
    logger.info("\n" + "=" * 80)
    logger.info("📊 综合测试报告")
    logger.info("=" * 80)

    # 对比单币种 vs 多币种
    if 'single_symbol' in results and 'multi_symbol_5' in results:
        single = results['single_symbol']
        multi = results['multi_symbol_5']

        logger.info(f"\n📈 扩展性分析（单币种 vs 5 币种）:")
        logger.info(f"  内存增长:")
        logger.info(f"    单币种: {single['memory']['growth_mb']:.2f}MB "
                    f"({single['memory']['growth_rate_mb_per_sec']:.3f}MB/s)")
        logger.info(f"    5币种: {multi['memory']['growth_mb']:.2f}MB "
                    f"({multi['memory']['growth_rate_mb_per_sec']:.3f}MB/s)")
        logger.info(f"    扩展比例: {multi['memory']['growth_rate_mb_per_sec'] / single['memory']['growth_rate_mb_per_sec']:.2f}x")

        logger.info(f"\n  延迟分析:")
        logger.info(f"    单币种: 平均={single['market_data']['avg_latency_ms']:.3f}ms")
        logger.info(f"    5币种: 平均={multi['market_data']['avg_latency_ms']:.3f}ms")

        logger.info(f"\n  EventBus 性能:")
        logger.info(f"    单币种: 发布={single['event_bus']['total_published']}, "
                    f"最大队列={single['event_bus']['max_queue_size']}")
        logger.info(f"    5币种: 发布={multi['event_bus']['total_published']}, "
                    f"最大队列={multi['event_bus']['max_queue_size']}")

    # 保存测试结果
    results_file = 'tests/stress_test_lite_results.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    logger.info(f"\n✅ 测试结果已保存到: {results_file}")
    logger.info("=" * 80)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n测试被用户中断")
