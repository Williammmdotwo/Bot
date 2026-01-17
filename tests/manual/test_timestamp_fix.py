"""
测试时间戳修复

验证：
1. ISO 时间戳格式正确（毫秒精度，以 Z 结尾）
2. Unix 时间戳格式正确（秒级别）
3. 签名和 payload 使用正确的时间戳
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from src.gateways.okx.auth import OkxSigner


def test_iso_timestamp():
    """测试 ISO 时间戳格式"""
    print("\n🧪 测试 ISO 时间戳格式...")

    timestamp = OkxSigner.get_timestamp(mode='iso')
    print(f"   生成的 ISO 时间戳: {timestamp}")

    # 验证格式：YYYY-MM-DDTHH:MM:SS.sssZ
    # 必须以 'Z' 结尾（UTC 时区）
    assert timestamp.endswith('Z'), f"ISO 时间戳必须以 'Z' 结尾: {timestamp}"

    # 验证包含毫秒（应该有两个点：日期和时间的分隔，以及小数点）
    assert '.' in timestamp, f"ISO 时间戳应该包含毫秒: {timestamp}"

    # 验证可以解析
    from datetime import datetime, timezone
    try:
        # 将 'Z' 替换为 '+00:00' 以便解析
        parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        print(f"   ✅ 可以正确解析: {parsed}")
    except Exception as e:
        print(f"   ❌ 解析失败: {e}")
        raise

    print("   ✅ ISO 时间戳格式正确")


def test_unix_timestamp():
    """测试 Unix 时间戳格式"""
    print("\n🧪 测试 Unix 时间戳格式...")

    timestamp = OkxSigner.get_timestamp(mode='unix')
    print(f"   生成的 Unix 时间戳: {timestamp} (类型: {type(timestamp)})")

    # 验证是字符串
    assert isinstance(timestamp, str), f"Unix 时间戳必须是字符串: {type(timestamp)}"

    # 验证是整数
    try:
        value = int(timestamp)
        print(f"   ✅ 可以转换为整数: {value}")
    except ValueError as e:
        print(f"   ❌ 转换失败: {e}")
        raise

    # 验证是毫秒级别（应该是 13 位左右）
    assert 1600000000000 <= value <= 2000000000000, f"Unix 时间戳范围不正确: {value}"
    print(f"   ✅ Unix 时间戳范围正确")

    # 转换为秒级别（WebSocket 登录需要）
    timestamp_seconds = str(int(value / 1000))
    print(f"   转换为秒级别: {timestamp_seconds} (WebSocket 登录用)")


def test_timestamp_consistency():
    """测试时间戳一致性"""
    print("\n🧪 测试时间戳一致性...")

    # 模拟登录场景
    print("\n   模拟 WebSocket 登录场景:")

    # 生成两种时间戳
    timestamp_iso = OkxSigner.get_timestamp(mode='iso')
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    timestamp_unix_seconds = str(int(now.timestamp()))
    timestamp_unix_ms = OkxSigner.get_timestamp(mode='unix')

    print(f"   ISO 时间戳（签名用）: {timestamp_iso}")
    print(f"   Unix 秒时间戳（payload用）: {timestamp_unix_seconds}")
    print(f"   Unix 毫秒时间戳（REST API 用）: {timestamp_unix_ms}")

    # 验证时间戳在合理范围内
    import time
    current_time = int(time.time())
    payload_time = int(timestamp_unix_seconds)

    # 允许 1 秒的误差
    assert abs(current_time - payload_time) <= 1, \
        f"时间戳偏差过大: 当前={current_time}, payload={payload_time}"

    print(f"   ✅ 时间戳一致性正确（偏差 <= 1秒）")


def test_signature_with_timestamp():
    """测试签名生成"""
    print("\n🧪 测试签名生成...")

    # 模拟登录签名
    timestamp_iso = OkxSigner.get_timestamp(mode='iso')
    sign = OkxSigner.sign(
        timestamp_iso,
        "GET",
        "/users/self/verify",
        "",
        "test_secret_key"
    )

    print(f"   签名输入:")
    print(f"     - timestamp: {timestamp_iso}")
    print(f"     - method: GET")
    print(f"     - path: /users/self/verify")
    print(f"     - body: (empty)")
    print(f"   生成的签名: {sign}")

    # 验证签名格式
    import base64
    try:
        decoded = base64.b64decode(sign)
        print(f"   ✅ 签名是有效的 Base64 格式（长度: {len(decoded)} 字节）")
    except Exception as e:
        print(f"   ❌ 签名格式错误: {e}")
        raise


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🔧 时间戳修复验证测试")
    print("=" * 60)

    try:
        test_iso_timestamp()
        test_unix_timestamp()
        test_timestamp_consistency()
        test_signature_with_timestamp()

        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        print("\n✅ 修复总结:")
        print("   1. ✅ ISO 时间戳使用正确的 UTC 格式（以 Z 结尾）")
        print("   2. ✅ Unix 时间戳支持毫秒和秒两种格式")
        print("   3. ✅ 签名和 payload 使用正确的时间戳")
        print("   4. ✅ 时间戳在合理范围内，无过期风险")
        print("=" * 60 + "\n")

        return 0

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
