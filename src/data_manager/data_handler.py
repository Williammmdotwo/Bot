"""
数据处理器核心模块
负责数据处理的核心逻辑，从 main.py 中拆分出来
"""

import redis
import logging
import asyncio
import asyncpg
import json
import os
import time
import traceback
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

from .clients.websocket_client import OKXWebSocketClient
from .clients.rest_client import RESTClient
from .core.technical_indicators import TechnicalIndicators
from .utils.cache_manager import CacheManager
from .core.market_data_fetcher import MarketDataFetcher
from .utils.service_degradation import ServiceDegradationManager


class DataHandler:
    """数据处理器 - 负责市场数据的获取、处理和缓存"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._stop_event = None

        # 初始化组件
        self._init_rest_client()
        self._init_redis_connection()
        self._init_database_connection()

        # 初始化管理器
        self.cache_manager = CacheManager(self.redis_client)
        self.market_fetcher = MarketDataFetcher(self.rest_client)
        self.degradation_manager = ServiceDegradationManager(self.rest_client)

        # WebSocket 客户端将在 start 方法中初始化
        self.ws_client = None

        self.logger.info("DataHandler 初始化完成")

    def _init_rest_client(self):
        """初始化 REST 客户端"""
        try:
            okx_environment = os.getenv("OKX_ENVIRONMENT", "production").lower()
            use_demo = okx_environment in ["demo"]
            self.rest_client = RESTClient(use_demo=use_demo)
            self.logger.info(f"REST 客户端初始化成功 (使用 {okx_environment} 环境)")
        except Exception as e:
            self.logger.error(f"REST 客户端初始化失败: {e}")
            raise

    def _init_redis_connection(self):
        """初始化 Redis 连接"""
        try:
            # 尝试 REDIS_URL (Docker 环境)
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                self.redis_client = self._connect_redis_via_url(redis_url)
            else:
                self.redis_client = self._connect_redis_via_env_vars()

            # 测试连接
            self.redis_client.ping()
            self.logger.info("Redis 连接测试成功")

        except Exception as e:
            self.logger.error(f"Redis 连接失败: {e}")
            raise

    def _connect_redis_via_url(self, redis_url: str) -> redis.Redis:
        """通过 URL 连接 Redis"""
        import re
        match = re.match(r'redis://:(?P<password>[^@]*)@(?P<host>[^:]+):(?P<port>\d+)', redis_url)
        if match:
            return redis.Redis(
                host=match.group('host'),
                port=int(match.group('port')),
                password=match.group('password'),
                decode_responses=True
            )
        else:
            return redis.Redis.from_url(redis_url, decode_responses=True)

    def _connect_redis_via_env_vars(self) -> redis.Redis:
        """通过环境变量连接 Redis"""
        # 从配置管理器获取Redis配置
        try:
            from src.utils.config_loader import get_config_manager
            config_manager = get_config_manager()
            config = config_manager.get_config()
            redis_config = config['redis']
            redis_host = os.getenv("REDIS_HOST", redis_config['host'])
            redis_port = os.getenv("REDIS_PORT", str(redis_config['port']))
        except Exception:
            # 回退到环境变量或默认值
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = os.getenv("REDIS_PORT", "6379")
        redis_password = os.getenv("REDIS_PASSWORD")

        if redis_password:
            return redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                decode_responses=True
            )
        else:
            return redis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True
            )

    def _init_database_connection(self):
        """初始化数据库连接"""
        self.pg_pool = None
        use_database = os.getenv('USE_DATABASE', 'false').lower() == 'true'

        if use_database:
            try:
                postgres_db = os.getenv("POSTGRES_DB")
                postgres_user = os.getenv("POSTGRES_USER")
                postgres_password = os.getenv("POSTGRES_PASSWORD")
                postgres_host = os.getenv("POSTGRES_HOST", "localhost")
                postgres_port = os.getenv("POSTGRES_PORT", "5432")

                if all([postgres_db, postgres_user, postgres_password]):
                    self.pg_pool = asyncio.run(self._create_pg_pool(
                        postgres_host, postgres_port, postgres_db,
                        postgres_user, postgres_password
                    ))
                    self.logger.info(f"PostgreSQL 数据库连接成功: {postgres_db}")
                else:
                    self.logger.warning("数据库凭据不完整，跳过数据库连接")

            except Exception as e:
                self.logger.error(f"PostgreSQL 连接失败: {e}")
                self.pg_pool = None
        else:
            self.logger.info("数据库功能已禁用 (USE_DATABASE=false)")

    async def _create_pg_pool(self, host: str, port: str, database: str,
                            user: str, password: str) -> asyncpg.Pool:
        """创建 PostgreSQL 连接池"""
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

    def get_comprehensive_market_data(self, symbol: str, use_demo: bool = False) -> Dict[str, Any]:
        """获取综合市场数据，包含技术分析"""
        start_time = time.time()

        try:
            self.logger.info(f"获取 {symbol} 的综合市场数据")

            # 尝试从缓存获取
            cached_data = self.cache_manager.get_market_data(symbol)
            if cached_data:
                self.logger.info(f"从缓存获取 {symbol} 数据成功")
                return cached_data

            # 从市场获取数据
            market_data = self.market_fetcher.get_comprehensive_market_data(symbol, use_demo)
            if not market_data:
                return self._get_fallback_data(symbol, "MARKET_DATA_UNAVAILABLE")

            # 计算技术指标
            technical_analysis = self._calculate_technical_indicators(market_data)

            # 分析市场情绪
            market_sentiment = self._calculate_market_sentiment(market_data, technical_analysis)

            # 构建综合数据
            comprehensive_data = {
                "symbol": symbol,
                "current_price": market_data.get("current_price", 0),
                "ticker": market_data.get("ticker", {}),
                "orderbook": market_data.get("orderbook", {}),
                "recent_trades": market_data.get("recent_trades", []),
                "technical_analysis": technical_analysis,
                "volume_profile": market_data.get("volume_profile", {}),
                "market_sentiment": market_sentiment,
                "timestamp": market_data.get("timestamp", int(time.time() * 1000)),
                "use_demo": use_demo,
                "data_status": "COMPREHENSIVE",
                "processing_time": time.time() - start_time
            }

            # 缓存数据
            self.cache_manager.cache_market_data(symbol, comprehensive_data)

            processing_time = time.time() - start_time
            self.logger.info(f"{symbol} 市场数据处理完成，耗时 {processing_time:.2f}s")

            return comprehensive_data

        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(f"获取 {symbol} 综合市场数据失败，耗时 {processing_time:.2f}s: {e}")
            self.logger.debug(traceback.format_exc())
            return self._get_fallback_data(symbol, "CRITICAL_ERROR")

    def _calculate_technical_indicators(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """计算技术指标"""
        technical_analysis = {}
        successful_timeframes = []
        failed_timeframes = []

        ohlcv_data = market_data.get("ohlcv", {})
        for tf, candles in ohlcv_data.items():
            try:
                if candles:
                    technical_analysis[tf] = TechnicalIndicators.calculate_all_indicators(candles)
                    successful_timeframes.append(tf)
                else:
                    self.logger.warning(f"{tf} 时间框架没有 OHLCV 数据")
                    failed_timeframes.append(tf)
            except Exception as e:
                self.logger.error(f"计算 {tf} 技术指标失败: {e}")
                failed_timeframes.append(tf)

        # 记录处理结果
        if successful_timeframes:
            self.logger.info(f"成功计算技术指标: {successful_timeframes}")
        if failed_timeframes:
            self.logger.warning(f"技术指标计算失败: {failed_timeframes}")

        return technical_analysis

    def _calculate_market_sentiment(self, market_info: Dict, technical_analysis: Dict) -> Dict[str, Any]:
        """计算市场情绪"""
        try:
            orderbook = market_info.get("orderbook", {})
            recent_trades = market_info.get("recent_trades", [])

            # 分析订单簿不平衡
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])

            total_bid_volume = sum(bid[1] for bid in bids[:5]) if len(bids) >= 5 else 0
            total_ask_volume = sum(ask[1] for ask in asks[:5]) if len(asks) >= 5 else 0

            orderbook_imbalance = (total_bid_volume - total_ask_volume) / (total_bid_volume + total_ask_volume) if (total_bid_volume + total_ask_volume) > 0 else 0

            # 分析交易方向
            buy_volume = sum(trade.get("amount", 0) for trade in recent_trades if trade.get("side") == "buy")
            sell_volume = sum(trade.get("amount", 0) for trade in recent_trades if trade.get("side") == "sell")

            trade_imbalance = (buy_volume - sell_volume) / (buy_volume + sell_volume) if (buy_volume + sell_volume) > 0 else 0

            # 获取技术情绪
            tf_5m = technical_analysis.get("5m", {})
            momentum = tf_5m.get("momentum", "neutral")
            trend = tf_5m.get("trend", "sideways")

            # 综合情绪分数
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
            self.logger.warning(f"计算市场情绪失败: {e}")
            return {"overall_sentiment": "neutral", "sentiment_score": 0.0}

    def get_snapshot(self, symbol: str) -> Dict[str, Any]:
        """获取市场快照，支持服务降级"""
        try:
            # 尝试从 Redis 获取快照
            snapshot = self.cache_manager.get_snapshot(symbol)
            if snapshot:
                return snapshot

            # 服务降级：从 REST 客户端获取
            return self.degradation_manager.get_degraded_snapshot(symbol)

        except Exception as e:
            self.logger.error(f"获取 {symbol} 快照失败: {e}")
            return {
                "symbol": symbol,
                "klines": [],
                "indicators": {},
                "account": {},
                "data_status": "ERROR"
            }

    def _get_fallback_data(self, symbol: str, error_type: str = "UNKNOWN") -> Dict[str, Any]:
        """获取最小回退数据"""
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

    def start_websocket(self):
        """启动 WebSocket 监控"""
        try:
            self.ws_client = OKXWebSocketClient(self.redis_client)
            self.logger.info("WebSocket 客户端初始化成功")

            self.logger.info("启动 WebSocket 监控...")
            self.ws_client.start()

        except Exception as e:
            self.logger.error(f"启动 WebSocket 监控失败: {e}")
            self.logger.warning("继续运行，不使用 WebSocket 监控...")

    def stop(self):
        """停止数据处理器"""
        self.logger.info("停止数据处理器...")
        if self._stop_event:
            self._stop_event.set()

        if self.ws_client:
            try:
                self.ws_client.stop()
                self.logger.info("WebSocket 客户端已停止")
            except Exception as e:
                self.logger.error(f"停止 WebSocket 客户端失败: {e}")

    async def close(self):
        """关闭所有连接"""
        try:
            # 关闭 PostgreSQL 连接池
            if self.pg_pool:
                await self.pg_pool.close()
                self.logger.info("PostgreSQL 连接池已关闭")

            # 关闭 Redis 连接
            if self.redis_client:
                self.redis_client.close()
                self.logger.info("Redis 连接已关闭")

            # 关闭 WebSocket 客户端
            if self.ws_client:
                await self.ws_client.disconnect()
                self.logger.info("WebSocket 客户端已关闭")

        except Exception as e:
            self.logger.error(f"关闭连接时出错: {e}")
