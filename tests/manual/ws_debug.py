"""
调试版本的 OkxPublicWsGateway

添加详细的日志输出，追踪消息处理流程
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logger import setup_logging, get_logger
from src.core.event_bus import EventBus
from src.core.event_types import EventType
import aiohttp


class DebugOkxPublicWsGateway:
    """调试版本的公共 WebSocket 网关"""

    def __init__(self, symbol: str, event_bus=None):
        self.symbol = symbol
        self._event_bus = event_bus
        self._connected = False
        self._ws = None
        self._session = None

        logger = get_logger(__name__)
        logger.info(f"调试网关初始化: symbol={symbol}")

    async def connect(self) -> bool:
        """连接 WebSocket"""
        logger = get_logger(__name__)

        try:
            # 创建 session
            self._session = aiohttp.ClientSession()

            ws_url = "wss://ws.okx.com:8443/ws/v5/public"
            logger.info(f"正在连接: {ws_url}")

            self._ws = await self._session.ws_connect(ws_url)
            self._connected = True

            logger.info(f"✅ WebSocket 连接成功")

            # 发送订阅消息
            subscribe_msg = {
                "op": "subscribe",
                "args": [{
                    "channel": "trades",
                    "instId": self.symbol
                }]
            }

            json_str = json.dumps(subscribe_msg)
            logger.info(f"📤 发送订阅: {json_str}")

            await self._ws.send_str(json_str)
            logger.info(f"✅ 订阅已发送")

            # 启动消息循环
            asyncio.create_task(self._message_loop())
            logger.info(f"✅ 消息循环已启动")

            return True

        except Exception as e:
            logger.error(f"❌ 连接失败: {e}", exc_info=True)
            return False

    async def disconnect(self):
        """断开连接"""
        logger = get_logger(__name__)
        logger.info("断开连接...")

        self._connected = False

        if self._ws:
            await self._ws.close()
            self._ws = None

        if self._session:
            await self._session.close()
            self._session = None

        logger.info("✅ 已断开")

    async def _message_loop(self):
        """消息循环（带详细日志）"""
        logger = get_logger(__name__)
        logger.info("🔄 消息循环开始运行...")

        msg_count = 0
        start_time = asyncio.get_event_loop().time()

        while self._connected:
            try:
                # 接收消息
                logger.debug("等待接收消息...")
                msg = await asyncio.wait_for(
                    self._ws.receive(),
                    timeout=30.0
                )

                msg_count += 1
                logger.info(f"📥 [消息 #{msg_count}] 类型: {msg.type}")

                if msg.type == aiohttp.WSMsgType.TEXT:
                    logger.info(f"   内容: {msg.data[:200]}...")

                    # 解析数据
                    try:
                        data = json.loads(msg.data)
                        logger.info(f"   解析后: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}...")

                        await self._process_data(data)

                    except json.JSONDecodeError as e:
                        logger.error(f"   ❌ JSON 解析失败: {e}")

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"   ❌ WebSocket 错误: {msg.data}")
                    self._connected = False

                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.warning("   ⚠️  WebSocket 连接已关闭")
                    self._connected = False

                elif msg.type == aiohttp.WSMsgType.CLOSING:
                    logger.warning("   ⚠️  WebSocket 正在关闭")

                else:
                    logger.info(f"   其他类型: {msg.type}")

                # 检查超时
                current_time = asyncio.get_event_loop().time()
                if current_time - start_time >= 30:
                    logger.info(f"⏱️  30 秒超时，退出消息循环")
                    break

            except asyncio.TimeoutError:
                logger.warning("⚠️  接收消息超时（30 秒）")
                logger.info("   继续等待...")
                continue

            except Exception as e:
                logger.error(f"❌ 消息处理异常: {e}", exc_info=True)
                self._connected = False
                break

        logger.info(f"🏁 消息循环结束，共收到 {msg_count} 条消息")

    async def _process_data(self, data: dict):
        """处理数据"""
        logger = get_logger(__name__)

        # 处理订阅响应
        if "event" in data:
            event = data["event"]
            logger.info(f"📋 事件: {event}")

            if event == "subscribe":
                code = data.get("code")
                if code == "0":
                    logger.info(f"✅ 订阅成功: {data.get('arg', {})}")
                else:
                    logger.error(f"❌ 订阅失败: {data}")
            elif event == "error":
                logger.error(f"❌ OKX 错误: {data}")
            return

        # 处理交易数据
        if "data" in data and isinstance(data["data"], list):
            logger.info(f"📊 收到 {len(data['data'])} 笔交易数据")

            for i, trade_item in enumerate(data["data"]):
                logger.info(f"   交易 #{i+1}: {trade_item}")
                await self._process_trade(trade_item)

    async def _process_trade(self, trade_item):
        """处理单笔交易"""
        logger = get_logger(__name__)

        try:
            price = float(trade_item.get("px", "0"))
            size = float(trade_item.get("sz", "0"))
            timestamp = int(trade_item.get("ts", "0"))
            side = trade_item.get("side", "")

            usdt_value = price * size

            logger.info(
                f"💰 成交: {price:.2f} x {size:.4f} = {usdt_value:.2f} USDT "
                f"| {side} | {timestamp}"
            )

            # 发布事件
            if self._event_bus:
                event = EventType.TICK(
                    data={
                        'symbol': self.symbol,
                        'price': price,
                        'size': size,
                        'side': side,
                        'usdt_value': usdt_value,
                        'timestamp': timestamp
                    },
                    source="okx_ws_public"
                )
                self._event_bus.put_nowait(event)
                logger.info(f"✅ 事件已发布到 EventBus")

        except Exception as e:
            logger.error(f"❌ 交易处理异常: {e}", exc_info=True)


async def test_debug_gateway():
    """测试调试网关"""
    # 配置日志（DEBUG 级别）
    setup_logging(level="DEBUG")

    logger = get_logger(__name__)

    print("=" * 60)
    print("调试 OkxPublicWsGateway")
    print("=" * 60)

    # 创建事件总线
    event_bus = EventBus()
    await event_bus.start()
    logger.info("✅ EventBus 已启动")

    # 创建调试网关
    gateway = DebugOkxPublicWsGateway(
        symbol="SOL-USDT-SWAP",
        event_bus=event_bus
    )

    # 注册事件处理器
    tick_count = [0]

    async def tick_handler(event):
        tick_count[0] += 1
        logger.info(
            f"🎯 [TICK #{tick_count[0]}] "
            f"{event.data['symbol']} | {event.data['price']:.2f} | "
            f"{event.data['side']}"
        )

    event_bus.register(EventType.TICK, tick_handler)
    logger.info("✅ 事件处理器已注册")

    # 连接网关
    if not await gateway.connect():
        logger.error("❌ 网关连接失败")
        await event_bus.stop()
        return

    # 等待 30 秒
    print("=" * 60)
    print("⏱️  运行 30 秒...")
    print("=" * 60)

    await asyncio.sleep(30)

    # 断开连接
    print("=" * 60)
    print(f"📊 测试完成！共收到 {tick_count[0]} 条 TICK 事件")
    print("=" * 60)

    await gateway.disconnect()
    await event_bus.stop()

    logger.info("✅ 测试完成")


if __name__ == '__main__':
    try:
        asyncio.run(test_debug_gateway())
    except KeyboardInterrupt:
        print("\n👋 已退出")
