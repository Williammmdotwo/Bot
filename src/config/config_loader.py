"""
ConfigLoader - 策略配置加载器

职责：
- 从 JSON 文件加载策略配置
- 提供 Pydantic 模型验证
- 支持环境变量覆盖

设计原则：
- 配置即代码：使用 JSON 文件，易于版本控制
- 类型安全：使用 Pydantic 模型验证
- 灵活覆盖：支持环境变量覆盖配置
"""

import json
import os
from typing import Optional, Dict, Any
from pathlib import Path
import logging

try:
    from pydantic import BaseModel, Field, validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    logging.warning("Pydantic 不可用，将使用基础配置加载（无类型验证）")

logger = logging.getLogger(__name__)


# ========== Pydantic 模型定义 ==========

if PYDANTIC_AVAILABLE:

    class PositionSizingConfig(BaseModel):
        """仓位管理配置"""
        base_equity_ratio: float = Field(default=0.02, ge=0.001, le=1.0)
        max_leverage: float = Field(default=5.0, ge=1.0, le=100.0)
        min_order_value: float = Field(default=10.0, gt=0)
        signal_scaling_enabled: bool = True
        signal_threshold_normal: float = Field(default=5.0, gt=0)
        signal_threshold_aggressive: float = Field(default=10.0, gt=0)
        signal_aggressive_multiplier: float = Field(default=1.5, gt=0)
        liquidity_protection_enabled: bool = True
        liquidity_depth_ratio: float = Field(default=0.20, ge=0.01, le=1.0)
        liquidity_depth_levels: int = Field(default=3, ge=1, le=10)
        volatility_protection_enabled: bool = True
        volatility_ema_period: int = Field(default=20, ge=5, le=100)
        volatility_threshold: float = Field(default=0.001, gt=0)

    class ExecutionAlgoConfig(BaseModel):
        """执行算法配置"""
        enable_chasing: bool = True
        min_chasing_distance_pct: float = Field(default=0.0005, gt=0)
        max_chase_distance_pct: float = Field(default=0.001, gt=0)
        min_order_life_seconds: float = Field(default=2.0, gt=0)
        aggressive_maker_spread_ticks: float = Field(default=2.0, gt=0)
        aggressive_maker_price_offset: float = Field(default=1.0, ge=0)

    class SignalGeneratorConfig(BaseModel):
        """信号生成器配置"""
        ema_period: int = Field(default=50, ge=5, le=200)
        spread_threshold_pct: float = Field(default=0.0005, gt=0)

    class StrategyParams(BaseModel):
        """策略参数"""
        imbalance_ratio: float = Field(default=5.0, gt=0)
        min_flow_usdt: float = Field(default=5000.0, gt=0)
        take_profit_pct: float = Field(default=0.002, gt=0)
        stop_loss_pct: float = Field(default=0.01, gt=0)
        time_limit_seconds: int = Field(default=30, gt=0)
        cooldown_seconds: float = Field(default=0.1, gt=0)
        maker_timeout_seconds: float = Field(default=3.0, gt=0)

    class StrategyConfig(BaseModel):
        """完整策略配置"""
        strategy_name: str
        version: str
        description: Optional[str] = None
        symbol: str
        mode: str = Field(default="PRODUCTION")
        strategy_params: StrategyParams
        position_sizing: PositionSizingConfig
        execution_algo: ExecutionAlgoConfig
        signal_generator: SignalGeneratorConfig


# ========== ConfigLoader 类 ==========

class ConfigLoader:
    """
    配置加载器

    职责：
    - 从 JSON 文件加载配置
    - 使用 Pydantic 验证配置（如果可用）
    - 支持环境变量覆盖

    使用示例：
        >>> loader = ConfigLoader('config/strategies/scalper_v2.json')
        >>> config = loader.load()
        >>> # 或者
        >>> config = loader.load_with_env_override('MY_STRATEGY_')
    """

    def __init__(self, config_path: str):
        """
        初始化配置加载器

        Args:
            config_path: 配置文件路径（相对于项目根目录）
        """
        self.config_path = Path(config_path)

        # 检查文件是否存在
        if not self.config_path.exists():
            logger.error(f"配置文件不存在: {self.config_path}")
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        logger.info(f"ConfigLoader 初始化: {self.config_path}")

    def load(self) -> Dict[str, Any]:
        """
        加载配置文件

        Returns:
            Dict: 配置字典
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_dict = json.load(f)

            logger.info(f"✅ 配置加载成功: {self.config_path}")

            # 如果 Pydantic 可用，进行验证
            if PYDANTIC_AVAILABLE:
                try:
                    config_obj = StrategyConfig(**config_dict)
                    logger.info("✅ Pydantic 配置验证通过")
                    return config_obj.dict()
                except Exception as e:
                    logger.error(f"❌ Pydantic 配置验证失败: {e}")
                    raise

            # 如果 Pydantic 不可用，直接返回字典
            return config_dict

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 解析失败: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 配置加载失败: {e}")
            raise

    def load_with_env_override(self, env_prefix: str = "STRATEGY_") -> Dict[str, Any]:
        """
        加载配置并应用环境变量覆盖

        Args:
            env_prefix: 环境变量前缀（例如 "STRATEGY_"）

        Returns:
            Dict: 配置字典（已应用环境变量覆盖）

        环境变量命名规则：
            - 嵌套结构使用 __ 分隔
            - 例如：STRATEGY_SYMBOL, STRATEGY_POSITION_SIZING__BASE_EQUITY_RATIO
        """
        config_dict = self.load()

        # 遍历环境变量
        for key, value in os.environ.items():
            if key.startswith(env_prefix):
                # 移除前缀并转换为小写
                config_key = key[len(env_prefix):].lower()

                # 替换 __ 为 .
                config_key = config_key.replace("__", ".")

                # 解析值
                parsed_value = self._parse_env_value(value)

                # 更新配置（递归）
                self._update_config_dict(config_dict, config_key, parsed_value)

                logger.info(f"🔧 环境变量覆盖: {key} = {parsed_value}")

        return config_dict

    def _parse_env_value(self, value: str) -> Any:
        """
        解析环境变量值

        Args:
            value: 环境变量字符串值

        Returns:
            解析后的值（int, float, bool, str）
        """
        # 尝试解析为布尔值
        if value.lower() in ('true', '1', 'yes'):
            return True
        elif value.lower() in ('false', '0', 'no'):
            return False

        # 尝试解析为数字
        try:
            # 尝试整数
            if '.' not in value:
                return int(value)
            else:
                return float(value)
        except ValueError:
            pass

        # 返回字符串
        return value

    def _update_config_dict(self, config_dict: Dict[str, Any], key: str, value: Any):
        """
        递归更新配置字典

        Args:
            config_dict: 配置字典
            key: 配置键（支持点号分隔的嵌套结构）
            value: 要设置的值
        """
        keys = key.split('.')
        d = config_dict

        # 遍历到最后一个键之前
        for k in keys[:-1]:
            if k not in d:
                d[k] = {}
            d = d[k]

        # 设置最后一个键
        d[keys[-1]] = value

    @staticmethod
    def get_strategy_config_path(strategy_name: str) -> str:
        """
        获取策略配置文件路径

        Args:
            strategy_name: 策略名称（例如 "scalper_v2"）

        Returns:
            配置文件路径
        """
        # 假设配置文件在 config/strategies/ 目录下
        return f"config/strategies/{strategy_name}.json"


# ========== 便捷函数 ==========

def load_strategy_config(strategy_name: str, env_prefix: Optional[str] = None) -> Dict[str, Any]:
    """
    便捷函数：加载策略配置

    Args:
        strategy_name: 策略名称
        env_prefix: 环境变量前缀（可选）

    Returns:
        配置字典

    使用示例：
        >>> config = load_strategy_config('scalper_v2')
        >>> # 或者
        >>> config = load_strategy_config('scalper_v2', env_prefix='MY_STRATEGY_')
    """
    config_path = ConfigLoader.get_strategy_config_path(strategy_name)
    loader = ConfigLoader(config_path)

    if env_prefix:
        return loader.load_with_env_override(env_prefix)
    else:
        return loader.load()
