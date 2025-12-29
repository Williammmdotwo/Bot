import redis
import logging
import asyncio
import asyncpg
import json
import os
import threading
import time
import traceback
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

# Fix relative imports for direct execution
try:
    from .clients.websocket_client import OKXWebSocketClient
    from .clients.rest_client import RESTClient
    from .core.technical_indicators import TechnicalIndicators
    from src.utils.environment_utils import get_data_source_config, get_data_source_label, is_using_mock_data
except ImportError:
    from src.data_manager.clients.websocket_client import OKXWebSocketClient
    from src.data_manager.clients.rest_client import RESTClient
    from src.data_manager.core.technical_indicators import TechnicalIndicators
    from src.utils.environment_utils import get_data_source_config, get_data_source_label, is_using_mock_data

class DataHandler:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._stop_event = threading.Event()

        # 使用新的数据源配置系统
        try:
            # 获取数据源配置
            data_source_config = get_data_source_config()
            self.data_source_type = data_source_config['data_source_type']
            self.data_source_label = data_source_config['data_source_label']

            # 统一初始化REST客户端（Mock和API模式都用）
            use_demo = data_source_config['use_demo']
            self.rest_client = RESTClient(use_demo=use_demo)

            if data_source_config['use_mock']:
                self.logger.info(f"[{self.data_source_label}] 初始化完成 - 使用本地Mock数据")
            else:
                self.logger.info(f"[{self.data_source_label}] REST客户端初始化成功 (use_demo={use_demo})")

        except (ConnectionError, ValueError, KeyError) as e:
            self.logger.error(f"[{self.data_source_label}] REST客户端初始化失败: {e}")
            raise
        except Exception as e:
            self.logger.error(f"[{self.data_source_label}] REST客户端初始化异常: {e}")
            raise

        # Connect to Redis (optional for testing)
        self.redis_client = None
        try:
            # Check if Redis is disabled for testing
            if os.getenv('DISABLE_REDIS', 'false').lower() == 'true':
                self.logger.warning("Redis disabled by DISABLE_REDIS=true")
                # Don't return here, continue to database initialization
                pass
            else:
                # Try REDIS_URL first (Docker environment)
                redis_url = os.getenv("REDIS_URL")
                if redis_url:
                    # Parse redis://:password@host:port format
                    import re
                    match = re.match(r'redis://:(?P<password>[^@]*)@(?P<host>[^:]+):(?P<port>\d+)', redis_url)
                    if match:
                        self.redis_client = redis.Redis(
                            host=match.group('host'),
                            port=int(match.group('port')),
                            password=match.group('password'),
                            decode_responses=True
                        )
                        self.logger.info(f"Connected to Redis via URL: {match.group('host')}:{match.group('port')}")
                    else:
                        # Fallback to localhost parsing
                        self.redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
                        self.logger.info(f"Connected to Redis via URL")
                else:
                    # Fallback to individual environment variables
                    redis_host = os.getenv("REDIS_HOST", "localhost")
                    redis_port = os.getenv("REDIS_PORT", "6379")
                    redis_password = os.getenv("REDIS_PASSWORD")

                    # Connect with password if provided
                    if redis_password:
                        self.redis_client = redis.Redis(
                            host=redis_host,
                            port=redis_port,
                            password=redis_password,
                            decode_responses=True
                        )
                    else:
                        self.redis_client = redis.Redis(
                            host=redis_host,
                            port=redis_port,
                            decode_responses=True
                        )

                    self.logger.info(f"Connected to Redis at {redis_host}:{redis_port}")

            # 优化的缓存策略配置
            self.OPTIMIZED_CACHE_DURATION = {
                "1m": 180,      # 3分钟
                "5m": 900,      # 15分钟
                "15m": 1800,    # 30分钟
                "1h": 3600,     # 1小时
                "4h": 7200,     # 2小时
                "1d": 14400      # 4小时
            }

            # Test Redis connection
            self.redis_client.ping()
            self.logger.info("Redis connection test successful")
        except (redis.ConnectionError, redis.AuthenticationError, redis.TimeoutError) as e:
            self.logger.warning(f"Redis connection failed: {e}")
            self.redis_client = None
        except (ValueError, OSError) as e:
            self.logger.warning(f"Redis configuration error: {e}")
            self.redis_client = None
        except Exception as e:
            self.logger.warning(f"Unexpected Redis error: {e}")
            self.redis_client = None

        # Connect to PostgreSQL (with database switch)
        use_database = os.getenv('USE_DATABASE', 'false').lower() == 'true'

        # Always initialize pg_pool attribute
        self.pg_pool = None

        if use_database:
            try:
                postgres_db = os.getenv("POSTGRES_DB")
                postgres_user = os.getenv("POSTGRES_USER")
                postgres_password = os.getenv("POSTGRES_PASSWORD")
                postgres_host = os.getenv("POSTGRES_HOST", "localhost")
                postgres_port = os.getenv("POSTGRES_PORT", "5432")

                if not all([postgres_db, postgres_user, postgres_password]):
                    self.logger.warning("Database credentials not provided, skipping database connection")
                    return

                # Create async connection pool
                try:
                    self.pg_pool = asyncio.run(self._create_pg_pool(
                        postgres_host, postgres_port, postgres_db,
                        postgres_user, postgres_password
                    ))
                except Exception as e:
                    self.logger.error(f"Failed to create PostgreSQL pool: {e}")
                    self.pg_pool = None
                self.logger.info(f"Connected to PostgreSQL database: {postgres_db}")
            except Exception as e:
                self.logger.error(f"Failed to connect to PostgreSQL: {e}")
                self.pg_pool = None
        else:
            self.logger.info("Database functionality disabled by USE_DATABASE=false")

        # WebSocket client will be initialized in start method
        self.ws_client = None

    async def _create_pg_pool(self, host: str, port: str, database: str,
                            user: str, password: str) -> asyncpg.Pool:
        """Create PostgreSQL connection pool"""
        return await asyncpg.create_pool(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            min_size=1,
            max_size=10,
            command_timeout=60
        )

    def _check_indicators_ready(self) -> bool:
        """Check if indicators are ready"""
        try:
            if not self.redis_client:
                return False
            # Check if we have recent data in Redis
            test_symbol = "BTC-USDT"
            redis_key = f"ohlcv:{test_symbol}:5m"
            latest_data = self.redis_client.zrevrange(redis_key, 0, 0)
            return len(latest_data) > 0
        except Exception:
            return False

    def get_comprehensive_market_data(self, symbol: str, use_demo: bool = False) -> Dict[str, Any]:
        """Get comprehensive market data with technical analysis"""
        start_time = time.time()

        try:
            self.logger.info(f"[{self.data_source_label}] 获取 {symbol} 综合市场数据")

            # 根据数据源类型处理
            if self.data_source_type == "MOCK_DATA":
                # Mock数据模式
                self.logger.info(f"[{self.data_source_label}] 使用本地Mock数据")
                return self._generate_mock_market_data(symbol, use_demo)

            # OKX API模式 - 初始化REST客户端
            try:
                rest_client = RESTClient(use_demo=use_demo)
            except Exception as e:
                self.logger.error(f"[{self.data_source_label}] REST客户端初始化失败: {e}")
                return self._get_fallback_data(symbol, "REST_CLIENT_INIT_FAILED")

            # Get market information with service degradation
            market_info = None
            try:
                market_info = rest_client.get_market_info(symbol)
                if not market_info:
                    self.logger.warning(f"Market info returned None for {symbol}, attempting service degradation")
                    market_info = self._get_degraded_market_data(rest_client, symbol)
            except Exception as e:
                self.logger.error(f"Failed to get market info for {symbol}: {e}")
                self.logger.info("Attempting service degradation...")
                market_info = self._get_degraded_market_data(rest_client, symbol)

            if not market_info:
                self.logger.error(f"OKX API failed to get market info for {symbol}")
                return self._get_fallback_data(symbol, "OKX_API_FAILED")

            # Calculate technical indicators for each timeframe with error handling
            technical_analysis = {}
            successful_timeframes = []
            failed_timeframes = []

            # 确保有OHLCV数据
            ohlcv_data = market_info.get("ohlcv", {})
            if not ohlcv_data:
                self.logger.error(f"No OHLCV data from OKX API for {symbol}")
                return self._get_fallback_data(symbol, "NO_OHLCV_DATA")

            for tf, candles in ohlcv_data.items():
                try:
                    if candles and len(candles) >= 10:  # 确保有足够的数据
                        technical_analysis[tf] = TechnicalIndicators.calculate_all_indicators(candles)
                        successful_timeframes.append(tf)
                        self.logger.info(f"Successfully calculated indicators for {symbol} {tf}: {len(candles)} candles")
                    else:
                        self.logger.warning(f"Insufficient OHLCV data for {symbol} {tf}: {len(candles) if candles else 0} candles")
                        failed_timeframes.append(tf)
                except Exception as e:
                    self.logger.error(f"Failed to calculate indicators for {symbol} {tf}: {e}")
                    failed_timeframes.append(tf)
                    # 继续处理其他时间框架

            # 记录时间框架处理结果
            if successful_timeframes:
                self.logger.info(f"Successfully calculated indicators for {symbol}: {successful_timeframes}")
            if failed_timeframes:
                self.logger.warning(f"Failed to calculate indicators for {symbol}: {failed_timeframes}")

            # Analyze volume profile with error handling
            volume_profile = {}
            try:
                if market_info.get("recent_trades"):
                    volume_profile = TechnicalIndicators.analyze_volume_profile(market_info["recent_trades"])
                else:
                    self.logger.warning(f"No recent trades data for {symbol}")
            except Exception as e:
                self.logger.error(f"Failed to analyze volume profile for {symbol}: {e}")

            # Get current market state with validation
            current_price = 0
            orderbook = {}
            ticker = {}

            try:
                ticker = market_info.get("ticker", {})
                current_price = ticker.get("last", 0) if ticker else 0
                orderbook = market_info.get("orderbook", {})

                # 验证价格合理性
                if current_price <= 0:
                    self.logger.warning(f"Invalid current price for {symbol}: {current_price}")
                    # 尝试从订单簿获取价格
                    if orderbook.get("bids") and orderbook.get("asks"):
                        best_bid = orderbook["bids"][0][0] if orderbook["bids"] else 0
                        best_ask = orderbook["asks"][0][0] if orderbook["asks"] else 0
                        if best_bid > 0 and best_ask > 0:
                            current_price = (best_bid + best_ask) / 2
                            self.logger.info(f"Derived price from orderbook for {symbol}: {current_price}")

            except Exception as e:
                self.logger.error(f"Failed to extract market state for {symbol}: {e}")

            # Calculate market sentiment with error handling
            sentiment = {}
            try:
                sentiment = self._calculate_market_sentiment(market_info, technical_analysis)
            except Exception as e:
                self.logger.error(f"Failed to calculate market sentiment for {symbol}: {e}")
                sentiment = {"overall_sentiment": "neutral", "sentiment_score": 0.0}

            # 确定数据状态
            data_status = "COMPREHENSIVE"
            if failed_timeframes:
                data_status = "PARTIAL"
            if len(successful_timeframes) == 0:
                data_status = "DEGRADED"

            processing_time = time.time() - start_time
            self.logger.info(f"Market data processing for {symbol} completed in {processing_time:.2f}s, status: {data_status}")

            comprehensive_data = {
                "symbol": symbol,
                "current_price": current_price,
                "ticker": ticker,
                "orderbook": orderbook,
                "recent_trades": market_info.get("recent_trades", []),
                "technical_analysis": technical_analysis,
                "volume_profile": volume_profile,
                "market_sentiment": sentiment,
                "timestamp": market_info.get("timestamp", int(time.time() * 1000)),
                "use_demo": use_demo,
                "data_status": data_status,
                "processing_time": processing_time,
                "successful_timeframes": successful_timeframes,
                "failed_timeframes": failed_timeframes
            }

            # Cache in Redis with error handling
            try:
                self._cache_market_data(symbol, comprehensive_data)
            except Exception as e:
                self.logger.error(f"Failed to cache market data for {symbol}: {e}")
                # 缓存失败不影响主流程，只记录错误

            return comprehensive_data

        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(f"Critical error in get_comprehensive_market_data for {symbol} after {processing_time:.2f}s: {e}")
            self.logger.debug(traceback.format_exc())
            return self._get_fallback_data(symbol, "CRITICAL_ERROR")

    def get_snapshot(self, symbol: str) -> Dict[str, Any]:
        """Get market snapshot with service degradation support"""
        import json

        def _fetch_from_redis():
            # Get latest N Klines from Redis Sorted Set
            redis_key = f"ohlcv:{symbol}:5m"
            latest_data = self.redis_client.zrevrange(redis_key, 0, 49)  # Get latest 50 candles
            klines = [json.loads(data) for data in latest_data]

            # Get latest indicators from Redis (assuming they are stored separately)
            indicators_key = f"indicators:{symbol}:5m"
            indicators_raw = self.redis_client.get(indicators_key) or "{}"
            indicators = json.loads(indicators_raw)

            # Get account status from Redis
            account_key = f"account:status"
            account_raw = self.redis_client.get(account_key) or "{}"
            account = json.loads(account_raw)

            return {
                "symbol": symbol,
                "klines": klines,
                "indicators": indicators,
                "account": account,
                "data_status": "OK"
            }

        try:
            snapshot = _fetch_from_redis()

            # Check if indicators are ready
            if not self._check_indicators_ready():
                snapshot["data_status"] = "INDICATORS_NOT_READY"

            self.logger.info(f"Successfully retrieved snapshot for {symbol} from Redis")
            return snapshot

        except Exception as e:
            self.logger.warning(f"Redis failed, performing service degradation for {symbol}: {e}")

            # Service degradation: fetch data from REST client
            try:
                # Get latest OHLCV data for backfill
                import time
                since = int((time.time() - 300 * 50) * 1000)  # Last 50 candles (5min each)
                ohlcv_data = self.rest_client.fetch_ohlcv(symbol, since, 50)
                # Convert OHLCV to expected format [{"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}]
                klines = [
                    {
                        "timestamp": candle[0],
                        "open": candle[1],
                        "high": candle[2],
                        "low": candle[3],
                        "close": candle[4],
                        "volume": candle[5]
                    } for candle in ohlcv_data
                ]

                # Get account status
                balance = self.rest_client.fetch_balance()
                positions = self.rest_client.fetch_positions()
                account = {
                    "balance": balance,
                    "positions": positions
                }

                return {
                    "symbol": symbol,
                    "klines": klines,
                    "indicators": {},
                    "account": account,
                    "data_status": "DEGRADED"
                }

            except Exception as rest_error:
                self.logger.error(f"REST client also failed for {symbol}: {rest_error}")
                # Return minimal error snapshot
                return {
                    "symbol": symbol,
                    "klines": [],
                    "indicators": {},
                    "account": {},
                    "data_status": "ERROR"
                }

    def _calculate_market_sentiment(self, market_info: Dict, technical_analysis: Dict) -> Dict[str, Any]:
        """Calculate market sentiment based on orderbook and trades"""
        try:
            orderbook = market_info.get("orderbook", {})
            recent_trades = market_info.get("recent_trades", [])

            # Analyze orderbook imbalance
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])

            total_bid_volume = sum(bid[1] for bid in bids[:5]) if len(bids) >= 5 else 0
            total_ask_volume = sum(ask[1] for ask in asks[:5]) if len(asks) >= 5 else 0

            orderbook_imbalance = (total_bid_volume - total_ask_volume) / (total_bid_volume + total_ask_volume) if (total_bid_volume + total_ask_volume) > 0 else 0

            # Analyze trade direction
            buy_volume = sum(trade.get("amount", 0) for trade in recent_trades if trade.get("side") == "buy")
            sell_volume = sum(trade.get("amount", 0) for trade in recent_trades if trade.get("side") == "sell")

            trade_imbalance = (buy_volume - sell_volume) / (buy_volume + sell_volume) if (buy_volume + sell_volume) > 0 else 0

            # Get technical sentiment from 5m timeframe
            tf_5m = technical_analysis.get("5m", {})
            momentum = tf_5m.get("momentum", "neutral")
            trend = tf_5m.get("trend", "sideways")

            # Overall sentiment score
            sentiment_score = (orderbook_imbalance * 0.3 + trade_imbalance * 0.4 +
                             (1 if "bullish" in momentum else -1 if "bearish" in momentum else 0) * 0.3)

            return {
                "sentiment_score": float(sentiment_score),
                "orderbook_imbalance": float(orderbook_imbalance),
                "trade_imbalance": float(trade_imbalance),
                "technical_momentum": momentum,
                "technical_trend": trend,
                "overall_sentiment": "bullish" if sentiment_score > 0.2 else "bearish" if sentiment_score < -0.2 else "neutral"
            }

        except Exception as e:
            self.logger.warning(f"Failed to calculate market sentiment: {e}")
            return {"overall_sentiment": "neutral", "sentiment_score": 0.0}

    def _cache_market_data(self, symbol: str, data: Dict[str, Any]):
        """Cache market data in Redis with improved strategy"""
        if not self.redis_client:
            return  # Skip caching if Redis is not available

        try:
            timestamp = int(time.time())

            # Cache comprehensive market data with version control
            cache_key = f"market_data:{symbol}:v2"
            cache_data = {
                "data": data,
                "timestamp": timestamp,
                "version": "2.0",
                "symbol": symbol
            }
            self.redis_client.setex(cache_key, 300, json.dumps(cache_data))  # Cache for 5 minutes

            # Cache technical analysis separately with detailed metadata
            technical_key = f"technical_analysis:{symbol}:v2"
            technical_data = data.get("technical_analysis", {})
            if technical_data and "error" not in technical_data:
                technical_cache = {
                    "data": technical_data,
                    "timestamp": timestamp,
                    "data_points": len(technical_data),
                    "symbol": symbol,
                    "version": "2.0"
                }
                self.redis_client.setex(technical_key, 300, json.dumps(technical_cache))

            # Cache OHLCV data for each timeframe with quality metrics
            ohlcv_data = data.get("ohlcv", {})
            for timeframe, candles in ohlcv_data.items():
                if candles:
                    ohlcv_key = f"ohlcv:{symbol}:{timeframe}:v2"
                    ohlcv_cache = {
                        "candles": candles,
                        "timestamp": timestamp,
                        "count": len(candles),
                        "timeframe": timeframe,
                        "symbol": symbol,
                        "version": "2.0"
                    }
                    # OHLCV data cached for longer (15 minutes)
                    self.redis_client.setex(ohlcv_key, 900, json.dumps(ohlcv_cache))

            # Cache market sentiment separately
            sentiment_data = data.get("market_sentiment", {})
            if sentiment_data:
                sentiment_key = f"market_sentiment:{symbol}:v2"
                sentiment_cache = {
                    "data": sentiment_data,
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "version": "2.0"
                }
                self.redis_client.setex(sentiment_key, 180, json.dumps(sentiment_cache))  # 3 minutes

            self.logger.info(f"Successfully cached market data for {symbol} with {len(ohlcv_data)} timeframes")

        except Exception as e:
            self.logger.error(f"Failed to cache market data for {symbol}: {e}")

    def _get_degraded_market_data(self, rest_client: RESTClient, symbol: str) -> Optional[Dict[str, Any]]:
        """Get degraded market data when full market info fails"""
        try:
            self.logger.info(f"Attempting degraded data fetch for {symbol}")

            # 尝试获取基本数据
            degraded_data = {
                "symbol": symbol,
                "ticker": {},
                "orderbook": {},
                "recent_trades": [],
                "ohlcv": {},
                "timestamp": int(time.time() * 1000)
            }

            # 尝试获取ticker数据
            try:
                ticker = rest_client.fetch_ticker(symbol)
                if ticker:
                    degraded_data["ticker"] = ticker
                    self.logger.info(f"Successfully fetched ticker for {symbol}")
            except Exception as e:
                self.logger.warning(f"Failed to fetch ticker for {symbol}: {e}")

            # 尝试获取订单簿数据
            try:
                orderbook = rest_client.fetch_orderbook(symbol, 10)
                if orderbook:
                    degraded_data["orderbook"] = orderbook
                    self.logger.info(f"Successfully fetched orderbook for {symbol}")
            except Exception as e:
                self.logger.warning(f"Failed to fetch orderbook for {symbol}: {e}")

            # 尝试获取OHLCV数据（仅关键时间框架）
            try:
                critical_timeframes = ["5m", "15m", "1h"]
                ohlcv_data = {}

                for tf in critical_timeframes:
                    try:
                        since = int((time.time() - 300 * 50) * 1000)  # 最近50个K线
                        ohlcv = rest_client.fetch_ohlcv(symbol, since, 50, tf)
                        if ohlcv:
                            ohlcv_data[tf] = ohlcv
                            self.logger.info(f"Successfully fetched {tf} OHLCV for {symbol}: {len(ohlcv)} candles")
                    except Exception as e:
                        self.logger.warning(f"Failed to fetch {tf} OHLCV for {symbol}: {e}")

                degraded_data["ohlcv"] = ohlcv_data

            except Exception as e:
                self.logger.warning(f"Failed to fetch OHLCV data for {symbol}: {e}")

            # 尝试获取最近交易
            try:
                trades = rest_client.fetch_recent_trades(symbol, 20)
                if trades:
                    degraded_data["recent_trades"] = trades
                    self.logger.info(f"Successfully fetched recent trades for {symbol}: {len(trades)} trades")
            except Exception as e:
                self.logger.warning(f"Failed to fetch recent trades for {symbol}: {e}")

            # 检查是否有任何数据
            has_data = (
                degraded_data["ticker"] or
                degraded_data["orderbook"] or
                degraded_data["ohlcv"] or
                degraded_data["recent_trades"]
            )

            if has_data:
                self.logger.info(f"Degraded data fetch successful for {symbol}")
                return degraded_data
            else:
                self.logger.warning(f"No data available in degraded fetch for {symbol}")
                return None

        except Exception as e:
            self.logger.error(f"Degraded market data fetch failed for {symbol}: {e}")
            return None

    def _generate_mock_market_data(self, symbol: str, use_demo: bool = False) -> Dict[str, Any]:
        """Generate mock market data for testing when real data is unavailable"""
        try:
            self.logger.info(f"[{self.data_source_label}] 生成 {symbol} Mock市场数据")

            # 生成模拟价格数据
            import random
            base_price = 50000.0 if "BTC" in symbol else 3000.0 if "ETH" in symbol else 100.0

            # 生成模拟OHLCV数据
            mock_ohlcv = {}
            timeframes = ["5m", "15m", "1h", "4h"]

            for tf in timeframes:
                candles = []
                current_time = int(time.time() * 1000)
                tf_minutes = self._timeframe_to_minutes(tf)

                # 生成50根K线
                for i in range(50):
                    timestamp = current_time - (50 - i) * tf_minutes * 60 * 1000

                    # 模拟价格波动
                    price_change = random.uniform(-0.02, 0.02)  # ±2%波动
                    open_price = base_price * (1 + price_change)
                    close_price = open_price * random.uniform(0.98, 1.02)
                    high_price = max(open_price, close_price) * random.uniform(1.0, 1.01)
                    low_price = min(open_price, close_price) * random.uniform(0.99, 1.0)
                    volume = random.uniform(100, 1000)

                    candles.append([timestamp, open_price, high_price, low_price, close_price, volume])

                mock_ohlcv[tf] = candles

            # 计算技术指标
            technical_analysis = {}
            successful_timeframes = []

            for tf, candles in mock_ohlcv.items():
                try:
                    if candles and len(candles) >= 10:
                        technical_analysis[tf] = TechnicalIndicators.calculate_all_indicators(candles)
                        successful_timeframes.append(tf)
                        self.logger.info(f"Successfully calculated mock indicators for {symbol} {tf}: {len(candles)} candles")
                except Exception as e:
                    self.logger.error(f"Failed to calculate mock indicators for {symbol} {tf}: {e}")

            # 生成模拟ticker
            current_price = base_price * random.uniform(0.98, 1.02)
            ticker = {
                "symbol": symbol,
                "last": current_price,
                "bid": current_price * 0.999,
                "ask": current_price * 1.001,
                "baseVolume": random.uniform(1000, 10000),
                "quoteVolume": random.uniform(100000, 1000000),
                "change": random.uniform(-5, 5),
                "percentage": random.uniform(-5, 5),
                "timestamp": int(time.time() * 1000)
            }

            # 确保current_price不为0
            if current_price <= 0:
                current_price = base_price
                ticker["last"] = current_price
                ticker["bid"] = current_price * 0.999
                ticker["ask"] = current_price * 1.001

            # 生成模拟订单簿
            orderbook = {
                "symbol": symbol,
                "bids": [],
                "asks": [],
                "timestamp": int(time.time() * 1000)
            }

            # 生成买单
            for i in range(10):
                price = current_price * (1 - (i + 1) * 0.001)
                volume = random.uniform(0.1, 10)
                orderbook["bids"].append([price, volume])

            # 生成卖单
            for i in range(10):
                price = current_price * (1 + (i + 1) * 0.001)
                volume = random.uniform(0.1, 10)
                orderbook["asks"].append([price, volume])

            # 生成模拟交易记录
            recent_trades = []
            for i in range(20):
                trade_time = int(time.time() * 1000) - i * 60000  # 每分钟一笔
                trade_price = current_price * random.uniform(0.999, 1.001)
                trade_amount = random.uniform(0.1, 5)
                trade_side = random.choice(["buy", "sell"])

                recent_trades.append({
                    "timestamp": trade_time,
                    "price": trade_price,
                    "amount": trade_amount,
                    "side": trade_side
                })

            # 计算市场情绪
            sentiment = self._calculate_market_sentiment(
                {"orderbook": orderbook, "recent_trades": recent_trades},
                technical_analysis
            )

            # 分析成交量分布
            volume_profile = TechnicalIndicators.analyze_volume_profile(recent_trades)

            mock_data = {
                "symbol": symbol,
                "current_price": current_price,
                "ticker": ticker,
                "orderbook": orderbook,
                "recent_trades": recent_trades,
                "technical_analysis": technical_analysis,
                "volume_profile": volume_profile,
                "market_sentiment": sentiment,
                "timestamp": int(time.time() * 1000),
                "use_demo": use_demo,
                "data_status": "MOCK_DATA",
                "processing_time": 0.1,
                "successful_timeframes": successful_timeframes,
                "failed_timeframes": [],
                "mock_data": True
            }

            self.logger.info(f"Successfully generated mock market data for {symbol} with {len(successful_timeframes)} timeframes")
            return mock_data

        except Exception as e:
            self.logger.error(f"Failed to generate mock market data for {symbol}: {e}")
            return {"error": "MOCK_DATA_FAILED", "symbol": symbol}

    def _get_fallback_data(self, symbol: str, error_type: str = "UNKNOWN") -> Dict[str, Any]:
        """Get fallback minimal data when all else fails"""
        return {
            "symbol": symbol,
            "current_price": 0,
            "ticker": {},
            "orderbook": {},
            "recent_trades": [],
            "klines": [],
            "indicators": {},
            "account": {},
            "technical_analysis": {},
            "volume_profile": {},
            "market_sentiment": {"overall_sentiment": "neutral", "sentiment_score": 0.0},
            "data_status": "MINIMAL_FALLBACK",
            "error_type": error_type,
            "timestamp": int(time.time() * 1000),
            "processing_time": 0,
            "successful_timeframes": [],
            "failed_timeframes": []
        }

    async def close(self):
        """Close all connections"""
        try:
            # Close PostgreSQL connection pool
            if self.pg_pool:
                await self.pg_pool.close()
                self.logger.info("PostgreSQL connection pool closed")

            # Close Redis connection
            if self.redis_client:
                self.redis_client.close()
                self.logger.info("Redis connection closed")

            # Close WebSocket client
            if self.ws_client:
                await self.ws_client.disconnect()
                self.logger.info("WebSocket client closed")

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

    def start_websocket(self):
        """Start WebSocket monitoring in a non-blocking way"""
        try:
            # Initialize WebSocket client
            self.ws_client = OKXWebSocketClient(self.redis_client)
            self.logger.info("WebSocket client initialized")

            # Start WebSocket client in background
            self.logger.info("Starting WebSocket monitoring...")
            self.ws_client.start()

        except Exception as e:
            self.logger.error(f"Failed to start WebSocket monitoring: {e}")
            # Don't raise exception - allow service to continue without WebSocket
            self.logger.warning("Continuing without WebSocket monitoring...")

    def get_historical_klines(self, symbol: str, timeframe: str, limit: int = 1000,
                            since: Optional[int] = None, use_demo: bool = False) -> List[List]:
        """
        获取历史K线数据，支持多时间框架和智能采样

        Args:
            symbol: 交易对符号
            timeframe: 时间框架 (5m, 15m, 1h, 4h, 1d)
            limit: 获取数量限制
            since: 开始时间戳（毫秒）
            use_demo: 是否使用模拟环境

        Returns:
            List of OHLCV data: [[timestamp, open, high, low, close, volume], ...]
        """
        try:
            self.logger.info(f"Fetching historical klines for {symbol} {timeframe}, limit={limit}")

            # 检查缓存中是否有历史数据
            cache_key = f"historical_klines:{symbol}:{timeframe}"
            cached_data = self._get_cached_historical_data(cache_key, since, limit)

            if cached_data:
                self.logger.info(f"Found cached historical data for {symbol} {timeframe}: {len(cached_data)} candles")
                return cached_data

            # 从交易所API获取数据
            rest_client = RESTClient(use_demo=use_demo)

            # 计算时间范围
            if not since:
                # 根据时间框架和数量计算开始时间
                timeframe_minutes = self._timeframe_to_minutes(timeframe)
                since = int((time.time() - timeframe_minutes * limit * 60) * 1000)

            # 分批获取数据以避免API限制
            all_klines = []
            batch_size = 500  # 每批获取500个K线
            current_since = since

            while len(all_klines) < limit:
                batch_limit = min(batch_size, limit - len(all_klines))

                try:
                    batch_klines = rest_client.fetch_ohlcv(symbol, timeframe, batch_limit, current_since)

                    if not batch_klines:
                        self.logger.warning(f"No more historical data available for {symbol} {timeframe}")
                        break

                    # 数据去重和验证
                    combined_klines = self._deduplicate_klines(all_klines + batch_klines)
                    # 只取新的数据
                    new_klines = combined_klines[len(all_klines):]
                    all_klines.extend(new_klines)

                    # 更新下次获取的开始时间
                    if batch_klines:
                        current_since = batch_klines[-1][0] + 1  # 下一个时间点

                    self.logger.info(f"Fetched batch for {symbol} {timeframe}: {len(new_klines)} new candles, total: {len(all_klines)}")

                    # 避免API频率限制
                    time.sleep(0.1)

                except Exception as e:
                    self.logger.error(f"Failed to fetch batch for {symbol} {timeframe}: {e}")
                    break

            # 智能采样：保留关键转折点
            if len(all_klines) > limit:
                all_klines = self._smart_sampling(all_klines, limit)

            # 缓存历史数据
            self._cache_historical_data(cache_key, all_klines, timeframe)

            self.logger.info(f"Successfully fetched historical data for {symbol} {timeframe}: {len(all_klines)} candles")
            return all_klines

        except Exception as e:
            self.logger.error(f"Failed to get historical klines for {symbol} {timeframe}: {e}")
            return []

    def get_multi_timeframe_data(self, symbol: str, timeframes: List[str] = None,
                                limit: int = 500, use_demo: bool = False) -> Dict[str, List[List]]:
        """
        获取多时间框架数据，实现分层存储策略

        Args:
            symbol: 交易对符号
            timeframes: 时间框架列表，默认为 ["5m", "15m", "1h", "4h"]
            limit: 每个时间框架的数据量
            use_demo: 是否使用模拟环境

        Returns:
            Dict: {timeframe: OHLCV data}
        """
        if timeframes is None:
            timeframes = ["5m", "15m", "1h", "4h"]

        try:
            self.logger.info(f"Fetching multi-timeframe data for {symbol}: {timeframes}")

            multi_data = {}
            successful_timeframes = []
            failed_timeframes = []

            # 按优先级顺序获取数据（细粒度优先）
            for timeframe in timeframes:
                try:
                    # 根据时间框架调整数据量
                    timeframe_limit = self._adjust_limit_by_timeframe(limit, timeframe)

                    klines = self.get_historical_klines(
                        symbol, timeframe, timeframe_limit, use_demo=use_demo
                    )

                    if klines:
                        multi_data[timeframe] = klines
                        successful_timeframes.append(timeframe)
                        self.logger.info(f"Successfully got {timeframe} data for {symbol}: {len(klines)} candles")
                    else:
                        failed_timeframes.append(timeframe)
                        self.logger.warning(f"No data available for {symbol} {timeframe}")

                except Exception as e:
                    failed_timeframes.append(timeframe)
                    self.logger.error(f"Failed to get {timeframe} data for {symbol}: {e}")

            # 记录获取结果
            if successful_timeframes:
                self.logger.info(f"Multi-timeframe data fetch completed for {symbol}: {successful_timeframes}")
            if failed_timeframes:
                self.logger.warning(f"Failed timeframes for {symbol}: {failed_timeframes}")

            return multi_data

        except Exception as e:
            self.logger.error(f"Failed to get multi-timeframe data for {symbol}: {e}")
            return {}

    def get_historical_with_indicators(self, symbol: str, timeframes: List[str] = None,
                                     limit: int = 200, use_demo: bool = False) -> Dict[str, Any]:
        """
        获取历史数据并计算技术指标，避免重复计算

        Args:
            symbol: 交易对符号
            timeframes: 时间框架列表
            limit: 数据量限制
            use_demo: 是否使用模拟环境

        Returns:
            Dict: 包含OHLCV数据和技术指标的完整数据结构
        """
        try:
            self.logger.info(f"Getting historical data with indicators for {symbol}")

            # 获取多时间框架数据
            multi_timeframe_data = self.get_multi_timeframe_data(
                symbol, timeframes, limit, use_demo
            )

            if not multi_timeframe_data:
                self.logger.warning(f"No historical data available for {symbol}")
                return {"error": "No historical data available"}

            # 计算技术指标（统一计算，避免重复）
            historical_analysis = {}
            successful_calculations = []
            failed_calculations = []

            for timeframe, klines in multi_timeframe_data.items():
                try:
                    if klines and len(klines) >= 10:  # 最少需要10个K线
                        indicators = TechnicalIndicators.calculate_all_indicators(klines)
                        historical_analysis[timeframe] = {
                            "ohlcv": klines,
                            "indicators": indicators,
                            "data_points": len(klines),
                            "timeframe": timeframe,
                            "latest_timestamp": klines[-1][0] if klines else None
                        }
                        successful_calculations.append(timeframe)
                    else:
                        failed_calculations.append(timeframe)
                        self.logger.warning(f"Insufficient data for {symbol} {timeframe}: {len(klines)} candles")

                except Exception as e:
                    failed_calculations.append(timeframe)
                    self.logger.error(f"Failed to calculate indicators for {symbol} {timeframe}: {e}")

            # 添加元数据
            result = {
                "symbol": symbol,
                "historical_analysis": historical_analysis,
                "successful_timeframes": successful_calculations,
                "failed_timeframes": failed_calculations,
                "total_timeframes": len(timeframes) if timeframes else 4,
                "data_freshness": int(time.time() * 1000),
                "use_demo": use_demo
            }

            self.logger.info(f"Historical analysis completed for {symbol}: {len(successful_calculations)}/{len(timeframes) if timeframes else 4} timeframes")
            return result

        except Exception as e:
            self.logger.error(f"Failed to get historical data with indicators for {symbol}: {e}")
            return {"error": str(e)}

    def _timeframe_to_minutes(self, timeframe: str) -> int:
        """将时间框架转换为分钟数"""
        timeframe_map = {
            "1m": 1, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480, "12h": 720,
            "1d": 1440, "3d": 4320, "1w": 10080
        }
        return timeframe_map.get(timeframe, 5)  # 默认5分钟

    def _adjust_limit_by_timeframe(self, base_limit: int, timeframe: str) -> int:
        """根据时间框架调整数据量限制"""
        timeframe_minutes = self._timeframe_to_minutes(timeframe)

        # 基于时间框架调整数据量，确保覆盖相似的时间范围
        if timeframe_minutes <= 15:  # 短时间框架
            return base_limit
        elif timeframe_minutes <= 60:  # 中时间框架
            return max(base_limit // 2, 100)
        elif timeframe_minutes <= 240:  # 长时间框架
            return max(base_limit // 4, 50)
        else:  # 超长时间框架
            return max(base_limit // 8, 30)

    def _deduplicate_klines(self, klines: List[List]) -> List[List]:
        """去除重复的K线数据"""
        if not klines:
            return []

        # 先按时间戳排序
        sorted_klines = sorted(klines, key=lambda x: x[0])

        # 按时间戳去重，保留最新的数据
        seen_timestamps = set()
        deduplicated = []

        for kline in sorted_klines:
            timestamp = kline[0]
            if timestamp not in seen_timestamps:
                seen_timestamps.add(timestamp)
                deduplicated.append(kline)

        return deduplicated

    def _smart_sampling(self, klines: List[List], target_count: int) -> List[List]:
        """智能采样：保留关键转折点"""
        if len(klines) <= target_count:
            return klines

        try:
            import numpy as np

            # 计算价格变化率
            closes = np.array([kline[4] for kline in klines])  # 收盘价
            volumes = np.array([kline[5] for kline in klines])  # 成交量

            # 计算价格变化幅度
            price_changes = np.abs(np.diff(closes))
            volume_changes = np.abs(np.diff(volumes))

            # 综合变化分数（价格变化 + 成交量变化）
            change_scores = price_changes + volume_changes * 0.1  # 成交量权重较低

            # 总是需要包含第一个和最后一个K线
            important_indices = {0, len(klines) - 1}

            # 选择变化最大的点
            remaining_slots = target_count - 2  # 减去首尾两个固定点
            if remaining_slots > 0:
                # 获取变化最大的点的索引
                top_indices = np.argsort(change_scores)[-remaining_slots:]
                important_indices.update(top_indices + 1)  # +1 因为diff减少了长度

            # 按时间顺序排序并返回
            sorted_indices = sorted(important_indices)
            sampled_klines = [klines[i] for i in sorted_indices]

            # 确保返回正确数量的数据
            if len(sampled_klines) > target_count:
                sampled_klines = sampled_klines[:target_count]
            elif len(sampled_klines) < target_count:
                # 如果采样数据不足，用均匀采样补充
                needed = target_count - len(sampled_klines)
                step = max(1, len(klines) // needed)
                additional = [klines[i] for i in range(1, len(klines)-1, step) if i not in important_indices]
                sampled_klines.extend(additional[:needed])
                sampled_klines = sorted(sampled_klines, key=lambda x: x[0])[:target_count]

            self.logger.info(f"Smart sampling: {len(klines)} -> {len(sampled_klines)} klines")
            return sampled_klines

        except Exception as e:
            self.logger.warning(f"Smart sampling failed, using simple sampling: {e}")
            # 回退到简单均匀采样
            step = max(1, len(klines) // target_count)
            return klines[::step][:target_count]

    def _get_cached_historical_data(self, cache_key: str, since: Optional[int], limit: int) -> Optional[List[List]]:
        """从缓存获取历史数据"""
        if not self.redis_client:
            return None

        try:
            cached = self.redis_client.get(cache_key)
            if not cached:
                return None

            cache_data = json.loads(cached)
            cached_klines = cache_data.get("klines", [])

            if not cached_klines:
                return None

            # 检查数据新鲜度
            cache_time = cache_data.get("timestamp", 0)
            current_time = int(time.time() * 1000)

            # 根据时间框架设置不同的缓存有效期
            timeframe = cache_key.split(":")[-1]
            cache_duration = self._get_cache_duration(timeframe)

            if current_time - cache_time > cache_duration:
                self.logger.info(f"Cached data expired for {cache_key}")
                return None

            # 如果指定了开始时间，过滤数据
            if since:
                filtered_klines = [k for k in cached_klines if k[0] >= since]
                if len(filtered_klines) >= limit:
                    return filtered_klines[-limit:]

            # 返回最新的数据
            return cached_klines[-limit:] if len(cached_klines) >= limit else cached_klines

        except Exception as e:
            self.logger.warning(f"Failed to get cached historical data: {e}")
            return None

    def _cache_historical_data(self, cache_key: str, klines: List[List], timeframe: str):
        """缓存历史数据"""
        if not self.redis_client:
            return  # Skip caching if Redis is not available

        try:
            cache_data = {
                "klines": klines,
                "timestamp": int(time.time() * 1000),
                "timeframe": timeframe,
                "count": len(klines)
            }

            # 根据时间框架设置缓存过期时间
            cache_duration = self._get_cache_duration(timeframe) // 1000  # 转换为秒

            self.redis_client.setex(cache_key, cache_duration, json.dumps(cache_data))
            self.logger.info(f"Cached historical data for {cache_key}: {len(klines)} klines, TTL: {cache_duration}s")

        except Exception as e:
            self.logger.error(f"Failed to cache historical data: {e}")

    def _get_cache_duration(self, timeframe: str) -> int:
        """获取缓存持续时间（毫秒）- 优化版本"""
        # 使用优化的缓存策略
        if hasattr(self, 'OPTIMIZED_CACHE_DURATION') and timeframe in self.OPTIMIZED_CACHE_DURATION:
            return self.OPTIMIZED_CACHE_DURATION[timeframe] * 1000

        # 回退到原有逻辑
        timeframe_minutes = self._timeframe_to_minutes(timeframe)

        # 短时间框架缓存时间较短，长时间框架缓存时间较长
        if timeframe_minutes <= 15:
            return 5 * 60 * 1000  # 5分钟
        elif timeframe_minutes <= 60:
            return 15 * 60 * 1000  # 15分钟
        elif timeframe_minutes <= 240:
            return 30 * 60 * 1000  # 30分钟
        else:
            return 60 * 60 * 1000  # 1小时

    def _get_smart_cache_duration(self, timeframe: str, data_age: int = 0) -> int:
        """根据数据新鲜度智能调整缓存时间"""
        base_duration = self._get_cache_duration(timeframe)

        # 如果数据较旧，减少缓存时间
        if data_age > 3600000:  # 1小时
            return base_duration // 2

        # 如果是高频交易时间，减少缓存时间
        current_hour = time.localtime().tm_hour
        if 9 <= current_hour <= 16:  # 交易活跃时间
            return base_duration // 2

        return base_duration
    def get_account_balance(self, use_demo: bool = False) -> Dict[str, Any]:
        """Get account balance from OKX"""
        try:
            self.logger.info(f"[{self.data_source_label}] 获取账户余额 (use_demo={use_demo})")

            # 如果是Mock数据模式，返回模拟余额
            if self.data_source_type == "MOCK_DATA":
                return self._generate_mock_balance()

            # 初始化REST客户端
            rest_client = RESTClient(use_demo=use_demo)

            # 获取账户余额
            balance_data = rest_client.fetch_balance()

            if balance_data:
                self.logger.info(f"[{self.data_source_label}] 成功获取账户余额")
                return {
                    "balance": balance_data,
                    "use_demo": use_demo,
                    "data_source": self.data_source_label,
                    "timestamp": int(time.time() * 1000),
                    "status": "success"
                }
            else:
                self.logger.error(f"[{self.data_source_label}] 获取账户余额失败")
                return {
                    "error": "Failed to fetch balance",
                    "use_demo": use_demo,
                    "data_source": self.data_source_label,
                    "timestamp": int(time.time() * 1000),
                    "status": "error"
                }

        except Exception as e:
            self.logger.error(f"[{self.data_source_label}] 获取账户余额异常: {e}")
            return {
                "error": str(e),
                "use_demo": use_demo,
                "data_source": self.data_source_label,
                "timestamp": int(time.time() * 1000),
                "status": "error"
            }

    def get_account_positions(self, use_demo: bool = False) -> Dict[str, Any]:
        """Get account positions from OKX"""
        try:
            self.logger.info(f"[{self.data_source_label}] 获取账户持仓 (use_demo={use_demo})")

            # 如果是Mock数据模式，返回模拟持仓
            if self.data_source_type == "MOCK_DATA":
                return self._generate_mock_positions()

            # 初始化REST客户端
            rest_client = RESTClient(use_demo=use_demo)

            # 获取账户持仓
            positions_data = rest_client.fetch_positions()

            if positions_data:
                self.logger.info(f"[{self.data_source_label}] 成功获取账户持仓: {len(positions_data)} 个持仓")
                return {
                    "positions": positions_data,
                    "count": len(positions_data),
                    "use_demo": use_demo,
                    "data_source": self.data_source_label,
                    "timestamp": int(time.time() * 1000),
                    "status": "success"
                }
            else:
                self.logger.error(f"[{self.data_source_label}] 获取账户持仓失败")
                return {
                    "error": "Failed to fetch positions",
                    "use_demo": use_demo,
                    "data_source": self.data_source_label,
                    "timestamp": int(time.time() * 1000),
                    "status": "error"
                }

        except Exception as e:
            self.logger.error(f"[{self.data_source_label}] 获取账户持仓异常: {e}")
            return {
                "error": str(e),
                "use_demo": use_demo,
                "data_source": self.data_source_label,
                "timestamp": int(time.time() * 1000),
                "status": "error"
            }

    def _generate_mock_balance(self) -> Dict[str, Any]:
        """生成模拟账户余额数据"""
        import random

        mock_balance = {
            "info": {"mock": True},
            "free": {
                "USDT": random.uniform(10000, 50000),
                "BTC": random.uniform(0.1, 1.0),
                "ETH": random.uniform(1.0, 10.0)
            },
            "used": {
                "USDT": random.uniform(0, 5000),
                "BTC": random.uniform(0, 0.1),
                "ETH": random.uniform(0, 1.0)
            },
            "total": {}
        }

        # 计算总额
        for currency in mock_balance["free"]:
            mock_balance["total"][currency] = (
                mock_balance["free"][currency] + mock_balance["used"].get(currency, 0)
            )

        return {
            "balance": mock_balance,
            "use_demo": True,
            "data_source": self.data_source_label,
            "timestamp": int(time.time() * 1000),
            "status": "mock_success"
        }

    def _generate_mock_positions(self) -> Dict[str, Any]:
        """生成模拟账户持仓数据"""
        import random

        mock_positions = [
            {
                "info": {"mock": True},
                "id": f"mock_pos_{int(time.time())}",
                "symbol": "BTC-USDT",
                "side": "long" if random.random() > 0.5 else "short",
                "size": random.uniform(0.001, 0.1),
                "contracts": random.uniform(0.001, 0.1),
                "contractSize": 0.001,
                "unrealizedPnl": random.uniform(-100, 100),
                "leverage": random.uniform(1, 10),
                "entryPrice": random.uniform(45000, 55000),
                "markPrice": random.uniform(45000, 55000),
                "liquidationPrice": random.uniform(40000, 43000) if random.random() > 0.5 else None,
                "percentage": random.uniform(-5, 5),
                "timestamp": int(time.time() * 1000)
            }
        ]

        # 随机决定是否有持仓
        if random.random() > 0.7:  # 30%概率有持仓
            mock_positions = []

        return {
            "positions": mock_positions,
            "count": len(mock_positions),
            "use_demo": True,
            "data_source": self.data_source_label,
            "timestamp": int(time.time() * 1000),
            "status": "mock_success"
        }

    def stop(self):
        """Stop data handler"""
        self.logger.info("Stopping data handler...")
        self._stop_event.set()

        # Stop WebSocket client if it exists
        if self.ws_client:
            try:
                self.ws_client.stop()
                self.logger.info("WebSocket client stopped")
            except Exception as e:
                self.logger.error(f"Error stopping WebSocket client: {e}")
