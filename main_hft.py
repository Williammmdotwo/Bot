"""
HFT 交易引擎启动脚本

本脚本是 HFT 模块的独立入口，负责初始化所有模块、启动交易引擎，
并处理优雅退出。

核心功能：
- 加载 HFT 配置
- 初始化所有核心模块
- 启动混合交易引擎
- 优雅退出（Ctrl+C 处理）
- 定期打印统计信息

使用方法：
    python main_hft.py

环境变量：
    OKX_API_KEY: OKX API Key
    OKX_SECRET_KEY: OKX Secret Key
    OKX_PASSPHRASE: OKX Passphrase
    OKX_ENVIRONMENT: 环境类型（production/demo）

设计原则：
- 不引用 src/data_manager
- 不使用 ccxt
- 完整的优雅退出逻辑
"""

import asyncio
import os
import sys
import signal
import logging
from dotenv import load_dotenv

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.high_frequency.config_loader import load_hft_config
from src.high_frequency.data.memory_state import MarketState
from src.high_frequency.data.tick_stream import TickStream
from src.high_frequency.execution.executor import OrderExecutor
from src.high_frequency.execution.circuit_breaker import RiskGuard
from src.high_frequency.core.engine import HybridEngine
from src.utils.logging_config import setup_logging

# 配置日志
setup_logging(log_level="INFO")
logger = logging.getLogger(__name__)

# 全局变量（用于信号处理）
tick_stream: Optional[TickStream] = None
executor: Optional[OrderExecutor] = None
stop_event = asyncio.Event()


async def cleanup():
    """清理资源，优雅退出"""
    logger.info("🔄 开始清理资源...")

    try:
        # 1. 批量撤单
        logger.info("📋 撤销所有挂单...")
        if executor:
            try:
                results = await executor.cancel_all("BTC-USDT-SWAP")
                success_count = sum(1 for r in results if not isinstance(r, Exception))
                logger.info(f"✓ 已撤销 {success_count}/{len(results)} 个订单")
            except Exception as e:
                logger.error(f"⚠️  撤单失败: {e}")

        # 2. 停止 Tick 流
        logger.info("📡 停止 WebSocket 连接...")
        if tick_stream:
            try:
                await tick_stream.stop()
                logger.info("✓ WebSocket 已断开")
            except Exception as e:
                logger.error(f"⚠️  停止 WebSocket 失败: {e}")

        # 3. 关闭 Executor
        logger.info("🔌 关闭订单执行器...")
        if executor:
            try:
                await executor.close()
                logger.info("✓ Executor 已关闭")
            except Exception as e:
                logger.error(f"⚠️  关闭 Executor 失败: {e}")

    except Exception as e:
        logger.error(f"❌ 清理过程中发生错误: {e}")


def signal_handler(sig, frame):
    """信号处理器（Ctrl+C）"""
    logger.warning("\n⚠️  收到停止信号...")
    stop_event.set()


async def print_statistics(engine, risk_guard, market_state):
    """打印统计信息"""
    engine_stats = engine.get_statistics()
    risk_stats = risk_guard.get_status()
    market_stats = market_state.get_statistics()

    print("\n" + "=" * 60)
    print("📊 HFT 引擎统计")
    print("=" * 60)

    # 引擎统计
    print(f"🚀 引擎统计:")
    print(f"  - Tick 数量: {engine_stats['tick_count']:,}")
    print(f"  - 秃鹫触发: {engine_stats['vulture_triggers']}")
    print(f"  - 狙击触发: {engine_stats['sniper_triggers']}")
    print(f"  - 订单执行: {engine_stats['trade_executions']}")
    print(f"  - EMA 快速: {engine_stats['ema_fast']:.2f}")
    print(f"  - EMA 慢速: {engine_stats['ema_slow']:.2f}")
    print(f"  - 阻力位: {engine_stats['resistance']:.2f}")

    # 风控统计
    print(f"\n🛡️  风控状态:")
    print(f"  - 累计亏损: {risk_stats['daily_loss']:.2f}")
    print(f"  - 亏损比例: {risk_stats['loss_percent'] * 100:.2f}%")
    print(f"  - 冷却剩余: {risk_stats['cooldown_remaining']:.1f}s")
    print(f"  - 允许交易: {'✓ 是' if risk_stats['can_trade'] else '✗ 否'}")

    # 市场统计
    print(f"\n📈 市场状态:")
    print(f"  - 总交易数: {market_stats['total_trades']:,}")
    print(f"  - 大单数: {market_stats['whale_trades']}")
    print(f"  - 最新价格: {market_stats['latest_price']:.2f}")
    print(f"  - 平均价格: {market_stats['average_price']:.2f}")
    print(f"  - 价格范围: {market_stats['min_price']:.2f} ~ {market_stats['max_price']:.2f}")

    print("=" * 60)


async def statistics_printer(engine, risk_guard, market_state, interval=30):
    """定期打印统计信息"""
    while True:
        try:
            await asyncio.sleep(interval)
            await print_statistics(engine, risk_guard, market_state)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"打印统计信息失败: {e}")


async def main():
    """主函数"""
    global tick_stream, executor, stop_event

    # 1. 加载环境变量
    load_dotenv()

    # 2. 判断是否使用模拟交易
    okx_environment = os.getenv("OKX_ENVIRONMENT", "production").lower()
    use_demo = okx_environment in ["demo", "demo环境", "demo-trading"]

    # 3. 根据 API 密钥
    if use_demo:
        # 使用模拟盘密钥
        api_key = os.getenv("OKX_DEMO_API_KEY")
        secret_key = os.getenv("OKX_DEMO_SECRET")
        passphrase = os.getenv("OKX_DEMO_PASSPHRASE")

        logger.info("🌍 使用模拟交易环境（Demo API）")

        if not all([api_key, secret_key, passphrase]):
            logger.error("❌ 模拟盘 API 密钥未完整配置，请检查 .env 文件")
            print("\n请确保在 .env 文件中设置以下变量：")
            print("  - OKX_DEMO_API_KEY")
            print("  - OKX_DEMO_SECRET")
            print("  - OKX_DEMO_PASSPHRASE")
            return
    else:
        # 使用实盘密钥
        api_key = os.getenv("OKX_API_KEY")
        secret_key = os.getenv("OKX_SECRET")  # 注意：是 OKX_SECRET 而不是 OKX_SECRET_KEY
        passphrase = os.getenv("OKX_PASSPHRASE")

        logger.info("🌍 使用实盘交易环境（Production API）")

        if not all([api_key, secret_key, passphrase]):
            logger.error("❌ 实盘 API 密钥未完整配置，请检查 .env 文件")
            print("\n请确保在 .env 文件中设置以下变量：")
            print("  - OKX_API_KEY")
            print("  - OKX_SECRET")
            print("  - OKX_PASSPHRASE")
            return

    # 4. 加载 HFT 配置
    logger.info("📋 加载 HFT 配置...")
    hft_config = await load_hft_config()

    # 配置参数
    symbol = hft_config.get("symbol", "BTC-USDT-SWAP")
    mode = hft_config.get("mode", "hybrid")
    order_size = hft_config.get("order_size", 0.01)
    ema_fast_period = hft_config.get("ema_fast_period", 9)
    ema_slow_period = hft_config.get("ema_slow_period", 21)
    initial_balance = hft_config.get("initial_balance", 10000.0)
    current_balance = hft_config.get("current_balance", 10000.0)
    whale_threshold = hft_config.get("whale_threshold", 10000.0)

    # 5. 初始化模块
    logger.info("🔧 初始化模块...")

    # 初始化市场状态
    market_state = MarketState()
    market_state.set_whale_threshold(whale_threshold)

    # 初始化订单执行器
    executor = OrderExecutor(
        api_key=api_key,
        secret_key=secret_key,
        passphrase=passphrase,
        base_url="https://www.okx.com",
        use_demo=use_demo,
        timeout=5  # HFT 场景使用更短的超时
    )

    # 初始化风控（单例）
    risk_guard = RiskGuard()
    risk_guard.set_balances(initial=initial_balance, current=current_balance)

    # 初始化混合引擎
    engine = HybridEngine(
        market_state=market_state,
        executor=executor,
        risk_guard=risk_guard,
        symbol=symbol,
        mode=mode,
        order_size=order_size,
        ema_fast_period=ema_fast_period,
        ema_slow_period=ema_slow_period
    )

    # 初始化 Tick 流
    tick_stream = TickStream(
        symbol=symbol,
        market_state=market_state,
        use_demo=use_demo
    )

    # 设置大单回调（触发引擎）
    async def on_whale(price, size, side, timestamp, usdt_value):
        await engine.on_tick(price, timestamp)

    tick_stream.set_whale_callback(on_whale)

    # 6. 启动引擎
    print("\n" + "=" * 60)
    print("🚀 HFT 交易引擎启动")
    print("=" * 60)
    print(f"📊 交易对: {symbol}")
    print(f"🎯 模式: {mode}")
    print(f"📦 订单大小: {order_size}")
    print(f"🌍 环境: {'模拟交易' if use_demo else '实盘交易'}")
    print(f"📈 EMA 周期: 快速={ema_fast_period}, 慢速={ema_slow_period}")
    print(f"💰 初始余额: {initial_balance:.2f}")
    print(f"🐋 大单阈值: {whale_threshold:.2f} USDT")
    print("=" * 60)

    try:
        # 7. 启动 Tick 流
        logger.info("📡 连接 WebSocket...")
        await tick_stream.start()

        print("\n✓ HFT 引擎已启动，等待交易信号...")
        print("✓ 按 Ctrl+C 停止\n")

        # 8. 启动统计任务
        stats_task = asyncio.create_task(
            statistics_printer(engine, risk_guard, market_state, interval=30)
        )

        # 9. 等待停止信号
        await stop_event.wait()

        # 10. 取消统计任务
        stats_task.cancel()
        try:
            await stats_task
        except asyncio.CancelledError:
            pass

    except KeyboardInterrupt:
        logger.warning("\n⚠️  收到中断信号")
    except Exception as e:
        logger.error(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 11. 清理资源
        await cleanup()

        # 12. 打印最终统计
        print("\n" + "=" * 60)
        print("📊 最终统计")
        print("=" * 60)
        await print_statistics(engine, risk_guard, market_state)

        print("\n✓ HFT 引擎已停止")


if __name__ == "__main__":
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 运行主函数
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  收到中断信号")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
