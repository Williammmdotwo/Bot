"""
Config Loader 单元测试
Unit Tests for Config Loader
"""

import pytest
import json
import os
import tempfile
import threading
from unittest.mock import patch, Mock, MagicMock
from pathlib import Path

from src.utils.config_loader import (
    ConfigManager,
    ServiceConfig,
    DatabaseConfig,
    RedisConfig,
    LoggingConfig,
    TradingConfig,
    RiskLimitsConfig,
    AuthConfig,
    PerformanceConfig,
    AthenaConfigSchema,
    ConfigFileHandler,
    get_config_manager
)


class TestConfigModels:
    """测试配置模型"""

    @pytest.mark.unit
    def test_service_config_valid(self):
        """测试有效的服务配置"""
        config = ServiceConfig(port=8000, enabled=True, host="localhost")
        assert config.port == 8000
        assert config.enabled is True
        assert config.host == "localhost"

    @pytest.mark.unit
    def test_service_config_invalid_port(self):
        """测试无效端口的服务配置"""
        with pytest.raises(ValueError):
            ServiceConfig(port=70000)  # 超出范围

    @pytest.mark.unit
    def test_database_config_valid(self):
        """测试有效的数据库配置"""
        config = DatabaseConfig(
            use_database=True,
            mock_data=False,
            host="localhost",
            port=5432,
            name="test_db",
            user="test_user",
            pool_size=10,
            max_overflow=20
        )
        assert config.use_database is True
        assert config.port == 5432
        assert config.name == "test_db"

    @pytest.mark.unit
    def test_risk_limits_config_valid(self):
        """测试有效的风险限制配置"""
        config = RiskLimitsConfig(
            max_single_order_size_percent=0.1,
            max_total_position_percent=0.5,
            mandatory_stop_loss_percent=-0.02,
            mandatory_take_profit_percent=0.05,
            max_drawdown_percent=0.15
        )
        assert config.max_single_order_size_percent == 0.1
        assert config.max_total_position_percent == 0.5

    @pytest.mark.unit
    def test_risk_limits_config_invalid_values(self):
        """测试无效值的风险限制配置"""
        with pytest.raises(ValueError):
            RiskLimitsConfig(max_single_order_size_percent=2.0)  # 超出范围

    @pytest.mark.unit
    def test_trading_config_valid(self):
        """测试有效的交易配置"""
        config = TradingConfig(
            use_demo=True,
            simulation_mode=False,
            test_duration_minutes=30,
            signal_interval_seconds=15,
            progress_interval_seconds=30,
            default_symbols=["BTC-USDT", "ETH-USDT"],
            default_timeframes=["5m", "15m", "1h", "4h"]
        )
        assert config.use_demo is True
        assert config.default_symbols == ["BTC-USDT", "ETH-USDT"]

    @pytest.mark.unit
    def test_athena_config_schema_valid(self):
        """测试有效的Athena配置模式"""
        config = AthenaConfigSchema(
            environment="development",
            database=DatabaseConfig(),
            redis=RedisConfig(),
            services={
                "data_manager": ServiceConfig(port=8000),
                "risk_manager": ServiceConfig(port=8001)
            },
            logging=LoggingConfig(),
            trading=TradingConfig(),
            risk_limits=RiskLimitsConfig(),
            auth=AuthConfig(internal_token="test-token"),
            performance=PerformanceConfig()
        )
        assert config.environment == "development"
        assert len(config.services) == 2


class TestConfigManagerMethods:
    """测试配置管理器方法（不涉及初始化）"""

    @pytest.mark.unit
    def test_merge_configs(self):
        """测试配置合并"""
        base = {"a": 1, "b": {"c": 2, "d": 3}}
        env = {"b": {"c": 4}, "e": 5}
        local = {"a": 6, "b": {"f": 7}}

        manager = ConfigManager()
        result = manager._merge_configs(base, env, local)

        assert result["a"] == 6  # local覆盖
        assert result["b"]["c"] == 4  # env覆盖
        assert result["b"]["d"] == 3  # 保留base
        assert result["b"]["f"] == 7  # local添加
        assert result["e"] == 5  # env添加

    @pytest.mark.unit
    def test_deep_merge(self):
        """测试深度合并"""
        base = {"a": {"b": {"c": 1}, "d": 2}}
        override = {"a": {"b": {"e": 3}, "f": 4}}

        manager = ConfigManager()
        result = manager._deep_merge(base, override)

        assert result["a"]["b"]["c"] == 1  # 保留
        assert result["a"]["b"]["e"] == 3  # 新增
        assert result["a"]["d"] == 2  # 保留
        assert result["a"]["f"] == 4  # 新增

    @pytest.mark.unit
    def test_preprocess_config(self):
        """测试配置预处理"""
        config_data = {
            "environment": "development",
            "database": {"use_database": True},
            "services": {
                "data_manager": {"port": 8000}
            }
        }

        manager = ConfigManager()
        processed = manager._preprocess_config(config_data)

        # 应该添加默认服务配置
        assert "risk_manager" in processed["services"]
        assert "executor" in processed["services"]
        assert "strategy_engine" in processed["services"]

        # 应该添加默认auth配置
        assert "internal_token" in processed["auth"]

    @pytest.mark.unit
    def test_validate_business_rules_port_conflict(self):
        """测试端口冲突验证"""
        config = {
            "services": {
                "service1": {"port": 8000},
                "service2": {"port": 8000}  # 端口冲突
            }
        }

        manager = ConfigManager()
        with pytest.raises(Exception):
            manager._validate_business_rules(config)

    @pytest.mark.unit
    def test_validate_business_rules_risk_limits(self):
        """测试风险限制业务规则验证"""
        config = {
            "risk_limits": {
                "max_single_order_size_percent": 0.6,
                "max_total_position_percent": 0.5  # 单笔超过总持仓
            }
        }

        manager = ConfigManager()
        with pytest.raises(Exception):
            manager._validate_business_rules(config)

    @pytest.mark.unit
    def test_validate_business_rules_production_auth(self):
        """测试生产环境认证验证"""
        config = {
            "environment": "production",
            "auth": {"require_auth": False}  # 生产环境必须启用认证
        }

        manager = ConfigManager()
        with pytest.raises(Exception):
            manager._validate_business_rules(config)

    @pytest.mark.unit
    def test_get_service_config(self):
        """测试获取服务配置"""
        manager = ConfigManager()
        manager.config = {
            "services": {
                "data_manager": {"port": 8000, "enabled": True, "host": "localhost"}
            }
        }

        service_config = manager.get_service_config("data_manager")
        assert service_config["port"] == 8000
        assert service_config["enabled"] is True

    @pytest.mark.unit
    def test_get_service_config_not_found(self):
        """测试获取不存在的服务配置"""
        manager = ConfigManager()
        manager.config = {"services": {}}

        service_config = manager.get_service_config("nonexistent")
        assert service_config is None

    @pytest.mark.unit
    def test_is_service_enabled(self):
        """测试检查服务是否启用"""
        manager = ConfigManager()
        manager.config = {
            "services": {
                "data_manager": {"enabled": True},
                "risk_manager": {"enabled": False}
            }
        }

        assert manager.is_service_enabled("data_manager") is True
        assert manager.is_service_enabled("risk_manager") is False
        assert manager.is_service_enabled("nonexistent") is False

    @pytest.mark.unit
    def test_get_service_port(self):
        """测试获取服务端口"""
        manager = ConfigManager()
        manager.config = {
            "services": {
                "data_manager": {"port": 8000},
                "risk_manager": {"port": 8001}
            }
        }

        assert manager.get_service_port("data_manager") == 8000
        assert manager.get_service_port("risk_manager") == 8001
        assert manager.get_service_port("nonexistent") is None

    @pytest.mark.unit
    def test_get_config_thread_safety(self):
        """测试获取配置的线程安全性"""
        manager = ConfigManager()
        manager.config = {"test": "value"}

        def get_config():
            return manager.get_config()

        # 创建多个线程同时获取配置
        threads = []
        results = []

        for _ in range(10):
            thread = threading.Thread(target=lambda: results.append(get_config()))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # 所有结果应该相同
        assert all(result == {"test": "value"} for result in results)

    @pytest.mark.unit
    def test_get_config_value(self):
        """测试获取配置值"""
        manager = ConfigManager()
        manager.config = {
            "existing_key": "existing_value",
            "nested": {"key": "nested_value"}
        }

        assert manager.get_config_value("existing_key") == "existing_value"
        assert manager.get_config_value("nonexistent", "default") == "default"
        assert manager.get_config_value("nested") == {"key": "nested_value"}

    @pytest.mark.unit
    def test_add_remove_callback(self):
        """测试添加和移除回调函数"""
        manager = ConfigManager()

        callback1 = Mock()
        callback2 = Mock()

        # 添加回调
        manager.add_reload_callback(callback1)
        manager.add_reload_callback(callback2)

        assert len(manager._callbacks) == 2

        # 移除回调
        manager.remove_reload_callback(callback1)
        assert len(manager._callbacks) == 1
        assert callback2 in manager._callbacks

    @pytest.mark.unit
    @patch('src.utils.config_loader.logger')
    def test_add_invalid_callback(self, mock_logger):
        """测试添加无效回调函数"""
        manager = ConfigManager()

        manager.add_reload_callback("not_callable")
        mock_logger.error.assert_called()

    @pytest.mark.unit
    @patch('src.utils.config_loader.logger')
    def test_remove_nonexistent_callback(self, mock_logger):
        """测试移除不存在的回调函数"""
        manager = ConfigManager()
        callback = Mock()

        manager.remove_reload_callback(callback)
        mock_logger.warning.assert_called()

    @pytest.mark.unit
    @patch('time.sleep')
    @patch('src.utils.config_loader.logger')
    def test_call_callbacks(self, mock_logger, mock_sleep):
        """测试调用回调函数"""
        manager = ConfigManager()

        callback1 = Mock()
        callback2 = Mock()
        callback3 = Mock(side_effect=Exception("Callback error"))

        manager._callbacks = [callback1, callback2, callback3]

        manager._call_callbacks()

        # 成功的回调应该被调用
        callback1.assert_called_once()
        callback2.assert_called_once()
        callback3.assert_called_once()

        # 错误应该被记录
        mock_logger.error.assert_called()


class TestConfigFileHandler:
    """测试配置文件处理器"""

    @pytest.mark.unit
    @patch('time.sleep')
    def test_on_modified_config_file(self, mock_sleep):
        """测试配置文件修改事件"""
        manager = Mock()
        manager.config_dir = "/tmp"
        handler = ConfigFileHandler(manager)

        # 创建模拟事件
        event = Mock()
        event.is_directory = False
        event.src_path = "/path/to/base.json"
        manager.reload_config = Mock()

        with patch('os.path.basename') as mock_basename:
            mock_basename.return_value = "base.json"

            handler.on_modified(event)

            manager.reload_config.assert_called_once()

    @pytest.mark.unit
    def test_on_modified_non_config_file(self):
        """测试非配置文件修改事件"""
        manager = Mock()
        handler = ConfigFileHandler(manager)

        # 创建模拟事件
        event = Mock()
        event.is_directory = False
        event.src_path = "/path/to/other.txt"

        handler.on_modified(event)

        manager.reload_config.assert_not_called()

    @pytest.mark.unit
    def test_on_modified_directory(self):
        """测试目录修改事件"""
        manager = Mock()
        handler = ConfigFileHandler(manager)

        # 创建模拟事件
        event = Mock()
        event.is_directory = True

        handler.on_modified(event)

        manager.reload_config.assert_not_called()


class TestGetConfigManager:
    """测试全局配置管理器获取函数"""

    @pytest.mark.unit
    @patch('src.utils.config_loader._config_manager', None)
    def test_get_config_manager_singleton(self):
        """测试配置管理器单例"""
        manager1 = get_config_manager()
        manager2 = get_config_manager()

        # 应该返回同一个实例
        assert manager1 is manager2

    @pytest.mark.unit
    def test_get_config_manager_existing(self):
        """测试获取已存在的配置管理器"""
        existing_manager = Mock()

        with patch('src.utils.config_loader._config_manager', existing_manager):
            manager = get_config_manager()

            # 应该返回已存在的实例
            assert manager is existing_manager
