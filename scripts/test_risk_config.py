"""
风险比例配置测试脚本

验证单笔风险比例（Lower Risk %）配置是否正确工作。
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

from src.config.risk_config import RiskConfig, DEFAULT_RISK_CONFIG
from src.utils.logger import setup_logging, get_logger

logger = get_logger(__name__)


def test_risk_config():
    """测试风险配置"""

    print("=" * 70)
    print("🔬 风险比例配置测试")
    print("=" * 70)

    # 加载环境变量
    env_file = PROJECT_ROOT / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✅ 已加载环境变量: {env_file}\n")
    else:
        print(f"⚠️  未找到 .env 文件: {env_file}\n")

    # 测试场景
    print("=" * 70)
    print("📊 测试场景 1: 默认配置")
    print("=" * 70)

    default_config = DEFAULT_RISK_CONFIG
    print(f"默认风险比例: {default_config.RISK_PER_TRADE_PCT * 100:.2f}%")
    print(f"说明: 每笔交易风险不超过总资金的 {default_config.RISK_PER_TRADE_PCT * 100:.2f}%")

    # 模拟仓位计算
    total_capital = 10000.0
    risk_amount = total_capital * default_config.RISK_PER_TRADE_PCT
    price_distance = 1.55  # 假设止损价差
    quantity = risk_amount / price_distance

    print(f"\n模拟仓位计算:")
    print(f"  总资金: {total_capital:,.0f} USDT")
    print(f"  风险金额: {risk_amount:,.2f} USDT ({default_config.RISK_PER_TRADE_PCT * 100:.2f}%)")
    print(f"  止损价差: {price_distance:.2f} USDT")
    print(f"  计算仓位: {quantity:.2f} 个合约")

    # 测试场景 2: 自定义配置
    print("\n" + "=" * 70)
    print("📊 测试场景 2: 自定义配置（0.5%）")
    print("=" * 70)

    custom_config = RiskConfig(RISK_PER_TRADE_PCT=0.005)
    print(f"自定义风险比例: {custom_config.RISK_PER_TRADE_PCT * 100:.2f}%")
    print(f"说明: 每笔交易风险不超过总资金的 {custom_config.RISK_PER_TRADE_PCT * 100:.2f}%")

    # 模拟仓位计算
    risk_amount = total_capital * custom_config.RISK_PER_TRADE_PCT
    quantity = risk_amount / price_distance

    print(f"\n模拟仓位计算:")
    print(f"  总资金: {total_capital:,.0f} USDT")
    print(f"  风险金额: {risk_amount:,.2f} USDT ({custom_config.RISK_PER_TRADE_PCT * 100:.2f}%)")
    print(f"  止损价差: {price_distance:.2f} USDT")
    print(f"  计算仓位: {quantity:.2f} 个合约")
    print(f"  对比默认配置: 减少了 {(DEFAULT_RISK_CONFIG.RISK_PER_TRADE_PCT / custom_config.RISK_PER_TRADE_PCT - 1) * 100:.1f}%")

    # 测试场景 3: 激进配置
    print("\n" + "=" * 70)
    print("📊 测试场景 3: 激进配置（2%）")
    print("=" * 70)

    aggressive_config = RiskConfig(RISK_PER_TRADE_PCT=0.02)
    print(f"激进风险比例: {aggressive_config.RISK_PER_TRADE_PCT * 100:.2f}%")
    print(f"说明: 每笔交易风险不超过总资金的 {aggressive_config.RISK_PER_TRADE_PCT * 100:.2f}%")

    # 模拟仓位计算
    risk_amount = total_capital * aggressive_config.RISK_PER_TRADE_PCT
    quantity = risk_amount / price_distance

    print(f"\n模拟仓位计算:")
    print(f"  总资金: {total_capital:,.0f} USDT")
    print(f"  风险金额: {risk_amount:,.2f} USDT ({aggressive_config.RISK_PER_TRADE_PCT * 100:.2f}%)")
    print(f"  止损价差: {price_distance:.2f} USDT")
    print(f"  计算仓位: {quantity:.2f} 个合约")
    print(f"  对比默认配置: 增加了 {(aggressive_config.RISK_PER_TRADE_PCT / DEFAULT_RISK_CONFIG.RISK_PER_TRADE_PCT - 1) * 100:.1f}%")

    # 测试场景 4: 读取环境变量
    print("\n" + "=" * 70)
    print("📊 测试场景 4: 环境变量配置")
    print("=" * 70)

    env_risk_pct = os.getenv("RISK_PER_TRADE_PCT")

    if env_risk_pct:
        risk_value = float(env_risk_pct)
        print(f"✅ 环境变量已设置: RISK_PER_TRADE_PCT={env_risk_pct}")
        print(f"风险比例: {risk_value * 100:.2f}%")

        # 模拟仓位计算
        risk_amount = total_capital * risk_value
        quantity = risk_amount / price_distance

        print(f"\n模拟仓位计算:")
        print(f"  总资金: {total_capital:,.0f} USDT")
        print(f"  风险金额: {risk_amount:,.2f} USDT ({risk_value * 100:.2f}%)")
        print(f"  止损价差: {price_distance:.2f} USDT")
        print(f"  计算仓位: {quantity:.2f} 个合约")

        # 验证配置合理性
        if risk_value < 0.005:
            print(f"\n⚠️  警告: 风险比例过低 ({risk_value * 100:.2f}%)")
            print(f"   建议: 保守型交易者使用 0.5-1.0%，普通交易者使用 1-2%")
        elif risk_value > 0.02:
            print(f"\n⚠️  警告: 风险比例过高 ({risk_value * 100:.2f}%)")
            print(f"   建议: 激进型交易者使用 1.5-2%，超过 2% 属于高风险")
        else:
            print(f"\n✅ 风险比例合理 ({risk_value * 100:.2f}%)")
    else:
        print(f"⚠️  环境变量未设置: RISK_PER_TRADE_PCT")
        print(f"将使用默认值: {DEFAULT_RISK_CONFIG.RISK_PER_TRADE_PCT * 100:.2f}%")
        print(f"\n💡 如需自定义，在 .env 中设置:")
        print(f"   RISK_PER_TRADE_PCT=0.005  # 0.5% (保守)")
        print(f"   RISK_PER_TRADE_PCT=0.01   # 1.0% (默认)")
        print(f"   RISK_PER_TRADE_PCT=0.02   # 2.0% (激进)")

    # 配置建议
    print("\n" + "=" * 70)
    print("💡 配置建议")
    print("=" * 70)

    print("""
风险比例（Lower Risk %）选择指南：

1. 新手/保守型 (0.5% - 1.0%)
   - 优点: 风险可控，适合学习和测试
   - 缺点: 收益较慢，可能错过机会
   - 适用: 刚开始实盘，资金较少

2. 普通/平衡型 (1.0% - 1.5%)
   - 优点: 风险收益平衡
   - 缺点: 需要一定的交易经验
   - 适用: 有一定经验，追求稳定增长

3. 激进型 (1.5% - 2.0%)
   - 优点: 收益较高
   - 缺点: 回撤较大，需要严格止损
   - 适用: 经验丰富，能承受较大波动

4. 极端风险 (> 2.0%)
   - 警告: 不建议！可能导致爆仓
   - 适用: 仅限专业交易员，且有完善的风控体系
    """)

    print("=" * 70)
    print("✅ 测试完成")
    print("=" * 70)


if __name__ == '__main__':
    setup_logging('INFO')
    test_risk_config()
