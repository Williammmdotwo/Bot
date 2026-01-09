"""
OKX API 鉴权诊断脚本

独立测试 REST API 和 WebSocket 鉴权功能，
用于诊断和验证签名问题。

使用方法：
    python debug_auth.py
"""

import asyncio
import os
import aiohttp
from dotenv import load_dotenv
from src.high_frequency.utils.auth import OkxSigner

# 加载 .env
load_dotenv()

API_KEY = os.getenv("OKX_DEMO_API_KEY")
SECRET_KEY = os.getenv("OKX_DEMO_SECRET")
PASSPHRASE = os.getenv("OKX_DEMO_PASSPHRASE")
BASE_URL = "https://www.okx.com"  # 即使是模拟盘，REST 也通常走这个，带 Header 区分

print("=" * 60)
print("🔍 OKX API 鉴权诊断工具")
print("=" * 60)
print(f"API Key: {API_KEY[:10]}...")
print(f"Secret Key: {SECRET_KEY[:10]}...")
print(f"Passphrase: {PASSPHRASE[:5]}...")
print()


async def test_rest_login():
    """测试 REST API 鉴权"""
    print("-" * 60)
    print("📡 测试 REST API 鉴权")
    print("-" * 60)

    endpoint = "/api/v5/account/balance"
    params = {"ccy": "USDT"}

    # 构造带参数的路径
    from urllib.parse import urlencode
    clean_params = {k: v for k, v in params.items() if v is not None}
    if clean_params:
        query_string = urlencode(clean_params, safe=',')
        request_path = f"{endpoint}?{query_string}"
    else:
        request_path = endpoint

    timestamp = OkxSigner.get_timestamp()
    sign = OkxSigner.sign(timestamp, "GET", request_path, "", SECRET_KEY)

    headers = {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json",
        "x-simulated-trading": "1"  # 模拟盘必须
    }

    print(f"时间戳: {timestamp}")
    print(f"请求路径: {request_path}")
    print(f"签名: {sign}")
    print()

    async with aiohttp.ClientSession() as session:
        url = f"{BASE_URL}{request_path}"
        async with session.get(url, headers=headers) as resp:
            data = await resp.json()
            print(f"状态码: {resp.status}")
            print(f"响应: {data}")
            if data.get('code') == '0':
                print("✅ REST API 鉴权成功！")
                print()
                # 打印余额
                balance_list = data.get('data', [])
                if balance_list:
                    usdt_balance = next((b for b in balance_list if b.get('ccy') == 'USDT'), None)
                    if usdt_balance:
                        avail = float(usdt_balance.get('avail', 0))
                        print(f"💰 USDT 余额: {avail:.2f}")
            else:
                print("❌ REST API 鉴权失败！")
            print()


async def test_ws_login():
    """测试 WebSocket 鉴权"""
    print("-" * 60)
    print("🔗 测试 WebSocket 鉴权")
    print("-" * 60)

    # 尝试使用生产环境 WS 地址连接模拟盘 (绕过 502)
    url = "wss://ws.okx.com:8443/ws/v5/private"

    timestamp = OkxSigner.get_timestamp()
    # WS 登录 path 固定，method 固定 GET
    sign = OkxSigner.sign(timestamp, "GET", "/users/self/verify", "", SECRET_KEY)

    login_packet = {
        "op": "login",
        "args": [{
            "apiKey": API_KEY,
            "passphrase": PASSPHRASE,
            "timestamp": timestamp,
            "sign": sign
        }]
    }

    print(f"连接: {url}")
    print(f"登录包: {login_packet}")
    print()

    async with aiohttp.ClientSession() as session:
        try:
            async with session.ws_connect(url) as ws:
                await ws.send_json(login_packet)
                print("登录包已发送，等待响应...")
                print()

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = msg.json()
                        print(f"收到 WS 消息: {data}")
                        if data.get('event') == 'login' and data.get('code') == '0':
                            print("✅ WebSocket 鉴权成功！")
                            print()
                            break
                        elif data.get('event') == 'error':
                            print("❌ WebSocket 鉴权失败！")
                            print()
                            break
                    else:
                        print(f"消息类型: {msg.type}")
                        break
        except Exception as e:
            print(f"❌ WS 连接异常: {e}")
            print()


async def test_rest_get_pending_orders():
    """测试查询挂单（最容易出错的地方）"""
    print("-" * 60)
    print("📋 测试查询挂单（关键测试）")
    print("-" * 60)

    endpoint = "/api/v5/trade/orders-pending"
    params = {
        "instType": "SWAP",
        "instId": "BTC-USDT-SWAP"
    }

    # 构造带参数的路径
    from urllib.parse import urlencode
    clean_params = {k: v for k, v in params.items() if v is not None}
    if clean_params:
        query_string = urlencode(clean_params, safe=',')
        request_path = f"{endpoint}?{query_string}"
    else:
        request_path = endpoint

    timestamp = OkxSigner.get_timestamp()
    sign = OkxSigner.sign(timestamp, "GET", request_path, "", SECRET_KEY)

    headers = {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json",
        "x-simulated-trading": "1"
    }

    print(f"时间戳: {timestamp}")
    print(f"请求路径: {request_path}")
    print(f"签名: {sign}")
    print()

    async with aiohttp.ClientSession() as session:
        url = f"{BASE_URL}{request_path}"
        async with session.get(url, headers=headers) as resp:
            data = await resp.json()
            print(f"状态码: {resp.status}")
            print(f"响应: {data}")
            if data.get('code') == '0':
                print("✅ 查询挂单成功！")
                print()
                order_list = data.get('data', [])
                if order_list:
                    print(f"📦 挂单数量: {len(order_list)}")
                else:
                    print("📦 暂无挂单")
            else:
                print(f"❌ 查询挂单失败！错误码: {data.get('code')}")
                print(f"错误信息: {data.get('msg')}")
            print()


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("开始诊断测试...")
    print("=" * 60)
    print()

    # 测试 1: REST API 登录
    await test_rest_login()

    # 测试 2: WebSocket 登录
    await test_ws_login()

    # 测试 3: 查询挂单（关键测试）
    await test_rest_get_pending_orders()

    print("=" * 60)
    print("✅ 诊断测试完成")
    print("=" * 60)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
