"""
业务指标监控模块
提供细粒度的业务指标收集、分析和告警功能
"""

import time
import json
import logging
import asyncio
import inspect
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict, deque
import redis.asyncio as redis
from src.utils.config_loader import get_config_manager

logger = logging.getLogger(__name__)


@dataclass
class TradingMetric:
    """交易指标数据结构"""
    timestamp: float
    symbol: str
    metric_type: str  # 'signal', 'order', 'position', 'pnl'
    value: float
    metadata: Dict[str, Any]


@dataclass
class SystemMetric:
    """系统指标数据结构"""
    timestamp: float
    service: str
    metric_type: str  # 'response_time', 'error_rate', 'throughput'
    value: float
    metadata: Dict[str, Any]


class BusinessMetricsCollector:
    """业务指标收集器"""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client
        self.metrics_buffer: deque = deque(maxlen=10000)
        self.alert_handlers: List[Callable] = []
        self.thresholds = self._load_thresholds()
        self.aggregation_window = 300  # 5分钟聚合窗口
        
        # 指标聚合缓存
        self._aggregated_metrics = {}
        self._last_aggregation = 0
        
    def _load_thresholds(self) -> Dict[str, Dict[str, float]]:
        """加载指标阈值配置"""
        try:
            config_manager = get_config_manager()
            monitoring_config = config_manager.get_config().get('monitoring', {})
            return monitoring_config.get('business_thresholds', {
                'signal_generation': {
                    'min_rate': 0.1,  # 每分钟最少信号数
                    'max_latency': 5.0  # 最大延迟秒数
                },
                'order_execution': {
                    'success_rate': 0.95,  # 最小成功率
                    'max_latency': 2.0  # 最大延迟秒数
                },
                'position_management': {
                    'max_drawdown': 0.05,  # 最大回撤
                    'min_profit_ratio': 0.02  # 最小盈利率
                },
                'system_performance': {
                    'max_response_time': 1.0,  # 最大响应时间
                    'max_error_rate': 0.01  # 最大错误率
                }
            })
        except Exception as e:
            logger.warning(f"Failed to load thresholds, using defaults: {e}")
            return {}
    
    async def collect_trading_metric(self, metric: TradingMetric):
        """收集交易指标"""
        try:
            # 添加到缓冲区
            self.metrics_buffer.append(metric)
            
            # 实时检查阈值
            await self._check_trading_thresholds(metric)
            
            # 异步存储到Redis
            if self.redis_client:
                await self._store_trading_metric(metric)
            
            # 定期聚合
            await self._maybe_aggregate_metrics()
            
        except Exception as e:
            logger.error(f"Failed to collect trading metric: {e}")
    
    async def collect_system_metric(self, metric: SystemMetric):
        """收集系统指标"""
        try:
            # 添加到缓冲区
            self.metrics_buffer.append(metric)
            
            # 实时检查阈值
            await self._check_system_thresholds(metric)
            
            # 异步存储到Redis
            if self.redis_client:
                await self._store_system_metric(metric)
            
            # 定期聚合
            await self._maybe_aggregate_metrics()
            
        except Exception as e:
            logger.error(f"Failed to collect system metric: {e}")
    
    async def _check_trading_thresholds(self, metric: TradingMetric):
        """检查交易指标阈值"""
        thresholds = self.thresholds.get(metric.metric_type, {})
        
        for threshold_name, threshold_value in thresholds.items():
            if self._is_threshold_violated(metric, threshold_name, threshold_value):
                alert = {
                    'type': 'threshold_violation',
                    'metric_type': metric.metric_type,
                    'threshold_name': threshold_name,
                    'current_value': metric.value,
                    'threshold_value': threshold_value,
                    'timestamp': metric.timestamp,
                    'symbol': metric.symbol,
                    'severity': self._get_severity(metric, threshold_name, threshold_value)
                }
                await self._trigger_alert(alert)
    
    async def _check_system_thresholds(self, metric: SystemMetric):
        """检查系统指标阈值"""
        thresholds = self.thresholds.get(metric.metric_type, {})
        
        for threshold_name, threshold_value in thresholds.items():
            if self._is_threshold_violated(metric, threshold_name, threshold_value):
                alert = {
                    'type': 'threshold_violation',
                    'metric_type': metric.metric_type,
                    'threshold_name': threshold_name,
                    'current_value': metric.value,
                    'threshold_value': threshold_value,
                    'timestamp': metric.timestamp,
                    'service': metric.service,
                    'severity': self._get_severity(metric, threshold_name, threshold_value)
                }
                await self._trigger_alert(alert)
    
    def _is_threshold_violated(self, metric, threshold_name: str, threshold_value: float) -> bool:
        """检查是否违反阈值"""
        if 'max' in threshold_name:
            return metric.value > threshold_value
        elif 'min' in threshold_name:
            return metric.value < threshold_value
        elif 'rate' in threshold_name:
            return metric.value < threshold_value
        else:
            return False
    
    def _get_severity(self, metric, threshold_name: str, threshold_value: float) -> str:
        """获取告警严重程度"""
        ratio = abs(metric.value - threshold_value) / threshold_value
        
        if ratio > 0.5:
            return 'critical'
        elif ratio > 0.2:
            return 'warning'
        else:
            return 'info'
    
    async def _trigger_alert(self, alert: Dict[str, Any]):
        """触发告警"""
        try:
            logger.warning(f"Business metric alert: {alert}")
            
            # 调用所有告警处理器
            for handler in self.alert_handlers:
                try:
                    if inspect.iscoroutinefunction(handler):
                        await handler(alert)
                    else:
                        handler(alert)
                except Exception as e:
                    logger.error(f"Alert handler failed: {e}")
            
            # 存储告警到Redis
            if self.redis_client:
                await self.redis_client.lpush(
                    'business_alerts',
                    json.dumps({**alert, 'id': f"alert_{int(time.time())}"})
                )
                await self.redis_client.ltrim('business_alerts', 0, 999)  # 保留最近1000条告警
                
        except Exception as e:
            logger.error(f"Failed to trigger alert: {e}")
    
    async def _store_trading_metric(self, metric: TradingMetric):
        """存储交易指标到Redis"""
        try:
            key = f"trading_metrics:{metric.symbol}:{metric.metric_type}"
            await self.redis_client.zadd(
                key,
                {json.dumps(asdict(metric)): metric.timestamp}
            )
            await self.redis_client.expire(key, 86400)  # 24小时过期
            
        except Exception as e:
            logger.error(f"Failed to store trading metric: {e}")
    
    async def _store_system_metric(self, metric: SystemMetric):
        """存储系统指标到Redis"""
        try:
            key = f"system_metrics:{metric.service}:{metric.metric_type}"
            await self.redis_client.zadd(
                key,
                {json.dumps(asdict(metric)): metric.timestamp}
            )
            await self.redis_client.expire(key, 86400)  # 24小时过期
            
        except Exception as e:
            logger.error(f"Failed to store system metric: {e}")
    
    async def _maybe_aggregate_metrics(self):
        """定期聚合指标"""
        current_time = time.time()
        if current_time - self._last_aggregation < 60:  # 每分钟聚合一次
            return
        
        self._last_aggregation = current_time
        await self._aggregate_metrics()
    
    async def _aggregate_metrics(self):
        """聚合指标数据"""
        try:
            current_time = time.time()
            window_start = current_time - self.aggregation_window
            
            # 按类型分组聚合
            trading_metrics = defaultdict(list)
            system_metrics = defaultdict(list)
            
            for metric in self.metrics_buffer:
                if metric.timestamp < window_start:
                    continue
                    
                if isinstance(metric, TradingMetric):
                    trading_metrics[metric.metric_type].append(metric)
                elif isinstance(metric, SystemMetric):
                    system_metrics[metric.metric_type].append(metric)
            
            # 计算聚合统计
            aggregated = {}
            
            # 交易指标聚合
            for metric_type, metrics in trading_metrics.items():
                if not metrics:
                    continue
                    
                values = [m.value for m in metrics]
                aggregated[f'trading.{metric_type}'] = {
                    'count': len(metrics),
                    'sum': sum(values),
                    'avg': sum(values) / len(values),
                    'min': min(values),
                    'max': max(values),
                    'timestamp': current_time
                }
            
            # 系统指标聚合
            for metric_type, metrics in system_metrics.items():
                if not metrics:
                    continue
                    
                values = [m.value for m in metrics]
                aggregated[f'system.{metric_type}'] = {
                    'count': len(metrics),
                    'sum': sum(values),
                    'avg': sum(values) / len(values),
                    'min': min(values),
                    'max': max(values),
                    'timestamp': current_time
                }
            
            # 存储聚合结果
            self._aggregated_metrics = aggregated
            
            if self.redis_client:
                await self.redis_client.hset(
                    'aggregated_metrics',
                    mapping={k: json.dumps(v) for k, v in aggregated.items()}
                )
                await self.redis_client.expire('aggregated_metrics', 3600)  # 1小时过期
            
            logger.debug(f"Aggregated {len(aggregated)} metric types")
            
        except Exception as e:
            logger.error(f"Failed to aggregate metrics: {e}")
    
    def add_alert_handler(self, handler: Callable):
        """添加告警处理器"""
        self.alert_handlers.append(handler)
        logger.info(f"Added alert handler: {handler.__name__}")
    
    def remove_alert_handler(self, handler: Callable):
        """移除告警处理器"""
        if handler in self.alert_handlers:
            self.alert_handlers.remove(handler)
            logger.info(f"Removed alert handler: {handler.__name__}")
    
    async def get_metrics_summary(self, time_window: int = 300) -> Dict[str, Any]:
        """获取指标摘要"""
        try:
            current_time = time.time()
            window_start = current_time - time_window
            
            # 过滤时间窗口内的指标
            recent_metrics = [
                m for m in self.metrics_buffer 
                if m.timestamp >= window_start
            ]
            
            # 按类型统计
            trading_by_type = defaultdict(list)
            system_by_type = defaultdict(list)
            
            for metric in recent_metrics:
                if isinstance(metric, TradingMetric):
                    trading_by_type[metric.metric_type].append(metric)
                elif isinstance(metric, SystemMetric):
                    system_by_type[metric.metric_type].append(metric)
            
            summary = {
                'time_window': time_window,
                'total_metrics': len(recent_metrics),
                'trading_metrics': {},
                'system_metrics': {},
                'aggregated_metrics': self._aggregated_metrics
            }
            
            # 交易指标统计
            for metric_type, metrics in trading_by_type.items():
                values = [m.value for m in metrics]
                symbols = list(set(m.symbol for m in metrics))
                
                summary['trading_metrics'][metric_type] = {
                    'count': len(metrics),
                    'symbols': symbols,
                    'avg_value': sum(values) / len(values) if values else 0,
                    'min_value': min(values) if values else 0,
                    'max_value': max(values) if values else 0
                }
            
            # 系统指标统计
            for metric_type, metrics in system_by_type.items():
                values = [m.value for m in metrics]
                services = list(set(m.service for m in metrics))
                
                summary['system_metrics'][metric_type] = {
                    'count': len(metrics),
                    'services': services,
                    'avg_value': sum(values) / len(values) if values else 0,
                    'min_value': min(values) if values else 0,
                    'max_value': max(values) if values else 0
                }
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get metrics summary: {e}")
            return {}
    
    async def get_real_time_dashboard_data(self) -> Dict[str, Any]:
        """获取实时仪表板数据"""
        try:
            # 获取最近5分钟的指标摘要
            summary = await self.get_metrics_summary(300)
            
            # 获取最近的告警
            recent_alerts = []
            if self.redis_client:
                alert_data = await self.redis_client.lrange('business_alerts', 0, 9)  # 最近10条
                recent_alerts = [json.loads(alert) for alert in alert_data]
            
            # 计算关键业务指标
            key_metrics = self._calculate_key_metrics(summary)
            
            return {
                'timestamp': time.time(),
                'summary': summary,
                'recent_alerts': recent_alerts,
                'key_metrics': key_metrics,
                'health_score': self._calculate_health_score(key_metrics)
            }
            
        except Exception as e:
            logger.error(f"Failed to get dashboard data: {e}")
            return {}
    
    def _calculate_key_metrics(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """计算关键业务指标"""
        key_metrics = {}
        
        # 交易相关指标
        trading_metrics = summary.get('trading_metrics', {})
        
        # 信号生成率
        if 'signal' in trading_metrics:
            signal_count = trading_metrics['signal']['count']
            key_metrics['signal_rate_per_minute'] = signal_count / 5  # 5分钟窗口
        
        # 订单执行成功率
        if 'order' in trading_metrics:
            order_metrics = trading_metrics['order']
            # 假设value为1表示成功，0表示失败
            if order_metrics['count'] > 0:
                success_rate = order_metrics['avg_value']
                key_metrics['order_success_rate'] = success_rate
        
        # 持仓盈利率
        if 'position' in trading_metrics:
            position_metrics = trading_metrics['position']
            key_metrics['position_profit_rate'] = position_metrics['avg_value']
        
        # 系统相关指标
        system_metrics = summary.get('system_metrics', {})
        
        # 平均响应时间
        if 'response_time' in system_metrics:
            key_metrics['avg_response_time'] = system_metrics['response_time']['avg_value']
        
        # 错误率
        if 'error_rate' in system_metrics:
            key_metrics['system_error_rate'] = system_metrics['error_rate']['avg_value']
        
        return key_metrics
    
    def _calculate_health_score(self, key_metrics: Dict[str, Any]) -> float:
        """计算系统健康分数 (0-100)"""
        try:
            scores = []
            
            # 订单成功率权重30%
            if 'order_success_rate' in key_metrics:
                success_rate = key_metrics['order_success_rate']
                scores.append(min(success_rate * 100, 30))
            
            # 系统错误率权重25% (错误率越低分数越高)
            if 'system_error_rate' in key_metrics:
                error_rate = key_metrics['system_error_rate']
                error_score = max(0, 25 * (1 - error_rate * 10))  # 假设1%错误率为0分
                scores.append(error_score)
            
            # 响应时间权重20% (响应时间越低分数越高)
            if 'avg_response_time' in key_metrics:
                response_time = key_metrics['avg_response_time']
                response_score = max(0, 20 * (1 - response_time))  # 假设1秒为0分
                scores.append(response_score)
            
            # 信号生成率权重15%
            if 'signal_rate_per_minute' in key_metrics:
                signal_rate = key_metrics['signal_rate_per_minute']
                signal_score = min(signal_rate * 3, 15)  # 假设5个/分钟为满分
                scores.append(signal_score)
            
            # 持仓盈利率权重10%
            if 'position_profit_rate' in key_metrics:
                profit_rate = key_metrics['position_profit_rate']
                profit_score = max(0, min(profit_rate * 100, 10))
                scores.append(profit_score)
            
            return sum(scores)
            
        except Exception as e:
            logger.error(f"Failed to calculate health score: {e}")
            return 50.0  # 默认中等分数


# 全局实例
_business_metrics_collector = None

def get_business_metrics_collector(redis_client: Optional[redis.Redis] = None) -> BusinessMetricsCollector:
    """获取全局业务指标收集器实例"""
    global _business_metrics_collector
    if _business_metrics_collector is None:
        _business_metrics_collector = BusinessMetricsCollector(redis_client)
    return _business_metrics_collector


# 便捷函数
async def record_trading_signal(symbol: str, signal_strength: float, metadata: Dict[str, Any] = None):
    """记录交易信号指标"""
    collector = get_business_metrics_collector()
    metric = TradingMetric(
        timestamp=time.time(),
        symbol=symbol,
        metric_type='signal',
        value=signal_strength,
        metadata=metadata or {}
    )
    await collector.collect_trading_metric(metric)


async def record_order_execution(symbol: str, success: bool, latency: float, metadata: Dict[str, Any] = None):
    """记录订单执行指标"""
    collector = get_business_metrics_collector()
    metric = TradingMetric(
        timestamp=time.time(),
        symbol=symbol,
        metric_type='order',
        value=1.0 if success else 0.0,
        metadata={**(metadata or {}), 'latency': latency}
    )
    await collector.collect_trading_metric(metric)


async def record_system_performance(service: str, response_time: float, metadata: Dict[str, Any] = None):
    """记录系统性能指标"""
    collector = get_business_metrics_collector()
    metric = SystemMetric(
        timestamp=time.time(),
        service=service,
        metric_type='response_time',
        value=response_time,
        metadata=metadata or {}
    )
    await collector.collect_system_metric(metric)


async def record_system_error(service: str, error_type: str, metadata: Dict[str, Any] = None):
    """记录系统错误指标"""
    collector = get_business_metrics_collector()
    metric = SystemMetric(
        timestamp=time.time(),
        service=service,
        metric_type='error_rate',
        value=1.0,
        metadata={**(metadata or {}), 'error_type': error_type}
    )
    await collector.collect_system_metric(metric)
