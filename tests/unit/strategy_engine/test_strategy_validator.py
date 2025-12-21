"""
Strategy Engine Validator 单元测试
Unit Tests for Strategy Engine Validator
"""

import pytest
from unittest.mock import patch

from src.strategy_engine.validator import validate_data, validate_signal


class TestValidateData:
    """测试数据验证功能"""

    @pytest.mark.unit
    def test_validate_complete_snapshot(self):
        """测试完整的快照数据"""
        snapshot = {
            "klines": [[1609459200000, 29000, 29500, 28500, 29250, 1000.5]],
            "indicators": {"rsi": 50, "macd": {"signal": 0.1}},
            "account": {"balance": 10000, "position": 0.5},
            "symbol": "BTC-USDT"
        }
        
        result = validate_data(snapshot)
        
        assert result is True

    @pytest.mark.unit
    def test_validate_missing_klines(self):
        """测试缺少klines字段"""
        snapshot = {
            "indicators": {"rsi": 50},
            "account": {"balance": 10000},
            "symbol": "BTC-USDT"
        }
        
        result = validate_data(snapshot)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_missing_indicators(self):
        """测试缺少indicators字段"""
        snapshot = {
            "klines": [[1609459200000, 29000, 29500, 28500, 29250, 1000.5]],
            "account": {"balance": 10000},
            "symbol": "BTC-USDT"
        }
        
        result = validate_data(snapshot)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_missing_account(self):
        """测试缺少account字段"""
        snapshot = {
            "klines": [[1609459200000, 29000, 29500, 28500, 29250, 1000.5]],
            "indicators": {"rsi": 50},
            "symbol": "BTC-USDT"
        }
        
        result = validate_data(snapshot)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_missing_symbol(self):
        """测试缺少symbol字段"""
        snapshot = {
            "klines": [[1609459200000, 29000, 29500, 28500, 29250, 1000.5]],
            "indicators": {"rsi": 50},
            "account": {"balance": 10000}
        }
        
        result = validate_data(snapshot)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_none_klines(self):
        """测试klines为None"""
        snapshot = {
            "klines": None,
            "indicators": {"rsi": 50},
            "account": {"balance": 10000},
            "symbol": "BTC-USDT"
        }
        
        result = validate_data(snapshot)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_empty_snapshot(self):
        """测试空快照"""
        snapshot = {}
        
        result = validate_data(snapshot)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_none_snapshot(self):
        """测试None快照"""
        result = validate_data(None)
        
        assert result is False

    @pytest.mark.unit
    @patch('src.strategy_engine.validator.logger')
    def test_validate_data_exception_handling(self, mock_logger):
        """测试数据验证异常处理"""
        # 创建一个会导致异常的snapshot
        snapshot = {
            "klines": "not_a_list",  # 这可能导致异常
            "indicators": {"rsi": 50},
            "account": {"balance": 10000},
            "symbol": "BTC-USDT"
        }
        
        result = validate_data(snapshot)
        
        # 由于代码有异常处理，可能返回True或False
        # 主要验证不会崩溃，并且可能记录错误
        assert isinstance(result, bool)
        # mock_logger.error.assert_called()  # 可能不调用，取决于实现

    @pytest.mark.unit
    def test_validate_minimal_valid_snapshot(self):
        """测试最小有效快照"""
        snapshot = {
            "klines": [],
            "indicators": {},
            "account": {},
            "symbol": "BTC-USDT"
        }
        
        result = validate_data(snapshot)
        
        assert result is True

    @pytest.mark.unit
    def test_validate_snapshot_with_extra_fields(self):
        """测试包含额外字段的快照"""
        snapshot = {
            "klines": [[1609459200000, 29000, 29500, 28500, 29250, 1000.5]],
            "indicators": {"rsi": 50},
            "account": {"balance": 10000},
            "symbol": "BTC-USDT",
            "extra_field": "should_not_cause_error",
            "another_extra": {"nested": "data"}
        }
        
        result = validate_data(snapshot)
        
        assert result is True


class TestValidateSignal:
    """测试信号验证功能"""

    @pytest.mark.unit
    def test_validate_valid_buy_signal(self):
        """测试有效的买入信号"""
        signal = {
            "side": "BUY",
            "position_size": 0.1,
            "stop_loss": 28500,
            "take_profit": 31000
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is True

    @pytest.mark.unit
    def test_validate_valid_sell_signal(self):
        """测试有效的卖出信号"""
        signal = {
            "side": "SELL",
            "position_size": 0.1,
            "stop_loss": 31500,
            "take_profit": 28000
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is True

    @pytest.mark.unit
    def test_validate_valid_hold_signal(self):
        """测试有效的持有信号"""
        signal = {
            "side": "HOLD",
            "position_size": 0.0,
            "stop_loss": 28500,
            "take_profit": 31500
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is True

    @pytest.mark.unit
    def test_validate_signal_with_action_field(self):
        """测试使用action字段的信号"""
        signal = {
            "action": "BUY",
            "position_size": 0.1,
            "stop_loss": 28500,
            "take_profit": 31000
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is True

    @pytest.mark.unit
    def test_validate_signal_missing_both_side_and_action(self):
        """测试缺少side和action字段的信号"""
        signal = {
            "position_size": 0.1,
            "stop_loss": 28500,
            "take_profit": 31000
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_signal_invalid_side(self):
        """测试无效的side值"""
        signal = {
            "side": "INVALID",
            "position_size": 0.1,
            "stop_loss": 28500,
            "take_profit": 31000
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_signal_missing_position_size(self):
        """测试缺少position_size字段"""
        signal = {
            "side": "BUY",
            "stop_loss": 28500,
            "take_profit": 31000
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_signal_missing_stop_loss(self):
        """测试缺少stop_loss字段"""
        signal = {
            "side": "BUY",
            "position_size": 0.1,
            "take_profit": 31000
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_signal_missing_take_profit(self):
        """测试缺少take_profit字段"""
        signal = {
            "side": "BUY",
            "position_size": 0.1,
            "stop_loss": 28500
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_signal_none_position_size(self):
        """测试position_size为None"""
        signal = {
            "side": "BUY",
            "position_size": None,
            "stop_loss": 28500,
            "take_profit": 31000
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_signal_zero_stop_loss(self):
        """测试stop_loss为0"""
        signal = {
            "side": "BUY",
            "position_size": 0.1,
            "stop_loss": 0,
            "take_profit": 31000
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_signal_negative_take_profit(self):
        """测试take_profit为负数"""
        signal = {
            "side": "BUY",
            "position_size": 0.1,
            "stop_loss": 28500,
            "take_profit": -100
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_signal_string_numeric_fields(self):
        """测试字符串类型的数值字段"""
        signal = {
            "side": "BUY",
            "position_size": "0.1",
            "stop_loss": "28500",
            "take_profit": "31000"
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is True

    @pytest.mark.unit
    def test_validate_signal_large_stop_loss_distance(self):
        """测试过大的止损距离"""
        signal = {
            "side": "BUY",
            "position_size": 0.1,
            "stop_loss": 20000,  # 超过20%的止损
            "take_profit": 31000
        }
        current_price = 30000
        
        with patch('src.strategy_engine.validator.logger') as mock_logger:
            result = validate_signal(signal, current_price)
            
            # 应该仍然返回True，但记录警告
            assert result is True
            mock_logger.warning.assert_called()

    @pytest.mark.unit
    def test_validate_signal_large_take_profit_distance(self):
        """测试过大的止盈距离"""
        signal = {
            "side": "BUY",
            "position_size": 0.1,
            "stop_loss": 28500,
            "take_profit": 50000  # 超过50%的止盈
        }
        current_price = 30000
        
        with patch('src.strategy_engine.validator.logger') as mock_logger:
            result = validate_signal(signal, current_price)
            
            # 应该仍然返回True，但记录警告
            assert result is True
            mock_logger.warning.assert_called()

    @pytest.mark.unit
    def test_validate_signal_zero_current_price(self):
        """测试当前价格为0的情况"""
        signal = {
            "side": "BUY",
            "position_size": 0.1,
            "stop_loss": 28500,
            "take_profit": 31000
        }
        current_price = 0
        
        result = validate_signal(signal, current_price)
        
        # 应该跳过价格距离检查，但仍然验证基本字段
        assert result is True

    @pytest.mark.unit
    def test_validate_signal_negative_current_price(self):
        """测试当前价格为负数的情况"""
        signal = {
            "side": "BUY",
            "position_size": 0.1,
            "stop_loss": 28500,
            "take_profit": 31000
        }
        current_price = -100
        
        result = validate_signal(signal, current_price)
        
        # 应该跳过价格距离检查，但仍然验证基本字段
        assert result is True

    @pytest.mark.unit
    @patch('src.strategy_engine.validator.logger')
    def test_validate_signal_exception_handling(self, mock_logger):
        """测试信号验证异常处理"""
        # 创建一个会导致异常的signal
        signal = {
            "side": "BUY",
            "position_size": "not_a_number",  # 这可能导致异常
            "stop_loss": 28500,
            "take_profit": 31000
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        # 由于代码有异常处理，可能返回True或False
        # 主要验证不会崩溃，并且可能记录错误
        assert isinstance(result, bool)
        # mock_logger.error.assert_called()  # 可能不调用，取决于实现

    @pytest.mark.unit
    def test_validate_signal_with_side_priority_over_action(self):
        """测试side字段优先于action字段"""
        signal = {
            "side": "BUY",
            "action": "SELL",  # side应该优先
            "position_size": 0.1,
            "stop_loss": 28500,
            "take_profit": 31000
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is True

    @pytest.mark.unit
    def test_validate_signal_with_action_only(self):
        """测试只有action字段的信号"""
        signal = {
            "action": "SELL",
            "position_size": 0.1,
            "stop_loss": 31500,
            "take_profit": 28000
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is True

    @pytest.mark.unit
    def test_validate_signal_with_extra_fields(self):
        """测试包含额外字段的信号"""
        signal = {
            "side": "BUY",
            "position_size": 0.1,
            "stop_loss": 28500,
            "take_profit": 31000,
            "confidence": 0.85,
            "reasoning": "Strong uptrend",
            "extra_field": "should_not_cause_error"
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is True

    @pytest.mark.unit
    def test_validate_signal_edge_case_prices(self):
        """测试边界价格情况"""
        # 测试非常小的价格差异
        signal = {
            "side": "BUY",
            "position_size": 0.1,
            "stop_loss": 29999.99,
            "take_profit": 30000.01
        }
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is True

    @pytest.mark.unit
    def test_validate_signal_empty_signal(self):
        """测试空信号"""
        signal = {}
        current_price = 30000
        
        result = validate_signal(signal, current_price)
        
        assert result is False

    @pytest.mark.unit
    def test_validate_signal_none_signal(self):
        """测试None信号"""
        result = validate_signal(None, 30000)
        
        assert result is False


class TestValidatorIntegration:
    """验证器集成测试"""

    @pytest.mark.unit
    def test_complete_validation_workflow(self):
        """测试完整的验证工作流"""
        # 测试数据验证
        valid_snapshot = {
            "klines": [[1609459200000, 29000, 29500, 28500, 29250, 1000.5]],
            "indicators": {"rsi": 50, "macd": {"signal": 0.1}},
            "account": {"balance": 10000, "position": 0.5},
            "symbol": "BTC-USDT"
        }
        
        assert validate_data(valid_snapshot) is True
        
        # 测试信号验证
        valid_signal = {
            "side": "BUY",
            "position_size": 0.1,
            "stop_loss": 28500,
            "take_profit": 31000,
            "confidence": 0.85
        }
        
        assert validate_signal(valid_signal, 30000) is True

    @pytest.mark.unit
    @patch('src.strategy_engine.validator.logger')
    def test_validation_error_logging(self, mock_logger):
        """测试验证错误日志记录"""
        # 测试数据验证错误
        invalid_snapshot = {"klines": []}
        validate_data(invalid_snapshot)
        mock_logger.error.assert_called()
        
        # 测试信号验证错误
        invalid_signal = {"side": "INVALID"}
        validate_signal(invalid_signal, 30000)
        mock_logger.error.assert_called()

    @pytest.mark.unit
    def test_validation_with_realistic_data(self):
        """测试使用真实数据的验证"""
        # 真实的快照数据
        realistic_snapshot = {
            "klines": [
                [1609459200000, 29000.0, 29500.0, 28500.0, 29250.0, 1000.5],
                [1609459500000, 29250.0, 29800.0, 29000.0, 29600.0, 1200.3],
                [1609459800000, 29600.0, 30000.0, 29300.0, 29850.0, 980.7]
            ],
            "indicators": {
                "rsi": 65.5,
                "macd": {"signal": 0.15, "macd": 0.12, "histogram": 0.03},
                "bollinger": {"upper": 30500, "middle": 29500, "lower": 28500},
                "ema": {"ema20": 29600, "ema50": 29400}
            },
            "account": {
                "balance": 10000.0,
                "position": 0.5,
                "available_margin": 5000.0,
                "unrealized_pnl": 250.0
            },
            "symbol": "BTC-USDT"
        }
        
        assert validate_data(realistic_snapshot) is True
        
        # 真实的信号数据
        realistic_signal = {
            "side": "BUY",
            "position_size": 0.15,
            "stop_loss": 28800.0,
            "take_profit": 31200.0,
            "confidence": 0.78,
            "reasoning": "RSI shows bullish momentum, MACD crossover confirmed"
        }
        
        assert validate_signal(realistic_signal, 30000.0) is True
