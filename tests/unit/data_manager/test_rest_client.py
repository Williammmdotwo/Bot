"""
RESTClient 单元测试
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
import ccxt

from src.data_manager.rest_client import RESTClient


class TestRESTClient:
    """RESTClient 测试类"""
    
    @patch('src.data_manager.rest_client.get_environment_config')
    @patch('src.data_manager.rest_client.get_api_credentials')
    @patch('src.data_manager.rest_client.get_ccxt_config')
    @patch('src.data_manager.rest_client.ccxt.okx')
    def test_init_with_credentials(self, mock_okx, mock_ccxt_config, mock_api_creds, mock_env_config):
        """测试初始化 - 有凭据"""
        mock_env_config.return_value = {"is_demo": False}
        mock_api_creds.return_value = ({"apiKey": "test"}, True)
        mock_ccxt_config.return_value = {"sandbox": False, "apiKey": "test"}
        mock_exchange = Mock()
        mock_okx.return_value = mock_exchange
        
        client = RESTClient()
        
        assert client.use_demo is False
        assert client.has_credentials is True
        mock_okx.assert_called_once_with({"sandbox": False, "apiKey": "test"})
    
    @patch('src.data_manager.rest_client.get_environment_config')
    @patch('src.data_manager.rest_client.get_api_credentials')
    @patch('src.data_manager.rest_client.get_ccxt_config')
    @patch('src.data_manager.rest_client.ccxt.okx')
    def test_init_without_credentials(self, mock_okx, mock_ccxt_config, mock_api_creds, mock_env_config):
        """测试初始化 - 无凭据"""
        mock_env_config.return_value = {"is_demo": True}
        mock_api_creds.return_value = ({}, False)
        mock_ccxt_config.return_value = {"sandbox": True}
        mock_exchange = Mock()
        mock_okx.return_value = mock_exchange
        
        client = RESTClient()
        
        assert client.use_demo is True
        assert client.has_credentials is False
        mock_okx.assert_called_once_with({"sandbox": True})
    
    @patch('src.data_manager.rest_client.get_environment_config')
    @patch('src.data_manager.rest_client.get_api_credentials')
    @patch('src.data_manager.rest_client.get_ccxt_config')
    @patch('src.data_manager.rest_client.ccxt.okx')
    def test_init_with_use_demo_param(self, mock_okx, mock_ccxt_config, mock_api_creds, mock_env_config):
        """测试初始化 - 指定use_demo参数"""
        mock_api_creds.return_value = ({"apiKey": "test"}, True)
        mock_ccxt_config.return_value = {"sandbox": True, "apiKey": "test"}
        mock_exchange = Mock()
        mock_okx.return_value = mock_exchange
        
        client = RESTClient(use_demo=True)
        
        assert client.use_demo is True
        assert client.has_credentials is True
        mock_okx.assert_called_once_with({"sandbox": True, "apiKey": "test"})
    
    def test_fetch_balance_with_credentials(self):
        """测试获取余额 - 有凭据"""
        mock_exchange = Mock()
        mock_exchange.fetch_balance.return_value = {"free": {"USDT": 1000}}
        
        client = RESTClient()
        client.exchange = mock_exchange
        client.has_credentials = True
        
        result = client.fetch_balance()
        
        assert result == {"free": {"USDT": 1000}}
        mock_exchange.fetch_balance.assert_called_once()
    
    def test_fetch_balance_without_credentials(self):
        """测试获取余额 - 无凭据"""
        mock_exchange = Mock()
        
        client = RESTClient()
        client.exchange = mock_exchange
        client.has_credentials = False
        
        result = client.fetch_balance()
        
        assert "info" in result
        assert result["free"] == {}
        assert result["used"] == {}
        assert result["total"] == {}
        mock_exchange.fetch_balance.assert_not_called()
    
    def test_fetch_balance_exception(self):
        """测试获取余额异常"""
        mock_exchange = Mock()
        mock_exchange.fetch_balance.side_effect = Exception("API error")
        
        client = RESTClient()
        client.exchange = mock_exchange
        client.has_credentials = True
        
        with pytest.raises(Exception):
            client.fetch_balance()
    
    def test_fetch_positions_with_credentials(self):
        """测试获取持仓 - 有凭据"""
        mock_exchange = Mock()
        mock_exchange.fetch_positions.return_value = [{"symbol": "BTC-USDT", "size": 0.1}]
        
        client = RESTClient()
        client.exchange = mock_exchange
        client.has_credentials = True
        
        result = client.fetch_positions()
        
        assert result == [{"symbol": "BTC-USDT", "size": 0.1}]
        mock_exchange.fetch_positions.assert_called_once()
    
    def test_fetch_positions_without_credentials(self):
        """测试获取持仓 - 无凭据"""
        mock_exchange = Mock()
        
        client = RESTClient()
        client.exchange = mock_exchange
        client.has_credentials = False
        
        result = client.fetch_positions()
        
        assert result == []
        mock_exchange.fetch_positions.assert_not_called()
    
    def test_fetch_ohlcv_success(self):
        """测试获取OHLCV数据成功"""
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        mock_exchange.parse_timeframe.return_value = 300000  # 5分钟
        mock_exchange.fetch_ohlcv.return_value = [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        result = client.fetch_ohlcv("BTC-USDT", 1609459200000, 100, "5m")
        
        assert result == [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        mock_exchange.fetch_ohlcv.assert_called_once()
    
    def test_fetch_ohlcv_invalid_symbol(self):
        """测试获取OHLCV数据 - 无效交易对"""
        mock_exchange = Mock()
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        with pytest.raises(ValueError):
            client.fetch_ohlcv("", 1609459200000, 100, "5m")
        
        with pytest.raises(ValueError):
            client.fetch_ohlcv(None, 1609459200000, 100, "5m")
    
    def test_fetch_ohlcv_invalid_timeframe(self):
        """测试获取OHLCV数据 - 无效时间框架"""
        mock_exchange = Mock()
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        with pytest.raises(ValueError):
            client.fetch_ohlcv("BTC-USDT", 1609459200000, 100, "invalid")
    
    def test_fetch_ohlcv_invalid_since(self):
        """测试获取OHLCV数据 - 无效since参数"""
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        mock_exchange.parse_timeframe.return_value = 300000
        mock_exchange.fetch_ohlcv.return_value = []
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        # 应该自动计算新的since值
        result = client.fetch_ohlcv("BTC-USDT", 0, 100, "5m")
        
        assert isinstance(result, list)
    
    def test_fetch_ohlcv_network_error_retry(self):
        """测试获取OHLCV数据 - 网络错误重试"""
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        mock_exchange.parse_timeframe.return_value = 300000
        
        # 第一次网络错误，第二次成功
        mock_exchange.fetch_ohlcv.side_effect = [
            ccxt.NetworkError("Network error"),
            [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        ]
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        with patch('time.sleep'):  # 跳过sleep
            result = client.fetch_ohlcv("BTC-USDT", 1609459200000, 100, "5m", max_retries=2)
        
        assert result == [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        assert mock_exchange.fetch_ohlcv.call_count == 2
    
    def test_fetch_ohlcv_exchange_error_retry(self):
        """测试获取OHLCV数据 - 交易所错误重试"""
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        mock_exchange.parse_timeframe.return_value = 300000
        
        # 第一次交易所错误，第二次成功
        mock_exchange.fetch_ohlcv.side_effect = [
            ccxt.ExchangeError("Exchange error"),
            [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        ]
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        with patch('time.sleep'):  # 跳过sleep
            result = client.fetch_ohlcv("BTC-USDT", 1609459200000, 100, "5m", max_retries=2)
        
        assert result == [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        assert mock_exchange.fetch_ohlcv.call_count == 2
    
    def test_fetch_ohlcv_all_retries_failed(self):
        """测试获取OHLCV数据 - 所有重试失败"""
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        mock_exchange.parse_timeframe.return_value = 300000
        mock_exchange.fetch_ohlcv.side_effect = ccxt.NetworkError("Persistent network error")
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        with patch('time.sleep'):  # 跳过sleep
            with pytest.raises(ccxt.NetworkError):
                client.fetch_ohlcv("BTC-USDT", 1609459200000, 100, "5m", max_retries=2)
        
        assert mock_exchange.fetch_ohlcv.call_count == 2
    
    def test_validate_ohlcv_data_success(self):
        """测试验证OHLCV数据成功"""
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        ohlcv_data = [
            [1609459200000, 50000, 50100, 49900, 50050, 100],
            [1609459260000, 50050, 50150, 49950, 50100, 150]
        ]
        
        result = client._validate_ohlcv_data(ohlcv_data, "BTC-USDT", "5m")
        
        assert len(result) == 2
        assert result[0][0] == 1609459200000
        assert result[1][0] == 1609459260000
    
    def test_validate_ohlcv_data_empty(self):
        """测试验证OHLCV数据 - 空数据"""
        mock_exchange = Mock()
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        result = client._validate_ohlcv_data([], "BTC-USDT", "5m")
        
        assert result == []
    
    def test_validate_ohlcv_data_invalid_structure(self):
        """测试验证OHLCV数据 - 无效结构"""
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        # 无效的数据结构
        invalid_data = [
            "invalid_candle",
            [1609459200000, 50000, 50100],  # 缺少字段
            [1609459260000, 50050, 50150, 49950, 50100, 150]  # 有效的
        ]
        
        result = client._validate_ohlcv_data(invalid_data, "BTC-USDT", "5m")
        
        # 应该只返回有效的K线
        assert len(result) == 1
        assert result[0][0] == 1609459260000
    
    def test_validate_ohlcv_data_invalid_prices(self):
        """测试验证OHLCV数据 - 无效价格"""
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        # 价格逻辑错误的K线
        invalid_price_data = [
            [1609459200000, 50000, 49900, 50100, 50050, 100],  # high < low
            [1609459260000, 50050, 50150, 49950, 50100, 150]   # 有效的
        ]
        
        result = client._validate_ohlcv_data(invalid_price_data, "BTC-USDT", "5m")
        
        # 应该只返回有效的K线
        assert len(result) == 1
        assert result[0][0] == 1609459260000
    
    def test_validate_ohlcv_data_invalid_timestamps(self):
        """测试验证OHLCV数据 - 无效时间戳"""
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        # 时间戳无效的K线
        invalid_timestamp_data = [
            [1609459200000 - 365*24*60*60*1000 - 1, 50000, 50100, 49900, 50050, 100],  # 太旧
            [1609459200000, 50050, 50150, 49950, 50100, 150]  # 有效的
        ]
        
        result = client._validate_ohlcv_data(invalid_timestamp_data, "BTC-USDT", "5m")
        
        # 应该只返回有效的K线
        assert len(result) == 1
        assert result[0][0] == 1609459200000
    
    def test_validate_ohlcv_data_duplicates(self):
        """测试验证OHLCV数据 - 重复时间戳"""
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        # 重复时间戳的K线
        duplicate_data = [
            [1609459200000, 50000, 50100, 49900, 50050, 100],
            [1609459260000, 50050, 50150, 49950, 50100, 150],
            [1609459200000, 50010, 50110, 49910, 50060, 110]  # 重复时间戳
        ]
        
        result = client._validate_ohlcv_data(duplicate_data, "BTC-USDT", "5m")
        
        # 应该去重，保留最新的
        assert len(result) == 2
        timestamps = [candle[0] for candle in result]
        assert len(set(timestamps)) == 2  # 无重复
    
    def test_fetch_multiple_timeframes_success(self):
        """测试获取多时间框架数据成功"""
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        mock_exchange.parse_timeframe.return_value = 300000  # 5分钟
        mock_exchange.fetch_ohlcv.return_value = [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        with patch.object(client, 'fetch_ohlcv', return_value=[[1609459200000, 50000, 50100, 49900, 50050, 100]]):
            result = client.fetch_multiple_timeframes("BTC-USDT", 50)
        
        assert "1m" in result
        assert "5m" in result
        assert "15m" in result
        assert "1h" in result
        assert "4h" in result
        assert "1d" in result
    
    def test_fetch_multiple_timeframes_partial_failure(self):
        """测试获取多时间框架数据 - 部分失败"""
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        mock_exchange.parse_timeframe.return_value = 300000
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        # 模拟部分时间框架失败
        def mock_fetch_ohlcv(symbol, since, limit, timeframe):
            if timeframe in ["5m", "15m"]:
                return [[1609459200000, 50000, 50100, 49900, 50050, 100]]
            else:
                raise Exception("API error")
        
        with patch.object(client, 'fetch_ohlcv', side_effect=mock_fetch_ohlcv):
            result = client.fetch_multiple_timeframes("BTC-USDT", 50)
        
        assert "5m" in result
        assert "15m" in result
        assert result["1m"] == []  # 失败的时间框架返回空列表
    
    def test_fetch_orderbook_success(self):
        """测试获取订单簿成功"""
        mock_exchange = Mock()
        mock_exchange.fetch_order_book.return_value = {
            "bids": [[49900, 1], [49800, 2]],
            "asks": [[50100, 1], [50200, 2]]
        }
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        result = client.fetch_orderbook("BTC-USDT", 100)
        
        assert "bids" in result
        assert "asks" in result
        assert len(result["bids"]) == 2
        assert len(result["asks"]) == 2
        mock_exchange.fetch_order_book.assert_called_once_with("BTC-USDT", 100)
    
    def test_fetch_orderbook_exception(self):
        """测试获取订单簿异常"""
        mock_exchange = Mock()
        mock_exchange.fetch_order_book.side_effect = Exception("API error")
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        with pytest.raises(Exception):
            client.fetch_orderbook("BTC-USDT", 100)
    
    def test_fetch_ticker_success(self):
        """测试获取ticker成功"""
        mock_exchange = Mock()
        mock_exchange.fetch_ticker.return_value = {
            "symbol": "BTC-USDT",
            "last": 50000,
            "volume": 1000
        }
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        result = client.fetch_ticker("BTC-USDT")
        
        assert result["symbol"] == "BTC-USDT"
        assert result["last"] == 50000
        assert result["volume"] == 1000
        mock_exchange.fetch_ticker.assert_called_once_with("BTC-USDT")
    
    def test_fetch_ticker_exception(self):
        """测试获取ticker异常"""
        mock_exchange = Mock()
        mock_exchange.fetch_ticker.side_effect = Exception("API error")
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        with pytest.raises(Exception):
            client.fetch_ticker("BTC-USDT")
    
    def test_fetch_recent_trades_success(self):
        """测试获取最近交易成功"""
        mock_exchange = Mock()
        mock_exchange.fetch_trades.return_value = [
            {"price": 50000, "size": 0.1, "side": "buy"},
            {"price": 50100, "size": 0.2, "side": "sell"}
        ]
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        result = client.fetch_recent_trades("BTC-USDT", 100)
        
        assert len(result) == 2
        assert result[0]["price"] == 50000
        assert result[1]["price"] == 50100
        mock_exchange.fetch_trades.assert_called_once_with("BTC-USDT", limit=100)
    
    def test_fetch_recent_trades_exception(self):
        """测试获取最近交易异常"""
        mock_exchange = Mock()
        mock_exchange.fetch_trades.side_effect = Exception("API error")
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        with pytest.raises(Exception):
            client.fetch_recent_trades("BTC-USDT", 100)
    
    def test_fetch_funding_rate_success(self):
        """测试获取资金费率成功"""
        mock_exchange = Mock()
        mock_exchange.fetch_funding_rate.return_value = {
            "symbol": "BTC-USDT-SWAP",
            "fundingRate": 0.0001,
            "timestamp": 1609459200000
        }
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        result = client.fetch_funding_rate("BTC-USDT-SWAP")
        
        assert result["symbol"] == "BTC-USDT-SWAP"
        assert result["fundingRate"] == 0.0001
        mock_exchange.fetch_funding_rate.assert_called_once_with("BTC-USDT-SWAP")
    
    def test_fetch_funding_rate_exception(self):
        """测试获取资金费率异常"""
        mock_exchange = Mock()
        mock_exchange.fetch_funding_rate.side_effect = Exception("API error")
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        with pytest.raises(Exception):
            client.fetch_funding_rate("BTC-USDT-SWAP")
    
    def test_get_market_info_success(self):
        """测试获取市场信息成功"""
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        mock_exchange.fetch_ticker.return_value = {"symbol": "BTC-USDT", "last": 50000}
        mock_exchange.fetch_order_book.return_value = {"bids": [[49900, 1]], "asks": [[50100, 1]]}
        mock_exchange.fetch_trades.return_value = [{"price": 50000, "size": 0.1}]
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        with patch.object(client, 'fetch_multiple_timeframes', return_value={"5m": []}):
            result = client.get_market_info("BTC-USDT")
        
        assert result["symbol"] == "BTC-USDT"
        assert "ticker" in result
        assert "orderbook" in result
        assert "recent_trades" in result
        assert "ohlcv" in result
        assert "timestamp" in result
        assert "use_demo" in result
    
    def test_get_market_info_exception(self):
        """测试获取市场信息异常"""
        mock_exchange = Mock()
        mock_exchange.fetch_ticker.side_effect = Exception("API error")
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        with pytest.raises(Exception):
            client.get_market_info("BTC-USDT")
    
    def test_deduplicate_ohlcv_data_success(self):
        """测试去重OHLCV数据成功"""
        client = RESTClient()
        
        ohlcv_data = [
            [1609459200000, 50000, 50100, 49900, 50050, 100],
            [1609459260000, 50050, 50150, 49950, 50100, 150],
            [1609459200000, 50010, 50110, 49910, 50060, 110],  # 重复时间戳
            [1609459320000, 50100, 50200, 50000, 50150, 200]
        ]
        
        result = client._deduplicate_ohlcv_data(ohlcv_data)
        
        # 应该去重，保留最新的
        assert len(result) == 3
        timestamps = [candle[0] for candle in result]
        assert len(set(timestamps)) == 3  # 无重复
        # 检查时间戳顺序
        assert result[0][0] < result[1][0] < result[2][0]
    
    def test_deduplicate_ohlcv_data_empty(self):
        """测试去重OHLCV数据 - 空数据"""
        client = RESTClient()
        
        result = client._deduplicate_ohlcv_data([])
        
        assert result == []


class TestRESTClientIntegration:
    """RESTClient 集成测试"""
    
    @patch('src.data_manager.rest_client.get_environment_config')
    @patch('src.data_manager.rest_client.get_api_credentials')
    @patch('src.data_manager.rest_client.get_ccxt_config')
    @patch('src.data_manager.rest_client.ccxt.okx')
    def test_complete_workflow(self, mock_okx, mock_ccxt_config, mock_api_creds, mock_env_config):
        """测试完整工作流"""
        mock_env_config.return_value = {"is_demo": False}
        mock_api_creds.return_value = ({"apiKey": "test"}, True)
        mock_ccxt_config.return_value = {"sandbox": False, "apiKey": "test"}
        
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        mock_exchange.parse_timeframe.return_value = 300000
        mock_exchange.fetch_balance.return_value = {"free": {"USDT": 1000}}
        mock_exchange.fetch_positions.return_value = []
        mock_exchange.fetch_ticker.return_value = {"symbol": "BTC-USDT", "last": 50000}
        mock_exchange.fetch_order_book.return_value = {"bids": [[49900, 1]], "asks": [[50100, 1]]}
        mock_exchange.fetch_trades.return_value = [{"price": 50000, "size": 0.1}]
        mock_exchange.fetch_ohlcv.return_value = [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        
        mock_okx.return_value = mock_exchange
        
        client = RESTClient()
        
        # 测试各种操作
        balance = client.fetch_balance()
        positions = client.fetch_positions()
        ticker = client.fetch_ticker("BTC-USDT")
        orderbook = client.fetch_orderbook("BTC-USDT")
        trades = client.fetch_recent_trades("BTC-USDT")
        ohlcv = client.fetch_ohlcv("BTC-USDT", 1609459200000, 100, "5m")
        market_info = client.get_market_info("BTC-USDT")
        
        assert balance["free"]["USDT"] == 1000
        assert positions == []
        assert ticker["last"] == 50000
        assert "bids" in orderbook
        assert len(trades) == 1
        assert len(ohlcv) == 1
        assert market_info["symbol"] == "BTC-USDT"
    
    def test_error_recovery_workflow(self):
        """测试错误恢复工作流"""
        mock_exchange = Mock()
        mock_exchange.milliseconds.return_value = 1609459200000
        mock_exchange.parse_timeframe.return_value = 300000
        
        # 模拟网络错误然后恢复
        mock_exchange.fetch_ohlcv.side_effect = [
            ccxt.NetworkError("Network error"),
            [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        ]
        
        client = RESTClient()
        client.exchange = mock_exchange
        
        with patch('time.sleep'):  # 跳过sleep
            result = client.fetch_ohlcv("BTC-USDT", 1609459200000, 100, "5m", max_retries=2)
        
        assert result == [[1609459200000, 50000, 50100, 49900, 50050, 100]]
        assert mock_exchange.fetch_ohlcv.call_count == 2
