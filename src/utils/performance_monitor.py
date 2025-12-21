"""
性能监控模块
Performance Monitoring Module
"""

import time
import logging
import psutil
import threading
from typing import Dict, List, Any
from collections import deque, defaultdict

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics = defaultdict(lambda: deque(maxlen=max_history))
        self.counters = defaultdict(int)
        self.start_times = {}
        self.lock = threading.Lock()
        
        # 系统监控
        self.system_metrics = deque(maxlen=100)
        
    def start_timer(self, operation: str):
        """开始计时"""
        with self.lock:
            self.start_times[operation] = time.time()
    
    def end_timer(self, operation: str) -> float:
        """结束计时并记录"""
        end_time = time.time()
        
        with self.lock:
            if operation in self.start_times:
                duration = end_time - self.start_times[operation]
                self.metrics[operation].append({
                    'timestamp': end_time,
                    'duration': duration
                })
                del self.start_times[operation]
                return duration
        
        return 0.0
    
    def record_metric(self, metric_name: str, value: float):
        """记录指标"""
        with self.lock:
            self.metrics[metric_name].append({
                'timestamp': time.time(),
                'value': value
            })
    
    def increment_counter(self, counter_name: str, increment: int = 1):
        """增加计数器"""
        with self.lock:
            self.counters[counter_name] += increment
    
    def get_metrics_summary(self, operation: str) -> Dict[str, Any]:
        """获取操作指标摘要"""
        with self.lock:
            if operation not in self.metrics or not self.metrics[operation]:
                return {}
            
            values = [m['duration'] if 'duration' in m else m['value'] 
                     for m in self.metrics[operation]]
            
            return {
                'count': len(values),
                'avg': sum(values) / len(values),
                'min': min(values),
                'max': max(values),
                'latest': values[-1] if values else 0
            }
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """获取系统指标"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_used_gb': memory.used / (1024**3),
                'memory_total_gb': memory.total / (1024**3),
                'disk_percent': disk.percent,
                'timestamp': time.time()
            }
        except Exception as e:
            logger.error(f"获取系统指标失败: {e}")
            return {}
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        result = {
            'operations': {},
            'counters': dict(self.counters),
            'system': self.get_system_metrics(),
            'timestamp': time.time()
        }
        
        # 获取所有操作的摘要
        with self.lock:
            for operation in self.metrics:
                result['operations'][operation] = self.get_metrics_summary(operation)
        
        return result
    
    def check_performance_alerts(self) -> List[str]:
        """检查性能告警"""
        alerts = []
        
        # 检查系统指标
        system = self.get_system_metrics()
        if system.get('cpu_percent', 0) > 80:
            alerts.append(f"CPU使用率过高: {system['cpu_percent']:.1f}%")
        
        if system.get('memory_percent', 0) > 85:
            alerts.append(f"内存使用率过高: {system['memory_percent']:.1f}%")
        
        # 检查操作性能
        with self.lock:
            for operation, data in self.metrics.items():
                if not data:
                    continue
                
                recent_data = [m for m in data if time.time() - m['timestamp'] < 300]  # 最近5分钟
                if not recent_data:
                    continue
                
                durations = [m['duration'] if 'duration' in m else m['value'] for m in recent_data]
                avg_duration = sum(durations) / len(durations)
                
                # 不同操作的阈值
                thresholds = {
                    'fetch_ohlcv': 1.0,  # 1秒
                    'calculate_indicators': 0.1,  # 100ms
                    'cache_operation': 0.01  # 10ms
                }
                
                threshold = thresholds.get(operation, 0.5)
                if avg_duration > threshold:
                    alerts.append(f"{operation}平均响应时间过长: {avg_duration:.3f}s (阈值: {threshold}s)")
        
        return alerts

# 全局性能监控器实例
performance_monitor = PerformanceMonitor()

def monitor_performance(operation_name: str):
    """性能监控装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            performance_monitor.start_timer(operation_name)
            try:
                result = func(*args, **kwargs)
                performance_monitor.increment_counter(f"{operation_name}_success")
                return result
            except Exception as e:
                performance_monitor.increment_counter(f"{operation_name}_error")
                raise
            finally:
                performance_monitor.end_timer(operation_name)
        return wrapper
    return decorator
