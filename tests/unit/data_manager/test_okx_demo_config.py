#!/usr/bin/env python3
"""
OKX Demo配置验证脚本
验证executor-service是否正确使用sandbox模式
"""

import os
import sys
import logging
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# 加载环境变量
env_file = project_root / ".env"
if env_file.exists():
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_environment_config():
    """测试环境配置"""
    logger.info("🔧 测试环境配置...")
    
    # 1. 测试环境变量
    data_source_mode = os.getenv("DATA_SOURCE_MODE", "NOT_SET")
    use_mock_data = os.getenv("USE_MOCK_DATA", "true").lower() == "true"
    okx_environment = os.getenv("OKX_ENVIRONMENT", "NOT_SET")
    
    logger.info(f"DATA_SOURCE_MODE: {data_source_mode}")
    logger.info(f"USE_MOCK_DATA: {use_mock_data}")
    logger.info(f"OKX_ENVIRONMENT: {okx_environment}")
    
    # 2. 测试OKX Demo API密钥
    demo_api_key = os.getenv("OKX_DEMO_API_KEY", "NOT_SET")
    demo_secret = os.getenv("OKX_DEMO_SECRET", "NOT_SET")
    demo_passphrase = os.getenv("OKX_DEMO_PASSPHRASE", "NOT_SET")
    
    logger.info(f"OKX_DEMO_API_KEY: {'SET' if demo_api_key != 'NOT_SET' else 'NOT_SET'}")
    logger.info(f"OKX_DEMO_SECRET: {'SET' if demo_secret != 'NOT_SET' else 'NOT_SET'}")
    logger.info(f"OKX_DEMO_PASSPHRASE: {'SET' if demo_passphrase != 'NOT_SET' else 'NOT_SET'}")
    
    # 3. 验证配置正确性
    expected_config = {
        "DATA_SOURCE_MODE": "OKX_DEMO",
        "USE_MOCK_DATA": "false",
        "OKX_ENVIRONMENT": "demo"
    }
    
    actual_config = {
        "DATA_SOURCE_MODE": data_source_mode,
        "USE_MOCK_DATA": str(use_mock_data).lower(),
        "OKX_ENVIRONMENT": okx_environment
    }
    
    config_correct = True
    for key, expected_value in expected_config.items():
        actual_value = actual_config[key]
        if actual_value != expected_value:
            logger.error(f"❌ 配置错误: {key} = {actual_value}, 期望: {expected_value}")
            config_correct = False
        else:
            logger.info(f"✅ 配置正确: {key} = {actual_value}")
    
    return config_correct and all([
        demo_api_key != "NOT_SET",
        demo_secret != "NOT_SET", 
        demo_passphrase != "NOT_SET"
    ])

def test_executor_ccxt_config():
    """测试Executor的CCXT配置"""
    logger.info("🏗️ 测试Executor CCXT配置...")
    
    try:
        # 导入executor的API服务器模块
        from src.executor.api_server import DemoCCXTExchange
        
        # 创建DemoCCXTExchange实例
        demo_exchange = DemoCCXTExchange()
        
        logger.info(f"DemoCCXTExchange创建成功")
        logger.info(f"Mock模式: {demo_exchange.mock_mode}")
        
        if not demo_exchange.mock_mode:
            # 检查CCXT实例配置
            exchange = demo_exchange.exchange
            if exchange:
                logger.info(f"CCXT交易所类型: {type(exchange).__name__}")
                logger.info(f"Sandbox模式: {exchange.sandbox}")
                logger.info(f"API密钥配置: {'是' if exchange.apiKey else '否'}")
                logger.info(f"默认类型: {exchange.options.get('defaultType', '未设置')}")
                
                # 验证sandbox配置
                if exchange.sandbox:
                    logger.info("✅ CCXT正确配置为sandbox模式")
                    return True
                else:
                    logger.error("❌ CCXT未配置为sandbox模式")
                    return False
            else:
                logger.error("❌ CCXT实例未创建")
                return False
        else:
            logger.info("ℹ️ DemoCCXTExchange处于Mock模式（API密钥未配置）")
            return True
            
    except Exception as e:
        logger.error(f"❌ 测试Executor CCXT配置失败: {e}")
        return False

def test_data_manager_config():
    """测试数据管理器配置"""
    logger.info("📊 测试数据管理器配置...")
    
    try:
        from src.utils.environment_utils import get_data_source_config, get_data_source_label
        
        # 获取数据源配置
        data_config = get_data_source_config()
        data_label = get_data_source_label()
        
        logger.info(f"数据源类型: {data_config['data_source_type']}")
        logger.info(f"数据源标签: {data_config['data_source_label']}")
        logger.info(f"使用Mock: {data_config['use_mock']}")
        logger.info(f"使用Demo: {data_config['use_demo']}")
        logger.info(f"描述: {data_config['description']}")
        
        # 验证是否为OKX_DEMO
        if data_config['data_source_type'] == 'OKX_DEMO':
            logger.info("✅ 数据管理器正确配置为OKX Demo")
            return True
        else:
            logger.error(f"❌ 数据管理器配置错误: {data_config['data_source_type']}")
            return False
            
    except Exception as e:
        logger.error(f"❌ 测试数据管理器配置失败: {e}")
        return False

def test_rest_client_config():
    """测试REST客户端配置"""
    logger.info("🌐 测试REST客户端配置...")
    
    try:
        from src.data_manager.rest_client import RESTClient
        
        # 创建REST客户端实例
        rest_client = RESTClient()
        
        logger.info(f"REST客户端创建成功")
        logger.info(f"使用Mock: {rest_client.use_mock}")
        logger.info(f"使用Demo: {rest_client.use_demo}")
        logger.info(f"有API密钥: {rest_client.has_credentials}")
        
        if not rest_client.use_mock and rest_client.use_demo:
            logger.info("✅ REST客户端正确配置为OKX Demo模式")
            return True
        elif rest_client.use_mock:
            logger.info("ℹ️ REST客户端处于Mock模式")
            return True
        else:
            logger.error("❌ REST客户端配置错误")
            return False
            
    except Exception as e:
        logger.error(f"❌ 测试REST客户端配置失败: {e}")
        return False

def main():
    """主测试函数"""
    logger.info("🚀 开始OKX Demo配置验证")
    logger.info("=" * 60)
    
    # 执行所有测试
    tests = [
        ("环境配置", test_environment_config),
        ("Executor CCXT配置", test_executor_ccxt_config),
        ("数据管理器配置", test_data_manager_config),
        ("REST客户端配置", test_rest_client_config)
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\n📋 执行测试: {test_name}")
        logger.info("-" * 40)
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"测试异常: {e}")
            results.append((test_name, False))
    
    # 输出测试结果
    logger.info("\n" + "=" * 60)
    logger.info("📊 测试结果汇总")
    logger.info("=" * 60)
    
    passed_tests = 0
    total_tests = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name}: {status}")
        if result:
            passed_tests += 1
    
    logger.info("=" * 60)
    logger.info(f"总计: {passed_tests}/{total_tests} 测试通过")
    
    if passed_tests == total_tests:
        logger.info("🎉 所有测试通过！OKX Demo配置正确！")
        return True
    else:
        logger.error(f"⚠️ {total_tests - passed_tests} 个测试失败，请检查配置")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
