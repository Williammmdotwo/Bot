"""
Pytest Configuration and Fixtures for Athena OS Test Suite
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock
from pathlib import Path

# Add src to path for imports
import sys
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def event_bus():
    """Create a mock EventBus"""
    bus = MagicMock()
    bus.put_nowait = Mock()
    bus.register = Mock()
    return bus


@pytest.fixture
def mock_rest_gateway():
    """Create a mock REST Gateway"""
    gateway = AsyncMock()

    # Create a counter for unique order IDs
    order_counter = [0]

    def mock_place_order(**kwargs):
        order_counter[0] += 1
        return {
            'ordId': f'test_order_{order_counter[0]}',
            'clOrdId': f'test_cl_ord_id_{order_counter[0]}',
            'fillSz': '0.0'
        }

    # Mock place_order to return unique order IDs
    gateway.place_order = AsyncMock(side_effect=mock_place_order)

    # Mock cancel_order
    gateway.cancel_order = AsyncMock(return_value={'ordId': 'test_order_123'})

    # Mock get_ticker
    gateway.get_ticker = Mock(return_value={'last': '50000.0'})

    # Mock get_positions (returns empty list by default, can be overridden in tests)
    gateway.get_positions = AsyncMock(return_value=[])

    # Mock get_order_status (returns pending by default, can be overridden in tests)
    gateway.get_order_status = AsyncMock(return_value={
        'state': 'live',
        'fillSz': '0',
        'avgPx': '0'
    })

    # 🔥 [修复] Mock get_instrument_details 方法（返回正确的仪器详情）
    # 针对 DOGE-USDT-SWAP 返回合理的合约面值
    async def mock_get_instrument_details(symbol):
        """Mock instrument details for DOGE and BTC"""
        if symbol == "DOGE-USDT-SWAP":
            return [{
                'instId': 'DOGE-USDT-SWAP',
                'ctVal': '10',  # 合约面值 10
                'tickSz': '0.00001',  # 最小价格变动
                'last': '0.12345'
            }]
        elif symbol == "BTC-USDT-SWAP":
            return [{
                'instId': 'BTC-USDT-SWAP',
                'ctVal': '100',  # 合约面值 100
                'tickSz': '0.1',  # 最小价格变动
                'last': '50000.0'
            }]
        else:
            return [{
                'instId': symbol,
                'ctVal': '1',  # 默认面值 1
                'tickSz': '0.01',
                'last': '0.0'
            }]

    gateway.get_instrument_details = AsyncMock(side_effect=mock_get_instrument_details)

    return gateway


@pytest.fixture
def pre_trade_check():
    """Create a PreTradeCheck instance"""
    from src.risk.pre_trade import PreTradeCheck
    pre_trade = PreTradeCheck(
        max_order_amount=10000.0,
        max_frequency=100,
        frequency_window=1.0
    )
    # Mock check to always pass for testing
    pre_trade.check = Mock(return_value=(True, None))
    return pre_trade


@pytest.fixture
def capital_commander():
    """Create a CapitalCommander instance"""
    from src.oms.capital_commander import CapitalCommander
    return CapitalCommander(total_capital=100000.0)  # Increased to 100k for testing


@pytest.fixture
def position_manager(event_bus):
    """Create a PositionManager instance"""
    from src.oms.position_manager import PositionManager
    return PositionManager(
        event_bus=event_bus,
        sync_threshold_pct=0.10,
        cooldown_seconds=60
    )


@pytest.fixture
def mock_public_gateway():
    """Create a mock public gateway for order book data"""
    gateway = Mock()
    # Mock get_best_bid_ask to return valid prices
    gateway.get_best_bid_ask = Mock(return_value=(49999.0, 50001.0))
    return gateway


@pytest.fixture
def scalper_v1(event_bus, order_manager, capital_commander, mock_public_gateway):
    """Create a ScalperV1 strategy instance (V1 - Blind Momentum)"""
    from src.strategies.hft.scalper_v2 import ScalperV1Refactored as ScalperV1

    # Register to instrument to ensure lot_size and min_notional are known
    capital_commander.register_instrument(
        symbol="BTC-USDT-SWAP",
        lot_size=0.001,
        min_order_size=0.001,
        min_notional=10.0
    )

    # Allocate sufficient funds for test
    # The test tries to open 0.1 BTC (~$5000), so we give it $50,000
    capital_commander.allocate_strategy(
        strategy_id="test_scalper_v1",
        amount=50000.0
    )

    strategy = ScalperV1(
        event_bus=event_bus,
        order_manager=order_manager,
        capital_commander=capital_commander,
        symbol="BTC-USDT-SWAP",
        imbalance_ratio=3.0,
        min_flow_usdt=1000.0,
        take_profit_pct=0.002,
        stop_loss_pct=0.01,
        time_limit_seconds=5,
        position_size=1.0,
        mode="DEV",  # Use DEV mode for testing
        strategy_id="test_scalper_v1"
    )
    # Inject public gateway for order book data
    strategy.set_public_gateway(mock_public_gateway)
    return strategy


@pytest.fixture
def scalper_v2(event_bus, order_manager, capital_commander, mock_rest_gateway):
    """Create a ScalperV1 strategy instance (V2 - Micro-Reversion Sniper)"""
    from src.strategies.hft.scalper_v2 import ScalperV1Refactored as ScalperV1

    # Register DOGE-USDT-SWAP instrument to ensure lot_size and min_notional are known
    capital_commander.register_instrument(
        symbol="DOGE-USDT-SWAP",
        lot_size=0.001,
        min_order_size=0.001,
        min_notional=10.0
    )

    # Allocate sufficient funds for test
    # V2 tests use DOGE, so we need funds for that
    capital_commander.allocate_strategy(
        strategy_id="test_scalper_v2",
        amount=50000.0
    )

    strategy = ScalperV1(
        event_bus=event_bus,
        order_manager=order_manager,
        capital_commander=capital_commander,
        symbol="DOGE-USDT-SWAP",  # V2 uses DOGE
        imbalance_ratio=5.0,  # V2: Higher imbalance ratio
        min_flow_usdt=5000.0,  # V2: Higher flow threshold
        take_profit_pct=0.002,
        stop_loss_pct=0.01,
        time_limit_seconds=30,  # V2: Longer time limit
        # position_size=None,  # Test expects None (default)
        mode="DEV",  # Use DEV mode for testing
        strategy_id="test_scalper_v2",
        cooldown_seconds=0.1  # V2: HFT mode with short cooldown
    )
    # Note: Public gateway is injected in test methods with tight/wide spread mocks
    return strategy


@pytest.fixture
def order_manager(mock_rest_gateway, event_bus, pre_trade_check, capital_commander):
    """Create an OrderManager instance with all dependencies"""
    from src.oms.order_manager import OrderManager
    manager = OrderManager(
        rest_gateway=mock_rest_gateway,
        event_bus=event_bus,
        pre_trade_check=pre_trade_check,
        capital_commander=capital_commander
    )

    # 🔥 [修复] Mock RiskGuardian 的 validate_order 方法（允许所有订单）
    # 这样测试就不会因为风控拒绝而失败
    async def mock_validate_order(**kwargs):
        from src.risk import RiskValidationResult
        return RiskValidationResult(
            is_passed=True,
            reason="Mock allows all orders in tests",
            suggested_size=kwargs.get('size', 1.0)
        )

    manager.risk_guardian = Mock()
    manager.risk_guardian.validate_order = AsyncMock(side_effect=mock_validate_order)

    return manager


@pytest.fixture
def sample_order_data():
    """Sample order data for testing"""
    return {
        'order_id': 'test_order_123',
        'clOrdId': 'test_cl_ord_id',
        'symbol': 'BTC-USDT-SWAP',
        'side': 'buy',
        'size': 1.0,
        'price': 50000.0,
        'order_type': 'limit'
    }


@pytest.fixture
def sample_filled_order():
    """Sample filled order data"""
    return {
        'order_id': 'test_order_123',
        'clOrdId': 'test_cl_ord_id',
        'symbol': 'BTC-USDT-SWAP',
        'side': 'buy',
        'filled_size': 1.0,
        'price': 50000.0,
        'stop_loss_price': 49900.0
    }
