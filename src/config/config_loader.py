"""
ConfigLoader - 统一配置加载器

职责：
- 统一加载所有策略配置
- 支持 strategy_config.py 中的配置类
- 提供便捷的配置加载接口
- 支持环境变量和 JSON 文件加载

设计原则：
- 配置即代码：使用 dataclass 定义
- 类型安全：使用类型注解
- 统一接口：所有策略使用相同加载方式
- 易于测试：支持灵活的配置来源
"""

import os
from typing import Optional
from pathlib import Path
import logging

# 导入统一的策略配置
from .strategy_config import ScalperConfig, BaseStrategyConfig

logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    统一配置加载器

    职责：
    - 从环境变量加载策略配置
    - 从 JSON 文件加载策略配置
    - 提供统一的配置加载接口

    使用示例：
        >>> # 方式 1：从环境变量加载
        >>> config = ConfigLoader.load_strategy_config("scalper_v2", source="env")
        >>>
        >>> # 方式 2：从 JSON 文件加载
        >>> config = ConfigLoader.load_strategy_config(
        ...     "scalper_v2",
        ...     source="json",
        ...     file_path="config/strategies/scalper_v2.json"
        ... )
    """

    @staticmethod
    def load_strategy_config(
        strategy_type: str,
        source: str = "env",
        file_path: Optional[str] = None,
        env_prefix: str = "SCALPER"
    ) -> BaseStrategyConfig:
        """
        加载策略配置（统一接口）

        Args:
            strategy_type: 策略类型（"scalper_v2"）
            source: 配置来源（"env" 或 "json"）
            file_path: JSON 文件路径（source="json" 时必需）
            env_prefix: 环境变量前缀（source="env" 时使用）

        Returns:
            BaseStrategyConfig: 策略配置对象

        Raises:
            ValueError: 未知的策略类型或配置来源
            FileNotFoundError: JSON 文件不存在

        使用示例：
            >>> # 从环境变量加载
            >>> config = ConfigLoader.load_strategy_config("scalper_v2")
            >>>
            >>> # 从 JSON 文件加载
            >>> config = ConfigLoader.load_strategy_config(
            ...     "scalper_v2",
            ...     source="json",
            ...     file_path="config/strategies/scalper_v2.json"
            ... )
        """
        # 根据策略类型选择配置类
        if strategy_type == "scalper_v2":
            if source == "env":
                config = ScalperConfig.from_env(env_prefix)
            elif source == "json":
                if not file_path:
                    raise ValueError("source='json' 时必须提供 file_path 参数")
                config = ScalperConfig.from_json_file(file_path)
            else:
                raise ValueError(f"未知的配置来源: {source}（必须是 'env' 或 'json'）")
        else:
            raise ValueError(f"未知的策略类型: {strategy_type}")

        # 验证配置
        config.validate()

        logger.info(f"✅ 策略配置加载成功: {strategy_type} (source={source})")
        return config

    @staticmethod
    def get_default_strategy_config_path(strategy_name: str) -> str:
        """
        获取默认策略配置文件路径

        Args:
            strategy_name: 策略名称（例如 "scalper_v2"）

        Returns:
            配置文件路径
        """
        return f"config/strategies/{strategy_name}.json"
