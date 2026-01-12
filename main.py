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

    symbol = os.getenv('TRADING_SYMBOL')
    if symbol:
        public_ws_config['symbol'] = symbol

    config['public_ws'] = public_ws_config

    # Private WebSocket 配置
    private_ws_config = config.get('private_ws', {})
    private_ws_config['use_demo'] = rest_config.get('use_demo', True)
    config['private_ws'] = private_ws_config

    # 风控配置
    risk_config = config.get('risk', {})

    max_order_amount = os.getenv('MAX_ORDER_AMOUNT')
    if max_order_amount:
        risk_config['max_order_amount'] = float(max_order_amount)

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
            scalper_config = {
                'id': 'scalper_v1',
                'type': 'scalper_v1',
                'capital': float(os.getenv('SCALPER_CAPITAL', 100.0)),
                'params': {
                    'symbol': os.getenv('SCALPER_SYMBOL', 'BTC-USDT-SWAP'),
                    'imbalance_ratio': float(os.getenv('SCALPER_IMBALANCE_RATIO', 3.0)),
                    'min_flow_usdt': float(os.getenv('SCALPER_MIN_FLOW', 1000.0)),
                    'take_profit_pct': float(os.getenv('SCALPER_TAKE_PROFIT_PCT', 0.002)),
                    'stop_loss_pct': float(os.getenv('SCALPER_STOP_LOSS_PCT', 0.01)),
                    'time_limit_seconds': int(os.getenv('SCALPER_TIME_LIMIT_SECONDS', 5)),
                    'position_size': float(os.getenv('SCALPER_POSITION_SIZE', 0.1)) if os.getenv('SCALPER_POSITION_SIZE') else None
                }
            }

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
