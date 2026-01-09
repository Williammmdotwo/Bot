"""
HFT 模块集成测试

本模块提供 HFT 模块的集成测试，验证各模块协同工作的正确性。

测试范围：
- 完整交易周期测试（开仓 -> 持仓 -> 平仓）
- 多策略协同测试
- 持仓同步测试
- 错误恢复测试
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from src.high_frequency.core.engine import HybridEngine
from src.high_frequency.execution.executor import OrderExecutor
from src.high_frequency.execution.circuit_breaker import RiskGuard
from src.high_frequency.data.memory_state import MarketState
from src.high_frequency.data.user_stream import UserStream
from src.high_frequency.exceptions import (
    HFTError,
    OrderExecutionError,
    PositionSyncError,
    RiskControlError
)


@pytest.mark.asyncio
class TestHFTIntegration:
    """HFT 模块集成测试"""

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

    async def test_full_trading_cycle_vulture(self, engine, mock_executor):
        """
        测试完整交易周期：秃鹫模式

        验证流程：
        1. 模拟价格暴跌，触发秃鹫策略
        2. 验证下单成功
        3. 模拟价格上涨，触发追踪止盈
        4. 验证平仓成功
        5. 验证持仓状态重置
        """
        # 1. 初始化 EMA
        base_price = 50000.0
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        # 2. 触发秃鹫策略（价格暴跌 1%）
        trigger_price = base_price * 0.99
        await engine.on_tick(
            price=trigger_price,
            timestamp=int(time.time() * 1000) + 100
        )

        # 验证下单
        mock_executor.place_ioc_order.assert_called_once()
        assert engine.current_position > 0
        assert engine.entry_price == trigger_price
        assert engine.highest_price == trigger_price

        # 3. 模拟价格上涨到最高点
        peak_price = trigger_price * 1.02
        await engine.on_tick(
            price=peak_price,
            timestamp=int(time.time() * 1000) + 200
        )
        assert engine.highest_price == peak_price

        # 4. 触发追踪止盈（从最高点回撤 0.5%）
        exit_price = peak_price * 0.995
        await engine.on_tick(
            price=exit_price,
            timestamp=int(time.time() * 1000) + 300
        )

        # 验证平仓
        mock_executor.close_position.assert_called_once()
        assert engine.current_position == 0
        assert engine.entry_price is None
        assert engine.highest_price is None

    async def test_full_trading_cycle_sniper(self, engine, market_state, mock_executor):
        """
        测试完整交易周期：狙击模式

        验证流程：
        1. 模拟大单涌入，触发狙击策略
        2. 验证下单成功
        3. 触发硬止损
        4. 验证平仓成功
        """
        # 1. 初始化价格和阻力位
        base_price = 50000.0
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        # 2. 模拟大单涌入（3 秒内超过阈值）
        current_time = int(time.time() * 1000)
        for i in range(25):
            # 买单，总金额 > 10000 USDT
            market_state.update_trade(
                price=base_price + 1,
                size=500.0 / (base_price + 1),
                side="buy",
                timestamp=current_time + i * 100
            )

        # 3. 价格突破阻力位
        trigger_price = base_price * 1.0001
        await engine.on_tick(
            price=trigger_price,
            timestamp=current_time + 5000
        )

        # 验证下单
        mock_executor.place_ioc_order.assert_called()
        assert engine.current_position > 0

        # 4. 触发硬止损（亏损 1%）
        exit_price = trigger_price * 0.99
        await engine.on_tick(
            price=exit_price,
            timestamp=current_time + 6000
        )

        # 验证平仓
        mock_executor.close_position.assert_called()
        assert engine.current_position == 0

    async def test_position_sync_websocket(self, engine):
        """
        测试持仓同步：WebSocket 推送

        验证流程：
        1. WebSocket 推送持仓更新
        2. 验证引擎状态正确更新
        3. 验证出场逻辑使用正确状态
        """
        # 1. 模拟 WebSocket 推送持仓
        positions = [{
            'instId': 'BTC-USDT-SWAP',
            'pos': '10',
            'avgPx': '50000.0',
            'cTime': str(int(time.time() * 1000))
        }]

        await engine.update_position_state(positions)

        # 验证状态更新
        assert engine.current_position == 10.0
        assert engine.entry_price == 50000.0
        assert engine.entry_time == int(time.time() * 1000)
        assert engine.highest_price == 50000.0

    async def test_position_sync_rest_api(self, engine, mock_executor):
        """
        测试持仓同步：REST API 校准

        验证流程：
        1. WebSocket 推送持仓
        2. REST API 查询结果不同
        3. 验证以 REST API 为准覆盖状态
        """
        # 1. WebSocket 推送持仓
        positions = [{
            'instId': 'BTC-USDT-SWAP',
            'pos': '10',
            'avgPx': '50000.0',
            'cTime': str(int(time.time() * 1000))
        }]
        await engine.update_position_state(positions)
        assert engine.current_position == 10.0

        # 2. REST API 返回不同持仓
        mock_executor.get_positions.return_value = [{
            'instId': 'BTC-USDT-SWAP',
            'pos': '5',
            'avgPx': '50100.0',
            'cTime': str(int(time.time() * 1000))
        }]

        # 3. 触发 REST API 校准（模拟 60 秒后）
        engine.last_sync_time = time.time() - 70.0
        await engine.on_tick(price=50100.0, timestamp=int(time.time() * 1000))

        # 等待异步任务完成
        await asyncio.sleep(0.1)

        # 验证状态被 REST API 覆盖
        assert engine.current_position == 5.0
        assert engine.entry_price == 50100.0

    async def test_multiple_strategies_no_conflict(self, engine, market_state, mock_executor):
        """
        测试多策略协同：无冲突

        验证流程：
        1. 同时触发秃鹫和狙击策略
        2. 验证只执行一个订单（风控冷却）
        3. 验证持仓状态正确
        """
        # 1. 初始化 EMA 和阻力位
        base_price = 50000.0
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        # 2. 同时满足秃鹫和狙击条件
        current_time = int(time.time() * 1000)

        # 添加大单（狙击条件）
        for i in range(25):
            market_state.update_trade(
                price=base_price + 1,
                size=500.0 / (base_price + 1),
                side="buy",
                timestamp=current_time + i * 100
            )

        # 价格暴跌（秃鹫条件）且突破阻力位（狙击条件）
        trigger_price = base_price * 0.99
        await engine.on_tick(
            price=trigger_price,
            timestamp=current_time + 5000
        )

        # 验证只执行一个订单
        assert mock_executor.place_ioc_order.call_count == 1
        assert engine.current_position > 0

    async def test_risk_control_blocks_trading(self, engine, risk_guard):
        """
        测试风控拒绝交易

        验证流程：
        1. 设置亏损超过阈值
        2. 触发秃鹫策略
        3. 验证订单未执行
        """
        # 1. 设置亏损超过 3%
        risk_guard.set_balances(initial=10000.0, current=9600.0)

        # 2. 初始化 EMA
        base_price = 50000.0
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        # 3. 触发秃鹫策略
        trigger_price = base_price * 0.99
        await engine.on_tick(
            price=trigger_price,
            timestamp=int(time.time() * 1000) + 100
        )

        # 验证订单未执行
        assert engine.current_position == 0
        assert engine.entry_price is None

    async def test_error_recovery_order_failure(self, engine, mock_executor):
        """
        测试错误恢复：订单执行失败

        验证流程：
        1. 模拟订单执行失败
        2. 验证不影响后续交易
        """
        # 1. 初始化 EMA
        base_price = 50000.0
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        # 2. 模拟订单执行失败
        mock_executor.place_ioc_order.side_effect = Exception("网络错误")
        trigger_price = base_price * 0.99
        await engine.on_tick(
            price=trigger_price,
            timestamp=int(time.time() * 1000) + 100
        )

        # 验证持仓状态未更新
        assert engine.current_position == 0

        # 3. 恢复订单执行
        mock_executor.place_ioc_order.side_effect = None
        mock_executor.place_ioc_order.return_value = {
            "code": "0",
            "data": [{"ordId": "123456"}]
        }

        # 4. 再次触发策略
        await engine.on_tick(
            price=trigger_price,
            timestamp=int(time.time() * 1000) + 200
        )

        # 验证订单成功执行
        assert engine.current_position > 0

    async def test_dynamic_sizing_balance_insufficient(self, engine, mock_executor):
        """
        测试动态仓位：余额不足

        验证流程：
        1. 模拟余额不足
        2. 触发策略
        3. 验证订单未执行
        """
        # 1. 模拟余额不足
        mock_executor.get_usdt_balance.return_value = 0.0

        # 2. 初始化 EMA
        base_price = 50000.0
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        # 3. 触发秃鹫策略
        trigger_price = base_price * 0.99
        await engine.on_tick(
            price=trigger_price,
            timestamp=int(time.time() * 1000) + 100
        )

        # 验证订单未执行
        assert mock_executor.place_ioc_order.call_count == 0

    async def test_concurrent_ticks_performance(self, engine):
        """
        测试并发 Tick 处理性能

        验证流程：
        1. 并发处理 100 个 Tick
        2. 验证处理时间 < 100ms
        """
        # 1. 初始化 EMA
        base_price = 50000.0
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        # 2. 并发处理 100 个 Tick
        tasks = []
        start_time = time.time()

        for i in range(100):
            task = engine.on_tick(
                price=base_price + i * 0.1,
                timestamp=int(time.time() * 1000) + i * 10
            )
            tasks.append(task)

        await asyncio.gather(*tasks)
        duration = time.time() - start_time

        # 3. 验证性能
        assert duration < 0.1  # 100 个 tick 应在 100ms 内处理完
        assert engine.tick_count >= 150  # 50 个初始化 + 100 个并发

    async def test_statistics_tracking(self, engine):
        """
        测试统计信息追踪

        验证流程：
        1. 触发多个策略
        2. 验证统计信息正确
        """
        # 1. 初始化 EMA
        base_price = 50000.0
        for i in range(50):
            await engine.on_tick(price=base_price, timestamp=int(time.time() * 1000) + i)

        # 2. 触发秃鹫策略
        trigger_price = base_price * 0.99
        await engine.on_tick(
            price=trigger_price,
            timestamp=int(time.time() * 1000) + 100
        )

        # 3. 获取统计信息
        stats = engine.get_statistics()

        # 4. 验证统计信息
        assert stats['symbol'] == 'BTC-USDT-SWAP'
        assert stats['mode'] == 'hybrid'
        assert stats['tick_count'] > 50
        assert stats['vulture_triggers'] > 0
        assert stats['ema_fast'] is not None
        assert stats['ema_slow'] is not None
        assert stats['resistance'] > 0
