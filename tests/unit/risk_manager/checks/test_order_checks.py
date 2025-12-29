"""
Risk Manager Checks 单元测试
Unit Tests for Risk Manager Checks
"""

import pytest
from unittest.mock import patch, Mock

from src.risk_manager.checks.order_checks import (
    OrderDetails,
    is_order_rational,
    _validate_stop_take_profit_logic,
    validate_order_size,
    get_position_ratio
)


class TestOrderDetails:
    """测试订单详情模型"""

    @pytest.mark.unit
    def test_valid_buy_order(self):
        """测试有效的买单"""
        order = OrderDetails(
            symbol="BTC-USDT",
            side="buy",
            position_size=1000.0,
            stop_loss=29000.0,
            take_profit=31000.0
        )

        assert order.symbol == "BTC-USDT"
        assert order.side == "buy"
        assert order.position_size == 1000.0
        assert order.stop_loss == 29000.0
        assert order.take_profit == 31000.0

    @pytest.mark.unit
    def test_valid_sell_order(self):
        """测试有效的卖单"""
        order = OrderDetails(
            symbol="ETH-USDT",
            side="SELL",
            position_size=500.0,
            stop_loss=2100.0,
            take_profit=1900.0
        )

        assert order.symbol == "ETH-USDT"
        assert order.side == "sell"  # 应该被转换为小写
        assert order.position_size == 500.0
        assert order.stop_loss == 2100.0
        assert order.take_profit == 1900.0

    @pytest.mark.unit
    def test_invalid_side(self):
        """测试无效的side"""
        with pytest.raises(ValueError, match="side必须是buy或sell"):
            OrderDetails(
                symbol="BTC-USDT",
                side="invalid",
                position_size=1000.0,
                stop_loss=29000.0,
                take_profit=31000.0
            )

    @pytest.mark.unit
    def test_negative_position_size(self):
        """测试负数仓位大小"""
        from pydantic import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            OrderDetails(
                symbol="BTC-USDT",
                side="buy",
                position_size=-100.0,
                stop_loss=29000.0,
                take_profit=31000.0
            )
        # 验证错误信息包含position_size相关的验证错误
        assert "position_size" in str(exc_info.value)
        assert "greater than 0" in str(exc_info.value)

    @pytest.mark.unit
    def test_zero_position_size(self):
        """测试零仓位大小"""
        from pydantic import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            OrderDetails(
                symbol="BTC-USDT",
                side="buy",
                position_size=0.0,
                stop_loss=29000.0,
                take_profit=31000.0
            )
        # 验证错误信息包含position_size相关的验证错误
        assert "position_size" in str(exc_info.value)
        assert "greater than 0" in str(exc_info.value)

    @pytest.mark.unit
    def test_negative_stop_loss(self):
        """测试负数止损价格"""
        with pytest.raises(ValueError, match="价格必须为正数"):
            OrderDetails(
                symbol="BTC-USDT",
                side="buy",
                position_size=1000.0,
                stop_loss=-100.0,
                take_profit=31000.0
            )

    @pytest.mark.unit
    def test_zero_take_profit(self):
        """测试零止盈价格"""
        with pytest.raises(ValueError, match="价格必须为正数"):
            OrderDetails(
                symbol="BTC-USDT",
                side="buy",
                position_size=1000.0,
                stop_loss=29000.0,
                take_profit=0.0
            )

    @pytest.mark.unit
    def test_missing_required_fields(self):
        """测试缺少必需字段"""
        with pytest.raises(ValueError):
            OrderDetails(
                symbol="BTC-USDT",
                side="buy"
                # 缺少其他必需字段
            )


class TestIsOrderRational:
    """测试订单合理性检查"""

    @pytest.mark.unit
    def test_rational_buy_order(self):
        """测试合理的买单"""
        order_details = {
            "symbol": "BTC-USDT",
            "side": "buy",
            "position_size": 1000.0,
            "stop_loss": 29000.0,
            "take_profit": 31000.0
        }
        current_equity = 10000.0

        with patch('src.risk_manager.checks.get_config') as mock_get_config:
            mock_config = Mock()
            mock_config.risk_limits.max_single_order_size_percent = 0.2
            mock_get_config.return_value = mock_config

            result = is_order_rational(order_details, current_equity)

            assert result is True

    @pytest.mark.unit
    def test_rational_sell_order(self):
        """测试合理的卖单"""
        order_details = {
            "symbol": "BTC-USDT",
            "side": "sell",
            "position_size": 500.0,
            "stop_loss": 31000.0,
            "take_profit": 29000.0
        }
        current_equity = 10000.0

        with patch('src.risk_manager.checks.get_config') as mock_get_config:
            mock_config = Mock()
            mock_config.risk_limits.max_single_order_size_percent = 0.1
            mock_get_config.return_value = mock_config

            result = is_order_rational(order_details, current_equity)

            assert result is True

    @pytest.mark.unit
    def test_order_size_too_large(self):
        """测试订单过大"""
        order_details = {
            "symbol": "BTC-USDT",
            "side": "buy",
            "position_size": 5000.0,  # 50%的权益
            "stop_loss": 29000.0,
            "take_profit": 31000.0
        }
        current_equity = 10000.0

        with patch('src.risk_manager.checks.get_config') as mock_get_config:
            mock_config = Mock()
            mock_config.risk_limits.max_single_order_size_percent = 0.2  # 最大20%
            mock_get_config.return_value = mock_config

            result = is_order_rational(order_details, current_equity)

            assert result is False

    @pytest.mark.unit
    def test_invalid_stop_take_profit_logic_buy(self):
        """测试买单止损止盈逻辑错误"""
        order_details = {
            "symbol": "BTC-USDT",
            "side": "buy",
            "position_size": 1000.0,
            "stop_loss": 31000.0,  # 止损高于止盈
            "take_profit": 29000.0
        }
        current_equity = 10000.0

        with patch('src.risk_manager.checks.get_config') as mock_get_config:
            mock_config = Mock()
            mock_config.risk_limits.max_single_order_size_percent = 0.2
            mock_get_config.return_value = mock_config

            result = is_order_rational(order_details, current_equity)

            assert result is False

    @pytest.mark.unit
    def test_invalid_stop_take_profit_logic_sell(self):
        """测试卖单止损止盈逻辑错误"""
        order_details = {
            "symbol": "BTC-USDT",
            "side": "sell",
            "position_size": 1000.0,
            "stop_loss": 29000.0,  # 止损低于止盈
            "take_profit": 31000.0
        }
        current_equity = 10000.0

        with patch('src.risk_manager.checks.get_config') as mock_get_config:
            mock_config = Mock()
            mock_config.risk_limits.max_single_order_size_percent = 0.2
            mock_get_config.return_value = mock_config

            result = is_order_rational(order_details, current_equity)

            assert result is False

    @pytest.mark.unit
    def test_invalid_order_details(self):
        """测试无效的订单详情"""
        order_details = {
            "symbol": "BTC-USDT",
            "side": "invalid_side",  # 无效side
            "position_size": 1000.0,
            "stop_loss": 29000.0,
            "take_profit": 31000.0
        }
        current_equity = 10000.0

        with patch('src.risk_manager.checks.get_config') as mock_get_config:
            mock_config = Mock()
            mock_config.risk_limits.max_single_order_size_percent = 0.2
            mock_get_config.return_value = mock_config

            result = is_order_rational(order_details, current_equity)

            assert result is False

    @pytest.mark.unit
    def test_with_custom_config(self):
        """测试使用自定义配置"""
        order_details = {
            "symbol": "BTC-USDT",
            "side": "buy",
            "position_size": 1000.0,
            "stop_loss": 29000.0,
            "take_profit": 31000.0
        }
        current_equity = 10000.0

        custom_config = Mock()
        custom_config.risk_limits.max_single_order_size_percent = 0.15

        result = is_order_rational(order_details, current_equity, custom_config)

        assert result is True

    @pytest.mark.unit
    @patch('src.risk_manager.checks.logger')
    def test_exception_handling(self, mock_logger):
        """测试异常处理"""
        # 创建一个会导致异常的订单详情
        order_details = {
            "symbol": "BTC-USDT",
            "side": "buy",
            "position_size": "invalid",  # 这可能导致异常
            "stop_loss": 29000.0,
            "take_profit": 31000.0
        }
        current_equity = 10000.0

        with patch('src.risk_manager.checks.get_config') as mock_get_config:
            mock_config = Mock()
            mock_config.risk_limits.max_single_order_size_percent = 0.2
            mock_get_config.return_value = mock_config

            result = is_order_rational(order_details, current_equity)

            assert result is False
            mock_logger.critical.assert_called()

    @pytest.mark.unit
    def test_edge_case_exact_limit(self):
        """测试边界情况 - 刚好达到限制"""
        order_details = {
            "symbol": "BTC-USDT",
            "side": "buy",
            "position_size": 2000.0,  # 刚好20%
            "stop_loss": 29000.0,
            "take_profit": 31000.0
        }
        current_equity = 10000.0

        with patch('src.risk_manager.checks.get_config') as mock_get_config:
            mock_config = Mock()
            mock_config.risk_limits.max_single_order_size_percent = 0.2
            mock_get_config.return_value = mock_config

            result = is_order_rational(order_details, current_equity)

            assert result is True

    @pytest.mark.unit
    def test_zero_equity(self):
        """测试零权益"""
        order_details = {
            "symbol": "BTC-USDT",
            "side": "buy",
            "position_size": 1000.0,
            "stop_loss": 29000.0,
            "take_profit": 31000.0
        }
        current_equity = 0.0

        with patch('src.risk_manager.checks.get_config') as mock_get_config:
            mock_config = Mock()
            mock_config.risk_limits.max_single_order_size_percent = 0.2
            mock_get_config.return_value = mock_config

            result = is_order_rational(order_details, current_equity)

            # 应该返回False，因为除零错误
            assert result is False


class TestValidateStopTakeProfitLogic:
    """测试止损止盈逻辑验证"""

    @pytest.mark.unit
    def test_valid_buy_order_logic(self):
        """测试有效的买单逻辑"""
        order = OrderDetails(
            symbol="BTC-USDT",
            side="buy",
            position_size=1000.0,
            stop_loss=29000.0,
            take_profit=31000.0
        )

        result = _validate_stop_take_profit_logic(order)

        assert result is True

    @pytest.mark.unit
    def test_valid_sell_order_logic(self):
        """测试有效的卖单逻辑"""
        order = OrderDetails(
            symbol="BTC-USDT",
            side="sell",
            position_size=1000.0,
            stop_loss=31000.0,
            take_profit=29000.0
        )

        result = _validate_stop_take_profit_logic(order)

        assert result is True

    @pytest.mark.unit
    def test_invalid_buy_order_logic(self):
        """测试无效的买单逻辑"""
        order = OrderDetails(
            symbol="BTC-USDT",
            side="buy",
            position_size=1000.0,
            stop_loss=31000.0,  # 止损高于止盈
            take_profit=29000.0
        )

        result = _validate_stop_take_profit_logic(order)

        assert result is False

    @pytest.mark.unit
    def test_invalid_sell_order_logic(self):
        """测试无效的卖单逻辑"""
        order = OrderDetails(
            symbol="BTC-USDT",
            side="sell",
            position_size=1000.0,
            stop_loss=29000.0,  # 止损低于止盈
            take_profit=31000.0
        )

        result = _validate_stop_take_profit_logic(order)

        assert result is False

    @pytest.mark.unit
    def test_equal_stop_take_profit_buy(self):
        """测试买单止损止盈相等"""
        order = OrderDetails(
            symbol="BTC-USDT",
            side="buy",
            position_size=1000.0,
            stop_loss=30000.0,
            take_profit=30000.0
        )

        result = _validate_stop_take_profit_logic(order)

        assert result is False

    @pytest.mark.unit
    def test_equal_stop_take_profit_sell(self):
        """测试卖单止损止盈相等"""
        order = OrderDetails(
            symbol="BTC-USDT",
            side="sell",
            position_size=1000.0,
            stop_loss=30000.0,
            take_profit=30000.0
        )

        result = _validate_stop_take_profit_logic(order)

        assert result is False

    @pytest.mark.unit
    @patch('src.risk_manager.checks.logger')
    def test_exception_handling(self, mock_logger):
        """测试异常处理"""
        # 创建一个会导致异常的情况
        order = Mock()
        order.side = "buy"
        order.stop_loss = None  # 这可能导致异常
        order.take_profit = 31000.0

        result = _validate_stop_take_profit_logic(order)

        assert result is False
        mock_logger.error.assert_called()


class TestValidateOrderSize:
    """测试订单大小验证"""

    @pytest.mark.unit
    def test_valid_order_size(self):
        """测试有效的订单大小"""
        order_amount = 1000.0
        current_equity = 10000.0
        max_percent = 0.2

        result = validate_order_size(order_amount, current_equity, max_percent)

        assert result is True

    @pytest.mark.unit
    def test_order_size_exceeds_limit(self):
        """测试订单大小超限"""
        order_amount = 3000.0
        current_equity = 10000.0
        max_percent = 0.2

        result = validate_order_size(order_amount, current_equity, max_percent)

        assert result is False

    @pytest.mark.unit
    def test_zero_current_equity(self):
        """测试零当前权益"""
        order_amount = 1000.0
        current_equity = 0.0
        max_percent = 0.2

        result = validate_order_size(order_amount, current_equity, max_percent)

        assert result is False

    @pytest.mark.unit
    def test_negative_current_equity(self):
        """测试负数当前权益"""
        order_amount = 1000.0
        current_equity = -1000.0
        max_percent = 0.2

        result = validate_order_size(order_amount, current_equity, max_percent)

        assert result is False

    @pytest.mark.unit
    def test_zero_order_amount(self):
        """测试零订单金额"""
        order_amount = 0.0
        current_equity = 10000.0
        max_percent = 0.2

        result = validate_order_size(order_amount, current_equity, max_percent)

        assert result is False

    @pytest.mark.unit
    def test_negative_order_amount(self):
        """测试负数订单金额"""
        order_amount = -1000.0
        current_equity = 10000.0
        max_percent = 0.2

        result = validate_order_size(order_amount, current_equity, max_percent)

        assert result is False

    @pytest.mark.unit
    def test_edge_case_exact_limit(self):
        """测试边界情况 - 刚好达到限制"""
        order_amount = 2000.0
        current_equity = 10000.0
        max_percent = 0.2

        result = validate_order_size(order_amount, current_equity, max_percent)

        assert result is True

    @pytest.mark.unit
    def test_very_small_order(self):
        """测试非常小的订单"""
        order_amount = 0.01
        current_equity = 10000.0
        max_percent = 0.2

        result = validate_order_size(order_amount, current_equity, max_percent)

        assert result is True

    @pytest.mark.unit
    @patch('src.risk_manager.checks.logger')
    def test_exception_handling(self, mock_logger):
        """测试异常处理"""
        # 创建一个会导致异常的情况
        order_amount = "invalid"
        current_equity = 10000.0
        max_percent = 0.2

        result = validate_order_size(order_amount, current_equity, max_percent)

        assert result is False
        mock_logger.error.assert_called()


class TestGetPositionRatio:
    """测试仓位占比计算"""

    @pytest.mark.unit
    def test_normal_position_ratio(self):
        """测试正常仓位占比"""
        order_amount = 1000.0
        current_equity = 10000.0

        result = get_position_ratio(order_amount, current_equity)

        assert result == 0.1

    @pytest.mark.unit
    def test_full_position_ratio(self):
        """测试满仓"""
        order_amount = 10000.0
        current_equity = 10000.0

        result = get_position_ratio(order_amount, current_equity)

        assert result == 1.0

    @pytest.mark.unit
    def test_zero_current_equity(self):
        """测试零当前权益"""
        order_amount = 1000.0
        current_equity = 0.0

        result = get_position_ratio(order_amount, current_equity)

        assert result == 0.0

    @pytest.mark.unit
    def test_negative_current_equity(self):
        """测试负数当前权益"""
        order_amount = 1000.0
        current_equity = -1000.0

        result = get_position_ratio(order_amount, current_equity)

        assert result == 0.0

    @pytest.mark.unit
    def test_zero_order_amount(self):
        """测试零订单金额"""
        order_amount = 0.0
        current_equity = 10000.0

        result = get_position_ratio(order_amount, current_equity)

        assert result == 0.0

    @pytest.mark.unit
    def test_very_small_ratio(self):
        """测试非常小的占比"""
        order_amount = 1.0
        current_equity = 10000.0

        result = get_position_ratio(order_amount, current_equity)

        assert result == 0.0001

    @pytest.mark.unit
    def test_large_ratio(self):
        """测试大占比"""
        order_amount = 15000.0
        current_equity = 10000.0

        result = get_position_ratio(order_amount, current_equity)

        assert result == 1.5

    @pytest.mark.unit
    @patch('src.risk_manager.checks.logger')
    def test_exception_handling(self, mock_logger):
        """测试异常处理"""
        # 创建一个会导致异常的情况
        order_amount = "invalid"
        current_equity = 10000.0

        result = get_position_ratio(order_amount, current_equity)

        assert result == 0.0
        mock_logger.error.assert_called()


class TestRiskManagerIntegration:
    """风险管理器集成测试"""

    @pytest.mark.unit
    def test_complete_risk_check_workflow(self):
        """测试完整的风险检查工作流"""
        # 测试数据
        order_details = {
            "symbol": "BTC-USDT",
            "side": "buy",
            "position_size": 1500.0,
            "stop_loss": 29000.0,
            "take_profit": 31000.0
        }
        current_equity = 10000.0
        max_percent = 0.2

        # 1. 测试订单合理性检查
        with patch('src.risk_manager.checks.get_config') as mock_get_config:
            mock_config = Mock()
            mock_config.risk_limits.max_single_order_size_percent = max_percent
            mock_get_config.return_value = mock_config

            rational_result = is_order_rational(order_details, current_equity)
            assert rational_result is True

        # 2. 测试订单大小验证
        size_result = validate_order_size(
            order_details["position_size"],
            current_equity,
            max_percent
        )
        assert size_result is True

        # 3. 测试仓位占比计算
        ratio = get_position_ratio(order_details["position_size"], current_equity)
        assert ratio == 0.15
        assert ratio <= max_percent

    @pytest.mark.unit
    def test_risk_check_with_realistic_data(self):
        """测试使用真实数据的风险检查"""
        # 真实的交易场景
        order_details = {
            "symbol": "BTC-USDT",
            "side": "buy",
            "position_size": 2500.0,  # 25%仓位
            "stop_loss": 28500.0,
            "take_profit": 32000.0
        }
        current_equity = 10000.0

        with patch('src.risk_manager.checks.get_config') as mock_get_config:
            mock_config = Mock()
            mock_config.risk_limits.max_single_order_size_percent = 0.3  # 最大30%
            mock_get_config.return_value = mock_config

            # 执行风险检查
            result = is_order_rational(order_details, current_equity)

            assert result is True

    @pytest.mark.unit
    def test_multiple_risk_scenarios(self):
        """测试多种风险场景"""
        scenarios = [
            # (订单详情, 当前权益, 最大比例, 预期结果)
            ({
                "symbol": "BTC-USDT",
                "side": "buy",
                "position_size": 500.0,
                "stop_loss": 29000.0,
                "take_profit": 31000.0
            }, 10000.0, 0.1, True),  # 正常情况

            ({
                "symbol": "ETH-USDT",
                "side": "sell",
                "position_size": 2000.0,
                "stop_loss": 2200.0,
                "take_profit": 1800.0
            }, 10000.0, 0.25, True),  # 正常卖单

            ({
                "symbol": "BTC-USDT",
                "side": "buy",
                "position_size": 5000.0,
                "stop_loss": 29000.0,
                "take_profit": 31000.0
            }, 10000.0, 0.3, False),  # 超过限制

            ({
                "symbol": "BTC-USDT",
                "side": "buy",
                "position_size": 1000.0,
                "stop_loss": 31000.0,
                "take_profit": 29000.0
            }, 10000.0, 0.2, False),  # 止损止盈逻辑错误
        ]

        for order_details, equity, max_percent, expected in scenarios:
            with patch('src.risk_manager.checks.get_config') as mock_get_config:
                mock_config = Mock()
                mock_config.risk_limits.max_single_order_size_percent = max_percent
                mock_get_config.return_value = mock_config

                result = is_order_rational(order_details, equity)
                assert result == expected, f"Failed for {order_details}"
