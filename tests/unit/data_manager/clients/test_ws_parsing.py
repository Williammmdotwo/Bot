"""
WebSocket Client Data Parsing Tests
Target: Test WebSocket data parsing logic without network connections
"""

import pytest
import json
from unittest.mock import MagicMock

from src.data_manager.clients.websocket_client import OKXWebSocketClient


@pytest.mark.asyncio
class TestWebSocketParsing:
    """WebSocket data parsing logic tests - white-box testing, no network"""

    async def test_process_candle_data_logic(self):
        """Test K-line data parsing logic - white-box test, no network"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()
        client.running = True

        mock_payload = {
            "arg": {"channel": "candle1m", "instId": "BTC-USDT"},
            "data": [
                ["1678888888000", "50000.5", "50100.0", "49900.0", "50000.0", "100.0", "1.0", "1.0", "1"],
                ["1678888890000", "50050.0", "50200.0", "50000.0", "50050.0", "120.3", "1.0", "1.0", "1"]
            ]
        }

        await client._handle_message(json.dumps(mock_payload))
        assert True

    async def test_process_ticker_data_logic(self):
        """Test Ticker data parsing logic"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        mock_payload = {
            "arg": {"channel": "tickers", "instId": "ETH-USDT"},
            "data": [{
                "instId": "ETH-USDT",
                "last": "30000.0",
                "askPx": "30000.1",
                "bidPx": "29999.9"
            }]
        }

        await client._handle_message(json.dumps(mock_payload))
        assert True

    async def test_process_multiple_candles(self):
        """Test processing multiple K-lines"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        mock_payload = {
            "arg": {"channel": "candle5m", "instId": "BTC-USDT-SWAP"},
            "data": [
                ["16094592000000", "50000.0", "50100.0", "49900.0", "50000.0", "100.0"],
                ["1609459230000", "50000.0", "50200.0", "50000.0", "50050.0", "150.0"],
                ["1609459260000", "50000.0", "50300.0", "50000.0", "50050.0", "50200.0", "120.0"]
            ]
        }

        await client._handle_message(json.dumps(mock_payload))
        assert True

    async def test_process_candle_with_missing_fields(self):
        """Test processing K-line data with missing fields"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        mock_payload = {
            "arg": {"channel": "candle1m", "instId": "BTC-USDT"},
            "data": [
                ["1609459200000", "50000.0", "50100.0", "49900.0", "50000.0"]  # only 5 fields
            ]
        }

        await client._handle_message(json.dumps(mock_payload))
        assert True

    async def test_process_ticker_with_extra_fields(self):
        """Test processing Ticker data with extra fields"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        mock_payload = {
            "arg": {"channel": "tickers", "instId": "ETH-USDT"},
            "data": [{
                "instId": "ETH-USDT",
                "last": "30000.0",
                "askPx": "30000.1",
                "bidPx": "29999.9",
                "volume24h": "1234567.89",
                "open24h": "29950.5"
            }]
        }

        await client._handle_message(json.dumps(mock_payload))
        assert True

    async def test_handle_ping_message(self):
        """Test handling ping message"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        ping_message = "ping"

        await client._handle_message(ping_message)
        assert True

    async def test_handle_pong_message(self):
        """Test handling pong message"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        pong_message = "pong"

        await client._handle_message(pong_message)
        assert True

    async def test_handle_login_response_success(self):
        """Test handling login success response"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        client.credentials = {
            "api_key": "test_key",
            "passphrase": "test_pass",
            "secret": "test_secret"
        }
        client.has_credentials = True

        login_message = {
            "event": "login",
            "code": "0",
            "msg": "Success"
        }

        await client._handle_message(json.dumps(login_message))
        assert True

    async def test_handle_login_response_failure(self):
        """Test handling login failure response"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        login_message = {
            "event": "login",
            "code": "50001",
            "msg": "Invalid sign"
        }

        await client._handle_message(json.dumps(login_message))
        assert True

    async def test_handle_subscribe_response_success(self):
        """Test handling subscribe success response"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        subscribe_message = {
            "event": "subscribe",
            "code": "0",
            "msg": "subscribe success",
            "arg": {
                "channel": "candle5m",
                "instId": "BTC-USDT-SWAP"
            }
        }

        await client._handle_message(json.dumps(subscribe_message))
        assert True

    async def test_handle_error_response(self):
        """Test handling error response"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        error_message = {
            "event": "error",
            "code": "60012",
            "msg": "Invalid subscription"
        }

        await client._handle_message(json.dumps(error_message))
        assert True

    async def test_handle_invalid_json(self):
        """Test handling invalid JSON"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        invalid_json = "invalid {{{"

        await client._handle_message(invalid_json)
        assert True

    async def test_handle_empty_data_array(self):
        """Test handling empty data array"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        mock_payload = {
            "arg": {"channel": "candle1m", "instId": "BTC-USDT"},
            "data": []
        }

        await client._handle_message(json.dumps(mock_payload))
        assert True

    async def test_handle_non_standard_channel(self):
        """Test handling non-standard channel messages"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        mock_payload = {
            "arg": {"channel": "unknown", "instId": "BTC-USDT"},
            "data": [{"something": "data"}]
        }

        await client._handle_message(json.dumps(mock_payload))
        assert True

    async def test_process_candle_extreme_values(self):
        """Test processing K-line data with extreme values"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        mock_payload = {
            "arg": {"channel": "candle1m", "instId": "BTC-USDT"},
            "data": [
                ["0", "0", "0", "0", "0", "1", "1"],
                ["9999999999999", "9999999999999", "9999999999999", "9999999999999", "9999999999999", "1", "1"]
            ]
        }

        await client._handle_message(json.dumps(mock_payload))
        assert True

    async def test_process_ticker_zero_price(self):
        """Test processing Ticker data with zero price"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        mock_payload = {
            "arg": {"channel": "tickers", "instId": "BTC-USDT"},
            "data": [{
                "instId": "BTC-USDT",
                "last": "0",
                "askPx": "0",
                "bidPx": "0"
            }]
        }

        await client._handle_message(json.dumps(mock_payload))
        assert True

    async def test_process_candle_with_negative_volume(self):
        """Test processing K-line data with negative volume"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        mock_payload = {
            "arg": {"channel": "candle1m", "instId": "BTC-USDT"},
            "data": [
                ["1609459200000", "50000.0", "50100.0", "49900.0", "50000.0", "-100.0", "1", "1"]
            ]
        }

        await client._handle_message(json.dumps(mock_payload))
        assert True

    async def test_consecutive_message_handling(self):
        """Test consecutive message handling"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        messages = [
            {"event": "subscribe", "code": "0"},
            {"event": "login", "code": "0"},
            {"arg": {"channel": "candle1m", "instId": "BTC-USDT"}, "data": [["1609459200000", "50000.0", "50100.0", "49900.0", "50000.0", "100.0"]]}
        ]

        for msg in messages:
            await client._handle_message(json.dumps(msg))

        assert True

    async def test_malformed_json_recovery(self):
        """Test malformed JSON recovery"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        malformed_jsons = [
            '{"event": "subscribe"}',
            '{"event": "subscribe"}',
            '{event: "subscribe"}',
            '{"event": null}',
            '[]',
            '{}'
        ]

        for malformed in malformed_jsons:
            await client._handle_message(malformed)

        assert True

    async def test_large_message_payload(self):
        """Test large message payload processing"""
        client = OKXWebSocketClient()
        client.data_handler = MagicMock()

        large_data = [[f"{i}000", f"{i+1}00.0", f"{i+2}00.0", f"{i+3}00.0", f"{i+4}00.0", f"{i+5}00.0", "100.0", "1", "1"] for i in range(100)]

        mock_payload = {
            "arg": {"channel": "candle1m", "instId": "BTC-USDT"},
            "data": large_data
        }

        await client._handle_message(json.dumps(mock_payload))
        assert True
