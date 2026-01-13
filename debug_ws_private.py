import asyncio
import websockets
import json
import time
import hmac
import base64
import os
import hashlib
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

API_KEY = os.getenv("OKX_API_KEY")
SECRET_KEY = os.getenv("OKX_SECRET_KEY")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")
USE_DEMO = True  # 强制模拟盘

# 模拟盘地址
WS_URL = "wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999" if USE_DEMO else "wss://ws.okx.com:8443/ws/v5/private"


def get_sign(timestamp, method, request_path, body, secret_key):
    message = str(timestamp) + str(method) + str(request_path) + str(body)
    mac = hmac.new(bytes(secret_key, encoding='utf8'), bytes(message, encoding='utf8'), digestmod='sha256')
    d = mac.digest()
    return base64.b64encode(d).decode("utf-8")


async def test_private_ws():
    print(f"🔌 正在连接: {WS_URL}")
    print(f"🔑 使用 API_KEY: {API_KEY[:4]}***")

    async with websockets.connect(WS_URL) as websocket:
        print("✅ 连接建立成功！准备登录...")

        # 1. 发送登录包
        timestamp = str(int(time.time()))
        sign = get_sign(timestamp, "GET", "/users/self/verify", "", SECRET_KEY)

        login_msg = {
            "op": "login",
            "args": [
                {
                    "apiKey": API_KEY,
                    "passphrase": PASSPHRASE,
                    "timestamp": timestamp,
                    "sign": sign
                }
            ]
        }
        await websocket.send(json.dumps(login_msg))

        # 2. 等待登录响应
        while True:
            response = await websocket.recv()
            data = json.loads(response)
            print(f"📩 收到消息: {data}")

            if data.get("event") == "login":
                if data.get("code") == "0":
                    print("🎉 登录成功！")
                    break
                else:
                    print(f"❌ 登录失败: {data}")
                    return

        # 3. 订阅频道 (订单和持仓)
        # 注意：模拟盘的合约交易对通常是 SWAP
        sub_msg = {
            "op": "subscribe",
            "args": [
                {
                    "channel": "orders",
                    "instType": "SWAP"  # 监听所有永续合约订单
                },
                {
                    "channel": "positions",
                    "instType": "SWAP"  # 监听所有永续合约持仓
                }
            ]
        }
        print(f"📡 发送订阅请求: {json.dumps(sub_msg)}")
        await websocket.send(json.dumps(sub_msg))

        # 4. 持续监听循环
        print("👀 开始监听数据流 (请现在去运行策略下单)...")
        print("------------------------------------------------")

        try:
            while True:
                response = await websocket.recv()
                data = json.loads(response)

                # 过滤心跳包
                if data == "pong":
                    continue

                # 打印重要数据
                arg = data.get("arg", {})
                channel = arg.get("channel", "unknown")

                if channel == "orders":
                    print(f"📦 [订单更新] {json.dumps(data['data'], indent=2)}")
                elif channel == "positions":
                    print(f"💰 [持仓更新] {json.dumps(data['data'], indent=2)}")
                else:
                    print(f"📨 [其他消息] {data}")

        except KeyboardInterrupt:
            print("🛑 停止监听")


if __name__ == "__main__":
    if not API_KEY:
        print("❌ 错误: 未找到环境变量。请确保 .env 文件存在且配置正确。")
    else:
        asyncio.run(test_private_ws())
