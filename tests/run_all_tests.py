#!/usr/bin/env python3
"""
运行所有数据管理服务测试的便捷脚本
Convenient Script to Run All Data Manager Service Tests
"""

import os
import sys
import subprocess
import time
import json
from pathlib import Path

def run_test_script(script_name, description):
    """运行单个测试脚本"""
    print(f"\n{'='*60}")
    print(f"运行测试: {description}")
    print(f"脚本: {script_name}")
    print('='*60)
    
    try:
        start_time = time.time()
        result = subprocess.run(
            [sys.executable, script_name],
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        
        execution_time = time.time() - start_time
        
        print(f"\n执行时间: {execution_time:.2f}秒")
        print(f"退出码: {result.returncode}")
        
        if result.stdout:
            print("\n标准输出:")
            print(result.stdout)
        
        if result.stderr:
            print("\n标准错误:")
            print(result.stderr)
        
        return {
            'script': script_name,
            'description': description,
            'exit_code': result.returncode,
            'execution_time': execution_time,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0
        }
        
    except subprocess.TimeoutExpired:
        print(f"\n❌ 测试超时 (5分钟)")
        return {
            'script': script_name,
            'description': description,
            'exit_code': -1,
            'execution_time': 300,
            'stdout': '',
            'stderr': 'Test timeout after 5 minutes',
            'success': False
        }
    except Exception as e:
        print(f"\n❌ 测试执行异常: {e}")
        return {
            'script': script_name,
            'description': description,
            'exit_code': -2,
            'execution_time': 0,
            'stdout': '',
            'stderr': str(e),
            'success': False
        }

def main():
    """主函数"""
    print("数据管理服务测试套件")
    print("="*60)
    print("此脚本将运行所有测试来验证数据管理服务的功能")
    print()
    
    # 确保在正确的目录中
    script_dir = Path(__file__).parent
    os.chdir(script_dir.parent)
    
    print(f"当前工作目录: {os.getcwd()}")
    print(f"脚本目录: {script_dir}")
    
    # 定义要运行的测试脚本
    test_scripts = [
        {
            'script': 'tests/integration/test_api_endpoint.py',
            'description': 'API端点测试'
        },
        {
            'script': 'tests/unit/test_technical_indicators.py',
            'description': '技术指标计算测试'
        },
        {
            'script': 'tests/integration/test_data_manager_service.py',
            'description': '综合服务测试'
        }
    ]
    
    # 运行所有测试
    all_results = []
    total_start_time = time.time()
    
    for test_config in test_scripts:
        result = run_test_script(
            test_config['script'],
            test_config['description']
        )
        all_results.append(result)
        
        # 如果测试失败，询问是否继续
        if not result['success']:
            print(f"\n⚠️ 测试失败: {test_config['description']}")
            try:
                response = input("是否继续运行下一个测试? (y/n): ").lower().strip()
                if response not in ['y', 'yes', '']:
                    print("测试被用户中断")
                    break
            except KeyboardInterrupt:
                print("\n测试被用户中断")
                break
    
    total_execution_time = time.time() - total_start_time
    
    # 生成测试总结
    print(f"\n{'='*60}")
    print("测试套件总结")
    print('='*60)
    
    total_tests = len(all_results)
    passed_tests = sum(1 for r in all_results if r['success'])
    failed_tests = total_tests - passed_tests
    
    print(f"总测试数: {total_tests}")
    print(f"通过: {passed_tests}")
    print(f"失败: {failed_tests}")
    print(f"成功率: {(passed_tests/total_tests*100):.1f}%")
    print(f"总执行时间: {total_execution_time:.2f}秒")
    
    print("\n详细结果:")
    for i, result in enumerate(all_results, 1):
        status = "✅ 通过" if result['success'] else "❌ 失败"
        print(f"{i}. {result['description']}: {status} ({result['execution_time']:.2f}s)")
        if not result['success']:
            print(f"   退出码: {result['exit_code']}")
            if result['stderr']:
                print(f"   错误: {result['stderr'][:100]}...")
    
    # 保存测试结果
    test_results = {
        'test_suite': 'data_manager_service_complete',
        'timestamp': time.time(),
        'total_execution_time': total_execution_time,
        'summary': {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': failed_tests,
            'success_rate': passed_tests/total_tests*100 if total_tests > 0 else 0
        },
        'individual_results': all_results
    }
    
    results_file = 'complete_test_results.json'
    try:
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(test_results, f, indent=2, ensure_ascii=False)
        print(f"\n测试结果已保存到: {results_file}")
    except Exception as e:
        print(f"\n保存测试结果失败: {e}")
    
    # 返回适当的退出码
    if failed_tests == 0:
        print("\n🎉 所有测试通过!")
        sys.exit(0)
    else:
        print(f"\n⚠️ 有 {failed_tests} 个测试失败")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n测试套件执行失败: {e}")
        sys.exit(1)
