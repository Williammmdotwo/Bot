"""
Position Manager Tests - Zero Coverage Module
Target: Add tests to achieve 50%+ coverage with focus on error handling
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import asyncpg

from src.executor.core.position_manager import (
    check_position_exists,
    get_position_size,
    execute_force_close
)


class TestPositionManagerBasic:
    """Basic tests for position_manager.py"""

    @pytest.mark.asyncio
    async def test_check_position_exists_success(self):
        """Test checking position existence - success"""
        postgres_pool = AsyncMock()
        postgres_pool.fetch.return_value = [
            {'order_id': 'order_123', 'amount': 0.001, 'filled_amount': 0.001}
        ]

        result = await check_position_exists('BTC-USDT', 'buy', postgres_pool)

        assert result is True
        postgres_pool.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_position_exists_no_position(self):
        """Test checking position existence - no position found"""
        postgres_pool = AsyncMock()
        postgres_pool.fetch.return_value = []

        result = await check_position_exists('BTC-USDT', 'buy', postgres_pool)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_position_exists_database_error(self):
        """Test checking position existence - database error"""
        postgres_pool = AsyncMock()
        postgres_pool.fetch.side_effect = Exception("Database connection failed")

        with pytest.raises(Exception):
            await check_position_exists('BTC-USDT', 'buy', postgres_pool)

    @pytest.mark.asyncio
    async def test_get_position_size_success(self):
        """Test getting position size - success"""
        postgres_pool = AsyncMock()
        postgres_pool.fetchrow.return_value = {'total_filled': 0.005}

        result = await get_position_size('BTC-USDT', 'buy', postgres_pool)

        assert result == 0.005

    @pytest.mark.asyncio
    async def test_get_position_size_no_position(self):
        """Test getting position size - no position"""
        postgres_pool = AsyncMock()
        postgres_pool.fetchrow.return_value = None

        result = await get_position_size('BTC-USDT', 'buy', postgres_pool)

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_get_position_size_database_error(self):
        """Test getting position size - database error"""
        postgres_pool = AsyncMock()
        postgres_pool.fetchrow.side_effect = Exception("Query timeout")

        with pytest.raises(Exception):
            await get_position_size('BTC-USDT', 'buy', postgres_pool)

    @pytest.mark.asyncio
    async def test_execute_force_close_success(self):
        """Test executing force close - success"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_123',
            'status': 'closed',
            'filled': 0.005,
            'price': 95000,
            'fee': {'cost': 2.5}
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.return_value = None

        redis_client = AsyncMock()
        redis_client.publish.return_value = None

        with patch('src.executor.core.position_manager.track') as mock_track:
            mock_track.return_value = None

            result = await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0.005,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

            assert result['close_order_id'] == 'close_order_123'
            assert result['symbol'] == 'BTC-USDT'
            assert result['side'] == 'buy'
            assert result['close_side'] == 'sell'
            assert result['status'] == 'closed'

    @pytest.mark.asyncio
    async def test_execute_force_close_sell_position(self):
        """Test executing force close for sell position"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_456',
            'status': 'closed',
            'filled': 0.01,
            'price': 90000,
            'fee': {'cost': 5}
        }

        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        with patch('src.executor.core.position_manager.track'):
            result = await execute_force_close(
                symbol='BTC-USDT',
                side='sell',
                position_size=0.01,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

            assert result['close_side'] == 'buy'
            assert result['position_size'] == 0.01

    @pytest.mark.asyncio
    async def test_execute_force_close_order_creation_error(self):
        """Test executing force close - order creation error"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.side_effect = Exception("Insufficient balance")

        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        with pytest.raises(Exception):
            await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0.005,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

    @pytest.mark.asyncio
    async def test_execute_force_close_postgres_update_error(self):
        """Test executing force close - PostgreSQL update error"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_123',
            'status': 'closed',
            'filled': 0.005,
            'price': 95000,
            'fee': {'cost': 2.5}
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.side_effect = [
            None,  # First execute (insert original record) succeeds
            Exception("PostgreSQL constraint violation")  # Second execute (update) fails
        ]

        redis_client = AsyncMock()

        with pytest.raises(Exception):
            await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0.005,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

    @pytest.mark.asyncio
    async def test_execute_force_close_redis_publish_error(self):
        """Test executing force close - Redis publish error"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_123',
            'status': 'closed',
            'filled': 0.005,
            'price': 95000,
            'fee': {'cost': 2.5}
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.return_value = None

        redis_client = AsyncMock()
        redis_client.publish.side_effect = Exception("Redis connection lost")

        with patch('src.executor.core.position_manager.track'):
            with pytest.raises(Exception):
                await execute_force_close(
                    symbol='BTC-USDT',
                    side='buy',
                    position_size=0.005,
                    ccxt_exchange=ccxt_exchange,
                    postgres_pool=postgres_pool,
                    redis_client=redis_client
                )

    @pytest.mark.asyncio
    async def test_execute_force_close_track_error(self):
        """Test executing force close - track function error"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_123',
            'status': 'closed',
            'filled': 0.005,
            'price': 95000,
            'fee': {'cost': 2.5}
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.return_value = None

        redis_client = AsyncMock()
        redis_client.publish.return_value = None

        with patch('src.executor.core.position_manager.track') as mock_track:
            mock_track.side_effect = Exception("Order tracking failed")

            with pytest.raises(Exception):
                await execute_force_close(
                    symbol='BTC-USDT',
                    side='buy',
                    position_size=0.005,
                    ccxt_exchange=ccxt_exchange,
                    postgres_pool=postgres_pool,
                    redis_client=redis_client
                )

    @pytest.mark.asyncio
    async def test_execute_force_close_missing_order_fields(self):
        """Test executing force close - missing fields in order response"""
        ccxt_exchange = Mock()
        # Return order with missing fields
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_123',
            'status': 'closed'
            # Missing: filled, price, fee
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.return_value = None

        redis_client = AsyncMock()
        redis_client.publish.return_value = None

        with patch('src.executor.core.position_manager.track'):
            result = await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0.005,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

            # Should still succeed with default values (0.0)
            assert result['close_order_id'] == 'close_order_123'
            postgres_pool.execute.assert_called()  # Should have been called with default values

    @pytest.mark.asyncio
    async def test_execute_force_close_partial_fee_info(self):
        """Test executing force close - order has fee dict but missing cost"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_123',
            'status': 'closed',
            'filled': 0.005,
            'price': 95000,
            'fee': {}  # Empty fee dict
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.return_value = None

        redis_client = AsyncMock()
        redis_client.publish.return_value = None

        with patch('src.executor.core.position_manager.track'):
            result = await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0.005,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

            assert result['close_order_id'] == 'close_order_123'

    @pytest.mark.asyncio
    async def test_execute_force_close_no_fee(self):
        """Test executing force close - order without fee field"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_123',
            'status': 'closed',
            'filled': 0.005,
            'price': 95000
            # No fee field at all
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.return_value = None

        redis_client = AsyncMock()
        redis_client.publish.return_value = None

        with patch('src.executor.core.position_manager.track'):
            result = await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0.005,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

            assert result['close_order_id'] == 'close_order_123'


class TestPositionManagerEdgeCases:
    """Edge case tests for position_manager.py"""

    @pytest.mark.asyncio
    async def test_check_position_exists_empty_result(self):
        """Test with None or empty result from database"""
        postgres_pool = AsyncMock()
        postgres_pool.fetch.return_value = []  # Return empty list instead of None

        result = await check_position_exists('BTC-USDT', 'buy', postgres_pool)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_position_size_invalid_float(self):
        """Test handling of invalid float values"""
        postgres_pool = AsyncMock()
        # Return string instead of float
        postgres_pool.fetchrow.side_effect = [
            {'total_filled': '0.005'},  # String
            {'total_filled': None},     # None
        ]

        result1 = await get_position_size('BTC-USDT', 'buy', postgres_pool)
        # Since float('0.005') = 0.005, this will work
        # But if we want to test invalid conversion...

        postgres_pool.fetchrow.side_effect = None
        postgres_pool.fetchrow.return_value = {'total_filled': 'invalid'}

        # This will raise ValueError when converting to float
        with pytest.raises((ValueError, TypeError)):
            await get_position_size('BTC-USDT', 'buy', postgres_pool)

    @pytest.mark.asyncio
    async def test_execute_force_close_zero_position_size(self):
        """Test force close with zero position size"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_000',
            'status': 'closed',
            'filled': 0,
            'price': 95000,
            'fee': {'cost': 0}
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.return_value = None

        redis_client = AsyncMock()
        redis_client.publish.return_value = None

        with patch('src.executor.core.position_manager.track'):
            result = await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

            assert result['position_size'] == 0

    @pytest.mark.asyncio
    async def test_execute_force_close_negative_position_size(self):
        """Test force close with negative position size (error case)"""
        ccxt_exchange = Mock()
        # Exchange might reject negative amount
        ccxt_exchange.create_market_order.side_effect = Exception("Invalid amount")

        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        with pytest.raises(Exception):
            await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=-0.005,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

    @pytest.mark.asyncio
    async def test_execute_force_close_very_small_position(self):
        """Test force close with very small position size"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_789',
            'status': 'closed',
            'filled': 0.000001,
            'price': 95000,
            'fee': {'cost': 0.0005}
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.return_value = None

        redis_client = AsyncMock()
        redis_client.publish.return_value = None

        with patch('src.executor.core.position_manager.track'):
            result = await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0.000001,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

            assert result['position_size'] == 0.000001

    @pytest.mark.asyncio
    async def test_execute_force_close_multiple_records_update(self):
        """Test that update affects multiple records if they exist"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_multi',
            'status': 'closed',
            'filled': 0.015,
            'price': 95000,
            'fee': {'cost': 7.5}
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.return_value = None

        redis_client = AsyncMock()
        redis_client.publish.return_value = None

        with patch('src.executor.core.position_manager.track'):
            result = await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0.015,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

            # Should have called execute twice (update + insert)
            assert postgres_pool.execute.call_count == 2
            assert result['close_order_id'] == 'close_order_multi'

    @pytest.mark.asyncio
    async def test_check_position_symbols_with_hyphens_and_slashes(self):
        """Test position checking with various symbol formats"""
        postgres_pool = AsyncMock()
        postgres_pool.fetch.return_value = [{'order_id': 'test'}]

        # Test different symbol formats
        symbols = ['BTC-USDT', 'ETH/USDT', 'SOL-USDT', 'ADA/USDT']

        for symbol in symbols:
            result = await check_position_exists(symbol, 'buy', postgres_pool)
            assert result is True

    @pytest.mark.asyncio
    async def test_execute_force_close_database_connection_lost(self):
        """Test database connection lost during operation"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_123',
            'status': 'closed',
            'filled': 0.005,
            'price': 95000,
            'fee': {'cost': 2.5}
        }

        postgres_pool = AsyncMock()
        # First call succeeds (create order record), second fails (update)
        postgres_pool.execute.side_effect = [None, asyncpg.exceptions.ConnectionDoesNotExistError()]

        redis_client = AsyncMock()

        with pytest.raises(Exception):
            await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0.005,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

    @pytest.mark.asyncio
    async def test_get_position_size_multiple_positions(self):
        """Test getting total position size when multiple trades exist"""
        postgres_pool = AsyncMock()
        postgres_pool.fetchrow.return_value = {'total_filled': 0.05}

        result = await get_position_size('BTC-USDT', 'buy', postgres_pool)

        assert result == 0.05

    @pytest.mark.asyncio
    async def test_execute_force_close_order_rejected_by_exchange(self):
        """Test when exchange rejects the close order"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.side_effect = Exception("Order rejected: insufficient balance")

        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        with pytest.raises(Exception):
            await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0.005,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )
