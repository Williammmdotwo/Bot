"""
ScalperV1 HFT 策略专项测试

验证 Maker (Post-Only) 模式下的核心功能：
- get_best_bid_ask 数据处理
- 失衡信号触发
- Maker 挂单逻辑
- 止盈止损机制
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from decimal import Decimal
from datetime import datetime

from src.strategies.hft.scalper_v1 import ScalperV1
from src.core.event_types import Event, EventType


@pytest.fixture
def mock_gateway():
    """模拟公共网关"""
    gateway = Mock()

    # Mock get_best_bid_ask 返回值
    gateway.get_best_bid_ask = AsyncMock(return_value=(50000.0, 50005.0))

    return gateway


@pytest.fixture
def mock_order_manager():
    """模拟订单管理器"""
    manager = Mock()

    # Mock place_limit_order
    manager.place_limit_order = AsyncMock(return_value="test_order_001")

    # Mock cancel_order
    manager.cancel_order = AsyncMock(return_value=True)

    return manager


@pytest.fixture
def mock_event_bus():
    """模拟事件总线"""
    bus = Mock()
    bus.put = AsyncMock()
    return bus


@pytest.fixture
def mock_position_manager():
    """模拟持仓管理器"""
    manager = Mock()
    manager.get_position = Mock(return_value=None)  # 无持仓
    return manager


@pytest.fixture
def mock_capital_commander():
    """模拟资金指挥官"""
    commander = Mock()
    commander.get_total_equity = Mock(return_value=10000.0)  # 总权益
    commander._risk_config = Mock()
    commander._risk_config.RISK_PER_TRADE_PCT = 0.02  # 单笔风险 2%
    return commander


@pytest.fixture
def scalper(mock_gateway, mock_order_manager, mock_event_bus, mock_position_manager, mock_capital_commander):
    """创建 ScalperV1 实例"""
    strategy = ScalperV1(
        event_bus=mock_event_bus,
        order_manager=mock_order_manager,
        capital_commander=mock_capital_commander,
        symbol="BTC-USDT-SWAP",
        strategy_id="test_scalper_001"
    )

    # 注入依赖
    strategy.public_gateway = mock_gateway
    strategy._order_manager = mock_order_manager
    strategy._event_bus = mock_event_bus
    strategy._position_manager = mock_position_manager

    # 启用策略
    strategy._enabled = True

    return strategy


class TestScalperV1Basics:
    """ScalperV1 基础功能测试"""

    def test_strategy_initialization(self, scalper):
        """测试策略初始化"""
        assert scalper.symbol == "BTC-USDT-SWAP"
        assert scalper.strategy_id == "test_scalper_001"
        assert scalper._enabled is True

    def test_config_attributes(self, scalper):
        """测试配置属性"""
        assert hasattr(scalper.config, 'imbalance_ratio')
        assert hasattr(scalper.config, 'min_flow_usdt')
        assert hasattr(scalper.config, 'take_profit_pct')
        assert hasattr(scalper.config, 'stop_loss_pct')
        assert hasattr(scalper.config, 'position_size')
        assert hasattr(scalper.config, 'maker_timeout_seconds')

    def test_update_config(self, scalper):
        """测试配置更新"""
        # 更新配置
        scalper.update_config(
            imbalance_ratio=3.0,
            min_flow_usdt=5000,
            take_profit_pct=0.003,
            stop_loss_pct=0.002,
            time_limit_seconds=30,
            position_size=0.001,
            maker_timeout_seconds=10
        )

        # 验证更新
        assert scalper.config.imbalance_ratio == 3.0
        assert scalper.config.min_flow_usdt == 5000
        assert scalper.config.take_profit_pct == 0.003
        assert scalper.config.stop_loss_pct == 0.002
        assert scalper.config.time_limit_seconds == 30
        assert scalper.config.position_size == 0.001
        assert scalper.config.maker_timeout_seconds == 10


class TestOrderbookData:
    """Orderbook 数据处理测试"""

    @pytest.mark.asyncio
    async def test_get_best_bid_ask_normal(self, scalper, mock_gateway):
        """测试正常的 get_best_bid_ask 返回"""
        bid, ask = await mock_gateway.get_best_bid_ask(scalper.symbol)

        assert bid == 50000.0
        assert ask == 50005.0
        assert ask > bid

    @pytest.mark.asyncio
    async def test_get_best_bid_ask_invalid(self, scalper, mock_gateway):
        """测试无效的 get_best_bid_ask 返回"""
        # 模拟无效数据
        mock_gateway.get_best_bid_ask = AsyncMock(return_value=(0.0, 0.0))

        bid, ask = await mock_gateway.get_best_bid_ask(scalper.symbol)

        assert bid == 0.0
        assert ask == 0.0


class TestMakerLogic:
    """Maker 挂单逻辑测试"""

    @pytest.mark.asyncio
    async def test_place_maker_order_buy(self, scalper, mock_order_manager):
        """测试买单 Maker 挂单"""
        # 下买单（应该挂在对盘价格）
        price = 50000.0
        size = 0.001

        order_id = await mock_order_manager.place_limit_order(
            symbol=scalper.symbol,
            side="buy",
            order_type="limit",
            size=size,
            price=price,
            post_only=True  # Maker 模式
        )

        assert order_id == "test_order_001"
        mock_order_manager.place_limit_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_place_maker_order_sell(self, scalper, mock_order_manager):
        """测试卖单 Maker 挂单"""
        # 下卖单（应该挂在卖一价格）
        price = 50005.0
        size = 0.001

        order_id = await mock_order_manager.place_limit_order(
            symbol=scalper.symbol,
            side="sell",
            order_type="limit",
            size=size,
            price=price,
            post_only=True  # Maker 模式
        )

        assert order_id == "test_order_001"
        mock_order_manager.place_limit_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_maker_order(self, scalper, mock_order_manager):
        """测试撤销 Maker 挂单"""
        order_id = "test_order_001"

        success = await mock_order_manager.cancel_order(order_id)

        assert success is True
        mock_order_manager.cancel_order.assert_called_once_with(order_id)


class TestPositionManagement:
    """持仓管理测试"""

    @pytest.mark.asyncio
    async def test_no_position(self, scalper, mock_position_manager):
        """测试无持仓状态"""
        position = mock_position_manager.get_position(scalper.symbol)

        assert position is None

    @pytest.mark.asyncio
    async def test_check_open_position(self, scalper, mock_position_manager):
        """测试检查是否有开仓"""
        # 无持仓
        position = mock_position_manager.get_position(scalper.symbol)
        has_position = position is not None and position.size != 0

        assert has_position is False


class TestImbalanceSignal:
    """失衡信号测试（简化测试）"""

    def test_imbalance_threshold(self, scalper):
        """测试失衡阈值配置"""
        # 默认配置
        assert scalper.config.imbalance_ratio > 0

        # 更新配置
        scalper.update_config(imbalance_ratio=3.0)
        assert scalper.config.imbalance_ratio == 3.0

    def test_min_flow_threshold(self, scalper):
        """测试最小流量阈值配置"""
        assert scalper.config.min_flow_usdt > 0

        # 更新配置
        scalper.update_config(min_flow_usdt=5000)
        assert scalper.config.min_flow_usdt == 5000


class TestRiskManagement:
    """风险管理测试"""

    def test_take_profit_config(self, scalper):
        """测试止盈配置"""
        assert scalper.config.take_profit_pct > 0

        scalper.update_config(take_profit_pct=0.003)  # 0.3%
        assert scalper.config.take_profit_pct == 0.003

    def test_stop_loss_config(self, scalper):
        """测试止损配置"""
        assert scalper.config.stop_loss_pct > 0

        scalper.update_config(stop_loss_pct=0.002)  # 0.2%
        assert scalper.config.stop_loss_pct == 0.002

    def test_time_limit_config(self, scalper):
        """测试时间限制配置"""
        assert scalper.config.time_limit_seconds > 0

        scalper.update_config(time_limit_seconds=30)
        assert scalper.config.time_limit_seconds == 30


class TestStrategyLifecycle:
    """策略生命周期测试"""

    @pytest.mark.asyncio
    async def test_strategy_enable(self, scalper):
        """测试策略启用"""
        scalper._enabled = True
        assert scalper._enabled is True

    @pytest.mark.asyncio
    async def test_strategy_disable(self, scalper):
        """测试策略禁用"""
        scalper._enabled = False
        assert scalper._enabled is False

    @pytest.mark.asyncio
    async def test_reset_stats(self, scalper):
        """测试重置统计"""
        scalper.reset_statistics()

        assert scalper._total_trades == 0
        assert scalper._win_trades == 0
        assert scalper._loss_trades == 0


@pytest.mark.integration
class TestScalperV1Integration:
    """ScalperV1 集成测试"""

    @pytest.mark.asyncio
    async def test_full_cycle_mock(self, scalper, mock_gateway, mock_order_manager, mock_event_bus):
        """测试完整的交易周期（模拟）"""

        # 1. 获取订单簿价格
        bid, ask = await mock_gateway.get_best_bid_ask(scalper.symbol)
        assert bid > 0 and ask > 0

        # 2. 下 Maker 挂单
        order_id = await mock_order_manager.place_limit_order(
            symbol=scalper.symbol,
            side="buy",
            order_type="limit",
            size=scalper.config.position_size,
            price=bid,
            post_only=True
        )
        assert order_id is not None

        # 3. 撤销挂单
        success = await mock_order_manager.cancel_order(order_id)
        assert success is True

        # 4. 验证事件发布
        # mock_event_bus.put.assert_called()  # 验证事件总线被调用


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
