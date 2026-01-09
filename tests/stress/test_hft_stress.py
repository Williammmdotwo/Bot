"""
HFT 模块压力测试

本模块提供 HFT 模块的压力测试，验证系统在高负载下的性能表现。

测试范围：
- 高频 Tick 处理性能
- 并发订单执行性能
- 内存泄漏检测
- 长时间运行稳定性
"""

import pytest
import asyncio
import time
import psutil
import os
from unittest.mock import Mock, AsyncMock
from src.high_frequency.core.engine import HybridEngine
from src.high_frequency.execution.executor import OrderExecutor
from src.high_frequency.execution.circuit_breaker import RiskGuard
from src.high_frequency.data.memory_state import MarketState
from src.high_frequency.monitoring import PerformanceMetrics


@pytest.mark.asyncio
@pytest.mark.slow
class TestHFTStress:
    """HFT 模块压力测试"""

    @pytest.fixture
    def market_state(self):
        """创建市场状态管理器"""
        return MarketState()

    @pytest.fixture
    def risk_guard(self):
        """创建风控熔断器（单例）"""
        guard = RiskGuard()
        guard.set_balances(initial=10000.0, current=10000.0)
        return guard

    @pytest.fixture
    def mock_executor(self):
        """创建模拟订单执行器"""
        executor = Mock(spec=OrderExecutor)
        executor.place_ioc_order = AsyncMock(return_value={
            "code": "0",
            "data": [{"ordId": "123456"}]
        })
        executor.close_position = AsyncMock(return_value={
            "code": "0",
            "data": [{"ordId": "654321"}]
        })
        executor.get_usdt_balance = AsyncMock(return_value=10000.0)
        executor.get_positions = AsyncMock(return_value=[])
        return executor

    @pytest.fixture
    def engine(self, market_state, mock_executor, risk_guard):
        """创建混合交易引擎"""
        engine = HybridEngine(
            market_state=market_state,
            executor=mock_executor,
            risk_guard=risk_guard,
            symbol="BTC-USDT-SWAP",
            mode="hybrid",
            order_size=1,
            risk_ratio=0.2,
            leverage=10
        )
        return engine

    @pytest.fixture
    def metrics(self):
        """创建性能指标收集器"""
        return PerformanceMetrics()

    async def test_high_frequency_ticks_1000(self, engine, metrics):
        """
        测试高频 Tick 处理性能：1000 个 Tick

        验证目标：
        - 1000 个 Tick 应在 500ms 内处理完
        - 平均延迟 < 0.5ms
        - P95 延迟 < 1ms
        """
        # 初始化 EMA
        base_price = 50000.0
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        # 记录 1000 个 Tick 的处理时间
        start_time = time.time()
        tick_count = 1000

        for i in range(tick_count):
            tick_start = time.time()

            await engine.on_tick(
                price=base_price + i * 0.01,
                timestamp=int(time.time() * 1000) + i
            )

            # 记录延迟
            tick_latency = (time.time() - tick_start) * 1000  # 转换为毫秒
            metrics.record_tick_latency(tick_latency)

        duration = time.time() - start_time

        # 验证性能
        assert duration < 0.5, f"1000 ticks 处理时间 {duration:.3f}s 超过 0.5s"
        assert metrics.get_avg_tick_latency() < 0.5, f"平均延迟 {metrics.get_avg_tick_latency():.3f}ms 超过 0.5ms"
        assert metrics.get_percentile_tick_latency(95) < 1.0, f"P95 延迟 {metrics.get_percentile_tick_latency(95):.3f}ms 超过 1ms"

    async def test_high_frequency_ticks_10000(self, engine, metrics):
        """
        测试高频 Tick 处理性能：10000 个 Tick

        验证目标：
        - 10000 个 Tick 应在 5s 内处理完
        - 平均延迟 < 0.5ms
        - P99 延迟 < 2ms
        """
        # 初始化 EMA
        base_price = 50000.0
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        # 记录 10000 个 Tick 的处理时间
        start_time = time.time()
        tick_count = 10000

        for i in range(tick_count):
            tick_start = time.time()

            await engine.on_tick(
                price=base_price + i * 0.001,
                timestamp=int(time.time() * 1000) + i
            )

            # 记录延迟
            tick_latency = (time.time() - tick_start) * 1000  # 转换为毫秒
            metrics.record_tick_latency(tick_latency)

        duration = time.time() - start_time

        # 验证性能
        assert duration < 5.0, f"10000 ticks 处理时间 {duration:.3f}s 超过 5s"
        assert metrics.get_avg_tick_latency() < 0.5, f"平均延迟 {metrics.get_avg_tick_latency():.3f}ms 超过 0.5ms"
        assert metrics.get_percentile_tick_latency(99) < 2.0, f"P99 延迟 {metrics.get_percentile_tick_latency(99):.3f}ms 超过 2ms"

    async def test_concurrent_ticks_100(self, engine, metrics):
        """
        测试并发 Tick 处理性能：100 个并发 Tick

        验证目标：
        - 100 个并发 Tick 应在 100ms 内处理完
        - 无死锁或竞态条件
        """
        # 初始化 EMA
        base_price = 50000.0
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        # 并发处理 100 个 Tick
        start_time = time.time()
        tasks = []

        for i in range(100):
            tick_start = time.time()

            task = asyncio.create_task(
                self._tick_with_metrics(
                    engine,
                    base_price + i * 0.1,
                    metrics,
                    tick_start,
                    timestamp=int(time.time() * 1000) + i
                )
            )
            tasks.append(task)

        await asyncio.gather(*tasks)
        duration = time.time() - start_time

        # 验证性能
        assert duration < 0.1, f"100 个并发 Tick 处理时间 {duration:.3f}s 超过 0.1s"
        assert engine.tick_count >= 150  # 50 个初始化 + 100 个并发

    async def _tick_with_metrics(self, engine, price, metrics, tick_start, **kwargs):
        """辅助方法：处理 Tick 并记录延迟"""
        await engine.on_tick(price=price, **kwargs)
        tick_latency = (time.time() - tick_start) * 1000
        metrics.record_tick_latency(tick_latency)

    async def test_memory_leak_detection(self, engine):
        """
        测试内存泄漏检测

        验证目标：
        - 处理 10000 个 Tick 后，内存增长 < 10MB
        """
        # 获取当前进程
        process = psutil.Process(os.getpid())

        # 记录初始内存
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # 处理 10000 个 Tick
        base_price = 50000.0
        for i in range(10000):
            await engine.on_tick(
                price=base_price + i * 0.001,
                timestamp=int(time.time() * 1000) + i
            )

        # 记录最终内存
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory

        # 验证内存增长
        assert memory_growth < 10, f"内存增长 {memory_growth:.2f}MB 超过 10MB"

    async def test_market_state_memory_leak(self):
        """
        测试 MarketState 内存泄漏

        验证目标：
        - 更新 10000 笔交易后，内存增长 < 5MB
        """
        process = psutil.Process(os.getpid())

        # 创建 MarketState
        market_state = MarketState()

        # 记录初始内存
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # 更新 10000 笔交易
        base_price = 50000.0
        for i in range(10000):
            market_state.update_trade(
                price=base_price + i * 0.01,
                size=1.0,
                side="buy",
                timestamp=int(time.time() * 1000) + i
            )

        # 记录最终内存
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory

        # 验证内存增长
        assert memory_growth < 5, f"内存增长 {memory_growth:.2f}MB 超过 5MB"

        # 验证 deque 自动清理
        assert len(market_state.recent_trades) <= 1000, "recent_trades 超过 maxlen"
        assert len(market_state.whale_orders) <= 50, "whale_orders 超过 maxlen"

    async def test_concurrent_orders_100(self, engine, mock_executor, metrics):
        """
        测试并发订单执行性能：100 个订单

        验证目标：
        - 100 个并发订单应在 2s 内执行完
        - 平均订单延迟 < 100ms
        """
        # 初始化 EMA 和阻力位
        base_price = 50000.0
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        # 模拟持仓（允许下单）
        engine.current_position = 0.0

        # 并发下达 100 个订单
        start_time = time.time()
        tasks = []

        for i in range(100):
            order_start = time.time()

            task = asyncio.create_task(
                self._order_with_metrics(
                    engine,
                    mock_executor,
                    base_price,
                    metrics,
                    order_start,
                    timestamp=int(time.time() * 1000) + i * 10
                )
            )
            tasks.append(task)

        await asyncio.gather(*tasks)
        duration = time.time() - start_time

        # 验证性能
        assert duration < 2.0, f"100 个并发订单执行时间 {duration:.3f}s 超过 2s"
        assert metrics.get_avg_order_latency() < 100, f"平均订单延迟 {metrics.get_avg_order_latency():.3f}ms 超过 100ms"

    async def _order_with_metrics(self, engine, executor, price, metrics, order_start, **kwargs):
        """辅助方法：执行订单并记录延迟"""
        # 模拟策略触发
        engine.current_position = 0.0
        await engine._vulture_strategy(price, price * 0.99)

        # 记录订单延迟
        order_latency = (time.time() - order_start) * 1000
        metrics.record_order_latency(order_latency)

    async def test_long_running_stability_1min(self, engine, metrics):
        """
        测试长时间运行稳定性：1 分钟

        验证目标：
        - 1 分钟内处理 60000 个 Tick
        - 无崩溃或异常
        - 平均延迟稳定
        """
        # 初始化 EMA
        base_price = 50000.0
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        # 模拟 1 分钟的市场数据（1000 ticks/s）
        start_time = time.time()
        tick_count = 60000
        duration_seconds = 60

        for i in range(tick_count):
            tick_start = time.time()

            # 模拟价格波动
            price = base_price + (i % 100) * 0.01

            await engine.on_tick(
                price=price,
                timestamp=int(time.time() * 1000) + i
            )

            # 记录延迟
            tick_latency = (time.time() - tick_start) * 1000
            metrics.record_tick_latency(tick_latency)

            # 控制处理速度（1000 ticks/s）
            elapsed = time.time() - start_time
            expected_time = (i + 1) / 1000.0
            if elapsed < expected_time:
                await asyncio.sleep(expected_time - elapsed)

        total_duration = time.time() - start_time

        # 验证稳定性
        assert total_duration < duration_seconds + 5.0, f"运行时间 {total_duration:.3f}s 超过预期"
        assert engine.tick_count == tick_count + 50, f"Tick 数量不匹配"
        assert metrics.get_avg_tick_latency() < 1.0, f"平均延迟 {metrics.get_avg_tick_latency():.3f}ms 超过 1ms"

    async def test_metrics_collection_overhead(self, engine):
        """
        测试性能指标收集开销

        验证目标：
        - 启用指标收集后，性能下降 < 10%
        """
        # 不使用指标收集器的性能
        base_price = 50000.0
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        start_time_without_metrics = time.time()
        tick_count = 1000

        for i in range(tick_count):
            await engine.on_tick(
                price=base_price + i * 0.01,
                timestamp=int(time.time() * 1000) + i
            )

        duration_without_metrics = time.time() - start_time_without_metrics

        # 重置引擎
        engine.reset_statistics()

        # 使用指标收集器的性能
        metrics = PerformanceMetrics()
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        start_time_with_metrics = time.time()

        for i in range(tick_count):
            tick_start = time.time()

            await engine.on_tick(
                price=base_price + i * 0.01,
                timestamp=int(time.time() * 1000) + i
            )

            # 记录延迟
            tick_latency = (time.time() - tick_start) * 1000
            metrics.record_tick_latency(tick_latency)

        duration_with_metrics = time.time() - start_time_with_metrics

        # 计算性能下降
        overhead_percent = ((duration_with_metrics - duration_without_metrics) / duration_without_metrics) * 100

        # 验证开销
        assert overhead_percent < 10, f"指标收集开销 {overhead_percent:.2f}% 超过 10%"

    async def test_extreme_market_conditions(self, engine, market_state, mock_executor):
        """
        测试极端市场条件

        验证目标：
        - 价格剧烈波动时系统稳定
        - 大单涌入时系统稳定
        """
        base_price = 50000.0

        # 模拟极端价格波动（±5%）
        price_series = [
            base_price * (1 + 0.05 * (i % 2))  # 交替上涨和下跌 5%
            for i in range(1000)
        ]

        # 模拟大单涌入
        current_time = int(time.time() * 1000)
        for i in range(100):
            market_state.update_trade(
                price=base_price,
                size=10000.0 / base_price,  # 10000 USDT 的大单
                side="buy",
                timestamp=current_time + i * 10
            )

        # 处理极端价格
        for i, price in enumerate(price_series):
            await engine.on_tick(
                price=price,
                timestamp=current_time + i * 10
            )

        # 验证系统稳定
        assert engine.tick_count >= 1000
        assert len(market_state.recent_trades) <= 1000  # deque 自动清理
        assert len(market_state.whale_orders) <= 50

    async def test_performance_metrics_export(self, metrics):
        """
        测试性能指标导出

        验证目标：
        - 导出 Prometheus 格式正确
        - 导出 JSON 格式正确
        """
        # 添加一些测试数据
        for i in range(100):
            metrics.record_tick_latency(0.5 + i * 0.01)
            metrics.record_order_latency(100.0 + i * 0.5)

        metrics.record_trade(pnl=100.0, strategy="vulture")
        metrics.record_trade(pnl=-50.0, strategy="sniper")
        metrics.record_strategy_trigger("vulture")
        metrics.record_exit("trailing_stop")
        metrics.record_error("order")

        # 测试 Prometheus 导出
        prometheus_metrics = metrics.export_prometheus()
        assert "hft_ticks_total" in prometheus_metrics
        assert "hft_tick_latency_avg" in prometheus_metrics
        assert "hft_trades_total" in prometheus_metrics

        # 测试汇总导出
        summary = metrics.get_summary()
        assert 'total_ticks' in summary
        assert 'avg_tick_latency' in summary
        assert 'total_pnl' in summary
        assert 'win_rate' in summary

        # 测试字符串输出
        str_output = str(metrics)
        assert "HFT 性能指标汇总" in str_output
        assert "总 Tick 数" in str_output
        assert "平均延迟" in str_output
