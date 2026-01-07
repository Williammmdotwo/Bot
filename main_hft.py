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
from typing import Optional
from dotenv import load_dotenv

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.high_frequency.config_loader import load_hft_config
from src.high_frequency.data.memory_state import MarketState
from src.high_frequency.data.tick_stream import TickStream
from src.high_frequency.execution.executor import OrderExecutor
from src.high_frequency.execution.circuit_breaker import RiskGuard
from src.high_frequency.core.engine import HybridEngine
from src.utils.logging_config import setup_logging, set_log_level, get_hud_logger
from datetime import datetime

# 配置日志
setup_logging()
# 临时设置为 DEBUG 级别，查看 WebSocket 消息
set_log_level('DEBUG')
# 手动设置所有日志器的级别，确保 DEBUG 生效
logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger('src.high_frequency.data.tick_stream').setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# 全局变量（用于信号处理）
tick_stream: Optional[TickStream] = None
executor: Optional[OrderExecutor] = None
stop_event = asyncio.Event()

# HUD 打印计数器（避免首次打印）
hud_print_count = 0


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
    print(f"  - Tick 数量: {engine_stats.get('tick_count', 0):,}")
    print(f"  - 秃鹫触发: {engine_stats.get('vulture_triggers', 0)}")
    print(f"  - 狙击触发: {engine_stats.get('sniper_triggers', 0)}")
    print(f"  - 订单执行: {engine_stats.get('trade_executions', 0)}")

    ema_fast = engine_stats.get('ema_fast')
    ema_slow = engine_stats.get('ema_slow')
    resistance = engine_stats.get('resistance')

    if ema_fast is not None:
        print(f"  - EMA 快速: {ema_fast:.2f}")
    else:
        print(f"  - EMA 快速: 未计算")

    if ema_slow is not None:
        print(f"  - EMA 慢速: {ema_slow:.2f}")
    else:
        print(f"  - EMA 慢速: 未计算")

    if resistance is not None:
        print(f"  - 阻力位: {resistance:.2f}")
    else:
        print(f"  - 阻力位: 未计算")

    # 风控统计
    print(f"\n🛡️  风控状态:")
    print(f"  - 累计亏损: {risk_stats.get('daily_loss', 0):.2f}")
    loss_percent = risk_stats.get('loss_percent', 0)
    print(f"  - 亏损比例: {loss_percent * 100:.2f}%")
    print(f"  - 冷却剩余: {risk_stats.get('cooldown_remaining', 0):.1f}s")
    can_trade = risk_stats.get('can_trade', False)
    print(f"  - 允许交易: {'✓ 是' if can_trade else '✗ 否'}")

    # 市场统计
    print(f"\n📈 市场状态:")
    print(f"  - 总交易数: {market_stats.get('total_trades', 0):,}")
    print(f"  - 大单数: {market_stats.get('whale_trades', 0)}")

    latest_price = market_stats.get('latest_price')
    if latest_price is not None:
        print(f"  - 最新价格: {latest_price:.2f}")
    else:
        print(f"  - 最新价格: 无数据")

    average_price = market_stats.get('average_price')
    if average_price is not None:
        print(f"  - 平均价格: {average_price:.2f}")
    else:
        print(f"  - 平均价格: 无数据")

    min_price = market_stats.get('min_price')
    max_price = market_stats.get('max_price')
    if min_price is not None and max_price is not None:
        print(f"  - 价格范围: {min_price:.2f} ~ {max_price:.2f}")
    else:
        print(f"  - 价格范围: 无数据")

    print("=" * 60)


async def print_hud(engine, risk_guard, market_state, whale_threshold, interval=10):
    """
    打印 HUD（Head-Up Display）到日志文件

    每 10 秒将实时状态摘要写入日志文件（不输出到控制台）

    Args:
        engine: HybridEngine 实例
        risk_guard: RiskGuard 实例
        market_state: MarketState 实例
        whale_threshold: 大单阈值
        interval: 打印间隔（秒），默认 10 秒
    """
    global hud_print_count

    # 获取 HUD 专用 logger（只写文件，不写控制台）
    hud_logger = get_hud_logger()

    while True:
        try:
            # 获取统计数据
            engine_stats = engine.get_statistics()
            risk_stats = risk_guard.get_status()
            market_stats = market_state.get_statistics()

            # 计算 3 秒内流量压力
            net_volume, trade_count, intensity = market_state.calculate_flow_pressure(3.0)

            # 格式化时间
            current_time = datetime.now().strftime("%H:%M:%S")

            # EMA 快/慢
            ema_fast = engine_stats.get('ema_fast')
            ema_slow = engine_stats.get('ema_slow')
            ema_str = f"{ema_fast:.2f} / {ema_slow:.2f}" if (ema_fast and ema_slow) else "未计算"

            # 最新价格
            latest_price = market_stats.get('latest_price')
            price_str = f"{latest_price:.2f}" if latest_price else "无数据"

            # 3秒内交易数（净买入）
            # 🔥 修复：使用 trade_count（3秒内的笔数），而不是 whale_trades（累计大单数）
            net_buy_str = f"+{abs(net_volume):.0f} U" if net_volume > 0 else f"{net_volume:.0f} U"
            flow_str = f"{trade_count} (净买入: {net_buy_str})"

            # 余额 & 盈亏
            current_balance = risk_stats.get('current_balance', 0)
            loss_percent = risk_stats.get('loss_percent', 0)
            pnl_str = f"{current_balance:.2f} ({loss_percent*100:+.2f}%)"

            # 冷却状态
            is_cooldown = risk_stats.get('cooldown_remaining', 0) > 0
            cooldown_remaining = risk_stats.get('cooldown_remaining', 0)
            cooldown_str = f"是 (剩余 {cooldown_remaining:.0f}s)" if is_cooldown else "否"

            # 战绩
            vulture_count = engine_stats.get('vulture_triggers', 0)
            sniper_count = engine_stats.get('sniper_triggers', 0)

            # 构建 HUD（写入日志文件）
            hud_lines = [
                f"[{current_time}]",
                f"⚡ HFT 引擎运行中 | 💓 心跳正常",
                "",
                "📊 市场状态:",
                f"  - 最新价格: {price_str}",
                f"  - EMA(快/慢): {ema_str}",
                f"  - 3s内交易数: {flow_str}",
                "",
                "🛡️ 账户状态:",
                f"  - 余额: {pnl_str}",
                f"  - 冷却中: {cooldown_str}",
                "",
                "🎯 战绩:",
                f"  - 秃鹫触发: {vulture_count} 次",
                f"  - 狙击触发: {sniper_count} 次"
            ]

            # 写入 HUD 日志（只写文件，不写控制台）
            hud_text = "\n".join(hud_lines)
            hud_logger.info(hud_text)

            # 首次打印时在控制台提示
            if hud_print_count == 0:
                logger.info("✓ HUD 状态已开始记录到日志文件（每 10 秒）")

            hud_print_count += 1

            # 等待指定间隔
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"HUD 打印失败: {e}")


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
    whale_threshold = hft_config.get("whale_threshold", 100.0)  # 降低阈值以便测试

    # 加载滑点配置
    vulture_mode_config = hft_config.get("vulture_mode", {})
    ioc_slippage_pct = vulture_mode_config.get("ioc_slippage_pct", 0.002)  # 默认 0.2%

    # 加载狙击模式配置
    sniper_mode_config = hft_config.get("sniper_mode", {})
    sniper_flow_window = sniper_mode_config.get("flow_window", 3.0)  # 默认 3 秒
    sniper_min_trades = sniper_mode_config.get("min_trades", 20)  # 默认 20 笔
    sniper_min_net_volume = sniper_mode_config.get("min_net_volume", 10000.0)  # 默认 10000 USDT

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
        ema_slow_period=ema_slow_period,
        ioc_slippage_pct=ioc_slippage_pct,
        sniper_flow_window=sniper_flow_window,
        sniper_min_trades=sniper_min_trades,
        sniper_min_net_volume=sniper_min_net_volume
    )

    # 初始化 Tick 流
    tick_stream = TickStream(
        symbol=symbol,
        market_state=market_state,
        use_demo=use_demo  # 传递环境参数
    )

    # 设置交易回调（每次 Tick 都调用）
    # 🔥 修复：使用 set_trade_callback 而不是 set_whale_callback
    # 这样每次交易都会更新 EMA，而不是只有大单才更新
    async def on_trade(price, size, side, timestamp):
        await engine.on_tick(price, size, side, timestamp)

    tick_stream.set_trade_callback(on_trade)

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

        # 8. 启动 HUD 任务（每 10 秒，记录到日志文件）
        hud_task = asyncio.create_task(
            print_hud(engine, risk_guard, market_state, whale_threshold, interval=10)
        )

        # 9. 启动统计任务（每 30 秒）
        stats_task = asyncio.create_task(
            statistics_printer(engine, risk_guard, market_state, interval=30)
        )

        # 10. 等待停止信号
        await stop_event.wait()

        # 11. 取消任务
        hud_task.cancel()
        stats_task.cancel()
        try:
            await hud_task
        except asyncio.CancelledError:
            pass
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
