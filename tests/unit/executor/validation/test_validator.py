"""
Executor验证器模块单元测试
覆盖executor/validator.py的核心功能
"""

import os
import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock

# 导入测试目标
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../..'))

from src.executor.validation.validator import validate_order_signal


class TestValidateOrderSignal:
    """validate_order_signal函数测试"""

    @pytest.fixture
    def mock_order_details(self):
        """模拟订单详情"""
        return {
            'symbol': 'BTC-USDT',
            'action': 'buy',
            'size': 0.001,
            'side': 'buy',
            'decision_id': 'test_decision_123'
        }

    @pytest.mark.asyncio
    async def test_validate_order_signal_success(self, mock_order_details):
        """测试订单验证成功"""
        # Mock risk manager的is_order_rational函数
        with patch('src.risk_manager.is_order_rational', return_value=True) as mock_is_rational:
            result = await validate_order_signal(mock_order_details, current_equity=1000.0, current_price=30000.0)

            assert result is True
            mock_is_rational.assert_called_once()
            call_args = mock_is_rational.call_args
            assert call_args[0][0] == mock_order_details
            assert call_args[0][1] == 1000.0
            assert call_args[0][2] == 30000.0

    @pytest.mark.asyncio
    async def test_validate_order_signal_rational_false(self, mock_order_details):
        """测试订单验证失败（is_order_rational返回False）"""
        with patch('src.risk_manager.is_order_rational', return_value=False) as mock_is_rational:
            with pytest.raises(ValueError, match="Order validation failed: Order is not rational"):
                await validate_order_signal(mock_order_details, current_equity=1000.0, current_price=30000.0)

            mock_is_rational.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_order_signal_import_error(self, mock_order_details):
        """测试risk_manager导入失败"""
        with patch('src.risk_manager.is_order_rational', side_effect=ImportError("Module not found")):
            with pytest.raises(ValueError, match="Risk manager not available"):
                await validate_order_signal(mock_order_details, current_equity=1000.0, current_price=30000.0)

    @pytest.mark.asyncio
    async def test_validate_order_signal_unexpected_error(self, mock_order_details):
        """测试意外错误"""
        with patch('src.risk_manager.is_order_rational', side_effect=Exception("Unexpected error")):
            with pytest.raises(ValueError, match="Unexpected error in validate_order_signal"):
                await validate_order_signal(mock_order_details, current_equity=1000.0, current_price=30000.0)

    @pytest.mark.asyncio
    async def test_validate_order_signal_without_current_price(self, mock_order_details):
        """测试不提供current_price参数"""
        with patch('src.risk_manager.is_order_rational', return_value=True) as mock_is_rational:
            result = await validate_order_signal(mock_order_details, current_equity=1000.0, current_price=None)

            assert result is True
            mock_is_rational.assert_called_once()
            call_args = mock_is_rational.call_args
            assert call_args[0][0] == mock_order_details
            assert call_args[0][1] == 1000.0
            assert call_args[0][2] is None

    @pytest.mark.asyncio
    async def test_validate_order_signal_large_order(self):
        """测试大额订单"""
        large_order = {
            'symbol': 'ETH-USDT',
            'action': 'buy',
            'size': 10.0,
            'side': 'buy',
            'decision_id': 'large_order_123'
        }

        with patch('src.risk_manager.is_order_rational', return_value=True) as mock_is_rational:
            result = await validate_order_signal(large_order, current_equity=50000.0, current_price=2000.0)

            assert result is True
            mock_is_rational.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_order_signal_sell_order(self):
        """测试卖出订单"""
        sell_order = {
            'symbol': 'BTC-USDT',
            'action': 'sell',
            'size': 0.01,
            'side': 'sell',
            'decision_id': 'sell_order_123'
        }

        with patch('src.risk_manager.is_order_rational', return_value=True) as mock_is_rational:
            result = await validate_order_signal(sell_order, current_equity=5000.0, current_price=30000.0)

            assert result is True
            mock_is_rational.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_order_signal_complex_order_details(self):
        """测试复杂订单详情"""
        complex_order = {
            'symbol': 'SOL-USDT',
            'action': 'buy',
            'size': 5.0,
            'side': 'buy',
            'decision_id': 'complex_456',
            'price': 150.0,
            'type': 'limit',
            'time_in_force': 'GTC',
            'metadata': {
                'notes': 'Test order',
                'tags': ['urgent', 'manual']
            }
        }

        with patch('src.risk_manager.is_order_rational', return_value=True) as mock_is_rational:
            result = await validate_order_signal(complex_order, current_equity=10000.0, current_price=150.0)

            assert result is True
            mock_is_rational.assert_called_once()


class TestValidatorEdgeCases:
    """验证器边缘案例测试"""

    @pytest.fixture
    def basic_order(self):
        """基础订单"""
        return {
            'symbol': 'BTC-USDT',
            'action': 'buy',
            'size': 0.001,
            'side': 'buy'
        }

    @pytest.mark.asyncio
    async def test_validate_order_signal_zero_equity(self, basic_order):
        """测试零权益"""
        with patch('src.risk_manager.is_order_rational', return_value=True):
            result = await validate_order_signal(basic_order, current_equity=0.0, current_price=30000.0)
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_order_signal_negative_equity(self, basic_order):
        """测试负权益"""
        with patch('src.risk_manager.is_order_rational', return_value=True):
            result = await validate_order_signal(basic_order, current_equity=-100.0, current_price=30000.0)
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_order_signal_very_low_price(self, basic_order):
        """测试极低价格"""
        with patch('src.risk_manager.is_order_rational', return_value=True):
            result = await validate_order_signal(basic_order, current_equity=1000.0, current_price=0.01)
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_order_signal_very_high_price(self, basic_order):
        """测试极高价格"""
        with patch('src.risk_manager.is_order_rational', return_value=True):
            result = await validate_order_signal(basic_order, current_equity=1000000.0, current_price=1000000.0)
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_order_signal_empty_order_details(self):
        """测试空订单详情"""
        empty_order = {}

        with patch('src.risk_manager.is_order_rational', return_value=True) as mock_is_rational:
            result = await validate_order_signal(empty_order, current_equity=1000.0, current_price=30000.0)

            assert result is True
            mock_is_rational.assert_called_once()
            call_args = mock_is_rational.call_args
            assert call_args[0][0] == {}

    @pytest.mark.asyncio
    async def test_validate_order_signal_invalid_order_details(self):
        """测试无效订单详情"""
        invalid_order = {
            'symbol': '',
            'action': 'invalid',
            'size': -1.0,
            'side': 'unknown'
        }

        with patch('src.risk_manager.is_order_rational', return_value=True):
            result = await validate_order_signal(invalid_order, current_equity=1000.0, current_price=30000.0)

            # 验证器不应该验证订单格式，只应该传递给risk manager
            assert result is True


class TestValidatorIntegration:
    """验证器集成测试"""

    @pytest.mark.asyncio
    async def test_validate_order_signal_with_real_risk_manager(self):
        """测试与真实risk manager的集成（需要完整的risk manager导入）"""
        order_details = {
            'symbol': 'BTC-USDT',
            'action': 'buy',
            'size': 0.001,
            'side': 'buy'
        }

        # 这个测试会在risk manager模块完善后通过
        # 目前跳过，因为is_order_rational函数需要实现
        pytest.skip("需要完整的risk manager实现")

    @pytest.mark.asyncio
    async def test_validate_order_signal_performance(self):
        """测试验证性能"""
        order_details = {
            'symbol': 'BTC-USDT',
            'action': 'buy',
            'size': 0.001,
            'side': 'buy'
        }

        with patch('src.risk_manager.is_order_rational', return_value=True):
            import time
            start_time = time.time()

            # 执行多次验证测试性能
            for i in range(100):
                await validate_order_signal(order_details, current_equity=1000.0, current_price=30000.0)

            elapsed = time.time() - start_time

            # 100次异步调用应该在1秒内完成
            assert elapsed < 1.0
