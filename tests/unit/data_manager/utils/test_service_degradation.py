"""
Service Degradation Manager Tests
Target: Improve coverage from 9.24% to 70%+
重点：修正断言字段名称和字符串匹配问题
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
import json

from src.data_manager.utils.service_degradation import ServiceDegradationManager


class TestServiceDegradationManager:
    """服务降级管理器测试"""

    def setup_method(self):
        """每个测试前初始化"""
        self.mock_rest_client = Mock()
        self.manager = ServiceDegradationManager(self.mock_rest_client)

    def test_initialization(self):
        """测试初始化"""
        assert self.manager.rest_client == self.mock_rest_client
        assert self.manager.logger is not None

    def test_get_degraded_snapshot_success(self):
        """测试成功获取降级快照"""
        # 模拟REST客户端返回数据
        self.mock_rest_client.fetch_ohlcv.return_value = [
            [1609459200000, 50000.0, 50100.0, 49900.0, 50000.0, 1000.0]
        ]
        self.mock_rest_client.fetch_balance.return_value = {"USDT": 10000}
        self.mock_rest_client.fetch_positions.return_value = []

        result = self.manager.get_degraded_snapshot("BTC-USDT")

        # 验证返回结构
        assert result["symbol"] == "BTC-USDT"
        assert result["data_status"] == "DEGRADED"
        assert "klines" in result
        assert "indicators" in result
        assert "account" in result

        # 验证K线数据格式
        assert len(result["klines"]) == 1
        assert result["klines"][0]["timestamp"] == 1609459200000
        assert result["klines"][0]["open"] == 50000.0
        assert result["klines"][0]["close"] == 50000.0

    def test_get_degraded_snapshot_no_data(self):
        """测试无数据时的降级快照"""
        # 模拟REST客户端返回None
        self.mock_rest_client.fetch_ohlcv.return_value = None

        result = self.manager.get_degraded_snapshot("BTC-USDT")

        assert result["data_status"] == "ERROR"
        assert result["klines"] == []
        assert result["indicators"] == {}

    def test_get_degraded_snapshot_exception(self):
        """测试异常情况"""
        # 模拟REST客户端抛出异常
        self.mock_rest_client.fetch_ohlcv.side_effect = Exception("API Error")

        result = self.manager.get_degraded_snapshot("BTC-USDT")

        # 应该返回ERROR状态而不是崩溃
        assert result["data_status"] == "ERROR"
        assert result["symbol"] == "BTC-USDT"

    def test_get_fallback_market_data(self):
        """测试最小回退数据"""
        result = self.manager.get_fallback_market_data("BTC-USDT", "TEST_ERROR")

        # 验证字段
        assert result["symbol"] == "BTC-USDT"
        assert result["current_price"] == 0
        assert result["ticker"] == {}
        assert result["orderbook"] == {}
        assert result["recent_trades"] == []
        assert result["klines"] == []
        assert result["indicators"] == {}
        assert result["account"] == {}
        assert result["technical_analysis"] == {}
        assert result["volume_profile"] == {}

        # 验证市场情绪（中性）
        assert result["market_sentiment"]["overall_sentiment"] == "neutral"
        assert result["market_sentiment"]["sentiment_score"] == 0.0

        # 验证状态和时间戳
        assert result["data_status"] == "MINIMAL_FALLBACK"
        assert result["error_type"] == "TEST_ERROR"
        assert "timestamp" in result
        assert isinstance(result["timestamp"], int)

    def test_try_partial_data_recovery_all_success(self):
        """测试全部组件恢复成功（recent_trades返回空列表会失败）"""
        # 模拟所有REST调用成功，但recent_trades返回空列表（会被视为失败）
        self.mock_rest_client.fetch_ticker.return_value = {"last": 50000.0}
        self.mock_rest_client.fetch_orderbook.return_value = {"bids": [], "asks": []}
        self.mock_rest_client.fetch_recent_trades.return_value = []  # 空列表会被视为失败
        self.mock_rest_client.fetch_ohlcv.return_value = [[1609459200000, 50000, 50100, 49900, 50000, 1000]]

        result = self.manager.try_partial_data_recovery("BTC-USDT")

        # 验证恢复结果
        assert result["data_status"] == "PARTIAL_RECOVERY"
        assert result["symbol"] == "BTC-USDT"
        assert "ticker" in result
        assert "orderbook" in result
        assert "basic_ohlcv" in result

        # 验证恢复的组件和失败的组件
        assert "ticker" in result["recovered_components"]
        assert "orderbook" in result["recovered_components"]
        assert "basic_ohlcv" in result["recovered_components"]
        assert "recent_trades" in result["failed_components"]  # 空列表会被视为失败
        assert len(result["recovered_components"]) == 3
        assert len(result["failed_components"]) == 1

    def test_try_partial_data_recovery_partial_success(self):
        """测试部分组件恢复成功"""
        # 模拟部分成功部分失败
        self.mock_rest_client.fetch_ticker.return_value = {"last": 50000.0}
        self.mock_rest_client.fetch_orderbook.side_effect = Exception("Orderbook Error")
        self.mock_rest_client.fetch_recent_trades.return_value = []  # 空列表会被视为失败
        self.mock_rest_client.fetch_ohlcv.return_value = [[1609459200000, 50000, 50100, 49900, 50000, 1000]]

        result = self.manager.try_partial_data_recovery("BTC-USDT")

        # 验证部分恢复
        assert result["data_status"] == "PARTIAL_RECOVERY"
        assert "ticker" in result["recovered_components"]
        assert "orderbook" in result["failed_components"]
        assert "recent_trades" in result["failed_components"]  # 空列表会被视为失败
        assert len(result["recovered_components"]) == 2  # ticker, basic_ohlcv
        assert len(result["failed_components"]) == 2  # orderbook, recent_trades

    def test_try_partial_data_recovery_all_failed(self):
        """测试所有组件恢复失败"""
        # 模拟所有REST调用失败
        self.mock_rest_client.fetch_ticker.side_effect = Exception("Ticker Error")
        self.mock_rest_client.fetch_orderbook.side_effect = Exception("Orderbook Error")
        self.mock_rest_client.fetch_recent_trades.side_effect = Exception("Trades Error")
        self.mock_rest_client.fetch_ohlcv.side_effect = Exception("OHLCV Error")

        result = self.manager.try_partial_data_recovery("BTC-USDT")

        # 应该回退到最小数据
        assert result["data_status"] == "MINIMAL_FALLBACK"
        assert "error_type" in result
        assert result["error_type"] == "PARTIAL_RECOVERY_FAILED"

    def test_try_partial_data_recovery_exception(self):
        """测试部分数据恢复异常（ticker失败，但basic_ohlcv成功）"""
        # 模拟ticker失败但basic_ohlcv成功
        self.mock_rest_client.fetch_ticker.side_effect = RuntimeError("Unexpected Error")
        self.mock_rest_client.fetch_orderbook.side_effect = Exception("Orderbook Error")
        self.mock_rest_client.fetch_recent_trades.return_value = []
        self.mock_rest_client.fetch_ohlcv.return_value = [[1609459200000, 50000, 50100, 49900, 50000, 1000]]

        result = self.manager.try_partial_data_recovery("BTC-USDT")

        # basic_ohlcv成功，所以仍然返回PARTIAL_RECOVERY
        assert result["data_status"] == "PARTIAL_RECOVERY"
        assert "basic_ohlcv" in result["recovered_components"]

    def test_get_service_health_status_all_healthy(self):
        """测试所有端点健康（ohlcv返回数据）"""
        # 模拟所有端点正常，ohlcv必须返回非空数据
        self.mock_rest_client.fetch_ticker.return_value = {"last": 50000.0}
        self.mock_rest_client.fetch_orderbook.return_value = {"bids": [], "asks": []}
        self.mock_rest_client.fetch_ohlcv.return_value = [[1609459200000, 50000, 50100, 49900, 50000, 1000]]  # 非空
        self.mock_rest_client.fetch_balance.return_value = {"USDT": 10000}

        result = self.manager.get_service_health_status()

        # 验证健康状态
        assert result["service_status"] == "healthy"
        assert "ticker" in result["available_endpoints"]
        assert "orderbook" in result["available_endpoints"]
        assert "ohlcv" in result["available_endpoints"]
        assert "balance" in result["available_endpoints"]
        assert len(result["failed_endpoints"]) == 0

        # 验证响应时间
        assert "response_times" in result
        assert "ticker" in result["response_times"]
        assert "orderbook" in result["response_times"]
        assert "ohlcv" in result["response_times"]
        assert "balance" in result["response_times"]

    def test_get_service_health_status_partial_failed(self):
        """测试部分端点失败"""
        # ticker和orderbook失败，但ohlcv和balance成功
        self.mock_rest_client.fetch_ticker.side_effect = Exception("Ticker Error")
        self.mock_rest_client.fetch_orderbook.side_effect = Exception("Orderbook Error")
        self.mock_rest_client.fetch_ohlcv.return_value = [[1609459200000, 50000, 50100, 49900, 50000, 1000]]  # 非空
        self.mock_rest_client.fetch_balance.return_value = {"USDT": 10000}

        result = self.manager.get_service_health_status()

        # 2个失败，2个成功，失败数<=总数/2，所以是degraded
        assert result["service_status"] == "degraded"
        assert "ticker" in result["failed_endpoints"]
        assert "orderbook" in result["failed_endpoints"]
        assert "ohlcv" in result["available_endpoints"]
        assert "balance" in result["available_endpoints"]

        # 验证错误率
        assert "error_rates" in result
        assert result["error_rates"]["ticker"] == 1.0
        assert result["error_rates"]["orderbook"] == 1.0

    def test_get_service_health_status_all_failed(self):
        """测试所有端点失败"""
        self.mock_rest_client.fetch_ticker.side_effect = Exception("Error")
        self.mock_rest_client.fetch_orderbook.side_effect = Exception("Error")
        self.mock_rest_client.fetch_ohlcv.side_effect = Exception("Error")
        self.mock_rest_client.fetch_balance.side_effect = Exception("Error")

        result = self.manager.get_service_health_status()

        # 所有端点都失败，但总数是4，失败数是4，4<=4//2=2为False，所以返回unhealthy
        assert result["service_status"] == "unhealthy"
        assert len(result["available_endpoints"]) == 0
        assert len(result["failed_endpoints"]) == 4

    def test_get_service_health_status_exception(self):
        """测试健康检查异常（只是ticker失败，其他成功）"""
        # ticker失败，其他成功
        self.mock_rest_client.fetch_ticker.side_effect = RuntimeError("Unexpected Error")
        self.mock_rest_client.fetch_orderbook.return_value = {"bids": [], "asks": []}
        self.mock_rest_client.fetch_ohlcv.return_value = [[1609459200000, 50000, 50100, 49900, 50000, 1000]]
        self.mock_rest_client.fetch_balance.return_value = {"USDT": 10000}

        result = self.manager.get_service_health_status()

        # 1个失败，3个成功，失败数<=总数/2，所以是degraded
        assert result["service_status"] == "degraded"
        assert "ticker" in result["failed_endpoints"]

    def test_should_enable_degradation_unhealthy(self):
        """测试不健康状态启用降级"""
        health_status = {
            "service_status": "unhealthy"
        }

        result = self.manager.should_enable_degradation(health_status)

        assert result is True

    def test_should_enable_degradation_critical(self):
        """测试关键状态启用降级"""
        health_status = {
            "service_status": "critical"
        }

        result = self.manager.should_enable_degradation(health_status)

        assert result is True

    def test_should_enable_degradation_slow_response(self):
        """测试响应时间过长启用降级"""
        health_status = {
            "service_status": "healthy",
            "response_times": {
                "ticker": 15.0,  # 超过10秒
                "orderbook": 1.0,
                "ohlcv": 2.0,
                "balance": 1.5
            }
        }

        result = self.manager.should_enable_degradation(health_status)

        assert result is True

    def test_should_enable_degradation_high_error_rate(self):
        """测试错误率过高启用降级"""
        health_status = {
            "service_status": "healthy",
            "response_times": {},
            "error_rates": {
                "ticker": 0.6,  # 超过50%
                "orderbook": 0.3,
                "ohlcv": 0.4
            }
        }

        result = self.manager.should_enable_degradation(health_status)

        assert result is True

    def test_should_enable_degradation_healthy(self):
        """测试健康状态不启用降级"""
        health_status = {
            "service_status": "healthy",
            "response_times": {
                "ticker": 1.0,
                "orderbook": 2.0,
                "ohlcv": 3.0,
                "balance": 1.5
            },
            "error_rates": {
                "ticker": 0.1,
                "orderbook": 0.2,
                "ohlcv": 0.3
            }
        }

        result = self.manager.should_enable_degradation(health_status)

        assert result is False

    def test_get_degradation_strategy_minimal(self):
        """测试最小服务策略"""
        health_status = {
            "failed_endpoints": ["ticker", "orderbook", "ohlcv", "balance"]
        }

        result = self.manager.get_degradation_strategy(health_status)

        assert result == "minimal"

    def test_get_degradation_strategy_cached(self):
        """测试缓存服务策略"""
        health_status = {
            "failed_endpoints": ["ohlcv", "balance"]
        }

        result = self.manager.get_degradation_strategy(health_status)

        assert result == "cached"

    def test_get_degradation_strategy_partial(self):
        """测试部分服务策略"""
        health_status = {
            "failed_endpoints": ["ticker"]
        }

        result = self.manager.get_degradation_strategy(health_status)

        assert result == "partial"

    def test_get_degradation_strategy_full(self):
        """测试完整服务策略"""
        health_status = {
            "failed_endpoints": []
        }

        result = self.manager.get_degradation_strategy(health_status)

        assert result == "full"

    def test_get_degradation_strategy_unknown(self):
        """测试未知策略"""
        health_status = {
            "failed_endpoints": ["unknown_endpoint"]
        }

        result = self.manager.get_degradation_strategy(health_status)

        # 1个失败，不符合任何条件，返回partial
        assert result == "partial"

    def test_fetch_degraded_data_from_rest_success(self):
        """测试成功从REST获取降级数据"""
        # 模拟成功返回
        self.mock_rest_client.fetch_ohlcv.return_value = [
            [1609459200000, 50000.0, 50100.0, 49900.0, 50000.0, 1000.0],
            [16094592300000, 50100.0, 50200.0, 50000.0, 50100.0, 1200.0]
        ]
        self.mock_rest_client.fetch_balance.return_value = {"USDT": 10000}
        self.mock_rest_client.fetch_positions.return_value = [
            {"symbol": "BTC-USDT", "size": 0.1}
        ]

        result = self.manager._fetch_degraded_data_from_rest("BTC-USDT")

        # 验证返回结构
        assert result is not None
        assert "klines" in result
        assert "indicators" in result
        assert "account" in result

        # 验证K线数据转换
        assert len(result["klines"]) == 2
        assert result["klines"][0]["timestamp"] == 1609459200000
        assert result["klines"][0]["open"] == 50000.0
        assert result["klines"][0]["high"] == 50100.0
        assert result["klines"][0]["low"] == 49900.0
        assert result["klines"][0]["close"] == 50000.0
        assert result["klines"][0]["volume"] == 1000.0

        # 验证账户数据
        assert "balance" in result["account"]
        assert "positions" in result["account"]
        assert len(result["indicators"]) == 0  # 降级模式不计算复杂指标

    def test_fetch_degraded_data_from_rest_exception(self):
        """测试REST获取降级数据异常"""
        self.mock_rest_client.fetch_ohlcv.side_effect = Exception("API Error")

        result = self.manager._fetch_degraded_data_from_rest("BTC-USDT")

        assert result is None

    def test_try_recover_ticker_success(self):
        """测试成功恢复ticker数据"""
        recovery_data = {"recovered_components": [], "failed_components": []}
        self.mock_rest_client.fetch_ticker.return_value = {"last": 50000.0, "bid": 49990.0}

        self.manager._try_recover_ticker("BTC-USDT", recovery_data)

        assert "ticker" in recovery_data["recovered_components"]
        assert recovery_data["ticker"] == {"last": 50000.0, "bid": 49990.0}

    def test_try_recover_ticker_failed(self):
        """测试ticker恢复失败"""
        recovery_data = {"recovered_components": [], "failed_components": []}
        self.mock_rest_client.fetch_ticker.side_effect = Exception("Ticker Error")

        self.manager._try_recover_ticker("BTC-USDT", recovery_data)

        assert "ticker" in recovery_data["failed_components"]

    def test_try_recover_ticker_none(self):
        """测试ticker返回None"""
        recovery_data = {"recovered_components": [], "failed_components": []}
        self.mock_rest_client.fetch_ticker.return_value = None

        self.manager._try_recover_ticker("BTC-USDT", recovery_data)

        assert "ticker" in recovery_data["failed_components"]

    def test_try_recover_orderbook_success(self):
        """测试成功恢复orderbook数据"""
        recovery_data = {"recovered_components": [], "failed_components": []}
        self.mock_rest_client.fetch_orderbook.return_value = {"bids": [[50000, 1]], "asks": [[50100, 1]]}

        self.manager._try_recover_orderbook("BTC-USDT", recovery_data)

        assert "orderbook" in recovery_data["recovered_components"]

    def test_try_recover_orderbook_failed(self):
        """测试orderbook恢复失败"""
        recovery_data = {"recovered_components": [], "failed_components": []}
        self.mock_rest_client.fetch_orderbook.side_effect = Exception("Orderbook Error")

        self.manager._try_recover_orderbook("BTC-USDT", recovery_data)

        assert "orderbook" in recovery_data["failed_components"]

    def test_try_recover_recent_trades_success(self):
        """测试成功恢复recent_trades数据"""
        recovery_data = {"recovered_components": [], "failed_components": []}
        self.mock_rest_client.fetch_recent_trades.return_value = [
            {"timestamp": 16094592000, "price": 50000, "amount": 1.0}
        ]

        self.manager._try_recover_recent_trades("BTC-USDT", recovery_data)

        assert "recent_trades" in recovery_data["recovered_components"]

    def test_try_recover_recent_trades_failed(self):
        """测试recent_trades恢复失败"""
        recovery_data = {"recovered_components": [], "failed_components": []}
        self.mock_rest_client.fetch_recent_trades.side_effect = Exception("Trades Error")

        self.manager._try_recover_recent_trades("BTC-USDT", recovery_data)

        assert "recent_trades" in recovery_data["failed_components"]

    def test_try_recover_basic_ohlcv_success(self):
        """测试成功恢复basic_ohlcv数据"""
        recovery_data = {"recovered_components": [], "failed_components": []}
        self.mock_rest_client.fetch_ohlcv.return_value = [
            [16094592000, 50000, 50100, 49900, 50000, 1000]
        ]

        self.manager._try_recover_basic_ohlcv("BTC-USDT", recovery_data)

        assert "basic_ohlcv" in recovery_data["recovered_components"]

    def test_try_recover_basic_ohlcv_failed(self):
        """测试basic_ohlcv恢复失败"""
        recovery_data = {"recovered_components": [], "failed_components": []}
        self.mock_rest_client.fetch_ohlcv.side_effect = Exception("OHLCV Error")

        self.manager._try_recover_basic_ohlcv("BTC-USDT", recovery_data)

        assert "basic_ohlcv" in recovery_data["failed_components"]
