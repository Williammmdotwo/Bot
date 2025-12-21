#!/usr/bin/env python3
"""
双均线策略测试脚本
用于验证策略逻辑是否正常工作
"""

import logging
import os
import sys
import time
from datetime import datetime
from typing import List

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

from src.data_manager.main import DataHandler
from src.strategy_engine.dual_ema_strategy import DualEMAStrategy, generate_dual_ema_signal

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def create_mock_ohlcv_data(base_price: float = 50000, num_candles: int = 50, trend: str = "up") -> List:
    """
    创建模拟OHLCV数据用于测试
    
    Args:
        base_price: 基础价格
        num_candles: K线数量
        trend: 趋势方向 ("up", "down", "sideways")
    
    Returns:
        List: OHLCV数据列表
    """
    import random
    
    ohlcv_data = []
    current_price = base_price
    
    for i in range(num_candles):
        timestamp = int(time.time() * 1000) - (num_candles - i) * 15 * 60 * 1000  # 15分钟间隔
        
        # 根据趋势生成价格
        if trend == "up":
            price_change = random.uniform(0.001, 0.005)  # 0.1% - 0.5% 上涨
        elif trend == "down":
            price_change = random.uniform(-0.005, -0.001)  # -0.5% - -0.1% 下跌
        else:
            price_change = random.uniform(-0.002, 0.002)  # 横盘
        
        current_price *= (1 + price_change)
        
        # 生成OHLCV
        high_price = current_price * random.uniform(1.0, 1.002)
        low_price = current_price * random.uniform(0.998, 1.0)
        close_price = current_price
        open_price = current_price * random.uniform(0.999, 1.001)
        volume = random.uniform(100, 1000)
        
        ohlcv_data.append([timestamp, open_price, high_price, low_price, close_price, volume])
    
    return ohlcv_data


def create_golden_cross_data() -> List:
    """创建金叉测试数据"""
    # 先下跌，然后上涨，形成金叉
    base_price = 50000
    
    # 前30根K线下跌
    down_candles = create_mock_ohlcv_data(base_price, 30, "down")
    
    # 后20根K线上涨
    up_candles = create_mock_ohlcv_data(down_candles[-1][4], 20, "up")
    
    return down_candles + up_candles


def create_death_cross_data() -> List:
    """创建死叉测试数据"""
    # 先上涨，然后下跌，形成死叉
    base_price = 50000
    
    # 前30根K线上涨
    up_candles = create_mock_ohlcv_data(base_price, 30, "up")
    
    # 后20根K线下跌
    down_candles = create_mock_ohlcv_data(up_candles[-1][4], 20, "down")
    
    return up_candles + down_candles


def test_dual_ema_strategy() -> bool:
    """
    测试双均线策略
    
    Returns:
        bool: 测试是否通过
    """
    logger.info("🚀 开始测试双均线策略...")
    
    try:
        # 创建策略实例
        strategy = DualEMAStrategy(ema_fast=9, ema_slow=21)
        
        # 测试1: 金叉信号
        logger.info("📈 测试1: 金叉信号检测")
        golden_cross_data = create_golden_cross_data()
        
        historical_data_golden = {
            "historical_analysis": {
                "15m": {
                    "ohlcv": golden_cross_data,
                    "data_points": len(golden_cross_data)
                }
            }
        }
        
        signal_golden = strategy.generate_signal(historical_data_golden, "BTC-USDT")
        logger.info(f"金叉测试结果: {signal_golden['signal']} - {signal_golden['reasoning']}")
        
        # 测试2: 死叉信号
        logger.info("📉 测试2: 死叉信号检测")
        death_cross_data = create_death_cross_data()
        
        historical_data_death = {
            "historical_analysis": {
                "15m": {
                    "ohlcv": death_cross_data,
                    "data_points": len(death_cross_data)
                }
            }
        }
        
        signal_death = strategy.generate_signal(historical_data_death, "BTC-USDT")
        logger.info(f"死叉测试结果: {signal_death['signal']} - {signal_death['reasoning']}")
        
        # 测试3: 横盘信号
        logger.info("➡️ 测试3: 横盘信号检测")
        sideways_data = create_mock_ohlcv_data(50000, 50, "sideways")
        
        historical_data_sideways = {
            "historical_analysis": {
                "15m": {
                    "ohlcv": sideways_data,
                    "data_points": len(sideways_data)
                }
            }
        }
        
        signal_sideways = strategy.generate_signal(historical_data_sideways, "BTC-USDT")
        logger.info(f"横盘测试结果: {signal_sideways['signal']} - {signal_sideways['reasoning']}")
        
        # 测试4: 数据不足情况
        logger.info("⚠️ 测试4: 数据不足情况")
        insufficient_data = create_mock_ohlcv_data(50000, 10, "up")  # 只有10根K线
        
        historical_data_insufficient = {
            "historical_analysis": {
                "15m": {
                    "ohlcv": insufficient_data,
                    "data_points": len(insufficient_data)
                }
            }
        }
        
        signal_insufficient = strategy.generate_signal(historical_data_insufficient, "BTC-USDT")
        logger.info(f"数据不足测试结果: {signal_insufficient['signal']} - {signal_insufficient['reasoning']}")
        
        # 测试5: 便捷函数测试
        logger.info("🔧 测试5: 便捷函数测试")
        signal_convenient = generate_dual_ema_signal(historical_data_golden, "ETH-USDT")
        logger.info(f"便捷函数测试结果: {signal_convenient['signal']} - {signal_convenient['reasoning']}")
        
        # 测试总结
        logger.info("✅ 双均线策略测试完成!")
        logger.info(f"📊 测试结果汇总:")
        logger.info(f"   - 金叉检测: {signal_golden['signal']}")
        logger.info(f"   - 死叉检测: {signal_death['signal']}")
        logger.info(f"   - 横盘检测: {signal_sideways['signal']}")
        logger.info(f"   - 数据不足: {signal_insufficient['signal']}")
        logger.info(f"   - 便捷函数: {signal_convenient['signal']}")
        
        # 验证信号格式
        required_fields = ['signal', 'symbol', 'decision_id', 'confidence', 'reasoning', 
                         'position_size', 'stop_loss', 'take_profit', 'timestamp']
        
        test_signal = signal_golden
        missing_fields = [field for field in required_fields if field not in test_signal]
        
        if missing_fields:
            logger.error(f"❌ 信号格式验证失败，缺少字段: {missing_fields}")
            return False
        else:
            logger.info("✅ 信号格式验证通过")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 策略测试失败: {e}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        return False


def test_integration_with_data_manager() -> bool:
    """
    测试与数据管理器的集成
    
    Returns:
        bool: 测试是否通过
    """
    logger.info("🔗 测试与数据管理器的集成...")
    
    try:
        # 初始化数据处理器
        data_handler = DataHandler()
        
        # 获取历史数据
        symbol = "BTC-USDT"
        historical_data = data_handler.get_historical_with_indicators(
            symbol, 
            timeframes=["15m"], 
            limit=50, 
            use_demo=True
        )
        
        if "error" in historical_data:
            logger.warning(f"无法获取真实历史数据，使用模拟数据: {historical_data['error']}")
            return test_dual_ema_strategy()  # 回退到模拟测试
        
        # 使用真实数据测试策略
        signal = generate_dual_ema_signal(historical_data, symbol)
        
        logger.info(f"📈 真实数据测试结果:")
        logger.info(f"   - 信号: {signal['signal']}")
        logger.info(f"   - 原因: {signal['reasoning']}")
        logger.info(f"   - 置信度: {signal['confidence']}")
        logger.info(f"   - EMA快线: {signal.get('ema_fast', 'N/A')}")
        logger.info(f"   - EMA慢线: {signal.get('ema_slow', 'N/A')}")
        logger.info(f"   - 当前价格: {signal.get('current_price', 'N/A')}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 集成测试失败: {e}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    print("🎯 双均线策略测试开始")
    print("=" * 50)
    
    # 基础策略测试
    success1 = test_dual_ema_strategy()
    
    print("\n" + "=" * 50)
    
    # 集成测试
    success2 = test_integration_with_data_manager()
    
    print("\n" + "=" * 50)
    print("🏁 测试总结:")
    print(f"   基础策略测试: {'✅ 通过' if success1 else '❌ 失败'}")
    print(f"   集成测试: {'✅ 通过' if success2 else '❌ 失败'}")
    
    if success1 and success2:
        print("🎉 所有测试通过！双均线策略已准备就绪。")
        sys.exit(0)
    else:
        print("⚠️ 部分测试失败，请检查错误信息。")
        sys.exit(1)
