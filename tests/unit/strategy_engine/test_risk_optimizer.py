"""
风险优化器测试 - 提升risk_optimizer.py覆盖率
目标：从6.32%提升到85%+
"""

import pytest
from src.strategy_engine.core.risk_optimizer import (
    optimize_signal_with_risk,
    apply_conservative_adjustment,
    get_volatility_metrics
)


class TestRiskOptimizerCoverage:
    """提升risk_optimizer覆盖率的测试"""

    def test_optimize_signal_with_risk_buy(self):
        """测试BUY信号的风险优化"""
        signal = {
            "side": "BUY",
            "confidence": 70.0,
            "position_size": 0.02,
            "stop_loss": 49000.0,
            "take_profit": 51000.0,
            "risk_assessment": {
                "risk_level": "MEDIUM",
                "stop_loss_distance": 0.02,
                "take_profit_ratio": 2.0
            }
        }

        enhanced_analysis = {
            "5m": {"volatility": 0.02},
            "15m": {"volatility": 0.03},
            "1h": {"volatility": 0.025}
        }

        current_price = 50000.0

        optimized = optimize_signal_with_risk(signal, enhanced_analysis, current_price)

        assert optimized["side"] == "BUY"
        assert "risk_assessment" in optimized

    def test_optimize_signal_with_risk_sell(self):
        """测试SELL信号的风险优化"""
        signal = {
            "side": "SELL",
            "confidence": 70.0,
            "position_size": 0.02,
            "stop_loss": 51000.0,
            "take_profit": 49000.0,
            "risk_assessment": {
                "risk_level": "MEDIUM",
                "stop_loss_distance": 0.02,
                "take_profit_ratio": 2.0
            }
        }

        enhanced_analysis = {
            "5m": {"volatility": 0.02}
        }

        current_price = 50000.0

        optimized = optimize_signal_with_risk(signal, enhanced_analysis, current_price)

        assert optimized["side"] == "SELL"
        # 正常波动性下 multiplier=1.0，止损 = 50000 * (1 + 0.02*1.0) = 51000
        assert optimized["stop_loss"] >= 51000.0
        assert optimized["take_profit"] <= 49000.0

    def test_high_volatility_adjustment(self):
        """测试高波动性调整"""
        signal = {
            "side": "BUY",
            "confidence": 70.0,
            "risk_assessment": {"risk_level": "LOW"}
        }

        # 高波动性数据
        enhanced_analysis = {
            "5m": {"volatility": 0.05},
            "15m": {"volatility": 0.06}
        }

        current_price = 50000.0

        optimized = optimize_signal_with_risk(signal, enhanced_analysis, current_price)

        # 验证风险等级提升
        assert optimized["risk_assessment"]["risk_level"] in ["HIGH", "MEDIUM"]

    def test_low_volatility_adjustment(self):
        """测试低波动性调整"""
        signal = {
            "side": "BUY",
            "confidence": 70.0,
            "risk_assessment": {"risk_level": "HIGH"}
        }

        # 低波动性数据
        enhanced_analysis = {
            "5m": {"volatility": 0.01}
        }

        current_price = 50000.0

        optimized = optimize_signal_with_risk(signal, enhanced_analysis, current_price)

        # 验证风险等级降低
        assert optimized["risk_assessment"]["risk_level"] in ["LOW", "MEDIUM"]

    def test_optimize_signal_exception(self):
        """测试异常处理"""
        signal = {
            "side": "BUY"
        }

        optimized = optimize_signal_with_risk(signal, {}, 50000.0)

        # 异常时应该返回原始信号
        assert optimized["side"] == "BUY"

    def test_apply_conservative_adjustment_buy(self):
        """测试BUY信号的保守调整"""
        signal = {
            "side": "BUY",
            "confidence": 80.0,
            "position_size": 0.02,
            "stop_loss": 49000.0,
            "take_profit": 51000.0,
            "risk_assessment": {"risk_level": "HIGH"}
        }

        current_price = 50000.0

        adjusted = apply_conservative_adjustment(signal, current_price)

        # 验证置信度降低
        assert adjusted["confidence"] < signal["confidence"]
        assert adjusted["confidence"] >= 65.0

        # 验证仓位减小
        assert adjusted["position_size"] < signal["position_size"]

        # 验证止损止盈收紧（保守调整：止损=50000*0.99=49500，止盈=50000*1.03=51500）
        assert adjusted["stop_loss"] == 49500.0
        assert adjusted["take_profit"] == 51500.0

        # 验证风险等级降低
        assert adjusted["risk_assessment"]["risk_level"] == "LOW"

    def test_apply_conservative_adjustment_sell(self):
        """测试SELL信号的保守调整"""
        signal = {
            "side": "SELL",
            "confidence": 80.0,
            "position_size": 0.02,
            "stop_loss": 51000.0,
            "take_profit": 49000.0,
            "risk_assessment": {"risk_level": "HIGH"}
        }

        current_price = 50000.0

        adjusted = apply_conservative_adjustment(signal, current_price)

        assert adjusted["side"] == "SELL"
        assert adjusted["confidence"] < 80.0
        # 保守调整：止损=50000*1.01=50500，止盈=50000*0.97=48500
        assert adjusted["stop_loss"] == 50500.0
        assert adjusted["take_profit"] == 48500.0

    def test_conservative_adjustment_exception(self):
        """测试保守调整异常处理"""
        signal = {
            "side": "BUY"
        }

        adjusted = apply_conservative_adjustment(signal, 50000.0)

        # 异常时返回原始信号
        assert adjusted["side"] == "BUY"

    def test_get_volatility_metrics(self):
        """测试获取波动性指标"""
        enhanced_analysis = {
            "5m": {"volatility": 0.02},
            "15m": {"volatility": 0.03},
            "1h": {"volatility": 0.025},
            "4h": {"volatility": 0.015}
        }

        metrics = get_volatility_metrics(enhanced_analysis)

        assert "multiplier" in metrics
        assert "average_volatility" in metrics
        assert "volatility_values" in metrics
        assert 0.8 <= metrics["multiplier"] <= 2.0
        assert metrics["average_volatility"] == (0.02 + 0.03 + 0.025 + 0.015) / 4

    def test_get_volatility_metrics_empty_data(self):
        """测试空数据时的波动性指标"""
        metrics = get_volatility_metrics({})

        assert metrics["multiplier"] == 1.0
        assert metrics["average_volatility"] == 0.0

    def test_get_volatility_metrics_invalid_data(self):
        """测试无效数据时的波动性指标"""
        enhanced_analysis = {
            "5m": {"volatility": "invalid"}
        }

        metrics = get_volatility_metrics(enhanced_analysis)

        # 应该忽略无效数据
        assert metrics["multiplier"] == 1.0

    def test_get_volatility_metrics_exception(self):
        """测试异常处理"""
        metrics = get_volatility_metrics(None)

        assert metrics["multiplier"] == 1.0

    def test_optimize_non_trading_signal(self):
        """测试非交易信号（HOLD）的风险优化"""
        signal = {
            "side": "HOLD",
            "confidence": 50.0
        }

        enhanced_analysis = {
            "5m": {"volatility": 0.02}
        }

        current_price = 50000.0

        optimized = optimize_signal_with_risk(signal, enhanced_analysis, current_price)

        assert optimized["side"] == "HOLD"
        assert optimized["confidence"] == 50.0

    def test_volatility_multiplier_bounds(self):
        """测试波动性倍数边界"""
        # 测试极低波动性
        enhanced_analysis = {
            "5m": {"volatility": 0.005},
            "15m": {"volatility": 0.008}
        }

        metrics = get_volatility_metrics(enhanced_analysis)
        assert metrics["multiplier"] >= 0.8

        # 测试极高波动性
        enhanced_analysis = {
            "5m": {"volatility": 0.1},
            "15m": {"volatility": 0.15}
        }

        metrics = get_volatility_metrics(enhanced_analysis)
        assert metrics["multiplier"] <= 2.0

    def test_conservative_adjustment_preserves_reasoning(self):
        """测试保守调整保留原有推理"""
        signal = {
            "side": "BUY",
            "confidence": 80.0,
            "reasoning": "Golden Cross detected"
        }

        current_price = 50000.0

        adjusted = apply_conservative_adjustment(signal, current_price)

        assert "Conservative adjustment applied" in adjusted["reasoning"]
        assert "Golden Cross detected" in adjusted["reasoning"]

    def test_risk_level_classification(self):
        """测试风险等级分类"""
        # 测试低风险
        signal_low = {
            "side": "BUY",
            "risk_assessment": {"risk_level": "LOW"}
        }

        enhanced_analysis = {"5m": {"volatility": 0.01}}
        optimized_low = optimize_signal_with_risk(signal_low, enhanced_analysis, 50000.0)
        assert optimized_low["risk_assessment"]["risk_level"] == "LOW"

        # 测试高风险
        enhanced_analysis = {"5m": {"volatility": 0.05}}
        optimized_high = optimize_signal_with_risk(signal_low, enhanced_analysis, 50000.0)
        assert optimized_high["risk_assessment"]["risk_level"] in ["HIGH", "MEDIUM"]
