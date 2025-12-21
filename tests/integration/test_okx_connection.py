#!/usr/bin/env python3
"""
OKX API连接测试脚本
验证OKX Demo API配置和连接状态
"""

import os
import sys
import logging
import time
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.data_manager.rest_client import RESTClient
from src.utils.environment_utils import get_data_source_config, get_environment_config, get_api_credentials

def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def test_okx_demo_connection():
    """测试OKX Demo API连接"""
    print("=" * 60)
    print("🔧 OKX Demo API 连接测试")
    print("=" * 60)
    
    # 显示当前环境配置
    env_config = get_environment_config()
    print(f"📊 环境配置: {env_config}")
    
    # 显示API密钥状态
    credentials, has_credentials = get_api_credentials()
    print(f"🔑 API密钥状态: {'完整' if has_credentials else '缺失'}")
    
    if has_credentials:
        print(f"   API Key: {credentials['api_key'][:8]}...")
        print(f"   Environment: {credentials['environment']}")
    
    # 测试REST客户端连接
    print("\n🌐 测试REST客户端连接...")
    try:
        # 强制使用Demo模式
        rest_client = RESTClient(use_demo=True)
        
        print(f"   客户端初始化: {'Demo' if rest_client.use_demo else 'Production'}")
        print(f"   密钥状态: {'有' if rest_client.has_credentials else '无'}")
        
        # 测试获取ticker数据
        print("\n📈 测试获取BTC-USDT ticker数据...")
        start_time = time.time()
        ticker = rest_client.fetch_ticker("BTC-USDT")
        response_time = time.time() - start_time
        
        if ticker:
            print(f"   ✅ Ticker获取成功 (耗时: {response_time:.2f}s)")
            print(f"   当前价格: {ticker.get('last', 'N/A')}")
            print(f"   24h变化: {ticker.get('percentage', 'N/A'):.2f}%")
        else:
            print("   ❌ Ticker获取失败")
            return False
        
        # 测试获取订单簿
        print("\n📚 测试获取订单簿数据...")
        start_time = time.time()
        orderbook = rest_client.fetch_orderbook("BTC-USDT", 5)
        response_time = time.time() - start_time
        
        if orderbook and orderbook.get('bids') and orderbook.get('asks'):
            print(f"   ✅ 订单簿获取成功 (耗时: {response_time:.2f}s)")
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
        start_time = time.time()
        since = int((time.time() - 300) * 1000)  # 最近5分钟
        ohlcv_data = rest_client.fetch_ohlcv("BTC-USDT", since, 10, "5m")
        response_time = time.time() - start_time
        
        if ohlcv_data:
            print(f"   ✅ K线数据获取成功 (耗时: {response_time:.2f}s)")
            print(f"   数据条数: {len(ohlcv_data)}")
            if len(ohlcv_data) > 0:
                latest_candle = ohlcv_data[-1]
                print(f"   最新价格: {latest_candle[4]:.2f}")
                print(f"   最新成交量: {latest_candle[5]:.2f}")
        else:
            print("   ❌ K线数据获取失败")
            return False
        
        # 测试获取账户信息
        print("\n💰 测试获取账户信息...")
        if rest_client.has_credentials:
            start_time = time.time()
            try:
                balance = rest_client.fetch_balance()
                response_time = time.time() - start_time
                
                if balance:
                    print(f"   ✅ 账户信息获取成功 (耗时: {response_time:.2f}s)")
                    total_balance = balance.get('total', {}).get('USDT', 0)
                    free_balance = balance.get('free', {}).get('USDT', 0)
                    print(f"   总余额: {total_balance:.2f} USDT")
                    print(f"   可用余额: {free_balance:.2f} USDT")
                else:
                    print("   ❌ 账户信息获取失败")
                    return False
            except Exception as e:
                print(f"   ⚠️ 账户信息获取异常: {e}")
                print("   (这可能是Demo API权限限制)")
        else:
            print("   ⚠️ 跳过账户信息测试 (无API密钥)")
        
        print("\n🎯 OKX Demo API连接测试完成")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ OKX API连接测试失败: {e}")
        print("=" * 60)
        return False

def test_data_source_switching():
    """测试数据源切换"""
    print("\n🔄 测试数据源切换...")
    
    # 测试Mock数据源
    print("\n1. 测试Mock数据源...")
    os.environ["DATA_SOURCE_MODE"] = "MOCK_DATA"
    mock_config = get_data_source_config()
    print(f"   数据源: {mock_config['data_source_label']}")
    print(f"   使用Mock: {mock_config['use_mock']}")
    print(f"   使用Demo: {mock_config['use_demo']}")
    
    # 测试OKX Demo数据源
    print("\n2. 测试OKX Demo数据源...")
    os.environ["DATA_SOURCE_MODE"] = "OKX_DEMO"
    demo_config = get_data_source_config()
    print(f"   数据源: {demo_config['data_source_label']}")
    print(f"   使用Mock: {demo_config['use_mock']}")
    print(f"   使用Demo: {demo_config['use_demo']}")
    
    # 恢复原始设置
    print("\n3. 恢复原始设置...")
    if "DATA_SOURCE_MODE" in os.environ:
        del os.environ["DATA_SOURCE_MODE"]
    original_config = get_data_source_config()
    print(f"   数据源: {original_config['data_source_label']}")

def main():
    """主函数"""
    setup_logging()
    
    print(f"🚀 开始OKX连接测试 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 测试数据源切换
    test_data_source_switching()
    
    # 测试OKX Demo API连接
    success = test_okx_demo_connection()
    
    if success:
        print("\n✅ 所有测试通过！OKX Demo API连接正常")
        print("\n💡 建议:")
        print("   - 可以使用 'export DATA_SOURCE_MODE=OKX_DEMO' 切换到OKX Demo模式")
        print("   - 系统将使用真实的OKX市场数据进行模拟交易")
        return 0
    else:
        print("\n❌ OKX API连接测试失败")
        print("\n🔧 可能的解决方案:")
        print("   1. 检查网络连接")
        print("   2. 验证API密钥配置")
        print("   3. 确认OKX Demo服务状态")
        print("   4. 继续使用Mock数据模式")
        return 1

if __name__ == "__main__":
    sys.exit(main())
