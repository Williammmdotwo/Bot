#!/usr/bin/env python3
"""
测试数据管理器返回的数据结构
"""

import sys
import os
sys.path.append('.')

from src.data_manager.main import DataHandler

def test_data_manager():
    """测试数据管理器"""
    print("=== 数据管理器测试 ===")
    
    # 初始化数据处理器
    data_handler = DataHandler()
    print("数据处理器初始化完成")
    
    # 获取市场数据
    market_data = data_handler.get_comprehensive_market_data('BTC-USDT', use_demo=True)
    
    print(f"Current Price: {market_data.get('current_price', 'N/A')}")
    print(f"Data Status: {market_data.get('data_status', 'N/A')}")
    print(f"Available Keys: {list(market_data.keys())}")
    
    if 'ticker' in market_data:
        ticker = market_data['ticker']
        print(f"Ticker Keys: {list(ticker.keys()) if ticker else 'None'}")
        print(f"Ticker Last: {ticker.get('last', 'N/A') if ticker else 'N/A'}")
    
    # 检查技术指标
    if 'technical_analysis' in market_data:
        ta = market_data['technical_analysis']
        print(f"Technical Analysis Timeframes: {list(ta.keys())}")
        
        for tf, indicators in ta.items():
            print(f"  {tf}: current_price = {indicators.get('current_price', 'N/A')}")

if __name__ == "__main__":
    test_data_manager()
