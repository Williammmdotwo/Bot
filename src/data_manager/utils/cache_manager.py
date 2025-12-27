"""
缓存管理器模块
负责 Redis 缓存的管理和优化策略
"""

import json
import time
import logging
from typing import Dict, Any, List, Optional
import redis


class CacheManager:
    """缓存管理器 - 优化 Redis 缓存策略"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self.logger = logging.getLogger(__name__)
        
        # 优化的缓存持续时间配置
        self.OPTIMIZED_CACHE_DURATION = {
            "1m": 180,      # 3分钟
            "5m": 900,      # 15分钟
            "15m": 1800,    # 30分钟
            "1h": 3600,     # 1小时
            "4h": 7200,     # 2小时
            "1d": 14400     # 4小时
        }
        
        self.logger.info("CacheManager 初始化完成")
    
    def get_market_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """从缓存获取市场数据"""
        try:
            cache_key = f"market_data:{symbol}:v2"
            cached = self.redis_client.get(cache_key)
            
            if cached:
                cache_data = json.loads(cached)
                self.logger.debug(f"从缓存获取 {symbol} 市场数据成功")
                return cache_data.get("data")
            
            return None
            
        except Exception as e:
            self.logger.warning(f"获取 {symbol} 缓存数据失败: {e}")
            return None
    
    def cache_market_data(self, symbol: str, data: Dict[str, Any]):
        """缓存市场数据"""
        try:
            timestamp = int(time.time())
            
            # 缓存综合市场数据（版本控制）
            cache_key = f"market_data:{symbol}:v2"
            cache_data = {
                "data": data,
                "timestamp": timestamp,
                "version": "2.0",
                "symbol": symbol
            }
            self.redis_client.setex(cache_key, 300, json.dumps(cache_data))  # 缓存5分钟
            
            # 缓存技术分析数据
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
            
            # 缓存 OHLCV 数据
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
                    # OHLCV 数据缓存更长时间
                    cache_duration = self._get_cache_duration(timeframe)
                    self.redis_client.setex(ohlcv_key, cache_duration, json.dumps(ohlcv_cache))
            
            # 缓存市场情绪
            sentiment_data = data.get("market_sentiment", {})
            if sentiment_data:
                sentiment_key = f"market_sentiment:{symbol}:v2"
                sentiment_cache = {
                    "data": sentiment_data,
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "version": "2.0"
                }
                self.redis_client.setex(sentiment_key, 180, json.dumps(sentiment_cache))  # 3分钟
            
            self.logger.info(f"成功缓存 {symbol} 市场数据，包含 {len(ohlcv_data)} 个时间框架")
            
        except Exception as e:
            self.logger.error(f"缓存 {symbol} 市场数据失败: {e}")
    
    def get_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取市场快照"""
        try:
            # 从 Redis 获取最新的 K 线数据
            redis_key = f"ohlcv:{symbol}:5m"
            latest_data = self.redis_client.zrevrange(redis_key, 0, 49)  # 获取最新50根K线
            
            # 安全处理K线数据
            klines = []
            if latest_data:
                for data in latest_data:
                    try:
                        if isinstance(data, (str, bytes)):
                            klines.append(json.loads(data))
                        else:
                            klines.append(data)
                    except (json.JSONDecodeError, TypeError) as e:
                        self.logger.warning(f"解析K线数据失败: {e}")
                        continue

            # 获取最新指标数据
            indicators_key = f"indicators:{symbol}:5m"
            indicators_raw = self.redis_client.get(indicators_key) or "{}"
            try:
                indicators = json.loads(indicators_raw) if isinstance(indicators_raw, (str, bytes)) else indicators_raw
            except (json.JSONDecodeError, TypeError):
                indicators = {}

            # 获取账户状态
            account_key = f"account:status"
            account_raw = self.redis_client.get(account_key) or "{}"
            try:
                account = json.loads(account_raw) if isinstance(account_raw, (str, bytes)) else account_raw
            except (json.JSONDecodeError, TypeError):
                account = {}

            snapshot = {
                "symbol": symbol,
                "klines": klines,
                "indicators": indicators,
                "account": account,
                "data_status": "OK"
            }

            # 检查指标是否就绪
            if not self._check_indicators_ready(symbol):
                snapshot["data_status"] = "INDICATORS_NOT_READY"

            self.logger.info(f"从 Redis 成功获取 {symbol} 快照")
            return snapshot

        except Exception as e:
            self.logger.warning(f"从 Redis 获取 {symbol} 快照失败: {e}")
            return None
    
    def _check_indicators_ready(self, symbol: str) -> bool:
        """检查指标是否就绪"""
        try:
            test_symbol = symbol or "BTC-USDT"
            redis_key = f"ohlcv:{test_symbol}:5m"
            latest_data = self.redis_client.zrevrange(redis_key, 0, 0)
            return len(latest_data) > 0
        except Exception:
            return False
    
    def get_historical_data(self, symbol: str, timeframe: str, since: Optional[int] = None, limit: int = 1000) -> Optional[List[List]]:
        """获取历史数据"""
        try:
            cache_key = f"historical_klines:{symbol}:{timeframe}"
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
            cache_duration = self._get_cache_duration(timeframe)
            
            if current_time - cache_time > cache_duration:
                self.logger.info(f"{cache_key} 缓存数据已过期")
                return None
            
            # 如果指定了开始时间，过滤数据
            if since:
                filtered_klines = [k for k in cached_klines if k[0] >= since]
                if len(filtered_klines) >= limit:
                    return filtered_klines[-limit:]
                else:
                    return filtered_klines
            
            # 返回最新的数据
            return cached_klines[-limit:] if len(cached_klines) >= limit else cached_klines
            
        except Exception as e:
            self.logger.warning(f"获取历史缓存数据失败: {e}")
            return None
    
    def cache_historical_data(self, symbol: str, timeframe: str, klines: List[List]):
        """缓存历史数据"""
        try:
            cache_key = f"historical_klines:{symbol}:{timeframe}"
            cache_data = {
                "klines": klines,
                "timestamp": int(time.time() * 1000),
                "timeframe": timeframe,
                "count": len(klines)
            }
            
            # 根据时间框架设置缓存过期时间
            cache_duration = self._get_cache_duration(timeframe) // 1000  # 转换为秒
            
            self.redis_client.setex(cache_key, cache_duration, json.dumps(cache_data))
            self.logger.info(f"缓存历史数据 {cache_key}: {len(klines)} 根K线，TTL: {cache_duration}s")
            
        except Exception as e:
            self.logger.error(f"缓存历史数据失败: {e}")
    
    def _get_cache_duration(self, timeframe: str) -> int:
        """获取缓存持续时间（毫秒）"""
        # 使用优化的缓存策略
        if timeframe in self.OPTIMIZED_CACHE_DURATION:
            return self.OPTIMIZED_CACHE_DURATION[timeframe] * 1000
        
        # 回退到默认逻辑
        timeframe_minutes = self._timeframe_to_minutes(timeframe)
        
        if timeframe_minutes <= 15:
            return 5 * 60 * 1000  # 5分钟
        elif timeframe_minutes <= 60:
            return 15 * 60 * 1000  # 15分钟
        elif timeframe_minutes <= 240:
            return 30 * 60 * 1000  # 30分钟
        else:
            return 60 * 60 * 1000  # 1小时
    
    def _timeframe_to_minutes(self, timeframe: str) -> int:
        """将时间框架转换为分钟数"""
        timeframe_map = {
            "1m": 1, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480, "12h": 720,
            "1d": 1440, "3d": 4320, "1w": 10080
        }
        return timeframe_map.get(timeframe, 5)  # 默认5分钟
    
    def get_smart_cache_duration(self, timeframe: str, data_age: int = 0) -> int:
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
    
    def invalidate_symbol_cache(self, symbol: str):
        """清除指定交易对的所有缓存"""
        try:
            # 获取所有相关的缓存键
            pattern = f"*:{symbol}:*"
            keys = self.redis_client.keys(pattern)
            
            if keys:
                self.redis_client.delete(*keys)
                self.logger.info(f"清除 {symbol} 的 {len(keys)} 个缓存键")
            
        except Exception as e:
            self.logger.error(f"清除 {symbol} 缓存失败: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            info = self.redis_client.info()
            
            return {
                "used_memory": info.get("used_memory_human", "N/A"),
                "used_memory_peak": info.get("used_memory_peak_human", "N/A"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0)
            }
            
        except Exception as e:
            self.logger.error(f"获取缓存统计失败: {e}")
            return {}
