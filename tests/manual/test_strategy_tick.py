"""
测试策略是否收到 TICK 事件
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logger import setup_logging, get_logger
from src.core.event_bus import EventBus
from src.core.event_types import EventType
from src.gateways.okx.ws_public_gateway import OkxPublicWsGateway

# 设置 DEBUG 日志
setup_logging(level="DEBUG")
logger = get_logger(__name__)


async def test_strategy_receives_tick():
    """测试策略接收 TICK 事件"""

    print("=" * 60)
    print("测试：策略是否收到 TICK 事件")
    print("=" * 60)

    # 创建事件总线
    event_bus = EventBus()
    await event_bus.start()

    # 创建网关
    gateway = OkxPublicWsGateway(
        symbol="SOL-USDT-SWAP",
        use_demo=True,
        event_bus=event_bus
    )

    # 模拟策略接收 TICK
    tick_count = [0]

    async def strategy_tick_handler(event):
        """模拟策略的 Tick 处理器"""
        tick_count[0] += 1
        logger.info(
            f"🎯 策略 Sniper 收到 Tick #{tick_count[0]}: "
            f"{event.data['symbol']} | {event.data['price']:.2f} | "
            f"{event.data['side']} | {event.data['usdt_value']:.2f} USDT"
        )

    event_bus.register(EventType.TICK, strategy_tick_handler)

    # 连接网关
    if not await gateway.connect():
        logger.error("网关连接失败")
        await event_bus.stop()
        return

    print("=" * 60)
    print("⏱️  运行 30 秒...")
    print("=" * 60)

    await asyncio.sleep(30)

    # 断开连接
    print("=" * 60)
    print(f"📊 测试完成！策略共收到 {tick_count[0]} 条 Tick 事件")
    print("=" * 60)

    await gateway.disconnect()
    await event_bus.stop()

    logger.info("✅ 测试完成")


if __name__ == '__main__':
    try:
        asyncio.run(test_strategy_receives_tick())
    except KeyboardInterrupt:
        print("\n👋 已退出")
