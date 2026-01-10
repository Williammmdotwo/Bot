"""
测试 OkxPublicWsGateway 和事件发布

验证：
1. WebSocket 连接
2. 数据接收
3. 事件发布到 EventBus
4. 策略接收事件
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


async def test_gateway():
    """
    测试网关和事件总线
    """
    # 配置日志（DEBUG 级别）
    setup_logging(level="DEBUG")

    logger = get_logger(__name__)

    print("=" * 60)
    print("测试 OkxPublicWsGateway 和事件发布")
    print("=" * 60)

    # 1. 创建事件总线
    logger.info("创建 EventBus...")
    event_bus = EventBus()
    await event_bus.start()
    logger.info("✅ EventBus 已启动")

    # 2. 创建网关
    logger.info("创建 OkxPublicWsGateway...")
    gateway = OkxPublicWsGateway(
        symbol="SOL-USDT-SWAP",
        use_demo=True,
        event_bus=event_bus
    )
    logger.info("✅ 网关已创建")

    # 3. 注册事件处理器（监听所有事件）
    event_count = {'TICK': 0, 'TOTAL': 0}

    async def tick_handler(event):
        """TICK 事件处理器"""
        event_count['TICK'] += 1
        event_count['TOTAL'] += 1

        data = event.data
        logger.info(
            f"📊 [TICK #{event_count['TICK']}] "
            f"{data['symbol']} | {data['price']:.2f} | "
            f"{data['size']:.4f} | {data['side']} | "
            f"{data['usdt_value']:.2f} USDT"
        )

        # 每 10 条打印一次统计
        if event_count['TICK'] % 10 == 0:
            logger.info(f"📈 已收到 {event_count['TICK']} 条 TICK 事件")

    # 注册处理器
    logger.info("注册 TICK 事件处理器...")
    event_bus.register(EventType.TICK, tick_handler)
    logger.info("✅ 事件处理器已注册")

    # 4. 连接网关
    logger.info("连接 WebSocket...")
    if not await gateway.connect():
        logger.error("❌ 网关连接失败")
        await event_bus.stop()
        return

    logger.info("✅ 网关已连接")

    # 5. 等待接收数据（30 秒）
    print("=" * 60)
    print("⏱️  运行 30 秒后自动退出...")
    print("=" * 60)

    await asyncio.sleep(30)

    # 6. 断开连接
    print("=" * 60)
    print(f"📊 测试完成！共收到 {event_count['TICK']} 条 TICK 事件")
    print("=" * 60)

    await gateway.disconnect()
    await event_bus.stop()

    logger.info("✅ 测试完成")


if __name__ == '__main__':
    try:
        asyncio.run(test_gateway())
    except KeyboardInterrupt:
        print("\n👋 已退出")
