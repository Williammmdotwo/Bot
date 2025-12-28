"""
CacheManager 单元测试
"""

import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock
import redis

from src.data_manager.utils.cache_manager import CacheManager


class TestCacheManager:
    """CacheManager 测试类"""

    def setup_method(self):
        """测试前设置"""
        self.mock_redis = Mock(spec=redis.Redis)
        self.cache_manager = CacheManager(self.mock_redis)

    def test_init(self):
        """测试初始化"""
        assert self.cache_manager.redis_client == self.mock_redis
        assert "1m" in self.cache_manager.OPTIMIZED_CACHE_DURATION
        assert self.cache_manager.OPTIMIZED_CACHE_DURATION["1m"] == 180

    def test_get_market_data_success(self):
        """测试成功获取市场数据"""
        # 模拟缓存数据
        test_data = {"symbol": "BTC-USDT", "price": 50000}
        cache_data = {
            "data": test_data,
            "timestamp": int(time.time()),
            "version": "2.0"
        }

        self.mock_redis.get.return_value = json.dumps(cache_data)

        result = self.cache_manager.get_market_data("BTC-USDT")

        assert result == test_data
        self.mock_redis.get.assert_called_once_with("market_data:BTC-USDT:v2")

    def test_get_market_data_no_cache(self):
        """测试获取市场数据无缓存"""
        self.mock_redis.get.return_value = None

        result = self.cache_manager.get_market_data("BTC-USDT")

        assert result is None
        self.mock_redis.get.assert_called_once_with("market_data:BTC-USDT:v2")

    def test_get_market_data_exception(self):
        """测试获取市场数据异常"""
        self.mock_redis.get.side_effect = Exception("Redis error")

        result = self.cache_manager.get_market_data("BTC-USDT")

        assert result is None

    def test_cache_market_data_success(self):
        """测试成功缓存市场数据"""
        test_data = {
            "symbol": "BTC-USDT",
            "price": 50000,
            "technical_analysis": {"rsi": 70},
            "ohlcv": {"5m": [[1609459200000, 50000, 50100, 49900, 50050, 100]]},
            "market_sentiment": {"bullish": 0.7}
        }

        self.cache_manager.cache_market_data("BTC-USDT", test_data)

        # 验证多个缓存键被设置
        assert self.mock_redis.setex.call_count >= 4

        # 验证调用参数
        calls = self.mock_redis.setex.call_args_list
        cache_keys = [call[0][0] for call in calls]

        assert "market_data:BTC-USDT:v2" in cache_keys
        assert "technical_analysis:BTC-USDT:v2" in cache_keys
        assert "ohlcv:BTC-USDT:5m:v2" in cache_keys
        assert "market_sentiment:BTC-USDT:v2" in cache_keys

    def test_cache_market_data_exception(self):
        """测试缓存市场数据异常"""
        self.mock_redis.setex.side_effect = Exception("Redis error")

        test_data = {"symbol": "BTC-USDT", "price": 50000}

        # 不应该抛出异常
        self.cache_manager.cache_market_data("BTC-USDT", test_data)

    def test_get_snapshot_success(self):
        """测试成功获取快照"""
        # 模拟Redis数据
        klines_data = [json.dumps([1609459200000, 50000, 50100, 49900, 50050, 100])]
        indicators_data = json.dumps({"rsi": 70})
        account_data = json.dumps({"balance": 1000})

        self.mock_redis.zrevrange.return_value = klines_data
        self.mock_redis.get.side_effect = [indicators_data, account_data]

        result = self.cache_manager.get_snapshot("BTC-USDT")

        assert result is not None
        assert result["symbol"] == "BTC-USDT"
        assert result["data_status"] == "OK"
        assert len(result["klines"]) == 1
        assert "indicators" in result
        assert "account" in result

    def test_get_snapshot_no_indicators(self):
        """测试获取快照但指标未就绪"""
        # 模拟无K线数据
        self.mock_redis.zrevrange.return_value = []

        result = self.cache_manager.get_snapshot("BTC-USDT")

        assert result is not None
        assert result["data_status"] == "INDICATORS_NOT_READY"

    def test_get_snapshot_exception(self):
        """测试获取快照异常"""
        self.mock_redis.zrevrange.side_effect = Exception("Redis error")

        result = self.cache_manager.get_snapshot("BTC-USDT")

        assert result is None

    def test_check_indicators_ready_true(self):
        """测试检查指标就绪 - 就绪"""
        self.mock_redis.zrevrange.return_value = ["data"]

        result = self.cache_manager._check_indicators_ready("BTC-USDT")

        assert result is True

    def test_check_indicators_ready_false(self):
        """测试检查指标就绪 - 未就绪"""
        self.mock_redis.zrevrange.return_value = []

        result = self.cache_manager._check_indicators_ready("BTC-USDT")

        assert result is False

    def test_check_indicators_ready_exception(self):
        """测试检查指标就绪异常"""
        self.mock_redis.zrevrange.side_effect = Exception("Redis error")

        result = self.cache_manager._check_indicators_ready("BTC-USDT")

        assert result is False

    def test_get_historical_data_success(self):
        """测试成功获取历史数据"""
        test_klines = [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        cache_data = {
            "klines": test_klines,
            "timestamp": int(time.time() * 1000),
            "timeframe": "5m",
            "count": 1
        }

        self.mock_redis.get.return_value = json.dumps(cache_data)

        result = self.cache_manager.get_historical_data("BTC-USDT", "5m")

        assert result == test_klines
        self.mock_redis.get.assert_called_once_with("historical_klines:BTC-USDT:5m")

    def test_get_historical_data_no_cache(self):
        """测试获取历史数据无缓存"""
        self.mock_redis.get.return_value = None

        result = self.cache_manager.get_historical_data("BTC-USDT", "5m")

        assert result is None

    def test_get_historical_data_expired(self):
        """测试获取历史数据已过期"""
        test_klines = [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        cache_data = {
            "klines": test_klines,
            "timestamp": int(time.time() * 1000) - 1000000,  # 过期时间戳
            "timeframe": "5m",
            "count": 1
        }

        self.mock_redis.get.return_value = json.dumps(cache_data)

        result = self.cache_manager.get_historical_data("BTC-USDT", "5m")

        assert result is None

    def test_get_historical_data_with_since(self):
        """测试获取历史数据指定开始时间"""
        test_klines = [
            [1609459200000, 50000, 50100, 49900, 50050, 100],
            [1609459260000, 50050, 50150, 49950, 50100, 150]
        ]
        cache_data = {
            "klines": test_klines,
            "timestamp": int(time.time() * 1000),
            "timeframe": "5m",
            "count": 2
        }

        self.mock_redis.get.return_value = json.dumps(cache_data)

        result = self.cache_manager.get_historical_data("BTC-USDT", "5m", since=1609459250000)

        assert len(result) == 1
        assert result[0][0] == 1609459260000

    def test_cache_historical_data_success(self):
        """测试成功缓存历史数据"""
        test_klines = [[1609459200000, 50000, 50100, 49900, 50050, 100]]

        self.cache_manager.cache_historical_data("BTC-USDT", "5m", test_klines)

        self.mock_redis.setex.assert_called_once()
        call_args = self.mock_redis.setex.call_args
        cache_key = call_args[0][0]
        cache_duration = call_args[0][1]
        cache_data = json.loads(call_args[0][2])

        assert cache_key == "historical_klines:BTC-USDT:5m"
        assert cache_data["klines"] == test_klines
        assert cache_data["count"] == 1

    def test_cache_historical_data_exception(self):
        """测试缓存历史数据异常"""
        self.mock_redis.setex.side_effect = Exception("Redis error")

        test_klines = [[1609459200000, 50000, 50100, 49900, 50050, 100]]

        # 不应该抛出异常
        self.cache_manager.cache_historical_data("BTC-USDT", "5m", test_klines)

    def test_get_cache_duration_optimized(self):
        """测试获取优化的缓存持续时间"""
        duration = self.cache_manager._get_cache_duration("1m")
        assert duration == 180000  # 3分钟

        duration = self.cache_manager._get_cache_duration("5m")
        assert duration == 900000  # 15分钟

        duration = self.cache_manager._get_cache_duration("1h")
        assert duration == 3600000  # 1小时

    def test_get_cache_duration_default(self):
        """测试获取默认缓存持续时间"""
        duration = self.cache_manager._get_cache_duration("30m")
        assert duration == 15 * 60 * 1000  # 15分钟

        duration = self.cache_manager._get_cache_duration("2h")
        assert duration == 30 * 60 * 1000  # 30分钟

    def test_timeframe_to_minutes(self):
        """测试时间框架转换为分钟"""
        assert self.cache_manager._timeframe_to_minutes("1m") == 1
        assert self.cache_manager._timeframe_to_minutes("5m") == 5
        assert self.cache_manager._timeframe_to_minutes("1h") == 60
        assert self.cache_manager._timeframe_to_minutes("1d") == 1440
        assert self.cache_manager._timeframe_to_minutes("unknown") == 5  # 默认值

    @patch('time.localtime')
    def test_get_smart_cache_duration_normal(self, mock_localtime):
        """测试智能缓存持续时间 - 正常情况"""
        mock_localtime.return_value.tm_hour = 20  # 非交易时间

        base_duration = self.cache_manager._get_cache_duration("5m")
        duration = self.cache_manager.get_smart_cache_duration("5m")

        assert duration == base_duration

    def test_get_smart_cache_duration_old_data(self):
        """测试智能缓存持续时间 - 旧数据"""
        base_duration = self.cache_manager._get_cache_duration("5m")
        duration = self.cache_manager.get_smart_cache_duration("5m", data_age=4000000)  # 超过1小时

        assert duration == base_duration // 2

    @patch('time.localtime')
    def test_get_smart_cache_duration_trading_hours(self, mock_localtime):
        """测试智能缓存持续时间 - 交易时间"""
        mock_localtime.return_value.tm_hour = 10  # 交易时间

        base_duration = self.cache_manager._get_cache_duration("5m")
        duration = self.cache_manager.get_smart_cache_duration("5m")

        assert duration == base_duration // 2

    def test_invalidate_symbol_cache_success(self):
        """测试成功清除符号缓存"""
        test_keys = ["market_data:BTC-USDT:v2", "ohlcv:BTC-USDT:5m:v2"]
        self.mock_redis.keys.return_value = test_keys
        self.mock_redis.delete.return_value = 2

        self.cache_manager.invalidate_symbol_cache("BTC-USDT")

        self.mock_redis.keys.assert_called_once_with("*:BTC-USDT:*")
        self.mock_redis.delete.assert_called_once_with(*test_keys)

    def test_invalidate_symbol_cache_no_keys(self):
        """测试清除符号缓存 - 无键"""
        self.mock_redis.keys.return_value = []

        self.cache_manager.invalidate_symbol_cache("BTC-USDT")

        self.mock_redis.delete.assert_not_called()

    def test_invalidate_symbol_cache_exception(self):
        """测试清除符号缓存异常"""
        self.mock_redis.keys.side_effect = Exception("Redis error")

        # 不应该抛出异常
        self.cache_manager.invalidate_symbol_cache("BTC-USDT")

    def test_get_cache_stats_success(self):
        """测试成功获取缓存统计"""
        mock_info = {
            "used_memory_human": "1.5M",
            "used_memory_peak_human": "2.0M",
            "keyspace_hits": 1000,
            "keyspace_misses": 100,
            "connected_clients": 5,
            "total_commands_processed": 5000
        }

        self.mock_redis.info.return_value = mock_info

        result = self.cache_manager.get_cache_stats()

        assert result["used_memory"] == "1.5M"
        assert result["keyspace_hits"] == 1000
        assert result["connected_clients"] == 5

    def test_get_cache_stats_exception(self):
        """测试获取缓存统计异常"""
        self.mock_redis.info.side_effect = Exception("Redis error")

        result = self.cache_manager.get_cache_stats()

        assert result == {}


class TestCacheManagerIntegration:
    """CacheManager 集成测试"""

    def setup_method(self):
        """测试前设置"""
        self.mock_redis = Mock(spec=redis.Redis)
        self.cache_manager = CacheManager(self.mock_redis)

    def test_complete_cache_workflow(self):
        """测试完整缓存工作流"""
        # 1. 缓存数据
        test_data = {
            "symbol": "BTC-USDT",
            "price": 50000,
            "technical_analysis": {"rsi": 70},
            "ohlcv": {"5m": [[1609459200000, 50000, 50100, 49900, 50050, 100]]}
        }

        self.cache_manager.cache_market_data("BTC-USDT", test_data)

        # 2. 获取数据
        cache_data = {
            "data": test_data,
            "timestamp": int(time.time()),
            "version": "2.0"
        }
        self.mock_redis.get.return_value = json.dumps(cache_data)

        result = self.cache_manager.get_market_data("BTC-USDT")

        assert result == test_data

        # 3. 清除缓存
        test_keys = ["market_data:BTC-USDT:v2"]
        self.mock_redis.keys.return_value = test_keys

        self.cache_manager.invalidate_symbol_cache("BTC-USDT")

        # 验证所有调用都正确执行
        assert self.mock_redis.setex.call_count > 0
        assert self.mock_redis.get.call_count > 0
        self.mock_redis.keys.assert_called()
        self.mock_redis.delete.assert_called()

    def test_error_recovery(self):
        """测试错误恢复"""
        # 模拟Redis连接失败
        self.mock_redis.get.side_effect = Exception("Connection failed")

        # 获取数据应该返回None而不是抛出异常
        result = self.cache_manager.get_market_data("BTC-USDT")
        assert result is None

        # 缓存数据应该不抛出异常
        test_data = {"symbol": "BTC-USDT", "price": 50000}
        self.cache_manager.cache_market_data("BTC-USDT", test_data)

        # 获取统计应该返回空字典而不是抛出异常
        self.mock_redis.info.side_effect = Exception("Connection failed")
        stats = self.cache_manager.get_cache_stats()
        assert stats == {}
