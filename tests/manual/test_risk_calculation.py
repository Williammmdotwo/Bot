"""
风控计算测试脚本

验证自适应风控计算是否正确工作。
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

from src.core.engine import create_default_config
from src.utils.logger import setup_logging, get_logger

logger = get_logger(__name__)


def test_adaptive_risk():
    """测试自适应风控计算"""

    print("=" * 70)
    print("🔬 风控计算测试")
    print("=" * 70)

    # 加载环境变量
    env_file = PROJECT_ROOT / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✅ 已加载环境变量: {env_file}\n")
    else:
        print(f"⚠️  未找到 .env 文件: {env_file}\n")

    # 模拟 main.py 中的逻辑
    config = create_default_config()

    # 资金配置
    total_capital = os.getenv('TOTAL_CAPITAL')
    if total_capital:
        config['total_capital'] = float(total_capital)

    # 获取总资金（用于自适应计算）
    total_capital_value = config.get('total_capital', 10000.0)
    print(f"💰 总资金: {total_capital_value:.2f} USDT")

    # 风控配置 - 自适应计算
    env_max_amount = os.getenv("MAX_ORDER_AMOUNT")

    if env_max_amount:
        max_order_amount = float(env_max_amount)
        print(f"🛡️  使用环境变量风控限制: {max_order_amount:.2f} USDT")
    else:
        # 自适应计算
        max_order_amount = total_capital_value * 5.0
        print(f"🛡️  自动计算风控限制 (自适应): {max_order_amount:.2f} USDT (基于资金 5x)")

    # 打印测试场景
    print("\n" + "=" * 70)
    print("📊 测试场景")
    print("=" * 70)

    scenarios = [
        (1000.0, "小资金账户"),
        (10000.0, "中等资金账户"),
        (100000.0, "大资金账户"),
    ]

    for capital, desc in scenarios:
        auto_limit = capital * 5.0
        print(f"\n{desc}:")
        print(f"  资金: {capital:,.0f} USDT")
        print(f"  自适应限额: {auto_limit:,.0f} USDT")
        print(f"  支持 5x 杠杆: ✅" if auto_limit >= capital else "  支持 5x 杠杆: ❌")

    # 检查当前配置
    print("\n" + "=" * 70)
    print("🔍 当前配置检查")
    print("=" * 70)

    strategy_capital = float(os.getenv('SCALPER_CAPITAL', 1000.0))
    print(f"\n策略资金: {strategy_capital:.2f} USDT")
    print(f"总资金: {total_capital_value:.2f} USDT")
    print(f"风控限额: {max_order_amount:.2f} USDT")

    # 计算实际下单能力
    if max_order_amount >= strategy_capital * 5:
        print(f"\n✅ 风控计算正确！")
        print(f"   策略可以开 {strategy_capital * 5:.2f} USDT 仓位 (5x 杠杆)")
        print(f"   风控限制 {max_order_amount:.2f} USDT 足够")
    else:
        print(f"\n⚠️  风控限制可能不足！")
        print(f"   策略需要: {strategy_capital * 5:.2f} USDT (5x 杠杆)")
        print(f"   风控限制: {max_order_amount:.2f} USDT")
        print(f"   缺口: {(strategy_capital * 5) - max_order_amount:.2f} USDT")

    # 检查是否设置了 MAX_ORDER_AMOUNT
    if not env_max_amount:
        print(f"\n💡 提示: 未设置 MAX_ORDER_AMOUNT，使用自适应计算")
        print(f"   如需手动控制，可在 .env 中设置: MAX_ORDER_AMOUNT=5000.0")

    print("\n" + "=" * 70)
    print("✅ 测试完成")
    print("=" * 70)


if __name__ == '__main__':
    setup_logging('INFO')
    test_adaptive_risk()
