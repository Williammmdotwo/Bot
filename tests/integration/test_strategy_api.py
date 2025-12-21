#!/usr/bin/env python3
"""
测试策略引擎API响应格式
"""

import sys
import os
import requests
import json
sys.path.append('.')

from src.utils.environment_utils import get_data_source_config

def test_strategy_api():
    """测试策略引擎API"""
    print("=== 策略引擎API测试 ===")
    
    # 获取配置
    data_source_config = get_data_source_config()
    print(f"数据源配置: {data_source_config}")
    
    # API配置
    strategy_url = "http://localhost:8003/api/generate-signal"
    headers = {
        'Content-Type': 'application/json',
        'x-service-token': 'athena-internal-token-change-in-production'
    }
    
    # 请求数据
    data = {
        'symbol': 'BTC-USDT',
        'use_demo': data_source_config['use_demo']
    }
    
    print(f"\n=== 发送请求到 {strategy_url} ===")
    print(f"请求数据: {json.dumps(data, indent=2)}")
    
    try:
        response = requests.post(strategy_url, headers=headers, json=data, timeout=30)
        print(f"\n=== HTTP响应状态 ===")
        print(f"状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        
        if response.status_code == 200:
            response_data = response.json()
            print(f"\n=== 完整响应数据 ===")
            print(json.dumps(response_data, indent=2, ensure_ascii=False))
            
            print(f"\n=== 关键字段提取 ===")
            print(f"Signal: {response_data.get('signal', 'N/A')}")
            print(f"Confidence: {response_data.get('confidence', 'N/A')}")
            print(f"Decision ID: {response_data.get('decision_id', 'N/A')}")
            print(f"Reason: {response_data.get('reason', 'N/A')}")
            
            # 检查嵌套结构
            if 'parsed_response' in response_data:
                parsed = response_data['parsed_response']
                print(f"\n=== 嵌套parsed_response字段 ===")
                print(f"Action: {parsed.get('action', 'N/A')}")
                print(f"Side: {parsed.get('side', 'N/A')}")
                print(f"Confidence: {parsed.get('confidence', 'N/A')}")
                print(f"Reasoning: {parsed.get('reasoning', 'N/A')}")
            
            # 检查嵌套结构
            if 'parsed_response' in response_data:
                parsed = response_data['parsed_response']
                print(f"\n=== 嵌套parsed_response字段 ===")
                print(f"Action: {parsed.get('action', 'N/A')}")
                print(f"Side: {parsed.get('side', 'N/A')}")
                print(f"Confidence: {parsed.get('confidence', 'N/A')}")
                print(f"Reasoning: {parsed.get('reasoning', 'N/A')}")
            
        else:
            print(f"请求失败: {response.text}")
            
    except Exception as e:
        print(f"API调用异常: {e}")

if __name__ == "__main__":
    test_strategy_api()
