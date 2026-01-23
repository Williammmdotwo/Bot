#!/usr/bin/env python3
"""
Athena OS 模拟运行脚本 (Simulation Runner)

用于在 OKX Demo Trading 环境中进行 24-48 小时长期运行的模拟测试。

功能：
- 强制连接到模拟盘（Demo Trading）
- 日志轮转（100MB/文件，保留 10 个备份）
- 健康监控（每分钟打印心跳和系统状态）
- 内存和连接状态监控

使用方法：
    python scripts/run_simulation.py
"""

import asyncio
import sys
import os
import psutil
import time
from pathlib import Path
from typing import Optional

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except ImportError:
    print("错误: 需要安装 python-dotenv")
    print("运行: pip install python-dotenv")
    sys.exit(1)

from src.utils.logger import setup_logging, get_logger
from src.core.engine import Engine, create_default_config
from src.core.event_types import EventType

logger = get_logger(__name__)


class HealthMonitor:
    """健康监控器 - 定期检查系统状态"""

    def __init__(self, engine: Engine, check_interval: int = 60):
        """
        初始化健康监控器

        Args:
            engine (Engine): 引擎实例
            check_interval (int): 检查间隔（秒），默认 60 秒
        """
        self.engine = engine
        self.check_interval = check_interval
        self.running = False
        self.task = None

    async def start(self):
        """启动健康监控"""
        self.running = True
        self.task = asyncio.create_task(self._monitor_loop())
        logger.info(f"🩺 健康监控已启动 (检查间隔: {self.check_interval}s)")

    async def stop(self):
        """停止健康监控"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("🩺 健康监控已停止")

    async def _monitor_loop(self):
        """监控循环"""
        while self.running:
            await self._print_health_status()
            await asyncio.sleep(self.check_interval)

    async def _print_health_status(self):
        """打印健康状态"""
        try:
            # 获取系统资源使用情况
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_gb = memory.used / (1024 ** 3)
            memory_total_gb = memory.total / (1024 ** 3)

            # 获取 WebSocket 连接状态
            ws_status = self._get_ws_status()

            # 获取引擎运行时间
            uptime = time.time() - self.engine.start_time if hasattr(self.engine, 'start_time') else 0
            uptime_hours = uptime / 3600

            # 打印心跳日志
            separator = "=" * 80
            heartbeat_msg = [
                separator,
                "💓 System Heartbeat: OK",
                f"📊 系统资源:",
                f"   CPU 使用率: {cpu_percent:.1f}%",
                f"   内存使用: {memory_percent:.1f}% ({memory_used_gb:.2f}GB / {memory_total_gb:.2f}GB)",
                f"⏱️  运行时间: {uptime_hours:.2f} 小时 ({uptime:.0f} 秒)",
                f"🔌 WebSocket 状态:",
                f"   {ws_status}",
                separator
            ]

            # 打印到控制台（使用 print 确保可见）
            print("\n" + "\n".join(heartbeat_msg) + "\n")

            # 同时记录到日志
            logger.info(f"💓 系统心跳 | CPU: {cpu_percent:.1f}% | 内存: {memory_percent:.1f}% | "
                      f"运行时间: {uptime_hours:.2f}h | WS: {ws_status}")

        except Exception as e:
            logger.error(f"健康监控异常: {e}", exc_info=True)

    def _get_ws_status(self) -> str:
        """
        获取 WebSocket 连接状态

        Returns:
            str: 连接状态描述
        """
        try:
            # 检查公共 WebSocket
            public_ws = self.engine.public_ws_gateway if hasattr(self.engine, 'public_ws_gateway') else None
            if public_ws:
                if hasattr(public_ws, 'is_connected'):
                    public_status = "✅ 连接" if public_ws.is_connected() else "❌ 断开"
                else:
                    public_status = "❓ 未知"
            else:
                public_status = "❌ 未初始化"

            # 检查私有 WebSocket
            private_ws = self.engine.private_ws_gateway if hasattr(self.engine, 'private_ws_gateway') else None
            if private_ws:
                if hasattr(private_ws, 'is_connected'):
                    private_status = "✅ 连接" if private_ws.is_connected() else "❌ 断开"
                else:
                    private_status = "❓ 未知"
            else:
                private_status = "❌ 未初始化"

            return f"公共: {public_status} | 私有: {private_status}"

        except Exception as e:
            logger.error(f"获取 WebSocket 状态失败: {e}")
            return "❌ 状态检查失败"


def setup_simulation_logging():
    """
    配置模拟运行的日志（支持大文件轮转）

    日志轮转配置：
    - 单个文件最大 100MB
    - 保留 10 个备份文件
    - 总计最大 1GB 日志
    """
    import logging
    import logging.handlers
    from src.utils.logger import get_logger

    # 获取根 Logger
    root_logger = logging.getLogger()

    # 清理旧 Handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    # 设置日志级别
    log_level = logging.INFO
    root_logger.setLevel(log_level)

    # 创建格式器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 添加控制台 Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 添加文件 Handler（大文件轮转）
    logs_dir = PROJECT_ROOT / 'logs' / 'simulation'
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            filename=logs_dir / 'simulation.log',
            maxBytes=100 * 1024 * 1024,  # 100MB
            backupCount=10,  # 保留 10 个备份
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        logger.info(f"📝 模拟运行日志已配置: {logs_dir / 'simulation.log'}")
        logger.info(f"   单文件最大: 100MB, 备份数量: 10, 总计最大: 1GB")

    except Exception as e:
        logger.error(f"无法创建日志文件: {e}", exc_info=True)

    # 降低第三方库日志级别
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('websockets').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('ccxt').setLevel(logging.WARNING)


def validate_simulation_environment():
    """
    验证模拟环境配置

    Returns:
        bool: 是否通过验证
    """
    print("=" * 80)
    print("🔍 模拟环境验证")
    print("=" * 80)

    # 检查 IS_SIMULATION 环境变量
    is_simulation = os.getenv('IS_SIMULATION', '').lower() == 'true'

    if not is_simulation:
        print("❌ 错误: IS_SIMULATION 未设置为 'true'")
        print("   必须在 .env 文件中设置: IS_SIMULATION=true")
        print("   这是安全措施，防止意外连接到实盘环境")
        print("=" * 80)
        return False

    print("✅ IS_SIMULATION=true (安全检查通过)")

    # 检查 USE_DEMO 环境变量
    use_demo = os.getenv('USE_DEMO', '').lower() == 'true'

    if not use_demo:
        print("⚠️  警告: USE_DEMO 未设置为 'true'")
        print("   建议在 .env 文件中设置: USE_DEMO=true")
        print("   确保连接到模拟盘而非实盘")
    else:
        print("✅ USE_DEMO=true (模拟盘模式)")

    # 检查 API 密钥
    api_key = os.getenv('OKX_API_KEY')
    secret_key = os.getenv('OKX_SECRET_KEY')
    passphrase = os.getenv('OKX_PASSPHRASE')

    if not api_key or not secret_key or not passphrase:
        print("❌ 错误: OKX API 密钥未完全配置")
        print("   需要: OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE")
        print("=" * 80)
        return False

    print("✅ OKX API 密钥已配置")

    # 检查 psutil 是否安装
    try:
        import psutil
        print("✅ psutil 已安装 (用于资源监控)")
    except ImportError:
        print("⚠️  警告: psutil 未安装，将跳过 CPU/内存监控")
        print("   安装: pip install psutil")

    print("=" * 80)
    print("✅ 环境验证通过，可以安全启动模拟运行")
    print("=" * 80)
    return True


def load_simulation_config() -> dict:
    """
    加载模拟运行配置

    Returns:
        dict: 配置字典
    """
    # 加载环境变量
    env_file = PROJECT_ROOT / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f"已加载环境变量: {env_file}")
    else:
        logger.error(f"未找到 .env 文件: {env_file}")
        sys.exit(1)

    # 创建默认配置
    config = create_default_config()

    # 强制设置模拟模式
    config['rest_gateway']['use_demo'] = True
    config['public_ws']['use_demo'] = True
    config['private_ws']['use_demo'] = True

    logger.info("🔒 强制设置模拟模式 (所有网关)")

    # 从环境变量加载配置
    # REST Gateway
    api_key = os.getenv('OKX_API_KEY')
    if api_key:
        config['rest_gateway']['api_key'] = api_key

    secret_key = os.getenv('OKX_SECRET_KEY')
    if secret_key:
        config['rest_gateway']['secret_key'] = secret_key

    passphrase = os.getenv('OKX_PASSPHRASE')
    if passphrase:
        config['rest_gateway']['passphrase'] = passphrase

    # 交易对配置
    symbol = os.getenv('SCALPER_SYMBOL') or os.getenv('TRADING_SYMBOL', 'SOL-USDT-SWAP')
    config['public_ws']['symbol'] = symbol
    logger.info(f"📊 交易对: {symbol}")

    # 资金配置
    total_capital = float(os.getenv('TOTAL_CAPITAL', 10000.0))
    config['total_capital'] = total_capital
    logger.info(f"💰 总资金: {total_capital:.2f} USDT")

    # 策略配置
    strategies_config = []
    active_strategy = os.getenv('ACTIVE_STRATEGY', 'scalper_v1').lower()

    if active_strategy == 'scalper_v1':
        enable_scalper = os.getenv('ENABLE_SCALPER_V1', 'true').lower() == 'true'

        if enable_scalper:
            position_size_env = os.getenv('SCALPER_POSITION_SIZE')
            position_size_value = float(position_size_env) if position_size_env else None

            scalper_config = {
                'id': 'scalper_v1',
                'type': 'scalper_v1',
                'capital': float(os.getenv('SCALPER_CAPITAL', 10000.0)),
                'params': {
                    'symbol': symbol,
                    'imbalance_ratio': float(os.getenv('SCALPER_IMBALANCE_RATIO', 6.0)),
                    'min_flow_usdt': float(os.getenv('SCALPER_MIN_FLOW', 100000.0)),
                    'take_profit_pct': float(os.getenv('SCALPER_TAKE_PROFIT_PCT', 0.002)),
                    'stop_loss_pct': float(os.getenv('SCALPER_STOP_LOSS_PCT', 0.01)),
                    'time_limit_seconds': int(os.getenv('SCALPER_TIME_LIMIT_SECONDS', 5)),
                    'cooldown_seconds': float(os.getenv('SCALPER_COOLDOWN', 0.0)),
                    'position_size': position_size_value
                }
            }
            strategies_config.append(scalper_config)
            logger.info(f"📈 已启用策略: ScalperV1")

    config['strategies'] = strategies_config

    return config


def print_simulation_banner():
    """打印模拟运行横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   🚀 Athena OS v3.0 - 模拟运行模式                                           ║
║                                                                              ║
║   ⚠️  当前运行在 OKX Demo Trading 环境                                        ║
║   💰 不涉及真实资金，仅用于测试和验证                                           ║
║                                                                              ║
║   📋 功能:                                                                    ║
║   • 长期运行测试 (24-48 小时)                                                   ║
║   • 健康监控 (每分钟心跳)                                                       ║
║   • 日志轮转 (100MB/文件, 保留 10 个备份)                                        ║
║   • 资源监控 (CPU/内存)                                                        ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
    print(banner)


async def main():
    """
    主函数
    """
    # 1. 打印横幅
    print_simulation_banner()

    # 2. 验证模拟环境
    if not validate_simulation_environment():
        sys.exit(1)

    # 3. 配置日志（大文件轮转）
    setup_simulation_logging()

    logger.info("=" * 80)
    logger.info("🚀 Athena OS 模拟运行启动中...")
    logger.info("=" * 80)

    # 4. 加载配置
    config = load_simulation_config()

    # 5. 创建引擎
    engine = Engine(config)
    engine.start_time = time.time()  # 记录启动时间

    # 6. 创建健康监控器
    health_monitor = HealthMonitor(engine, check_interval=60)

    # 7. 启动系统
    try:
        logger.info("🚀 正在启动引擎...")

        # 启动健康监控
        await health_monitor.start()

        # 运行引擎
        await engine.run()

    except KeyboardInterrupt:
        logger.info("\n" + "=" * 80)
        logger.info("👋 收到 Ctrl+C，准备退出...")
        logger.info("=" * 80)

        # 停止健康监控
        await health_monitor.stop()

        # 停止引擎
        await engine.stop()

        logger.info("✅ Athena OS 模拟运行已安全停止")

    except Exception as e:
        logger.error("=" * 80, exc_info=True)
        logger.error(f"❌ 系统异常: {e}", exc_info=True)
        logger.error("=" * 80)

        # 停止健康监控
        await health_monitor.stop()

        # 停止引擎
        await engine.stop()

        sys.exit(1)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Athena OS 已停止")
        sys.exit(0)
