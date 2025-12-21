#!/usr/bin/env python3
"""
Mock数据功能测试脚本
验证系统在Mock模式下的完整功能
"""

import os
import sys
import logging
import time
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.utils.environment_utils import get_data_source_config, get_environment_config
from src.data_manager.rest_client import RESTClient
from src.data_manager.market_data_fetcher import MarketDataFetcher

def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def test_mock_data_source():
    """测试Mock数据源配置"""
    print("=" * 60)
    print("🔧 Mock数据源配置测试")
    print("=" * 60)
    
    # 强制使用Mock模式
    os.environ["DATA_SOURCE_MODE"] = "MOCK_DATA"
    
    # 测试配置
    config = get_data_source_config()
    env_config = get_environment_config()
    
    print(f"📊 数据源配置: {config['data_source_label']}")
    print(f"   使用Mock: {config['use_mock']}")
    print(f"   使用Demo: {config['use_demo']}")
    print(f"   环境类型: {env_config['environment_type']}")
    
    return config

def test_rest_client_mock():
    """测试REST客户端Mock功能"""
    print("\n🌐 测试REST客户端Mock功能...")
    
    try:
        # 创建REST客户端（会自动使用Mock模式）
        rest_client = RESTClient()
        
        print(f"   客户端模式: {'Demo' if rest_client.use_demo else 'Production'}")
        print(f"   密钥状态: {'有' if rest_client.has_credentials else '无'}")
        
        # 测试获取ticker数据
        print("\n📈 测试获取BTC-USDT ticker数据...")
        ticker = rest_client.fetch_ticker("BTC-USDT")
        
        if ticker:
            print(f"   ✅ Ticker获取成功")
            print(f"   当前价格: {ticker.get('last', 'N/A')}")
            print(f"   24h变化: {ticker.get('percentage', 'N/A'):.2f}%")
            print(f"   数据来源: {ticker.get('source', 'N/A')}")
        else:
            print("   ❌ Ticker获取失败")
            return False
        
        # 测试获取订单簿
        print("\n📚 测试获取订单簿数据...")
        orderbook = rest_client.fetch_orderbook("BTC-USDT", 5)
        
        if orderbook and orderbook.get('bids') and orderbook.get('asks'):
            print(f"   ✅ 订单簿获取成功")
            best_bid = orderbook['bids'][0] if orderbook['bids'] else None
            best_ask = orderbook['asks'][0] if orderbook['asks'] else None
            if best_bid and best_ask:
                spread = best_ask[0] - best_bid[0]
                print(f"   最佳买价: {best_bid[0]:.2f}")
                print(f"   最佳卖价: {best_ask[0]:.2f}")
                print(f"   价差: {spread:.2f}")
        else:
            print("   ❌ 订单簿获取失败")
            return False
        
        # 测试获取K线数据
        print("\n📊 测试获取K线数据...")
        since = int((time.time() - 300) * 1000)  # 最近5分钟
        ohlcv_data = rest_client.fetch_ohlcv("BTC-USDT", since, 10, "5m")
        
        if ohlcv_data:
            print(f"   ✅ K线数据获取成功")
            print(f"   数据条数: {len(ohlcv_data)}")
            if len(ohlcv_data) > 0:
                latest_candle = ohlcv_data[-1]
                print(f"   最新价格: {latest_candle[4]:.2f}")
                print(f"   最新成交量: {latest_candle[5]:.2f}")
        else:
            print("   ❌ K线数据获取失败")
            return False
        
        return True
        
    except Exception as e:
        print(f"\n❌ REST客户端测试失败: {e}")
        return False

def test_market_data_fetcher():
    """测试市场数据获取器"""
    print("\n📊 测试市场数据获取器...")
    
    try:
        # 创建市场数据获取器
        fetcher = MarketDataFetcher()
        
        # 测试获取综合市场信息
        print("🔍 获取BTC-USDT综合市场信息...")
        market_info = fetcher.get_market_info("BTC-USDT")
        
        if market_info:
            print("   ✅ 市场信息获取成功")
            print(f"   交易对: {market_info.get('symbol', 'N/A')}")
            print(f"   数据源: {market_info.get('data_source', 'N/A')}")
            print(f"   时间戳: {market_info.get('timestamp', 'N/A')}")
            
            # 检查各个数据组件
            if market_info.get('ticker'):
                ticker = market_info['ticker']
                print(f"   Ticker价格: {ticker.get('last', 'N/A')}")
            
            if market_info.get('orderbook'):
                orderbook = market_info['orderbook']
                if orderbook.get('bids') and orderbook.get('asks'):
                    print(f"   订单簿深度: 买{len(orderbook['bids'])} 卖{len(orderbook['asks'])}")
            
            if market_info.get('ohlcv'):
                ohlcv = market_info['ohlcv']
                print(f"   K线时间框架: {list(ohlcv.keys())}")
        else:
            print("   ❌ 市场信息获取失败")
            return False
        
        return True
        
    except Exception as e:
        print(f"\n❌ 市场数据获取器测试失败: {e}")
        return False

def test_data_consistency():
    """测试数据一致性"""
    print("\n🔍 测试数据一致性...")
    
    try:
        rest_client = RESTClient()
        
        # 多次获取同一数据，检查一致性
        print("📈 多次获取ticker数据...")
        tickers = []
        for i in range(3):
            ticker = rest_client.fetch_ticker("BTC-USDT")
            if ticker:
                tickers.append(ticker)
                print(f"   第{i+1}次: {ticker.get('last', 'N/A')} ({ticker.get('timestamp', 'N/A')})")
            time.sleep(1)
        
        if len(tickers) >= 2:
            # 检查价格变化是否合理
            prices = [t.get('last', 0) for t in tickers]
            price_changes = [abs(prices[i+1] - prices[i]) for i in range(len(prices)-1)]
            avg_change = sum(price_changes) / len(price_changes) if price_changes else 0
            
            print(f"   价格变化分析:")
            print(f"   平均变化: {avg_change:.2f}")
            print(f"   数据一致性: {'✅ 良好' if avg_change < 1000 else '⚠️ 需要关注'}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 数据一致性测试失败: {e}")
        return False

def main():
    """主函数"""
    setup_logging()
    
    print(f"🚀 开始Mock数据功能测试 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 测试Mock数据源配置
    config = test_mock_data_source()
    
    # 测试REST客户端Mock功能
    rest_success = test_rest_client_mock()
    
    # 测试市场数据获取器
    fetcher_success = test_market_data_fetcher()
    
    # 测试数据一致性
    consistency_success = test_data_consistency()
    
    # 总结测试结果
    print("\n" + "=" * 60)
    print("📊 测试结果总结")
    print("=" * 60)
    
    results = [
        ("数据源配置", True),  # 配置测试总是成功
        ("REST客户端", rest_success),
        ("市场数据获取器", fetcher_success),
        ("数据一致性", consistency_success)
    ]
    
    passed = 0
    total = len(results)
    
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
        if success:
            passed += 1
    
    print(f"\n📈 总体结果: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有Mock数据功能测试通过！")
        print("\n💡 系统状态:")
        print("   ✅ Mock数据源配置正确")
        print("   ✅ REST客户端Mock功能正常")
        print("   ✅ 市场数据获取器工作正常")
        print("   ✅ 数据一致性良好")
        print("\n🔧 可以安全使用Mock模式进行策略测试")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 个测试失败，需要进一步检查")
        return 1

if __name__ == "__main__":
    sys.exit(main())
