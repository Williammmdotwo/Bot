"""
Athena Trader 性能监控仪表板
Performance Monitoring Dashboard for Athena Trader
"""

import time
import threading
from datetime import datetime, timedelta
import json
from typing import Dict, List, Any, Optional
import logging

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)

# 全局仪表板实例
_dashboard_instance = None


class PerformanceDashboard:
    """性能监控仪表板"""

    def __init__(self, max_history: int = 100):
        """
        初始化性能监控仪表板

        Args:
            max_history: 保留的历史数据最大数量
        """
        self.max_history = max_history
        self._running = False
        self._monitor_thread = None
        self._stop_event = threading.Event()

        # 请求统计
        self.request_count = 0
        self.error_count = 0
        self.start_time = time.time()
        self.response_times = []

        # 指标历史
        self.metrics_history: Dict[str, List[Dict[str, Any]]] = {
            'system.cpu_percent': [],
            'system.memory_percent': [],
            'system.disk_percent': [],
            'process.cpu_percent': [],
            'application.uptime_seconds': [],
            'application.error_rate': [],
            'application.avg_response_time': []
        }

        # 告警列表
        self.alerts: List[Dict[str, Any]] = []

        # 阈值配置
        self.thresholds = {
            'cpu_usage': 80.0,        # CPU使用率阈值
            'memory_usage': 85.0,     # 内存使用率阈值
            'disk_usage': 90.0,       # 磁盘使用率阈值
            'error_rate': 5.0,        # 错误率阈值（错误/分钟）
            'response_time': 1000.0   # 响应时间阈值（毫秒）
        }

        logger.info("PerformanceDashboard initialized")

    def start_monitoring(self, interval: int = 10):
        """
        启动监控

        Args:
            interval: 监控间隔（秒）
        """
        if self._running:
            logger.warning("监控已经在运行中")
            return

        self._running = True
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, args=(interval,), daemon=True)
        self._monitor_thread.start()
        logger.info(f"监控已启动，间隔: {interval}秒")

    def stop_monitoring(self):
        """停止监控"""
        if not self._running:
            logger.warning("监控未在运行")
            return

        self._running = False
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("监控已停止")

    def _monitor_loop(self, interval: int):
        """监控循环"""
        while not self._stop_event.is_set():
            try:
                # 收集系统指标
                self._collect_system_metrics()

                # 计算应用指标
                self._calculate_application_metrics()

                # 检查告警
                self._check_alerts()

                # 等待下一次采集
                self._stop_event.wait(interval)

            except Exception as e:
                logger.error(f"监控循环错误: {e}", exc_info=True)

    def _collect_system_metrics(self):
        """收集系统指标"""
        timestamp = datetime.now().isoformat()

        if psutil:
            try:
                # CPU 使用率
                cpu_percent = psutil.cpu_percent(interval=0.1)
                self._add_metric('system.cpu_percent', cpu_percent, timestamp)

                # 内存使用率
                memory = psutil.virtual_memory()
                self._add_metric('system.memory_percent', memory.percent, timestamp)

                # 磁盘使用率
                disk = psutil.disk_usage('/')
                self._add_metric('system.disk_percent', disk.percent, timestamp)

                # 进程 CPU 使用率
                process = psutil.Process()
                process_cpu = process.cpu_percent(interval=0.1)
                self._add_metric('process.cpu_percent', process_cpu, timestamp)

            except Exception as e:
                logger.error(f"收集系统指标失败: {e}")

        # 应用运行时间
        uptime = time.time() - self.start_time
        self._add_metric('application.uptime_seconds', uptime, timestamp)

    def _calculate_application_metrics(self):
        """计算应用指标"""
        timestamp = datetime.now().isoformat()

        # 计算错误率
        error_rate = self._calculate_error_rate()
        self._add_metric('application.error_rate', error_rate, timestamp)

        # 计算平均响应时间
        avg_response_time = self._calculate_avg_response_time()
        self._add_metric('application.avg_response_time', avg_response_time, timestamp)

    def _add_metric(self, metric_name: str, value: Any, timestamp: str):
        """
        添加指标到历史记录

        Args:
            metric_name: 指标名称
            value: 指标值
            timestamp: 时间戳
        """
        if metric_name not in self.metrics_history:
            self.metrics_history[metric_name] = []

        self.metrics_history[metric_name].append({
            'timestamp': timestamp,
            'value': value
        })

        # 限制历史记录数量
        if len(self.metrics_history[metric_name]) > self.max_history:
            self.metrics_history[metric_name] = self.metrics_history[metric_name][-self.max_history:]

    def record_request(self, response_time: float, success: bool):
        """
        记录请求

        Args:
            response_time: 响应时间（毫秒）
            success: 是否成功
        """
        self.request_count += 1
        self.response_times.append(response_time)

        if not success:
            self.error_count += 1

        # 限制响应时间历史记录
        if len(self.response_times) > self.max_history:
            self.response_times = self.response_times[-self.max_history:]

    def _calculate_error_rate(self) -> float:
        """
        计算错误率（错误/分钟）

        Returns:
            float: 错误率
        """
        elapsed_minutes = (time.time() - self.start_time) / 60.0
        if elapsed_minutes <= 0:
            return 0.0

        return self.error_count / elapsed_minutes

    def _calculate_avg_response_time(self) -> float:
        """
        计算平均响应时间

        Returns:
            float: 平均响应时间（毫秒）
        """
        if not self.response_times:
            return 0.0

        return sum(self.response_times) / len(self.response_times)

    def _check_alerts(self):
        """检查并生成告警"""
        # 检查 CPU 使用率
        cpu_history = self.metrics_history.get('system.cpu_percent', [])
        if cpu_history and cpu_history[-1]['value'] > self.thresholds['cpu_usage']:
            self._create_alert('cpu_high', 'warning',
                             f"CPU使用率过高: {cpu_history[-1]['value']:.1f}%")

        # 检查内存使用率
        memory_history = self.metrics_history.get('system.memory_percent', [])
        if memory_history and memory_history[-1]['value'] > self.thresholds['memory_usage']:
            self._create_alert('memory_high', 'warning',
                             f"内存使用率过高: {memory_history[-1]['value']:.1f}%")

        # 检查磁盘使用率
        disk_history = self.metrics_history.get('system.disk_percent', [])
        if disk_history and disk_history[-1]['value'] > self.thresholds['disk_usage']:
            self._create_alert('disk_high', 'critical',
                             f"磁盘使用率过高: {disk_history[-1]['value']:.1f}%")

        # 检查错误率
        error_rate_history = self.metrics_history.get('application.error_rate', [])
        if error_rate_history and error_rate_history[-1]['value'] > self.thresholds['error_rate']:
            self._create_alert('error_rate_high', 'critical',
                             f"错误率过高: {error_rate_history[-1]['value']:.2f}/分钟")

        # 检查响应时间
        response_time_history = self.metrics_history.get('application.avg_response_time', [])
        if response_time_history and response_time_history[-1]['value'] > self.thresholds['response_time']:
            self._create_alert('response_time_high', 'warning',
                             f"平均响应时间过长: {response_time_history[-1]['value']:.0f}ms")

    def _create_alert(self, alert_type: str, level: str, message: str):
        """
        创建告警

        Args:
            alert_type: 告警类型
            level: 告警级别 (info, warning, critical)
            message: 告警消息
        """
        alert = {
            'type': alert_type,
            'level': level,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }

        # 检查是否为重复告警
        if not self._is_duplicate_alert(alert):
            self.alerts.append(alert)
            logger.warning(f"告警: {message}")

    def _is_duplicate_alert(self, alert: Dict[str, Any]) -> bool:
        """
        检查是否为重复告警（5分钟内相同类型）

        Args:
            alert: 待检查的告警

        Returns:
            bool: 是否为重复告警
        """
        now = datetime.now()
        five_minutes_ago = now - timedelta(minutes=5)

        for existing_alert in self.alerts:
            if (existing_alert['type'] == alert['type'] and
                existing_alert['level'] == alert['level']):

                alert_time = datetime.fromisoformat(existing_alert['timestamp'])
                if alert_time > five_minutes_ago:
                    return True

        return False

    def get_current_metrics(self) -> Dict[str, Any]:
        """
        获取当前指标

        Returns:
            dict: 当前指标
        """
        current_metrics = {}

        for metric_name, history in self.metrics_history.items():
            if history:
                current_metrics[metric_name] = history[-1]['value']
            else:
                current_metrics[metric_name] = 0.0

        return current_metrics

    def get_metrics_history(self, metric_name: str, minutes: int = 60) -> List[Dict[str, Any]]:
        """
        获取指标历史

        Args:
            metric_name: 指标名称
            minutes: 获取最近多少分钟的历史

        Returns:
            list: 指标历史
        """
        if metric_name not in self.metrics_history:
            return []

        history = self.metrics_history[metric_name]
        cutoff_time = datetime.now() - timedelta(minutes=minutes)

        filtered = [
            item for item in history
            if datetime.fromisoformat(item['timestamp']) > cutoff_time
        ]

        return filtered

    def get_alerts(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        获取告警

        Args:
            hours: 获取最近多少小时的告警

        Returns:
            list: 告警列表
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)

        filtered = [
            alert for alert in self.alerts
            if datetime.fromisoformat(alert['timestamp']) > cutoff_time
        ]

        return filtered

    def _get_system_status(self) -> str:
        """
        获取系统状态

        Returns:
            str: 系统状态 (healthy, degraded, critical)
        """
        # 检查是否有 critical 级别的告警
        critical_alerts = [a for a in self.alerts if a['level'] == 'critical']
        if critical_alerts:
            return 'critical'

        # 检查是否有 warning 级别的告警
        warning_alerts = [a for a in self.alerts if a['level'] == 'warning']
        if warning_alerts:
            return 'degraded'

        return 'healthy'

    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        获取仪表板数据

        Returns:
            dict: 仪表板数据
        """
        return {
            'timestamp': datetime.now().isoformat(),
            'status': self._get_system_status(),
            'metrics': self.get_current_metrics(),
            'alerts': self.get_alerts(hours=1),
            'summary': {
                'total_requests': self.request_count,
                'total_errors': self.error_count,
                'avg_response_time_ms': self._calculate_avg_response_time(),
                'error_rate': self._calculate_error_rate(),
                'uptime_seconds': time.time() - self.start_time
            },
            'thresholds': self.thresholds.copy()
        }

    def update_threshold(self, metric_name: str, value: float):
        """
        更新阈值

        Args:
            metric_name: 指标名称
            value: 阈值
        """
        if metric_name in self.thresholds:
            self.thresholds[metric_name] = value
            logger.info(f"阈值已更新: {metric_name} = {value}")
        else:
            logger.warning(f"未知的指标: {metric_name}")

    def clear_alerts(self):
        """清除所有告警"""
        self.alerts.clear()
        logger.info("所有告警已清除")

    def export_metrics(self, filename: str, hours: int = 24):
        """
        导出指标到文件

        Args:
            filename: 文件名
            hours: 导出最近多少小时的指标
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)

        filtered_history = {}
        for metric_name, history in self.metrics_history.items():
            filtered_history[metric_name] = [
                item for item in history
                if datetime.fromisoformat(item['timestamp']) > cutoff_time
            ]

        export_data = {
            'export_time': datetime.now().isoformat(),
            'dashboard_data': self.get_dashboard_data(),
            'metrics_history': filtered_history
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        logger.info(f"指标已导出到: {filename}")


def get_dashboard() -> PerformanceDashboard:
    """
    获取全局仪表板实例（单例模式）

    Returns:
        PerformanceDashboard: 全局仪表板实例
    """
    global _dashboard_instance

    if _dashboard_instance is None:
        _dashboard_instance = PerformanceDashboard()

    return _dashboard_instance


def start_monitoring(interval: int = 10):
    """
    启动全局监控

    Args:
        interval: 监控间隔（秒）
    """
    dashboard = get_dashboard()
    dashboard.start_monitoring(interval)


def stop_monitoring():
    """停止全局监控"""
    dashboard = get_dashboard()
    dashboard.stop_monitoring()
