"""
Athena OS 主入口 (Main Entry)

系统启动入口，负责：
- 配置日志
- 加载环境变量
- 配置系统
- 初始化引擎
- 启动系统
- 优雅退出
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except ImportError:
    print("警告: python-dotenv 未安装，跳过环境变量加载")
    load_dotenv = lambda: None

from src.utils.logger import setup_logging, get_logger
from src.core.engine import Engine, create_default_config
from src.core.event_types import EventType

logger = get_logger(__name__)


def load_config_from_env() -> dict:
    """
    从环境变量加载配置

    Returns:
        dict: 配置字典
    """
    config = create_default_config()

    # 🔍 调试：打印关键环境变量
    logger.info("=" * 60)
    logger.info("🔍 环境变量检查")
    logger.info("=" * 60)
    logger.info(f"ACTIVE_STRATEGY: {os.getenv('ACTIVE_STRATEGY', 'NOT SET')}")
    logger.info(f"SCALPER_SYMBOL: {os.getenv('SCALPER_SYMBOL', 'NOT SET')}")
    logger.info(f"SCALPER_CAPITAL: {os.getenv('SCALPER_CAPITAL', 'NOT SET')}")
    logger.info(f"TOTAL_CAPITAL: {os.getenv('TOTAL_CAPITAL', 'NOT SET')}")
    logger.info("=" * 60)

    # 资金配置
    total_capital = os.getenv('TOTAL_CAPITAL')
    if total_capital:
        config['total_capital'] = float(total_capital)

    # REST Gateway 配置
    rest_config = config.get('rest_gateway', {})

    api_key = os.getenv('OKX_API_KEY')
    if api_key:
        rest_config['api_key'] = api_key

    secret_key = os.getenv('OKX_SECRET_KEY')
    if secret_key:
        rest_config['secret_key'] = secret_key

    passphrase = os.getenv('OKX_PASSPHRASE')
    if passphrase:
        rest_config['passphrase'] = passphrase

    use_demo = os.getenv('USE_DEMO')
    if use_demo is not None:
        rest_config['use_demo'] = use_demo.lower() == 'true'

    config['rest_gateway'] = rest_config

    # Public WebSocket 配置
    public_ws_config = config.get('public_ws', {})

    # 🔧 修复"精神分裂"问题：统一使用策略的交易对
    # 优先使用 SCALPER_SYMBOL（策略配置），如果不存在则使用 TRADING_SYMBOL（网关配置）
    # 确保网关和策略使用相同的交易对，避免配置不一致
    symbol = os.getenv('SCALPER_SYMBOL') or os.getenv('TRADING_SYMBOL')
    if symbol:
        public_ws_config['symbol'] = symbol
        logger.info(f"✅ 网关交易对已设置: {symbol} (来源: SCALPER_SYMBOL)")
    else:
        # 如果都没有设置，使用默认值
        default_symbol = 'BTC-USDT-SWAP'
        public_ws_config['symbol'] = default_symbol
        logger.warning(f"⚠️  未设置交易对环境变量，使用默认值: {default_symbol}")

    config['public_ws'] = public_ws_config

    # Private WebSocket 配置
    private_ws_config = config.get('private_ws', {})
    private_ws_config['use_demo'] = rest_config.get('use_demo', True)
    config['private_ws'] = private_ws_config

    # 风控配置
    risk_config = config.get('risk', {})

    # 获取总资金（用于自适应计算）
    total_capital = config.get('total_capital', 10000.0)

    # 自适应计算 MAX_ORDER_AMOUNT
    env_max_amount = os.getenv("MAX_ORDER_AMOUNT")

    if env_max_amount:
        max_order_amount = float(env_max_amount)
        logger.info(f"🛡️ 使用环境变量风控限制: {max_order_amount} USDT")
    else:
        # 自适应计算：允许最大单笔下单为总资金的 500% (对应 5x 杠杆)
        # 这样 10000 U 本金会自动拥有 50000 U 的单笔限额，既安全又灵活
        max_order_amount = total_capital * 5.0
        logger.info(f"🛡️ 自动计算风控限制 (自适应): {max_order_amount} USDT (基于资金 5x)")

    risk_config['max_order_amount'] = max_order_amount

    # 🔧 支持配置单笔风险比例（Lower Risk %）
    # 默认 1%，可通过环境变量 RISK_PER_TRADE_PCT 覆盖
    risk_per_trade_pct = float(os.getenv("RISK_PER_TRADE_PCT", "0.01"))
    logger.info(f"🛡️ 单笔风险比例: {risk_per_trade_pct*100:.2f}% (每笔交易风险不超过总资金)")

    # 将风险比例添加到风控配置（后续传递给 RiskConfig）
    risk_config['RISK_PER_TRADE_PCT'] = risk_per_trade_pct

    max_frequency = os.getenv('MAX_FREQUENCY')
    if max_frequency:
        risk_config['max_frequency'] = int(max_frequency)

    config['risk'] = risk_config

    # 策略配置
    # 清空默认策略列表，只根据 ACTIVE_STRATEGY 加载指定策略
    strategies_config = []

    # 检查激活的策略类型
    active_strategy = os.getenv('ACTIVE_STRATEGY', 'sniper').lower()

    # 根据激活的策略类型加载配置
    if active_strategy == 'sniper':
        enable_sniper = os.getenv('ENABLE_SNIPER', 'true').lower() == 'true'

        if enable_sniper:
            sniper_config = {
                'id': 'sniper',
                'type': 'sniper',
                'capital': float(os.getenv('SNIPER_CAPITAL', 2000.0)),
                'params': {
                    'symbol': os.getenv('TRADING_SYMBOL', 'BTC-USDT-SWAP'),
                    'position_size': float(os.getenv('SNIPER_POSITION_SIZE', 0.1)),
                    'cooldown_seconds': float(os.getenv('SNIPER_COOLDOWN', 5.0)),
                    'order_type': os.getenv('SNIPER_ORDER_TYPE', 'market'),
                    'min_big_order_usdt': float(os.getenv('SNIPER_MIN_BIG_ORDER', 5000.0))
                }
            }

            # 更新或追加策略配置
            existing = False
            for i, s in enumerate(strategies_config):
                if s.get('type') == 'sniper':
                    strategies_config[i] = sniper_config
                    existing = True
                    break

            if not existing:
                strategies_config.append(sniper_config)

    elif active_strategy == 'scalper_v1':
        enable_scalper = os.getenv('ENABLE_SCALPER_V1', 'true').lower() == 'true'

        if enable_scalper:
            # 🔧 修复仓位传递逻辑：只在显式设置时才传递固定仓位
            # 未设置时为 None，让策略自动基于风险计算
            position_size_env = os.getenv('SCALPER_POSITION_SIZE')
            position_size_value = float(position_size_env) if position_size_env else None

            scalper_config = {
                'id': 'scalper_v1',
                'type': 'scalper_v1',
                'capital': float(os.getenv('SCALPER_CAPITAL', 10000.0)),
                'params': {
                    'symbol': os.getenv('SCALPER_SYMBOL', 'DOGE-USDT-SWAP'),
                    'imbalance_ratio': float(os.getenv('SCALPER_IMBALANCE_RATIO', 5.0)),  # V2: 5.0
                    'min_flow_usdt': float(os.getenv('SCALPER_MIN_FLOW', 5000.0)),  # V2: 5000
                    'take_profit_pct': float(os.getenv('SCALPER_TAKE_PROFIT_PCT', 0.002)),
                    'stop_loss_pct': float(os.getenv('SCALPER_STOP_LOSS_PCT', 0.01)),
                    'time_limit_seconds': int(os.getenv('SCALPER_TIME_LIMIT_SECONDS', 30)),  # V2: 30s
                    'cooldown_seconds': float(os.getenv('SCALPER_COOLDOWN', 0.1)),  # V2: HFT mode
                    'position_size': position_size_value,  # 只在显式设置时才传值
                    # ✨ V2 新增参数（有默认值，可通过环境变量覆盖）
                    'trailing_stop_activation_pct': float(os.getenv('SCALPER_TRAILING_STOP_ACTIVATION_PCT', 0.001)),  # 0.1%
                    'trailing_stop_callback_pct': float(os.getenv('SCALPER_TRAILING_STOP_CALLBACK_PCT', 0.0005)),  # 0.05%
                    'ema_period': int(os.getenv('SCALPER_EMA_PERIOD', 50)),  # 50 ticks
                    'spread_threshold_pct': float(os.getenv('SCALPER_SPREAD_THRESHOLD_PCT', 0.0005)),  # 0.05%
                    # 🔥 [修复] 插队和追单配置
                    'enable_chasing': os.getenv('SCALPER_ENABLE_CHASING', 'true').lower() == 'true',  # 是否启用追单
                    'tick_size': float(os.getenv('SCALPER_TICK_SIZE', 0.01)),  # 最小价格跳动
                    'max_chase_distance_pct': float(os.getenv('SCALPER_MAX_CHASE_DISTANCE', 0.001))  # 最大追单距离 0.1%
                }
            }

            # [新增] 打印 ScalperV1 V2 配置，验证环境变量透传
            params_dict = scalper_config.get('params', {})
            logger.info(
                f"🔧 ScalperV1 V2 Config Loaded: "
                f"symbol={params_dict.get('symbol', 'N/A')}, "
                f"min_flow={params_dict.get('min_flow_usdt', 'N/A')}, "
                f"ratio={params_dict.get('imbalance_ratio', 'N/A')}, "
                f"time_limit={params_dict.get('time_limit_seconds', 'N/A')}s, "
                f"cooldown={params_dict.get('cooldown_seconds', 'N/A')}s, "
                f"trailing_stop={params_dict.get('trailing_stop_activation_pct', 'N/A')}%"
            )

            # 更新或追加策略配置
            existing = False
            for i, s in enumerate(strategies_config):
                if s.get('type') == 'scalper_v1':
                    strategies_config[i] = scalper_config
                    existing = True
                    break

            if not existing:
                strategies_config.append(scalper_config)

    config['strategies'] = strategies_config

    return config


def print_config(config: dict):
    """
    打印配置信息

    Args:
        config (dict): 配置字典
    """
    logger.info("=" * 60)
    logger.info("Athena OS v3.0 配置")
    logger.info("=" * 60)

    logger.info(f"总资金: {config.get('total_capital', 0):.2f} USDT")
    logger.info(f"交易对: {config.get('public_ws', {}).get('symbol', 'N/A')}")
    logger.info(f"模拟模式: {config.get('rest_gateway', {}).get('use_demo', True)}")

    risk = config.get('risk', {})
    logger.info(f"风控 - 最大单笔订单: {risk.get('max_order_amount', 0):.2f} USDT")
    logger.info(f"风控 - 最大频率: {risk.get('max_frequency', 0)} 单/1s")

    strategies = config.get('strategies', [])
    logger.info(f"已启用策略 ({len(strategies)} 个):")
    for s in strategies:
        logger.info(f"  - {s.get('id', 'N/A')} ({s.get('type', 'N/A')})")
        logger.info(f"    资金: {s.get('capital', 0):.2f} USDT")
        params = s.get('params', {})
        logger.info(f"    配置: {params}")

    logger.info("=" * 60)


async def main():
    """
    主函数

    1. 配置日志
    2. 加载环境变量
    3. 加载配置
    4. 初始化引擎
    5. 启动系统
    """
    # 1. 配置日志（必须最先执行）
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    setup_logging(log_level)

    # 存活确认（在日志系统初始化之前）
    print("🔥 系统正在启动...")
    logger.info("🚀 Athena OS v3.0 启动中...")

    # 2. 加载环境变量
    env_file = PROJECT_ROOT / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f"已加载环境变量: {env_file}")
    else:
        logger.warning(f"未找到 .env 文件: {env_file}，使用默认配置")

    # 3. 加载配置
    config = load_config_from_env()
    print_config(config)

    # 4. 创建并运行引擎
    engine = Engine(config)

    try:
        await engine.run()

    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C，准备退出...")
        await engine.stop()

    except Exception as e:
        logger.error(f"系统异常: {e}", exc_info=True)
        await engine.stop()
        sys.exit(1)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Athena OS 已停止")
        sys.exit(0)
