"""
MarketDataFetcher 单元测试
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock

from src.data_manager.core.market_data_fetcher import MarketDataFetcher
from src.data_manager.clients.rest_client import RESTClient


class TestMarketDataFetcher:
    """MarketDataFetcher 测试类"""

    def setup_method(self):
        """测试前设置"""
        self.mock_rest_client = Mock(spec=RESTClient)
        self.market_data_fetcher = MarketDataFetcher(self.mock_rest_client)

    def test_init(self):
        """测试初始化"""
        assert self.market_data_fetcher.rest_client == self.mock_rest_client
        assert self.market_data_fetcher.logger is not None

    @patch('src.data_manager.core.market_data_fetcher.RESTClient')
    def test_get_comprehensive_market_data_success(self, mock_rest_client_class):
        """测试成功获取综合市场数据"""
        # 模拟REST客户端
        mock_rest_instance = Mock()
        mock_rest_client_class.return_value = mock_rest_instance

        # 模拟市场信息
        market_info = {
            "symbol": "BTC-USDT",
            "ticker": {"last": 50000, "volume": 1000},
            "orderbook": {"bids": [[49900, 1]], "asks": [[50100, 1]]},
            "recent_trades": [{"price": 50000, "size": 0.1, "side": "buy"}],
            "ohlcv": {"5m": [[1609459200000, 50000, 50100, 49900, 50050, 100]]},
            "timestamp": int(time.time() * 1000)
        }
        mock_rest_instance.get_market_info.return_value = market_info

        result = self.market_data_fetcher.get_comprehensive_market_data("BTC-USDT")

        assert result is not None
        assert result["symbol"] == "BTC-USDT"
        assert result["current_price"] == 50000
        assert "ticker" in result
        assert "orderbook" in result
        assert "ohlcv" in result
        assert result["use_demo"] is False

    @patch('src.data_manager.core.market_data_fetcher.RESTClient')
    def test_get_comprehensive_market_data_demo(self, mock_rest_client_class):
        """测试获取综合市场数据 - 演示模式"""
        mock_rest_instance = Mock()
        mock_rest_client_class.return_value = mock_rest_instance

        market_info = {
            "symbol": "BTC-USDT",
            "ticker": {"last": 50000},
            "orderbook": {},
            "recent_trades": [],
            "ohlcv": {},
            "timestamp": int(time.time() * 1000)
        }
        mock_rest_instance.get_market_info.return_value = market_info

        result = self.market_data_fetcher.get_comprehensive_market_data("BTC-USDT", use_demo=True)

        assert result is not None
        assert result["use_demo"] is True
        mock_rest_client_class.assert_called_with(use_demo=True)

    @patch('src.data_manager.core.market_data_fetcher.RESTClient')
    def test_get_comprehensive_market_data_rest_client_error(self, mock_rest_client_class):
        """测试获取综合市场数据 - REST客户端初始化失败"""
        mock_rest_client_class.side_effect = Exception("REST client init failed")

        result = self.market_data_fetcher.get_comprehensive_market_data("BTC-USDT")

        assert result is None

    @patch('src.data_manager.core.market_data_fetcher.RESTClient')
    def test_get_comprehensive_market_data_fallback(self, mock_rest_client_class):
        """测试获取综合市场数据 - 服务降级"""
        mock_rest_instance = Mock()
        mock_rest_client_class.return_value = mock_rest_instance

        # 模拟get_market_info失败，但降级数据成功
        mock_rest_instance.get_market_info.return_value = None
        mock_rest_instance.fetch_ticker.return_value = {"last": 50000}
        mock_rest_instance.fetch_orderbook.return_value = {"bids": [[49900, 1]]}
        mock_rest_instance.fetch_ohlcv.return_value = [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        mock_rest_instance.fetch_recent_trades.return_value = [{"price": 50000, "size": 0.1}]

        result = self.market_data_fetcher.get_comprehensive_market_data("BTC-USDT")

        assert result is not None
        assert result["symbol"] == "BTC-USDT"
        assert result["ticker"]["last"] == 50000

    def test_get_market_info_with_fallback_success(self):
        """测试获取市场信息成功"""
        market_info = {"symbol": "BTC-USDT", "ticker": {"last": 50000}}
        self.mock_rest_client.get_market_info.return_value = market_info

        result = self.market_data_fetcher._get_market_info_with_fallback(
            self.mock_rest_client, "BTC-USDT"
        )

        assert result == market_info
        self.mock_rest_client.get_market_info.assert_called_once_with("BTC-USDT")

    def test_get_market_info_with_fallback_degraded(self):
        """测试获取市场信息 - 降级模式"""
        self.mock_rest_client.get_market_info.return_value = None
        self.mock_rest_client.fetch_ticker.return_value = {"last": 50000}
        self.mock_rest_client.fetch_orderbook.return_value = {}
        self.mock_rest_client.fetch_ohlcv.return_value = []
        self.mock_rest_client.fetch_recent_trades.return_value = []

        result = self.market_data_fetcher._get_market_info_with_fallback(
            self.mock_rest_client, "BTC-USDT"
        )

        assert result is not None
        assert result["symbol"] == "BTC-USDT"
        assert result["ticker"]["last"] == 50000

    def test_get_degraded_market_data_success(self):
        """测试获取降级市场数据成功"""
        self.mock_rest_client.fetch_ticker.return_value = {"last": 50000}
        self.mock_rest_client.fetch_orderbook.return_value = {"bids": [[49900, 1]]}
        self.mock_rest_client.fetch_ohlcv.return_value = [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        self.mock_rest_client.fetch_recent_trades.return_value = [{"price": 50000, "size": 0.1}]

        result = self.market_data_fetcher._get_degraded_market_data(
            self.mock_rest_client, "BTC-USDT"
        )

        assert result is not None
        assert result["symbol"] == "BTC-USDT"
        assert result["ticker"]["last"] == 50000
        assert result["orderbook"]["bids"] == [[49900, 1]]
        assert len(result["ohlcv"]) > 0
        assert len(result["recent_trades"]) > 0

    def test_get_degraded_market_data_no_data(self):
        """测试获取降级市场数据 - 无数据"""
        self.mock_rest_client.fetch_ticker.return_value = None
        self.mock_rest_client.fetch_orderbook.return_value = None
        self.mock_rest_client.fetch_ohlcv.return_value = None
        self.mock_rest_client.fetch_recent_trades.return_value = None

        result = self.market_data_fetcher._get_degraded_market_data(
            self.mock_rest_client, "BTC-USDT"
        )

        assert result is None

    def test_try_get_ticker_success(self):
        """测试尝试获取ticker数据成功"""
        ticker_data = {"last": 50000, "volume": 1000}
        self.mock_rest_client.fetch_ticker.return_value = ticker_data

        data = {}
        self.market_data_fetcher._try_get_ticker(self.mock_rest_client, "BTC-USDT", data)

        assert data["ticker"] == ticker_data

    def test_try_get_ticker_failure(self):
        """测试尝试获取ticker数据失败"""
        self.mock_rest_client.fetch_ticker.side_effect = Exception("API error")

        data = {}
        self.market_data_fetcher._try_get_ticker(self.mock_rest_client, "BTC-USDT", data)

        assert data.get("ticker") is None

    def test_try_get_orderbook_success(self):
        """测试尝试获取订单簿数据成功"""
        orderbook_data = {"bids": [[49900, 1]], "asks": [[50100, 1]]}
        self.mock_rest_client.fetch_orderbook.return_value = orderbook_data

        data = {}
        self.market_data_fetcher._try_get_orderbook(self.mock_rest_client, "BTC-USDT", data)

        assert data["orderbook"] == orderbook_data

    def test_try_get_ohlcv_success(self):
        """测试尝试获取OHLCV数据成功"""
        ohlcv_data = [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        self.mock_rest_client.fetch_ohlcv.return_value = ohlcv_data

        data = {}
        self.market_data_fetcher._try_get_ohlcv(self.mock_rest_client, "BTC-USDT", data)

        assert "5m" in data["ohlcv"]
        assert data["ohlcv"]["5m"] == ohlcv_data

    def test_try_get_recent_trades_success(self):
        """测试尝试获取最近交易数据成功"""
        trades_data = [{"price": 50000, "size": 0.1, "side": "buy"}]
        self.mock_rest_client.fetch_recent_trades.return_value = trades_data

        data = {}
        self.market_data_fetcher._try_get_recent_trades(self.mock_rest_client, "BTC-USDT", data)

        assert data["recent_trades"] == trades_data

    @patch('src.data_manager.core.market_data_fetcher.TechnicalIndicators')
    def test_calculate_all_timeframe_indicators_success(self, mock_technical_indicators):
        """测试计算所有时间框架技术指标成功"""
        mock_technical_indicators.calculate_all_indicators.return_value = {"rsi": 70}

        ohlcv_data = {
            "5m": [[1609459200000, 50000, 50100, 49900, 50050, 100]],
            "15m": [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        }

        result = self.market_data_fetcher._calculate_all_timeframe_indicators(ohlcv_data)

        assert "5m" in result
        assert "15m" in result
        assert result["5m"]["rsi"] == 70

    def test_calculate_all_timeframe_indicators_empty_data(self):
        """测试计算所有时间框架技术指标 - 空数据"""
        ohlcv_data = {}

        result = self.market_data_fetcher._calculate_all_timeframe_indicators(ohlcv_data)

        assert result == {}

    def test_extract_market_state_success(self):
        """测试提取市场状态成功"""
        market_info = {
            "ticker": {"last": 50000, "volume": 1000},
            "orderbook": {"bids": [[49900, 1]], "asks": [[50100, 1]]}
        }

        current_price, orderbook, ticker = self.market_data_fetcher._extract_market_state(market_info)

        assert current_price == 50000
        assert orderbook == {"bids": [[49900, 1]], "asks": [[50100, 1]]}
        assert ticker == {"last": 50000, "volume": 1000}

    def test_extract_market_state_invalid_price(self):
        """测试提取市场状态 - 无效价格"""
        market_info = {
            "ticker": {"last": 0, "volume": 1000},
            "orderbook": {"bids": [[49900, 1]], "asks": [[50100, 1]]}
        }

        current_price, orderbook, ticker = self.market_data_fetcher._extract_market_state(market_info)

        assert current_price == 50000.0  # 从订单簿推导的价格
        assert orderbook == {"bids": [[49900, 1]], "asks": [[50100, 1]]}

    @patch('src.data_manager.core.market_data_fetcher.RESTClient')
    def test_get_historical_klines_success(self, mock_rest_client_class):
        """测试获取历史K线数据成功"""
        mock_rest_instance = Mock()
        mock_rest_client_class.return_value = mock_rest_instance

        klines_data = [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        # 第一次返回数据，第二次返回空列表表示没有更多数据
        mock_rest_instance.fetch_ohlcv.side_effect = [klines_data, []]

        with patch('time.sleep'):  # 跳过sleep
            result = self.market_data_fetcher.get_historical_klines("BTC-USDT", "5m", 100)

        assert result == klines_data
        assert mock_rest_instance.fetch_ohlcv.call_count >= 1

    @patch('src.data_manager.core.market_data_fetcher.RESTClient')
    def test_get_historical_klines_batch(self, mock_rest_client_class):
        """测试获取历史K线数据 - 分批获取"""
        mock_rest_instance = Mock()
        mock_rest_client_class.return_value = mock_rest_instance

        # 模拟分批返回
        batch1 = [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        batch2 = [[1609459260000, 50050, 50150, 49950, 50100, 150]]
        mock_rest_instance.fetch_ohlcv.side_effect = [batch1, batch2, []]  # 第三次返回空表示结束

        result = self.market_data_fetcher.get_historical_klines("BTC-USDT", "5m", 150)

        assert len(result) == 2
        assert result[0] == batch1[0]
        assert result[1] == batch2[0]

    @patch('src.data_manager.clients.rest_client.RESTClient')
    def test_get_multi_timeframe_data_success(self, mock_rest_client_class):
        """测试获取多时间框架数据成功"""
        mock_rest_instance = Mock()
        mock_rest_client_class.return_value = mock_rest_instance

        klines_data = [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        mock_rest_instance.fetch_ohlcv.return_value = klines_data

        with patch.object(self.market_data_fetcher, 'get_historical_klines', return_value=klines_data):
            result = self.market_data_fetcher.get_multi_timeframe_data("BTC-USDT", ["5m", "15m"])

        assert "5m" in result
        assert "15m" in result
        assert result["5m"] == klines_data
        assert result["15m"] == klines_data

    def test_timeframe_to_minutes(self):
        """测试时间框架转换为分钟"""
        assert self.market_data_fetcher._timeframe_to_minutes("1m") == 1
        assert self.market_data_fetcher._timeframe_to_minutes("5m") == 5
        assert self.market_data_fetcher._timeframe_to_minutes("1h") == 60
        assert self.market_data_fetcher._timeframe_to_minutes("1d") == 1440
        assert self.market_data_fetcher._timeframe_to_minutes("unknown") == 5  # 默认值

    def test_adjust_limit_by_timeframe(self):
        """测试根据时间框架调整数据量限制"""
        # 短时间框架
        limit = self.market_data_fetcher._adjust_limit_by_timeframe(500, "5m")
        assert limit == 500

        # 中时间框架
        limit = self.market_data_fetcher._adjust_limit_by_timeframe(500, "1h")
        assert limit == 250

        # 长时间框架
        limit = self.market_data_fetcher._adjust_limit_by_timeframe(500, "4h")
        assert limit == 125

        # 超长时间框架
        limit = self.market_data_fetcher._adjust_limit_by_timeframe(500, "1d")
        assert limit == 62  # 500 // 8

    def test_deduplicate_klines(self):
        """测试去除重复K线数据"""
        klines = [
            [1609459200000, 50000, 50100, 49900, 50050, 100],
            [1609459260000, 50050, 50150, 49950, 50100, 150],
            [1609459200000, 50000, 50100, 49900, 50050, 100],  # 重复
            [1609459320000, 50100, 50200, 50000, 50150, 200]
        ]

        result = self.market_data_fetcher._deduplicate_klines(klines)

        assert len(result) == 3
        assert result[0][0] == 1609459200000
        assert result[1][0] == 1609459260000
        assert result[2][0] == 1609459320000

    def test_deduplicate_klines_empty(self):
        """测试去除重复K线数据 - 空数据"""
        result = self.market_data_fetcher._deduplicate_klines([])

        assert result == []

    @patch('numpy.array')
    @patch('numpy.diff')
    @patch('numpy.argsort')
    def test_smart_sampling_success(self, mock_argsort, mock_diff, mock_array):
        """测试智能采样成功"""
        # 模拟numpy操作
        mock_array.side_effect = lambda x: x
        mock_diff.return_value = [100, 200, 150]  # 价格变化
        mock_argsort.return_value = [1, 0, 2]  # 变化最大的索引

        klines = [
            [1609459200000, 50000, 50100, 49900, 50050, 100],
            [1609459260000, 50050, 50150, 49950, 50100, 150],
            [1609459320000, 50100, 50200, 50000, 50150, 200],
            [1609459380000, 50150, 50250, 50050, 50200, 250]
        ]

        result = self.market_data_fetcher._smart_sampling(klines, 3)

        assert len(result) == 3

    def test_smart_sampling_fallback(self):
        """测试智能采样回退到简单采样"""
        klines = [
            [1609459200000, 50000, 50100, 49900, 50050, 100],
            [1609459260000, 50050, 50150, 49950, 50100, 150],
            [1609459320000, 50100, 50200, 50000, 50150, 200],
            [1609459380000, 50150, 50250, 50050, 50200, 250]
        ]

        # 模拟numpy导入失败
        with patch.dict('sys.modules', {'numpy': None}):
            result = self.market_data_fetcher._smart_sampling(klines, 2)

        assert len(result) == 2


class TestMarketDataFetcherIntegration:
    """MarketDataFetcher 集成测试"""

    def setup_method(self):
        """测试前设置"""
        self.mock_rest_client = Mock(spec=RESTClient)
        self.market_data_fetcher = MarketDataFetcher(self.mock_rest_client)

    @patch('src.data_manager.core.market_data_fetcher.RESTClient')
    def test_complete_market_data_workflow(self, mock_rest_client_class):
        """测试完整市场数据工作流"""
        mock_rest_instance = Mock()
        mock_rest_client_class.return_value = mock_rest_instance

        # 模拟完整的市场数据
        market_info = {
            "symbol": "BTC-USDT",
            "ticker": {"last": 50000, "volume": 1000},
            "orderbook": {"bids": [[49900, 1]], "asks": [[50100, 1]]},
            "recent_trades": [{"price": 50000, "size": 0.1, "side": "buy"}],
            "ohlcv": {
                "5m": [[1609459200000, 50000, 50100, 49900, 50050, 100]],
                "15m": [[1609459200000, 50000, 50100, 49900, 50050, 100]]
            },
            "timestamp": int(time.time() * 1000)
        }
        mock_rest_instance.get_market_info.return_value = market_info

        with patch('src.data_manager.core.market_data_fetcher.TechnicalIndicators') as mock_ti:
            mock_ti.calculate_all_indicators.return_value = {"rsi": 70}
            mock_ti.analyze_volume_profile.return_value = {"buy_ratio": 0.6}

            result = self.market_data_fetcher.get_comprehensive_market_data("BTC-USDT")

        assert result is not None
        assert result["symbol"] == "BTC-USDT"
        assert result["current_price"] == 50000
        assert "technical_analysis" in result
        assert "volume_profile" in result

    def test_error_recovery_workflow(self):
        """测试错误恢复工作流"""
        # 模拟各种失败情况
        self.mock_rest_client.get_market_info.side_effect = Exception("API error")
        self.mock_rest_client.fetch_ticker.side_effect = Exception("Ticker error")
        self.mock_rest_client.fetch_orderbook.side_effect = Exception("Orderbook error")
        self.mock_rest_client.fetch_ohlcv.side_effect = Exception("OHLCV error")
        self.mock_rest_client.fetch_recent_trades.side_effect = Exception("Trades error")

        result = self.market_data_fetcher._get_degraded_market_data(
            self.mock_rest_client, "BTC-USDT"
        )

        # 应该返回None，因为所有数据源都失败
        assert result is None

    @patch('src.data_manager.core.market_data_fetcher.RESTClient')
    def test_historical_data_batch_workflow(self, mock_rest_client_class):
        """测试历史数据分批获取工作流"""
        mock_rest_instance = Mock()
        mock_rest_client_class.return_value = mock_rest_instance

        # 模拟多批数据
        batch1 = [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        batch2 = [[1609459260000, 50050, 50150, 49950, 50100, 150]]
        batch3 = []  # 空批次表示结束

        mock_rest_instance.fetch_ohlcv.side_effect = [batch1, batch2, batch3]

        with patch('time.sleep'):  # 跳过sleep
            result = self.market_data_fetcher.get_historical_klines("BTC-USDT", "5m", 100)

        assert len(result) == 2
        assert mock_rest_instance.fetch_ohlcv.call_count == 3
