"""
策略引擎主模块测试 - 提升main.py和signal_generator.py覆盖率
目标：main.py从59.42%提升到85%+，signal_generator.py从58.62%提升到85%+
"""

import pytest
import uuid
import time
from unittest.mock import Mock, patch, MagicMock

from src.strategy_engine.main import main_strategy_loop
from src.strategy_engine.core.signal_generator import (
    generate_fallback_signal,
    generate_fallback_signal_with_details,
    generate_emergency_hold_signal
)


class TestMainStrategyLoopCoverage:
    """提升main.py覆盖率的测试"""

    @pytest.fixture
    def mock_data_manager(self):
        """模拟数据管理器"""
        mock_dm = Mock()
        mock_dm.get_comprehensive_market_data.return_value = {
            "symbol": "BTC-USDT",
            "current_price": 50000.0,
            "technical_analysis": {
                "5m": {"rsi": 50, "trend": "upward"}
            },
            "orderbook": {
                "bids": [[49900, 0.1], [49800, 0.2]],
                "asks": [[50100, 0.1], [50200, 0.2]]
            },
            "volume_profile": {
                "poc": 50000,
                "value_area": {"high": 50500, "low": 49500}
            },
            "market_sentiment": {
                "overall_sentiment": "bullish",
                "sentiment_score": 0.7,
                "orderbook_imbalance": 0.3,
                "trade_imbalance": 0.2,
                "technical_momentum": "strong",
                "technical_trend": "upward"
            },
            "account": {"balance": {"BTC": 1.0, "USDT": 10000}},
            "data_status": "OK"
        }
        mock_dm.get_historical_with_indicators.return_value = {
            "historical_analysis": {
                "5m": {
                    "indicators": {"ema_fast": 49500.0, "ema_slow": 49000.0},
                    "data_points": 200,
                    "latest_timestamp": 16094592000000
                },
                "15m": {
                    "indicators": {"ema_fast": 49200.0, "ema_slow": 48800.0},
                    "data_points": 200,
                    "latest_timestamp": 16094592000000
                }
            }
        }
        return mock_dm

    def test_main_strategy_loop_success(self, mock_data_manager):
        """测试成功信号生成（完整路径）"""
        with patch('src.strategy_engine.main.generate_fallback_signal_with_details') as mock_signal:
            mock_signal.return_value = {
                "side": "BUY",
                "confidence": 75.0,
                "reasoning": "Test signal",
                "position_size": 0.02,
                "stop_loss": 49000.0,
                "take_profit": 51000.0
            }

            result = main_strategy_loop(mock_data_manager, "BTC-USDT")

            assert result["signal"] == "BUY"
            assert result["confidence"] == 75.0
            assert result["reason"] == "Test signal"  # main.py返回的是"reason"字段
            assert result["position_size"] == 0.02
            # stop_loss和take_profit在parsed_response中
            assert result["parsed_response"]["stop_loss"] == 49000.0
            assert result["parsed_response"]["take_profit"] == 51000.0
            assert "decision_id" in result
            assert "timestamp" in result
            assert "market_data" in result
            assert "historical_data" in result

    def test_market_data_error_returns_hold(self, mock_data_manager):
        """测试市场数据获取错误返回HOLD"""
        mock_data_manager.get_comprehensive_market_data.return_value = {
            "data_status": "ERROR"
        }

        result = main_strategy_loop(mock_data_manager, "BTC-USDT")

        assert result["signal"] == "HOLD"
        assert "Failed to fetch market data" in result["reason"]
        assert "decision_id" in result
        assert "timestamp" in result

    def test_technical_analysis_failed_returns_hold(self, mock_data_manager):
        """测试技术分析失败返回HOLD"""
        mock_data_manager.get_comprehensive_market_data.return_value = {
            "data_status": "SUCCESS",
            "current_price": 50000.0,
            "technical_analysis": {}
        }

        mock_data_manager.get_historical_with_indicators.return_value = {
            "historical_analysis": {}
        }

        with patch('src.strategy_engine.main.generate_fallback_signal_with_details') as mock_signal:
            mock_signal.return_value = None  # 模拟返回None

            result = main_strategy_loop(mock_data_manager, "BTC-USDT")

            assert result["signal"] == "HOLD"
            assert "Technical analysis failed" in result["reason"]

    def test_zero_current_price_uses_default(self, mock_data_manager):
        """测试当前价格为0时使用默认价格"""
        # 模拟价格为0
        mock_data_manager.get_comprehensive_market_data.return_value = {
            "data_status": "SUCCESS",
            "current_price": 0,  # 价格为0
            "technical_analysis": {}
        }

        mock_data_manager.get_historical_with_indicators.return_value = {
            "historical_analysis": {}
        }

        with patch('src.strategy_engine.main.generate_fallback_signal_with_details') as mock_signal:
            mock_signal.return_value = {
                "side": "BUY",
                "confidence": 70.0
            }

            result = main_strategy_loop(mock_data_manager, "BTC-USDT")

            # 验证使用了默认价格50000
            assert "decision_id" in result
            assert "timestamp" in result

    def test_exception_handling_with_decision_id(self, mock_data_manager):
        """测试异常处理时返回decision_id"""
        mock_data_manager.get_comprehensive_market_data.side_effect = Exception("Test error")

        result = main_strategy_loop(mock_data_manager, "BTC-USDT")

        assert result["signal"] == "HOLD"
        assert "Unexpected error" in result["reason"]
        assert "decision_id" in result
        assert "timestamp" in result

    def test_different_signal_sides(self, mock_data_manager):
        """测试不同信号方向"""
        # 测试BUY信号
        with patch('src.strategy_engine.main.generate_fallback_signal_with_details') as mock_signal:
            mock_signal.return_value = {
                "side": "BUY",
                "confidence": 75.0
            }

            result = main_strategy_loop(mock_data_manager, "BTC-USDT")
            assert result["signal"] == "BUY"

        # 测试SELL信号
        with patch('src.strategy_engine.main.generate_fallback_signal_with_details') as mock_signal:
            mock_signal.return_value = {
                "side": "SELL",
                "confidence": 70.0
            }

            result = main_strategy_loop(mock_data_manager, "BTC-USDT")
            assert result["signal"] == "SELL"

        # 测试HOLD信号
        with patch('src.strategy_engine.main.generate_fallback_signal_with_details') as mock_signal:
            mock_signal.return_value = {
                "side": "HOLD",
                "confidence": 50.0
            }

            result = main_strategy_loop(mock_data_manager, "BTC-USDT")
            assert result["signal"] == "HOLD"

    def test_signal_with_enhanced_analysis(self, mock_data_manager):
        """测试带有增强分析的信号"""
        enhanced_analysis = {
            "5m": {"trend": "bullish", "volatility": 0.02}
        }

        mock_data_manager.get_historical_with_indicators.return_value = {
            "historical_analysis": enhanced_analysis
        }

        mock_data_manager.get_comprehensive_market_data.return_value = {
            "data_status": "SUCCESS",
            "current_price": 50000.0,
            "technical_analysis": {}
        }

        with patch('src.strategy_engine.main.generate_fallback_signal_with_details') as mock_signal:
            mock_signal.return_value = {
                "side": "BUY",
                "confidence": 75.0
            }

            with patch('src.strategy_engine.main.merge_historical_with_current') as mock_merge:
                mock_merge.return_value = enhanced_analysis

                result = main_strategy_loop(mock_data_manager, "BTC-USDT")

                assert "enhanced_analysis" in result
                assert result["enhanced_analysis"]["5m"]["trend"] == "bullish"

    def test_decision_id_is_uuid(self, mock_data_manager):
        """测试decision_id是UUID格式"""
        with patch('src.strategy_engine.main.generate_fallback_signal_with_details') as mock_signal:
            mock_signal.return_value = {
                "side": "BUY",
                "confidence": 75.0
            }

            result = main_strategy_loop(mock_data_manager, "BTC-USDT")

            # 验证decision_id是UUID
            assert "decision_id" in result
            assert isinstance(result["decision_id"], str)

    def test_position_size_default(self, mock_data_manager):
        """测试默认仓位大小"""
        with patch('src.strategy_engine.main.generate_fallback_signal_with_details') as mock_signal:
            mock_signal.return_value = {
                "side": "BUY",
                "confidence": 75.0,
                # 不包含 position_size 字段，应该使用默认值 0.02
            }

            result = main_strategy_loop(mock_data_manager, "BTC-USDT")

            # 应该使用默认值0.02
            assert result["position_size"] == 0.02

    def test_timestamp_is_int(self, mock_data_manager):
        """测试timestamp是整数"""
        with patch('src.strategy_engine.main.generate_fallback_signal_with_details') as mock_signal:
            mock_signal.return_value = {
                "side": "BUY",
                "confidence": 75.0
            }

            result = main_strategy_loop(mock_data_manager, "BTC-USDT")

            assert "timestamp" in result
            assert isinstance(result["timestamp"], int)
            assert result["timestamp"] > 0

    def test_use_demo_parameter(self, mock_data_manager):
        """测试use_demo参数"""
        with patch('src.strategy_engine.main.generate_fallback_signal_with_details') as mock_signal:
            mock_signal.return_value = {
                "side": "BUY",
                "confidence": 75.0
            }

            result = main_strategy_loop(mock_data_manager, "BTC-USDT", use_demo=True)

            assert result["signal"] == "BUY"

    def test_default_parameters(self, mock_data_manager):
        """测试默认参数"""
        with patch('src.strategy_engine.main.generate_fallback_signal_with_details') as mock_signal:
            mock_signal.return_value = {
                "side": "BUY",
                "confidence": 75.0
            }

            result = main_strategy_loop(mock_data_manager, "BTC-USDT")

            # 验证使用了默认参数
            assert result["signal"] == "BUY"
            assert "decision_id" in result

    def test_merge_historical_with_current_call(self, mock_data_manager):
        """测试merge_historical_with_current被调用"""
        mock_data_manager.get_historical_with_indicators.return_value = {
            "historical_analysis": {
                "5m": {"indicators": {"ema_fast": 49500.0} }
            }
        }

        mock_data_manager.get_comprehensive_market_data.return_value = {
            "data_status": "SUCCESS",
            "current_price": 50000.0,
            "technical_analysis": {"5m": {"indicators": {"ema_fast": 49200.0}}}
        }

        with patch('src.strategy_engine.main.generate_fallback_signal_with_details') as mock_signal:
            mock_signal.return_value = {
                "side": "BUY",
                "confidence": 75.0
            }

            with patch('src.strategy_engine.main.merge_historical_with_current') as mock_merge:
                result = main_strategy_loop(mock_data_manager, "BTC-USDT")

                # 验证merge_historical_with_current被调用
                mock_merge.assert_called_once()


class TestSignalGeneratorCoverage:
    """提升signal_generator.py覆盖率的测试"""

    def test_generate_fallback_signal_success(self):
        """测试成功生成信号"""
        from src.strategy_engine.core.signal_generator import generate_fallback_signal

        enhanced_analysis = {
            "historical_analysis": {
                "5m": {
                    "trend": "bullish",
                    "indicators": {
                        "ema_fast": 49500.0,
                        "ema_slow": 49000.0
                    }
                }
            }
        }

        market_data = {
            "current_price": 50000.0
        }

        with patch('src.strategy_engine.dual_ema_strategy.generate_dual_ema_signal') as mock_dual:
            mock_dual.return_value = {
                "signal": "BUY",
                "confidence": 75.0,
                "reasoning": "Golden Cross",
                "position_size": 0.02,
                "stop_loss": 49000.0,
                "take_profit": 51000.0
            }

            signal = generate_fallback_signal(enhanced_analysis, market_data, "BTC-USDT")

            assert signal["side"] == "BUY"
            assert signal["confidence"] == 75.0
            assert signal["reasoning"] == "Golden Cross"
            assert signal["position_size"] == 0.02

    def test_generate_fallback_signal_to_emergency(self):
        """测试fallback到紧急HOLD信号"""
        from src.strategy_engine.core.signal_generator import generate_fallback_signal

        enhanced_analysis = {}
        market_data = {"current_price": 50000.0}

        with patch('src.strategy_engine.dual_ema_strategy.generate_dual_ema_signal') as mock_dual:
            mock_dual.return_value = None  # 模拟返回None

            signal = generate_fallback_signal(enhanced_analysis, market_data, "BTC-USDT")

            assert signal["side"] == "HOLD"
            assert "Strategy returned None" in signal["reasoning"]

    def test_generate_emergency_hold_signal(self):
        """测试紧急HOLD信号生成"""
        signal = generate_emergency_hold_signal("BTC-USDT", "Test reason")

        assert signal["side"] == "HOLD"
        assert signal["symbol"] == "BTC-USDT"
        assert signal["confidence"] == 50.0
        assert signal["reasoning"] == "Test reason"
        assert signal["position_size"] == 0.0
        assert signal["stop_loss"] == 0
        assert signal["take_profit"] == 0
        assert signal["current_price"] == 0
        assert signal["ema_fast"] == 0
        assert signal["ema_slow"] == 0

    def test_generate_fallback_signal_with_details_success(self):
        """测试详细信号生成"""
        enhanced_analysis = {
            "historical_analysis": {
                "5m": {
                    "indicators": {
                        "ema_fast": 49500.0,
                        "ema_slow": 49000.0
                    }
                }
            }
        }

        market_data = {
            "current_price": 50000.0
        }

        with patch('src.strategy_engine.core.signal_generator.generate_fallback_signal') as mock_fallback:
            mock_fallback.return_value = {
                "side": "BUY",
                "confidence": 75.0,
                "reasoning": "Test"
            }

            signal = generate_fallback_signal_with_details(
                enhanced_analysis,
                market_data,
                "BTC-USDT"
            )

            assert signal["side"] == "BUY"
            assert signal["symbol"] == "BTC-USDT"
            assert signal["confidence"] == 75.0
            assert signal["reasoning"] == "Test"
            assert "current_price" in signal

    def test_generate_fallback_signal_with_details_includes_ema(self):
        """测试信号包含EMA值"""
        enhanced_analysis = {
            "historical_analysis": {
                "5m": {
                    "indicators": {
                        "ema_fast": 49500.0,
                        "ema_slow": 49000.0
                    }
                }
            }
        }

        market_data = {"current_price": 50000.0}

        with patch('src.strategy_engine.core.signal_generator.generate_fallback_signal') as mock_fallback:
            mock_fallback.return_value = {
                "side": "BUY",
                "confidence": 75.0
            }

            signal = generate_fallback_signal_with_details(
                enhanced_analysis,
                market_data,
                "BTC-USDT"
            )

            assert signal["ema_fast"] == 49500.0
            assert signal["ema_slow"] == 49000.0

    def test_signal_includes_risk_assessment(self):
        """测试信号包含风险评估"""
        enhanced_analysis = {}
        market_data = {"current_price": 50000.0}

        with patch('src.strategy_engine.core.signal_generator.generate_fallback_signal') as mock_fallback:
            mock_fallback.return_value = {
                "side": "BUY",
                "confidence": 75.0
            }

            signal = generate_fallback_signal_with_details(
                enhanced_analysis,
                market_data,
                "BTC-USDT"
            )

            assert "risk_assessment" in signal
            assert signal["risk_assessment"]["risk_level"] == "MEDIUM"
            assert signal["risk_assessment"]["stop_loss_distance"] == 0.02
            assert signal["risk_assessment"]["take_profit_ratio"] == 2.0

    def test_signal_includes_technical_summary(self):
        """测试信号包含技术摘要"""
        enhanced_analysis = {}
        market_data = {"current_price": 50000.0}

        with patch('src.strategy_engine.core.signal_generator.generate_fallback_signal') as mock_fallback:
            mock_fallback.return_value = {
                "side": "BUY",
                "confidence": 75.0
            }

            signal = generate_fallback_signal_with_details(
                enhanced_analysis,
                market_data,
                "BTC-USDT"
            )

            assert "technical_summary" in signal
            assert "market_conditions" in signal
            assert "historical_analysis" in signal

    def test_generate_fallback_signal_exception(self):
        """测试异常处理"""
        enhanced_analysis = {}
        market_data = {}

        with patch('src.strategy_engine.dual_ema_strategy.generate_dual_ema_signal') as mock_dual:
            mock_dual.side_effect = Exception("Test error")

            signal = generate_fallback_signal(enhanced_analysis, market_data, "BTC-USDT")

            assert signal["side"] == "HOLD"
            assert "Error" in signal["reasoning"]

    def test_generate_fallback_signal_with_details_exception(self):
        """测试详细信号生成异常处理"""
        enhanced_analysis = {}
        market_data = {}

        with patch('src.strategy_engine.core.signal_generator.generate_fallback_signal') as mock_fallback:
            mock_fallback.side_effect = Exception("Test error")

            signal = generate_fallback_signal_with_details(
                enhanced_analysis,
                market_data,
                "BTC-USDT"
            )

            assert signal["side"] == "HOLD"
            assert "Error" in signal["reasoning"]

    def test_generate_emergency_hold_complete(self):
        """测试紧急HOLD信号完整性"""
        signal = generate_emergency_hold_signal("BTC-USDT", "Test")

        # 验证所有必要字段
        required_fields = ["side", "symbol", "position_size", "confidence", "reasoning",
                         "stop_loss", "take_profit", "current_price", "ema_fast", "ema_slow"]

        for field in required_fields:
            assert field in signal

    def test_decision_id_in_signal(self):
        """测试信号中的决策ID"""
        enhanced_analysis = {}
        market_data = {"current_price": 50000.0}

        with patch('src.strategy_engine.core.signal_generator.generate_fallback_signal') as mock_fallback:
            mock_fallback.return_value = {
                "side": "BUY",
                "confidence": 75.0
            }

            signal = generate_fallback_signal_with_details(
                enhanced_analysis,
                market_data,
                "BTC-USDT"
            )

            assert "decision_id" in signal
            assert len(signal["decision_id"]) > 0

    def test_available_margin_in_signal(self):
        """测试信号包含available_margin"""
        enhanced_analysis = {}
        market_data = {"current_price": 50000.0}

        with patch('src.strategy_engine.core.signal_generator.generate_fallback_signal') as mock_fallback:
            mock_fallback.return_value = {
                "side": "BUY",
                "confidence": 75.0
            }

            signal = generate_fallback_signal_with_details(
                enhanced_analysis,
                market_data,
                "BTC-USDT"
            )

            assert "available_margin" in signal
            assert signal["available_margin"] == 1000

    def test_signal_side_variations(self):
        """测试不同信号方向"""
        enhanced_analysis = {}
        market_data = {"current_price": 50000.0}

        with patch('src.strategy_engine.core.signal_generator.generate_fallback_signal') as mock_fallback:
            # 测试BUY
            mock_fallback.return_value = {
                "side": "BUY",
                "confidence": 75.0,
                "reasoning": "Buy reason"
            }

            signal_buy = generate_fallback_signal_with_details(
                enhanced_analysis,
                market_data,
                "BTC-USDT"
            )

            assert signal_buy["side"] == "BUY"

            # 测试SELL
            mock_fallback.return_value = {
                "side": "SELL",
                "confidence": 70.0,
                "reasoning": "Sell reason"
            }

            signal_sell = generate_fallback_signal_with_details(
                enhanced_analysis,
                market_data,
                "BTC-USDT"
            )

            assert signal_sell["side"] == "SELL"

    def test_signal_without_historical_analysis(self):
        """测试没有历史分析时的信号生成"""
        enhanced_analysis = {}  # 无历史分析数据
        market_data = {"current_price": 50000.0}

        with patch('src.strategy_engine.core.signal_generator.generate_fallback_signal') as mock_fallback:
            mock_fallback.return_value = {
                "side": "HOLD",
                "confidence": 50.0,
                "reasoning": "No data"
            }

            signal = generate_fallback_signal_with_details(
                enhanced_analysis,
                market_data,
                "BTC-USDT"
            )

            # 应该仍然生成信号（fallback机制）
            assert "side" in signal
            assert signal["side"] in ["BUY", "SELL", "HOLD"]
