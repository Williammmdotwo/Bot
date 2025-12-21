#!/usr/bin/env python3
"""
安全修复验证测试脚本
验证所有交易模式切换相关的安全修复是否正确实施
"""

import os
import sys
import subprocess
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_environment_validation():
    """测试环境配置验证"""
    print("🔍 测试环境配置验证...")
    
    try:
        result = subprocess.run([
            sys.executable, 'scripts/verify_environment_config.py'
        ], capture_output=True, text=True, cwd='.')
        
        if result.returncode == 0:
            print("✅ 环境配置验证通过")
            return True
        else:
            print("❌ 环境配置验证失败")
            print(result.stdout)
            print(result.stderr)
            return False
    except Exception as e:
        print(f"❌ 环境配置验证异常: {e}")
        return False

def test_risk_manager_fix():
    """测试风险管理服务修复"""
    print("🔍 测试风险管理服务修复...")
    
    try:
        with open('src/risk_manager/actions.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查是否使用了正确的环境变量
        if 'OKX_ENVIRONMENT' in content and 'OKX_SANDBOX' not in content:
            print("✅ 风险管理服务环境判断已修复")
            return True
        else:
            print("❌ 风险管理服务仍使用过时的环境变量")
            return False
    except Exception as e:
        print(f"❌ 风险管理服务检查失败: {e}")
        return False

def test_executor_security():
    """测试执行服务安全验证"""
    print("🔍 测试执行服务安全验证...")
    
    try:
        with open('src/executor/main.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查是否有环境验证逻辑
        checks = [
            'Trading only allowed in demo environment' in content,
            'OKX_ENVIRONMENT' in content,
            'use_demo' in content
        ]
        
        if all(checks):
            print("✅ 执行服务安全验证已添加")
            return True
        else:
            print("❌ 执行服务缺少安全验证逻辑")
            return False
    except Exception as e:
        print(f"❌ 执行服务检查失败: {e}")
        return False

def test_data_manager_consistency():
    """测试数据管理服务一致性"""
    print("🔍 测试数据管理服务一致性...")
    
    try:
        with open('src/data_manager/websocket_client.py', 'r', encoding='utf-8') as f:
            ws_content = f.read()
        
        with open('src/data_manager/rest_client.py', 'r', encoding='utf-8') as f:
            rest_content = f.read()
        
        # 检查WebSocket客户端是否使用统一环境工具
        ws_checks = [
            'from src.utils.environment_utils import' in ws_content,
            'get_environment_config()' in ws_content,
            'get_ccxt_config()' in ws_content
        ]
        
        # 检查REST客户端是否使用统一环境工具
        rest_checks = [
            'from src.utils.environment_utils import' in rest_content,
            'get_environment_config()' in rest_content,
            'get_ccxt_config()' in rest_content
        ]
        
        if all(ws_checks) and all(rest_checks):
            print("✅ 数据管理服务一致性检查通过")
            return True
        else:
            print("❌ 数据管理服务一致性检查失败")
            print(f"   WebSocket检查: {ws_checks}")
            print(f"   REST检查: {rest_checks}")
            return False
    except Exception as e:
        print(f"❌ 数据管理服务检查失败: {e}")
        return False

def test_default_environment_values():
    """测试默认环境值"""
    print("🔍 测试默认环境值...")
    
    files_to_check = [
        'src/data_manager/websocket_client.py',
        'src/data_manager/rest_client.py',
        'src/risk_manager/actions.py',
        'src/executor/main.py'
    ]
    
    unsafe_defaults = 0
    
    for file_path in files_to_check:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查是否有不安全的默认值
            if '"production"' in content and 'default' in content.lower():
                print(f"⚠️ {file_path} 可能使用了不安全的默认值")
                unsafe_defaults += 1
        except Exception as e:
            print(f"❌ 检查 {file_path} 失败: {e}")
            unsafe_defaults += 1
    
    if unsafe_defaults == 0:
        print("✅ 默认环境值检查通过")
        return True
    else:
        print(f"❌ 发现 {unsafe_defaults} 个不安全的默认值")
        return False

def generate_final_report(results: dict):
    """生成最终报告"""
    print("\n" + "="*80)
    print("🎯 Athena Trader 安全修复验证报告")
    print("="*80)
    
    total_tests = len(results)
    passed_tests = sum(results.values())
    
    print(f"\n📊 测试结果概览:")
    print(f"   总测试数: {total_tests}")
    print(f"   通过测试: {passed_tests}")
    print(f"   失败测试: {total_tests - passed_tests}")
    print(f"   成功率: {passed_tests/total_tests*100:.1f}%")
    
    print(f"\n📋 详细结果:")
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    if all(results.values()):
        print(f"\n🎉 所有安全修复验证通过！")
        print(f"✨ 系统现在处于安全状态")
        print(f"\n💡 建议:")
        print(f"   1. 定期运行此验证脚本")
        print(f"   2. 在部署前进行安全审计")
        print(f"   3. 监控生产环境配置")
        return True
    else:
        failed_tests = [name for name, result in results.items() if not result]
        print(f"\n🚨 以下测试失败，需要进一步修复:")
        for test_name in failed_tests:
            print(f"   - {test_name}")
        
        print(f"\n⚠️ 系统仍存在安全风险")
        return False

def main():
    """主函数"""
    print("🔍 开始安全修复验证测试...")
    print()
    
    # 加载环境变量
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ 环境变量已加载")
    except ImportError:
        print("⚠️ 未安装python-dotenv，部分测试可能失败")
    
    print()
    
    # 运行所有测试
    results = {}
    
    results['环境配置验证'] = test_environment_validation()
    results['风险管理服务修复'] = test_risk_manager_fix()
    results['执行服务安全验证'] = test_executor_security()
    results['数据管理服务一致性'] = test_data_manager_consistency()
    results['默认环境值安全'] = test_default_environment_values()
    
    # 生成最终报告
    success = generate_final_report(results)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
