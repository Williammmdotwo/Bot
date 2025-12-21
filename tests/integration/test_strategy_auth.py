#!/usr/bin/env python3
"""
测试策略引擎认证
"""
import os
import requests
import json

def test_strategy_auth():
    # 设置环境变量
    os.environ['INTERNAL_SERVICE_TOKEN'] = 'athena-internal-token-change-in-production'
    
    print(f"INTERNAL_SERVICE_TOKEN: {os.getenv('INTERNAL_SERVICE_TOKEN')}")
    
    # 测试健康检查
    try:
        response = requests.get("http://localhost:8003/health", timeout=5)
        print(f"Health check: {response.status_code} - {response.json()}")
    except Exception as e:
        print(f"Health check failed: {e}")
    
    # 测试认证API
    headers = {
        'Content-Type': 'application/json',
        'x-service-token': 'athena-internal-token-change-in-production'
    }
    
    data = {
        'symbol': 'BTC-USDT',
        'use_demo': True
    }
    
    try:
        response = requests.post(
            "http://localhost:8003/api/generate-signal",
            headers=headers,
            json=data,
            timeout=30
        )
        print(f"API call: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"API call failed: {e}")

if __name__ == "__main__":
    test_strategy_auth()
