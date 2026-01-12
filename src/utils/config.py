import os
import json
import logging
import threading
from typing import Dict, Any, Callable, List, Optional
from pydantic import BaseModel, ValidationError, Field
from dataclasses import dataclass
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path

logger = logging.getLogger(__name__)


class ServiceConfig(BaseModel):
    """服务配置模型"""
    port: int = Field(ge=1, le=65535, description="服务端口")
    enabled: bool = True
    host: str = "localhost"


class DatabaseConfig(BaseModel):
    """数据库配置模型"""
    use_database: bool = True
    mock_data: bool = False
    host: str = "localhost"
    port: int = Field(5432, ge=1, le=65535)
    name: str = "athena_trader"
    user: str = "athena"
    pool_size: int = Field(10, ge=1, le=100)
    max_overflow: int = Field(20, ge=0, le=100)


class RedisConfig(BaseModel):
    """Redis配置模型"""
    enabled: bool = True
    host: str = "localhost"
    port: int = Field(6379, ge=1, le=65535)
    db: int = Field(0, ge=0, le=15)
    max_connections: int = Field(10, ge=1, le=100)


class LoggingConfig(BaseModel):
    """日志配置模型"""
    level: str = Field("INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    console_output: bool = True
    file_path: Optional[str] = None
    max_file_size: str = "10MB"
    backup_count: int = Field(5, ge=1, le=50)


class TradingConfig(BaseModel):
    """交易配置模型"""
    use_demo: bool = True
    simulation_mode: bool = False
    test_duration_minutes: int = Field(30, ge=1, le=1440)
    signal_interval_seconds: int = Field(15, ge=1, le=3600)
    progress_interval_seconds: int = Field(30, ge=1, le=3600)
    default_symbols: List[str] = ["BTC-USDT", "ETH-USDT"]
    default_timeframes: List[str] = ["5m", "15m", "1h", "4h"]


class RiskLimitsConfig(BaseModel):
    """风险限制配置模型"""
    max_single_order_size_percent: float = Field(0.1, ge=0.001, le=1.0)
    max_total_position_percent: float = Field(0.5, ge=0.001, le=1.0)
    mandatory_stop_loss_percent: float = Field(-0.02, le=0)
    mandatory_take_profit_percent: float = Field(0.05, ge=0)
    max_drawdown_percent: float = Field(0.15, ge=0, le=1.0)


class AuthConfig(BaseModel):
    """认证配置模型"""
    internal_token: str
    require_auth: bool = True


class PerformanceConfig(BaseModel):
    """性能配置模型"""
    max_response_time_seconds: int = Field(30, ge=1, le=300)
    max_fetch_time_seconds: int = Field(5, ge=1, le=60)
    max_indicator_calc_time_seconds: float = Field(0.1, ge=0.001, le=10.0)
    health_check_interval_seconds: int = Field(60, ge=10, le=3600)


class AthenaConfigSchema(BaseModel):
    """Athena配置完整模型"""
    environment: str = Field("development", pattern="^(development|test|production|local)$")
    database: DatabaseConfig = DatabaseConfig()
    redis: RedisConfig = RedisConfig()
    services: Dict[str, ServiceConfig] = {}
    logging: LoggingConfig = LoggingConfig()
    trading: TradingConfig = TradingConfig()
    risk_limits: RiskLimitsConfig = RiskLimitsConfig()
    auth: AuthConfig
    performance: PerformanceConfig = PerformanceConfig()


class ConfigManager:
    """统一配置管理器 - 支持环境分离和热加载"""

    def __init__(self, environment: Optional[str] = None):
        """初始化配置管理器"""
        # 获取环境
        self.environment = environment or os.getenv('ATHENA_ENV', 'development')

        # 获取配置目录
        self.config_dir = self._get_config_dir()

        # 初始化配置
        self.config: Dict[str, Any] = {}

        # 线程安全锁
        self._lock = threading.Lock()

        # 回调函数列表
        self._callbacks: List[Callable[[], None]] = []

        # 文件监视器
        self._observer = None
        self._watching = False

        # 初始加载配置
        self._load_initial_config()

        logger.info(f"配置管理器初始化完成，环境: {self.environment}, 配置目录: {self.config_dir}")

    def _get_config_dir(self) -> str:
        """获取配置目录路径"""
        # 优先使用环境变量
        env_path = os.getenv('CONFIG_PATH')
        if env_path:
            if os.path.isdir(env_path):
                logger.info(f"使用环境变量配置目录: {env_path}")
                return env_path
            else:
                logger.warning(f"CONFIG_PATH 不是目录: {env_path}")

        # 默认路径：项目根目录下的 config 目录
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        default_path = os.path.join(project_root, 'config')
        logger.info(f"使用默认配置目录: {default_path}")
        return default_path

    def _load_initial_config(self):
        """初始加载配置 - 支持环境分离"""
        try:
            # 确保配置目录路径没有尾部空格
            self.config_dir = self.config_dir.strip()

            # 加载基础配置
            base_config_path = os.path.join(self.config_dir, 'base.json')
            if not os.path.exists(base_config_path):
                logger.critical(f"基础配置文件不存在: {base_config_path}")
                exit(1)

            with open(base_config_path, 'r', encoding='utf-8') as f:
                base_config = json.load(f)

            # 加载环境特定配置
            env_config_path = os.path.join(self.config_dir, f'{self.environment}.json')
            env_config = {}
            if os.path.exists(env_config_path):
                with open(env_config_path, 'r', encoding='utf-8') as f:
                    env_config = json.load(f)
                logger.info(f"已加载环境配置: {env_config_path}")
            else:
                logger.warning(f"环境配置文件不存在: {env_config_path}，仅使用基础配置")

            # 加载本地覆盖配置（不提交到版本控制）
            local_config_path = os.path.join(self.config_dir, 'local.json')
            local_config = {}
            if os.path.exists(local_config_path):
                with open(local_config_path, 'r', encoding='utf-8') as f:
                    local_config = json.load(f)
                logger.info(f"已加载本地覆盖配置: {local_config_path}")

            # 合并配置：base -> environment -> local
            merged_config = self._merge_configs(base_config, env_config, local_config)

            # 验证最终配置
            self._validate_config(merged_config)

            with self._lock:
                self.config = merged_config

            logger.info(f"配置加载成功，环境: {self.environment}")

        except json.JSONDecodeError as e:
            logger.critical(f"配置文件JSON格式错误: {e}")
            exit(1)
        except ValidationError as e:
            logger.critical(f"配置文件验证失败: {e}")
            exit(1)
        except Exception as e:
            logger.critical(f"加载配置文件失败: {e}")
            exit(1)

    def _merge_configs(self, base_config: Dict[str, Any], env_config: Dict[str, Any], local_config: Dict[str, Any]) -> Dict[str, Any]:
        """深度合并配置"""
        result = base_config.copy()

        # 合并环境配置
        result = self._deep_merge(result, env_config)

        # 合并本地配置
        result = self._deep_merge(result, local_config)

        return result

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """深度合并字典"""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def _validate_config(self, config_data: Dict[str, Any]):
        """验证配置结构"""
        # 基础验证：确保是字典类型
        if not isinstance(config_data, dict):
            raise ValidationError("配置文件根节点必须是对象")

        # 使用Pydantic模型进行详细验证
        try:
            # 预处理配置数据以适应模型
            processed_config = self._preprocess_config(config_data)

            # 验证配置
            validated_config = AthenaConfigSchema(**processed_config)

            # 额外的业务逻辑验证
            self._validate_business_rules(validated_config.model_dump())

            logger.info("配置验证通过")

        except ValidationError as e:
            error_msg = f"配置验证失败: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)  # 改为ValueError避免递归
        except Exception as e:
            error_msg = f"配置验证过程中发生错误: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)  # 改为ValueError避免递归

    def _preprocess_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """预处理配置数据以适应验证模型"""
        processed = config_data.copy()

        # 确保services字段存在
        if 'services' not in processed:
            processed['services'] = {}

        # 处理services配置，确保每个服务都有必要的字段
        services = processed['services']
        default_services = {
            'data_manager': {'port': 8000, 'enabled': True, 'host': 'localhost'},
            'risk_manager': {'port': 8001, 'enabled': True, 'host': 'localhost'},
            'executor': {'port': 8002, 'enabled': True, 'host': 'localhost'},
            'strategy_engine': {'port': 8003, 'enabled': True, 'host': 'localhost'}
        }

        for service_name, default_config in default_services.items():
            if service_name not in services:
                services[service_name] = default_config
            else:
                # 合并默认配置
                for key, value in default_config.items():
                    if key not in services[service_name]:
                        services[service_name][key] = value

        # 确保auth字段存在
        if 'auth' not in processed:
            processed['auth'] = {'internal_token': 'athena-default-token', 'require_auth': True}
        elif 'internal_token' not in processed['auth']:
            processed['auth']['internal_token'] = 'athena-default-token'

        return processed

    def _validate_business_rules(self, config: Dict[str, Any]):
        """验证业务规则"""
        # 验证端口不冲突
        used_ports = set()
        for service_name, service_config in config.get('services', {}).items():
            port = service_config.get('port')
            if port:
                if port in used_ports:
                    raise ValueError(f"端口冲突: {port} 被多个服务使用")
                used_ports.add(port)

        # 验证风险限制的合理性
        risk_limits = config.get('risk_limits', {})
        max_single = risk_limits.get('max_single_order_size_percent', 0)
        max_total = risk_limits.get('max_total_position_percent', 0)

        if max_single > max_total:
            raise ValueError("单笔订单最大比例不能超过总持仓最大比例")

        # 验证环境特定的配置
        environment = config.get('environment', 'development')
        if environment == 'production':
            # 生产环境必须使用数据库
            if not config.get('database', {}).get('use_database', True):
                logger.warning("生产环境建议启用数据库")

            # 生产环境必须启用认证
            if not config.get('auth', {}).get('require_auth', True):
                raise ValueError("生产环境必须启用认证")

        elif environment == 'local':
            # 本地环境建议使用模拟数据
            if not config.get('database', {}).get('mock_data', False):
                logger.info("本地环境建议启用模拟数据")

    def validate_config_only(self) -> bool:
        """仅验证当前配置，不重新加载"""
        try:
            with self._lock:
                self._validate_config(self.config)
            return True
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            return False

    def get_service_config(self, service_name: str) -> Optional[Dict[str, Any]]:
        """获取特定服务的配置"""
        with self._lock:
            services = self.config.get('services', {})
            return services.get(service_name)

    def is_service_enabled(self, service_name: str) -> bool:
        """检查服务是否启用"""
        service_config = self.get_service_config(service_name)
        return service_config.get('enabled', False) if service_config else False

    def get_service_port(self, service_name: str) -> Optional[int]:
        """获取服务端口"""
        service_config = self.get_service_config(service_name)
        return service_config.get('port') if service_config else None

    def reload_config(self) -> bool:
        """重新加载配置文件 - 支持环境分离"""
        try:
            # 重新加载所有配置文件
            self._load_initial_config()

            logger.info("配置重载成功")

            # 调用所有回调函数
            self._call_callbacks()

            return True

        except Exception as e:
            logger.error(f"重载配置文件失败: {e}")
            return False

    def start_watching(self):
        """开始监视配置文件变化"""
        if self._watching:
            logger.warning("配置文件监视已在运行")
            return

        try:
            # 创建事件处理器
            event_handler = ConfigFileHandler(self)

            # 创建监视器 - 监视整个配置目录
            self._observer = Observer()
            self._observer.schedule(
                event_handler,
                self.config_dir,
                recursive=False  # 递归深度为0
            )

            # 启动监视
            self._observer.start()
            self._watching = True

            logger.info(f"开始监视配置目录: {self.config_dir}")

        except Exception as e:
            logger.error(f"启动配置文件监视失败: {e}")

    def stop_watching(self):
        """停止监视配置文件变化"""
        if not self._watching:
            return

        try:
            if self._observer:
                self._observer.stop()
                self._observer.join()
                self._watching = False

                logger.info("停止配置文件监视")

        except Exception as e:
            logger.error(f"停止配置文件监视失败: {e}")

    def add_reload_callback(self, callback: Callable[[], None]):
        """添加配置重载回调函数"""
        if not callable(callback):
            logger.error("回调函数必须是可调用对象")
            return

        with self._lock:
            self._callbacks.append(callback)

        logger.info(f"添加配置重载回调，当前回调数量: {len(self._callbacks)}")

    def remove_reload_callback(self, callback: Callable[[], None]):
        """移除配置重载回调函数"""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)
                logger.info(f"移除配置重载回调，当前回调数量: {len(self._callbacks)}")
            else:
                logger.warning("尝试移除不存在的回调函数")

    def get_config(self) -> Dict[str, Any]:
        """获取当前配置（线程安全）"""
        with self._lock:
            return self.config.copy()

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """获取配置中的指定值"""
        with self._lock:
            return self.config.get(key, default)

    def _call_callbacks(self):
        """调用所有回调函数"""
        callbacks_to_call = []

        with self._lock:
            callbacks_to_call = self._callbacks.copy()

        # 在锁外调用回调函数，避免死锁
        for callback in callbacks_to_call:
            try:
                callback()
            except Exception as e:
                logger.error(f"配置重载回调函数执行失败: {e}")

    def __del__(self):
        """析构函数"""
        self.stop_watching()


class ConfigFileHandler(FileSystemEventHandler):
    """配置文件事件处理器"""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager

    def on_modified(self, event):
        """文件修改事件处理"""
        if event.is_directory:
            return

        # 检查是否是配置文件
        config_files = ['base.json', 'development.json', 'test.json', 'production.json', 'local.json']
        filename = os.path.basename(event.src_path)

        if filename in config_files:
            logger.info(f"检测到配置文件修改: {event.src_path}")

            # 延迟一小段时间，确保文件写入完成
            import time
            time.sleep(0.1)

            # 重载配置
            self.config_manager.reload_config()


# 全局配置管理器实例
_config_manager = None

def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


# ==================== 环境变量配置加载函数 ====================
# 以下函数用于从 .env 文件加载策略配置


@dataclass
class ScalperV1Config:
    """ScalperV1 策略配置"""
    symbol: str = "SOL-USDT-SWAP"
    min_flow: float = 1000.0
    imbalance_ratio: float = 3.0
    leverage: float = 5.0
    take_profit_pct: float = 0.002
    stop_loss_pct: float = 0.01
    time_limit_seconds: int = 5
    max_order_size: float = 500.0
    single_loss_cap: float = 0.02
    daily_loss_limit: float = 0.05
    position_size: Optional[float] = None


@dataclass
class DualEMAConfig:
    """DualEMA 策略配置"""
    symbol: str = "BTC-USDT-SWAP"
    fast_period: int = 9
    slow_period: int = 21
    timeframe: int = 5
    leverage: float = 1.5
    atr_multiplier: float = 2.0


@dataclass
class SniperConfig:
    """Sniper 策略配置（已废弃，仅用于兼容）"""
    symbol: str = "BTC-USDT-SWAP"
    position_size: float = 0.1
    cooldown_seconds: float = 5.0
    order_type: str = "market"
    min_big_order: float = 5000.0


def load_scalper_config() -> ScalperV1Config:
    """
    从环境变量加载 ScalperV1 配置

    Returns:
        ScalperV1Config: ScalperV1 配置对象
    """
    config = ScalperV1Config()

    # 读取环境变量
    config.symbol = os.getenv('SCALPER_SYMBOL', config.symbol)
    config.min_flow = float(os.getenv('SCALPER_MIN_FLOW', str(config.min_flow)))
    config.imbalance_ratio = float(os.getenv('SCALPER_IMBALANCE_RATIO', str(config.imbalance_ratio)))
    config.leverage = float(os.getenv('SCALPER_LEVERAGE', str(config.leverage)))
    config.take_profit_pct = float(os.getenv('SCALPER_TAKE_PROFIT_PCT', str(config.take_profit_pct)))
    config.stop_loss_pct = float(os.getenv('SCALPER_STOP_LOSS_PCT', str(config.stop_loss_pct)))
    config.time_limit_seconds = int(os.getenv('SCALPER_TIME_LIMIT_SECONDS', str(config.time_limit_seconds)))
    config.max_order_size = float(os.getenv('SCALPER_MAX_ORDER_SIZE', str(config.max_order_size)))
    config.single_loss_cap = float(os.getenv('SCALPER_SINGLE_LOSS_CAP', str(config.single_loss_cap)))
    config.daily_loss_limit = float(os.getenv('SCALPER_DAILY_LOSS_LIMIT', str(config.daily_loss_limit)))

    # 可选参数
    position_size_str = os.getenv('SCALPER_POSITION_SIZE')
    if position_size_str:
        config.position_size = float(position_size_str)

    logger.info(f"加载 ScalperV1 配置: symbol={config.symbol}, "
                f"leverage={config.leverage}x, "
                f"min_flow={config.min_flow} USDT, "
                f"imbalance_ratio={config.imbalance_ratio}x")

    return config


def load_dual_ema_config() -> DualEMAConfig:
    """
    从环境变量加载 DualEMA 配置

    Returns:
        DualEMAConfig: DualEMA 配置对象
    """
    config = DualEMAConfig()

    # 读取环境变量
    config.symbol = os.getenv('DUAL_EMA_SYMBOL', config.symbol)
    config.fast_period = int(os.getenv('DUAL_EMA_FAST_PERIOD', str(config.fast_period)))
    config.slow_period = int(os.getenv('DUAL_EMA_SLOW_PERIOD', str(config.slow_period)))
    config.timeframe = int(os.getenv('DUAL_EMA_TIMEFRAME', str(config.timeframe)))
    config.leverage = float(os.getenv('DUAL_EMA_LEVERAGE', str(config.leverage)))
    config.atr_multiplier = float(os.getenv('DUAL_EMA_ATR_MULTIPLIER', str(config.atr_multiplier)))

    logger.info(f"加载 DualEMA 配置: symbol={config.symbol}, "
                f"fast={config.fast_period}, slow={config.slow_period}, "
                f"timeframe={config.timeframe}m, leverage={config.leverage}x")

    return config


def load_sniper_config() -> SniperConfig:
    """
    从环境变量加载 Sniper 配置（已废弃）

    ⚠️ 此函数已废弃，Sniper 策略已迁移到直接在代码中配置

    Returns:
        SniperConfig: Sniper 配置对象
    """
    logger.warning("load_sniper_config() 已废弃，Sniper 策略已迁移到直接在代码中配置")

    config = SniperConfig()

    # 读取环境变量
    config.symbol = os.getenv('TRADING_SYMBOL', config.symbol)
    config.position_size = float(os.getenv('SNIPER_POSITION_SIZE', str(config.position_size)))
    config.cooldown_seconds = float(os.getenv('SNIPER_COOLDOWN', str(config.cooldown_seconds)))
    config.order_type = os.getenv('SNIPER_ORDER_TYPE', config.order_type)
    config.min_big_order = float(os.getenv('SNIPER_MIN_BIG_ORDER', str(config.min_big_order)))

    logger.info(f"加载 Sniper 配置（已废弃）: symbol={config.symbol}, "
                f"position_size={config.position_size}, "
                f"cooldown={config.cooldown_seconds}s")

    return config


def load_main_config() -> Dict[str, Any]:
    """
    从环境变量加载主配置

    Returns:
        Dict[str, Any]: 主配置字典
    """
    config = {}

    # 基础配置
    config['environment'] = os.getenv('ENV', 'production')
    config['log_level'] = os.getenv('LOG_LEVEL', 'INFO')

    # 交易所 API 配置
    config['rest_gateway'] = {
        'api_key': os.getenv('OKX_API_KEY', ''),
        'secret_key': os.getenv('OKX_SECRET_KEY', ''),
        'passphrase': os.getenv('OKX_PASSPHRASE', ''),
        'use_demo': os.getenv('USE_DEMO', 'true').lower() == 'true'
    }

    # 资金配置
    config['total_capital'] = float(os.getenv('TOTAL_CAPITAL', '100.0'))

    # 策略选择
    config['active_strategy'] = os.getenv('ACTIVE_STRATEGY', 'scalper_v1')

    logger.info(f"加载主配置: environment={config['environment']}, "
                f"strategy={config['active_strategy']}, "
                f"capital={config['total_capital']} USDT")

    return config
