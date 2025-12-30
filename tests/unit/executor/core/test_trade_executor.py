"""
Trade Executor Tests - Zero Coverage Module
Target: Add tests to achieve 80%+ coverage with focus on error handling
"""

import pytest
import asyncio
import asyncpg
from unittest.mock import Mock, AsyncMock, patch

from src.executor.core.trade_executor import execute_trade_logic


class TestTradeExecutorBasic:
    """Basic tests for trade_executor.py"""

    @pytest.mark.asyncio
    async def test_execute_trade_logic_buy_signal(self):
        """Test BUY signal execution"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.return_value = {'id': 'order_123', 'status': 'open', 'price': 90000}
        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'BUY',
            'symbol': 'BTC-USDT',
            'confidence': 75.0,
            'decision_id': 'decision_001'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=True,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] == 'simulated'
        assert result['symbol'] == 'BTC-USDT'
        assert result['side'] == 'buy'

    @pytest.mark.asyncio
    async def test_execute_trade_logic_sell_signal(self):
        """Test SELL signal execution"""
        ccxt_exchange = Mock()
        ccxt_exchange.create_market_order.return_value = {'id': 'order_456', 'status': 'open', 'price': 91000}
        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'SELL',
            'symbol': 'BTC-USDT',
            'confidence': 80.0,
            'decision_id': 'decision_002'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=True,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] == 'simulated'
        assert result['side'] == 'sell'

    @pytest.mark.asyncio
    async def test_execute_trade_logic_hold_signal(self):
        """Test HOLD signal (should be ignored)"""
        ccxt_exchange = Mock()
        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'HOLD',
            'symbol': 'BTC-USDT',
            'decision_id': 'decision_003'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] == 'ignored'
        assert result['order_id'] is None

    @pytest.mark.asyncio
    async def test_execute_trade_logic_exception_handling(self):
        """Test exception handling - ccxt network error"""
        ccxt_exchange = Mock()
        ccxt_exchange.apiKey = 'test_key'
        ccxt_exchange.mock_mode = False
        ccxt_exchange.create_market_order.side_effect = Exception("Network error")
        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'BUY',
            'symbol': 'BTC-USDT',
            'confidence': 70.0,
            'decision_id': 'decision_007'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] == 'failed'
        assert 'Network error' in result['message']

    @pytest.mark.asyncio
    async def test_execute_trade_logic_demo_mode(self):
        """Test demo mode (should simulate)"""
        ccxt_exchange = Mock()
        ccxt_exchange.mock_mode = True
        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'BUY',
            'symbol': 'BTC-USDT',
            'confidence': 60.0,
            'decision_id': 'decision_005'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] == 'simulated'
        assert 'demo_' in result['order_id']

    @pytest.mark.asyncio
    async def test_execute_trade_logic_missing_fields(self):
        """Test missing fields handling"""
        ccxt_exchange = Mock()
        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'symbol': 'BTC-USDT',
            'confidence': 75.0
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] in ['ignored', 'simulated', 'executed']


class TestTradeExecutorErrorHandling:
    """Error handling tests for trade_executor.py"""

    @pytest.mark.asyncio
    async def test_execute_trade_logic_postgres_error(self):
        """Test PostgreSQL insert error"""
        ccxt_exchange = Mock()
        ccxt_exchange.apiKey = 'test_key'
        ccxt_exchange.mock_mode = False
        ccxt_exchange.create_market_order.return_value = {
            'id': 'order_789',
            'status': 'open',
            'price': 90000
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.side_effect = Exception("Database connection lost")
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'BUY',
            'symbol': 'BTC-USDT',
            'confidence': 75.0,
            'decision_id': 'decision_error_001'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] == 'failed'
        assert 'Trade execution failed' in result['message']

    @pytest.mark.asyncio
    async def test_execute_trade_logic_redis_publish_error(self):
        """Test Redis publish error"""
        ccxt_exchange = Mock()
        ccxt_exchange.apiKey = 'test_key'
        ccxt_exchange.mock_mode = False
        ccxt_exchange.create_market_order.return_value = {
            'id': 'order_999',
            'status': 'open',
            'price': 90000
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.return_value = None

        redis_client = AsyncMock()
        redis_client.publish.side_effect = Exception("Redis connection timeout")

        signal_data = {
            'signal': 'BUY',
            'symbol': 'BTC-USDT',
            'confidence': 85.0,
            'decision_id': 'decision_error_002'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] == 'failed'
        assert 'Trade execution failed' in result['message']

    @pytest.mark.asyncio
    async def test_execute_trade_logic_track_error(self):
        """Test track function error"""
        ccxt_exchange = Mock()
        ccxt_exchange.apiKey = 'test_key'
        ccxt_exchange.mock_mode = False
        ccxt_exchange.create_market_order.return_value = {
            'id': 'order_track_err',
            'status': 'open',
            'price': 90000
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.return_value = None

        redis_client = AsyncMock()
        redis_client.publish.return_value = None

        with patch('src.executor.core.trade_executor.track') as mock_track:
            mock_track.side_effect = Exception("Order tracking service unavailable")

            signal_data = {
                'signal': 'BUY',
                'symbol': 'BTC-USDT',
                'confidence': 90.0,
                'decision_id': 'decision_error_003'
            }

            result = await execute_trade_logic(
                signal_data=signal_data,
                use_demo=False,
                stop_loss_pct=0.03,
                take_profit_pct=0.06,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

            assert result['status'] == 'failed'

    @pytest.mark.asyncio
    async def test_execute_trade_logic_order_response_missing_fields(self):
        """Test order response with missing fields"""
        ccxt_exchange = Mock()
        ccxt_exchange.apiKey = 'test_key'
        ccxt_exchange.mock_mode = False
        ccxt_exchange.create_market_order.return_value = {
            'id': 'order_no_fields',
            'status': 'open'
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.return_value = None

        redis_client = AsyncMock()
        redis_client.publish.return_value = None

        with patch('src.executor.core.trade_executor.track'):
            signal_data = {
                'signal': 'BUY',
                'symbol': 'BTC-USDT',
                'confidence': 70.0,
                'decision_id': 'decision_error_004'
            }

            result = await execute_trade_logic(
                signal_data=signal_data,
                use_demo=False,
                stop_loss_pct=0.03,
                take_profit_pct=0.06,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

            assert result['status'] == 'executed'
            # price will be None since it's missing in order response
            assert result.get('price') is None

    @pytest.mark.asyncio
    async def test_execute_trade_logic_partial_failure(self):
        """Test partial failure - Redis fails but order was created"""
        ccxt_exchange = Mock()
        ccxt_exchange.apiKey = 'test_key'
        ccxt_exchange.mock_mode = False
        ccxt_exchange.create_market_order.return_value = {
            'id': 'order_partial_fail',
            'status': 'open',
            'price': 90500
        }

        postgres_pool = AsyncMock()
        postgres_pool.execute.return_value = None

        redis_client = AsyncMock()
        # Redis publish fails, but order was already created
        redis_client.publish.side_effect = Exception("Redis down")

        with patch('src.executor.core.trade_executor.track'):
            signal_data = {
                'signal': 'BUY',
                'symbol': 'BTC-USDT',
                'confidence': 80.0,
                'decision_id': 'decision_error_005'
            }

            result = await execute_trade_logic(
                signal_data=signal_data,
                use_demo=False,
                stop_loss_pct=0.03,
                take_profit_pct=0.06,
                ccxt_exchange=ccxt_exchange,
                postgres_pool=postgres_pool,
                redis_client=redis_client
            )

            # Since Redis publish happens after order creation, exception is caught
            assert result['status'] == 'failed'

    @pytest.mark.asyncio
    async def test_execute_trade_logic_ccxt_network_timeout(self):
        """Test CCXT exchange network timeout"""
        ccxt_exchange = Mock()
        ccxt_exchange.apiKey = 'test_key'
        ccxt_exchange.mock_mode = False
        ccxt_exchange.create_market_order.side_effect = Exception(
            "ccxt.base.errors.NetworkError: RequestTimeout"
        )

        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'BUY',
            'symbol': 'BTC-USDT',
            'confidence': 75.0,
            'decision_id': 'decision_error_006'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] == 'failed'
        assert 'NetworkError' in result['message']

    @pytest.mark.asyncio
    async def test_execute_trade_logic_ccxt_insufficient_balance(self):
        """Test CCXT exchange insufficient balance"""
        ccxt_exchange = Mock()
        ccxt_exchange.apiKey = 'test_key'
        ccxt_exchange.mock_mode = False
        ccxt_exchange.create_market_order.side_effect = Exception(
            "ccxt.base.errors.InsufficientFunds"
        )

        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'BUY',
            'symbol': 'BTC-USDT',
            'confidence': 65.0,
            'decision_id': 'decision_error_007'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] == 'failed'
        assert 'InsufficientFunds' in result['message']

    @pytest.mark.asyncio
    async def test_execute_trade_logic_ccxt_invalid_symbol(self):
        """Test CCXT exchange invalid symbol"""
        ccxt_exchange = Mock()
        ccxt_exchange.apiKey = 'test_key'
        ccxt_exchange.mock_mode = False
        ccxt_exchange.create_market_order.side_effect = Exception(
            "ccxt.base.errors.BadSymbol"
        )

        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'BUY',
            'symbol': 'INVALID-SYMBOL',
            'confidence': 95.0,
            'decision_id': 'decision_error_008'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] == 'failed'
        assert 'BadSymbol' in result['message']


class TestTradeExecutorEdgeCases:
    """Edge case tests for trade_executor.py"""

    @pytest.mark.asyncio
    async def test_execute_trade_logic_empty_symbol(self):
        """Test with empty symbol"""
        ccxt_exchange = Mock()
        ccxt_exchange.mock_mode = True
        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'BUY',
            'symbol': '',
            'confidence': 80.0,
            'decision_id': 'decision_edge_001'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] in ['simulated', 'ignored']

    @pytest.mark.asyncio
    async def test_execute_trade_logic_confidence_zero(self):
        """Test with zero confidence"""
        ccxt_exchange = Mock()
        ccxt_exchange.mock_mode = True
        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'BUY',
            'symbol': 'BTC-USDT',
            'confidence': 0.0,
            'decision_id': 'decision_edge_002'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] == 'simulated'

    @pytest.mark.asyncio
    async def test_execute_trade_logic_confidence_negative(self):
        """Test with negative confidence (invalid)"""
        ccxt_exchange = Mock()
        ccxt_exchange.mock_mode = True
        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'BUY',
            'symbol': 'BTC-USDT',
            'confidence': -10.0,
            'decision_id': 'decision_edge_003'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] == 'simulated'

    @pytest.mark.asyncio
    async def test_execute_trade_no_api_key_no_demo(self):
        """Test without API key and not in demo mode"""
        ccxt_exchange = Mock()
        # No apiKey attribute

        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'BUY',
            'symbol': 'BTC-USDT',
            'confidence': 70.0,
            'decision_id': 'decision_edge_004'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] == 'simulated'

    @pytest.mark.asyncio
    async def test_execute_trade_invalid_signal_type(self):
        """Test with invalid signal type"""
        ccxt_exchange = Mock()
        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'INVALID',
            'symbol': 'BTC-USDT',
            'confidence': 50.0,
            'decision_id': 'decision_edge_005'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        assert result['status'] == 'ignored'

    @pytest.mark.asyncio
    async def test_execute_trade_lowercase_signal(self):
        """Test with invalid lowercase signal 'buy'"""
        ccxt_exchange = Mock()
        ccxt_exchange.mock_mode = True
        postgres_pool = AsyncMock()
        redis_client = AsyncMock()

        signal_data = {
            'signal': 'buy',
            'symbol': 'BTC-USDT',
            'confidence': 75.0,
            'decision_id': 'decision_edge_006'
        }

        result = await execute_trade_logic(
            signal_data=signal_data,
            use_demo=False,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            ccxt_exchange=ccxt_exchange,
            postgres_pool=postgres_pool,
            redis_client=redis_client
        )

        # 'buy' (lowercase) is not in ['BUY', 'SELL'], should be ignored
        assert result['status'] == 'ignored'
        assert result['side'] == 'buy'
