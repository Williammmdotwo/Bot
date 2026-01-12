"""
配置验证脚本

验证系统配置是否一致，检查是否存在"精神分裂"问题。

检查项：
1. 网关交易对配置
2. 策略交易对配置
3. 配置一致性
"""

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

def verify_config():
    """验证配置一致性"""

    print("=" * 70)
    print("🔍 Athena OS 配置验证")
    print("=" * 70)

    # 加载环境变量
    env_file = PROJECT_ROOT / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✅ 已加载环境变量: {env_file}\n")
    else:
        print(f"⚠️  未找到 .env 文件: {env_file}\n")

    # 获取关键配置
    active_strategy = os.getenv('ACTIVE_STRATEGY', 'NOT SET')
    trading_symbol = os.getenv('TRADING_SYMBOL', 'NOT SET')
    scalper_symbol = os.getenv('SCALPER_SYMBOL', 'NOT SET')

    print(f"📊 当前激活策略: {active_strategy}")
    print(f"📊 TRADING_SYMBOL (网关): {trading_symbol}")
    print(f"📊 SCALPER_SYMBOL (策略): {scalper_symbol}")
    print()

    # 验证逻辑
    print("=" * 70)
    print("🔧 配置验证")
    print("=" * 70)

    issues = []
    warnings = []

    # 1. 检查是否设置了交易对
    if trading_symbol == 'NOT SET' and scalper_symbol == 'NOT SET':
        issues.append("❌ 严重问题: 未设置任何交易对环境变量 (TRADING_SYMBOL 或 SCALPER_SYMBOL)")
    elif scalper_symbol == 'NOT SET' and active_strategy == 'scalper_v1':
        issues.append(f"❌ 严重问题: ScalperV1 策略需要 SCALPER_SYMBOL，但未设置")

    # 2. 检查配置一致性
    if trading_symbol != 'NOT SET' and scalper_symbol != 'NOT SET':
        if trading_symbol != scalper_symbol:
            issues.append(
                f"❌ 严重问题: 配置不一致!\n"
                f"   网关 (TRADING_SYMBOL): {trading_symbol}\n"
                f"   策略 (SCALPER_SYMBOL): {scalper_symbol}\n"
                f"   这会导致网关和策略监听不同的交易对!"
            )
        else:
            print(f"✅ 配置一致: 网关和策略都使用 {trading_symbol}")

    # 3. 检查策略配置
    if active_strategy == 'scalper_v1':
        if scalper_symbol != 'NOT SET':
            print(f"✅ ScalperV1 策略交易对: {scalper_symbol}")
        else:
            issues.append("❌ ScalperV1 策略未配置交易对")
    elif active_strategy == 'sniper':
        if trading_symbol != 'NOT SET':
            print(f"✅ Sniper 策略交易对: {trading_symbol}")
        else:
            warnings.append("⚠️  Sniper 策略将使用默认交易对 (BTC-USDT-SWAP)")

    # 4. 检查修复后的逻辑
    print()
    print("=" * 70)
    print("🔍 修复后逻辑验证")
    print("=" * 70)

    # 模拟 main.py 中的逻辑
    print("\n📌 网关配置逻辑:")
    print("   1. 优先使用 SCALPER_SYMBOL")
    print("   2. 如果不存在，使用 TRADING_SYMBOL")
    print("   3. 如果都不存在，使用默认值 BTC-USDT-SWAP")

    final_symbol = os.getenv('SCALPER_SYMBOL') or os.getenv('TRADING_SYMBOL') or 'BTC-USDT-SWAP'

    print(f"\n   🔧 最终网关交易对: {final_symbol}")

    if final_symbol == scalper_symbol:
        print(f"   ✅ 网关和策略一致: {final_symbol}")
    elif final_symbol != 'BTC-USDT-SWAP':
        warnings.append(f"⚠️  网关使用 {final_symbol}，但策略可能使用不同的交易对")

    # 打印问题
    if issues:
        print()
        print("=" * 70)
        print("❌ 发现的问题")
        print("=" * 70)
        for issue in issues:
            print(issue)

    if warnings:
        print()
        print("=" * 70)
        print("⚠️  警告")
        print("=" * 70)
        for warning in warnings:
            print(warning)

    # 总结
    print()
    print("=" * 70)
    print("📋 总结")
    print("=" * 70)

    if not issues and not warnings:
        print("✅ 配置验证通过！系统配置正确，不存在'精神分裂'问题。")
        return True
    elif issues:
        print("❌ 发现严重问题，请修复后再运行系统！")
        return False
    else:
        print("⚠️  配置存在一些警告，建议检查。")
        return True

if __name__ == '__main__':
    success = verify_config()
    sys.exit(0 if success else 1)
