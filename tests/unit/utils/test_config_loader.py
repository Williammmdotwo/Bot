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


class TestConfigManager:
    """测试配置管理器"""

    @pytest.mark.unit
    def test_config_manager_initialization(self):
        """测试配置管理器初始化"""
        with patch('os.getenv') as mock_getenv:
            mock_getenv.return_value = 'test'
            
            with patch('os.path.exists') as mock_exists:
                mock_exists.return_value = True
                
                with patch('builtins.open', create=True) as mock_open:
                    mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({
                        "environment": "test",
                        "database": {"use_database": True},
                        "auth": {"internal_token": "test-token"}
                    })
                    
                    manager = ConfigManager()
                    assert manager.environment == 'test'
                    assert isinstance(manager.config, dict)

    @pytest.mark.unit
    def test_get_config_dir_from_env(self):
        """测试从环境变量获取配置目录"""
        with patch('os.getenv') as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: {
                'ATHENA_ENV': 'development',
                'CONFIG_PATH': '/custom/config/path'
            }.get(key, default)
            
            with patch('os.path.isdir') as mock_isdir:
                mock_isdir.return_value = True
                
                manager = ConfigManager()
                assert manager.config_dir == '/custom/config/path'

    @pytest.mark.unit
    def test_get_config_dir_default(self):
        """测试默认配置目录"""
        with patch('os.getenv') as mock_getenv:
            mock_getenv.return_value = None
            
            manager = ConfigManager()
            # 应该使用默认路径
            assert 'config' in manager.config_dir

    @pytest.mark.unit
    def test_load_initial_config_success(self):
        """测试成功加载初始配置"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建基础配置文件
            base_config = {
                "environment": "development",
                "database": {"use_database": True},
                "auth": {"internal_token": "test-token"}
            }
            base_path = os.path.join(temp_dir, 'base.json')
            with open(base_path, 'w') as f:
                json.dump(base_config, f)
            
            manager = ConfigManager()
            manager.config_dir = temp_dir
            manager._load_initial_config()
            
            assert manager.config["environment"] == "development"
            assert manager.config["database"]["use_database"] is True

    @pytest.mark.unit
    def test_load_initial_config_missing_base(self):
        """测试缺少基础配置文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ConfigManager()
            manager.config_dir = temp_dir
            
            with pytest.raises(SystemExit):
                manager._load_initial_config()

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
    def test_validate_config_success(self):
        """测试成功验证配置"""
        config_data = {
            "environment": "development",
            "database": {"use_database": True},
            "auth": {"internal_token": "test-token"},
            "services": {
                "data_manager": {"port": 8000}
            }
        }
        
        manager = ConfigManager()
        # 应该不抛出异常
        manager._validate_config(config_data)

    @pytest.mark.unit
    def test_validate_config_invalid_type(self):
        """测试验证无效类型配置"""
        config_data = "not a dict"
        
        manager = ConfigManager()
        with pytest.raises(Exception):
            manager._validate_config(config_data)

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
                "data_manager": {"port": 8000, "enabled": True}
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
    def test_reload_config(self):
        """测试重新加载配置"""
        manager = ConfigManager()
        
        with patch.object(manager, '_load_initial_config') as mock_load:
            with patch.object(manager, '_call_callbacks') as mock_callbacks:
                result = manager.reload_config()
                
                assert result is True
                mock_load.assert_called_once()
                mock_callbacks.assert_called_once()

    @pytest.mark.unit
    def test_reload_config_failure(self):
        """测试重新加载配置失败"""
        manager = ConfigManager()
        
        with patch.object(manager, '_load_initial_config') as mock_load:
            mock_load.side_effect = Exception("Load failed")
            
            result = manager.reload_config()
            assert result is False

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
    def test_add_invalid_callback(self):
        """测试添加无效回调函数"""
        manager = ConfigManager()
        
        with patch('src.utils.config_loader.logger') as mock_logger:
            manager.add_reload_callback("not_callable")
            mock_logger.error.assert_called()

    @pytest.mark.unit
    def test_remove_nonexistent_callback(self):
        """测试移除不存在的回调函数"""
        manager = ConfigManager()
        callback = Mock()
        
        with patch('src.utils.config_loader.logger') as mock_logger:
            manager.remove_reload_callback(callback)
            mock_logger.warning.assert_called()

    @pytest.mark.unit
    def test_call_callbacks(self):
        """测试调用回调函数"""
        manager = ConfigManager()
        
        callback1 = Mock()
        callback2 = Mock()
        callback3 = Mock(side_effect=Exception("Callback error"))
        
        manager._callbacks = [callback1, callback2, callback3]
        
        with patch('src.utils.config_loader.logger') as mock_logger:
            manager._call_callbacks()
            
            # 成功的回调应该被调用
            callback1.assert_called_once()
            callback2.assert_called_once()
            callback3.assert_called_once()
            
            # 错误应该被记录
            mock_logger.error.assert_called()

    @pytest.mark.unit
    def test_start_stop_watching(self):
        """测试开始和停止监视配置文件"""
        manager = ConfigManager()
        manager.config_dir = "/tmp"
        
        with patch('src.utils.config_loader.Observer') as mock_observer_class:
            mock_observer = Mock()
            mock_observer_class.return_value = mock_observer
            
            # 开始监视
            manager.start_watching()
            assert manager._watching is True
            mock_observer.start.assert_called_once()
            
            # 停止监视
            manager.stop_watching()
            assert manager._watching is False
            mock_observer.stop.assert_called_once()

    @pytest.mark.unit
    def test_start_watching_already_running(self):
        """测试开始已经运行的监视"""
        manager = ConfigManager()
        manager._watching = True
        
        with patch('src.utils.config_loader.logger') as mock_logger:
            manager.start_watching()
            mock_logger.warning.assert_called()

    @pytest.mark.unit
    def test_validate_config_only(self):
        """测试仅验证配置"""
        manager = ConfigManager()
        manager.config = {
            "environment": "development",
            "database": {"use_database": True},
            "auth": {"internal_token": "test-token"}
        }
        
        result = manager.validate_config_only()
        assert result is True

    @pytest.mark.unit
    def test_validate_config_only_failure(self):
        """测试验证配置失败"""
        manager = ConfigManager()
        manager.config = {"invalid": "config"}
        
        result = manager.validate_config_only()
        assert result is False


class TestConfigFileHandler:
    """测试配置文件处理器"""

    @pytest.mark.unit
    def test_on_modified_config_file(self):
        """测试配置文件修改事件"""
        manager = Mock()
        handler = ConfigFileHandler(manager)
        
        # 创建模拟事件
        event = Mock()
        event.is_directory = False
        event.src_path = "/path/to/base.json"
        
        with patch('time.sleep'):
            with patch('os.path.basename') as mock_basename:
                mock_basename.return_value = "base.json"
                
                handler.on_modified(event)
                
                # 应该调用重载配置
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
        
        with patch('os.path.basename') as mock_basename:
            mock_basename.return_value = "other.txt"
            
            handler.on_modified(event)
            
            # 不应该调用重载配置
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
        
        # 不应该调用重载配置
        manager.reload_config.assert_not_called()


class TestGetConfigManager:
    """测试全局配置管理器获取函数"""

    @pytest.mark.unit
    def test_get_config_manager_singleton(self):
        """测试配置管理器单例"""
        with patch('src.utils.config_loader._config_manager', None):
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


class TestConfigManagerIntegration:
    """配置管理器集成测试"""

    @pytest.mark.unit
    def test_complete_config_workflow(self):
        """测试完整的配置工作流"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建基础配置
            base_config = {
                "environment": "development",
                "database": {
                    "use_database": True,
                    "mock_data": False,
                    "host": "localhost",
                    "port": 5432,
                    "name": "athena_trader",
                    "user": "athena",
                    "pool_size": 10,
                    "max_overflow": 20
                },
                "redis": {
                    "enabled": True,
                    "host": "localhost",
                    "port": 6379,
                    "db": 0,
                    "max_connections": 10
                },
                "services": {
                    "data_manager": {"port": 8000, "enabled": True, "host": "localhost"},
                    "risk_manager": {"port": 8001, "enabled": True, "host": "localhost"}
                },
                "logging": {
                    "level": "INFO",
                    "console_output": True,
                    "file_path": None,
                    "max_file_size": "10MB",
                    "backup_count": 5
                },
                "trading": {
                    "use_demo": True,
                    "simulation_mode": False,
                    "test_duration_minutes": 30,
                    "signal_interval_seconds": 15,
                    "progress_interval_seconds": 30,
                    "default_symbols": ["BTC-USDT", "ETH-USDT"],
                    "default_timeframes": ["5m", "15m", "1h", "4h"]
                },
                "risk_limits": {
                    "max_single_order_size_percent": 0.1,
                    "max_total_position_percent": 0.5,
                    "mandatory_stop_loss_percent": -0.02,
                    "mandatory_take_profit_percent": 0.05,
                    "max_drawdown_percent": 0.15
                },
                "auth": {
                    "internal_token": "athena-test-token",
                    "require_auth": True
                },
                "performance": {
                    "max_response_time_seconds": 30,
                    "max_fetch_time_seconds": 5,
                    "max_indicator_calc_time_seconds": 0.1,
                    "health_check_interval_seconds": 60
                }
            }
            
            base_path = os.path.join(temp_dir, 'base.json')
            with open(base_path, 'w') as f:
                json.dump(base_config, f)
            
            # 创建环境配置
            env_config = {
                "database": {"mock_data": True},
                "trading": {"use_demo": False}
            }
            env_path = os.path.join(temp_dir, 'development.json')
            with open(env_path, 'w') as f:
                json.dump(env_config, f)
            
            # 初始化配置管理器
            manager = ConfigManager()
            manager.config_dir = temp_dir
            manager._load_initial_config()
            
            # 验证配置合并
            assert manager.config["environment"] == "development"
            assert manager.config["database"]["use_database"] is True
            assert manager.config["database"]["mock_data"] is True  # 环境配置覆盖
            assert manager.config["trading"]["use_demo"] is False  # 环境配置覆盖
            
            # 验证服务配置
            assert manager.is_service_enabled("data_manager") is True
            assert manager.get_service_port("data_manager") == 8000
            
            # 验证风险限制
            assert manager.config["risk_limits"]["max_single_order_size_percent"] == 0.1
            
            # 验证认证配置
            assert manager.config["auth"]["internal_token"] == "athena-test-token"

    @pytest.mark.unit
    def test_config_with_local_overrides(self):
        """测试本地覆盖配置"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建基础配置
            base_config = {
                "environment": "development",
                "database": {"use_database": True},
                "auth": {"internal_token": "base-token"}
            }
            base_path = os.path.join(temp_dir, 'base.json')
            with open(base_path, 'w') as f:
                json.dump(base_config, f)
            
            # 创建本地覆盖配置
            local_config = {
                "database": {"mock_data": True},
                "auth": {"internal_token": "local-token"}
            }
            local_path = os.path.join(temp_dir, 'local.json')
            with open(local_path, 'w') as f:
                json.dump(local_config, f)
            
            # 初始化配置管理器
            manager = ConfigManager()
            manager.config_dir = temp_dir
            manager._load_initial_config()
            
            # 验证本地配置覆盖
            assert manager.config["database"]["use_database"] is True  # 保留基础
            assert manager.config["database"]["mock_data"] is True  # 本地添加
            assert manager.config["auth"]["internal_token"] == "local-token"  # 本地覆盖

    @pytest.mark.unit
    def test_config_validation_comprehensive(self):
        """测试全面的配置验证"""
        manager = ConfigManager()
        
        # 测试有效配置
        valid_config = {
            "environment": "development",
            "database": {
                "use_database": True,
                "mock_data": False,
                "host": "localhost",
                "port": 5432,
                "name": "test_db",
                "user": "test_user",
                "pool_size": 10,
                "max_overflow": 20
            },
            "services": {
                "service1": {"port": 8000, "enabled": True, "host": "localhost"},
                "service2": {"port": 8001, "enabled": True, "host": "localhost"}
            },
            "risk_limits": {
                "max_single_order_size_percent": 0.1,
                "max_total_position_percent": 0.5
            },
            "auth": {"internal_token": "test-token", "require_auth": True}
        }
        
        # 应该不抛出异常
        manager._validate_config(valid_config)
        
        # 测试无效配置
        invalid_configs = [
            # 端口冲突
            {
                "environment": "development",
                "services": {
                    "service1": {"port": 8000},
                    "service2": {"port": 8000}
                },
                "auth": {"internal_token": "test-token"}
            },
            # 风险限制不合理
            {
                "environment": "development",
                "risk_limits": {
                    "max_single_order_size_percent": 0.6,
                    "max_total_position_percent": 0.5
                },
                "auth": {"internal_token": "test-token"}
            },
            # 生产环境无认证
            {
                "environment": "production",
                "auth": {"internal_token": "test-token", "require_auth": False}
            }
        ]
        
        for invalid_config in invalid_configs:
            with pytest.raises(Exception):
                manager._validate_config(invalid_config)
