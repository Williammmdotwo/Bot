"""
WebSocket 原始连接测试脚本

用于排查 OKX WebSocket 连接和订阅问题。

功能：
- 直接连接 OKX Public WebSocket
- 发送订阅请求
- 打印所有原始消息（包括 ping/pong）
- 30 秒后自动退出

使用：
    python scripts/test_ws_raw.py
"""

import asyncio
import json
import sys
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))


async def test_websocket():
    """
    测试 WebSocket 连接
    """
    print("=" * 60)
    print("WebSocket 原始连接测试")
    print("=" * 60)

    # WebSocket URL
    WS_URL = "wss://ws.okx.com:8443/ws/v5/public"

    # 订阅消息
    SUBSCRIBE_MSG = {
        "op": "subscribe",
        "args": [
            {
                "channel": "trades",
                "instId": "SOL-USDT-SWAP"
            }
        ]
    }

    print(f"\n📡 连接 URL: {WS_URL}")
    print(f"📤 订阅消息: {json.dumps(SUBSCRIBE_MSG, indent=2)}")
    print(f"\n⏱️  运行 30 秒后自动退出...")
    print("=" * 60)

    # 导入 aiohttp（延迟导入，避免依赖问题）
    try:
        import aiohttp
    except ImportError:
        print("❌ 错误: aiohttp 未安装")
        print("   请运行: pip install aiohttp")
        return

    # 创建超时
    timeout = aiohttp.ClientTimeout(total=35)  # 35 秒超时

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            print("\n🔄 正在连接...")

            async with session.ws_connect(WS_URL) as ws:
                print(f"✅ WebSocket 连接成功!")
                print(f"   状态: {ws.closed}")
                print("=" * 60)

                # 发送订阅请求
                print("\n📤 发送订阅请求...")
                await ws.send_json(SUBSCRIBE_MSG)
                print("✅ 订阅请求已发送")
                print("=" * 60)

                # 接收消息循环
                print("\n📥 开始接收消息...\n")
                message_count = 0
                start_time = asyncio.get_event_loop().time()

                while True:
                    # 检查是否超时（30 秒）
                    current_time = asyncio.get_event_loop().time()
                    if current_time - start_time >= 30:
                        print("\n" + "=" * 60)
                        print(f"⏱️  超时退出 (30 秒)")
                        print(f"📊 共收到 {message_count} 条消息")
                        print("=" * 60)
                        break

                    try:
                        # 接收消息（1 秒超时）
                        msg = await asyncio.wait_for(ws.receive(), timeout=1.0)

                        if msg.type == aiohttp.WSMsgType.TEXT:
                            # 文本消息
                            message_count += 1
                            data = json.loads(msg.data)

                            # 打印原始数据
                            print(f"\n[消息 #{message_count}]")
                            print(f"类型: TEXT")
                            print(f"内容: {json.dumps(data, indent=2, ensure_ascii=False)}")

                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            # 二进制消息
                            message_count += 1
                            print(f"\n[消息 #{message_count}]")
                            print(f"类型: BINARY")
                            print(f"长度: {len(msg.data)} bytes")
                            print(f"内容: {msg.data[:100]}...")  # 只打印前 100 字节

                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            print("\n" + "=" * 60)
                            print("❌ WebSocket 连接已关闭")
                            print("=" * 60)
                            break

                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print("\n" + "=" * 60)
                            print(f"❌ WebSocket 错误: {ws.exception()}")
                            print("=" * 60)
                            break

                        elif msg.type == aiohttp.WSMsgType.CLOSING:
                            print("\n" + "=" * 60)
                            print("🔄 WebSocket 正在关闭...")
                            print("=" * 60)

                    except asyncio.TimeoutError:
                        # 超时继续（1 秒无消息）
                        continue
                    except Exception as e:
                        print(f"\n❌ 接收消息异常: {e}")
                        import traceback
                        traceback.print_exc()
                        break

                # 正常关闭
                await ws.close()

    except aiohttp.ClientError as e:
        print("\n" + "=" * 60)
        print(f"❌ 连接失败: {e}")
        print(f"   类型: {type(e).__name__}")
        print("=" * 60)
        import traceback
        traceback.print_exc()

    except asyncio.TimeoutError:
        print("\n" + "=" * 60)
        print(f"❌ 连接超时: {WS_URL}")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("👋 用户中断")
        print("=" * 60)

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ 未知错误: {e}")
        print(f"   类型: {type(e).__name__}")
        print("=" * 60)
        import traceback
        traceback.print_exc()

    print("\n✅ 测试完成")


if __name__ == '__main__':
    try:
        # 运行测试
        asyncio.run(test_websocket())
    except KeyboardInterrupt:
        print("\n👋 已退出")
