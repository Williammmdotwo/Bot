#!/usr/bin/env python3
"""
专门测试EMA交叉信号的脚本
确保金叉和死叉检测逻辑正确
"""

import logging
import os
import sys
import time
from typing import List, Tuple

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

from src.data_manager.technical_indicators import TechnicalIndicators
from src.strategy_engine.dual_ema_strategy import DualEMAStrategy

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def create_perfect_golden_cross() -> List:
    """
    创建完美的金叉数据
    
    Returns:
        List: OHLCV数据列表
    """
    # 前30根K线：EMA9 < EMA21
    # 后2根K线：EMA9 > EMA21，形成交叉
    
    # 创建下跌趋势数据
    ohlcv = []
    base_price = 50000
    current_price = base_price
    
    # 前30根K线 - 下跌趋势
    for i in range(30):
        timestamp = 1700000000000 + i * 15 * 60 * 1000  # 15分钟间隔
        current_price *= 0.999  # 每根K线下跌0.1%
        
        high = current_price * 1.001
        low = current_price * 0.999
        close = current_price
        open_price = current_price * 1.0005
        volume = 1000
        
        ohlcv.append([timestamp, open_price, high, low, close, volume])
    
    # 后2根K线 - 快速上涨，确保EMA9超过EMA21
    for i in range(2):
        timestamp = 1700000000000 + (30 + i) * 15 * 60 * 1000
        current_price *= 1.01  # 每根K线上涨1%
        
        high = current_price * 1.002
        low = current_price * 0.998
        close = current_price
        open_price = current_price * 0.999
        volume = 2000  # 成交量放大
        
        ohlcv.append([timestamp, open_price, high, low, close, volume])
    
    return ohlcv


def create_perfect_death_cross() -> List:
    """
    创建完美的死叉数据
    
    Returns:
        List: OHLCV数据列表
    """
    # 前30根K线：EMA9 > EMA21
    # 后2根K线：EMA9 < EMA21，形成交叉
    
    # 创建上涨趋势数据
    ohlcv = []
    base_price = 50000
    current_price = base_price
    
    # 前30根K线 - 上涨趋势
    for i in range(30):
        timestamp = 1700000000000 + i * 15 * 60 * 1000
        current_price *= 1.001  # 每根K线上涨0.1%
        
        high = current_price * 1.002
        low = current_price * 0.999
        close = current_price
        open_price = current_price * 0.9995
        volume = 1000
        
        ohlcv.append([timestamp, open_price, high, low, close, volume])
    
    # 后2根K线 - 快速下跌，确保EMA9跌破EMA21
    for i in range(2):
        timestamp = 1700000000000 + (30 + i) * 15 * 60 * 1000
        current_price *= 0.99  # 每根K线下跌1%
        
        high = current_price * 1.001
        low = current_price * 0.998
        close = current_price
        open_price = current_price * 1.001
        volume = 2000  # 成交量放大
        
        ohlcv.append([timestamp, open_price, high, low, close, volume])
    
    return ohlcv


def test_ema_calculation() -> Tuple[float, float]:
    """
    测试EMA计算是否正确
    
    Returns:
        Tuple[float, float]: (ema_9, ema_21)
    """
    logger.info("🔬 测试EMA计算逻辑...")
    
    # 简单测试数据
    prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120]
    
    ema_9 = TechnicalIndicators.calculate_ema(prices, 9)
    ema_21 = TechnicalIndicators.calculate_ema(prices, 21)
    
    logger.info(f"测试数据长度: {len(prices)}")
    logger.info(f"EMA_9: {ema_9:.2f}")
    logger.info(f"EMA_21: {ema_21:.2f}")
    
    # 验证EMA值合理性
    if ema_9 > 100 and ema_9 < 120:
        logger.info("✅ EMA_9 计算合理")
    else:
        logger.error(f"❌ EMA_9 计算异常: {ema_9}")
    
    if ema_21 > 100 and ema_21 < 120:
        logger.info("✅ EMA_21 计算合理")
    else:
        logger.error(f"❌ EMA_21 计算异常: {ema_21}")
    
    return ema_9, ema_21


def test_perfect_crossover() -> None:
    """测试完美的交叉信号"""
    logger.info("🎯 测试完美交叉信号...")
    
    strategy = DualEMAStrategy(ema_fast=9, ema_slow=21)
    
    # 测试金叉
    logger.info("📈 测试完美金叉...")
    golden_data = create_perfect_golden_cross()
    
    # 手动计算EMA来验证
    closes = [candle[4] for candle in golden_data]
    
    # 计算最后两个时间点的EMA
    prev_closes = closes[:-1]
    curr_closes = closes[1:]  # 偏移一个位置
    
    prev_ema_9 = TechnicalIndicators.calculate_ema(prev_closes, 9)
    prev_ema_21 = TechnicalIndicators.calculate_ema(prev_closes, 21)
    curr_ema_9 = TechnicalIndicators.calculate_ema(curr_closes, 9)
    curr_ema_21 = TechnicalIndicators.calculate_ema(curr_closes, 21)
    
    logger.info(f"金叉数据验证:")
    logger.info(f"  前一时刻: EMA_9={prev_ema_9:.2f}, EMA_21={prev_ema_21:.2f}")
    logger.info(f"  当前时刻: EMA_9={curr_ema_9:.2f}, EMA_21={curr_ema_21:.2f}")
    logger.info(f"  交叉条件: {prev_ema_9 <= prev_ema_21} -> {curr_ema_9 > curr_ema_21}")
    
    # 使用策略检测
    historical_data = {
        "historical_analysis": {
            "15m": {
                "ohlcv": golden_data,
                "data_points": len(golden_data)
            }
        }
    }
    
    signal = strategy.generate_signal(historical_data, "BTC-USDT")
    logger.info(f"策略检测结果: {signal['signal']} - {signal['reasoning']}")
    
    # 测试死叉
    logger.info("📉 测试完美死叉...")
    death_data = create_perfect_death_cross()
    
    closes = [candle[4] for candle in death_data]
    prev_closes = closes[:-1]
    curr_closes = closes[1:]
    
    prev_ema_9 = TechnicalIndicators.calculate_ema(prev_closes, 9)
    prev_ema_21 = TechnicalIndicators.calculate_ema(prev_closes, 21)
    curr_ema_9 = TechnicalIndicators.calculate_ema(curr_closes, 9)
    curr_ema_21 = TechnicalIndicators.calculate_ema(curr_closes, 21)
    
    logger.info(f"死叉数据验证:")
    logger.info(f"  前一时刻: EMA_9={prev_ema_9:.2f}, EMA_21={prev_ema_21:.2f}")
    logger.info(f"  当前时刻: EMA_9={curr_ema_9:.2f}, EMA_21={curr_ema_21:.2f}")
    logger.info(f"  交叉条件: {prev_ema_9 >= prev_ema_21} -> {curr_ema_9 < curr_ema_21}")
    
    historical_data = {
        "historical_analysis": {
            "15m": {
                "ohlcv": death_data,
                "data_points": len(death_data)
            }
        }
    }
    
    signal = strategy.generate_signal(historical_data, "BTC-USDT")
    logger.info(f"策略检测结果: {signal['signal']} - {signal['reasoning']}")


if __name__ == "__main__":
    print("🔬 EMA交叉信号详细测试")
    print("=" * 50)
    
    # 测试EMA计算
    test_ema_calculation()
    
    print("\n" + "=" * 50)
    
    # 测试完美交叉
    test_perfect_crossover()
    
    print("\n" + "=" * 50)
    print("🏁 交叉信号测试完成")
