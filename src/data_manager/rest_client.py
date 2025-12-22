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

        # Initialize ccxt.okx exchange instance
        if has_credentials:
            self.exchange = ccxt.okx(ccxt_config)
            # 使用CCXT默认的sandbox配置，不强制修改域名
            if ccxt_config['sandbox']:
                self.logger.info(f"RESTClient initialized with OKX API credentials (demo environment) - using CCXT default sandbox")
            else:
                self.logger.info(f"RESTClient initialized with OKX API credentials (production environment) - using CCXT default")
        else:
            # Create client without credentials for public data only
            self.exchange = ccxt.okx(ccxt_config)
            # 使用CCXT默认的sandbox配置，不强制修改域名
            if ccxt_config['sandbox']:
                self.logger.warning(f"RESTClient initialized without API credentials (demo environment) - public data only - using CCXT default sandbox")
            else:
                self.logger.warning(f"RESTClient initialized without API credentials (production environment) - public data only - using CCXT default")

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

    def fetch_ohlcv(self, symbol: str, since: int, limit: int, timeframe="5m", max_retries: int = 3):
        """Fetch OHLCV data from OKX for data backfill with retry mechanism and data validation"""
        # 确保最少获取50个K线数据
        actual_limit = max(limit, 50)

        for attempt in range(max_retries):
            try:
                self.logger.debug(f"OHLCV fetch attempt {attempt + 1}/{max_retries} for {symbol} {timeframe}")

                # 验证参数
                if not symbol or not isinstance(symbol, str):
                    raise ValueError(f"Invalid symbol: {symbol}")

                if not timeframe or timeframe not in ["1m", "5m", "15m", "1h", "4h", "1d"]:
                    raise ValueError(f"Invalid timeframe: {timeframe}")

                if since <= 0:
                    # 如果since无效，计算合理的时间范围
                    timeframe_ms = self.exchange.parse_timeframe(timeframe) * 1000
                    since = self.exchange.milliseconds() - actual_limit * timeframe_ms
                    self.logger.warning(f"Invalid since parameter, calculated new since: {since}")

                self.logger.info(f"Fetching OHLCV data for {symbol}, timeframe: {timeframe}, since: {since}, limit: {actual_limit}")

                # 尝试获取数据
                ohlcv_data = self.exchange.fetch_ohlcv(symbol, timeframe, since, actual_limit)

                # 验证和清理数据
                validated_data = self._validate_ohlcv_data(ohlcv_data, symbol, timeframe)



                # 数据去重
                validated_data = self._deduplicate_ohlcv_data(validated_data)

                if validated_data:
                    self.logger.info(f"Successfully fetched and validated {len(validated_data)} OHLCV candles for {symbol} {timeframe}")
                    return validated_data
                else:
                    self.logger.warning(f"Data validation failed for {symbol} {timeframe} on attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        # 指数退避重试
                        wait_time = 2 ** attempt
                        self.logger.info(f"Retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                    continue

            except ccxt.NetworkError as e:
                self.logger.warning(f"Network error fetching OHLCV data for {symbol} {timeframe} on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    self.logger.info(f"Retrying in {wait_time} seconds due to network error...")
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.error(f"All {max_retries} attempts failed due to network error for {symbol} {timeframe}")
                    raise

            except ccxt.ExchangeError as e:
                self.logger.warning(f"Exchange error fetching OHLCV data for {symbol} {timeframe} on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    self.logger.info(f"Retrying in {wait_time} seconds due to exchange error...")
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.error(f"All {max_retries} attempts failed due to exchange error for {symbol} {timeframe}")
                    raise

            except Exception as e:
                self.logger.warning(f"Unexpected error fetching OHLCV data for {symbol} {timeframe} on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    self.logger.info(f"Retrying in {wait_time} seconds due to unexpected error...")
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.error(f"All {max_retries} attempts failed due to unexpected error for {symbol} {timeframe}")
                    raise

        self.logger.error(f"Failed to fetch OHLCV data for {symbol} {timeframe} after {max_retries} attempts")
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

    def fetch_orderbook(self, symbol: str, limit: int = 100):
        """Fetch order book depth data"""
        try:
            self.logger.info(f"Fetching order book for {symbol}, limit: {limit}")
            return self.exchange.fetch_order_book(symbol, limit)
        except Exception as e:
            self.logger.error(f"Failed to fetch order book: {e}")
            raise

    def fetch_ticker(self, symbol: str):
        """Fetch 24hr ticker data"""
        if self.use_mock:
            return self._generate_mock_ticker(symbol)

        try:
            self.logger.info(f"Fetching ticker for {symbol}")
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            self.logger.error(f"Failed to fetch ticker: {e}")
            raise

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
