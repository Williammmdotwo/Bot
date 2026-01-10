"""
高频交易策略配置加载器

提供配置管理功能，遵循以下原则：
- 不引入 ccxt 或 pandas
- 提供异步配置加载
- 支持从环境变量读取配置（优先级最高）
- 支持从 JSON 配置文件读取（次优先级）
- 使用默认配置作为兜底

配置加载优先级：
1. 环境变量（最高优先级）
2. JSON 配置文件（次优先级）
3. 默认配置（最低优先级）
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
    # 动态资金管理配置
    "symbol": "BTC-USDT-SWAP",
    "order_size": 1,
    "ema_fast_period": 9,
    "ema_slow_period": 21,
    "ioc_slippage_pct": 0.002,
    "sniper_flow_window": 3.0,
    "sniper_min_trades": 20,
    "sniper_min_net_volume": 10000.0,
    "risk_ratio": 0.2,  # 风险比例：使用 20% 的余额
    "leverage": 10,  # 杠杆倍数
    "whale_threshold": 5000.0,  # 大单阈值（USDT）
    "strategy_mode": "PRODUCTION",  # 策略模式：PRODUCTION 或 DEV
    "cooldown_period": 60.0,  # 风控冷却期（秒）
    "max_loss_pct": 0.03  # 风控最大亏损比例（3%）
}


# 环境变量映射
ENV_VAR_MAPPING = {
    "HFT_ENABLED": ("enabled", bool),
    "HFT_SYMBOL": ("symbol", str),
    "HFT_MODE": ("mode", str),
    "HFT_ORDER_SIZE": ("order_size", int),
    "HFT_EMA_FAST_PERIOD": ("ema_fast_period", int),
    "HFT_EMA_SLOW_PERIOD": ("ema_slow_period", int),
    "HFT_IOC_SLIPPAGE_PCT": ("ioc_slippage_pct", float),
    "HFT_SNIPER_FLOW_WINDOW": ("sniper_flow_window", float),
    "HFT_SNIPER_MIN_TRADES": ("sniper_min_trades", int),
    "HFT_SNIPER_MIN_NET_VOLUME": ("sniper_min_net_volume", float),
    "HFT_RISK_RATIO": ("risk_ratio", float),
    "HFT_LEVERAGE": ("leverage", int),
    "HFT_WHALE_THRESHOLD": ("whale_threshold", float),
    "HFT_MEMORY_LIMIT_MB": ("memory_limit_mb", int),
    "STRATEGY_MODE": ("strategy_mode", str),
    "HFT_COOLDOWN_PERIOD": ("cooldown_period", float),
    "HFT_MAX_LOSS_PCT": ("max_loss_pct", float)
}


async def load_hft_config() -> Dict[str, Any]:
    """
    异步加载高频交易策略配置

    配置加载优先级：
    1. 环境变量（最高优先级）
    2. JSON 配置文件（次优先级）
    3. 默认配置（最低优先级）

    Returns:
        Dict[str, Any]: 高频交易配置字典，包含以下字段：
            - enabled (bool): 是否启用高频交易策略
            - mode (str): 运行模式（如 "hybrid"）
            - memory_limit_mb (int): 内存限制（MB）
            - tick_channels (List[str]): Tick数据通道列表
            - symbol (str): 交易对（如 "BTC-USDT-SWAP"）
            - order_size (int): 订单数量（张数）
            - ema_fast_period (int): 快速 EMA 周期
            - ema_slow_period (int): 慢速 EMA 周期
            - ioc_slippage_pct (float): IOC 订单滑点百分比
            - sniper_flow_window (float): 狙击模式流量分析窗口
            - sniper_min_trades (int): 狙击模式最小交易笔数
            - sniper_min_net_volume (float): 狙击模式最小净流量
            - risk_ratio (float): 风险比例
            - leverage (int): 杠杆倍数
            - whale_threshold (float): 大单阈值（USDT）
            - strategy_mode (str): 策略模式（PRODUCTION 或 DEV）
            - cooldown_period (float): 风控冷却期（秒）
            - max_loss_pct (float): 风控最大亏损比例

    Example:
        >>> config = await load_hft_config()
        >>> print(config['enabled'])
        True
        >>> print(config['mode'])
        'hybrid'
    """
    try:
        # 1. 优先从环境变量读取
        env_config = _load_config_from_env()
        logger.info(f"从环境变量加载配置: {len(env_config)} 个参数")

        # 2. 如果环境变量不足，尝试从 JSON 配置文件读取
        if len(env_config) < 5:  # 如果环境变量参数少于 5 个，尝试读取 JSON
            try:
                config_path = _get_config_file_path()
                json_config = _read_hft_config_from_json(config_path)
                logger.info(f"从 JSON 配置文件加载配置: {len(json_config)} 个参数")
                # 合并配置：JSON 配置覆盖环境变量
                env_config.update(json_config)
            except Exception as e:
                logger.warning(f"JSON 配置文件读取失败: {e}，仅使用环境变量")

        # 3. 使用默认配置补充缺失的参数
        validated_config = DEFAULT_HFT_CONFIG.copy()
        validated_config.update(env_config)

        # 4. 验证配置
        validated_config = _validate_hft_config(validated_config)

        logger.info(f"高频交易策略配置加载成功")
        logger.debug(f"配置详情: {validated_config}")
        return validated_config

    except Exception as e:
        logger.error(f"加载高频交易配置失败: {e}，使用默认配置")
        return DEFAULT_HFT_CONFIG.copy()


def _load_config_from_env() -> Dict[str, Any]:
    """
    从环境变量加载配置

    Returns:
        Dict[str, Any]: 从环境变量读取的配置字典

    Example:
        >>> config = _load_config_from_env()
        >>> print(config)
        {'enabled': True, 'symbol': 'BTC-USDT-SWAP'}
    """
    config = {}

    for env_var, (config_key, config_type) in ENV_VAR_MAPPING.items():
        env_value = os.getenv(env_var)

        if env_value is not None:
            try:
                # 类型转换
                if config_type == bool:
                    config_value = env_value.lower() in ('true', '1', 'yes')
                elif config_type == int:
                    config_value = int(env_value)
                elif config_type == float:
                    config_value = float(env_value)
                else:
                    config_value = env_value

                config[config_key] = config_value
                logger.debug(f"环境变量 {env_var}={env_value} -> {config_key}={config_value}")

            except (ValueError, TypeError) as e:
                logger.warning(f"环境变量 {env_var}={env_value} 转换失败: {e}，使用默认值")

    return config


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
    # 验证并设置默认值
    validated = DEFAULT_HFT_CONFIG.copy()
    validated.update(config)

    # 类型验证
    if not isinstance(validated['enabled'], bool):
        raise ValueError("'enabled' 字段必须是布尔类型")

    if not isinstance(validated['mode'], str):
        raise ValueError("'mode' 字段必须是字符串类型")

    if not isinstance(validated['memory_limit_mb'], int) or validated['memory_limit_mb'] <= 0:
        raise ValueError("'memory_limit_mb' 必须是正整数")

    if not isinstance(validated['tick_channels'], list):
        raise ValueError("'tick_channels' 必须是列表类型")

    if not isinstance(validated['symbol'], str):
        raise ValueError("'symbol' 字段必须是字符串类型")

    if not isinstance(validated['order_size'], int) or validated['order_size'] <= 0:
        raise ValueError("'order_size' 必须是正整数")

    if not isinstance(validated['ema_fast_period'], int) or validated['ema_fast_period'] <= 0:
        raise ValueError("'ema_fast_period' 必须是正整数")

    if not isinstance(validated['ema_slow_period'], int) or validated['ema_slow_period'] <= 0:
        raise ValueError("'ema_slow_period' 必须是正整数")

    if not isinstance(validated['ioc_slippage_pct'], (int, float)) or validated['ioc_slippage_pct'] <= 0:
        raise ValueError("'ioc_slippage_pct' 必须是正数")

    if not isinstance(validated['risk_ratio'], (int, float)) or not (0 < validated['risk_ratio'] <= 1):
        raise ValueError("'risk_ratio' 必须是 0 到 1 之间的数")

    if not isinstance(validated['leverage'], int) or validated['leverage'] <= 0:
        raise ValueError("'leverage' 必须是正整数")

    if not isinstance(validated['whale_threshold'], (int, float)) or validated['whale_threshold'] <= 0:
        raise ValueError("'whale_threshold' 必须是正数")

    if not isinstance(validated['strategy_mode'], str):
        raise ValueError("'strategy_mode' 必须是字符串类型")

    if not isinstance(validated['cooldown_period'], (int, float)) or validated['cooldown_period'] <= 0:
        raise ValueError("'cooldown_period' 必须是正数")

    if not isinstance(validated['max_loss_pct'], (int, float)) or not (0 < validated['max_loss_pct'] <= 1):
        raise ValueError("'max_loss_pct' 必须是 0 到 1 之间的数")

    # 值验证
    valid_modes = ['hybrid', 'vulture', 'sniper']
    if validated['mode'] not in valid_modes:
        logger.warning(f"未知的运行模式 '{validated['mode']}'，有效模式: {valid_modes}，使用默认值")

    valid_strategy_modes = ['PRODUCTION', 'DEV']
    if validated['strategy_mode'] not in valid_strategy_modes:
        logger.warning(f"未知的策略模式 '{validated['strategy_mode']}'，有效模式: {valid_strategy_modes}，使用默认值")

    if validated['ema_fast_period'] >= validated['ema_slow_period']:
        logger.warning(f"EMA 快周期 ({validated['ema_fast_period']}) 大于等于慢周期 ({validated['ema_slow_period']})，建议调整")

    if validated['memory_limit_mb'] > 4096:
        logger.warning(f"内存限制 {validated['memory_limit_mb']}MB 过高，可能影响系统性能")

    if validated['risk_ratio'] > 0.5:
        logger.warning(f"风险比例 {validated['risk_ratio']} 过高（>50%），建议降低到 20% 或以下")

    if validated['leverage'] > 50:
        logger.warning(f"杠杆倍数 {validated['leverage']} 过高（>50x），建议降低到 20x 或以下")

    if not validated['tick_channels']:
        logger.warning("'tick_channels' 为空，将无法接收市场数据")

    logger.debug(f"配置验证通过")
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
