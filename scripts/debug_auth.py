#!/usr/bin/env python3
"""
API 鉴权诊断脚本

用于调试 OKX API 的签名和鉴权问题。

使用方法：
    python scripts/debug_auth.py
"""

import os
import sys
from datetime import datetime, timezone
import hmac
import hashlib
import base64
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


def test_timestamp_generation():
    """测试时间戳生成"""
    print("\n" + "="*60)
    print("📅 时间戳生成测试")
    print("="*60)

    # 方法 1：isoformat
    dt = datetime.now(timezone.utc)
    ts1 = dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    print(f"方法 1 (isoformat): {ts1}")

    # 方法 2：strftime
    ts2 = dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    print(f"方法 2 (strftime):  {ts2}")

    # 对比
    if ts1 == ts2:
        print("✅ 两种方法生成的时间戳完全一致")
    else:
        print("❌ 两种方法生成的时间戳不一致！")
        print(f"   差异: ts1 长度={len(ts1)}, ts2 长度={len(ts2)}")


def test_signature(api_key, secret_key, passphrase):
    """测试签名生成"""
    print("\n" + "="*60)
    print("🔐 签名计算测试")
    print("="*60)

    # 生成时间戳
    dt = datetime.now(timezone.utc)
    timestamp = dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    # 构造签名字符串（REST API）
    request_path = "/api/v5/account/balance"
    body = ""
    message = f"{timestamp}GET{request_path}{body}"

    print(f"时间戳: {timestamp}")
    print(f"请求方法: GET")
    print(f"请求路径: {request_path}")
    print(f"请求体: '{body}'")
    print(f"签名字符串: {message}")
    print(f"签名字符串长度: {len(message)}")

    # 计算签名
    mac = hmac.new(
        bytes(secret_key, encoding='utf-8'),
        bytes(message, encoding='utf-8'),
        digestmod=hashlib.sha256
    )
    sign = base64.b64encode(mac.digest()).decode('utf-8')

    print(f"签名结果: {sign}")
    print(f"签名长度: {len(sign)}")

    return timestamp, sign


def check_env_config():
    """检查环境配置"""
    print("\n" + "="*60)
    print("🔧 环境配置检查")
    print("="*60)

    config_keys = [
        ('OKX_DEMO_API_KEY', 'API Key'),
        ('OKX_DEMO_SECRET', 'Secret Key'),  # ← 修复：使用 OKX_DEMO_SECRET 而不是 OKX_DEMO_SECRET_KEY
        ('OKX_DEMO_PASSPHRASE', 'Passphrase'),
    ]

    issues = []

    for env_key, display_name in config_keys:
        value = os.getenv(env_key)
        if value is None:
            issues.append(f"❌ {display_name} ({env_key}) 未设置")
        elif len(value) == 0:
            issues.append(f"❌ {display_name} ({env_key}) 为空字符串")
        elif value.startswith(' ') or value.endswith(' '):
            issues.append(f"⚠️  {display_name} ({env_key}) 包含前后空格")
        else:
            # 检查是否有隐藏字符
            print(f"✅ {display_name}: {value[:10]}... (长度: {len(value)})")

    if issues:
        print("\n" + "="*60)
        print("⚠️  发现配置问题：")
        print("="*60)
        for issue in issues:
            print(issue)
    else:
        print("\n✅ 所有配置项都正确设置")


def main():
    """主函数"""
    print("\n" + "="*60)
    print("🔍 OKX API 鉴权诊断工具")
    print("="*60)

    # 1. 检查环境配置
    check_env_config()

    # 2. 测试时间戳生成
    test_timestamp_generation()

    # 3. 测试签名计算
    api_key = os.getenv('OKX_DEMO_API_KEY')
    secret_key = os.getenv('OKX_DEMO_SECRET')  # ← 修复：使用 OKX_DEMO_SECRET
    passphrase = os.getenv('OKX_DEMO_PASSPHRASE')

    if api_key and secret_key and passphrase:
        print("\n" + "="*60)
        print("🔐 签名计算测试（REST API）")
        print("="*60)
        test_signature(api_key, secret_key, passphrase)

        print("\n" + "="*60)
        print("🔐 签名计算测试（WebSocket）")
        print("="*60)

        # WebSocket 签名
        dt = datetime.now(timezone.utc)
        timestamp = dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        ws_message = f"{timestamp}GET/users/self/verify"

        print(f"时间戳: {timestamp}")
        print(f"请求方法: GET")
        print(f"请求路径: /users/self/verify")
        print(f"签名字符串: {ws_message}")
        print(f"签名字符串长度: {len(ws_message)}")

        mac = hmac.new(
            bytes(secret_key, encoding='utf-8'),
            bytes(ws_message, encoding='utf-8'),
            digestmod=hashlib.sha256
        )
        sign = base64.b64encode(mac.digest()).decode('utf-8')

        print(f"签名结果: {sign}")
        print(f"签名长度: {len(sign)}")

    else:
        print("\n" + "="*60)
        print("❌ 缺少必要的环境变量，无法测试签名")
        print("="*60)

    # 4. 建议
    print("\n" + "="*60)
    print("💡 诊断建议")
    print("="*60)
    print("""
如果遇到鉴权问题，请检查：

1. API Key、Secret Key、Passphrase 是否正确
2. 是否使用了生产环境的 Key 连接模拟盘（或反之）
3. 系统时间是否与 UTC 时间同步
4. 环境变量文件中是否有特殊字符或空格

详细的调试日志：
- 启动 HFT 程序时，查看日志中的 🔐 [签名计算] 和 🔐 [签名结果]
- 对比时间戳、签名字符串、签名结果是否符合预期
""")

    print("="*60)
    print("✅ 诊断完成")
    print("="*60)


if __name__ == "__main__":
    main()
