"""
PerformanceDashboard 单元测试
优化 Mock 策略以提高代码覆盖率
"""

import pytest
import time
import threading
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from src.monitoring.dashboard import PerformanceDashboard, get_dashboard


class TestPerformanceDashboard:
    """PerformanceDashboard 测试类"""

    def setup_method(self):
        """测试前设置"""
        self.dashboard = PerformanceDashboard(max_history=100)

    def teardown_method(self):
        """测试后清理"""
        if self.dashboard._running:
            self.dashboard.stop_monitoring()

    def test_init(self):
        """测试初始化"""
        assert self.dashboard.max_history == 100
        assert not self.dashboard._running
        assert self.dashboard.error_count == 0
        assert self.dashboard.request_count == 0
        assert len(self.dashboard.alerts) == 0
        assert 'cpu_usage' in self.dashboard.thresholds
        assert 'memory_usage' in self.dashboard.thresholds

    def test_start_stop_monitoring(self):
        """测试启动和停止监控"""
        # 测试启动
        self.dashboard.start_monitoring(interval=1)
        assert self.dashboard._running
        assert self.dashboard._monitor_thread is not None

        # 测试重复启动
        with patch('src.monitoring.dashboard.logger') as mock_logger:
            self.dashboard.start_monitoring()
            mock_logger.warning.assert_called_with("监控已经在运行中")

        # 测试停止
        self.dashboard.stop_monitoring()
        assert not self.dashboard._running

    def test_record_request(self):
        """测试记录请求"""
        # 记录成功请求
        self.dashboard.record_request(response_time=100.0, success=True)
        assert self.dashboard.request_count == 1
        assert self.dashboard.error_count == 0
        assert len(self.dashboard.response_times) == 1
        assert self.dashboard.response_times[0] == 100.0

        # 记录失败请求
        self.dashboard.record_request(response_time=200.0, success=False)
        assert self.dashboard.request_count == 2
        assert self.dashboard.error_count == 1
        assert len(self.dashboard.response_times) == 2

    def test_calculate_error_rate(self):
        """测试计算错误率"""
        # 无请求时
        assert self.dashboard._calculate_error_rate() == 0.0

        # 模拟一些请求和错误
        self.dashboard.request_count = 100
        self.dashboard.error_count = 5
        self.dashboard.start_time = time.time() - 300  # 5分钟前

        error_rate = self.dashboard._calculate_error_rate()
        # 5错误/5分钟 = 1.0/分钟
        assert error_rate > 0.5  # 至少应该大于0.5

    def test_calculate_avg_response_time(self):
        """测试计算平均响应时间"""
        # 无响应时间时
        assert self.dashboard._calculate_avg_response_time() == 0.0

        # 添加一些响应时间
        self.dashboard.response_times.extend([100.0, 200.0, 300.0])
        avg_time = self.dashboard._calculate_avg_response_time()
        assert avg_time == 200.0

    def test_collect_system_metrics_real(self):
        """测试收集系统指标（真实调用，不Mock psutil）"""
        # 不Mock psutil，让真实代码执行以提高覆盖率
        self.dashboard._collect_system_metrics()

        # 验证指标被收集
        assert 'system.cpu_percent' in self.dashboard.metrics_history
        assert 'system.memory_percent' in self.dashboard.metrics_history
        assert 'system.disk_percent' in self.dashboard.metrics_history
        assert 'process.cpu_percent' in self.dashboard.metrics_history
        assert 'application.uptime_seconds' in self.dashboard.metrics_history

        # 验证指标值是合理的范围
        cpu_history = self.dashboard.metrics_history['system.cpu_percent']
        assert len(cpu_history) == 1
        assert 0 <= cpu_history[0]['value'] <= 100  # CPU使用率应该在0-100之间

        memory_history = self.dashboard.metrics_history['system.memory_percent']
        assert 0 <= memory_history[0]['value'] <= 100  # 内存使用率应该在0-100之间

    def test_check_alerts_cpu_high(self):
        """测试CPU高使用率告警"""
        # 先收集一些真实的指标
        self.dashboard._collect_system_metrics()

        # 模拟高CPU使用率
        self.dashboard.metrics_history['system.cpu_percent'][-1]['value'] = 95.0  # 超过80%阈值

        self.dashboard._check_alerts()

        assert len(self.dashboard.alerts) == 1
        alert = self.dashboard.alerts[0]
        assert alert['type'] == 'cpu_high'
        assert alert['level'] == 'warning'
        assert 'CPU使用率过高' in alert['message']

    def test_check_alerts_memory_high(self):
        """测试内存高使用率告警"""
        # 先收集一些真实的指标
        self.dashboard._collect_system_metrics()

        # 模拟高内存使用率
        self.dashboard.metrics_history['system.memory_percent'][-1]['value'] = 95.0  # 超过85%阈值

        self.dashboard._check_alerts()

        assert len(self.dashboard.alerts) == 1
        alert = self.dashboard.alerts[0]
        assert alert['type'] == 'memory_high'
        assert alert['level'] == 'warning'
        assert '内存使用率过高' in alert['message']

    def test_check_alerts_disk_high(self):
        """测试磁盘高使用率告警"""
        # 先收集一些真实的指标
        self.dashboard._collect_system_metrics()

        # 模拟高磁盘使用率
        self.dashboard.metrics_history['system.disk_percent'][-1]['value'] = 99.0  # 超过90%阈值

        self.dashboard._check_alerts()

        assert len(self.dashboard.alerts) == 1
        alert = self.dashboard.alerts[0]
        assert alert['type'] == 'disk_high'
        assert alert['level'] == 'critical'
        assert '磁盘使用率过高' in alert['message']

    def test_check_alerts_error_rate_high(self):
        """测试错误率高告警"""
        # 模拟高错误率
        self.dashboard.request_count = 100
        self.dashboard.error_count = 20
        self.dashboard.start_time = time.time() - 60  # 1分钟前

        # 先计算错误率
        error_rate = self.dashboard._calculate_error_rate()

        # 添加应用指标到历史记录
        self.dashboard.metrics_history['application.error_rate'].append({
            'timestamp': datetime.now().isoformat(),
            'value': error_rate
        })

        self.dashboard._check_alerts()

        # 验证告警生成（错误率应该是20/分钟，超过5%阈值）
        assert len(self.dashboard.alerts) == 1
        alert = self.dashboard.alerts[0]
        assert alert['type'] == 'error_rate_high'
        assert alert['level'] == 'critical'
        assert '错误率过高' in alert['message']

    def test_check_alerts_response_time_high(self):
        """测试响应时间长告警"""
        # 模拟长响应时间
        self.dashboard.response_times.extend([1500.0, 1200.0, 1800.0])

        # 计算平均响应时间
        avg_response_time = self.dashboard._calculate_avg_response_time()

        # 添加应用指标到历史记录
        self.dashboard.metrics_history['application.avg_response_time'].append({
            'timestamp': datetime.now().isoformat(),
            'value': avg_response_time
        })

        self.dashboard._check_alerts()

        assert len(self.dashboard.alerts) == 1
        alert = self.dashboard.alerts[0]
        assert alert['type'] == 'response_time_high'
        assert alert['level'] == 'warning'
        assert '平均响应时间过长' in alert['message']

    def test_check_alerts_no_alert(self):
        """测试无告警情况"""
        # 收集正常的系统指标（不应该触发告警）
        self.dashboard._collect_system_metrics()

        self.dashboard._check_alerts()

        # 正常情况下不应该有告警
        assert len(self.dashboard.alerts) == 0

    def test_is_duplicate_alert(self):
        """测试重复告警检查"""
        # 添加一个告警
        existing_alert = {
            'type': 'cpu_high',
            'level': 'warning',
            'message': 'CPU使用率过高: 85.0%',
            'timestamp': datetime.now().isoformat(),
            'value': 85.0
        }
        self.dashboard.alerts.append(existing_alert)

        # 测试相同类型的告警（在5分钟内）
        new_alert = {
            'type': 'cpu_high',
            'level': 'warning',
            'message': 'CPU使用率过高: 86.0%',
            'timestamp': datetime.now().isoformat(),
            'value': 86.0
        }

        assert self.dashboard._is_duplicate_alert(new_alert) is True

        # 测试不同类型的告警
        different_alert = {
            'type': 'memory_high',
            'level': 'warning',
            'message': '内存使用率过高: 90.0%',
            'timestamp': datetime.now().isoformat(),
            'value': 90.0
        }

        assert self.dashboard._is_duplicate_alert(different_alert) is False

    def test_get_current_metrics(self):
        """测试获取当前指标"""
        # 收集真实的系统指标
        self.dashboard._collect_system_metrics()

        current_metrics = self.dashboard.get_current_metrics()

        # 验证指标存在且类型正确
        assert 'system.cpu_percent' in current_metrics
        assert isinstance(current_metrics['system.cpu_percent'], (int, float))
        assert 0 <= current_metrics['system.cpu_percent'] <= 100

        assert 'system.memory_percent' in current_metrics
        assert isinstance(current_metrics['system.memory_percent'], (int, float))
        assert 0 <= current_metrics['system.memory_percent'] <= 100

    def test_get_metrics_history(self):
        """测试获取指标历史"""
        # 收集两次指标以产生历史数据
        self.dashboard._collect_system_metrics()
        time.sleep(0.1)
        self.dashboard._collect_system_metrics()

        # 获取最近60分钟的历史
        history = self.dashboard.get_metrics_history('system.cpu_percent', minutes=60)
        assert len(history) >= 1
        assert all('timestamp' in item and 'value' in item for item in history)

        # 获取最近0.01分钟的历史（应该只返回最近的数据）
        history = self.dashboard.get_metrics_history('system.cpu_percent', minutes=0.01)
        # 可能是1条或2条，取决于时间间隔
        assert len(history) <= 2

    def test_get_alerts(self):
        """测试获取告警"""
        # 添加一些告警
        now = datetime.now()
        old_time = now - timedelta(hours=2)

        self.dashboard.alerts.extend([
            {
                'type': 'cpu_high',
                'level': 'warning',
                'message': 'CPU使用率过高',
                'timestamp': old_time.isoformat(),
                'value': 85.0
            },
            {
                'type': 'memory_high',
                'level': 'warning',
                'message': '内存使用率过高',
                'timestamp': now.isoformat(),
                'value': 90.0
            }
        ])

        # 获取最近24小时的告警
        alerts = self.dashboard.get_alerts(hours=24)
        assert len(alerts) == 2

        # 获取最近1小时的告警
        alerts = self.dashboard.get_alerts(hours=1)
        assert len(alerts) == 1
        assert alerts[0]['type'] == 'memory_high'

    def test_get_system_status(self):
        """测试获取系统状态"""
        # 收集真实的系统指标
        self.dashboard._collect_system_metrics()

        status = self.dashboard._get_system_status()

        # 状态应该是 healthy, degraded, 或 critical
        assert status in ['healthy', 'degraded', 'critical']

    def test_get_dashboard_data(self):
        """测试获取仪表板数据"""
        # 添加一些基础数据
        self.dashboard.request_count = 100
        self.dashboard.error_count = 5
        self.dashboard.response_times.extend([100.0, 200.0, 300.0])

        dashboard_data = self.dashboard.get_dashboard_data()

        # 验证数据结构
        assert 'timestamp' in dashboard_data
        assert 'status' in dashboard_data
        assert 'metrics' in dashboard_data
        assert 'alerts' in dashboard_data
        assert 'summary' in dashboard_data
        assert 'thresholds' in dashboard_data

        # 验证摘要数据
        assert dashboard_data['summary']['total_requests'] == 100
        assert dashboard_data['summary']['total_errors'] == 5
        assert dashboard_data['summary']['avg_response_time_ms'] == 200.0

        # 验证状态
        assert dashboard_data['status'] in ['healthy', 'degraded', 'critical']

    def test_update_threshold(self):
        """测试更新阈值"""
        # 更新存在的阈值
        self.dashboard.update_threshold('cpu_usage', 90.0)
        assert self.dashboard.thresholds['cpu_usage'] == 90.0

        # 尝试更新不存在的阈值
        with patch('src.monitoring.dashboard.logger') as mock_logger:
            self.dashboard.update_threshold('invalid_metric', 100.0)
            mock_logger.warning.assert_called_with("未知的指标: invalid_metric")

    def test_clear_alerts(self):
        """测试清除告警"""
        # 添加一些告警
        self.dashboard.alerts.extend([
            {'type': 'cpu_high', 'message': 'CPU高'},
            {'type': 'memory_high', 'message': '内存高'}
        ])

        assert len(self.dashboard.alerts) == 2

        self.dashboard.clear_alerts()
        assert len(self.dashboard.alerts) == 0

    @patch('builtins.open', create=True)
    def test_export_metrics(self, mock_open):
        """测试导出指标"""
        import json

        # 收集一些真实指标
        self.dashboard._collect_system_metrics()

        # Mock 文件写入
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        self.dashboard.export_metrics('test_metrics.json', hours=24)

        # 验证文件被打开
        mock_open.assert_called_once_with('test_metrics.json', 'w', encoding='utf-8')

        # 验证文件写入被调用
        mock_file.write.assert_called_once()

        # 验证写入的内容是有效的JSON
        written_content = mock_file.write.call_args[0][0]
        try:
            exported_data = json.loads(written_content)
            assert 'export_time' in exported_data
            assert 'dashboard_data' in exported_data
            assert 'metrics_history' in exported_data
        except json.JSONDecodeError:
            pytest.fail("导出的数据不是有效的JSON")


class TestGlobalDashboard:
    """全局仪表板测试"""

    def test_get_dashboard_singleton(self):
        """测试获取全局仪表板实例"""
        # 清除全局实例
        import src.monitoring.dashboard
        src.monitoring.dashboard._dashboard_instance = None

        dashboard1 = get_dashboard()
        dashboard2 = get_dashboard()

        assert dashboard1 is dashboard2
        assert isinstance(dashboard1, PerformanceDashboard)

    @patch('src.monitoring.dashboard.get_dashboard')
    def test_start_monitoring_global(self, mock_get_dashboard):
        """测试全局启动监控"""
        mock_dashboard = MagicMock()
        mock_get_dashboard.return_value = mock_dashboard

        from src.monitoring.dashboard import start_monitoring
        start_monitoring(interval=10)

        mock_dashboard.start_monitoring.assert_called_once_with(10)

    @patch('src.monitoring.dashboard.get_dashboard')
    def test_stop_monitoring_global(self, mock_get_dashboard):
        """测试全局停止监控"""
        mock_dashboard = MagicMock()
        mock_get_dashboard.return_value = mock_dashboard

        from src.monitoring.dashboard import stop_monitoring
        stop_monitoring()

        mock_dashboard.stop_monitoring.assert_called_once()


class TestPerformanceDashboardIntegration:
    """PerformanceDashboard 集成测试"""

    def test_monitoring_workflow(self):
        """测试完整的监控工作流"""
        dashboard = PerformanceDashboard(max_history=50)

        try:
            # 启动监控
            dashboard.start_monitoring(interval=1)

            # 等待一些指标收集
            time.sleep(2)

            # 记录一些请求
            for i in range(10):
                success = i % 4 != 0  # 25%失败率
                dashboard.record_request(response_time=100 + i * 10, success=success)

            # 获取仪表板数据
            data = dashboard.get_dashboard_data()

            # 验证数据结构
            assert 'timestamp' in data
            assert 'status' in data
            assert 'metrics' in data
            assert 'summary' in data

            # 验证请求统计
            assert data['summary']['total_requests'] == 10
            assert data['summary']['total_errors'] == 3  # 25% of 10, rounded

            # 验证指标历史
            current_metrics = dashboard.get_current_metrics()
            assert len(current_metrics) > 0

        finally:
            # 确保停止监控
            dashboard.stop_monitoring()

    def test_alert_workflow(self):
        """测试告警工作流"""
        dashboard = PerformanceDashboard()

        # 收集一些真实指标
        dashboard._collect_system_metrics()

        # 模拟高CPU使用率
        dashboard.metrics_history['system.cpu_percent'][-1]['value'] = 95.0

        # 检查告警
        dashboard._check_alerts()

        # 验证告警生成
        assert len(dashboard.alerts) == 1
        assert dashboard.alerts[0]['type'] == 'cpu_high'

        # 测试重复告警不会重复生成
        dashboard._check_alerts()
        assert len(dashboard.alerts) == 1  # 仍然是1个

        # 清除告警
        dashboard.clear_alerts()
        assert len(dashboard.alerts) == 0

    def test_multiple_collections(self):
        """测试多次收集指标"""
        dashboard = PerformanceDashboard()

        # 收集多次指标
        for _ in range(5):
            dashboard._collect_system_metrics()
            time.sleep(0.1)

        # 验证历史记录
        cpu_history = dashboard.metrics_history['system.cpu_percent']
        assert len(cpu_history) == 5

        # 验证所有数据都是有效的
        for item in cpu_history:
            assert 'timestamp' in item
            assert 'value' in item
            assert 0 <= item['value'] <= 100
