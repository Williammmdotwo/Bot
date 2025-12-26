import ccxt
import logging
import os
import time
import random
from typing import Optional, Dict, Any, List
from src.utils.environment_utils import get_environment_config, get_api_credentials, get_ccxt_config, log_environment_info, get_data_source_config

class RESTClient:
    def __init__(self, use_demo=None):
        # Initialize logger
        self.logger = logging.getLogger(__name__)

        # 检查数据源配置
        data_config = get_data_source_config()
        self.use_mock = data_config['use_mock']

        # 如果是Mock模式，不需要初始化exchange
        if self.use_mock:
            self.use_demo = False
            self.has_credentials = False
            self.exchange = None
            self.logger.info("RESTClient initialized in Mock mode")
            return

        # 使用统一的环境判断工具
        if use_demo is None:
            config = get_environment_config()
            use_demo = config["is_demo"]
        else:
            # 保持向后兼容性，允许外部指定
            use_demo = use_demo

        credentials, has_credentials = get_api_credentials()
        ccxt_config = get_ccxt_config()

        # 🔥 核心修复：准备配置字典
        exchange_config = {
            'apiKey': credentials['api_key'] if has_credentials else '',
            'secret': credentials['secret'] if has_credentials else '',
            'password': credentials['passphrase'] if has_credentials else '',
            'enableRateLimit': True,
            'sandbox': ccxt_config['sandbox']
        }

        # 🔥 核心修复：如果是模拟盘，必须加这个 Header
        if ccxt_config['sandbox']:
            exchange_config['headers'] = {
                'x-simulated-trading': '1'
            }
            # 也可以加上这个，双重保险
            exchange_config['options'] = {'defaultType': 'spot'}

        # Initialize ccxt.okx exchange instance
        if has_credentials:
            self.exchange = ccxt.okx(exchange_config)
            # 使用我们自己的配置，包含headers
            if ccxt_config['sandbox']:
                self.logger.info(f"RESTClient initialized with OKX API credentials (demo environment) - with simulated trading header")
            else:
                self.logger.info(f"RESTClient initialized with OKX API credentials (production environment)")
        else:
            # Create client without credentials for public data only
            self.exchange = ccxt.okx(exchange_config)
            # 使用我们自己的配置，包含headers
            if ccxt_config['sandbox']:
                self.logger.warning(f"RESTClient initialized without API credentials (demo environment) - public data only - with simulated trading header")
            else:
                self.logger.warning(f"RESTClient initialized without API credentials (production environment) - public data only")

        # 🔥🔥🔥 新增：创建一个"匿名"的公共客户端 🔥🔥🔥
        public_config = {
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'},  # 默认为合约
        }

        # 如果是模拟盘，必须带上Header，但绝不带Key！
        if ccxt_config['sandbox']:
            public_config['headers'] = {'x-simulated-trading': '1'}

        self.public_exchange = ccxt.okx(public_config)
        if ccxt_config['sandbox']:
            self.public_exchange.set_sandbox_mode(True)

        self.logger.info("RESTClient: Public (Anonymous) client initialized for market data")

        self.use_demo = ccxt_config["sandbox"]
        self.has_credentials = has_credentials

    def fetch_balance(self):
        """Fetch account balance from OKX"""
        if not self.has_credentials:
            self.logger.warning("Cannot fetch balance: no API credentials available")
            return {"info": "No API credentials - balance unavailable", "free": {}, "used": {}, "total": {}}

        try:
            self.logger.info("Fetching balance for account...")
            return self.exchange.fetch_balance()
        except Exception as e:
            self.logger.error(f"Failed to fetch balance: {e}")
            raise

    def fetch_positions(self):
        """Fetch open positions from OKX"""
        if not self.has_credentials:
            self.logger.warning("Cannot fetch positions: no API credentials available")
            return []

        try:
            self.logger.info("Fetching positions for account...")
            return self.exchange.fetch_positions()
        except Exception as e:
            self.logger.error(f"Failed to fetch positions: {e}")
            raise

    def fetch_ohlcv(self, symbol: str, timeframe: str = '5m', limit: int = 100, since: int = None):
        try:
            self.logger.info(f"Fetching OHLCV for {symbol}")

            # 映射 timeframe 格式 (OKX 格式和 CCXT 基本一样，不用大改)
            params = {
                'instId': symbol,
                'bar': timeframe,
                'limit': limit
            }
            # 🔥 修复：删除时间戳参数，避免51000错误
            # 冷启动只需要最新的K线数据，不需要传时间参数

            # 🚀 直接调用 mark-price-candle (标记价格K线，最稳)
            # 或者用 public_get_market_candles
            response = self.public_exchange.public_get_market_candles(params)

            if response['code'] == '0' and response['data']:
                # OKX 返回的数据格式: [ts, o, h, l, c, vol, ...] (字符串)
                # 我们需要转成 [int, float, float, float, float, float]
                ohlcvs = []
                for item in response['data']:
                    ohlcvs.append([
                        int(item[0]),      # Timestamp
                        float(item[1]),    # Open
                        float(item[2]),    # High
                        float(item[3]),    # Low
                        float(item[4]),    # Close
                        float(item[5])     # Volume
                    ])
                # OKX 返回是倒序的（最新的在前），CCXT 习惯正序，翻转一下
                return sorted(ohlcvs, key=lambda x: x[0])
            else:
                self.logger.error(f"OHLCV API error: {response}")
                return []
        except Exception as e:
            self.logger.error(f"Failed to fetch OHLCV: {e}")
            return []

    def _validate_ohlcv_data(self, ohlcv_data: List, symbol: str, timeframe: str) -> List:
        """验证和清理OHLCV数据"""
        try:
            if not ohlcv_data:
                self.logger.warning(f"No OHLCV data returned for {symbol} {timeframe}")
                return []

            if not isinstance(ohlcv_data, list):
                self.logger.error(f"OHLCV data is not a list for {symbol} {timeframe}")
                return []

            if len(ohlcv_data) < 5:
                self.logger.warning(f"Insufficient OHLCV data for {symbol} {timeframe}: got {len(ohlcv_data)} candles, expected at least 5")
                # 仍然返回数据，但记录警告

            # 验证和清理每个K线数据
            validated_candles = []
            invalid_count = 0

            for i, candle in enumerate(ohlcv_data):
                try:
                    # 检查K线数据结构
                    if not isinstance(candle, list) or len(candle) < 6:
                        self.logger.warning(f"Invalid candle structure at index {i} for {symbol} {timeframe}: {candle}")
                        invalid_count += 1
                        continue

                    timestamp, open_price, high_price, low_price, close_price, volume = candle[:6]

                    # 验证数值类型和合理性
                    try:
                        timestamp = int(timestamp)
                        open_price = float(open_price)
                        high_price = float(high_price)
                        low_price = float(low_price)
                        close_price = float(close_price)
                        volume = float(volume)
                    except (ValueError, TypeError):
                        self.logger.warning(f"Invalid numeric values in candle at index {i} for {symbol} {timeframe}")
                        invalid_count += 1
                        continue

                    # 验证价格逻辑
                    if high_price < low_price:
                        self.logger.warning(f"Invalid price relationship in candle at index {i} for {symbol} {timeframe}: high({high_price}) < low({low_price})")
                        invalid_count += 1
                        continue

                    if close_price <= 0 or open_price <= 0:
                        self.logger.warning(f"Invalid price values in candle at index {i} for {symbol} {timeframe}: close={close_price}, open={open_price}")
                        invalid_count += 1
                        continue

                    if volume < 0:
                        self.logger.warning(f"Invalid volume in candle at index {i} for {symbol} {timeframe}: {volume}")
                        invalid_count += 1
                        continue

                    # 验证时间戳合理性（不能太旧或太新）
                    current_time = self.exchange.milliseconds()
                    if timestamp < current_time - 365 * 24 * 60 * 60 * 1000:  # 超过1年
                        self.logger.warning(f"Timestamp too old in candle at index {i} for {symbol} {timeframe}: {timestamp}")
                        invalid_count += 1
                        continue

                    if timestamp > current_time + 60 * 1000:  # 超过当前时间1分钟
                        self.logger.warning(f"Timestamp too new in candle at index {i} for {symbol} {timeframe}: {timestamp}")
                        invalid_count += 1
                        continue

                    # 如果通过所有验证，添加到验证后的数据中
                    validated_candles.append([timestamp, open_price, high_price, low_price, close_price, volume])

                except Exception as e:
                    self.logger.warning(f"Error validating candle at index {i} for {symbol} {timeframe}: {e}")
                    invalid_count += 1
                    continue

            # 记录验证结果
            total_candles = len(ohlcv_data)
            valid_candles = len(validated_candles)

            if invalid_count > 0:
                self.logger.warning(f"Data validation for {symbol} {timeframe}: {valid_candles}/{total_candles} valid candles, {invalid_count} invalid")

            if valid_candles == 0:
                self.logger.error(f"No valid candles found for {symbol} {timeframe}")
                return []

            # 检查数据连续性（时间戳应该递增）
            validated_candles.sort(key=lambda x: x[0])  # 按时间戳排序

            # 检查是否有重复的时间戳
            timestamps = [candle[0] for candle in validated_candles]
            unique_timestamps = len(set(timestamps))
            if unique_timestamps != len(timestamps):
                self.logger.warning(f"Found duplicate timestamps for {symbol} {timeframe}: {len(timestamps) - unique_timestamps} duplicates")
                # 移除重复项，保留最新的
                seen = set()
                unique_candles = []
                for candle in reversed(validated_candles):
                    if candle[0] not in seen:
                        seen.add(candle[0])
                        unique_candles.append(candle)
                validated_candles = list(reversed(unique_candles))

            self.logger.info(f"OHLCV data validation completed for {symbol} {timeframe}: {len(validated_candles)} valid candles")
            return validated_candles

        except Exception as e:
            self.logger.error(f"Error during OHLCV data validation for {symbol} {timeframe}: {e}")
            return []

    def fetch_multiple_timeframes(self, symbol: str, limit: int = 100):
        """Fetch OHLCV data for multiple timeframes"""
        timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
        data = {}
        successful_fetches = 0

        self.logger.info(f"Fetching multiple timeframes for {symbol} with limit {limit}")

        for tf in timeframes:
            try:
                # 计算时间范围，确保获取足够的历史数据
                timeframe_ms = self.exchange.parse_timeframe(tf) * 1000  # 转换为毫秒
                since = self.exchange.milliseconds() - limit * timeframe_ms

                self.logger.debug(f"Fetching {tf} data for {symbol}: since={since}, limit={limit}")
                ohlcv_data = self.fetch_ohlcv(symbol, since, limit, tf)

                if ohlcv_data:
                    data[tf] = ohlcv_data
                    successful_fetches += 1
                    self.logger.info(f"Successfully fetched {len(ohlcv_data)} candles for {symbol} {tf}")
                else:
                    data[tf] = []
                    self.logger.warning(f"No data returned for {symbol} {tf}")

            except Exception as e:
                self.logger.error(f"Failed to fetch {tf} data for {symbol}: {e}")
                data[tf] = []

        # 总结获取结果
        self.logger.info(f"Timeframe fetch summary for {symbol}: {successful_fetches}/{len(timeframes)} successful")

        # 检查关键时间框架是否成功获取
        critical_timeframes = ["5m", "15m", "1h"]
        missing_critical = [tf for tf in critical_timeframes if not data.get(tf)]
        if missing_critical:
            self.logger.warning(f"Missing critical timeframe data for {symbol}: {missing_critical}")

        return data

    def fetch_orderbook(self, symbol: str, limit: int = 10):
        try:
            params = {'instId': symbol, 'sz': limit}
            response = self.public_exchange.public_get_market_books(params)

            if response['code'] == '0' and response['data']:
                book = response['data'][0]
                # 简单构造返回
                return {
                    'bids': [[float(p), float(v)] for p, v, _ in book['bids']],
                    'asks': [[float(p), float(v)] for p, v, _ in book['asks']],
                    'timestamp': int(book['ts'])
                }
            return None
        except Exception as e:
            self.logger.error(f"Failed to fetch orderbook: {e}")
            return None

    def fetch_ticker(self, symbol: str):
        """Fetch 24hr ticker data"""
        try:
            self.logger.info(f"Fetching ticker for {symbol}")
            # 🚀 绕过 CCXT 解析，直接调 OKX 接口
            # 注意：symbol 这里必须传 'BTC-USDT-SWAP' 这种格式
            response = self.public_exchange.public_get_market_ticker({'instId': symbol})

            # 手动提取我们需要的数据
            if response['code'] == '0' and response['data']:
                ticker_data = response['data'][0]
                # 构造成 CCXT 风格的字典，保持兼容性
                return {
                    'symbol': symbol,
                    'last': float(ticker_data['last']),
                    'bid': float(ticker_data['bidPx']),
                    'ask': float(ticker_data['askPx']),
                    'high': float(ticker_data['high24h']),
                    'low': float(ticker_data['low24h']),
                    'volume': float(ticker_data['vol24h']),
                    'quoteVolume': float(ticker_data['volCcy24h']),
                    'timestamp': int(ticker_data['ts']),
                }
            else:
                self.logger.error(f"Ticker API error: {response}")
                return None
        except Exception as e:
            self.logger.error(f"Failed to fetch ticker: {e}")
            return None

    def fetch_recent_trades(self, symbol: str, limit: int = 100):
        """Fetch recent trades data"""
        try:
            self.logger.info(f"Fetching recent trades for {symbol}, limit: {limit}")
            return self.exchange.fetch_trades(symbol, limit=limit)
        except Exception as e:
            self.logger.error(f"Failed to fetch recent trades: {e}")
            raise

    def fetch_funding_rate(self, symbol: str):
        """Fetch funding rate for perpetual contracts"""
        try:
            self.logger.info(f"Fetching funding rate for {symbol}")
            return self.exchange.fetch_funding_rate(symbol)
        except Exception as e:
            self.logger.error(f"Failed to fetch funding rate: {e}")
            raise

    def get_market_info(self, symbol: str):
        """Get comprehensive market information"""
        try:
            self.logger.info(f"Getting market info for {symbol}")

            # Fetch multiple data types
            ticker = self.fetch_ticker(symbol)
            orderbook = self.fetch_orderbook(symbol, 20)
            recent_trades = self.fetch_recent_trades(symbol, 50)
            ohlcv_data = self.fetch_multiple_timeframes(symbol, 50)

            return {
                "symbol": symbol,
                "ticker": ticker,
                "orderbook": orderbook,
                "recent_trades": recent_trades,
                "ohlcv": ohlcv_data,
                "timestamp": self.exchange.milliseconds(),
                "use_demo": self.use_demo
            }

        except Exception as e:
            self.logger.error(f"Failed to get market info: {e}")
            raise

    def _deduplicate_ohlcv_data(self, ohlcv_data: List[List]) -> List[List]:
        """去除重复的OHLCV数据，保留第一次出现的数据"""
        if not ohlcv_data:
            return []

        # 按时间戳去重，保留第一次出现的数据
        seen_timestamps = set()
        deduplicated = []

        # 按原始顺序遍历，保留第一次出现的数据
        for candle in ohlcv_data:
            timestamp = candle[0]
            if timestamp not in seen_timestamps:
                seen_timestamps.add(timestamp)
                deduplicated.append(candle)

        return deduplicated
