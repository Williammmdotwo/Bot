"""
优化版业务指标监控模块
提供高性能的指标收集、批量处理和内存优化功能
"""

import time
import json
import logging
import asyncio
import inspect
from typing import Dict, Any, List, Optional, Callable, Tuple
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


class OptimizedBusinessMetricsCollector:
    """优化版业务指标收集器"""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client
        self.alert_handlers: List[Callable] = []
        self.thresholds = self._load_thresholds()
        self.aggregation_window = 300  # 5分钟聚合窗口
        
        # 优化：使用多个队列分离不同类型的指标
        self.trading_metrics_queue = asyncio.Queue(maxsize=5000)
        self.system_metrics_queue = asyncio.Queue(maxsize=5000)
        self.alerts_queue = asyncio.Queue(maxsize=1000)
        
        # 优化：批量处理缓冲区
        self.trading_batch_buffer = []
        self.system_batch_buffer = []
        self.alert_batch_buffer = []
        
        # 批量处理配置
        self.batch_size = 100  # 批量大小
        self.batch_timeout = 5.0  # 批量超时时间（秒）
        
        # 内存优化：使用循环缓冲区
        self.metrics_buffer = deque(maxlen=5000)  # 减少缓冲区大小
        self._aggregated_metrics = {}
        self._last_aggregation = 0
        
        # 性能统计
        self.stats = {
            'metrics_processed': 0,
            'alerts_triggered': 0,
            'batches_processed': 0,
            'processing_errors': 0
        }
        
        # 启动后台处理任务
        self._background_tasks = []
        self._start_background_processors()
    
    def _load_thresholds(self) -> Dict[str, Dict[str, float]]:
        """加载指标阈值配置"""
        try:
            config_manager = get_config_manager()
            monitoring_config = config_manager.get_config().get('monitoring', {})
            return monitoring_config.get('business_thresholds', {
                'signal_generation': {
                    'min_rate': 0.1,
                    'max_latency': 5.0
                },
                'order_execution': {
                    'success_rate': 0.95,
                    'max_latency': 2.0
                },
                'position_management': {
                    'max_drawdown': 0.05,
                    'min_profit_ratio': 0.02
                },
                'system_performance': {
                    'max_response_time': 1.0,
                    'max_error_rate': 0.01
                }
            })
        except Exception as e:
            logger.warning(f"Failed to load thresholds, using defaults: {e}")
            return {}
    
    def _start_background_processors(self):
        """启动后台处理任务"""
        try:
            # 检查是否有运行的事件循环
            loop = asyncio.get_running_loop()
            
            # 交易指标处理器
            trading_task = loop.create_task(self._process_trading_metrics())
            self._background_tasks.append(trading_task)
            
            # 系统指标处理器
            system_task = loop.create_task(self._process_system_metrics())
            self._background_tasks.append(system_task)
            
            # 告警处理器
            alert_task = loop.create_task(self._process_alerts())
            self._background_tasks.append(alert_task)
            
            # 聚合任务
            aggregation_task = loop.create_task(self._periodic_aggregation())
            self._background_tasks.append(aggregation_task)
            
            logger.info("Started background processors for optimized metrics collector")
            
        except RuntimeError:
            # 没有运行的事件循环，延迟启动
            logger.warning("No event loop running, background processors will be started later")
    
    async def collect_trading_metric(self, metric: TradingMetric):
        """收集交易指标（非阻塞）"""
        try:
            # 非阻塞入队
            self.trading_metrics_queue.put_nowait(metric)
            self.stats['metrics_processed'] += 1
        except asyncio.QueueFull:
            logger.warning("Trading metrics queue is full, dropping metric")
            self.stats['processing_errors'] += 1
    
    async def collect_system_metric(self, metric: SystemMetric):
        """收集系统指标（非阻塞）"""
        try:
            # 非阻塞入队
            self.system_metrics_queue.put_nowait(metric)
            self.stats['metrics_processed'] += 1
        except asyncio.QueueFull:
            logger.warning("System metrics queue is full, dropping metric")
            self.stats['processing_errors'] += 1
    
    async def _process_trading_metrics(self):
        """后台处理交易指标"""
        while True:
            try:
                # 批量收集指标
                batch = await self._collect_batch(
                    self.trading_metrics_queue, 
                    self.trading_batch_buffer,
                    'trading'
                )
                
                if batch:
                    await self._process_trading_batch(batch)
                
                # 短暂休眠避免CPU占用过高
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error in trading metrics processor: {e}")
                self.stats['processing_errors'] += 1
                await asyncio.sleep(1)  # 错误后稍长休眠
    
    async def _process_system_metrics(self):
        """后台处理系统指标"""
        while True:
            try:
                # 批量收集指标
                batch = await self._collect_batch(
                    self.system_metrics_queue,
                    self.system_batch_buffer,
                    'system'
                )
                
                if batch:
                    await self._process_system_batch(batch)
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error in system metrics processor: {e}")
                self.stats['processing_errors'] += 1
                await asyncio.sleep(1)
    
    async def _collect_batch(self, queue: asyncio.Queue, buffer: List, metric_type: str) -> List:
        """收集批量数据"""
        batch = []
        
        # 首先从缓冲区获取剩余数据
        if buffer:
            batch.extend(buffer)
            buffer.clear()
        
        # 尝试从队列获取更多数据
        try:
            # 等待第一个数据或超时
            metric = await asyncio.wait_for(queue.get(), timeout=self.batch_timeout)
            batch.append(metric)
            
            # 快速获取更多数据（非阻塞）
            while len(batch) < self.batch_size:
                try:
                    metric = queue.get_nowait()
                    batch.append(metric)
                except asyncio.QueueEmpty:
                    break
                    
        except asyncio.TimeoutError:
            # 超时了，使用当前批次
            pass
        
        return batch
    
    async def _process_trading_batch(self, batch: List[TradingMetric]):
        """批量处理交易指标"""
        try:
            # 内存优化：只保留最近的指标
            for metric in batch:
                self.metrics_buffer.append(metric)
            
            # 批量阈值检查
            await self._batch_check_trading_thresholds(batch)
            
            # 批量存储到Redis
            if self.redis_client and batch:
                await self._batch_store_trading_metrics(batch)
            
            self.stats['batches_processed'] += 1
            
        except Exception as e:
            logger.error(f"Failed to process trading batch: {e}")
            self.stats['processing_errors'] += 1
    
    async def _process_system_batch(self, batch: List[SystemMetric]):
        """批量处理系统指标"""
        try:
            # 内存优化：只保留最近的指标
            for metric in batch:
                self.metrics_buffer.append(metric)
            
            # 批量阈值检查
            await self._batch_check_system_thresholds(batch)
            
            # 批量存储到Redis
            if self.redis_client and batch:
                await self._batch_store_system_metrics(batch)
            
            self.stats['batches_processed'] += 1
            
        except Exception as e:
            logger.error(f"Failed to process system batch: {e}")
            self.stats['processing_errors'] += 1
    
    async def _batch_check_trading_thresholds(self, batch: List[TradingMetric]):
        """批量检查交易指标阈值"""
        alerts = []
        
        for metric in batch:
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
                    alerts.append(alert)
        
        # 批量处理告警
        if alerts:
            await self._batch_queue_alerts(alerts)
    
    async def _batch_check_system_thresholds(self, batch: List[SystemMetric]):
        """批量检查系统指标阈值"""
        alerts = []
        
        for metric in batch:
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
                    alerts.append(alert)
        
        # 批量处理告警
        if alerts:
            await self._batch_queue_alerts(alerts)
    
    async def _batch_queue_alerts(self, alerts: List[Dict[str, Any]]):
        """批量队列告警"""
        for alert in alerts:
            try:
                self.alerts_queue.put_nowait(alert)
                self.stats['alerts_triggered'] += 1
            except asyncio.QueueFull:
                logger.warning("Alerts queue is full, dropping alert")
    
    async def _process_alerts(self):
        """后台处理告警"""
        while True:
            try:
                # 批量收集告警
                batch = await self._collect_batch(
                    self.alerts_queue,
                    self.alert_batch_buffer,
                    'alerts'
                )
                
                if batch:
                    await self._batch_trigger_alerts(batch)
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error in alerts processor: {e}")
                self.stats['processing_errors'] += 1
                await asyncio.sleep(1)
    
    async def _batch_trigger_alerts(self, alerts: List[Dict[str, Any]]):
        """批量触发告警"""
        try:
            # 调用所有告警处理器
            for handler in self.alert_handlers:
                try:
                    if inspect.iscoroutinefunction(handler):
                        await handler(alerts)
                    else:
                        handler(alerts)
                except Exception as e:
                    logger.error(f"Alert handler failed: {e}")
            
            # 批量存储告警到Redis
            if self.redis_client and alerts:
                await self._batch_store_alerts(alerts)
                
        except Exception as e:
            logger.error(f"Failed to batch trigger alerts: {e}")
            self.stats['processing_errors'] += 1
    
    async def _batch_store_trading_metrics(self, batch: List[TradingMetric]):
        """批量存储交易指标到Redis"""
        try:
            # 按类型分组以减少Redis操作
            grouped_metrics = defaultdict(list)
            for metric in batch:
                key = f"trading_metrics:{metric.symbol}:{metric.metric_type}"
                grouped_metrics[key].append(metric)
            
            # 批量存储
            pipe = self.redis_client.pipeline()
            for key, metrics in grouped_metrics.items():
                for metric in metrics:
                    pipe.zadd(
                        key,
                        {json.dumps(asdict(metric)): metric.timestamp}
                    )
                pipe.expire(key, 86400)  # 24小时过期
            
            await pipe.execute()
            
        except Exception as e:
            logger.error(f"Failed to batch store trading metrics: {e}")
    
    async def _batch_store_system_metrics(self, batch: List[SystemMetric]):
        """批量存储系统指标到Redis"""
        try:
            # 按类型分组以减少Redis操作
            grouped_metrics = defaultdict(list)
            for metric in batch:
                key = f"system_metrics:{metric.service}:{metric.metric_type}"
                grouped_metrics[key].append(metric)
            
            # 批量存储
            pipe = self.redis_client.pipeline()
            for key, metrics in grouped_metrics.items():
                for metric in metrics:
                    pipe.zadd(
                        key,
                        {json.dumps(asdict(metric)): metric.timestamp}
                    )
                pipe.expire(key, 86400)  # 24小时过期
            
            await pipe.execute()
            
        except Exception as e:
            logger.error(f"Failed to batch store system metrics: {e}")
    
    async def _batch_store_alerts(self, alerts: List[Dict[str, Any]]):
        """批量存储告警到Redis"""
        try:
            pipe = self.redis_client.pipeline()
            for alert in alerts:
                pipe.lpush(
                    'business_alerts',
                    json.dumps({**alert, 'id': f"alert_{int(time.time() * 1000)}"})
                )
            pipe.ltrim('business_alerts', 0, 999)  # 保留最近1000条告警
            await pipe.execute()
            
        except Exception as e:
            logger.error(f"Failed to batch store alerts: {e}")
    
    async def _periodic_aggregation(self):
        """定期聚合指标"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟聚合一次
                await self._aggregate_metrics()
                
            except Exception as e:
                logger.error(f"Error in periodic aggregation: {e}")
                self.stats['processing_errors'] += 1
    
    async def _aggregate_metrics(self):
        """聚合指标数据（优化版）"""
        try:
            current_time = time.time()
            window_start = current_time - self.aggregation_window
            
            # 优化：使用生成器减少内存使用
            def filter_metrics():
                for metric in self.metrics_buffer:
                    if metric.timestamp >= window_start:
                        yield metric
            
            # 按类型分组聚合
            trading_metrics = defaultdict(list)
            system_metrics = defaultdict(list)
            
            for metric in filter_metrics():
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
            
            # 优化：使用生成器过滤
            def filter_recent_metrics():
                for metric in self.metrics_buffer:
                    if metric.timestamp >= window_start:
                        yield metric
            
            # 按类型统计
            trading_by_type = defaultdict(list)
            system_by_type = defaultdict(list)
            
            for metric in filter_recent_metrics():
                if isinstance(metric, TradingMetric):
                    trading_by_type[metric.metric_type].append(metric)
                elif isinstance(metric, SystemMetric):
                    system_by_type[metric.metric_type].append(metric)
            
            summary = {
                'time_window': time_window,
                'total_metrics': len(self.metrics_buffer),
                'trading_metrics': {},
                'system_metrics': {},
                'aggregated_metrics': self._aggregated_metrics,
                'performance_stats': self.stats
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
                alert_data = await self.redis_client.lrange('business_alerts', 0, 9)
                recent_alerts = [json.loads(alert) for alert in alert_data]
            
            # 计算关键业务指标
            key_metrics = self._calculate_key_metrics(summary)
            
            return {
                'timestamp': time.time(),
                'summary': summary,
                'recent_alerts': recent_alerts,
                'key_metrics': key_metrics,
                'health_score': self._calculate_health_score(key_metrics),
                'queue_stats': {
                    'trading_queue_size': self.trading_metrics_queue.qsize(),
                    'system_queue_size': self.system_metrics_queue.qsize(),
                    'alerts_queue_size': self.alerts_queue.qsize()
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get dashboard data: {e}")
            return {}
    
    def _calculate_key_metrics(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """计算关键业务指标"""
        key_metrics = {}
        
        # 交易相关指标
        trading_metrics = summary.get('trading_metrics', {})
        
        if 'signal' in trading_metrics:
            signal_count = trading_metrics['signal']['count']
            key_metrics['signal_rate_per_minute'] = signal_count / 5
        
        if 'order' in trading_metrics:
            order_metrics = trading_metrics['order']
            if order_metrics['count'] > 0:
                success_rate = order_metrics['avg_value']
                key_metrics['order_success_rate'] = success_rate
        
        if 'position' in trading_metrics:
            position_metrics = trading_metrics['position']
            key_metrics['position_profit_rate'] = position_metrics['avg_value']
        
        # 系统相关指标
        system_metrics = summary.get('system_metrics', {})
        
        if 'response_time' in system_metrics:
            key_metrics['avg_response_time'] = system_metrics['response_time']['avg_value']
        
        if 'error_rate' in system_metrics:
            key_metrics['system_error_rate'] = system_metrics['error_rate']['avg_value']
        
        return key_metrics
    
    def _calculate_health_score(self, key_metrics: Dict[str, Any]) -> float:
        """计算系统健康分数 (0-100)"""
        try:
            scores = []
            
            if 'order_success_rate' in key_metrics:
                success_rate = key_metrics['order_success_rate']
                scores.append(min(success_rate * 100, 30))
            
            if 'system_error_rate' in key_metrics:
                error_rate = key_metrics['system_error_rate']
                error_score = max(0, 25 * (1 - error_rate * 10))
                scores.append(error_score)
            
            if 'avg_response_time' in key_metrics:
                response_time = key_metrics['avg_response_time']
                response_score = max(0, 20 * (1 - response_time))
                scores.append(response_score)
            
            if 'signal_rate_per_minute' in key_metrics:
                signal_rate = key_metrics['signal_rate_per_minute']
                signal_score = min(signal_rate * 3, 15)
                scores.append(signal_score)
            
            if 'position_profit_rate' in key_metrics:
                profit_rate = key_metrics['position_profit_rate']
                profit_score = max(0, min(profit_rate * 100, 10))
                scores.append(profit_score)
            
            return sum(scores)
            
        except Exception as e:
            logger.error(f"Failed to calculate health score: {e}")
            return 50.0
    
    async def shutdown(self):
        """优雅关闭"""
        logger.info("Shutting down optimized metrics collector...")
        
        # 取消后台任务
        for task in self._background_tasks:
            task.cancel()
        
        # 等待任务完成
        await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        logger.info("Optimized metrics collector shutdown complete")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        return {
            **self.stats,
            'queue_sizes': {
                'trading': self.trading_metrics_queue.qsize(),
                'system': self.system_metrics_queue.qsize(),
                'alerts': self.alerts_queue.qsize()
            },
            'buffer_sizes': {
                'metrics': len(self.metrics_buffer),
                'trading_batch': len(self.trading_batch_buffer),
                'system_batch': len(self.system_batch_buffer),
                'alert_batch': len(self.alert_batch_buffer)
            }
        }


# 全局实例
_optimized_business_metrics_collector = None

def get_optimized_business_metrics_collector(redis_client: Optional[redis.Redis] = None) -> OptimizedBusinessMetricsCollector:
    """获取全局优化版业务指标收集器实例"""
    global _optimized_business_metrics_collector
    if _optimized_business_metrics_collector is None:
        _optimized_business_metrics_collector = OptimizedBusinessMetricsCollector(redis_client)
    return _optimized_business_metrics_collector


# 便捷函数
async def record_trading_signal_optimized(symbol: str, signal_strength: float, metadata: Dict[str, Any] = None):
    """记录交易信号指标（优化版）"""
    collector = get_optimized_business_metrics_collector()
    metric = TradingMetric(
        timestamp=time.time(),
        symbol=symbol,
        metric_type='signal',
        value=signal_strength,
        metadata=metadata or {}
    )
    await collector.collect_trading_metric(metric)


async def record_order_execution_optimized(symbol: str, success: bool, latency: float, metadata: Dict[str, Any] = None):
    """记录订单执行指标（优化版）"""
    collector = get_optimized_business_metrics_collector()
    metric = TradingMetric(
        timestamp=time.time(),
        symbol=symbol,
        metric_type='order',
        value=1.0 if success else 0.0,
        metadata={**(metadata or {}), 'latency': latency}
    )
    await collector.collect_trading_metric(metric)


async def record_system_performance_optimized(service: str, response_time: float, metadata: Dict[str, Any] = None):
    """记录系统性能指标（优化版）"""
    collector = get_optimized_business_metrics_collector()
    metric = SystemMetric(
        timestamp=time.time(),
        service=service,
        metric_type='response_time',
        value=response_time,
        metadata=metadata or {}
    )
    await collector.collect_system_metric(metric)


async def record_system_error_optimized(service: str, error_type: str, metadata: Dict[str, Any] = None):
    """记录系统错误指标（优化版）"""
    collector = get_optimized_business_metrics_collector()
    metric = SystemMetric(
        timestamp=time.time(),
        service=service,
        metric_type='error_rate',
        value=1.0,
        metadata={**(metadata or {}), 'error_type': error_type}
    )
    await collector.collect_system_metric(metric)
