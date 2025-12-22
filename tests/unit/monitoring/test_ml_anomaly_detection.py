"""
机器学习异常检测模块测试
"""

import pytest
import asyncio
import time
import numpy as np
from unittest.mock import Mock, AsyncMock, patch
from src.monitoring.ml_anomaly_detection import (
    AnomalyDetectionEngine, AnomalyType, get_anomaly_detection_engine,
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
        assert len(engine.alert_handlers) == 0
        assert len(engine.detection_history) == 0
        assert engine.config is not None
    
    @pytest.mark.asyncio
    async def test_process_metric(self, engine):
        """测试指标处理"""
        # 添加正常数据
        normal_data = [1.0, 1.1, 0.9, 1.2, 0.8, 1.05, 0.95]
        for i, value in enumerate(normal_data):
            await engine.process_metric(
                service="test_service",
                metric_type="response_time",
                value=value,
                timestamp=time.time() + i,
                metadata={"test": True}
            )
        
        # 验证数据被添加到检测器
        key = "test_service:response_time"
        assert len(engine.statistical_detector.data_windows[key]) == len(normal_data)
        assert len(engine.ml_detector.training_data[key]) == len(normal_data)
    
    @pytest.mark.asyncio
    async def test_statistical_anomaly_detection(self, engine):
        """测试统计异常检测"""
        # 添加正常数据
        normal_data = [1.0, 1.1, 0.9, 1.2, 0.8, 1.05, 0.95, 1.1, 0.9, 1.0]
        for i, value in enumerate(normal_data):
            await engine.process_metric(
                service="test_service",
                metric_type="response_time",
                value=value,
                timestamp=time.time() + i
            )
        
        # 测试正常值（不应该触发异常）
        initial_history_len = len(engine.detection_history)
        await engine.process_metric(
            service="test_service",
            metric_type="response_time",
            value=1.0,
            timestamp=time.time() + 100
        )
        assert len(engine.detection_history) == initial_history_len  # 没有新的异常
        
        # 测试异常值（应该触发异常）
        await engine.process_metric(
            service="test_service",
            metric_type="response_time",
            value=5.0,  # 明显异常
            timestamp=time.time() + 101
        )
        assert len(engine.detection_history) > initial_history_len  # 有新的异常
    
    @pytest.mark.asyncio
    async def test_ml_model_training(self, engine):
        """测试机器学习模型训练"""
        # 添加足够的训练数据 - 需要多个不同的key来满足训练要求
        np.random.seed(42)
        
        # 为多个服务添加数据，确保有足够的训练样本
        services = ["service1", "service2", "service3", "service4", "service5"]
        for service_idx, service in enumerate(services):
            for i in range(30):  # 每个服务30个样本
                value = np.random.normal(1.0 + service_idx * 0.1, 0.1)
                await engine.process_metric(
                    service=service,
                    metric_type="response_time",
                    value=value,
                    timestamp=time.time() + service_idx * 100 + i
                )
        
        # 手动触发训练
        success = engine.ml_detector.train_model()
        assert success is True
        assert engine.ml_detector.is_trained is True
        assert engine.ml_detector.last_retrain > 0
    
    @pytest.mark.asyncio
    async def test_anomaly_alert_handling(self, engine):
        """测试异常告警处理"""
        # 模拟告警处理器
        alert_handler = Mock()
        engine.add_alert_handler(alert_handler)
        
        # 添加正常数据
        for i in range(15):
            await engine.process_metric(
                service="test_service",
                metric_type="response_time",
                value=1.0 + i * 0.01,
                timestamp=time.time() + i
            )
        
        # 添加异常数据
        await engine.process_metric(
            service="test_service",
            metric_type="response_time",
            value=10.0,  # 明显异常
            timestamp=time.time() + 100
        )
        
        # 验证告警处理器被调用
        assert alert_handler.call_count > 0
    
    def test_alert_handler_management(self, engine):
        """测试告警处理器管理"""
        handler1 = Mock()
        handler2 = Mock()
        
        # 添加处理器
        engine.add_alert_handler(handler1)
        engine.add_alert_handler(handler2)
        assert len(engine.alert_handlers) == 2
        assert handler1 in engine.alert_handlers
        assert handler2 in engine.alert_handlers
        
        # 移除处理器
        engine.remove_alert_handler(handler1)
        assert len(engine.alert_handlers) == 1
        assert handler1 not in engine.alert_handlers
        assert handler2 in engine.alert_handlers
    
    @pytest.mark.asyncio
    async def test_get_anomaly_summary(self, engine):
        """测试异常摘要"""
        # 模拟一些异常历史
        current_time = time.time()
        
        # 手动添加异常记录
        from src.monitoring.ml_anomaly_detection import AnomalyAlert
        engine.detection_history.append(AnomalyAlert(
            timestamp=current_time - 300,
            anomaly_type="statistical",
            severity="high",
            service="test_service",
            metric_type="response_time",
            current_value=5.0,
            expected_range=(0.5, 2.0),
            confidence=0.9,
            description="Test anomaly 1",
            metadata={"test": True}
        ))
        
        engine.detection_history.append(AnomalyAlert(
            timestamp=current_time - 60,
            anomaly_type="ml_isolation",
            severity="medium",
            service="test_service2",
            metric_type="cpu_usage",
            current_value=0.95,
            expected_range=(0.0, 0.8),
            confidence=0.8,
            description="Test anomaly 2",
            metadata={"test": True}
        ))
        
        # 获取摘要
        summary = await engine.get_anomaly_summary(time_window=600)
        
        assert summary["time_window"] == 600
        assert summary["total_anomalies"] == 2
        assert "statistical" in summary["by_type"]
        assert "ml_isolation" in summary["by_type"]
        assert "high" in summary["by_severity"]
        assert "medium" in summary["by_severity"]
        assert "test_service" in summary["by_service"]
        assert "test_service2" in summary["by_service"]
        assert "ml_model_status" in summary
    
    def test_edge_cases(self, engine):
        """测试边界情况"""
        # 测试空数据的异常检测
        assert engine.statistical_detector.detect_anomaly("nonexistent", 1.0, time.time()) is None
        assert engine.ml_detector.detect_anomaly("nonexistent", 1.0, time.time()) is None
    
    def test_performance_considerations(self, engine):
        """测试性能考虑"""
        import time
        
        # 测试大量数据处理
        start_time = time.time()
        for i in range(1000):
            engine.statistical_detector.add_sample(f"test:{i}", float(i), time.time() + i)
        add_time = time.time() - start_time
        
        # 性能断言
        assert add_time < 1.0  # 添加1000个数据点应该在1秒内


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
    async def test_detect_metric_anomaly(self):
        """测试指标异常检测便捷函数"""
        with patch('src.monitoring.ml_anomaly_detection.get_anomaly_detection_engine') as mock_get_engine:
            mock_engine = AsyncMock()
            mock_get_engine.return_value = mock_engine
            
            # 调用便捷函数
            await detect_metric_anomaly(
                service="test_service",
                metric_type="response_time",
                value=2.5,
                metadata={"test": True}
            )
            
            # 验证引擎方法被调用
            mock_engine.process_metric.assert_called_once()
            call_args = mock_engine.process_metric.call_args[1]
            assert call_args["service"] == "test_service"
            assert call_args["metric_type"] == "response_time"
            assert call_args["value"] == 2.5
            assert call_args["metadata"]["test"] is True
    
    @pytest.mark.asyncio
    async def test_get_anomaly_dashboard_data(self):
        """测试异常检测仪表板数据便捷函数"""
        with patch('src.monitoring.ml_anomaly_detection.get_anomaly_detection_engine') as mock_get_engine:
            mock_engine = AsyncMock()
            mock_engine.get_anomaly_summary.return_value = {
                "total_anomalies": 5,
                "by_type": {"statistical": 3, "ml_isolation": 2}
            }
            mock_engine.redis_client = None  # 模拟无Redis客户端
            mock_get_engine.return_value = mock_engine
            
            # 调用便捷函数
            dashboard_data = await get_anomaly_dashboard_data()
            
            # 验证返回数据结构
            assert "timestamp" in dashboard_data
            assert "summary" in dashboard_data
            assert "recent_alerts" in dashboard_data
            assert "detection_methods" in dashboard_data
            assert dashboard_data["summary"]["total_anomalies"] == 5


class TestStatisticalAnomalyDetector:
    """统计异常检测器测试"""
    
    @pytest.fixture
    def detector(self):
        """创建统计异常检测器实例"""
        from src.monitoring.ml_anomaly_detection import StatisticalAnomalyDetector
        return StatisticalAnomalyDetector()
    
    def test_statistical_detector_initialization(self, detector):
        """测试统计检测器初始化"""
        assert detector.window_size == 100
        assert detector.threshold_std == 2.5
        assert len(detector.data_windows) == 0
    
    def test_add_sample(self, detector):
        """测试添加样本"""
        detector.add_sample("test_key", 1.0, time.time())
        assert len(detector.data_windows["test_key"]) == 1
        
        # 添加更多样本
        for i in range(10):
            detector.add_sample("test_key", 1.0 + i * 0.1, time.time() + i)
        assert len(detector.data_windows["test_key"]) == 11
    
    def test_detect_anomaly_insufficient_data(self, detector):
        """测试数据不足时的异常检测"""
        # 添加少量数据
        for i in range(5):
            detector.add_sample("test_key", 1.0 + i * 0.1, time.time() + i)
        
        # 数据不足，应该返回None
        result = detector.detect_anomaly("test_key", 5.0, time.time() + 100)
        assert result is None
    
    def test_detect_anomaly_with_sufficient_data(self, detector):
        """测试数据充足时的异常检测"""
        # 添加足够的数据
        normal_data = [1.0, 1.1, 0.9, 1.2, 0.8, 1.05, 0.95, 1.1, 0.9, 1.0,
                     1.15, 0.85, 1.25, 0.75, 1.05]
        for i, value in enumerate(normal_data):
            detector.add_sample("test_key", value, time.time() + i)
        
        # 测试正常值
        result = detector.detect_anomaly("test_key", 1.0, time.time() + 100)
        assert result is None  # 正常值不应该被检测为异常
        
        # 测试异常值
        result = detector.detect_anomaly("test_key", 5.0, time.time() + 101)
        assert result is not None
        assert result["type"] == "statistical"
        assert result["severity"] in ["low", "medium", "high", "critical"]


class TestMLAnomalyDetector:
    """机器学习异常检测器测试"""
    
    @pytest.fixture
    def detector(self):
        """创建ML异常检测器实例"""
        from src.monitoring.ml_anomaly_detection import MLAnomalyDetector
        return MLAnomalyDetector()
    
    def test_ml_detector_initialization(self, detector):
        """测试ML检测器初始化"""
        assert detector.model_type == "isolation_forest"
        assert detector.retrain_interval == 3600
        assert detector.last_retrain == 0
        assert detector.is_trained is False
        assert detector.model is not None
        assert detector.scaler is not None
    
    def test_add_training_sample(self, detector):
        """测试添加训练样本"""
        detector.add_training_sample("test_key", 1.0, time.time())
        assert len(detector.training_data["test_key"]) == 1
        
        # 添加更多样本
        for i in range(10):
            detector.add_training_sample("test_key", 1.0 + i * 0.1, time.time() + i)
        assert len(detector.training_data["test_key"]) == 11
    
    def test_should_retrain(self, detector):
        """测试重训练判断"""
        # 初始状态应该需要训练
        assert detector.should_retrain() is True
        
        # 设置最近训练时间
        detector.last_retrain = time.time()
        assert detector.should_retrain() is False
        
        # 模拟时间过去
        detector.last_retrain = time.time() - detector.retrain_interval - 100
        assert detector.should_retrain() is True
    
    def test_train_model_insufficient_data(self, detector):
        """测试数据不足时的模型训练"""
        # 添加少量数据
        for i in range(10):
            detector.add_training_sample("test_key", 1.0 + i * 0.1, time.time() + i)
        
        # 数据不足，训练应该失败
        success = detector.train_model()
        assert success is False
        assert detector.is_trained is False
    
    def test_train_model_sufficient_data(self, detector):
        """测试数据充足时的模型训练"""
        # 添加足够的数据 - 需要多个不同的key来满足训练要求
        # 每个key需要至少20个样本，总共需要至少50个特征向量
        for key_idx in range(5):  # 5个不同的key
            key = f"test_key_{key_idx}"
            for i in range(30):  # 每个key 30个样本
                detector.add_training_sample(key, 1.0 + key_idx * 0.1 + i * 0.01, time.time() + key_idx * 100 + i)
        
        # 数据充足，训练应该成功
        success = detector.train_model()
        assert success is True
        assert detector.is_trained is True
        assert detector.last_retrain > 0
    
    def test_detect_anomaly_untrained(self, detector):
        """测试未训练模型的异常检测"""
        # 未训练的模型应该返回None
        result = detector.detect_anomaly("test_key", 5.0, time.time())
        assert result is None


class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_anomaly_detection(self):
        """端到端异常检测测试"""
        engine = AnomalyDetectionEngine()
        
        # 模拟真实的监控数据流
        np.random.seed(42)
        
        # 1. 正常运行阶段 - 添加多个服务和指标来满足ML训练要求
        services = ["data_manager", "strategy_engine", "risk_manager", "executor"]
        metrics = ["response_time", "cpu_usage", "memory_usage", "error_rate"]
        
        for service_idx, service in enumerate(services):
            for metric_idx, metric in enumerate(metrics):
                for i in range(15):  # 每个指标15个样本
                    value = np.random.normal(1.0 + service_idx * 0.1 + metric_idx * 0.05, 0.1)
                    await engine.process_metric(
                        service=service,
                        metric_type=metric,
                        value=value,
                        timestamp=time.time() + service_idx * 100 + metric_idx * 10 + i
                    )
                    await asyncio.sleep(0.001)  # 模拟时间间隔
        
        # 2. 手动训练ML模型
        success = engine.ml_detector.train_model()
        assert success is True
        
        # 3. 异常检测阶段
        initial_history_len = len(engine.detection_history)
        
        for i in range(50):
            if i % 10 == 0:
                # 每10个数据点插入一个异常
                value = np.random.normal(5.0, 0.5)  # 明显异常
            else:
                value = np.random.normal(1.0, 0.1)  # 正常数据
            
            await engine.process_metric(
                service="data_manager",
                metric_type="response_time",
                value=value,
                timestamp=time.time() + 100 + i
            )
        
        # 验证检测到异常
        final_history_len = len(engine.detection_history)
        assert final_history_len > initial_history_len
        
        # 检查异常摘要
        summary = await engine.get_anomaly_summary()
        assert summary["total_anomalies"] > 0
