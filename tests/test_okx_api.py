#!/usr/bin/env python3
"""
测试OKX API密钥配置
"""

import os
import ccxt
import ccxt.pro
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def test_okx_credentials():
    """测试OKX API密钥"""
    print("🔍 测试OKX API密钥配置...")
    
    # 获取环境变量
    okx_environment = os.getenv("OKX_ENVIRONMENT", "production").lower()
    use_demo = okx_environment in ["demo", "demo环境", "demo-trading"]
    
    print(f"📋 环境配置:")
    print(f"   OKX_ENVIRONMENT: {okx_environment}")
    print(f"   Use Demo: {use_demo}")
    
    # 获取API密钥
    if use_demo:
        api_key = os.getenv("OKX_DEMO_API_KEY")
        secret = os.getenv("OKX_DEMO_SECRET")
        passphrase = os.getenv("OKX_DEMO_PASSPHRASE")
        print(f"   API Key: {api_key}")
        print(f"   Secret: {secret[:10]}..." if secret else "None")
        print(f"   Passphrase: {passphrase}")
    else:
        api_key = os.getenv("OKX_API_KEY")
        secret = os.getenv("OKX_SECRET")
        passphrase = os.getenv("OKX_PASSPHRASE")
        print(f"   API Key: {api_key}")
        print(f"   Secret: {secret[:10]}..." if secret else "None")
        print(f"   Passphrase: {passphrase}")
    
    # 测试REST API
    print(f"\n🌐 测试REST API连接...")
    try:
        exchange = ccxt.okx({
            "apiKey": api_key,
            "secret": secret,
            "password": passphrase,
            "sandbox": use_demo,
            "enableRateLimit": True
        })
        
        # 测试获取账户信息
        balance = exchange.fetch_balance()
        print(f"✅ REST API连接成功")
        print(f"   账户信息: {balance.get('info', {}).get('code', 'N/A')}")
        
    except Exception as e:
        print(f"❌ REST API连接失败: {e}")
        return False
    
    # 测试WebSocket API
    print(f"\n🔌 测试WebSocket API连接...")
    try:
        ws_exchange = ccxt.pro.okx({
            "apiKey": api_key,
            "secret": secret,
            "password": passphrase,
            "sandbox": use_demo,
            "enableRateLimit": True
        })
        
        # 测试WebSocket连接
        import asyncio
        
        async def test_ws():
            try:
                await ws_exchange.load_markets()
                print(f"✅ WebSocket API连接成功")
                await ws_exchange.close()
                return True
            except Exception as e:
                print(f"❌ WebSocket API连接失败: {e}")
                return False
        
        result = asyncio.run(test_ws())
        return result
        
    except Exception as e:
        print(f"❌ WebSocket API测试失败: {e}")
        return False

def main():
    """主函数"""
    print("╔════════════════════════════════════════════════════════════╗")
    print("║              OKX API 密钥测试工具                          ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    
    success = test_okx_credentials()
    
    print(f"\n📊 === 测试结果 ===")
    if success:
        print("🎉 API密钥配置正确！")
        print("\n💡 如果data服务仍有问题，可能需要:")
        print("   1. 重启data服务")
        print("   2. 检查网络连接")
        print("   3. 确认API权限设置")
    else:
        print("❌ API密钥配置有问题")
        print("\n🔧 解决方案:")
        print("   1. 检查API密钥是否正确")
        print("   2. 确认使用Demo环境的API密钥")
        print("   3. 检查API权限设置")
        print("   4. 确认环境变量配置")
    
    return success

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
