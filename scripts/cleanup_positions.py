"""
清理 OKX 模拟盘持仓

清理所有 SOL-USDT-SWAP 持仓和挂单
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
from src.core.event_bus import EventBus

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def cleanup_positions():
    """清理所有持仓"""
    logger.info("=" * 60)
    logger.info("清理 OKX 模拟盘持仓")
    logger.info("=" * 60)

    # 加载环境变量
    env_file = PROJECT_ROOT / '.env'
    if env_file.exists():
        load_dotenv(env_file)
    else:
        logger.error(f"未找到 .env 文件: {env_file}")
        return

    # 读取配置
    api_key = os.getenv('OKX_API_KEY')
    secret_key = os.getenv('OKX_SECRET_KEY')
    passphrase = os.getenv('OKX_PASSPHRASE')
    use_demo = os.getenv('USE_DEMO', 'true').lower() == 'true'

    if not api_key or not secret_key or not passphrase:
        logger.error("缺少 API 配置，请检查 .env 文件")
        return

    symbol = "SOL-USDT-SWAP"

    # 创建 Event Bus
    event_bus = EventBus()
    await event_bus.start()

    # 创建 OKX REST 网关
    gateway = OkxRestGateway(
        api_key=api_key,
        secret_key=secret_key,
        passphrase=passphrase,
        use_demo=use_demo,
        event_bus=event_bus
    )

    if not await gateway.connect():
        logger.error("网关连接失败")
        await event_bus.stop()
        return

    try:
        # 创建 OrderManager
        order_manager = OrderManager(
            rest_gateway=gateway,
            event_bus=event_bus
        )

        # 1. 撤销所有挂单
        logger.info("撤销所有挂单...")
        await order_manager.cancel_all_orders(symbol=symbol)
        await asyncio.sleep(2)

        # 2. 查询持仓
        logger.info("查询持仓...")
        positions = await gateway.get_positions(symbol)

        if positions:
            position = positions[0]
            position_size = position.get('size', 0)
            logger.info(f"当前持仓: {position_size} SOL")

            if abs(position_size) > 0.001:
                # 根据持仓大小判断平仓方向
                if position_size > 0:
                    close_side = 'sell'
                else:
                    close_side = 'buy'

                logger.info(f"平仓: {symbol} {close_side} {abs(position_size)}")

                # 分批平仓（避免一次性平太多）
                batch_size = 2.0  # 每次平 2 个 SOL
                remaining = abs(position_size)

                while remaining > 0:
                    current_size = min(batch_size, remaining)
                    logger.info(f"批量平仓: {close_side} {current_size} SOL")

                    try:
                        await order_manager.submit_order(
                            symbol=symbol,
                            side=close_side,
                            order_type='market',
                            size=current_size,
                            strategy_id="cleanup"
                        )
                    except Exception as e:
                        logger.error(f"平仓失败: {e}")
                        break

                    remaining -= current_size
                    await asyncio.sleep(3)  # 等待成交

                    # 重新查询持仓
                    positions = await gateway.get_positions(symbol)
                    if not positions:
                        logger.info("持仓已清空")
                        break

                    position_size = positions[0].get('size', 0)
                    remaining = abs(position_size)

        else:
            logger.info("无持仓")

        # 3. 最终检查
        await asyncio.sleep(2)
        positions = await gateway.get_positions(symbol)

        if positions:
            final_size = positions[0].get('size', 0)
            if abs(final_size) < 0.001:
                logger.info("✅ 持仓已清理")
            else:
                logger.warning(f"⚠️  仍有持仓: {final_size} SOL")
        else:
            logger.info("✅ 持仓已清理")

        logger.info("=" * 60)
        logger.info("清理完成")
        logger.info("=" * 60)

    finally:
        await gateway.disconnect()
        await event_bus.stop()


if __name__ == '__main__':
    asyncio.run(cleanup_positions())
