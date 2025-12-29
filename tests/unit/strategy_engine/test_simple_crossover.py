#!/usr/bin/env python3
"""
简单明确的交叉信号测试
"""

import sys
import os
import logging

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def create_clear_golden_cross():
    """创建明确的金叉数据"""
    # 创建一个明确的金叉场景
    ohlcv = []

    # 前20根K线：价格从100逐渐下跌到90，EMA9 < EMA21
    for i in range(20):
        timestamp = 1700000000000 + i * 15 * 60 * 1000
        price = 100 - i * 0.5  # 从100跌到90

        ohlcv.append([
            timestamp,
            price + 0.1,  # open
            price + 0.2,  # high
            price - 0.1,  # low
            price,         # close
            1000          # volume
        ])

    # 后5根K线：价格快速上涨到110，EMA9 > EMA21
    for i in range(5):
        timestamp = 1700000000000 + (20 + i) * 15 * 60 * 1000
        price = 90 + i * 4  # 从90涨到110

        ohlcv.append([
            timestamp,
            price - 0.1,  # open
            price + 0.2,  # high
            price - 0.2,  # low
            price,         # close
            2000          # volume (放大)
        ])

    return ohlcv

def create_clear_death_cross():
    """创建明确的死叉数据"""
    # 创建一个明确的死叉场景
    ohlcv = []

    # 前20根K线：价格从100逐渐上涨到110，EMA9 > EMA21
    for i in range(20):
        timestamp = 1700000000000 + i * 15 * 60 * 1000
        price = 100 + i * 0.5  # 从100涨到110

        ohlcv.append([
            timestamp,
            price - 0.1,  # open
            price + 0.2,  # high
            price - 0.1,  # low
            price,         # close
            1000          # volume
        ])

    # 后5根K线：价格快速下跌到90，EMA9 < EMA21
    for i in range(5):
        timestamp = 1700000000000 + (20 + i) * 15 * 60 * 1000
        price = 110 - i * 4  # 从110跌到90

        ohlcv.append([
            timestamp,
            price + 0.1,  # open
            price + 0.2,  # high
            price - 0.2,  # low
            price,         # close
            2000          # volume (放大)
        ])

    return ohlcv

def test_clear_crossover():
    """测试明确的交叉信号"""
    from src.strategy_engine.dual_ema_strategy import DualEMAStrategy
    from src.data_manager.core.technical_indicators import TechnicalIndicators

    strategy = DualEMAStrategy(ema_fast=9, ema_slow=21)

    # 测试金叉
    logger.info("📈 测试明确金叉...")
    golden_data = create_clear_golden_cross()

    # 手动验证EMA值
    closes = [candle[4] for candle in golden_data]

    # 计算倒数第2根K线的EMA（前一时刻）
    prev_closes = closes[:-1]
    prev_ema_9 = TechnicalIndicators.calculate_ema(prev_closes, 9)
    prev_ema_21 = TechnicalIndicators.calculate_ema(prev_closes, 21)

    # 计算最后一根K线的EMA（当前时刻）
    curr_ema_9 = TechnicalIndicators.calculate_ema(closes, 9)
    curr_ema_21 = TechnicalIndicators.calculate_ema(closes, 21)

    logger.info(f"金叉验证:")
    logger.info(f"  前一时刻: EMA_9={prev_ema_9:.2f}, EMA_21={prev_ema_21:.2f}, 关系: {prev_ema_9 <= prev_ema_21}")
    logger.info(f"  当前时刻: EMA_9={curr_ema_9:.2f}, EMA_21={curr_ema_21:.2f}, 关系: {curr_ema_9 > curr_ema_21}")
    logger.info(f"  金叉条件: {prev_ema_9 <= prev_ema_21} AND {curr_ema_9 > curr_ema_21}")

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
    logger.info(f"策略结果: {signal['signal']} - {signal['reasoning']}")

    # 重置策略状态
    strategy.reset_state()

    # 测试死叉
    logger.info("📉 测试明确死叉...")
    death_data = create_clear_death_cross()

    closes = [candle[4] for candle in death_data]
    prev_closes = closes[:-1]
    prev_ema_9 = TechnicalIndicators.calculate_ema(prev_closes, 9)
    prev_ema_21 = TechnicalIndicators.calculate_ema(prev_closes, 21)
    curr_ema_9 = TechnicalIndicators.calculate_ema(closes, 9)
    curr_ema_21 = TechnicalIndicators.calculate_ema(closes, 21)

    logger.info(f"死叉验证:")
    logger.info(f"  前一时刻: EMA_9={prev_ema_9:.2f}, EMA_21={prev_ema_21:.2f}, 关系: {prev_ema_9 >= prev_ema_21}")
    logger.info(f"  当前时刻: EMA_9={curr_ema_9:.2f}, EMA_21={curr_ema_21:.2f}, 关系: {curr_ema_9 < curr_ema_21}")
    logger.info(f"  死叉条件: {prev_ema_9 >= prev_ema_21} AND {curr_ema_9 < curr_ema_21}")

    historical_data = {
        "historical_analysis": {
            "15m": {
                "ohlcv": death_data,
                "data_points": len(death_data)
            }
        }
    }

    signal = strategy.generate_signal(historical_data, "BTC-USDT")
    logger.info(f"策略结果: {signal['signal']} - {signal['reasoning']}")

if __name__ == "__main__":
    print("🎯 明确交叉信号测试")
    print("=" * 50)

    test_clear_crossover()

    print("\n" + "=" * 50)
    print("🏁 测试完成")
