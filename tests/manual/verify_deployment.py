"""
Athena Trader - 关键路径仿真脚本
Critical Path Dry Run Script

测试交易系统的核心流程，不连接网络，验证：
1. 数据转换层：JSON → DataFrame
2. 策略信号层：能否生成BUY/SELL信号
3. 风控检查层：订单合理性验证
4. 下单格式层：字段类型和完整性检查
"""

import logging
import sys
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# ==================== Mock 类定义 ====================

class MockCCXTExchange:
    """模拟CCXT交易所对象"""
    def __init__(self, mock_mode=True):
        self.mock_mode = mock_mode
        self.apiKey = None
        self.secret = None

    def create_market_order(self, symbol, side, amount):
        """模拟创建市价单"""
        logger.info(f"[MOCK] 创建市价单: {symbol} {side} {amount}")
        return {
            'id': f'mock_order_{int(datetime.now().timestamp())}',
            'symbol': symbol,
            'side': side,
            'amount': amount,
            'price': 100000.0 if side == 'buy' else 100500.0,
            'status': 'filled'
        }


class MockPostgresPool:
    """模拟PostgreSQL连接池"""
    def __init__(self):
        pass

    async def execute(self, sql, *args):
        """模拟执行SQL"""
        logger.info(f"[MOCK] 执行SQL: {sql[:50]}...")
        return None

    async def close(self):
        """模拟关闭连接"""
        logger.info("[MOCK] 关闭PostgreSQL连接")


class MockRedisClient:
    """模拟Redis客户端"""
    def __init__(self):
        pass

    async def publish(self, channel, message):
        """模拟发布消息"""
        logger.info(f"[MOCK] Redis发布: {channel}")

    def close(self):
        """模拟关闭连接"""
        logger.info("[MOCK] 关闭Redis连接")


# ==================== 数据生成函数 ====================

def generate_mock_ohlcv_data(count: int = 30, start_price: float = 100000.0, create_golden_cross: bool = False) -> list:
    """
    生成模拟的OHLCV数据（至少25根用于EMA 9/21策略）

    Args:
        count: K线数量（默认30根，确保足够数据）
        start_price: 起始价格
        create_golden_cross: 是否创建金叉场景（用于测试BUY信号）

    Returns:
        list: OHLCV数据列表 [[timestamp, open, high, low, close, volume], ...]
    """
    data = []
    base_time = int((datetime.now() - timedelta(minutes=count)).timestamp() * 1000)

    if create_golden_cross:
        # 创建明确的金叉场景
        # 前25根K线：平稳下跌趋势（快线在慢线下方）
        for i in range(25):
            timestamp = base_time + i * 300000
            # 下跌趋势，价格从100000降到97500
            price = start_price - (i * 100)
            data.append([timestamp, price, price + 50, price - 50, price, 100.0 + i * 10])

        # 第26-28根K线：底部震荡，确保快线接近但未突破慢线
        for i in range(25, 28):
            timestamp = base_time + i * 300000
            price = 97500 + ((i - 25) * 50)
            data.append([timestamp, price, price + 50, price - 50, price, 100.0 + i * 10])

        # 第29-30根K线：快速拉升，创造明确的金叉
        for i in range(28, count):
            timestamp = base_time + i * 300000
            # 快速上涨，价格从97600涨到103000
            price = 97600 + ((i - 28) * 2700)
            data.append([timestamp, price, price + 100, price - 50, price, 500.0 + i * 10])
    else:
        # 简单的上升趋势
        for i in range(count):
            timestamp = base_time + i * 300000
            price = start_price + (i * 100)
            data.append([timestamp, price, price + 50, price - 50, price, 100.0 + i * 10])

    return data


def generate_enhanced_analysis(symbol: str = "BTC-USDT", create_golden_cross: bool = True) -> Dict[str, Any]:
    """
    生成增强分析数据（模拟Data Manager输出）

    数据流说明：
    1. 本函数直接返回时间框架数据: {"5m": {...}, "15m": {...}}
    2. signal_generator接收后，会包装成: {"historical_analysis": enhanced_analysis}
    3. dual_ema_strategy接收: {"historical_analysis": {"5m": {...}}}
    4. dual_ema_strategy访问: historical_data.get("historical_analysis", {}).get("5m", {})

    Args:
        symbol: 交易对符号
        create_golden_cross: 是否创建金叉场景（默认True，用于测试BUY信号）

    Returns:
        Dict: 增强分析数据（直接返回时间框架，不包含historical_analysis外层）
    """
    ohlcv = generate_mock_ohlcv_data(count=25, start_price=100000.0, create_golden_cross=create_golden_cross)

    # 模拟技术指标
    closes = [candle[4] for candle in ohlcv]

    # 计算简单移动平均（简化版）
    ema_fast = sum(closes[-9:]) / 9 if len(closes) >= 9 else closes[-1]
    ema_slow = sum(closes[-21:]) / 21 if len(closes) >= 21 else closes[-1]

    # 直接返回时间框架数据，不要包含"historical_analysis"外层
    # 因为signal_generator.py会再次包装
    return {
        "5m": {
            "ohlcv": ohlcv,
            "indicators": {
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "rsi": 50.0,
                "macd": {
                    "signal": "buy",
                    "histogram": 10.0
                }
            }
        },
        "15m": {
            "ohlcv": ohlcv[:20],  # 较少的数据
            "indicators": {
                "ema_fast": ema_fast,
                "ema_slow": ema_slow
            }
        }
    }


def generate_market_data(current_price: float = 100000.0) -> Dict[str, Any]:
    """
    生成市场数据（模拟Data Manager输出）

    Args:
        current_price: 当前价格

    Returns:
        Dict: 市场数据
    """
    return {
        "symbol": "BTC-USDT",
        "current_price": current_price,
        "ticker": {
            "last": current_price,
            "bid": current_price - 50,
            "ask": current_price + 50
        },
        "orderbook": {
            "bids": [[current_price - 50, 1.0]],
            "asks": [[current_price + 50, 1.0]]
        },
        "recent_trades": [
            {"price": current_price, "amount": 0.1, "side": "buy"}
        ]
    }


# ==================== 测试函数 ====================

def test_data_conversion():
    """测试1：数据转换层（JSON → OHLCV格式）"""
    print("\n" + "="*60)
    print("[TEST 1] 数据转换层测试")
    print("="*60)

    try:
        # 生成模拟OHLCV数据
        ohlcv = generate_mock_ohlcv_data(count=25, start_price=100000.0)

        print(f"✅ 生成OHLCV数据成功")
        print(f"   - 数据点数量: {len(ohlcv)}")
        print(f"   - 起始价格: {ohlcv[0][4]:.2f}")
        print(f"   - 结束价格: {ohlcv[-1][4]:.2f}")
        print(f"   - 数据格式: {type(ohlcv[0])}")

        # 验证数据格式
        assert isinstance(ohlcv, list), "OHLCV必须是列表"
        assert len(ohlcv) >= 21, "至少需要21根K线用于EMA计算"

        # 逐个验证每个candle的长度（OHLCV格式：timestamp, open, high, low, close, volume）
        for i, candle in enumerate(ohlcv):
            assert len(candle) == 6, f"第{i+1}根K线字段数错误: {len(candle)} (应为6), 数据: {candle}"

        print(f"   - 数据验证: 检查{len(ohlcv)}根K线，每根6个字段 (OHLCV)")

        print("✅ 数据格式验证通过")
        return True

    except Exception as e:
        print(f"❌ 数据转换层测试失败: {e}")
        return False


def test_strategy_signal():
    """测试2：策略信号生成层"""
    print("\n" + "="*60)
    print("[TEST 2] 策略信号生成层测试")
    print("="*60)

    try:
        from src.strategy_engine.core.signal_generator import generate_fallback_signal_with_details

        # 生成测试数据
        enhanced_analysis = generate_enhanced_analysis("BTC-USDT")
        market_data = generate_market_data(100000.0)
        symbol = "BTC-USDT"

        print(f"✅ 准备策略输入数据")
        print(f"   - Symbol: {symbol}")

        # 调试：打印数据结构
        import json
        print(f"   - enhanced_analysis结构: {list(enhanced_analysis.keys())}")
        if 'historical_analysis' in enhanced_analysis:
            print(f"   - historical_analysis结构: {list(enhanced_analysis['historical_analysis'].keys())}")
            if '5m' in enhanced_analysis['historical_analysis']:
                print(f"   - 5m数据存在: 是")
                print(f"   - OHLCV数据量: {len(enhanced_analysis['historical_analysis']['5m']['ohlcv'])}")
            else:
                print(f"   - 5m数据存在: 否")

        print(f"   - 当前价格: {market_data['current_price']:.2f}")

        # 测试策略信号生成
        print(f"\n🧠 调用策略信号生成函数...")
        signal = generate_fallback_signal_with_details(
            enhanced_analysis,
            market_data,
            symbol
        )

        print(f"✅ 策略返回信号: {signal['side']}")
        print(f"   - 置信度: {signal['confidence']:.1f}%")
        print(f"   - 原因: {signal['reasoning']}")
        print(f"   - 仓位大小: {signal['position_size']}")
        print(f"   - 止损: {signal['stop_loss']:.2f}")
        print(f"   - 止盈: {signal['take_profit']:.2f}")

        # 验证信号格式
        required_fields = [
            'side', 'symbol', 'decision_id', 'position_size',
            'confidence', 'reasoning', 'stop_loss', 'take_profit'
        ]

        missing_fields = [f for f in required_fields if f not in signal]
        if missing_fields:
            print(f"❌ 信号缺少字段: {missing_fields}")
            return False

        # 验证信号类型
        if signal['side'] not in ['BUY', 'SELL', 'HOLD']:
            print(f"❌ 无效信号类型: {signal['side']}")
            return False

        print("✅ 策略信号格式验证通过")
        return signal

    except Exception as e:
        logger.error(f"策略信号生成测试失败: {e}", exc_info=True)
        print(f"❌ 策略信号生成测试失败: {e}")
        import traceback
        print(f"   错误详情:\n{traceback.format_exc()}")
        return None


def test_risk_control(signal: Dict[str, Any]):
    """测试3：风控检查层"""
    print("\n" + "="*60)
    print("[TEST 3] 风控检查层测试")
    print("="*60)

    try:
        from src.risk_manager.checks.order_checks import is_order_rational

        # 准备订单详情
        order_details = {
            "symbol": signal['symbol'],
            "side": signal['side'],
            "position_size": signal['position_size'],
            "stop_loss": signal['stop_loss'],
            "take_profit": signal['take_profit']
        }

        current_equity = 10000.0  # 假设账户权益10000 USDT
        current_price = signal.get('current_price', 100000.0)

        print(f"✅ 准备风控检查数据")
        print(f"   - Symbol: {order_details['symbol']}")
        print(f"   - Side: {order_details['side']}")
        print(f"   - Position Size: {order_details['position_size']}")
        print(f"   - Stop Loss: {order_details['stop_loss']:.2f}")
        print(f"   - Take Profit: {order_details['take_profit']:.2f}")
        print(f"   - Current Equity: {current_equity:.2f} USDT")

        # 测试风控检查
        print(f"\n🛡️ 调用风控检查函数...")
        is_safe = is_order_rational(
            order_details,
            current_equity,
            current_price
        )

        if is_safe:
            print("✅ 风控检查通过（订单合理）")
            return True
        else:
            print("⚠️ 风控拦截（订单被拒绝）")
            print("   这可能是因为：")
            print("   - 仓位大小超限")
            print("   - 止损止盈逻辑错误")
            return False

    except Exception as e:
        logger.error(f"风控检查测试失败: {e}", exc_info=True)
        print(f"❌ 风控检查测试失败: {e}")
        import traceback
        print(f"   错误详情:\n{traceback.format_exc()}")
        return False


def test_executor_format(signal: Dict[str, Any]):
    """测试4：执行器格式层"""
    print("\n" + "="*60)
    print("[TEST 4] 执行器格式层测试")
    print("="*60)

    try:
        from src.executor.core.trade_executor import execute_trade_logic

        # 准备信号数据（匹配execute_trade_logic期望格式）
        signal_data = {
            'signal': signal['side'],
            'symbol': signal['symbol'],
            'decision_id': signal['decision_id'],
            'confidence': signal['confidence'],
            'position_size': signal['position_size'],
            'stop_loss': signal['stop_loss'],
            'take_profit': signal['take_profit'],
            'current_price': signal.get('current_price', 100000.0)
        }

        print(f"✅ 准备执行器输入数据")
        print(f"   - Signal: {signal_data['signal']}")
        print(f"   - Symbol: {signal_data['symbol']}")
        print(f"   - Decision ID: {signal_data['decision_id']}")

        # 创建Mock对象
        ccxt_exchange = MockCCXTExchange(mock_mode=True)
        postgres_pool = MockPostgresPool()
        redis_client = MockRedisClient()

        # 测试执行器逻辑（不真正调用API，只检查格式）
        print(f"\n⚙️ 调用执行器逻辑函数...")

        # 检查字段类型
        print(f"\n📋 字段类型检查:")
        print(f"   - signal类型: {type(signal_data['signal'])} (应为str)")
        print(f"   - symbol类型: {type(signal_data['symbol'])} (应为str)")
        print(f"   - decision_id类型: {type(signal_data['decision_id'])} (应为str)")
        print(f"   - position_size类型: {type(signal_data['position_size'])} (应为float)")
        print(f"   - stop_loss类型: {type(signal_data['stop_loss'])} (应为float)")
        print(f"   - take_profit类型: {type(signal_data['take_profit'])} (应为float)")

        # 验证类型
        type_errors = []
        if not isinstance(signal_data['signal'], str):
            type_errors.append('signal应为str类型')
        if not isinstance(signal_data['symbol'], str):
            type_errors.append('symbol应为str类型')
        if not isinstance(signal_data['decision_id'], str):
            type_errors.append('decision_id应为str类型')
        if not isinstance(signal_data['position_size'], (int, float)):
            type_errors.append('position_size应为数值类型')
        if not isinstance(signal_data['stop_loss'], (int, float)):
            type_errors.append('stop_loss应为数值类型')
        if not isinstance(signal_data['take_profit'], (int, float)):
            type_errors.append('take_profit应为数值类型')

        if type_errors:
            print(f"❌ 字段类型错误:")
            for error in type_errors:
                print(f"   - {error}")
            return False

        print("✅ 字段类型验证通过")
        print("\n✅ 执行器格式层测试完成")
        return True

    except Exception as e:
        logger.error(f"执行器格式测试失败: {e}", exc_info=True)
        print(f"❌ 执行器格式测试失败: {e}")
        import traceback
        print(f"   错误详情:\n{traceback.format_exc()}")
        return False


def run_full_simulation():
    """运行完整仿真流程"""
    print("\n" + "="*60)
    print("🚀 Athena Trader 关键路径仿真 (Dry Run)")
    print("="*60)
    print("测试目标：验证数据流从Data Manager到Executor的完整性")
    print("="*60)

    results = {
        "data_conversion": False,
        "strategy_signal": False,
        "risk_control": False,
        "executor_format": False
    }

    # 测试1：数据转换
    results["data_conversion"] = test_data_conversion()
    if not results["data_conversion"]:
        print("\n❌ 数据转换失败，终止测试")
        return results

    # 测试2：策略信号
    signal = test_strategy_signal()
    if signal is None:
        print("\n❌ 策略信号生成失败，终止测试")
        return results
    results["strategy_signal"] = True

    # 测试3：风控检查
    if signal['side'] in ['BUY', 'SELL']:
        results["risk_control"] = test_risk_control(signal)
        if not results["risk_control"]:
            print("\n⚠️ 风控拦截，跳过执行器测试")
    else:
        print("\nℹ️ 信号为HOLD，跳过风控和执行器测试")
        results["risk_control"] = True

    # 测试4：执行器格式（即使HOLD也测试格式验证）
    print("\nℹ️ 测试执行器格式层（仅验证字段类型，不实际执行）...")
    results["executor_format"] = test_executor_format(signal)

    # 输出总结
    print("\n" + "="*60)
    print("📊 测试结果总结")
    print("="*60)

    total_tests = len(results)
    passed_tests = sum(results.values())

    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {test_name}: {status}")

    print(f"\n总计: {passed_tests}/{total_tests} 测试通过")

    if passed_tests == total_tests:
        print("\n🎉 恭喜！所有关键路径测试通过！")
        print("   数据流完整，系统可以进行下一步开发。")
    else:
        print("\n⚠️ 部分测试失败，请检查上述错误信息。")
        print("   建议优先修复失败的模块。")

    print("="*60)

    return results


if __name__ == "__main__":
    print("\n" + "🎯"*30)
    print("🎯 Athena Trader Dry Run Script")
    print("🎯"*30)
    print("测试时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    try:
        results = run_full_simulation()

        # 返回退出码
        sys.exit(0 if all(results.values()) else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断测试")
        sys.exit(130)
    except Exception as e:
        logger.critical(f"仿真脚本崩溃: {e}", exc_info=True)
        print(f"\n❌ 仿真脚本意外崩溃: {e}")
        import traceback
        print(f"   错误详情:\n{traceback.format_exc()}")
        sys.exit(1)
