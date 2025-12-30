"""
OKX REST API 客户端

提供与 OKX 交易所 REST API 的交互功能
支持模拟盘和实盘模式
"""

import ccxt
import logging
import os
import json
from typing import Optional, List, Dict, Any

from src.utils.environment_utils import get_api_credentials, get_ccxt_config, get_data_source_config

logger = logging.getLogger(__name__)


class RESTClient:
    """OKX REST API 客户端"""

    def __init__(self, use_demo: Optional[bool] = None):
        """
        初始化 REST 客户端

        Args:
            use_demo: 是否强制使用模拟盘模式（覆盖配置）
        """
        # 获取配置
        self.data_source_config = get_data_source_config()

        # 获取 API 凭据
        credentials, has_creds = get_api_credentials()
        self.has_credentials = has_creds
        self.api_credentials = credentials

        # 获取 CCXT 配置
        ccxt_config = get_ccxt_config()

        # 确定是否使用模拟盘
        if use_demo is not None:
            self.use_demo = use_demo
        else:
            self.use_demo = self.data_source_config.get('use_demo', False)

        self.is_demo = self.use_demo  # 别名，便于使用

        # 初始化 CCXT exchange
        try:
            self.exchange = ccxt.okx({
                'apiKey': credentials.get('api_key') if has_creds else None,
                'secret': credentials.get('secret') if has_creds else None,
                'password': credentials.get('passphrase') if has_creds else None,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                }
            })

            # 配置 Sandbox 模式
            sandbox_mode = ccxt_config.get('sandbox', True)
            if sandbox_mode:
                self.exchange.set_sandbox_mode(True)
                logger.info("OKX Exchange initialized in Sandbox mode")
            else:
                logger.info("OKX Exchange initialized in Production mode")

        except Exception as e:
            logger.error(f"Failed to initialize OKX exchange: {e}")
            raise

        # 设置日志记录器
        self.logger = logger

    def fetch_balance(self) -> Dict[str, Any]:
        """
        获取账户余额

        Returns:
            dict: 余额信息
        """
        if not self.has_credentials:
            self.logger.warning("Cannot fetch balance: no API credentials available")
            return {
                "info": "No credentials available",
                "free": {},
                "used": {},
                "total": {}
            }

        try:
            self.logger.info("Fetching account balance...")
            balance = self.exchange.fetch_balance()
            self.logger.info(f"Successfully fetched balance: {balance}")
            return balance
        except Exception as e:
            self.logger.error(f"Failed to fetch balance: {e}")
            raise

    def fetch_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取持仓

        注意：OKX 模拟盘 (Demo) 必须指定 symbol，否则会报 50038 错误。

        Args:
            symbol: 交易对符号（可选）。模拟盘必须提供。

        Returns:
            list: 持仓列表
        """
        if not self.has_credentials:
            self.logger.warning("Cannot fetch positions: no API credentials available")
            return []

        try:
            self.logger.info(f"Fetching positions for symbol: {symbol}")

            # 如果是模拟盘且没有 symbol，记录警告并返回空列表
            if self.is_demo and symbol is None:
                self.logger.warning("OKX Demo mode requires a symbol to fetch positions. Returning empty list.")
                return []

            # 如果提供了 symbol，就传给 ccxt；否则传 None (实盘可能允许 None)
            if symbol:
                positions = self.exchange.fetch_positions(symbol)
            else:
                positions = self.exchange.fetch_positions()

            # 处理响应
            positions = positions if isinstance(positions, list) else []

            self.logger.info(f"Successfully fetched {len(positions)} positions")
            return positions

        except Exception as e:
            self.logger.error(f"Failed to fetch positions for {symbol}: {e}")
            return []  # 发生错误时返回空列表，保证安全

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> List[List[float]]:
        """
        获取 OHLCV (K线) 数据

        Args:
            symbol: 交易对符号
            timeframe: 时间框架 (如 '1m', '5m', '1h')
            limit: 获取数量

        Returns:
            list: K线数据，每个元素为 [timestamp, open, high, low, close, volume]
        """
        if not symbol or not timeframe:
            self.logger.warning(f"Invalid parameters: symbol={symbol}, timeframe={timeframe}")
            return []

        try:
            # Mock 模式返回模拟数据
            if self.data_source_config.get('use_mock', False):
                return self._generate_mock_ohlcv(symbol, limit)

            # 实际模式从 API 获取
            self.logger.info(f"Fetching OHLCV data for {symbol} {timeframe}")

            try:
                # 尝试使用公共 API 获取（不需要认证）
                candles = self.exchange.public_get_market_candles(
                    instId=symbol,
                    bar=timeframe,
                    limit=str(limit)
                )

                if candles.get('code') != '0':
                    self.logger.warning(f"API returned error code: {candles.get('code')}")
                    return []

                data = candles.get('data', [])

                # 转换数据格式 [timestamp, open, high, low, close, volume]
                ohlcv = []
                for candle in data:
                    if len(candle) >= 6:
                        ohlcv.append([
                            int(candle[0]),  # timestamp
                            float(candle[1]),  # open
                            float(candle[2]),  # high
                            float(candle[3]),  # low
                            float(candle[4]),  # close
                            float(candle[5])   # volume
                        ])

                # 验证数据
                validated = self._validate_ohlcv_data(ohlcv, symbol, timeframe)

                self.logger.info(f"Fetched {len(validated)} candles for {symbol} {timeframe}")
                return validated

            except AttributeError:
                # 如果 public_get_market_candles 不可用，使用 fetch_ohlcv
                self.logger.warning("public_get_market_candles not available, using fetch_ohlcv")
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                return self._validate_ohlcv_data(ohlcv, symbol, timeframe)

        except Exception as e:
            self.logger.error(f"Failed to fetch OHLCV for {symbol} {timeframe}: {e}")
            return []

    def _generate_mock_ohlcv(self, symbol: str, limit: int) -> List[List[float]]:
        """生成模拟 OHLCV 数据（Mock 模式）"""
        import time
        base_price = 50000.0  # 默认基础价格
        ohlcv = []
        current_time = int(time.time() * 1000)

        for i in range(limit):
            # 生成随机波动
            price_change = (hash(str(i)) % 200 - 100)  # -100 到 +100
            timestamp = current_time - (limit - i) * 60000  # 每分钟

            open_price = base_price + price_change / 100
            high_price = open_price + abs(price_change) / 50
            low_price = open_price - abs(price_change) / 50
            close_price = open_price + (hash(str(i + 1)) % 50 - 25) / 100
            volume = (hash(str(i + 2)) % 1000) + 100

            ohlcv.append([timestamp, open_price, high_price, low_price, close_price, volume])

        return ohlcv

    def _validate_ohlcv_data(self, ohlcv_data: List[List[float]], symbol: str, timeframe: str) -> List[List[float]]:
        """
        验证 OHLCV 数据

        Args:
            ohlcv_data: 原始 K线数据
            symbol: 交易对符号
            timeframe: 时间框架

        Returns:
            list: 验证后的 K线数据
        """
        if not ohlcv_data:
            return []

        validated = []
        current_time = self.exchange.milliseconds() if hasattr(self.exchange, 'milliseconds') else int(time.time() * 1000)
        one_year_ago = current_time - 365 * 24 * 60 * 60 * 1000

        for candle in ohlcv_data:
            # 检查数据结构
            if not isinstance(candle, list) or len(candle) < 6:
                self.logger.warning(f"Invalid candle structure: {candle}")
                continue

            timestamp, open_price, high_price, low_price, close_price, volume = candle

            # 检查价格合理性
            if high_price < low_price:
                self.logger.warning(f"Invalid price: high={high_price} < low={low_price}")
                continue

            # 检查价格有效性
            if any(price <= 0 for price in [open_price, high_price, low_price, close_price]):
                self.logger.warning(f"Invalid zero/negative price in candle: {candle}")
                continue

            # 检查时间戳有效性
            if timestamp < one_year_ago:
                self.logger.warning(f"Timestamp too old: {timestamp}")
                continue

            # 检查时间戳格式
            if not isinstance(timestamp, (int, float)) or timestamp < 0:
                self.logger.warning(f"Invalid timestamp: {timestamp}")
                continue

            validated.append([timestamp, open_price, high_price, low_price, close_price, volume])

        return validated

    def _deduplicate_ohlcv_data(self, ohlcv_data: List[List[float]]) -> List[List[float]]:
        """
        去重 OHLCV 数据（基于时间戳）

        Args:
            ohlcv_data: 可能包含重复的 K线数据

        Returns:
            list: 去重后的 K线数据，保留最新的
        """
        if not ohlcv_data:
            return []

        # 使用字典去重，保留相同时间戳的最新数据
        unique_candles = {}
        for candle in reversed(ohlcv_data):  # 从后往前遍历，保留最新的
            timestamp = candle[0]
            unique_candles[timestamp] = candle

        # 按时间戳排序
        deduplicated = sorted(unique_candles.values(), key=lambda x: x[0])

        return deduplicated

    def fetch_multiple_timeframes(self, symbol: str, limit: int = 50) -> Dict[str, List[List[float]]]:
        """
        获取多个时间框架的 OHLCV 数据

        Args:
            symbol: 交易对符号
            limit: 每个时间框架获取的数量

        Returns:
            dict: 各时间框架的 K线数据
        """
        timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
        result = {}

        for tf in timeframes:
            try:
                ohlcv = self.fetch_ohlcv(symbol, tf, limit)
                result[tf] = ohlcv
            except Exception as e:
                self.logger.error(f"Failed to fetch {tf} data for {symbol}: {e}")
                result[tf] = []

        return result

    def fetch_orderbook(self, symbol: str, limit: int = 100) -> Optional[Dict[str, Any]]:
        """
        获取订单簿

        Args:
            symbol: 交易对符号
            limit: 获取深度

        Returns:
            dict: 订单簿数据 {bids: [...], asks: [...]}
        """
        if not symbol:
            self.logger.warning("Symbol is required for orderbook")
            return None

        try:
            self.logger.info(f"Fetching orderbook for {symbol}")

            # 尝试使用公共 API
            orderbook = self.exchange.public_get_market_books(
                instId=symbol,
                sz=str(limit)
            )

            if orderbook.get('code') != '0':
                self.logger.warning(f"API returned error: {orderbook.get('code')}")
                return None

            data = orderbook.get('data', [])
            if not data:
                return None

            book = data[0]
            bids = [[float(bid[0]), float(bid[1])] for bid in book.get('bids', [])]
            asks = [[float(ask[0]), float(ask[1])] for ask in book.get('asks', [])]

            return {
                'bids': bids,
                'asks': asks,
                'timestamp': book.get('ts')
            }

        except Exception as e:
            self.logger.error(f"Failed to fetch orderbook for {symbol}: {e}")
            return None

    def fetch_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取 Ticker 信息

        Args:
            symbol: 交易对符号

        Returns:
            dict: Ticker 信息
        """
        if not symbol:
            self.logger.warning("Symbol is required for ticker")
            return None

        try:
            self.logger.info(f"Fetching ticker for {symbol}")

            ticker = self.exchange.public_get_market_ticker(instId=symbol)

            if ticker.get('code') != '0':
                self.logger.warning(f"API returned error: {ticker.get('code')}")
                return None

            data = ticker.get('data', [])
            if not data:
                return None

            info = data[0]

            return {
                'symbol': symbol,
                'last': float(info.get('last', 0)),
                'bid': float(info.get('bidPx', 0)),
                'ask': float(info.get('askPx', 0)),
                'high': float(info.get('high24h', 0)),
                'low': float(info.get('low24h', 0)),
                'volume': float(info.get('vol24h', 0)),
                'timestamp': int(info.get('ts', 0))
            }

        except Exception as e:
            self.logger.error(f"Failed to fetch ticker for {symbol}: {e}")
            return None

    def fetch_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取最近交易记录

        Args:
            symbol: 交易对符号
            limit: 获取数量

        Returns:
            list: 交易记录列表（模拟盘始终返回空列表）
        """
        # OKX 模拟盘不支持获取交易记录
        if self.is_demo:
            self.logger.info("Demo mode does not support fetching recent trades")
            return []

        if not symbol:
            self.logger.warning("Symbol is required for recent trades")
            return []

        try:
            self.logger.info(f"Fetching recent trades for {symbol}")
            # 注意：公共 API 可能不支持此功能
            trades = []
            return trades
        except Exception as e:
            self.logger.error(f"Failed to fetch recent trades for {symbol}: {e}")
            return []

    def fetch_funding_rate(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取资金费率

        Args:
            symbol: 交易对符号（必须是永续合约，如 BTC-USDT-SWAP）

        Returns:
            dict: 资金费率信息
        """
        if not symbol:
            self.logger.warning("Symbol is required for funding rate")
            return None

        if not self.has_credentials:
            self.logger.warning("Cannot fetch funding rate: no credentials available")
            return None

        try:
            self.logger.info(f"Fetching funding rate for {symbol}")
            funding_rate = self.exchange.fetch_funding_rate(symbol)

            return {
                'symbol': symbol,
                'fundingRate': funding_rate.get('fundingRate', 0),
                'fundingTime': funding_rate.get('fundingTime', 0),
                'timestamp': self.exchange.milliseconds()
            }
        except Exception as e:
            self.logger.error(f"Failed to fetch funding rate for {symbol}: {e}")
            raise

    def get_market_info(self, symbol: str) -> Dict[str, Any]:
        """
        获取综合市场信息

        Args:
            symbol: 交易对符号

        Returns:
            dict: 包含 ticker、orderbook、ohlcv 等综合信息
        """
        self.logger.info(f"Fetching comprehensive market info for {symbol}")

        # 获取 ticker
        ticker = self.fetch_ticker(symbol)

        # 获取订单簿
        orderbook = self.fetch_orderbook(symbol)

        # 获取多时间框架 OHLCV
        ohlcv = self.fetch_multiple_timeframes(symbol, limit=50)

        # 获取最近交易
        trades = self.fetch_recent_trades(symbol)

        return {
            'symbol': symbol,
            'ticker': ticker,
            'orderbook': orderbook,
            'recent_trades': trades,
            'ohlcv': ohlcv,
            'timestamp': self.exchange.milliseconds() if hasattr(self.exchange, 'milliseconds') else int(time.time() * 1000),
            'use_demo': self.is_demo
        }
