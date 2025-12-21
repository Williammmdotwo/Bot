#!/usr/bin/env python3
"""
简单的API端点测试脚本
Simple API Endpoint Test Script
"""

import requests
import json
import time
import sys

def test_market_data_api():
    """测试市场数据API端点"""
    base_url = "http://localhost:8004"
    symbol = "BTC-USDT"
    
    print("=== 测试数据管理服务API端点 ===")
    print(f"服务地址: {base_url}")
    print(f"测试交易对: {symbol}")
    print()
    
    # 测试1: 健康检查
    print("1. 测试健康检查端点...")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            health_data = response.json()
            print(f"✓ 健康检查成功: {health_data}")
        else:
            print(f"✗ 健康检查失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ 健康检查异常: {e}")
        return False
    
    print()
    
    # 测试2: 演示数据API
    print("2. 测试演示数据API...")
    try:
        start_time = time.time()
        response = requests.get(
            f"{base_url}/api/market-data/{symbol}?use_demo=true",
            timeout=30
        )
        response_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ API调用成功 (响应时间: {response_time:.2f}s)")
            print(f"  交易对: {data.get('symbol', 'N/A')}")
            print(f"  当前价格: {data.get('current_price', 0)}")
            print(f"  数据状态: {data.get('data_status', 'N/A')}")
            print(f"  处理时间: {data.get('processing_time', 0):.3f}s")
            print(f"  使用演示数据: {data.get('use_demo', False)}")
            
            # 检查技术分析数据
            ta = data.get('technical_analysis', {})
            if ta and 'error' not in ta:
                print(f"  技术指标数量: {len(ta)}")
                print(f"  RSI: {ta.get('rsi', 'N/A')}")
                print(f"  趋势: {ta.get('trend', 'N/A')}")
                print(f"  动量: {ta.get('momentum', 'N/A')}")
            else:
                print(f"  技术分析: {ta.get('error', '无数据')}")
            
            # 检查成功和失败的时间框架
            successful_tfs = data.get('successful_timeframes', [])
            failed_tfs = data.get('failed_timeframes', [])
            if successful_tfs:
                print(f"  成功时间框架: {successful_tfs}")
            if failed_tfs:
                print(f"  失败时间框架: {failed_tfs}")
            
        else:
            print(f"✗ API调用失败: {response.status_code}")
            print(f"  响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"✗ API调用异常: {e}")
        return False
    
    print()
    
    # 测试3: 生产数据API（可选）
    print("3. 测试生产数据API...")
    try:
        start_time = time.time()
        response = requests.get(
            f"{base_url}/api/market-data/{symbol}?use_demo=false",
            timeout=30
        )
        response_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ 生产API调用成功 (响应时间: {response_time:.2f}s)")
            print(f"  当前价格: {data.get('current_price', 0)}")
            print(f"  数据状态: {data.get('data_status', 'N/A')}")
        else:
            print(f"⚠ 生产API调用失败: {response.status_code}")
            print("  这可能是正常的，如果生产环境API密钥未配置")
            
    except Exception as e:
        print(f"⚠ 生产API调用异常: {e}")
        print("  这可能是正常的，如果生产环境API密钥未配置")
    
    print()
    print("=== API测试完成 ===")
    return True

def main():
    """主函数"""
    try:
        success = test_market_data_api()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n测试执行失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
