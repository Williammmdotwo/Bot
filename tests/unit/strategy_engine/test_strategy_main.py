"""
Strategy Engine主模块单元测试
覆盖strategy_engine/main.py的核心功能
"""

import pytest
import uuid
import time
import os
from unittest.mock import Mock, patch, AsyncMock, MagicMock

# 导入测试目标
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../..'))

from src.strategy_engine.main import main_strategy_loop, _format_indicators_for_prompt, \
    _format_orderbook_for_prompt, _format_volume_profile_for_prompt, _format_sentiment_for_prompt, \
    _merge_historical_with_current, _format_historical_trends_for_prompt, \
    _analyze_trend_consistency, _identify_key_turning_points, _analyze_volatility_across_timeframes


class TestMainStrategyLoop:
    """main_strategy_loop函数测试"""
    
    @pytest.fixture
    def mock_data_manager(self):
        """模拟数据管理器"""
        mock_dm = Mock()
        mock_dm.get_comprehensive_market_data.return_value = {
            "symbol": "BTC-USDT",
            "current_price": 50000.0,
            "technical_analysis": {
                "5m": {"rsi": 50, "macd": {"macd": 0.1, "signal": 0.05}},
                "15m": {"rsi": 55, "macd": {"macd": 0.2, "signal": 0.1}},
                "1h": {"rsi": 60, "macd": {"macd": 0.3, "signal": 0.15}},
                "4h": {"rsi": 65, "macd": {"macd": 0.4, "signal": 0.2}}
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
                    "indicators": {"rsi": 48, "trend": "upward", "momentum": "strong"},
                    "data_points": 200,
                    "latest_timestamp": 1609459200000
                },
                "15m": {
                    "indicators": {"rsi": 52, "trend": "upward", "momentum": "moderate"},
                    "data_points": 200,
                    "latest_timestamp": 1609459200000
                }
            }
        }
        return mock_dm
    
    
    def test_main_strategy_loop_success(self, mock_data_manager):
        """测试策略循环成功"""
        with patch('src.strategy_engine.main.validate_signal') as mock_validate:
            mock_validate.return_value = True
            
            result = main_strategy_loop(
                mock_data_manager, symbol="BTC-USDT", use_demo=True
            )
            
            # 验证结果
            assert result["signal"] in ["BUY", "SELL", "HOLD"]
            assert "decision_id" in result
            assert "parsed_response" in result
            assert "market_data" in result
            assert "historical_data" in result
            assert "enhanced_analysis" in result
            assert "timestamp" in result
            
            # 验证调用
            mock_data_manager.get_comprehensive_market_data.assert_called_once_with("BTC-USDT", use_demo=True)
            mock_data_manager.get_historical_with_indicators.assert_called_once()
            mock_validate.assert_called_once()
    
    def test_main_strategy_loop_market_data_error(self, mock_data_manager):
        """测试市场数据获取错误"""
        mock_data_manager.get_comprehensive_market_data.return_value = {
            "data_status": "ERROR"
        }
        
        result = main_strategy_loop(
            mock_data_manager, symbol="BTC-USDT", use_demo=True
        )
        
        # 验证错误处理
        assert result["signal"] == "HOLD"
        assert "Failed to fetch market data" in result["reason"]
        assert "decision_id" in result
        assert "timestamp" in result
    
    def test_main_strategy_loop_empty_market_data(self, mock_data_manager):
        """测试空市场数据"""
        mock_data_manager.get_comprehensive_market_data.return_value = None
        
        result = main_strategy_loop(
            mock_data_manager, symbol="BTC-USDT", use_demo=True
        )
        
        # 验证错误处理
        assert result["signal"] == "HOLD"
        assert "Failed to fetch market data" in result["reason"]
    
    def test_main_strategy_loop_signal_validation_failed(self, mock_data_manager):
        """测试信号验证失败"""
        with patch('src.strategy_engine.main.validate_signal') as mock_validate:
            mock_validate.return_value = False
            
            result = main_strategy_loop(
                mock_data_manager, symbol="BTC-USDT", use_demo=True
            )
            
            # 验证错误处理
            assert result["signal"] == "HOLD"
            assert "Signal validation failed" in result["reason"]
    
    def test_main_strategy_loop_with_database(self, mock_data_manager):
        """测试带数据库存储的策略循环"""
        mock_postgres = Mock()
        mock_postgres.insert_ai_decision = Mock()
        
        with patch('src.strategy_engine.main.validate_signal') as mock_validate:
            mock_validate.return_value = True
            
            result = main_strategy_loop(
                mock_data_manager, symbol="BTC-USDT", 
                use_demo=True, postgres_db=mock_postgres
            )
            
            # 验证数据库存储
            mock_postgres.insert_ai_decision.assert_called_once()
            call_args = mock_postgres.insert_ai_decision.call_args[0][0]
            assert "decision_id" in call_args
            assert "input_data" in call_args
            assert "output_signal" in call_args
            assert "analysis_type" in call_args
            assert "timestamp" in call_args
    
    def test_main_strategy_loop_database_error_continues(self, mock_data_manager):
        """测试数据库错误时继续执行"""
        mock_postgres = Mock()
        mock_postgres.insert_ai_decision.side_effect = Exception("Database error")
        
        with patch('src.strategy_engine.main.validate_signal') as mock_validate:
            mock_validate.return_value = True
            
            result = main_strategy_loop(
                mock_data_manager, symbol="BTC-USDT", 
                use_demo=True, postgres_db=mock_postgres
            )
            
            # 验证仍然成功执行
            assert result["signal"] in ["BUY", "SELL", "HOLD"]
    
    def test_main_strategy_loop_exception_handling(self, mock_data_manager):
        """测试异常处理"""
        mock_data_manager.get_comprehensive_market_data.side_effect = Exception("Unexpected error")
        
        result = main_strategy_loop(
            mock_data_manager, symbol="BTC-USDT", use_demo=True
        )
        
        # 验证异常处理
        assert result["signal"] == "HOLD"
        assert "Unexpected error: Unexpected error" in result["reason"]
        assert "decision_id" in result
        assert "timestamp" in result


class TestFormatIndicatorsForPrompt:
    """_format_indicators_for_prompt函数测试"""
    
    def test_format_indicators_complete(self):
        """测试完整指标格式化"""
        indicators = {
            "current_price": 50000.0,
            "rsi": 65.5,
            "macd": {"macd": 0.1234, "signal": 0.0567},
            "bollinger": {"upper": 51000, "middle": 50000, "lower": 49000},
            "ema_20": 50200,
            "ema_50": 49800,
            "trend": "upward",
            "momentum": "strong",
            "volatility": "medium",
            "support_resistance": {"support": 49500, "resistance": 51000}
        }
        
        result = _format_indicators_for_prompt(indicators)
        
        # 验证关键信息
        assert "当前价格: 50000.00" in result
        assert "RSI: 65.50" in result
        assert "MACD: 0.1234, 信号: 0.0567" in result
        assert "布林带: 上轨 51000.00, 中轨 50000.00, 下轨 49000.00" in result
        assert "EMA20: 50200.00, EMA50: 49800.00" in result
        assert "趋势: upward" in result
        assert "动量: strong" in result
        assert "波动性: medium" in result
        assert "支撑位: 49500.00" in result
        assert "阻力位: 51000.00" in result
    
    def test_format_indicators_empty(self):
        """测试空指标"""
        result = _format_indicators_for_prompt({})
        assert result == "技术指标数据不足"
    
    def test_format_indicators_error(self):
        """测试错误指标"""
        indicators = {"error": "Data not available"}
        result = _format_indicators_for_prompt(indicators)
        assert result == "技术指标数据不足"
    
    def test_format_indicators_partial(self):
        """测试部分指标"""
        indicators = {
            "current_price": 50000,
            "rsi": "N/A",
            "macd": {"macd": None, "signal": 0.1}
        }
        
        result = _format_indicators_for_prompt(indicators)
        
        assert "当前价格: 50000.00" in result
        assert "RSI: N/A" in result
        assert "MACD: N/A, 信号: 0.10" in result
    
    def test_format_indicators_none_values(self):
        """测试None值处理"""
        indicators = {
            "current_price": None,
            "rsi": None,
            "trend": None
        }
        
        result = _format_indicators_for_prompt(indicators)
        
        assert "当前价格: N/A" in result
        assert "RSI: N/A" in result
        assert "趋势: N/A" in result


class TestFormatOrderbookForPrompt:
    """_format_orderbook_for_prompt函数测试"""
    
    def test_format_orderbook_complete(self):
        """测试完整订单簿格式化"""
        orderbook = {
            "bids": [[49900, 0.1], [49800, 0.2], [49700, 0.3]],
            "asks": [[50100, 0.1], [50200, 0.2], [50300, 0.3]]
        }
        
        result = _format_orderbook_for_prompt(orderbook)
        
        # 验证关键信息
        assert "订单簿分析:" in result
        assert "买单 1: 价格 49900.00, 数量 0.1000" in result
        assert "卖单 1: 价格 50100.00, 数量 0.1000" in result
        assert "最佳买价: 49900.00" in result
        assert "最佳卖价: 50100.00" in result
        assert "价差: 200.00" in result
    
    def test_format_orderbook_dict_format(self):
        """测试字典格式订单簿"""
        orderbook = {
            "bids": [
                {"price": 49900, "amount": 0.1},
                {"price": 49800, "amount": 0.2}
            ],
            "asks": [
                {"price": 50100, "amount": 0.1},
                {"price": 50200, "amount": 0.2}
            ]
        }
        
        result = _format_orderbook_for_prompt(orderbook)
        
        assert "买单 1: 价格 49900.00, 数量 0.1000" in result
        assert "卖单 1: 价格 50100.00, 数量 0.1000" in result
    
    def test_format_orderbook_empty(self):
        """测试空订单簿"""
        result = _format_orderbook_for_prompt({})
        assert result == "订单簿数据不可用"
    
    def test_format_orderbook_partial(self):
        """测试部分订单簿"""
        orderbook = {
            "bids": [[49900, 0.1]],
            "asks": []
        }
        
        result = _format_orderbook_for_prompt(orderbook)
        
        assert "买单 1: 价格 49900.00, 数量 0.1000" in result
        assert "最佳买价: 49900.00" in result
        assert "最佳卖价: 0.00" in result


class TestFormatVolumeProfileForPrompt:
    """_format_volume_profile_for_prompt函数测试"""
    
    def test_format_volume_profile_complete(self):
        """测试完整成交量分布格式化"""
        volume_profile = {
            "poc": 50000,
            "value_area": {"high": 51000, "low": 49000}
        }
        
        result = _format_volume_profile_for_prompt(volume_profile)
        
        # 验证关键信息
        assert "成交量分布:" in result
        assert "控制点价格 (POC): 50000.00" in result
        assert "价值区域高: 51000.00" in result
        assert "价值区域低: 49000.00" in result
    
    def test_format_volume_profile_empty(self):
        """测试空成交量分布"""
        result = _format_volume_profile_for_prompt({})
        assert result == "成交量分布数据不可用"
    
    def test_format_volume_profile_partial(self):
        """测试部分成交量分布"""
        volume_profile = {"poc": 50000}
        
        result = _format_volume_profile_for_prompt(volume_profile)
        
        assert "成交量分布:" in result
        assert "控制点价格 (POC): 50000.00" in result
        assert "价值区域高: 0.00" in result
        assert "价值区域低: 0.00" in result


class TestFormatSentimentForPrompt:
    """_format_sentiment_for_prompt函数测试"""
    
    def test_format_sentiment_complete(self):
        """测试完整市场情绪格式化"""
        sentiment = {
            "overall_sentiment": "bullish",
            "sentiment_score": 0.75,
            "orderbook_imbalance": 0.3,
            "trade_imbalance": 0.2,
            "technical_momentum": "strong",
            "technical_trend": "upward"
        }
        
        result = _format_sentiment_for_prompt(sentiment)
        
        # 验证关键信息
        assert "市场情绪分析:" in result
        assert "整体情绪: bullish" in result
        assert "情绪分数: 0.750" in result
        assert "订单簿不平衡: 0.300" in result
        assert "交易不平衡: 0.200" in result
        assert "技术动量: strong" in result
        assert "技术趋势: upward" in result
    
    def test_format_sentiment_empty(self):
        """测试空市场情绪"""
        result = _format_sentiment_for_prompt({})
        assert result == "市场情绪数据不可用"
    
    def test_format_sentiment_partial(self):
        """测试部分市场情绪"""
        sentiment = {
            "overall_sentiment": "bearish",
            "sentiment_score": -0.5
        }
        
        result = _format_sentiment_for_prompt(sentiment)
        
        assert "市场情绪分析:" in result
        assert "整体情绪: bearish" in result
        assert "情绪分数: -0.500" in result


class TestMergeHistoricalWithCurrent:
    """_merge_historical_with_current函数测试"""
    
    def test_merge_historical_with_current_complete(self):
        """测试完整数据合并"""
        current_analysis = {
            "5m": {"current_price": 50000, "rsi": 50},
            "15m": {"current_price": 50000, "rsi": 55}
        }
        
        historical_analysis = {
            "5m": {
                "indicators": {
                    "rsi": 48,
                    "trend": "upward",
                    "momentum": "strong",
                    "data_points": 200,
                    "latest_timestamp": 1609459200000
                }
            },
            "15m": {
                "indicators": {
                    "rsi": 52,
                    "trend": "upward",
                    "momentum": "moderate",
                    "data_points": 200,
                    "latest_timestamp": 1609459200000
                }
            }
        }
        
        result = _merge_historical_with_current(current_analysis, historical_analysis)
        
        # 验证合并结果
        assert "5m" in result
        assert "15m" in result
        
        # 验证历史数据优先
        assert result["5m"]["data_source"] == "historical_enhanced"
        assert result["5m"]["rsi"] == 48  # 历史数据
        assert result["5m"]["current_price"] == 50000  # 当前价格覆盖
        assert result["5m"]["data_points"] == 200
        assert result["5m"]["trend"] == "upward"
    
    def test_merge_historical_with_current_fallback(self):
        """测试回退到当前数据"""
        current_analysis = {
            "5m": {"current_price": 50000, "rsi": 50},
            "15m": {"current_price": 50000, "rsi": 55}
        }
        
        historical_analysis = {}  # 空历史数据
        
        result = _merge_historical_with_current(current_analysis, historical_analysis)
        
        # 验证回退到当前数据
        assert result["5m"]["data_source"] == "current_only"
        assert result["5m"]["rsi"] == 50
        assert result["5m"]["current_price"] == 50000
    
    def test_merge_historical_with_current_no_data(self):
        """测试无可用数据"""
        current_analysis = {}
        historical_analysis = {}
        
        result = _merge_historical_with_current(current_analysis, historical_analysis)
        
        # 验证所有时间框架都标记为错误
        for timeframe in ["5m", "15m", "1h", "4h"]:
            assert timeframe in result
            assert "error" in result[timeframe]
    
    def test_merge_historical_with_current_exception(self):
        """测试异常处理"""
        current_analysis = {"5m": {"rsi": 50}}
        historical_analysis = {"5m": {"indicators": "invalid"}}
        
        result = _merge_historical_with_current(current_analysis, historical_analysis)
        
        # 验证回退到当前数据
        assert result == current_analysis


class TestFormatHistoricalTrendsForPrompt:
    """_format_historical_trends_for_prompt函数测试"""
    
    def test_format_historical_trends_complete(self):
        """测试完整历史趋势格式化"""
        historical_data = {
            "historical_analysis": {
                "5m": {
                    "indicators": {"trend": "upward", "momentum": "strong"},
                    "ohlcv": [[1609459200000, 49900, 50100, 49800, 50000, 100]],
                    "data_points": 200
                },
                "15m": {
                    "indicators": {"trend": "upward", "momentum": "moderate"},
                    "ohlcv": [[1609459200000, 49900, 50100, 49800, 50000, 100]],
                    "data_points": 200
                }
            }
        }
        
        with patch('src.strategy_engine.main._analyze_trend_consistency') as mock_consistency:
            mock_consistency.return_value = {"overall_consistency": "高度一致"}
            
            with patch('src.strategy_engine.main._identify_key_turning_points') as mock_turning:
                mock_turning.return_value = ["关键转折点1", "关键转折点2"]
                
                with patch('src.strategy_engine.main._analyze_volatility_across_timeframes') as mock_volatility:
                    mock_volatility.return_value = "5m:medium, 15m:low"
                    
                    result = _format_historical_trends_for_prompt(historical_data)
                    
                    # 验证关键信息
                    assert "历史趋势分析:" in result
                    assert "趋势一致性: 高度一致" in result
                    assert "关键转折点:" in result
                    assert "波动性分析: 5m:medium, 15m:low" in result
    
    def test_format_historical_trends_empty(self):
        """测试空历史数据"""
        result = _format_historical_trends_for_prompt({})
        assert result == "**历史趋势**: 数据不可用"
    
    def test_format_historical_trends_no_analysis(self):
        """测试无分析数据"""
        historical_data = {"other_data": "value"}
        result = _format_historical_trends_for_prompt(historical_data)
        assert result == "**历史趋势**: 数据不可用"


class TestAnalyzeTrendConsistency:
    """_analyze_trend_consistency函数测试"""
    
    def test_analyze_trend_consistency_high(self):
        """测试高度一致性"""
        historical_analysis = {
            "5m": {"indicators": {"trend": "upward", "momentum": "strong"}},
            "15m": {"indicators": {"trend": "upward", "momentum": "strong"}},
            "1h": {"indicators": {"trend": "upward", "momentum": "moderate"}},
            "4h": {"indicators": {"trend": "upward", "momentum": "strong"}}
        }
        
        result = _analyze_trend_consistency(historical_analysis)
        
        assert result["dominant_trend"] == "upward"
        assert result["dominant_momentum"] == "strong"
        assert result["consistency_score"] == 0.75
        assert result["overall_consistency"] == "高度一致"
    
    def test_analyze_trend_consistency_medium(self):
        """测试中等一致性"""
        historical_analysis = {
            "5m": {"indicators": {"trend": "upward", "momentum": "strong"}},
            "15m": {"indicators": {"trend": "upward", "momentum": "strong"}},
            "1h": {"indicators": {"trend": "downward", "momentum": "weak"}},
            "4h": {"indicators": {"trend": "downward", "momentum": "weak"}}
        }
        
        result = _analyze_trend_consistency(historical_analysis)
        
        assert result["consistency_score"] == 0.5
        assert result["overall_consistency"] == "中等一致"
    
    def test_analyze_trend_consistency_low(self):
        """测试低一致性"""
        historical_analysis = {
            "5m": {"indicators": {"trend": "upward", "momentum": "strong"}},
            "15m": {"indicators": {"trend": "downward", "momentum": "weak"}},
            "1h": {"indicators": {"trend": "sideways", "momentum": "neutral"}},
            "4h": {"indicators": {"trend": "upward", "momentum": "strong"}}
        }
        
        result = _analyze_trend_consistency(historical_analysis)
        
        assert result["consistency_score"] == 0.5
        assert result["overall_consistency"] == "中等一致"
    
    def test_analyze_trend_consistency_empty(self):
        """测试空数据"""
        result = _analyze_trend_consistency({})
        assert result["overall_consistency"] == "分析失败"


class TestIdentifyKeyTurningPoints:
    """_identify_key_turning_points函数测试"""
    
    def test_identify_key_turning_points_complete(self):
        """测试完整转折点识别"""
        historical_analysis = {
            "5m": {
                "ohlcv": [
                    [1609459200000, 49900, 50100, 49800, 50000, 100],
                    [1609459260000, 50000, 51000, 49900, 51000, 200],  # 2%变化，高成交量
                    [1609459320000, 51000, 51100, 50900, 51000, 50]
                ]
            }
        }
        
        result = _identify_key_turning_points(historical_analysis)
        
        # 验证识别到转折点
        assert len(result) > 0
        assert any("5m时间框架" in point for point in result)
    
    def test_identify_key_turning_points_insufficient_data(self):
        """测试数据不足"""
        historical_analysis = {
            "5m": {"ohlcv": [[1609459200000, 49900, 50100, 49800, 50000, 100]]}
        }
        
        result = _identify_key_turning_points(historical_analysis)
        
        # 验证无转折点
        assert len(result) == 0
    
    def test_identify_key_turning_points_no_ohlcv(self):
        """测试无OHLCV数据"""
        historical_analysis = {
            "5m": {"indicators": {"rsi": 50}}
        }
        
        result = _identify_key_turning_points(historical_analysis)
        
        # 验证无转折点
        assert len(result) == 0


class TestAnalyzeVolatilityAcrossTimeframes:
    """_analyze_volatility_across_timeframes函数测试"""
    
    def test_analyze_volatility_complete(self):
        """测试完整波动性分析"""
        historical_analysis = {
            "5m": {"indicators": {"volatility": "high"}},
            "15m": {"indicators": {"volatility": "medium"}},
            "1h": {"indicators": {"volatility": "low"}},
            "4h": {"indicators": {"volatility": "medium"}}
        }
        
        result = _analyze_volatility_across_timeframes(historical_analysis)
        
        assert "5m:high" in result
        assert "15m:medium" in result
        assert "1h:low" in result
        assert "4h:medium" in result
    
    def test_analyze_volatility_empty(self):
        """测试空数据"""
        result = _analyze_volatility_across_timeframes({})
        assert result == "波动性数据不可用"
    
    def test_analyze_volatility_no_indicators(self):
        """测试无指标数据"""
        historical_analysis = {
            "5m": {"other_data": "value"}
        }
        
        result = _analyze_volatility_across_timeframes(historical_analysis)
        assert result == "波动性数据不可用"


class TestStrategyEngineIntegration:
    """策略引擎集成测试"""
    
    def test_full_strategy_workflow(self):
        """测试完整策略工作流"""
        # 准备测试数据
        mock_data_manager = Mock()
        mock_data_manager.get_comprehensive_market_data.return_value = {
            "symbol": "BTC-USDT",
            "current_price": 50000.0,
            "technical_analysis": {
                "5m": {"rsi": 50, "trend": "upward"},
                "15m": {"rsi": 55, "trend": "upward"}
            },
            "orderbook": {"bids": [[49900, 0.1]], "asks": [[50100, 0.1]]},
            "volume_profile": {"poc": 50000},
            "market_sentiment": {"overall_sentiment": "bullish"},
            "account": {"balance": {"BTC": 1.0}},
            "data_status": "OK"
        }
        
        mock_data_manager.get_historical_with_indicators.return_value = {
            "historical_analysis": {
                "5m": {
                    "indicators": {"rsi": 48, "trend": "upward"},
                    "data_points": 200
                }
            }
        }
        
        with patch('src.strategy_engine.main.validate_signal') as mock_validate:
            mock_validate.return_value = True
            
            result = main_strategy_loop(
                mock_data_manager, symbol="BTC-USDT", use_demo=True
            )
            
            # 验证完整工作流
            assert result["signal"] in ["BUY", "SELL", "HOLD"]
            assert "decision_id" in result
            assert "enhanced_analysis" in result
            
            # 验证数据合并
            assert "5m" in result["enhanced_analysis"]
            assert result["enhanced_analysis"]["5m"]["data_source"] == "historical_enhanced"
    
    def test_strategy_error_recovery(self):
        """测试策略错误恢复"""
        mock_data_manager = Mock()
        mock_data_manager.get_comprehensive_market_data.side_effect = Exception("Data error")
        
        result = main_strategy_loop(
            mock_data_manager, symbol="BTC-USDT", use_demo=True
        )
        
        # 验证错误恢复
        assert result["signal"] == "HOLD"
        assert "Unexpected error" in result["reason"]
        assert "decision_id" in result
