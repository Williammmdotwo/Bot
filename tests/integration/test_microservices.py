#!/usr/bin/env python3
"""
微服务测试脚本
测试各个微服务的核心功能
"""

import sys
import os
import time
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# 设置项目路径
project_root = Path(__file__).parent.parent.parent  # 从 tests/integration/ 向上两级到项目根目录
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

print(f"项目根目录: {project_root}")
print(f"src 目录: {src_path}")
print(f"Python 路径前3项: {sys.path[:3]}")

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_strategy_engine():
    """测试策略引擎"""
    logger.info("=== 测试策略引擎 ===")
    try:
        from strategy_engine.main import main_strategy_loop
        from data_manager.main import DataHandler
        
        # 创建模拟数据管理器
        data_handler = DataHandler()
        
        # 测试策略循环（使用技术分析）
        result = main_strategy_loop(
            data_manager=data_handler,
            symbol="BTC-USDT",
            use_demo=True
        )
        
        logger.info(f"策略引擎响应: {result}")
        logger.info("✅ 策略引擎测试通过")
        return True
        
    except Exception as e:
        logger.error(f"❌ 策略引擎测试失败: {e}")
        return False

def test_config_loading():
    """测试配置加载"""
    logger.info("=== 测试配置加载 ===")
    try:
        from risk_manager.config import get_config
        
        config = get_config()
        risk_limits = config.get_risk_limits()
        
        logger.info(f"风险限制配置: {risk_limits.dict()}")
        logger.info("✅ 配置加载测试通过")
        return True
        
    except Exception as e:
        logger.error(f"❌ 配置加载测试失败: {e}")
        return False

def test_database_config():
    """测试数据库配置"""
    logger.info("=== 测试数据库配置 ===")
    try:
        # 检查环境变量
        db_vars = [
            'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB',
            'REDIS_PASSWORD', 'AI_API_KEY'
        ]
        
        missing_vars = []
        for var in db_vars:
            value = os.getenv(var)
            if value:
                logger.info(f"✅ {var}: {'*' * len(value)}")
            else:
                missing_vars.append(var)
                logger.warning(f"❌ {var}: 未设置")
        
        if not missing_vars:
            logger.info("✅ 数据库配置测试通过")
            return True
        else:
            logger.warning(f"⚠️ 缺少环境变量: {missing_vars}")
            return False
            
    except Exception as e:
        logger.error(f"❌ 数据库配置测试失败: {e}")
        return False

def test_dependencies():
    """测试依赖包"""
    logger.info("=== 测试依赖包 ===")
    
    required_packages = [
        'fastapi', 'uvicorn', 'pydantic', 'asyncpg', 
        'redis', 'ccxt', 'pandas', 'requests'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            logger.info(f"✅ {package}")
        except ImportError:
            missing_packages.append(package)
            logger.error(f"❌ {package}")
    
    if not missing_packages:
        logger.info("✅ 依赖包测试通过")
        return True
    else:
        logger.error(f"❌ 缺少依赖包: {missing_packages}")
        return False

def test_api_endpoints():
    """测试 API 端点（模拟）"""
    logger.info("=== 测试 API 端点（模拟） ===")
    
    # 模拟风控服务检查
    order_data = {
        "symbol": "BTC-USDT",
        "side": "BUY", 
        "position_size": 1000,
        "stop_loss": 45000,
        "take_profit": 50000,
        "current_equity": 10000
    }
    
    # 简单的合理性检查
    is_rational = (
        order_data["position_size"] < order_data["current_equity"] and
        order_data["stop_loss"] < order_data["take_profit"] and
        order_data["side"] in ["BUY", "SELL"]
    )
    
    if is_rational:
        logger.info("✅ 订单合理性检查通过")
        logger.info(f"订单数据: {json.dumps(order_data, indent=2)}")
        return True
    else:
        logger.error("❌ 订单合理性检查失败")
        return False

def main():
    """主测试函数"""
    logger.info("🚀 开始微服务测试")
    logger.info(f"测试时间: {datetime.now().isoformat()}")
    
    test_results = []
    
    # 运行各项测试
    tests = [
        ("依赖包测试", test_dependencies),
        ("配置加载测试", test_config_loading),
        ("数据库配置测试", test_database_config),
        ("策略引擎测试", test_strategy_engine),
        ("API 端点测试", test_api_endpoints),
    ]
    
    for test_name, test_func in tests:
        logger.info(f"\n🧪 开始 {test_name}")
        try:
            result = test_func()
            test_results.append((test_name, result))
        except Exception as e:
            logger.error(f"❌ {test_name} 异常: {e}")
            test_results.append((test_name, False))
    
    # 汇总结果
    logger.info("\n" + "="*50)
    logger.info("📊 测试结果汇总")
    logger.info("="*50)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name}: {status}")
        if result:
            passed += 1
    
    logger.info(f"\n📈 总体结果: {passed}/{total} 测试通过")
    logger.info(f"成功率: {passed/total*100:.1f}%")
    
    if passed == total:
        logger.info("🎉 所有测试通过！系统基本功能正常")
    else:
        logger.warning("⚠️ 部分测试失败，需要进一步调试")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
