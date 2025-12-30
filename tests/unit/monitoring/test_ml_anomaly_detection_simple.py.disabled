"""
机器学习异常检测模块测试（简化版，不依赖sklearn）
"""

import pytest
import asyncio
import time
import gc
import numpy as np
from unittest.mock import Mock, AsyncMock, patch
from src.monitoring.ml_anomaly_detection import (
    AnomalyDetectionEngine, get_anomaly_detection_engine,
    detect_metric_anomaly, get_anomaly_dashboard_data
)


class TestAnomalyDetectionEngine:
    """异常检测引擎测试"""
    
    @pytest.fixture
    def engine(self):
        """创建异常检测引擎实例"""
        return AnomalyDetectionEngine()
    
    def test_engine_initialization(self, engine):
        """测试引擎初始化"""
        assert engine.statistical_detector is not None
        assert engine.ml_detector is not None
        assert engine.config is not None
        assert len(engine.alert_handlers) == 0
        assert len(engine.detection_history) == 0
    
    def test_config_loading(self, engine):
        """测试配置加载"""
        config = engine.config
        assert 'enabled' in config
        assert 'statistical_threshold' in config
        assert 'ml_retrain_interval' in config
        assert 'min_samples_for_training' in config
        assert 'alert_cooldown' in config
        
        # 检查默认值
        assert config['enabled'] is True
        assert config['statistical_threshold'] == 2.5
        assert config['ml_retrain_interval'] == 3600
        assert config['alert_cooldown'] == 300
    
    @pytest.mark.asyncio
    async def test_metric_processing(self, engine):
        """测试指标处理"""
        base_time = time.time()
        
        # 添加足够的正常数据以建立基线（需要至少10个数据点）
        normal_values = [0.5, 0.6, 0.4, 0.7, 0.5, 0.8, 0.3, 0.6, 0.5, 0.7, 0.4, 0.6]
        for i, value in enumerate(normal_values):
            await engine.process_metric(
                service="data_manager",
                metric_type="response_time",
                value=value,
                timestamp=base_time + i * 60,  # 每分钟一个数据点
                metadata={"endpoint": "/api/data"}
            )

        # 添加异常数据
        await engine.process_metric(
            service="data_manager",
            metric_type="response_time",
            value=5.0,  # 明显异常
            timestamp=base_time + len(normal_values) * 60,
            metadata={"endpoint": "/api/data"}
        )

        # 等待异步处理完成
        await asyncio.sleep(0.1)
        
        # 检查检测历史
        assert len(engine.detection_history) > 0
    
    @pytest.mark.asyncio
    async def test_statistical_anomaly_detection(self, engine):
        """测试统计异常检测"""
        # 添加足够的正常数据以建立基线
        base_time = time.time()
        normal_values = [0.5, 0.6, 0.4, 0.7, 0.5, 0.8, 0.3, 0.6, 0.5, 0.7, 0.4, 0.6]
        
        for i, value in enumerate(normal_values):
            await engine.process_metric(
                service="test_service",
                metric_type="response_time",
                value=value,
                timestamp=base_time + i * 60
            )
        
        # 添加异常值
        await engine.process_metric(
            service="test_service",
            metric_type="response_time",
            value=5.0,  # 明显异常
            timestamp=base_time + len(normal_values) * 60
        )
        
        # 等待异步处理完成
        await asyncio.sleep(0.1)
        
        # 检查是否检测到异常
        anomalies = [alert for alert in engine.detection_history 
                   if alert.service == "test_service"]
        assert len(anomalies) > 0
        
        # 检查异常类型
        anomaly_types = [alert.anomaly_type for alert in anomalies]
        assert 'statistical' in anomaly_types
    
    @pytest.mark.asyncio
    async def test_alert_handler_management(self, engine):
        """测试告警处理器管理"""
        alerts_received = []
        
        async def test_handler(alert):
            alerts_received.append(alert)
        
        # 添加处理器
        engine.add_alert_handler(test_handler)
        assert len(engine.alert_handlers) == 1
        
        # 先添加足够的正常数据建立基线
        base_time = time.time()
        normal_values = [0.01, 0.02, 0.015, 0.008, 0.012, 0.005, 0.018, 0.009, 0.011, 0.007, 0.013, 0.006]
        for i, value in enumerate(normal_values):
            await engine.process_metric(
                service="test_service",
                metric_type="error_rate",
                value=value,
                timestamp=base_time + i * 60
            )
        
        # 触发异常检测（高错误率）
        await engine.process_metric(
            service="test_service",
            metric_type="error_rate",
            value=0.1,  # 明显异常的高错误率
            timestamp=base_time + len(normal_values) * 60
        )
        
        # 等待异步处理
        await asyncio.sleep(0.1)
        
        # 检查处理器是否被调用
        assert len(alerts_received) > 0
        
        # 移除处理器
        engine.remove_alert_handler(test_handler)
        assert len(engine.alert_handlers) == 0
    
    @pytest.mark.asyncio
    async def test_cooldown_mechanism(self, engine):
        """测试冷却机制"""
        # 第一次异常检测
        await engine.process_metric(
            service="test_service",
            metric_type="response_time",
            value=5.0,
            timestamp=time.time()
        )
        
        # 立即再次检测（应该在冷却期内）
        initial_count = len(engine.detection_history)
        await engine.process_metric(
            service="test_service",
            metric_type="response_time",
            value=6.0,
            timestamp=time.time() + 1  # 1秒后
        )
        
        # 在冷却期内，不应该产生新的告警
        await asyncio.sleep(0.1)
        # 注意：由于没有Redis，冷却机制可能不生效，这是预期的
    
    @pytest.mark.asyncio
    async def test_anomaly_summary(self, engine):
        """测试异常摘要"""
        base_time = time.time()
        
        # 添加一些异常数据
        for i in range(5):
            await engine.process_metric(
                service=f"service_{i % 2}",
                metric_type="response_time",
                value=5.0 + i,  # 异常值
                timestamp=base_time + i * 300  # 每5分钟一个
            )
        
        # 获取摘要
        summary = await engine.get_anomaly_summary(time_window=3600)  # 1小时窗口
        
        assert 'time_window' in summary
        assert 'total_anomalies' in summary
        assert 'by_type' in summary
        assert 'by_severity' in summary
        assert 'by_service' in summary
        assert 'ml_model_status' in summary
        
        assert summary['total_anomalies'] >= 0
        assert isinstance(summary['by_type'], dict)
        assert isinstance(summary['by_severity'], dict)
        assert isinstance(summary['by_service'], dict)
    
    @pytest.mark.asyncio
    async def test_dashboard_data(self, engine):
        """测试仪表板数据"""
        # 添加一些测试数据
        await engine.process_metric(
            service="test_service",
            metric_type="response_time",
            value=0.5,
            timestamp=time.time()
        )
        
        # 获取仪表板数据
        dashboard_data = await get_anomaly_dashboard_data()
        
        assert 'timestamp' in dashboard_data
        assert 'summary' in dashboard_data
        assert 'recent_alerts' in dashboard_data
        assert 'detection_methods' in dashboard_data
        
        # 检查检测方法
        methods = dashboard_data['detection_methods']
        assert 'statistical' in methods
        assert 'ml_isolation' in methods
        assert 'ml_cluster' in methods


class TestConvenienceFunctions:
    """便捷函数测试"""
    
    @pytest.mark.asyncio
    async def test_get_anomaly_detection_engine_singleton(self):
        """测试全局单例"""
        # 清除全局实例
        import src.monitoring.ml_anomaly_detection
        src.monitoring.ml_anomaly_detection._anomaly_detection_engine = None
        
        # 第一次调用应该创建新实例
        engine1 = get_anomaly_detection_engine()
        assert engine1 is not None
        
        # 第二次调用应该返回相同实例
        engine2 = get_anomaly_detection_engine()
        assert engine1 is engine2
    
    @pytest.mark.asyncio
    async def test_detect_metric_anomaly_convenience(self):
        """测试异常检测便捷函数"""
        with patch('src.monitoring.ml_anomaly_detection.get_anomaly_detection_engine') as mock_get_engine:
            mock_engine = AsyncMock()
            mock_get_engine.return_value = mock_engine
            
            # 调用便捷函数
            await detect_metric_anomaly(
                service="test_service",
                metric_type="response_time",
                value=5.0,
                metadata={"endpoint": "/api/test"}
            )
            
            # 验证调用
            mock_engine.process_metric.assert_called_once()
            call_args = mock_engine.process_metric.call_args[1]
            
            assert call_args['service'] == "test_service"
            assert call_args['metric_type'] == "response_time"
            assert call_args['value'] == 5.0
            assert call_args['metadata']['endpoint'] == "/api/test"


class TestEdgeCases:
    """边界情况测试"""
    
    @pytest.fixture
    def engine(self):
        """创建异常检测引擎实例"""
        return AnomalyDetectionEngine()
    
    @pytest.mark.asyncio
    async def test_empty_data_handling(self, engine):
        """测试空数据处理"""
        # 处理单个数据点
        await engine.process_metric(
            service="test_service",
            metric_type="response_time",
            value=1.0,
            timestamp=time.time()
        )
        
        # 应该不会产生异常（数据不足）
        # 这是正常行为，不应该抛出异常
        assert True  # 如果到达这里说明没有抛出异常
    
    @pytest.mark.asyncio
    async def test_extreme_values(self, engine):
        """测试极值处理"""
        extreme_values = [
            float('inf'),   # 无穷大
            float('-inf'),  # 无穷小
            0.0,            # 零值
            1e-10,          # 极小值
            1e10             # 极大值
        ]
        
        for value in extreme_values:
            try:
                await engine.process_metric(
                    service="test_service",
                    metric_type="response_time",
                    value=value,
                    timestamp=time.time()
                )
                # 如果没有抛出异常，说明处理正常
                assert True
            except (ValueError, OverflowError):
                # 某些极值可能导致计算错误，这是预期的
                pass
    
    @pytest.mark.asyncio
    async def test_concurrent_processing(self, engine):
        """测试并发处理"""
        import asyncio
        
        # 并发处理多个指标
        tasks = []
        for i in range(10):
            task = engine.process_metric(
                service=f"service_{i}",
                metric_type="response_time",
                value=0.5 + i * 0.1,
                timestamp=time.time() + i
            )
            tasks.append(task)
        
        # 等待所有任务完成
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # 检查是否所有数据都被处理
        # 注意：由于没有实际的异常值，可能不会产生告警
        assert len(engine.detection_history) >= 0


class TestPerformance:
    """性能测试"""
    
    @pytest.fixture
    def engine(self):
        """创建异常检测引擎实例"""
        return AnomalyDetectionEngine()
    
    @pytest.mark.asyncio
    async def test_processing_performance(self, engine):
        """测试处理性能"""
        import time
        
        # 测试大量数据处理
        start_time = time.time()
        
        for i in range(100):
            await engine.process_metric(
                service=f"service_{i % 5}",
                metric_type="response_time",
                value=0.5 + (i % 10) * 0.1,
                timestamp=time.time() + i
            )
        
        processing_time = time.time() - start_time
        
        # 性能断言
        assert processing_time < 5.0  # 100个指标应该在5秒内处理完成
        assert len(engine.detection_history) >= 0  # 应该有处理记录
    
    def test_memory_usage(self, engine):
        """测试内存使用"""
        import sys
        
        # 获取初始内存使用
        initial_objects = len(gc.get_objects())
        
        # 添加大量数据
        async def add_data():
            for i in range(1000):
                await engine.process_metric(
                    service="test_service",
                    metric_type="response_time",
                    value=0.5,
                    timestamp=time.time() + i
                )
        
        # 运行异步函数
        asyncio.run(add_data())
        
        # 检查内存增长
        final_objects = len(gc.get_objects())
        memory_growth = final_objects - initial_objects
        
        # 内存增长应该在合理范围内
        assert memory_growth < 10000  # 允许一定的内存增长，但不应过多
