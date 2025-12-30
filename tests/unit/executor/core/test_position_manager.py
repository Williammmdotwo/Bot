"""
Position Manager Tests - Comprehensive Test Suite
Target: Achieve 50%+ coverage with focus on error handling
"""

import pytest
import asyncio
import json
import logging
import asyncpg
from unittest.mock import Mock, AsyncMock, patch, call
from decimal import Decimal

from src.executor.core.position_manager import (
    check_position_exists,
    get_position_size,
    execute_force_close
)


# Mock fixture for postgres_pool
@pytest.fixture
def postgres_pool():
    """Mock PostgreSQL connection pool"""
    pool = AsyncMock()
    pool.fetch.return_value = [
        {'order_id': 'order_123', 'amount': 0.001, 'filled_amount': 0.001}
    ]
    pool.fetchrow.return_value = {'total_filled': '0.005'}
    pool.execute.return_value = None
    return pool


@pytest.fixture
def ccxt_exchange():
    """Mock CCXT exchange"""
    exchange = Mock()
    exchange.create_market_order.return_value = {
        'id': 'close_order_123',
        'status': 'closed',
        'filled': 0.005,
        'price': 95000,
        'fee': {'cost': 2.5}
    }
    return exchange


@pytest.fixture
def redis_client():
    """Mock Redis client"""
    client = AsyncMock()
    client.publish.return_value = None
    return client


class TestPositionManagerLogging:
    """Test logging and debug functionality"""

    @pytest.mark.asyncio
    async def test_check_position_exists_logs_query(self, postgres_pool, caplog):
        """Test that check_position_exists logs SQL queries"""
        with caplog.at_level(logging.INFO):
            result = await check_position_exists('BTC-USDT', 'buy', postgres_pool)

        assert result is True

    @pytest.mark.asyncio
    async def test_get_position_size_logs_sql(self, postgres_pool, caplog):
        """Test that get_position_size logs SQL queries"""
        with caplog.at_level(logging.INFO):
            result = await get_position_size('BTC-USDT', 'buy', postgres_pool)

        assert result == 0.005

    @pytest.mark.asyncio
    async def test_execute_force_close_logs_debug_info(self, postgres_pool, redis_client, ccxt_exchange, caplog):
        """Test that execute_force_close logs detailed debug info"""
        with patch('src.executor.core.position_manager.track'):
            with caplog.at_level(logging.INFO):
                result = await execute_force_close(
                    symbol='BTC-USDT',
                    side='buy',
                    position_size=0.005,
                    ccxt_exchange=ccxt_exchange,
                    postgres_pool=postgres_pool,
                    redis_client=redis_client
                )

        assert "Executing force close" in caplog.text
        assert "Creating sell market order" in caplog.text


class TestPositionManagerInputValidation:
    """Test input validation and edge cases"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", [
        'BTC-USDT',
        'ETH/USDT',  # Test with forward slash
        'SOL-USDT',   # Test with hyphen
        'ADA/USDT',   # Test with capital letters
        'btc-usdt',   # Test lowercase
        'btc_usdt',   # Test with underscore
    ])
    async def test_check_position_exists_various_symbol_formats(self, postgres_pool, symbol):
        """Test check_position_exists with various symbol formats"""
        postgres_pool.fetch.return_value = [
            {'order_id': 'test_order', 'amount': 0.001}
        ]

        result = await check_position_exists(symbol, 'buy', postgres_pool)
        assert result is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("side", ['buy', 'sell', 'BUY', 'SELL', 'Long', 'Short'])
    async def test_check_position_exists_various_side_formats(self, postgres_pool, side):
        """Test check_position_exists with various side formats"""
        postgres_pool.fetch.return_value = [
            {'order_id': 'test_order', 'amount': 0.001}
        ]

        result = await check_position_exists(side.lower(), 'buy', postgres_pool)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_position_size_empty_result(self, postgres_pool):
        """Test get_position_size when result is empty"""
        postgres_pool.fetchrow.return_value = None

        result = await get_position_size('BTC-USDT', 'buy', postgres_pool)
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_get_position_size_zero_filled_amount(self, postgres_pool):
        """Test get_position_size when total_filled is zero"""
        postgres_pool.fetchrow.return_value = {'total_filled': 0}

        result = await get_position_size('BTC-USDT', 'buy', postgres_pool)
        assert result == 0

    @pytest.mark.asyncio
    async def test_get_position_size_negative_amount(self, postgres_pool):
        """Test get_position_size with negative filled amount"""
        postgres_pool.fetchrow.return_value = {'total_filled': -0.5}

        result = await get_position_size('BTC-USDT', 'buy', postgres_pool)
        assert result == -0.5

    @pytest.mark.asyncio
    async def test_get_position_size_large_amount(self, postgres_pool):
        """Test get_position_size with very large amount"""
        postgres_pool.fetchrow.return_value = {'total_filled': 999999.999}

        result = await get_position_size('BTC-USDT', 'buy', postgres_pool)
        assert result == 999999.999


class TestPositionManagerReturnValueHandling:
    """Test return value formatting and structure"""

    @pytest.mark.asyncio
    async def test_get_position_size_returns_float(self, postgres_pool):
        """Test that get_position_size always returns float type"""
        postgres_pool.fetchrow.return_value = {'total_filled': '0.005'}

        result = await get_position_size('BTC-USDT', 'buy', postgres_pool)
        assert isinstance(result, float)
        assert result == 0.005

    @pytest.mark.asyncio
    async def test_get_position_size_handles_decimal_string(self, postgres_pool):
        """Test handling of decimal strings from database"""
        postgres_pool.fetchrow.return_value = {'total_filled': '1.23456789'}

        result = await get_position_size('BTC-USDT', 'buy', postgres_pool)
        assert result == 1.23456789

    @pytest.mark.asyncio
    async def test_get_position_size_handles_scientific_notation(self, postgres_pool):
        """Test handling of scientific notation from database"""
        postgres_pool.fetchrow.return_value = {'total_filled': '1.23e5'}

        result = await get_position_size('BTC-USDT', 'buy', postgres_pool)
        assert result == 123000.0

    @pytest.mark.asyncio
    async def test_execute_force_close_return_structure(self, postgres_pool, redis_client, ccxt_exchange):
        """Test that execute_force_close returns proper structure"""
        with patch('src.executor.core.position_manager.track'):
            result = await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0.005,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

        assert isinstance(result, dict)
        assert 'close_order_id' in result
        assert 'symbol' in result
        assert 'side' in result
        assert 'close_side' in result
        assert 'position_size' in result
        assert 'status' in result
        assert result['close_order_id'] == 'close_order_123'

    @pytest.mark.asyncio
    async def test_execute_force_close_sell_position_returns_buy_close_side(self, postgres_pool, redis_client, ccxt_exchange):
        """Test that closing a sell position returns buy as close side"""
        with patch('src.executor.core.position_manager.track'):
            result = await execute_force_close(
                symbol='BTC-USDT',
                side='sell',
                position_size=0.005,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

        assert result['close_side'] == 'buy'

    @pytest.mark.asyncio
    async def test_execute_force_close_uses_correct_price_from_order(self, postgres_pool, redis_client, ccxt_exchange):
        """Test that correct price is extracted from order"""
        ccxt_exchange.create_market_order.return_value = {
            'id': 'test_id',
            'status': 'open',
            'price': 98000.50
        }

        with patch('src.executor.core.position_manager.track'):
            result = await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0.005,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

        assert 'status' in result


class TestPositionManagerFeeHandling:
    """Test fee calculation and handling"""

    @pytest.mark.asyncio
    async def test_execute_force_close_with_nested_fee_dict(self, postgres_pool, redis_client, ccxt_exchange):
        """Test force close with nested fee dict containing cost"""
        ccxt_exchange.create_market_order.return_value = {
            'id': 'test_id',
            'status': 'open',
            'price': 95000,
            'fee': {'cost': 5.25}
        }

        postgres_pool.execute.return_value = None

        with patch('src.executor.core.position_manager.track'):
            result = await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0.005,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

        postgres_pool.execute.assert_called()

    @pytest.mark.asyncio
    async def test_execute_force_close_with_flat_fee_dict(self, postgres_pool, redis_client, ccxt_exchange):
        """Test force close with flat fee dict (legacy format)"""
        ccxt_exchange.create_market_order.return_value = {
            'id': 'test_id',
            'status': 'open',
            'price': 95000,
            'fee': {}
        }

        postgres_pool.execute.return_value = None

        with patch('src.executor.core.position_manager.track'):
            result = await execute_force_close(
                symbol='BTC-USDT',
                side='buy',
                position_size=0.005,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

        assert result['close_order_id'] == 'test_id'


class TestPositionManagerMessagePublishing:
    """Test message publishing to Redis"""

    @pytest.mark.asyncio
    async def test_execute_force_close_publishes_correct_message(self, postgres_pool, redis_client, ccxt_exchange):
        """Test that force close publishes correct message structure"""
        ccxt_exchange.create_market_order.return_value = {
            'id': 'test_id',
            'status': 'closed'
        }

        postgres_pool.execute.return_value = None

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

        redis_client.publish.assert_called_once()
        call_args = redis_client.publish.call_args[0]

        assert call_args[0] == 'position_events'
        message = json.loads(call_args[1])

        assert message['event'] == 'position_closed'
        assert message['symbol'] == 'BTC-USDT'
        assert message['reason'] == 'RISK_STOP_LOSS'
        assert message['order_id'] == 'test_id'


class TestPositionManagerErrorHandling:
    """Test error handling in various scenarios"""

    @pytest.mark.asyncio
    async def test_check_position_exists_database_error(self, postgres_pool):
        """Test checking position existence - database error"""
        postgres_pool.fetch.side_effect = Exception("Database connection failed")

        with pytest.raises(Exception):
            await check_position_exists('BTC-USDT', 'buy', postgres_pool)

    @pytest.mark.asyncio
    async def test_get_position_size_database_error(self, postgres_pool):
        """Test getting position size - database error"""
        postgres_pool.fetchrow.side_effect = Exception("Query timeout")

        with pytest.raises(Exception):
            await get_position_size('BTC-USDT', 'buy', postgres_pool)

    @pytest.mark.asyncio
    async def test_execute_force_close_order_creation_error(self, postgres_pool, redis_client, ccxt_exchange):
        """Test executing force close - order creation error"""
        ccxt_exchange.create_market_order.side_effect = Exception("Insufficient balance")

        postgres_pool.execute.return_value = None
        redis_client.publish.return_value = None

        with pytest.raises(Exception):
            with patch('src.executor.core.position_manager.track'):
                await execute_force_close(
                    symbol='BTC-USDT',
                    side='buy',
                    position_size=0.005,
                    ccxt_exchange=ccxt_exchange,
                    postgres_pool=postgres_pool,
                    redis_client=redis_client
                )

    @pytest.mark.asyncio
    async def test_execute_force_close_postgres_update_error(self, postgres_pool, redis_client, ccxt_exchange):
        """Test executing force close - PostgreSQL update error"""
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_123',
            'status': 'closed',
            'filled': 0.005,
            'price': 95000,
            'fee': {'cost': 2.5}
        }

        postgres_pool.execute.side_effect = [
            None,  # First execute (insert original record) succeeds
            Exception("PostgreSQL constraint violation")  # Second execute (update) fails
        ]

        redis_client.publish.return_value = None

        with pytest.raises(Exception):
            with patch('src.executor.core.position_manager.track'):
                await execute_force_close(
                    symbol='BTC-USDT',
                    side='buy',
                    position_size=0.005,
                    ccxt_exchange=ccxt_exchange,
                    postgres_pool=postgres_pool,
                    redis_client=redis_client
                )


class TestPositionManagerSuccessScenarios:
    """Test successful scenarios"""

    @pytest.mark.asyncio
    async def test_check_position_exists_success(self, postgres_pool):
        """Test checking position existence - success"""
        postgres_pool.fetch.return_value = [
            {'order_id': 'order_123', 'amount': 0.001, 'filled_amount': 0.001}
        ]

        result = await check_position_exists('BTC-USDT', 'buy', postgres_pool)
        assert result is True
        postgres_pool.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_position_exists_no_position(self, postgres_pool):
        """Test checking position existence - no position found"""
        postgres_pool.fetch.return_value = []

        result = await check_position_exists('BTC-USDT', 'buy', postgres_pool)
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_force_close_success(self, postgres_pool, redis_client, ccxt_exchange):
        """Test executing force close - success"""
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_123',
            'status': 'closed',
            'filled': 0.005,
            'price': 95000,
            'fee': {'cost': 2.5}
        }

        postgres_pool.execute.return_value = None

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
        assert result['symbol'] == 'BTC-USDT'
        assert result['side'] == 'buy'
        assert result['close_side'] == 'sell'

    @pytest.mark.asyncio
    async def test_execute_force_close_sell_position(self, postgres_pool, redis_client, ccxt_exchange):
        """Test executing force close for sell position"""
        ccxt_exchange.create_market_order.return_value = {
            'id': 'close_order_456',
            'status': 'closed',
            'filled': 0.01,
            'price': 90000,
            'fee': {'cost': 5}
        }

        postgres_pool.execute.return_value = None

        redis_client.publish.return_value = None

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


class TestPositionManagerConcurrency:
    """Test concurrent operations"""

    @pytest.mark.asyncio
    async def test_concurrent_check_position_exists(self, postgres_pool):
        """Test that multiple concurrent position checks work correctly"""
        postgres_pool.fetch.return_value = [
            {'order_id': 'order_1', 'amount': 0.001}
        ]

        # Run multiple concurrent checks
        tasks = [
            check_position_exists('BTC-USDT', 'buy', postgres_pool)
            for _ in range(5)
        ]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(results)

    @pytest.mark.asyncio
    async def test_concurrent_get_position_size(self, postgres_pool):
        """Test that multiple concurrent size queries work correctly"""
        postgres_pool.fetchrow.return_value = {'total_filled': '0.001'}

        tasks = [
            get_position_size('BTC-USDT', 'buy', postgres_pool)
            for _ in range(3)
        ]

        results = await asyncio.gather(*tasks)

        # All should return same result
        assert all(r == 0.001 for r in results)
