"""
StrategyConfig - 统一策略配置管理

职责：
- 定义所有策略的配置类
- 支持从环境变量加载配置
- 提供配置验证
- 支持配置导出和导入

设计原则：
- 配置即代码：使用 dataclass 定义
- 类型安全：使用类型注解
- 灵活加载：支持环境变量、代码直接赋值
- 易于测试：可独立实例化
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import os
import json
import logging

logger = logging.getLogger(__name__)


# ========== 基础配置类 ==========

@dataclass
class BaseStrategyConfig:
    """策略基础配置（抽象基类）"""
    symbol: str
    capital: float
    leverage: float = 5.0
    mode: str = "production"  # production, paper, backtest

    @classmethod
    def from_env(cls, prefix: str):
        """从环境变量加载配置"""
        raise NotImplementedError

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典（用于日志和持久化）"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, (int, float, str, bool, type(None))):
                result[key] = value
            elif isinstance(value, Dict):
                result[key] = value
            else:
                # 对于复杂对象，尝试转换为字典
                try:
                    result[key] = value.to_dict() if hasattr(value, 'to_dict') else str(value)
                except Exception:
                    result[key] = str(value)
        return result

    def validate(self) -> bool:
        """配置验证"""
        raise NotImplementedError


# ========== ScalperV2 配置类 ==========

@dataclass
class ScalperPositionSizingConfig:
    """ScalperV2 仓位管理配置"""
    base_equity_ratio: float = 0.02
    max_leverage: float = 5.0
    min_order_value: float = 10.0
    signal_scaling_enabled: bool = True
    signal_threshold_normal: float = 5.0
    signal_threshold_aggressive: float = 10.0
    signal_aggressive_multiplier: float = 1.5
    liquidity_protection_enabled: bool = True
    liquidity_depth_ratio: float = 0.20
    liquidity_depth_levels: int = 3
    volatility_protection_enabled: bool = True
    volatility_ema_period: int = 20
    volatility_threshold: float = 0.001


@dataclass
class ScalperExecutionAlgoConfig:
    """ScalperV2 执行算法配置"""
    enable_chasing: bool = True
    min_chasing_distance_pct: float = 0.0005
    max_chase_distance_pct: float = 0.001
    min_order_life_seconds: float = 2.0
    aggressive_maker_spread_ticks: float = 2.0
    aggressive_maker_price_offset: float = 1.0
    max_slippage_pct: float = 0.001
    compute_throttle_ms: int = 50
    anti_flipping_threshold: float = 10.0
    enable_depth_protection: bool = True


@dataclass
class ScalperSignalGeneratorConfig:
    """ScalperV2 信号生成器配置"""
    ema_period: int = 50
    spread_threshold_pct: float = 0.0005


@dataclass
class ScalperConfig(BaseStrategyConfig):
    """ScalperV2 完整配置"""

    # 信号配置
    imbalance_ratio: float = 5.0
    min_flow_usdt: float = 5000.0

    # 风险配置
    take_profit_pct: float = 0.002
    stop_loss_pct: float = 0.01
    time_limit_seconds: int = 30
    cooldown_seconds: float = 0.1
    maker_timeout_seconds: float = 3.0

    # 深度过滤
    depth_filter_enabled: bool = True
    depth_ratio_low: float = 0.8
    depth_ratio_high: float = 1.25
    depth_check_levels: int = 3

    # 交易方向
    trade_direction: str = 'both'  # both, long_only, short_only

    # EMA 过滤
    ema_filter_mode: str = 'loose'  # strict, loose, off
    ema_boost_pct: float = 0.20

    # 子配置
    position_sizing: ScalperPositionSizingConfig = field(default_factory=ScalperPositionSizingConfig)
    execution_algo: ScalperExecutionAlgoConfig = field(default_factory=ScalperExecutionAlgoConfig)
    signal_generator: ScalperSignalGeneratorConfig = field(default_factory=ScalperSignalGeneratorConfig)

    @classmethod
    def from_env(cls, prefix: str = "SCALPER"):
        """
        从环境变量加载配置

        Args:
            prefix: 环境变量前缀（默认 "SCALPER"）

        Returns:
            ScalperConfig: 配置对象
        """
        def _get_float(key: str, default: float) -> float:
            return float(os.getenv(f"{prefix}_{key}", str(default)))

        def _get_int(key: str, default: int) -> int:
            return int(os.getenv(f"{prefix}_{key}", str(default)))

        def _get_bool(key: str, default: bool) -> bool:
            return os.getenv(f"{prefix}_{key}", str(default)).lower() in ('true', '1', 'yes')

        def _get_str(key: str, default: str) -> str:
            return os.getenv(f"{prefix}_{key}", default)

        # 基础配置
        config = cls(
            symbol=_get_str("SYMBOL", "DOGE-USDT-SWAP"),
            capital=_get_float("CAPITAL", "10000"),
            leverage=_get_float("LEVERAGE", "5.0"),
            mode=_get_str("MODE", "production"),

            # 信号配置
            imbalance_ratio=_get_float("IMBALANCE_RATIO", "5.0"),
            min_flow_usdt=_get_float("MIN_FLOW_USDT", "5000"),

            # 风险配置
            take_profit_pct=_get_float("TAKE_PROFIT_PCT", "0.002"),
            stop_loss_pct=_get_float("STOP_LOSS_PCT", "0.01"),
            time_limit_seconds=_get_int("TIME_LIMIT_SECONDS", "30"),
            cooldown_seconds=_get_float("COOLDOWN_SECONDS", "0.1"),
            maker_timeout_seconds=_get_float("MAKER_TIMEOUT_SECONDS", "3.0"),

            # 深度过滤
            depth_filter_enabled=_get_bool("DEPTH_FILTER_ENABLED", "true"),
            depth_ratio_low=_get_float("DEPTH_RATIO_LOW", "0.8"),
            depth_ratio_high=_get_float("DEPTH_RATIO_HIGH", "1.25"),
            depth_check_levels=_get_int("DEPTH_CHECK_LEVELS", "3"),

            # 交易方向
            trade_direction=_get_str("TRADE_DIRECTION", "both"),

            # EMA 过滤
            ema_filter_mode=_get_str("EMA_FILTER_MODE", "loose"),
            ema_boost_pct=_get_float("EMA_BOOST_PCT", "0.20"),

            # 子配置
            position_sizing=ScalperPositionSizingConfig(
                base_equity_ratio=_get_float("POSITION_SIZING_BASE_EQUITY_RATIO", "0.02"),
                max_leverage=_get_float("POSITION_SIZING_MAX_LEVERAGE", "5.0"),
                min_order_value=_get_float("POSITION_SIZING_MIN_ORDER_VALUE", "10.0"),
                signal_scaling_enabled=_get_bool("POSITION_SIZING_SIGNAL_SCALING_ENABLED", "true"),
                signal_threshold_normal=_get_float("POSITION_SIZING_SIGNAL_THRESHOLD_NORMAL", "5.0"),
                signal_threshold_aggressive=_get_float("POSITION_SIZING_SIGNAL_THRESHOLD_AGGRESSIVE", "10.0"),
                signal_aggressive_multiplier=_get_float("POSITION_SIZING_AGGRESSIVE_MULTIPLIER", "1.5"),
                liquidity_protection_enabled=_get_bool("POSITION_SIZING_LIQUIDITY_PROTECTION_ENABLED", "true"),
                liquidity_depth_ratio=_get_float("POSITION_SIZING_LIQUIDITY_DEPTH_RATIO", "0.20"),
                liquidity_depth_levels=_get_int("POSITION_SIZING_LIQUIDITY_DEPTH_LEVELS", "3"),
                volatility_protection_enabled=_get_bool("POSITION_SIZING_VOLATILITY_PROTECTION_ENABLED", "true"),
                volatility_ema_period=_get_int("POSITION_SIZING_VOLATILITY_EMA_PERIOD", "20"),
                volatility_threshold=_get_float("POSITION_SIZING_VOLATILITY_THRESHOLD", "0.001"),
            ),
            execution_algo=ScalperExecutionAlgoConfig(
                enable_chasing=_get_bool("EXECUTION_ALGO_ENABLE_CHASING", "true"),
                min_chasing_distance_pct=_get_float("EXECUTION_ALGO_MIN_CHASING_DISTANCE_PCT", "0.0005"),
                max_chase_distance_pct=_get_float("EXECUTION_ALGO_MAX_CHASE_DISTANCE_PCT", "0.001"),
                min_order_life_seconds=_get_float("EXECUTION_ALGO_MIN_ORDER_LIFE_SECONDS", "2.0"),
                aggressive_maker_spread_ticks=_get_float("EXECUTION_ALGO_AGGRESSIVE_MAKER_SPREAD_TICKS", "2.0"),
                aggressive_maker_price_offset=_get_float("EXECUTION_ALGO_AGGRESSIVE_MAKER_PRICE_OFFSET", "1.0"),
                max_slippage_pct=_get_float("EXECUTION_ALGO_MAX_SLIPPAGE_PCT", "0.001"),
                compute_throttle_ms=_get_int("EXECUTION_ALGO_COMPUTE_THROTTLE_MS", "50"),
                anti_flipping_threshold=_get_float("EXECUTION_ALGO_ANTI_FLIPPING_THRESHOLD", "10.0"),
                enable_depth_protection=_get_bool("EXECUTION_ALGO_ENABLE_DEPTH_PROTECTION", "true"),
            ),
            signal_generator=ScalperSignalGeneratorConfig(
                ema_period=_get_int("SIGNAL_GENERATOR_EMA_PERIOD", "50"),
                spread_threshold_pct=_get_float("SIGNAL_GENERATOR_SPREAD_THRESHOLD_PCT", "0.0005"),
            )
        )

        logger.info(f"✅ 配置从环境变量加载成功: {prefix}")
        return config

    def validate(self) -> bool:
        """
        配置验证

        Returns:
            bool: 验证是否通过

        Raises:
            AssertionError: 配置验证失败
        """
        # 基础配置验证
        assert self.capital > 0, "资金必须大于 0"
        assert 1.0 <= self.leverage <= 125.0, "杠杆必须在 1-125 之间"
        assert self.mode in ['production', 'paper', 'backtest'], "模式必须是 production, paper 或 backtest"

        # 信号配置验证
        assert self.imbalance_ratio > 1.0, "失衡比率必须 > 1"
        assert self.min_flow_usdt > 0, "最小流量必须 > 0"

        # 风险配置验证
        assert 0 < self.take_profit_pct < 1.0, "止盈比例必须在 0-1 之间"
        assert 0 < self.stop_loss_pct < 1.0, "止损比例必须在 0-1 之间"
        assert self.time_limit_seconds > 0, "时间限制必须 > 0"
        assert self.cooldown_seconds >= 0, "冷却时间必须 >= 0"

        # 深度过滤验证
        assert 0 < self.depth_ratio_low < 1.0, "深度比率下限必须在 0-1 之间"
        assert self.depth_ratio_high > 1.0, "深度比率上限必须 > 1"

        # 交易方向验证
        assert self.trade_direction in ['both', 'long_only', 'short_only'], "交易方向必须是 both, long_only 或 short_only"

        # EMA 过滤验证
        assert self.ema_filter_mode in ['strict', 'loose', 'off'], "EMA 过滤模式必须是 strict, loose 或 off"
        assert 0 <= self.ema_boost_pct <= 1.0, "EMA 加权比例必须在 0-1 之间"

        logger.info("✅ ScalperV2 配置验证通过")
        return True

    def to_json_file(self, file_path: str):
        """
        导出配置到 JSON 文件

        Args:
            file_path: 文件路径
        """
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"✅ 配置已导出到: {file_path}")

    @classmethod
    def from_json_file(cls, file_path: str):
        """
        从 JSON 文件加载配置

        Args:
            file_path: 文件路径

        Returns:
            ScalperConfig: 配置对象
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 提取策略参数
        strategy_params = data.get('strategy_params', {})

        config = cls(
            symbol=data.get('symbol', 'DOGE-USDT-SWAP'),
            capital=float(strategy_params.get('imbalance_ratio', 5.0) * 1000),  # 估算
            leverage=float(strategy_params.get('imbalance_ratio', 5.0)),
            mode=data.get('mode', 'PRODUCTION').lower(),

            # 信号配置
            imbalance_ratio=float(strategy_params.get('imbalance_ratio', 5.0)),
            min_flow_usdt=float(strategy_params.get('min_flow_usdt', 5000.0)),

            # 风险配置
            take_profit_pct=float(strategy_params.get('take_profit_pct', 0.002)),
            stop_loss_pct=float(strategy_params.get('stop_loss_pct', 0.01)),
            time_limit_seconds=int(strategy_params.get('time_limit_seconds', 30)),
            cooldown_seconds=float(strategy_params.get('cooldown_seconds', 0.1)),
            maker_timeout_seconds=float(strategy_params.get('maker_timeout_seconds', 3.0)),

            # 子配置
            position_sizing=ScalperPositionSizingConfig(**data.get('position_sizing', {})),
            execution_algo=ScalperExecutionAlgoConfig(**data.get('execution_algo', {})),
            signal_generator=ScalperSignalGeneratorConfig(**data.get('signal_generator', {}))
        )

        logger.info(f"✅ 配置从 JSON 文件加载成功: {file_path}")
        return config
