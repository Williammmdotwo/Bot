"""
服务降级管理器模块
负责在主服务不可用时提供降级服务
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional
from .rest_client import RESTClient


class ServiceDegradationManager:
    """服务降级管理器 - 提供服务降级功能"""
    
    def __init__(self, rest_client: RESTClient):
        self.rest_client = rest_client
        self.logger = logging.getLogger(__name__)
        self.logger.info("ServiceDegradationManager 初始化完成")
    
    def get_degraded_snapshot(self, symbol: str) -> Dict[str, Any]:
        """获取降级快照"""
        try:
            self.logger.info(f"为 {symbol} 执行服务降级")
            
            # 从 REST 客户端获取数据
            degraded_data = self._fetch_degraded_data_from_rest(symbol)
            
            if degraded_data:
                return {
                    "symbol": symbol,
                    "klines": degraded_data.get("klines", []),
                    "indicators": degraded_data.get("indicators", {}),
                    "account": degraded_data.get("account", {}),
                    "data_status": "DEGRADED"
                }
            else:
                return {
                    "symbol": symbol,
                    "klines": [],
                    "indicators": {},
                    "account": {},
                    "data_status": "ERROR"
                }
                
        except Exception as e:
            self.logger.error(f"获取 {symbol} 降级快照失败: {e}")
            return {
                "symbol": symbol,
                "klines": [],
                "indicators": {},
                "account": {},
                "data_status": "ERROR"
            }
    
    def _fetch_degraded_data_from_rest(self, symbol: str) -> Optional[Dict[str, Any]]:
        """从 REST 客户端获取降级数据"""
        try:
            # 获取最新的 OHLCV 数据用于回填
            since = int((time.time() - 300 * 50) * 1000)  # 最近50根K线（5分钟每根）
            ohlcv_data = self.rest_client.fetch_ohlcv(symbol, since, 50)
            
            # 转换 OHLCV 为期望格式
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
            
            # 获取账户状态
            balance = self.rest_client.fetch_balance()
            positions = self.rest_client.fetch_positions()
            account = {
                "balance": balance,
                "positions": positions
            }
            
            return {
                "klines": klines,
                "indicators": {},  # 降级模式下不计算复杂指标
                "account": account
            }
            
        except Exception as e:
            self.logger.error(f"从 REST 客户端获取降级数据失败: {e}")
            return None
    
    def get_fallback_market_data(self, symbol: str, error_type: str = "UNKNOWN") -> Dict[str, Any]:
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
    
    def try_partial_data_recovery(self, symbol: str) -> Dict[str, Any]:
        """尝试部分数据恢复"""
        try:
            self.logger.info(f"尝试 {symbol} 部分数据恢复")
            
            recovery_data = {
                "symbol": symbol,
                "recovered_components": [],
                "failed_components": [],
                "data_status": "PARTIAL_RECOVERY"
            }
            
            # 尝试恢复各个数据组件
            self._try_recover_ticker(symbol, recovery_data)
            self._try_recover_orderbook(symbol, recovery_data)
            self._try_recover_recent_trades(symbol, recovery_data)
            self._try_recover_basic_ohlcv(symbol, recovery_data)
            
            # 检查恢复结果
            if recovery_data["recovered_components"]:
                self.logger.info(f"{symbol} 部分数据恢复成功: {recovery_data['recovered_components']}")
                return recovery_data
            else:
                self.logger.warning(f"{symbol} 部分数据恢复失败")
                return self.get_fallback_market_data(symbol, "PARTIAL_RECOVERY_FAILED")
                
        except Exception as e:
            self.logger.error(f"{symbol} 部分数据恢复异常: {e}")
            return self.get_fallback_market_data(symbol, "PARTIAL_RECOVERY_ERROR")
    
    def _try_recover_ticker(self, symbol: str, recovery_data: Dict[str, Any]):
        """尝试恢复 ticker 数据"""
        try:
            ticker = self.rest_client.fetch_ticker(symbol)
            if ticker:
                recovery_data["ticker"] = ticker
                recovery_data["current_price"] = ticker.get("last", 0)
                recovery_data["recovered_components"].append("ticker")
                self.logger.info(f"成功恢复 {symbol} ticker 数据")
            else:
                recovery_data["failed_components"].append("ticker")
        except Exception as e:
            self.logger.warning(f"恢复 {symbol} ticker 数据失败: {e}")
            recovery_data["failed_components"].append("ticker")
    
    def _try_recover_orderbook(self, symbol: str, recovery_data: Dict[str, Any]):
        """尝试恢复订单簿数据"""
        try:
            orderbook = self.rest_client.fetch_orderbook(symbol, 5)  # 减少深度
            if orderbook:
                recovery_data["orderbook"] = orderbook
                recovery_data["recovered_components"].append("orderbook")
                self.logger.info(f"成功恢复 {symbol} 订单簿数据")
            else:
                recovery_data["failed_components"].append("orderbook")
        except Exception as e:
            self.logger.warning(f"恢复 {symbol} 订单簿数据失败: {e}")
            recovery_data["failed_components"].append("orderbook")
    
    def _try_recover_recent_trades(self, symbol: str, recovery_data: Dict[str, Any]):
        """尝试恢复最近交易数据"""
        try:
            trades = self.rest_client.fetch_recent_trades(symbol, 10)  # 减少数量
            if trades:
                recovery_data["recent_trades"] = trades
                recovery_data["recovered_components"].append("recent_trades")
                self.logger.info(f"成功恢复 {symbol} 最近交易数据")
            else:
                recovery_data["failed_components"].append("recent_trades")
        except Exception as e:
            self.logger.warning(f"恢复 {symbol} 最近交易数据失败: {e}")
            recovery_data["failed_components"].append("recent_trades")
    
    def _try_recover_basic_ohlcv(self, symbol: str, recovery_data: Dict[str, Any]):
        """尝试恢复基本 OHLCV 数据"""
        try:
            # 只获取最近的数据，减少API压力
            since = int((time.time() - 300 * 20) * 1000)  # 最近20根K线
            ohlcv = self.rest_client.fetch_ohlcv(symbol, since, 20, "5m")
            
            if ohlcv:
                recovery_data["basic_ohlcv"] = ohlcv
                recovery_data["recovered_components"].append("basic_ohlcv")
                self.logger.info(f"成功恢复 {symbol} 基本 OHLCV 数据")
            else:
                recovery_data["failed_components"].append("basic_ohlcv")
        except Exception as e:
            self.logger.warning(f"恢复 {symbol} 基本 OHLCV 数据失败: {e}")
            recovery_data["failed_components"].append("basic_ohlcv")
    
    def get_service_health_status(self) -> Dict[str, Any]:
        """获取服务健康状态"""
        try:
            health_status = {
                "timestamp": int(time.time() * 1000),
                "service_status": "unknown",
                "available_endpoints": [],
                "failed_endpoints": [],
                "response_times": {},
                "error_rates": {}
            }
            
            # 测试各个端点
            self._test_ticker_endpoint(health_status)
            self._test_orderbook_endpoint(health_status)
            self._test_ohlcv_endpoint(health_status)
            self._test_balance_endpoint(health_status)
            
            # 确定整体服务状态
            total_endpoints = len(health_status["available_endpoints"]) + len(health_status["failed_endpoints"])
            if total_endpoints == 0:
                health_status["service_status"] = "critical"
            elif len(health_status["failed_endpoints"]) == 0:
                health_status["service_status"] = "healthy"
            elif len(health_status["failed_endpoints"]) <= total_endpoints // 2:
                health_status["service_status"] = "degraded"
            else:
                health_status["service_status"] = "unhealthy"
            
            return health_status
            
        except Exception as e:
            self.logger.error(f"获取服务健康状态失败: {e}")
            return {
                "timestamp": int(time.time() * 1000),
                "service_status": "error",
                "error": str(e)
            }
    
    def _test_ticker_endpoint(self, health_status: Dict[str, Any]):
        """测试 ticker 端点"""
        try:
            start_time = time.time()
            ticker = self.rest_client.fetch_ticker("BTC-USDT")
            response_time = time.time() - start_time
            
            if ticker:
                health_status["available_endpoints"].append("ticker")
                health_status["response_times"]["ticker"] = response_time
            else:
                health_status["failed_endpoints"].append("ticker")
                health_status["error_rates"]["ticker"] = 1.0
        except Exception as e:
            health_status["failed_endpoints"].append("ticker")
            health_status["error_rates"]["ticker"] = 1.0
            self.logger.debug(f"Ticker 端点测试失败: {e}")
    
    def _test_orderbook_endpoint(self, health_status: Dict[str, Any]):
        """测试订单簿端点"""
        try:
            start_time = time.time()
            orderbook = self.rest_client.fetch_orderbook("BTC-USDT", 5)
            response_time = time.time() - start_time
            
            if orderbook:
                health_status["available_endpoints"].append("orderbook")
                health_status["response_times"]["orderbook"] = response_time
            else:
                health_status["failed_endpoints"].append("orderbook")
                health_status["error_rates"]["orderbook"] = 1.0
        except Exception as e:
            health_status["failed_endpoints"].append("orderbook")
            health_status["error_rates"]["orderbook"] = 1.0
            self.logger.debug(f"Orderbook 端点测试失败: {e}")
    
    def _test_ohlcv_endpoint(self, health_status: Dict[str, Any]):
        """测试 OHLCV 端点"""
        try:
            start_time = time.time()
            since = int((time.time() - 300) * 1000)  # 最近5分钟
            ohlcv = self.rest_client.fetch_ohlcv("BTC-USDT", since, 5, "5m")
            response_time = time.time() - start_time
            
            if ohlcv:
                health_status["available_endpoints"].append("ohlcv")
                health_status["response_times"]["ohlcv"] = response_time
            else:
                health_status["failed_endpoints"].append("ohlcv")
                health_status["error_rates"]["ohlcv"] = 1.0
        except Exception as e:
            health_status["failed_endpoints"].append("ohlcv")
            health_status["error_rates"]["ohlcv"] = 1.0
            self.logger.debug(f"OHLCV 端点测试失败: {e}")
    
    def _test_balance_endpoint(self, health_status: Dict[str, Any]):
        """测试余额端点"""
        try:
            start_time = time.time()
            balance = self.rest_client.fetch_balance()
            response_time = time.time() - start_time
            
            if balance is not None:
                health_status["available_endpoints"].append("balance")
                health_status["response_times"]["balance"] = response_time
            else:
                health_status["failed_endpoints"].append("balance")
                health_status["error_rates"]["balance"] = 1.0
        except Exception as e:
            health_status["failed_endpoints"].append("balance")
            health_status["error_rates"]["balance"] = 1.0
            self.logger.debug(f"Balance 端点测试失败: {e}")
    
    def should_enable_degradation(self, health_status: Dict[str, Any]) -> bool:
        """判断是否应该启用服务降级"""
        service_status = health_status.get("service_status", "unknown")
        
        # 如果服务状态为不健康或关键，启用降级
        if service_status in ["unhealthy", "critical"]:
            return True
        
        # 如果响应时间过长，考虑降级
        response_times = health_status.get("response_times", {})
        for endpoint, response_time in response_times.items():
            if response_time > 10.0:  # 10秒超时
                self.logger.warning(f"端点 {endpoint} 响应时间过长: {response_time:.2f}s")
                return True
        
        # 如果错误率过高，启用降级
        error_rates = health_status.get("error_rates", {})
        for endpoint, error_rate in error_rates.items():
            if error_rate > 0.5:  # 50%错误率
                self.logger.warning(f"端点 {endpoint} 错误率过高: {error_rate:.2%}")
                return True
        
        return False
    
    def get_degradation_strategy(self, health_status: Dict[str, Any]) -> str:
        """获取降级策略"""
        failed_endpoints = health_status.get("failed_endpoints", [])
        
        # 根据失败的端点确定降级策略
        if "ticker" in failed_endpoints and "orderbook" in failed_endpoints:
            return "minimal"  # 最小服务
        elif "ohlcv" in failed_endpoints:
            return "cached"  # 缓存服务
        elif len(failed_endpoints) == 1:
            return "partial"  # 部分服务
        else:
            return "full"  # 完整服务
