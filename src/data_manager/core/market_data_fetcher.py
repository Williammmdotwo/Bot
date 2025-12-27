"""
市场数据获取器模块
负责从交易所获取市场数据
"""

import logging
import time
from typing import Dict, Any, List, Optional
from .rest_client import RESTClient
from .technical_indicators import TechnicalIndicators


class MarketDataFetcher:
    """市场数据获取器 - 负责从交易所获取数据"""
    
    def __init__(self, rest_client: RESTClient):
        self.rest_client = rest_client
        self.logger = logging.getLogger(__name__)
        self.logger.info("MarketDataFetcher 初始化完成")
    
    def get_comprehensive_market_data(self, symbol: str, use_demo: bool = False) -> Optional[Dict[str, Any]]:
        """获取综合市场数据"""
        try:
            self.logger.info(f"获取 {symbol} 的综合市场数据")
            
            # 初始化适当的 REST 客户端
            try:
                rest_client = RESTClient(use_demo=use_demo)
            except Exception as e:
                self.logger.error(f"初始化 REST 客户端失败: {e}")
                return None
            
            # 获取市场信息，支持服务降级
            market_info = self._get_market_info_with_fallback(rest_client, symbol)
            if not market_info:
                return None
            
            # 计算技术指标
            technical_analysis = self._calculate_all_timeframe_indicators(market_info["ohlcv"])
            
            # 分析成交量分布
            volume_profile = {}
            try:
                if market_info.get("recent_trades"):
                    volume_profile = TechnicalIndicators.analyze_volume_profile(market_info["recent_trades"])
            except Exception as e:
                self.logger.error(f"分析 {symbol} 成交量分布失败: {e}")
            
            # 获取当前市场状态
            current_price, orderbook, ticker = self._extract_market_state(market_info)
            
            return {
                "symbol": symbol,
                "current_price": current_price,
                "ticker": ticker,
                "orderbook": orderbook,
                "recent_trades": market_info.get("recent_trades", []),
                "ohlcv": market_info.get("ohlcv", {}),
                "technical_analysis": technical_analysis,
                "volume_profile": volume_profile,
                "timestamp": market_info.get("timestamp", int(time.time() * 1000)),
                "use_demo": use_demo
            }
            
        except Exception as e:
            self.logger.error(f"获取 {symbol} 综合市场数据失败: {e}")
            return None
    
    def _get_market_info_with_fallback(self, rest_client: RESTClient, symbol: str) -> Optional[Dict[str, Any]]:
        """获取市场信息，支持服务降级"""
        try:
            market_info = rest_client.get_market_info(symbol)
            if market_info:
                return market_info
            
            self.logger.warning(f"获取 {symbol} 市场信息返回空，尝试服务降级")
            return self._get_degraded_market_data(rest_client, symbol)
            
        except Exception as e:
            self.logger.error(f"获取 {symbol} 市场信息失败: {e}")
            self.logger.info("尝试服务降级...")
            return self._get_degraded_market_data(rest_client, symbol)
    
    def _get_degraded_market_data(self, rest_client: RESTClient, symbol: str) -> Optional[Dict[str, Any]]:
        """获取降级市场数据"""
        try:
            self.logger.info(f"尝试获取 {symbol} 的降级数据")
            
            degraded_data = {
                "symbol": symbol,
                "ticker": {},
                "orderbook": {},
                "recent_trades": [],
                "ohlcv": {},
                "timestamp": int(time.time() * 1000)
            }
            
            # 尝试获取各种数据组件
            self._try_get_ticker(rest_client, symbol, degraded_data)
            self._try_get_orderbook(rest_client, symbol, degraded_data)
            self._try_get_ohlcv(rest_client, symbol, degraded_data)
            self._try_get_recent_trades(rest_client, symbol, degraded_data)
            
            # 检查是否有任何数据
            has_data = (
                degraded_data["ticker"] or 
                degraded_data["orderbook"] or 
                degraded_data["ohlcv"] or 
                degraded_data["recent_trades"]
            )
            
            if has_data:
                self.logger.info(f"成功获取 {symbol} 的降级数据")
                return degraded_data
            else:
                self.logger.warning(f"{symbol} 没有可用的降级数据")
                return None
                
        except Exception as e:
            self.logger.error(f"获取 {symbol} 降级数据失败: {e}")
            return None
    
    def _try_get_ticker(self, rest_client: RESTClient, symbol: str, data: Dict[str, Any]):
        """尝试获取 ticker 数据"""
        try:
            ticker = rest_client.fetch_ticker(symbol)
            if ticker:
                data["ticker"] = ticker
                self.logger.info(f"成功获取 {symbol} ticker 数据")
        except Exception as e:
            self.logger.warning(f"获取 {symbol} ticker 数据失败: {e}")
    
    def _try_get_orderbook(self, rest_client: RESTClient, symbol: str, data: Dict[str, Any]):
        """尝试获取订单簿数据"""
        try:
            orderbook = rest_client.fetch_orderbook(symbol, 10)
            if orderbook:
                data["orderbook"] = orderbook
                self.logger.info(f"成功获取 {symbol} 订单簿数据")
        except Exception as e:
            self.logger.warning(f"获取 {symbol} 订单簿数据失败: {e}")
    
    def _try_get_ohlcv(self, rest_client: RESTClient, symbol: str, data: Dict[str, Any]):
        """尝试获取 OHLCV 数据"""
        try:
            critical_timeframes = ["5m", "15m", "1h"]
            ohlcv_data = {}
            
            for tf in critical_timeframes:
                try:
                    since = int((time.time() - 300 * 50) * 1000)  # 最近50根K线
                    ohlcv = rest_client.fetch_ohlcv(symbol, since, 50, tf)
                    if ohlcv:
                        ohlcv_data[tf] = ohlcv
                        self.logger.info(f"成功获取 {symbol} {tf} OHLCV 数据: {len(ohlcv)} 根K线")
                except Exception as e:
                    self.logger.warning(f"获取 {symbol} {tf} OHLCV 数据失败: {e}")
            
            data["ohlcv"] = ohlcv_data
            
        except Exception as e:
            self.logger.warning(f"获取 {symbol} OHLCV 数据失败: {e}")
    
    def _try_get_recent_trades(self, rest_client: RESTClient, symbol: str, data: Dict[str, Any]):
        """尝试获取最近交易数据"""
        try:
            trades = rest_client.fetch_recent_trades(symbol, 20)
            if trades:
                data["recent_trades"] = trades
                self.logger.info(f"成功获取 {symbol} 最近交易数据: {len(trades)} 笔交易")
        except Exception as e:
            self.logger.warning(f"获取 {symbol} 最近交易数据失败: {e}")
    
    def _calculate_all_timeframe_indicators(self, ohlcv_data: Dict[str, List]) -> Dict[str, Any]:
        """计算所有时间框架的技术指标"""
        technical_analysis = {}
        successful_timeframes = []
        failed_timeframes = []
        
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
            self.logger.info(f"成功计算技术指标的时间框架: {successful_timeframes}")
        if failed_timeframes:
            self.logger.warning(f"技术指标计算失败的时间框架: {failed_timeframes}")
        
        return technical_analysis
    
    def _extract_market_state(self, market_info: Dict[str, Any]) -> tuple[float, Dict[str, Any], Dict[str, Any]]:
        """提取市场状态信息"""
        current_price = 0
        orderbook = {}
        ticker = {}
        
        try:
            ticker = market_info.get("ticker", {})
            current_price = ticker.get("last", 0) if ticker else 0
            orderbook = market_info.get("orderbook", {})
            
            # 验证价格合理性
            if current_price <= 0:
                self.logger.warning(f"当前价格无效: {current_price}")
                # 尝试从订单簿获取价格
                if orderbook.get("bids") and orderbook.get("asks"):
                    best_bid = orderbook["bids"][0][0] if orderbook["bids"] else 0
                    best_ask = orderbook["asks"][0][0] if orderbook["asks"] else 0
                    if best_bid > 0 and best_ask > 0:
                        current_price = (best_bid + best_ask) / 2
                        self.logger.info(f"从订单簿推导出价格: {current_price}")
            
        except Exception as e:
            self.logger.error(f"提取市场状态失败: {e}")
        
        return current_price, orderbook, ticker
    
    def get_historical_klines(self, symbol: str, timeframe: str, limit: int = 1000, 
                            since: Optional[int] = None, use_demo: bool = False) -> List[List]:
        """获取历史K线数据"""
        try:
            self.logger.info(f"获取 {symbol} {timeframe} 历史K线数据，限制={limit}")
            
            # 从交易所API获取数据
            rest_client = RESTClient(use_demo=use_demo)
            
            # 计算时间范围
            if not since:
                timeframe_minutes = self._timeframe_to_minutes(timeframe)
                since = int((time.time() - timeframe_minutes * limit * 60) * 1000)
            
            # 分批获取数据以避免API限制
            all_klines = []
            batch_size = 500  # 每批获取500根K线
            current_since = since
            
            while len(all_klines) < limit:
                batch_limit = min(batch_size, limit - len(all_klines))
                
                try:
                    batch_klines = rest_client.fetch_ohlcv(symbol, current_since, batch_limit, timeframe)
                    
                    if not batch_klines:
                        self.logger.warning(f"{symbol} {timeframe} 没有更多历史数据")
                        break
                    
                    # 数据去重和验证
                    batch_klines = self._deduplicate_klines(batch_klines)
                    all_klines.extend(batch_klines)
                    
                    # 更新下次获取的开始时间
                    if batch_klines:
                        current_since = batch_klines[-1][0] + 1  # 下一个时间点
                    
                    self.logger.info(f"获取 {symbol} {timeframe} 批次数据: {len(batch_klines)} 根K线，总计: {len(all_klines)}")
                    
                    # 避免API频率限制
                    time.sleep(0.1)
                    
                except Exception as e:
                    self.logger.error(f"获取 {symbol} {timeframe} 批次数据失败: {e}")
                    break
            
            # 智能采样：保留关键转折点
            if len(all_klines) > limit:
                all_klines = self._smart_sampling(all_klines, limit)
            
            self.logger.info(f"成功获取 {symbol} {timeframe} 历史数据: {len(all_klines)} 根K线")
            return all_klines
            
        except Exception as e:
            self.logger.error(f"获取 {symbol} {timeframe} 历史K线数据失败: {e}")
            return []
    
    def get_multi_timeframe_data(self, symbol: str, timeframes: List[str] = None, 
                                limit: int = 500, use_demo: bool = False) -> Dict[str, List[List]]:
        """获取多时间框架数据"""
        if timeframes is None:
            timeframes = ["5m", "15m", "1h", "4h"]
        
        try:
            self.logger.info(f"获取 {symbol} 多时间框架数据: {timeframes}")
            
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
                        self.logger.info(f"成功获取 {symbol} {timeframe} 数据: {len(klines)} 根K线")
                    else:
                        failed_timeframes.append(timeframe)
                        self.logger.warning(f"{symbol} {timeframe} 没有可用数据")
                        
                except Exception as e:
                    failed_timeframes.append(timeframe)
                    self.logger.error(f"获取 {symbol} {timeframe} 数据失败: {e}")
            
            # 记录获取结果
            if successful_timeframes:
                self.logger.info(f"{symbol} 多时间框架数据获取完成: {successful_timeframes}")
            if failed_timeframes:
                self.logger.warning(f"{symbol} 失败的时间框架: {failed_timeframes}")
            
            return multi_data
            
        except Exception as e:
            self.logger.error(f"获取 {symbol} 多时间框架数据失败: {e}")
            return {}
    
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
        
        # 按时间戳去重，保留第一次出现的数据
        seen_timestamps = set()
        deduplicated = []
        
        # 按原始顺序遍历，保留第一次出现的数据
        for kline in klines:
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
            
            self.logger.info(f"智能采样: {len(klines)} -> {len(sampled_klines)} 根K线")
            return sampled_klines
            
        except Exception as e:
            self.logger.warning(f"智能采样失败，使用简单采样: {e}")
            # 回退到简单均匀采样
            step = len(klines) // target_count
            return klines[::step][:target_count]
