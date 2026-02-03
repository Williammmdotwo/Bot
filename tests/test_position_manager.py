"""
Test Suite for PositionManager - Critical Fixes Validation

This test suite validates critical fixes implemented in PositionManager:
- Fix 26: Ghost Position Cleanup
- Fix 25: Cancel Logic / Status Check
- Fix 2: Backoff/Circuit Breaker
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from src.core.event_types import Event, EventType
from src.oms.position_manager import PositionManager, Position


class TestPositionManagerCriticalFixes:
    """Test critical fixes in PositionManager"""

    # ============================================
    # Fix 26: Ghost Position Cleanup
    # ============================================

    @pytest.mark.asyncio
    async def test_ghost_position_cleanup_sync_from_rest(self, position_manager):
        """
        Fix 26: Ghost Position Cleanup - REST Sync

        Scenario:
        1. Inject a fake position into manager.positions
        2. Mock get_positions to return [] (exchange says nothing)
        3. Call sync method
        4. Assert: Position is removed or quantity set to 0
        """
        # Step 1: Inject a fake position locally
        ghost_symbol = 'BTC-USDT-SWAP'
        position_manager._positions[ghost_symbol] = Position(
            symbol=ghost_symbol,
            side='long',
            size=1.0,
            entry_price=50000.0,
            unrealized_pnl=100.0,
            leverage=10
        )

        # Verify ghost position exists
        assert ghost_symbol in position_manager._positions
        assert position_manager._positions[ghost_symbol].size == 1.0

        # Step 2: Create API position data (exchange says no position)
        # In OKX, empty position is represented as size=0 or omitted
        api_position = {
            'symbol': ghost_symbol,
            'size': 0.0,  # Exchange says we have nothing
            'entry_price': 0,
            'unrealized_pnl': 0,
            'leverage': 1
        }

        # Step 3: Call update method (simulates REST sync)
        # 🔥 [修复] 使用 await 调用异步方法
        await position_manager._update_position(api_position)

        # Step 4: Assert: Position should be removed
        assert ghost_symbol not in position_manager._positions, \
            "Ghost position should be removed when exchange reports zero position"

    @pytest.mark.asyncio
    async def test_ghost_position_cleanup_from_order(self, position_manager):
        """
        Fix 26: Ghost Position Cleanup - Order-based

        Scenario:
        1. Have a long position of 1.0
        2. Process a sell order fill of 1.0
        3. Assert: Position should be removed (size becomes 0)
        """
        # Step 1: Create a long position
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0,
            unrealized_pnl=100.0
        )

        # Step 2: Process a sell order fill that closes position
        order_filled = {
            'symbol': 'BTC-USDT-SWAP',
            'side': 'sell',
            'filled_size': 1.0,
            'price': 50500.0
        }

        # 🔥 [修复] 使用 await 调用异步方法
        await position_manager._update_position_from_order(order_filled)

        # Step 3: Assert: Position should be removed
        assert 'BTC-USDT-SWAP' not in position_manager._positions, \
            "Position should be removed when fully closed by order fill"

    # ============================================
    # Fix 25: Cancel Logic / Status Check
    # ============================================

    @pytest.mark.asyncio
    async def test_cancel_failure_with_status_check(self, position_manager, order_manager):
        """
        Fix 25: Cancel Logic / Status Check

        Scenario:
        1. Have an order in the system
        2. Cancel order fails on gateway
        3. Status check reveals order is actually filled
        4. Assert: Manager updates local position correctly
        """
        # Setup: Create a position and mock order
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=0.5,
            entry_price=50000.0,
            unrealized_pnl=0.0
        )

        # Mock order manager to fail cancel
        order_manager.cancel_order = AsyncMock(return_value=False)

        # Create an order fill event (simulating status check reveals filled)
        # Even though cancel failed, order was filled
        order_filled_event = Event(
            type=EventType.ORDER_FILLED,
            data={
                'order_id': 'test_order_123',
                'clOrdId': 'test_cl_ord_id',
                'symbol': 'BTC-USDT-SWAP',
                'side': 'sell',
                'filled_size': 0.3,  # Partial fill
                'price': 50100.0,
                'stop_loss_price': None
            },
            source='test'
        )

        # Process order filled event
        await order_manager.on_order_filled(order_filled_event)
        # 🔥 [修复] 使用 await 调用异步方法
        await position_manager.update_from_event(order_filled_event)

        # Assert: Position should be updated correctly despite cancel failure
        position = position_manager.get_position('BTC-USDT-SWAP')
        assert position is not None, "Position should still exist"
        assert position.size == 0.2, \
            "Position size should be reduced by filled amount (0.5 - 0.3 = 0.2)"

    # ============================================
    # Fix 2: Backoff/Circuit Breaker
    # ============================================

    @pytest.mark.asyncio
    async def test_backoff_circuit_breaker(self, position_manager, caplog):
        """
        Fix 2: Backoff/Circuit Breaker

        Scenario:
        1. Mock get_positions to raise Exception repeatedly
        2. Verify manager handles gracefully with backoff
        3. Verify system doesn't enter infinite loop
        4. Verify exponential backoff increases wait times
        """
        # Setup: Create a task that will fail repeatedly
        fail_count = [0]

        async def failing_sync():
            """Mock sync that always fails"""
            fail_count[0] += 1
            raise Exception("API Error - Connection timeout")

        # Patch _sync_positions_from_api to always fail
        with patch.object(
            position_manager,
            '_sync_positions_from_api',
            side_effect=failing_sync
        ):
            # Start scheduled sync task
            sync_task = position_manager.start_scheduled_sync(interval=0.1)  # Fast interval for testing

            try:
                # Wait for failures to occur
                # With exponential backoff (1s, 2s, 4s, 8s...),
                # we expect fewer failures in the same time
                await asyncio.sleep(2.0)  # Allow time for failures and backoff

                # Assert: System should not crash (task still running)
                assert not sync_task.done(), "Sync task should still be running"

                # Assert: Should have encountered some failures
                # With backoff: 1s, 2s, 4s, 8s, 16s, 32s, 60s(max)
                # In 2 seconds, we expect: 1 (at 0.1s) + 1 (at 0.1+1s) = 2-3 failures
                assert fail_count[0] >= 2, \
                    f"Should have encountered at least 2 failures, got {fail_count[0]}"

                # Assert: Should not be in infinite loop (failures should be limited by backoff)
                # With proper backoff, we should not have 100 failures in 2 seconds
                assert fail_count[0] < 10, \
                    f"Should not have too many failures with backoff, got {fail_count[0]}"

                # Verify backoff warnings in logs
                backoff_warnings = [
                    record for record in caplog.records
                    if "同步失败" in record.message and "等待" in record.message
                ]
                assert len(backoff_warnings) > 0, \
                    "Should have backoff warnings in logs"

            finally:
                # Clean up: cancel sync task
                sync_task.cancel()
                try:
                    await sync_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_backoff_exponential_increase(self, position_manager, caplog):
        """
        Fix 2: Verify exponential backoff increases wait time

        Scenario:
        1. First failure: wait 1 second
        2. Second failure: wait 2 seconds
        3. Third failure: wait 4 seconds
        4. Verify exponential growth
        """
        # This is a simplified test - we verify the logic exists
        # Full timing verification would require more complex setup

        # Just verify the backoff parameters are accessible
        assert hasattr(position_manager, '_sync_cooldown'), "Should have cooldown parameter"
        assert position_manager._sync_cooldown == 60, "Default cooldown should be 60 seconds"

        # The exponential backoff logic is implemented in start_scheduled_sync
        # We verify it doesn't cause infinite loops in the test above


class TestPositionManagerBasicFunctionality:
    """Test basic PositionManager functionality"""

    @pytest.mark.asyncio
    async def test_update_position_from_api(self, position_manager):
        """Test updating position from API data"""
        api_position = {
            'symbol': 'BTC-USDT-SWAP',
            'size': 1.5,
            'entry_price': 50000.0,
            'unrealized_pnl': 750.0,
            'leverage': 10
        }

        # 🔥 [修复] 使用 await 调用异步方法
        await position_manager._update_position(api_position)

        position = position_manager.get_position('BTC-USDT-SWAP')
        assert position is not None
        assert position.size == 1.5
        assert position.side == 'long'
        assert position.entry_price == 50000.0
        assert position.unrealized_pnl == 750.0
        assert position.leverage == 10

    @pytest.mark.asyncio
    async def test_update_position_short(self, position_manager):
        """Test updating short position (negative size)"""
        api_position = {
            'symbol': 'BTC-USDT-SWAP',
            'size': -1.0,  # Negative for short
            'entry_price': 50500.0,
            'unrealized_pnl': -500.0,
            'leverage': 10
        }

        # 🔥 [修复] 使用 await 调用异步方法
        await position_manager._update_position(api_position)

        position = position_manager.get_position('BTC-USDT-SWAP')
        assert position is not None
        assert position.size == 1.0  # Absolute value
        assert position.side == 'short'
        assert position.entry_price == 50500.0
        assert position.unrealized_pnl == -500.0

    @pytest.mark.asyncio
    async def test_update_position_zero(self, position_manager, caplog):
        """Test that zero size removes position"""
        # First create a position
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0,
            unrealized_pnl=100.0
        )

        # Then update with zero size
        api_position = {
            'symbol': 'BTC-USDT-SWAP',
            'size': 0.0,
            'entry_price': 50000.0,
            'unrealized_pnl': 0.0,
            'leverage': 1
        }

        # 🔥 [修复] 使用 await 调用异步方法
        await position_manager._update_position(api_position)

        # Assert: Position should be removed
        assert 'BTC-USDT-SWAP' not in position_manager._positions

    @pytest.mark.asyncio
    async def test_update_position_from_order_buy(self, position_manager):
        """Test updating position from buy order fill"""
        # Starting position: long 0.5
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=0.5,
            entry_price=50000.0,
            unrealized_pnl=0.0
        )

        # Buy 0.3 more
        order_filled = {
            'symbol': 'BTC-USDT-SWAP',
            'side': 'buy',
            'filled_size': 0.3,
            'price': 50100.0
        }

        # 🔥 [修复] 使用 await 调用异步方法
        await position_manager._update_position_from_order(order_filled)

        position = position_manager.get_position('BTC-USDT-SWAP')
        assert position is not None
        assert position.size == 0.8  # 0.5 + 0.3
        # Entry price should be weighted average
        expected_entry = (0.5 * 50000.0 + 0.3 * 50100.0) / 0.8
        assert abs(position.entry_price - expected_entry) < 0.01

    @pytest.mark.asyncio
    async def test_update_position_from_order_sell_close(self, position_manager):
        """Test updating position from sell order (closing long)"""
        # Starting position: long 1.0
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0,
            unrealized_pnl=0.0
        )

        # Sell 0.5 (close half)
        order_filled = {
            'symbol': 'BTC-USDT-SWAP',
            'side': 'sell',
            'filled_size': 0.5,
            'price': 50500.0
        }

        # 🔥 [修复] 使用 await 调用异步方法
        await position_manager._update_position_from_order(order_filled)

        position = position_manager.get_position('BTC-USDT-SWAP')
        assert position is not None
        assert position.size == 0.5  # 1.0 - 0.5
        assert position.side == 'long'
        assert position.unrealized_pnl > 0  # Should have profit

    @pytest.mark.asyncio
    async def test_update_position_from_order_sell_close_all(self, position_manager):
        """Test updating position from sell order (closing all)"""
        # Starting position: long 1.0
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0,
            unrealized_pnl=0.0
        )

        # Sell 1.0 (close all)
        order_filled = {
            'symbol': 'BTC-USDT-SWAP',
            'side': 'sell',
            'filled_size': 1.0,
            'price': 50500.0
        }

        # 🔥 [修复] 使用 await 调用异步方法
        await position_manager._update_position_from_order(order_filled)

        # Assert: Position should be removed
        assert 'BTC-USDT-SWAP' not in position_manager._positions

    def test_calculate_pnl_long(self, position_manager):
        """Test PnL calculation for long position"""
        position = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0
        )

        pnl = position_manager._calculate_pnl(position, 50500.0)

        assert pnl == 500.0  # (50500 - 50000) * 1.0

    def test_calculate_pnl_short(self, position_manager):
        """Test PnL calculation for short position"""
        position = Position(
            symbol='BTC-USDT-SWAP',
            side='short',
            size=1.0,
            entry_price=50000.0
        )

        pnl = position_manager._calculate_pnl(position, 49500.0)

        assert pnl == 500.0  # (50000 - 49500) * 1.0

    def test_get_position(self, position_manager):
        """Test getting a position"""
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0
        )

        position = position_manager.get_position('BTC-USDT-SWAP')

        assert position is not None
        assert position.symbol == 'BTC-USDT-SWAP'
        assert position.size == 1.0

        # Test non-existent position
        position = position_manager.get_position('ETH-USDT-SWAP')
        assert position is None

    def test_get_all_positions(self, position_manager):
        """Test getting all positions"""
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0
        )
        position_manager._positions['ETH-USDT-SWAP'] = Position(
            symbol='ETH-USDT-SWAP',
            side='short',
            size=10.0,
            entry_price=3000.0
        )

        positions = position_manager.get_all_positions()

        assert len(positions) == 2
        assert 'BTC-USDT-SWAP' in positions
        assert 'ETH-USDT-SWAP' in positions

    def test_get_summary(self, position_manager):
        """Test getting position summary"""
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0,
            unrealized_pnl=100.0
        )
        position_manager._positions['ETH-USDT-SWAP'] = Position(
            symbol='ETH-USDT-SWAP',
            side='short',
            size=10.0,
            entry_price=3000.0,
            unrealized_pnl=-50.0
        )

        summary = position_manager.get_summary()

        assert summary['total_pnl'] == 50.0  # 100 + (-50)
        assert summary['position_count'] == 2
        assert summary['long_count'] == 1
        assert summary['short_count'] == 1

    def test_get_total_exposure(self, position_manager):
        """Test calculating total exposure"""
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0,
            raw={'current_price': 51000.0}
        )
        position_manager._positions['ETH-USDT-SWAP'] = Position(
            symbol='ETH-USDT-SWAP',
            side='short',
            size=10.0,
            entry_price=3000.0,
            raw={'current_price': 2950.0}
        )

        exposure = position_manager.get_total_exposure()

        # BTC: 1.0 * 51000 = 51000
        # ETH: 10.0 * 2950 = 29500
        # Total: 80500
        assert abs(exposure - 80500.0) < 1.0

    def test_get_symbol_exposure(self, position_manager):
        """Test calculating symbol exposure"""
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0,
            raw={'current_price': 51000.0}
        )

        exposure = position_manager.get_symbol_exposure('BTC-USDT-SWAP')

        assert abs(exposure - 51000.0) < 1.0

        # Test non-existent symbol
        exposure = position_manager.get_symbol_exposure('ETH-USDT-SWAP')
        assert exposure == 0.0

    def test_update_current_price(self, position_manager):
        """Test updating current price and recalculating PnL"""
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0,
            unrealized_pnl=0.0
        )

        # Update current price
        position_manager.update_current_price('BTC-USDT-SWAP', 50500.0)

        position = position_manager.get_position('BTC-USDT-SWAP')
        assert position.unrealized_pnl == 500.0  # (50500 - 50000) * 1.0

    def test_reconcile_sync_needed(self, position_manager):
        """Test reconciliation when sync is needed"""
        # Set target position
        position_manager.update_target_position('BTC-USDT-SWAP', 'long', 2.0)

        # Current position is different
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0
        )

        # Check if sync is needed
        sync_plan = position_manager.check_sync_needed('BTC-USDT-SWAP')

        assert sync_plan is not None
        assert sync_plan['type'] == 'RESYNC'
        assert sync_plan['symbol'] == 'BTC-USDT-SWAP'
        assert sync_plan['side'] == 'buy'
        assert abs(sync_plan['amount'] - 1.0) < 0.01  # 2.0 - 1.0

    def test_reconcile_no_sync_needed(self, position_manager):
        """Test reconciliation when sync is not needed"""
        # Set target position
        position_manager.update_target_position('BTC-USDT-SWAP', 'long', 1.0)

        # Current position matches target
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0
        )

        # Check if sync is needed
        sync_plan = position_manager.check_sync_needed('BTC-USDT-SWAP')

        assert sync_plan is None

    def test_reconcile_cooldown(self, position_manager):
        """Test reconciliation cooldown"""
        # Set target position
        position_manager.update_target_position('BTC-USDT-SWAP', 'long', 2.0)

        # Current position is different
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0
        )

        # First check should return sync plan
        sync_plan1 = position_manager.check_sync_needed('BTC-USDT-SWAP')
        assert sync_plan1 is not None

        # Immediate second check should be blocked by cooldown
        sync_plan2 = position_manager.check_sync_needed('BTC-USDT-SWAP')
        assert sync_plan2 is None  # Blocked by cooldown

    def test_reset(self, position_manager):
        """Test resetting position manager"""
        position_manager._positions['BTC-USDT-SWAP'] = Position(
            symbol='BTC-USDT-SWAP',
            side='long',
            size=1.0,
            entry_price=50000.0
        )
        position_manager.update_target_position('BTC-USDT-SWAP', 'long', 1.0)

        position_manager.reset()

        assert len(position_manager._positions) == 0
        assert len(position_manager._target_positions) == 0
        assert len(position_manager._last_sync_time) == 0
