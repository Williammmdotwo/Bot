"""
Athena Trader 性能监控仪表板
Performance Monitoring Dashboard for Athena Trader
"""

import time
import psutil
import threading
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json
import logging
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

class PerformanceDashboard:
    """性能监控仪表板"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics_history = defaultdict(lambda: deque(maxlen=max_history))
        self.alerts = []
        self.thresholds = {
            'cpu_usage': 80.0,      # CPU使用率阈值
            'memory_usage': 85.0,    # 内存使用率阈值
            'disk_usage': 90.0,      # 磁盘使用率阈值
            'error_rate': 5.0,        # 错误率阈值（每分钟）
            'response_time': 1000.0    # 响应时间阈值（毫秒）
        }
        self.start_time = time.time()
        self.error_count = 0
        self.request_count = 0
        self.response_times = deque(maxlen=100)
        self._running = False
        self._monitor_thread = None
        
    def start_monitoring(self, interval: int = 5):
        """启动监控"""
        if self._running:
            logger.warning("监控已经在运行中")
            return
            
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, args=(interval,))
        self._monitor_thread.daemon = True
        self._monitor_thread.start()
        logger.info(f"性能监控已启动，监控间隔: {interval}秒")
        
    def stop_monitoring(self):
        """停止监控"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=10)
        logger.info("性能监控已停止")
        
    def _monitor_loop(self, interval: int):
        """监控循环"""
        while self._running:
            try:
                self._collect_system_metrics()
                self._check_alerts()
                time.sleep(interval)
            except Exception as e:
                logger.error(f"监控循环出错: {e}")
                time.sleep(interval)
                
    def _collect_system_metrics(self):
        """收集系统指标"""
        timestamp = datetime.now()
        
        # CPU指标
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        # 内存指标
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used = memory.used / (1024**3)  # GB
        memory_total = memory.total / (1024**3)  # GB
        
        # 磁盘指标
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        disk_used = disk.used / (1024**3)  # GB
        disk_total = disk.total / (1024**3)  # GB
        
        # 网络指标
        network = psutil.net_io_counters()
        network_bytes_sent = network.bytes_sent / (1024**2)  # MB
        network_bytes_recv = network.bytes_recv / (1024**2)  # MB
        
        # 进程指标
        process = psutil.Process()
        process_cpu = process.cpu_percent()
        process_memory = process.memory_info().rss / (1024**2)  # MB
        
        metrics = {
            'timestamp': timestamp.isoformat(),
            'system': {
                'cpu_percent': cpu_percent,
                'cpu_count': cpu_count,
                'memory_percent': memory_percent,
                'memory_used_gb': memory_used,
                'memory_total_gb': memory_total,
                'disk_percent': disk_percent,
                'disk_used_gb': disk_used,
                'disk_total_gb': disk_total,
                'network_bytes_sent_mb': network_bytes_sent,
                'network_bytes_recv_mb': network_bytes_recv
            },
            'process': {
                'cpu_percent': process_cpu,
                'memory_mb': process_memory,
                'pid': process.pid,
                'status': process.status()
            },
            'application': {
                'uptime_seconds': time.time() - self.start_time,
                'error_count': self.error_count,
                'request_count': self.request_count,
                'error_rate': self._calculate_error_rate(),
                'avg_response_time': self._calculate_avg_response_time(),
                'active_threads': threading.active_count()
            }
        }
        
        # 保存到历史记录
        for category, values in metrics.items():
            if isinstance(values, dict):
                for key, value in values.items():
                    metric_key = f"{category}.{key}"
                    self.metrics_history[metric_key].append({
                        'timestamp': timestamp.isoformat(),
                        'value': value
                    })
                
    def _calculate_error_rate(self) -> float:
        """计算错误率（每分钟）"""
        if self.request_count == 0:
            return 0.0
        uptime_minutes = (time.time() - self.start_time) / 60
        if uptime_minutes == 0:
            return 0.0
        return (self.error_count / uptime_minutes) * 100
        
    def _calculate_avg_response_time(self) -> float:
        """计算平均响应时间"""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)
        
    def _check_alerts(self):
        """检查告警条件"""
        current_metrics = {}
        
        # 获取最新的指标值
        for metric_key, history in self.metrics_history.items():
            if history:
                current_metrics[metric_key] = history[-1]['value']
                
        alerts = []
        
        # CPU使用率告警
        if current_metrics.get('system.cpu_percent', 0) > self.thresholds['cpu_usage']:
            alerts.append({
                'type': 'cpu_high',
                'level': 'warning',
                'message': f"CPU使用率过高: {current_metrics['system.cpu_percent']:.1f}%",
                'timestamp': datetime.now().isoformat(),
                'value': current_metrics['system.cpu_percent']
            })
            
        # 内存使用率告警
        if current_metrics.get('system.memory_percent', 0) > self.thresholds['memory_usage']:
            alerts.append({
                'type': 'memory_high',
                'level': 'warning',
                'message': f"内存使用率过高: {current_metrics['system.memory_percent']:.1f}%",
                'timestamp': datetime.now().isoformat(),
                'value': current_metrics['system.memory_percent']
            })
            
        # 磁盘使用率告警
        if current_metrics.get('system.disk_percent', 0) > self.thresholds['disk_usage']:
            alerts.append({
                'type': 'disk_high',
                'level': 'critical',
                'message': f"磁盘使用率过高: {current_metrics['system.disk_percent']:.1f}%",
                'timestamp': datetime.now().isoformat(),
                'value': current_metrics['system.disk_percent']
            })
            
        # 错误率告警
        error_rate = current_metrics.get('application.error_rate', 0)
        if error_rate > self.thresholds['error_rate']:
            alerts.append({
                'type': 'error_rate_high',
                'level': 'critical',
                'message': f"错误率过高: {error_rate:.2f}/分钟",
                'timestamp': datetime.now().isoformat(),
                'value': error_rate
            })
            
        # 响应时间告警
        avg_response_time = current_metrics.get('application.avg_response_time', 0)
        if avg_response_time > self.thresholds['response_time']:
            alerts.append({
                'type': 'response_time_high',
                'level': 'warning',
                'message': f"平均响应时间过长: {avg_response_time:.2f}ms",
                'timestamp': datetime.now().isoformat(),
                'value': avg_response_time
            })
            
        # 添加新告警
        for alert in alerts:
            if not self._is_duplicate_alert(alert):
                self.alerts.append(alert)
                logger.warning(f"性能告警: {alert['message']}")
                
    def _is_duplicate_alert(self, new_alert: Dict[str, Any]) -> bool:
        """检查是否为重复告警"""
        if not self.alerts:
            return False
            
        # 检查最近5分钟内是否有相同类型的告警
        recent_time = datetime.now() - timedelta(minutes=5)
        recent_alerts = [a for a in self.alerts 
                         if datetime.fromisoformat(a['timestamp']) > recent_time]
        
        for alert in recent_alerts:
            if alert['type'] == new_alert['type']:
                return True
        return False
        
    def record_request(self, response_time: float, success: bool = True):
        """记录请求"""
        self.request_count += 1
        self.response_times.append(response_time)
        if not success:
            self.error_count += 1
            
    def get_current_metrics(self) -> Dict[str, Any]:
        """获取当前指标"""
        current_metrics = {}
        
        # 获取最新的指标值
        for metric_key, history in self.metrics_history.items():
            if history:
                current_metrics[metric_key] = history[-1]['value']
                
        return current_metrics
        
    def get_metrics_history(self, metric_key: str, minutes: int = 60) -> List[Dict[str, Any]]:
        """获取指标历史"""
        if metric_key not in self.metrics_history:
            return []
            
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [
            entry for entry in self.metrics_history[metric_key]
            if datetime.fromisoformat(entry['timestamp']) > cutoff_time
        ]
        
    def get_alerts(self, hours: int = 24) -> List[Dict[str, Any]]:
        """获取告警历史"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [
            alert for alert in self.alerts
            if datetime.fromisoformat(alert['timestamp']) > cutoff_time
        ]
        
    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取仪表板数据"""
        current_metrics = self.get_current_metrics()
        recent_alerts = self.get_alerts(hours=1)
        
        return {
            'timestamp': datetime.now().isoformat(),
            'status': self._get_system_status(),
            'metrics': current_metrics,
            'alerts': recent_alerts,
            'summary': {
                'uptime_hours': (time.time() - self.start_time) / 3600,
                'total_requests': self.request_count,
                'total_errors': self.error_count,
                'error_rate_percent': self._calculate_error_rate(),
                'avg_response_time_ms': self._calculate_avg_response_time()
            },
            'thresholds': self.thresholds
        }
        
    def _get_system_status(self) -> str:
        """获取系统状态"""
        current_metrics = self.get_current_metrics()
        
        # 检查关键指标
        cpu_ok = current_metrics.get('system.cpu_percent', 0) < self.thresholds['cpu_usage']
        memory_ok = current_metrics.get('system.memory_percent', 0) < self.thresholds['memory_usage']
        disk_ok = current_metrics.get('system.disk_percent', 0) < self.thresholds['disk_usage']
        error_rate_ok = current_metrics.get('application.error_rate', 0) < self.thresholds['error_rate']
        
        if all([cpu_ok, memory_ok, disk_ok, error_rate_ok]):
            return 'healthy'
        elif any([not cpu_ok, not memory_ok]):
            return 'degraded'
        else:
            return 'critical'
            
    def export_metrics(self, filename: str, hours: int = 24):
        """导出指标数据"""
        data = {
            'export_time': datetime.now().isoformat(),
            'dashboard_data': self.get_dashboard_data(),
            'metrics_history': {}
        }
        
        # 导出所有指标的历史数据
        cutoff_time = datetime.now() - timedelta(hours=hours)
        for metric_key, history in self.metrics_history.items():
            filtered_history = [
                entry for entry in history
                if datetime.fromisoformat(entry['timestamp']) > cutoff_time
            ]
            data['metrics_history'][metric_key] = filtered_history
            
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"指标数据已导出到: {filename}")
        except Exception as e:
            logger.error(f"导出指标数据失败: {e}")
            
    def clear_alerts(self):
        """清除告警历史"""
        self.alerts.clear()
        logger.info("告警历史已清除")
        
    def update_threshold(self, metric: str, value: float):
        """更新告警阈值"""
        if metric in self.thresholds:
            self.thresholds[metric] = value
            logger.info(f"告警阈值已更新: {metric} = {value}")
        else:
            logger.warning(f"未知的指标: {metric}")


# 全局监控实例
_dashboard_instance = None

def get_dashboard() -> PerformanceDashboard:
    """获取全局监控实例"""
    global _dashboard_instance
    if _dashboard_instance is None:
        _dashboard_instance = PerformanceDashboard()
    return _dashboard_instance

def start_monitoring(interval: int = 5):
    """启动全局监控"""
    dashboard = get_dashboard()
    dashboard.start_monitoring(interval)

def stop_monitoring():
    """停止全局监控"""
    dashboard = get_dashboard()
    dashboard.stop_monitoring()
