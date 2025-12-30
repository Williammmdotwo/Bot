"""
Emergency Actions Tests - Zero Coverage Module
Target: Add tests to achieve 70%+ coverage with focus on error handling
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import ccxt

from src.risk_manager.actions.emergency_actions import (
    emergency_close_position,
    get_current_position_size,
    validate_emergency_close_params,
    _log_successful_close_to_db,
    _log_failed_close_to_db
)


class TestEmergencyActionsBasic:
    """Basic tests for emergency_actions.py"""

    @pytest.mark.asyncio
    async def test_emergency_close_position_success(self):
        """Test successful emergency close position"""
        mock_postgres_pool = AsyncMock()
        mock_postgres_pool.execute.return_value = None

        mock_exchange = Mock(spec=ccxt.Exchange)
        mock_exchange.create_market_order.return_value = {
            'id': 'emergency_close_123',
            'status': 'closed',
            'filled': 0.005,
            'price': 95000
        }
        mock_exchange.fetch_positions.return_value = [
            {
                'symbol': 'BTC-USDT-SWAP',
                'side': 'buy',
                'contracts': '0.005'
            }
        ]

        mock_config = {
            'environment_type': 'production',
            'risk_api_key': 'test_key',
            'risk_secret': 'test_secret',
            'risk_passphrase': 'test_passphrase'
        }

        with patch('src.risk_manager.actions.emergency_actions.os.getenv', return_value='test'):
            with patch('src.risk_manager.actions.emergency_actions.get_config', return_value=mock_config):
                with patch('ccxt.okx', return_value=mock_exchange):
                    result = await emergency_close_position(
                        symbol='BTC-USDT-SWAP',  # Use full symbol name
                        side='buy',
                        postgres_pool=mock_postgres_pool,
                        config=mock_config
                    )

        assert result is True

    @pytest.mark.asyncio
    async def test_emergency_close_position_sell_position(self):
        """Test emergency close for sell position"""
        mock_postgres_pool = AsyncMock()
        mock_postgres_pool.execute.return_value = None

        mock_exchange = Mock(spec=ccxt.Exchange)
        mock_exchange.create_market_order.return_value = {
            'id': 'emergency_close_456',
            'status': 'closed',
            'filled': 0.01,
            'price': 91000
        }
        mock_exchange.fetch_positions.return_value = [
            {
                'symbol': 'BTC-USDT-SWAP',
                'side': 'sell',
                'contracts': '0.01'
            }
        ]

        mock_config = {
            'environment_type': 'production',
            'risk_api_key': 'test_key',
            'risk_secret': 'test_secret',
            'risk_passphrase': 'test_passphrase'
        }

        with patch('src.risk_manager.actions.emergency_actions.os.getenv', return_value='test'):
            with patch('src.risk_manager.actions.emergency_actions.get_config', return_value=mock_config):
                with patch('ccxt.okx', return_value=mock_exchange):
                    result = await emergency_close_position(
                        symbol='BTC-USDT-SWAP',
                        side='sell',
                        postgres_pool=mock_postgres_pool,
                        config=mock_config
                    )

        assert result is True

    @pytest.mark.asyncio
    async def test_emergency_close_position_no_credentials(self):
        """Test emergency close when API credentials are missing"""
        mock_postgres_pool = AsyncMock()

        mock_config = None

        with patch('src.risk_manager.actions.emergency_actions.os.getenv', return_value=''):  # Empty credential
            with patch('src.risk_manager.actions.emergency_actions.get_config', return_value=None):
                result = await emergency_close_position(
                    symbol='BTC-USDT',
                    side='buy',
                    postgres_pool=mock_postgres_pool,
                    config=mock_config
                )

        assert result is False
        mock_postgres_pool.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_emergency_close_position_no_position_found(self):
        """Test emergency close when no position is found"""
        mock_postgres_pool = AsyncMock()
        mock_postgres_pool.execute.return_value = None

        mock_exchange = Mock(spec=ccxt.Exchange)
        mock_exchange.fetch_positions.return_value = []

        mock_config = {
            'environment_type': 'production',
            'risk_api_key': 'test_key',
            'risk_secret': 'test_secret',
            'risk_passphrase': 'test_passphrase'
        }

        with patch('src.risk_manager.actions.emergency_actions.os.getenv', return_value='test'):
            with patch('src.risk_manager.actions.emergency_actions.get_config', return_value=mock_config):
                with patch('ccxt.okx', return_value=mock_exchange):
                    result = await emergency_close_position(
                        symbol='BTC-USDT-SWAP',
                        side='buy',
                        postgres_pool=mock_postgres_pool,
                        config=mock_config
                    )

        assert result is False
        mock_postgres_pool.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_emergency_close_position_okx_init_failed(self):
        """Test emergency close when OKX client initialization fails"""
        mock_postgres_pool = AsyncMock()

        mock_config = {
            'environment_type': 'production',
            'risk_api_key': 'test_key',
            'risk_secret': 'test_secret',
            'risk_passphrase': 'test_passphrase'
        }

        with patch('src.risk_manager.actions.emergency_actions.os.getenv', return_value='test'):
            with patch('src.risk_manager.actions.emergency_actions.get_config', return_value=mock_config):
                with patch('ccxt.okx', side_effect=Exception("OKX initialization failed")):
                    result = await emergency_close_position(
                        symbol='BTC-USDT',
                        side='buy',
                        postgres_pool=mock_postgres_pool,
                        config=mock_config
                    )

        assert result is False

    @pytest.mark.asyncio
    async def test_emergency_close_position_order_creation_failed(self):
        """Test emergency close when order creation fails"""
        mock_postgres_pool = AsyncMock()
        mock_postgres_pool.execute.return_value = None

        mock_exchange = Mock(spec=ccxt.Exchange)
        mock_exchange.create_market_order.side_effect = Exception("Order creation failed")
        mock_exchange.fetch_positions.return_value = [
            {
                'symbol': 'BTC-USDT-SWAP',
                'side': 'buy',
                'contracts': '0.005'
            }
        ]

        mock_config = {
            'environment_type': 'production',
            'risk_api_key': 'test_key',
            'risk_secret': 'test_secret',
            'risk_passphrase': 'test_passphrase'
        }

        with patch('src.risk_manager.actions.emergency_actions.os.getenv', return_value='test'):
            with patch('src.risk_manager.actions.emergency_actions.get_config', return_value=mock_config):
                with patch('ccxt.okx', return_value=mock_exchange):
                    result = await emergency_close_position(
                        symbol='BTC-USDT-SWAP',
                        side='buy',
                        postgres_pool=mock_postgres_pool,
                        config=mock_config
                    )

        assert result is False

    @pytest.mark.asyncio
    async def test_emergency_close_position_database_error(self):
        """Test emergency close when database error occurs during logging"""
        mock_postgres_pool = AsyncMock()
        mock_postgres_pool.execute.side_effect = Exception("Database connection lost")

        mock_exchange = Mock(spec=ccxt.Exchange)
        mock_exchange.create_market_order.return_value = {
            'id': 'emergency_close_999',
            'status': 'closed',
            'filled': 0.005,
            'price': 95000
        }
        mock_exchange.fetch_positions.return_value = [
            {
                'symbol': 'BTC-USDT-SWAP',
                'side': 'buy',
                'contracts': '0.005'
            }
        ]

        mock_config = {
            'environment_type': 'production',
            'risk_api_key': 'test_key',
            'risk_secret': 'test_secret',
            'risk_passphrase': 'test_passphrase'
        }

        with patch('src.risk_manager.actions.emergency_actions.os.getenv', return_value='test'):
            with patch('src.risk_manager.actions.emergency_actions.get_config', return_value=mock_config):
                with patch('ccxt.okx', return_value=mock_exchange):
                    result = await emergency_close_position(
                        symbol='BTC-USDT-SWAP',
                        side='buy',
                        postgres_pool=mock_postgres_pool,
                        config=mock_config
                    )

        assert result is False


class TestEmergencyActionsErrorHandling:
    """Error handling tests for emergency_actions.py"""

    @pytest.mark.asyncio
    async def test_emergency_close_position_fetch_positions_failed(self):
        """Test emergency close when fetching positions fails"""
        mock_postgres_pool = AsyncMock()

        mock_exchange = Mock(spec=ccxt.Exchange)
        mock_exchange.fetch_positions.side_effect = Exception("Network error")

        mock_config = {
            'environment_type': 'production',
            'risk_api_key': 'test_key',
            'risk_secret': 'test_secret',
            'risk_passphrase': 'test_passphrase'
        }

        with patch('src.risk_manager.actions.emergency_actions.os.getenv', return_value='test'):
            with patch('src.risk_manager.actions.emergency_actions.get_config', return_value=mock_config):
                with patch('ccxt.okx', return_value=mock_exchange):
                    result = await emergency_close_position(
                        symbol='BTC-USDT',
                        side='buy',
                        postgres_pool=mock_postgres_pool,
                        config=mock_config
                    )

        assert result is False

    @pytest.mark.asyncio
    async def test_emergency_close_position_insert_failed_after_order(self):
        """Test emergency close when database insert fails after order creation"""
        mock_postgres_pool = AsyncMock()
        mock_postgres_pool.execute.side_effect = Exception("Database insert failed")

        mock_exchange = Mock(spec=ccxt.Exchange)
        mock_exchange.create_market_order.return_value = {
            'id': 'emergency_close_789',
            'status': 'closed',
            'filled': 0.005,
            'price': 95000
        }
        mock_exchange.fetch_positions.return_value = [
            {
                'symbol': 'BTC-USDT-SWAP',
                'side': 'buy',
                'contracts': '0.005'
            }
        ]

        mock_config = {
            'environment_type': 'production',
            'risk_api_key': 'test_key',
            'risk_secret': 'test_secret',
            'risk_passphrase': 'test_passphrase'
        }

        with patch('src.risk_manager.actions.emergency_actions.os.getenv', return_value='test'):
            with patch('src.risk_manager.actions.emergency_actions.get_config', return_value=mock_config):
                with patch('ccxt.okx', return_value=mock_exchange):
                    result = await emergency_close_position(
                        symbol='BTC-USDT-SWAP',
                        side='buy',
                        postgres_pool=mock_postgres_pool,
                        config=mock_config
                    )

        assert result is False


class TestGetCurrentPositionSize:
    """Tests for get_current_position_size function"""

    def test_get_current_position_size_success(self):
        """Test getting current position size successfully"""
        mock_exchange = Mock(spec=ccxt.Exchange)
        mock_exchange.fetch_positions.return_value = [
            {
                'symbol': 'BTC-USDT-SWAP',
                'side': 'buy',
                'contracts': '0.005'
            }
        ]

        result = get_current_position_size(
            symbol='BTC-USDT-SWAP',
            side='buy',
            exchange=mock_exchange
        )

        assert result == 0.005

    def test_get_current_position_size_no_position(self):
        """Test getting position size when no position exists"""
        mock_exchange = Mock(spec=ccxt.Exchange)
        mock_exchange.fetch_positions.return_value = [
            {
                'symbol': 'ETH-USDT-SWAP',
                'side': 'buy',
                'contracts': '0.01'
            }
        ]

        result = get_current_position_size(
            symbol='BTC-USDT',
            side='buy',
            exchange=mock_exchange
        )

        assert result == 0.0

    def test_get_current_position_size_fetch_error(self):
        """Test getting position size when fetch fails"""
        mock_exchange = Mock(spec=ccxt.Exchange)
        mock_exchange.fetch_positions.side_effect = Exception("Network error")

        result = get_current_position_size(
            symbol='BTC-USDT',
            side='buy',
            exchange=mock_exchange
        )

        assert result == 0.0

    def test_get_current_position_size_zero_contracts(self):
        """Test getting position size when contracts are zero"""
        mock_exchange = Mock(spec=ccxt.Exchange)
        mock_exchange.fetch_positions.return_value = [
            {
                'symbol': 'BTC-USDT-SWAP',
                'side': 'buy',
                'contracts': '0'
            }
        ]

        result = get_current_position_size(
            symbol='BTC-USDT',
            side='buy',
            exchange=mock_exchange
        )

        assert result == 0.0


class TestValidateEmergencyCloseParams:
    """Tests for validate_emergency_close_params function"""

    def test_validate_emergency_close_params_success(self):
        """Test validation of emergency close parameters"""
        assert validate_emergency_close_params(symbol='BTC-USDT', side='buy') is True
        assert validate_emergency_close_params(symbol='BTC-USDT', side='sell') is True
        assert validate_emergency_close_params(symbol='ETH-USDT', side='buy') is True
        assert validate_emergency_close_params(symbol='ETH-USDT', side='sell') is True

    def test_validate_emergency_close_params_empty_symbol(self):
        """Test validation with empty symbol"""
        assert validate_emergency_close_params(symbol='', side='buy') is False
        assert validate_emergency_close_params(symbol=None, side='buy') is False

    def test_validate_emergency_close_params_empty_side(self):
        """Test validation with empty side"""
        assert validate_emergency_close_params(symbol='BTC-USDT', side='') is False
        assert validate_emergency_close_params(symbol='BTC-USDT', side=None) is False

    def test_validate_emergency_close_params_invalid_side(self):
        """Test validation with invalid side"""
        assert validate_emergency_close_params(symbol='BTC-USDT', side='invalid') is False
        assert validate_emergency_close_params(symbol='BTC-USDT', side='INVALID') is False
        assert validate_emergency_close_params(symbol='BTC-USDT', side='wrong') is False


class TestLogHelpers:
    """Tests for helper log functions"""

    @pytest.mark.asyncio
    async def test_log_successful_close_to_db(self):
        """Test _log_successful_close_to_db"""
        mock_postgres_pool = AsyncMock()
        mock_postgres_pool.execute.return_value = None

        order = {
            'id': 'test_order_123',
            'status': 'closed',
            'filled': 0.005,
            'price': 95000,
            'fee': {'cost': 0.05}
        }

        await _log_successful_close_to_db(
            symbol='BTC-USDT',
            original_side='buy',
            close_side='sell',
            position_size=0.005,
            order=order,
            postgres_pool=mock_postgres_pool
        )

        assert mock_postgres_pool.execute.called

    @pytest.mark.asyncio
    async def test_log_failed_close_to_db(self):
        """Test _log_failed_close_to_db"""
        mock_postgres_pool = AsyncMock()
        mock_postgres_pool.execute.return_value = None

        await _log_failed_close_to_db(
            symbol='BTC-USDT',
            original_side='buy',
            close_side='sell',
            position_size=0.005,
            error_msg='Order creation failed',
            postgres_pool=mock_postgres_pool
        )

        assert mock_postgres_pool.execute.called
