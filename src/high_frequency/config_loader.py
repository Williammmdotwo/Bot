"""
高频交易策略配置加载器

提供配置管理功能，遵循以下原则：
- 不引入 ccxt 或 pandas
- 提供异步配置加载
- 支持从 JSON 配置文件读取
"""

import os
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


# 默认配置
DEFAULT_HFT_CONFIG = {
    "enabled": False,
    "mode": "hybrid",
    "memory_limit_mb": 500,
    "tick_channels": ["trades"],
    # [新增] 动态资金管理配置
    "symbol": "BTC-USDT-SWAP",
    "order_size": 1,
    "ema_fast_period": 9,
    "ema_slow_period": 21,
    "ioc_slippage_pct": 0.002,
    "whale_threshold": 100.0,
    "risk_ratio": 0.2,  # 风险比例：使用 20% 的余额
    "leverage": 10  # 杠杆倍数
}


async def load_hft_config() -> Dict[str, Any]:
    """
    异步加载高频交易策略配置

    配置加载优先级：
    1. 从 config/base.json 的 high_freq_strategies 节点读取
    2. 如果读取失败，使用默认配置

    Returns:
        Dict[str, Any]: 高频交易配置字典，包含以下字段：
            - enabled (bool): 是否启用高频交易策略
            - mode (str): 运行模式（如 "hybrid"）
            - memory_limit_mb (int): 内存限制（MB）
            - tick_channels (List[str]): Tick数据通道列表

    Example:
        >>> config = await load_hft_config()
        >>> print(config['enabled'])
        True
        >>> print(config['mode'])
        'hybrid'
    """
    try:
        # 获取配置文件路径
        config_path = _get_config_file_path()

        # 读取配置文件
        hft_config = _read_hft_config_from_json(config_path)

        # 验证配置
        validated_config = _validate_hft_config(hft_config)

        logger.info(f"高频交易策略配置加载成功: {validated_config}")
        return validated_config

    except Exception as e:
        logger.error(f"加载高频交易配置失败: {e}，使用默认配置")
        return DEFAULT_HFT_CONFIG.copy()


def _get_config_file_path() -> str:
    """
    获取配置文件路径

    Returns:
        str: 配置文件的绝对路径
    """
    # 获取项目根目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))

    # 构建配置文件路径
    config_path = os.path.join(project_root, 'config', 'base.json')

    logger.debug(f"配置文件路径: {config_path}")
    return config_path


def _read_hft_config_from_json(config_path: str) -> Dict[str, Any]:
    """
    从 JSON 配置文件中读取高频交易配置

    Args:
        config_path (str): 配置文件路径

    Returns:
        Dict[str, Any]: 高频交易配置字典

    Raises:
        FileNotFoundError: 配置文件不存在
        json.JSONDecodeError: JSON 格式错误
        KeyError: 配置节点不存在
    """
    # 检查文件是否存在
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    # 读取 JSON 文件
    with open(config_path, 'r', encoding='utf-8') as f:
        full_config = json.load(f)

    # 提取高频交易配置节点
    if 'high_freq_strategies' not in full_config:
        raise KeyError("配置文件中缺少 'high_freq_strategies' 节点")

    hft_config = full_config['high_freq_strategies']
    logger.debug(f"从配置文件读取到的高频交易配置: {hft_config}")

    return hft_config


def _validate_hft_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证高频交易配置的完整性和有效性

    Args:
        config (Dict[str, Any]): 待验证的配置字典

    Returns:
        Dict[str, Any]: 验证后的配置字典（补充默认值）

    Raises:
        ValueError: 配置验证失败
    """
    # 验证必需字段
    if 'enabled' not in config:
        raise ValueError("配置缺少 'enabled' 字段")

    if not isinstance(config['enabled'], bool):
        raise ValueError("'enabled' 字段必须是布尔类型")

    # 验证并设置默认值
    validated = DEFAULT_HFT_CONFIG.copy()
    validated.update(config)

    # 类型验证
    if not isinstance(validated['mode'], str):
        raise ValueError("'mode' 字段必须是字符串类型")

    if not isinstance(validated['memory_limit_mb'], int) or validated['memory_limit_mb'] <= 0:
        raise ValueError("'memory_limit_mb' 必须是正整数")

    if not isinstance(validated['tick_channels'], list):
        raise ValueError("'tick_channels' 必须是列表类型")

    # 值验证
    valid_modes = ['hybrid', 'live', 'simulation', 'backtest']
    if validated['mode'] not in valid_modes:
        logger.warning(f"未知的运行模式 '{validated['mode']}'，有效模式: {valid_modes}")

    if validated['memory_limit_mb'] > 4096:
        logger.warning(f"内存限制 {validated['memory_limit_mb']}MB 过高，可能影响系统性能")

    if not validated['tick_channels']:
        logger.warning("'tick_channels' 为空，将无法接收市场数据")

    logger.debug(f"配置验证通过: {validated}")
    return validated


def get_hft_config_sync() -> Dict[str, Any]:
    """
    同步方式获取高频交易配置（用于非异步上下文）

    注意：此函数提供同步接口，但在异步环境中应使用 load_hft_config()

    Returns:
        Dict[str, Any]: 高频交易配置字典

    Example:
        >>> config = get_hft_config_sync()
        >>> print(config['enabled'])
        True
    """
    try:
        # 获取配置文件路径
        config_path = _get_config_file_path()

        # 读取配置文件
        hft_config = _read_hft_config_from_json(config_path)

        # 验证配置
        validated_config = _validate_hft_config(hft_config)

        logger.info(f"同步获取高频交易策略配置成功")
        return validated_config

    except Exception as e:
        logger.error(f"同步获取高频交易配置失败: {e}，使用默认配置")
        return DEFAULT_HFT_CONFIG.copy()


def is_hft_enabled() -> bool:
    """
    检查高频交易策略是否启用

    Returns:
        bool: 如果启用返回 True，否则返回 False

    Example:
        >>> if is_hft_enabled():
        ...     print("高频交易策略已启用")
    """
    config = get_hft_config_sync()
    return config.get('enabled', False)


def get_hft_mode() -> str:
    """
    获取高频交易运行模式

    Returns:
        str: 运行模式字符串

    Example:
        >>> mode = get_hft_mode()
        >>> print(f"当前运行模式: {mode}")
    """
    config = get_hft_config_sync()
    return config.get('mode', 'hybrid')
