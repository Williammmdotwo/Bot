"""
业务指标监控模块测试
"""

import pytest
import asyncio
import time
import json
from unittest.mock import Mock, AsyncMock, patch
from src.monitoring.business_metrics import (
    TradingMetric, SystemMetric, BusinessMetricsCollector,
    get_business_metrics_collector, record_trading_signal,
    record_order_execution, record_system_performance, record_system_error
)


class TestTradingMetric:
    """交易指标测试"""
    
    def test_trading_metric_creation(self):
        """测试交易指标创建"""
        timestamp = time.time()
        metric = TradingMetric(
            timestamp=timestamp,
            symbol="BTC-USDT",
            metric_type="signal",
            value=0.85,
            metadata={"strength": "high"}
        )
        
        assert metric.timestamp == timestamp
        assert metric.symbol == "BTC-USDT"
        assert metric.metric_type == "signal"
        assert metric.value == 0.85
        assert metric.metadata["strength"] == "high"


class TestSystemMetric:
    """系统指标测试"""
    
    def test_system_metric_creation(self):
        """测试系统指标创建"""
        timestamp = time.time()
        metric = SystemMetric(
            timestamp=timestamp,
            service="data_manager",
            metric_type="response_time",
            value=0.15,
            metadata={"endpoint": "/api/data"}
        )
        
        assert metric.timestamp == timestamp
        assert metric.service == "data_manager"
        assert metric.metric_type == "response_time"
        assert metric.value == 0.15
        assert metric.metadata["endpoint"] == "/api/data"


class TestBusinessMetricsCollector:
    """业务指标收集器测试"""
    
    @pytest.fixture
    def mock_redis(self):
        """模拟Redis客户端"""
        redis_mock = AsyncMock()
        redis_mock.zadd = AsyncMock(return_value=1)
        redis_mock.expire = AsyncMock(return_value=True)
        redis_mock.lpush = AsyncMock(return_value=1)
        redis_mock.ltrim = AsyncMock(return_value=True)
        redis_mock.hset = AsyncMock(return_value=1)
        return redis_mock
    
    @pytest.fixture
    def collector(self, mock_redis):
        """创建指标收集器实例"""
        return BusinessMetricsCollector(redis_client=mock_redis)
    
    def test_collector_initialization(self, mock_redis):
        """测试收集器初始化"""
        collector = BusinessMetricsCollector(redis_client=mock_redis)
        
        assert collector.redis_client == mock_redis
        assert len(collector.metrics_buffer) == 0
        assert len(collector.alert_handlers) == 0
        assert collector.aggregation_window == 300
    
    def test_load_thresholds_default(self):
        """测试加载默认阈值"""
        collector = BusinessMetricsCollector()
        
        thresholds = collector.thresholds
        assert 'signal_generation' in thresholds
        assert 'order_execution' in thresholds
        assert 'position_management' in thresholds
        assert 'system_performance' in thresholds
        
        # 检查具体阈值
        assert thresholds['order_execution']['success_rate'] == 0.95
        assert thresholds['system_performance']['max_response_time'] == 1.0
    
    @pytest.mark.asyncio
    async def test_collect_trading_metric(self, collector, mock_redis):
        """测试收集交易指标"""
        metric = TradingMetric(
            timestamp=time.time(),
            symbol="BTC-USDT",
            metric_type="signal",
            value=0.85,
            metadata={}
        )
        
        await collector.collect_trading_metric(metric)
        
        # 检查是否添加到缓冲区
        assert len(collector.metrics_buffer) == 1
        assert collector.metrics_buffer[0] == metric
        
        # 检查是否存储到Redis
        mock_redis.zadd.assert_called_once()
        # expire可能被调用多次（指标存储 + 聚合），所以检查至少调用一次
        assert mock_redis.expire.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_collect_system_metric(self, collector, mock_redis):
        """测试收集系统指标"""
        metric = SystemMetric(
            timestamp=time.time(),
            service="data_manager",
            metric_type="response_time",
            value=0.15,
            metadata={}
        )
        
        await collector.collect_system_metric(metric)
        
        # 检查是否添加到缓冲区
        assert len(collector.metrics_buffer) == 1
        assert collector.metrics_buffer[0] == metric
        
        # 检查是否存储到Redis
        mock_redis.zadd.assert_called_once()
        # expire可能被调用多次（指标存储 + 聚合），所以检查至少调用一次
        assert mock_redis.expire.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_threshold_violation_detection(self, collector):
        """测试阈值违规检测"""
        # 添加告警处理器
        alerts = []
        async def alert_handler(alert):
            alerts.append(alert)
        
        collector.add_alert_handler(alert_handler)
        
        # 确保阈值配置正确 - 需要按metric_type配置
        collector.thresholds['response_time'] = {
            'max_response_time': 1.0
        }
        
        # 创建违反阈值的指标
        metric = SystemMetric(
            timestamp=time.time(),
            service="data_manager",
            metric_type="response_time",
            value=2.0,  # 超过最大响应时间1.0
            metadata={}
        )
        
        # 手动触发阈值检查
        await collector._check_system_thresholds(metric)
        
        # 检查是否触发告警
        assert len(alerts) == 1
        assert alerts[0]['type'] == 'threshold_violation'
        assert alerts[0]['metric_type'] == 'response_time'
        assert alerts[0]['current_value'] == 2.0
        assert alerts[0]['severity'] in ['warning', 'critical']
    
    def test_is_threshold_violated(self, collector):
        """测试阈值违规判断"""
        # 测试max阈值
        assert collector._is_threshold_violated(
            Mock(value=2.0), 'max_response_time', 1.0
        )
        assert not collector._is_threshold_violated(
            Mock(value=0.5), 'max_response_time', 1.0
        )
        
        # 测试min阈值
        assert collector._is_threshold_violated(
            Mock(value=0.05), 'min_success_rate', 0.1
        )
        assert not collector._is_threshold_violated(
            Mock(value=0.15), 'min_success_rate', 0.1
        )
        
        # 测试rate阈值
        assert collector._is_threshold_violated(
            Mock(value=0.8), 'success_rate', 0.9
        )
        assert not collector._is_threshold_violated(
            Mock(value=0.95), 'success_rate', 0.9
        )
    
    def test_get_severity(self, collector):
        """测试严重程度计算"""
        # 严重违规
        severity = collector._get_severity(
            Mock(value=2.0), 'max_response_time', 1.0
        )
        assert severity == 'critical'
        
        # 中等违规
        severity = collector._get_severity(
            Mock(value=1.3), 'max_response_time', 1.0
        )
        assert severity == 'warning'
        
        # 轻微违规
        severity = collector._get_severity(
            Mock(value=1.1), 'max_response_time', 1.0
        )
        assert severity == 'info'
    
    @pytest.mark.asyncio
    async def test_aggregate_metrics(self, collector):
        """测试指标聚合"""
        # 添加多个指标（确保在聚合窗口内）
        current_time = time.time()
        
        # 交易指标 - 确保在5分钟窗口内
        for i in range(5):
            metric = TradingMetric(
                timestamp=current_time - i * 10,  # 0-40秒前
                symbol="BTC-USDT",
                metric_type="signal",
                value=0.8 + i * 0.05,  # 0.8, 0.85, 0.9, 0.95, 1.0
                metadata={}
            )
            collector.metrics_buffer.append(metric)
        
        # 系统指标
        for i in range(3):
            metric = SystemMetric(
                timestamp=current_time - i * 10,  # 0-20秒前
                service="data_manager",
                metric_type="response_time",
                value=0.1 + i * 0.05,  # 0.1, 0.15, 0.2
                metadata={}
            )
            collector.metrics_buffer.append(metric)
        
        await collector._aggregate_metrics()
        
        # 检查聚合结果
        aggregated = collector._aggregated_metrics
        assert 'trading.signal' in aggregated
        assert 'system.response_time' in aggregated
        
        # 检查统计计算
        signal_stats = aggregated['trading.signal']
        assert signal_stats['count'] == 5
        expected_avg = (0.8 + 0.85 + 0.9 + 0.95 + 1.0) / 5  # 0.9
        assert abs(signal_stats['avg'] - expected_avg) < 0.01
        assert signal_stats['min'] == 0.8
        assert signal_stats['max'] == 1.0
        
        response_stats = aggregated['system.response_time']
        assert response_stats['count'] == 3
        expected_response_avg = (0.1 + 0.15 + 0.2) / 3  # 0.15
        assert abs(response_stats['avg'] - expected_response_avg) < 0.01
        assert response_stats['min'] == 0.1
        assert response_stats['max'] == 0.2
    
    @pytest.mark.asyncio
    async def test_get_metrics_summary(self, collector):
        """测试获取指标摘要"""
        # 添加测试数据
        current_time = time.time()
        
        # 交易指标
        trading_metric = TradingMetric(
            timestamp=current_time - 60,  # 1分钟前
            symbol="BTC-USDT",
            metric_type="signal",
            value=0.85,
            metadata={}
        )
        collector.metrics_buffer.append(trading_metric)
        
        # 系统指标
        system_metric = SystemMetric(
            timestamp=current_time - 30,  # 30秒前
            service="data_manager",
            metric_type="response_time",
            value=0.15,
            metadata={}
        )
        collector.metrics_buffer.append(system_metric)
        
        # 获取摘要
        summary = await collector.get_metrics_summary(time_window=120)  # 2分钟窗口
        
        assert summary['time_window'] == 120
        assert summary['total_metrics'] == 2
        assert 'trading_metrics' in summary
        assert 'system_metrics' in summary
        
        # 检查交易指标统计
        trading_stats = summary['trading_metrics']['signal']
        assert trading_stats['count'] == 1
        assert trading_stats['symbols'] == ['BTC-USDT']
        assert trading_stats['avg_value'] == 0.85
        
        # 检查系统指标统计
        system_stats = summary['system_metrics']['response_time']
        assert system_stats['count'] == 1
        assert system_stats['services'] == ['data_manager']
        assert system_stats['avg_value'] == 0.15
    
    @pytest.mark.asyncio
    async def test_get_real_time_dashboard_data(self, collector, mock_redis):
        """测试获取实时仪表板数据"""
        # 模拟Redis返回的告警数据
        mock_alert = {
            'id': 'alert_123',
            'type': 'threshold_violation',
            'severity': 'warning',
            'metric_type': 'response_time',
            'current_value': 1.5
        }
        mock_redis.lrange.return_value = [json.dumps(mock_alert)]
        
        # 添加一些指标数据
        metric = TradingMetric(
            timestamp=time.time(),
            symbol="BTC-USDT",
            metric_type="signal",
            value=0.85,
            metadata={}
        )
        collector.metrics_buffer.append(metric)
        
        # 获取仪表板数据
        dashboard_data = await collector.get_real_time_dashboard_data()
        
        assert 'timestamp' in dashboard_data
        assert 'summary' in dashboard_data
        assert 'recent_alerts' in dashboard_data
        assert 'key_metrics' in dashboard_data
        assert 'health_score' in dashboard_data
        
        # 检查告警数据
        assert len(dashboard_data['recent_alerts']) == 1
        assert dashboard_data['recent_alerts'][0]['id'] == 'alert_123'
    
    def test_calculate_key_metrics(self, collector):
        """测试计算关键指标"""
        summary = {
            'trading_metrics': {
                'signal': {'count': 10, 'avg_value': 0.8},
                'order': {'count': 5, 'avg_value': 0.95},
                'position': {'count': 3, 'avg_value': 0.02}
            },
            'system_metrics': {
                'response_time': {'avg_value': 0.15},
                'error_rate': {'avg_value': 0.005}
            }
        }
        
        key_metrics = collector._calculate_key_metrics(summary)
        
        assert key_metrics['signal_rate_per_minute'] == 2.0  # 10个信号/5分钟
        assert key_metrics['order_success_rate'] == 0.95
        assert key_metrics['position_profit_rate'] == 0.02
        assert key_metrics['avg_response_time'] == 0.15
        assert key_metrics['system_error_rate'] == 0.005
    
    def test_calculate_health_score(self, collector):
        """测试计算健康分数"""
        key_metrics = {
            'order_success_rate': 0.95,
            'system_error_rate': 0.005,
            'avg_response_time': 0.15,
            'signal_rate_per_minute': 2.0,
            'position_profit_rate': 0.02
        }
        
        health_score = collector._calculate_health_score(key_metrics)
        
        # 健康分数应该在0-100之间
        assert 0 <= health_score <= 100
        
        # 高质量指标应该有较高的健康分数
        assert health_score > 70
    
    def test_alert_handler_management(self, collector):
        """测试告警处理器管理"""
        # 测试添加处理器
        def handler1():
            pass
        def handler2():
            pass
        
        collector.add_alert_handler(handler1)
        collector.add_alert_handler(handler2)
        
        assert len(collector.alert_handlers) == 2
        assert handler1 in collector.alert_handlers
        assert handler2 in collector.alert_handlers
        
        # 测试移除处理器
        collector.remove_alert_handler(handler1)
        
        assert len(collector.alert_handlers) == 1
        assert handler1 not in collector.alert_handlers
        assert handler2 in collector.alert_handlers


class TestConvenienceFunctions:
    """便捷函数测试"""
    
    @pytest.mark.asyncio
    async def test_record_trading_signal(self):
        """测试记录交易信号"""
        with patch('src.monitoring.business_metrics.get_business_metrics_collector') as mock_get_collector:
            mock_collector = AsyncMock()
            mock_get_collector.return_value = mock_collector
            
            await record_trading_signal("BTC-USDT", 0.85, {"strength": "high"})
            
            # 验证调用
            mock_get_collector.assert_called_once()
            mock_collector.collect_trading_metric.assert_called_once()
            
            # 检查传递的指标
            call_args = mock_collector.collect_trading_metric.call_args[0][0]
            assert isinstance(call_args, TradingMetric)
            assert call_args.symbol == "BTC-USDT"
            assert call_args.value == 0.85
            assert call_args.metric_type == "signal"
            assert call_args.metadata["strength"] == "high"
    
    @pytest.mark.asyncio
    async def test_record_order_execution(self):
        """测试记录订单执行"""
        with patch('src.monitoring.business_metrics.get_business_metrics_collector') as mock_get_collector:
            mock_collector = AsyncMock()
            mock_get_collector.return_value = mock_collector
            
            await record_order_execution("BTC-USDT", True, 0.5, {"order_id": "123"})
            
            # 验证调用
            mock_get_collector.assert_called_once()
            mock_collector.collect_trading_metric.assert_called_once()
            
            # 检查传递的指标
            call_args = mock_collector.collect_trading_metric.call_args[0][0]
            assert isinstance(call_args, TradingMetric)
            assert call_args.symbol == "BTC-USDT"
            assert call_args.value == 1.0  # 成功订单
            assert call_args.metric_type == "order"
            assert call_args.metadata["latency"] == 0.5
            assert call_args.metadata["order_id"] == "123"
    
    @pytest.mark.asyncio
    async def test_record_system_performance(self):
        """测试记录系统性能"""
        with patch('src.monitoring.business_metrics.get_business_metrics_collector') as mock_get_collector:
            mock_collector = AsyncMock()
            mock_get_collector.return_value = mock_collector
            
            await record_system_performance("data_manager", 0.15, {"endpoint": "/api/data"})
            
            # 验证调用
            mock_get_collector.assert_called_once()
            mock_collector.collect_system_metric.assert_called_once()
            
            # 检查传递的指标
            call_args = mock_collector.collect_system_metric.call_args[0][0]
            assert isinstance(call_args, SystemMetric)
            assert call_args.service == "data_manager"
            assert call_args.value == 0.15
            assert call_args.metric_type == "response_time"
            assert call_args.metadata["endpoint"] == "/api/data"
    
    @pytest.mark.asyncio
    async def test_record_system_error(self):
        """测试记录系统错误"""
        with patch('src.monitoring.business_metrics.get_business_metrics_collector') as mock_get_collector:
            mock_collector = AsyncMock()
            mock_get_collector.return_value = mock_collector
            
            await record_system_error("data_manager", "timeout", {"endpoint": "/api/data"})
            
            # 验证调用
            mock_get_collector.assert_called_once()
            mock_collector.collect_system_metric.assert_called_once()
            
            # 检查传递的指标
            call_args = mock_collector.collect_system_metric.call_args[0][0]
            assert isinstance(call_args, SystemMetric)
            assert call_args.service == "data_manager"
            assert call_args.value == 1.0  # 错误指标
            assert call_args.metric_type == "error_rate"
            assert call_args.metadata["error_type"] == "timeout"
            assert call_args.metadata["endpoint"] == "/api/data"


class TestGlobalInstance:
    """全局实例测试"""
    
    def test_get_business_metrics_collector_singleton(self):
        """测试全局单例"""
        # 清除全局实例
        import src.monitoring.business_metrics
        src.monitoring.business_metrics._business_metrics_collector = None
        
        # 第一次调用应该创建新实例
        collector1 = get_business_metrics_collector()
        assert collector1 is not None
        
        # 第二次调用应该返回相同实例
        collector2 = get_business_metrics_collector()
        assert collector1 is collector2
    
    def test_get_business_metrics_collector_with_redis(self):
        """测试带Redis参数的全局实例"""
        mock_redis = Mock()
        
        # 清除全局实例
        import src.monitoring.business_metrics
        src.monitoring.business_metrics._business_metrics_collector = None
        
        collector = get_business_metrics_collector(redis_client=mock_redis)
        assert collector.redis_client == mock_redis
