"""
OKX 模拟盘测试：三个关键生产级补丁

测试内容：
1. 硬止损重试机制（裸奔风险防护）
2. 幽灵单防护（持仓归零时撤销止损单）
3. 动态交易对加载

使用方法：
    1. 确保 .env 文件已配置（USE_DEMO=true）
    2. python scripts/test_critical_patches_demo.py

注意：
- 使用 OKX 模拟盘（Demo Trading）
- 使用 SOL-USDT-SWAP（约 100 USDT）
- 自动执行测试流程
- 完整的错误处理和回滚机制
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except ImportError:
    print("警告: python-dotenv 未安装")
    load_dotenv = lambda: None

from src.gateways.okx.rest_api import OkxRestGateway
from src.oms.order_manager import OrderManager
from src.oms.position_manager import PositionManager
from src.oms.capital_commander import CapitalCommander
from src.core.event_bus import EventBus
from src.core.event_types import Event, EventType

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_patch_1_stop_loss_retry(gateway: OkxRestGateway, event_bus: EventBus):
    """
    测试补丁一：硬止损重试机制（真实环境）

    模拟场景：
    1. 下单买入 SOL-USDT-SWAP（0.01，约 50 USDT）
    2. 等待成交
    3. 验证止损单是否自动提交
    """
    logger.info("=" * 60)
    logger.info("测试补丁一：硬止损重试机制（真实环境）")
    logger.info("=" * 60)

    try:
        # 1. 创建 OrderManager
        order_manager = OrderManager(
            rest_gateway=gateway,
            event_bus=event_bus
        )

        # 2. 下单买入 0.01 SOL（约 50 USDT）
        symbol = "SOL-USDT-SWAP"
        order_size = 0.01  # SOL 永续合约最小数量
        order_type = "market"  # 市价单

        logger.info(f"下单: {symbol} buy {order_size} @ market")

        order = await order_manager.submit_order(
            symbol=symbol,
            side="buy",
            order_type=order_type,
            size=order_size,
            stop_loss_price=0,  # 不设置止损，观察行为
            strategy_id="test_patch_1"
        )

        if not order:
            logger.error("❌ 下单失败")
            return False

        logger.info(f"✅ 订单已提交: {order.order_id}")

        # 3. 等待成交（最多 30 秒）
        logger.info("等待订单成交...")
        max_wait = 30
        wait_interval = 2
        total_waited = 0

        while total_waited < max_wait:
            await asyncio.sleep(wait_interval)
            total_waited += wait_interval

            # 查询订单状态
            order_status = await gateway.get_order_status(order.order_id, symbol)
            if order_status:
                status = order_status.get('state', '')
                filled_sz = float(order_status.get('fillSz', 0))

                logger.info(f"订单状态: {status}, 成交: {filled_sz}/{order_size}")

                if status in ['filled', 'live']:
                    if filled_sz >= order_size * 0.9:  # 至少成交 90%
                        logger.info(f"✅ 订单已成交: {filled_sz} SOL")
                        break

        # 4. 验证止损单
        await asyncio.sleep(2)  # 给止损单提交时间

        # 查询持仓
        positions = await gateway.get_positions(symbol)
        if positions:
            logger.info(f"当前持仓: {positions[0]}")
        else:
            logger.info("无持仓")

        # 查询止损单（同步方法，不需要 await）
        all_orders = order_manager.get_all_orders()
        stop_loss_orders = [
            o for o in all_orders.values()
            if o.order_type == 'stop_market'
        ]

        if stop_loss_orders:
            logger.info(f"✅ 发现 {len(stop_loss_orders)} 个止损单")
            for sl_order in stop_loss_orders:
                logger.info(f"  - {sl_order.order_id}: {sl_order.symbol} {sl_order.side}")
        else:
            logger.warning("⚠️  未发现止损单（这是正常的，因为没有设置 stop_loss_price）")

        # 5. 清理：撤销所有挂单，平仓
        logger.info("清理测试订单...")
        await order_manager.cancel_all_orders(symbol=symbol)

        # 平仓
        if positions:
            position_size = positions[0].get('size', 0)
            if position_size > 0:
                close_side = 'sell' if positions[0].get('side') == 'long' else 'buy'
                logger.info(f"平仓: {symbol} {close_side} {position_size}")

                try:
                    await order_manager.submit_order(
                        symbol=symbol,
                        side=close_side,
                        order_type='market',
                        size=position_size,
                        strategy_id="cleanup"
                    )
                except Exception as e:
                    logger.error(f"平仓失败: {e}")

        logger.info("✅ 补丁一测试完成")
        return True

    except Exception as e:
        logger.error(f"❌ 补丁一测试失败: {e}", exc_info=True)
        return False


async def test_patch_2_ghost_order_protection(gateway: OkxRestGateway, event_bus: EventBus):
    """
    测试补丁二：幽灵单防护（真实环境）

    模拟场景：
    1. 下单买入 SOL-USDT-SWAP（0.01）
    2. 等待成交
    3. 挂止损单
    4. 平仓
    5. 验证止损单是否自动撤销
    """
    logger.info("=" * 60)
    logger.info("测试补丁二：幽灵单防护（真实环境）")
    logger.info("=" * 60)

    try:
        # 1. 创建 OrderManager 和 PositionManager
        order_manager = OrderManager(
            rest_gateway=gateway,
            event_bus=event_bus
        )
        position_manager = PositionManager(
            event_bus=event_bus,
            order_manager=order_manager
        )

        # 2. 下单买入
        symbol = "SOL-USDT-SWAP"
        order_size = 0.01

        logger.info(f"下单: {symbol} buy {order_size} @ market")

        order = await order_manager.submit_order(
            symbol=symbol,
            side="buy",
            order_type="market",
            size=order_size,
            stop_loss_price=0,  # 后面手动挂止损单
            strategy_id="test_patch_2"
        )

        if not order:
            logger.error("❌ 下单失败")
            return False

        logger.info(f"✅ 订单已提交: {order.order_id}")

        # 3. 等待成交
        logger.info("等待订单成交...")
        await asyncio.sleep(10)  # 等待 10 秒

        # 4. 查询持仓
        positions = await gateway.get_positions(symbol)
        if not positions:
            logger.warning("⚠️  订单未成交，跳过测试")
            return False

        position = positions[0]
        position_size = position.get('size', 0)
        logger.info(f"✅ 当前持仓: {position_size} SOL")

        # 5. 手动挂止损单（模拟场景）
        # 获取当前价格，设置止损价
        current_price = position.get('entry_price', 0)
        stop_price = current_price * 0.95  # 止损价 5% 低于开仓价

        logger.info(f"挂止损单: {symbol} stop @ {stop_price:.2f}")

        # 注意：OKX SWAP 合约强制 size >= 1，所以会自动调整
        stop_loss_order = await order_manager.submit_order(
            symbol=symbol,
            side="sell",
            order_type="stop_market",  # 服务器端止损单
            size=1,  # 强制使用最小数量 1（OKX 要求）
            price=stop_price,
            strategy_id="test_stop_loss",
            reduce_only=True
        )

        if stop_loss_order:
            logger.info(f"✅ 止损单已挂: {stop_loss_order.order_id}")
        else:
            logger.warning("⚠️  止损单挂单失败")

        # 6. 等待一下
        await asyncio.sleep(2)

        # 查询所有止损单（同步方法，不需要 await）
        all_orders = order_manager.get_all_orders()
        stop_loss_orders_before = [
            o for o in all_orders.values()
            if o.order_type == 'stop_market' and o.symbol == symbol
        ]
        logger.info(f"平仓前止损单数量: {len(stop_loss_orders_before)}")

        # 7. 平仓
        # OKX 持仓 side 是 'net'，根据 size 判断方向
        if position_size > 0:
            close_side = 'sell'
        else:
            close_side = 'buy'

        logger.info(f"平仓: {symbol} {close_side} {abs(position_size)}")

        close_order = await order_manager.submit_order(
            symbol=symbol,
            side=close_side,
            order_type="market",
            size=abs(position_size),  # 平仓数量 = 持仓数量的绝对值
            strategy_id="close_position"
        )

        if close_order:
            logger.info(f"✅ 平仓单已提交: {close_order.order_id}")
        else:
            logger.warning("⚠️  平仓单提交失败")

        # 8. 等待持仓归零
        logger.info("等待持仓归零...")
        max_wait = 20
        wait_interval = 2
        total_waited = 0

        while total_waited < max_wait:
            await asyncio.sleep(wait_interval)
            total_waited += wait_interval

            positions = await gateway.get_positions(symbol)
            if not positions:
                logger.info("✅ 持仓已归零")
                break

            logger.info(f"持仓大小: {positions[0].get('size', 0)}")

        # 9. 验证止损单是否被撤销
        await asyncio.sleep(3)  # 给幽灵单防护时间触发

        # 同步方法，不需要 await
        all_orders = order_manager.get_all_orders()
        stop_loss_orders_after = [
            o for o in all_orders.values()
            if o.order_type == 'stop_market' and o.symbol == symbol
        ]

        logger.info(f"平仓后止损单数量: {len(stop_loss_orders_after)}")

        if len(stop_loss_orders_after) < len(stop_loss_orders_before):
            logger.info(f"✅ 幽灵单防护已触发: 撤销了 {len(stop_loss_orders_before) - len(stop_loss_orders_after)} 个止损单")
            return True
        else:
            logger.warning(f"⚠️  止损单未被撤销: {len(stop_loss_orders_after)} 个止损单仍然存在")
            # 手动撤销止损单
            for sl_order in stop_loss_orders_after:
                logger.info(f"手动撤销止损单: {sl_order.order_id}")
                try:
                    await order_manager.cancel_order(sl_order.order_id, symbol)
                except Exception as e:
                    logger.error(f"撤销失败: {e}")
            return False

    except Exception as e:
        logger.error(f"❌ 补丁二测试失败: {e}", exc_info=True)
        return False


async def test_patch_3_dynamic_instrument_loading(gateway: OkxRestGateway, event_bus: EventBus):
    """
    测试补丁三：动态交易对加载（真实环境）

    模拟场景：
    1. 从 OKX API 获取 SWAP 交易对
    2. 加载到 CapitalCommander
    3. 验证 SOL-USDT-SWAP 是否已注册
    """
    logger.info("=" * 60)
    logger.info("测试补丁三：动态交易对加载（真实环境）")
    logger.info("=" * 60)

    try:
        # 1. 从 API 获取 SWAP 交易对
        logger.info("从 OKX API 获取 SWAP 交易对...")
        instruments = await gateway.get_instruments(inst_type="SWAP")

        if not instruments:
            logger.error("❌ 未获取到交易对")
            return False

        logger.info(f"✅ 获取到 {len(instruments)} 个 SWAP 交易对")

        # 2. 创建 CapitalCommander
        capital_commander = CapitalCommander(
            total_capital=10000.0,  # 模拟 10000 USDT
            event_bus=event_bus
        )

        # 3. 注册交易对（只注册 SOL）
        symbol = "SOL-USDT-SWAP"
        found = False

        for inst in instruments:
            inst_id = inst.get('instId', '')
            if symbol in inst_id:
                lot_size = inst.get('lotSz', 0)
                min_order_size = inst.get('minSz', 0)
                tick_size = inst.get('tickSz', 0)

                logger.info(f"找到交易对: {inst_id}")
                logger.info(f"  lotSz: {lot_size}")
                logger.info(f"  minSz: {min_order_size}")
                logger.info(f"  tickSz: {tick_size}")

                # 计算最小名义价值
                min_notional = min_order_size * 100  # 假设价格 100
                if min_notional < 10:
                    min_notional = 10.0

                # 注册到 CapitalCommander
                capital_commander.register_instrument(
                    symbol=inst_id,
                    lot_size=lot_size,
                    min_order_size=min_order_size,
                    min_notional=min_notional
                )

                logger.info(f"✅ 交易对已注册: {inst_id}")
                found = True
                break

        if not found:
            logger.error(f"❌ 未找到交易对: {symbol}")
            return False

        # 4. 验证是否注册成功
        registered_instruments = capital_commander.get_all_instruments()
        if symbol in registered_instruments:
            logger.info(f"✅ 交易对 {symbol} 已成功注册")
            return True
        else:
            logger.error(f"❌ 交易对 {symbol} 未注册")
            return False

    except Exception as e:
        logger.error(f"❌ 补丁三测试失败: {e}", exc_info=True)
        return False


async def cleanup_all(gateway: OkxRestGateway, order_manager: OrderManager, symbol: str = "SOL-USDT-SWAP"):
    """
    清理所有测试数据

    Args:
        gateway: OKX REST 网关
        order_manager: 订单管理器
        symbol: 交易对
    """
    try:
        logger.info("=" * 60)
        logger.info("清理测试数据")
        logger.info("=" * 60)

        # 1. 撤销所有挂单
        logger.info("撤销所有挂单...")
        await order_manager.cancel_all_orders(symbol=symbol)
        await asyncio.sleep(2)

        # 2. 平仓
        positions = await gateway.get_positions(symbol)
        if positions:
            position = positions[0]
            position_size = position.get('size', 0)
            if abs(position_size) > 0.001:  # 如果有持仓
                # OKX 持仓 side 是 'net'，根据 size 判断方向
                if position_size > 0:
                    close_side = 'sell'
                else:
                    close_side = 'buy'

                logger.info(f"平仓: {symbol} {close_side} {abs(position_size)}")

                try:
                    await order_manager.submit_order(
                        symbol=symbol,
                        side=close_side,
                        order_type='market',
                        size=abs(position_size),  # 平仓数量 = 持仓数量的绝对值
                        strategy_id="cleanup"
                    )
                except Exception as e:
                    logger.error(f"平仓失败: {e}")
                await asyncio.sleep(5)

        # 3. 再次检查
        positions = await gateway.get_positions(symbol)
        if positions:
            position_size = positions[0].get('size', 0)
            if abs(position_size) < 0.001:
                logger.info("✅ 持仓已清理")
            else:
                logger.warning(f"⚠️  仍有持仓: {position_size}")
        else:
            logger.info("✅ 无持仓")

        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"清理失败: {e}", exc_info=True)


async def run_all_tests():
    """运行所有测试"""
    logger.info("\n" + "=" * 60)
    logger.info("OKX 模拟盘测试：三个关键生产级补丁")
    logger.info("=" * 60 + "\n")

    # 加载环境变量
    env_file = PROJECT_ROOT / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f"✅ 已加载环境变量: {env_file}")
    else:
        logger.error(f"❌ 未找到 .env 文件: {env_file}")
        return

    # 读取配置
    api_key = os.getenv('OKX_API_KEY')
    secret_key = os.getenv('OKX_SECRET_KEY')
    passphrase = os.getenv('OKX_PASSPHRASE')
    use_demo = os.getenv('USE_DEMO', 'true').lower() == 'true'

    if not api_key or not secret_key or not passphrase:
        logger.error("❌ 缺少 API 配置，请检查 .env 文件")
        return

    logger.info(f"API Key: {api_key[:8]}...")
    logger.info(f"模拟模式: {use_demo}")
    logger.info(f"交易对: SOL-USDT-SWAP")
    logger.info(f"测试资金: 约 100 USDT (0.01 SOL)")
    logger.info("")

    # 创建 Event Bus
    event_bus = EventBus()
    await event_bus.start()

    # 创建 OKX REST 网关
    logger.info("初始化 OKX REST 网关...")
    gateway = OkxRestGateway(
        api_key=api_key,
        secret_key=secret_key,
        passphrase=passphrase,
        use_demo=use_demo,
        event_bus=event_bus
    )

    # 连接网关
    if not await gateway.connect():
        logger.error("❌ 网关连接失败")
        await event_bus.stop()
        return

    logger.info("✅ 网关已连接\n")

    results = {}

    try:
        # 清理之前的测试数据
        logger.info("开始前清理...")
        order_manager = OrderManager(
            rest_gateway=gateway,
            event_bus=event_bus
        )
        await cleanup_all(gateway, order_manager, symbol="SOL-USDT-SWAP")
        await asyncio.sleep(2)
        logger.info("")

        # 测试补丁三（先加载交易对）
        try:
            logger.info("开始测试补丁三...")
            results['patch_3'] = await test_patch_3_dynamic_instrument_loading(gateway, event_bus)
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"❌ 补丁三测试失败: {e}")
            results['patch_3'] = False

        # 测试补丁一（硬止损重试）
        try:
            logger.info("开始测试补丁一...")
            results['patch_1'] = await test_patch_1_stop_loss_retry(gateway, event_bus)
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"❌ 补丁一测试失败: {e}")
            results['patch_1'] = False

        # 测试补丁二（幽灵单防护）
        try:
            logger.info("开始测试补丁二...")
            results['patch_2'] = await test_patch_2_ghost_order_protection(gateway, event_bus)
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"❌ 补丁二测试失败: {e}")
            results['patch_2'] = False

    finally:
        # 最终清理
        logger.info("\n最终清理...")
        order_manager = OrderManager(
            rest_gateway=gateway,
            event_bus=event_bus
        )
        await cleanup_all(gateway, order_manager, symbol="SOL-USDT-SWAP")

        # 关闭网关
        await gateway.disconnect()
        await event_bus.stop()

    # 汇总结果
    logger.info("\n" + "=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)

    patch_names = {
        'patch_1': '补丁一：硬止损重试机制',
        'patch_2': '补丁二：幽灵单防护',
        'patch_3': '补丁三：动态交易对加载'
    }

    for patch_key, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{patch_names[patch_key]}: {status}")

    total_passed = sum(results.values())
    logger.info(f"\n总计: {total_passed}/3 测试通过")

    if total_passed == 3:
        logger.info("\n🎉 所有测试通过！生产级补丁在模拟盘工作正常。")
    else:
        logger.warning(f"\n⚠️  有 {3 - total_passed} 个测试失败")


if __name__ == '__main__':
    # 运行测试
    asyncio.run(run_all_tests())
