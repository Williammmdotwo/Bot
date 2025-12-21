#!/usr/bin/env python3
"""
网络连接测试脚本
验证HTTPS连接到各个API服务器的可用性
"""

import requests
import time
import json
from datetime import datetime
import sys

def test_https_connection(url: str, name: str, timeout: int = 10) -> dict:
    """测试HTTPS连接"""
    result = {
        'name': name,
        'url': url,
        'success': False,
        'error': None,
        'response_time': None,
        'status_code': None
    }
    
    try:
        print(f"🔍 测试 {name}...")
        start_time = time.time()
        
        # 发送GET请求
        response = requests.get(url, timeout=timeout, verify=True)
        
        response_time = time.time() - start_time
        
        result.update({
            'success': True,
            'response_time': round(response_time * 1000, 2),  # 转换为毫秒
            'status_code': response.status_code
        })
        
        print(f"   ✅ {name} 连接成功 ({result['response_time']}ms)")
        
    except requests.exceptions.SSLError as e:
        result['error'] = f"SSL错误: {str(e)}"
        print(f"   ❌ {name} SSL错误: {str(e)[:100]}...")
        
    except requests.exceptions.ConnectionError as e:
        result['error'] = f"连接错误: {str(e)}"
        print(f"   ❌ {name} 连接错误: {str(e)[:100]}...")
        
    except requests.exceptions.Timeout as e:
        result['error'] = f"超时: {str(e)}"
        print(f"   ❌ {name} 连接超时")
        
    except requests.exceptions.RequestException as e:
        result['error'] = f"请求错误: {str(e)}"
        print(f"   ❌ {name} 请求错误: {str(e)[:100]}...")
        
    except Exception as e:
        result['error'] = f"未知错误: {str(e)}"
        print(f"   ❌ {name} 未知错误: {str(e)[:100]}...")
    
    return result

def main():
    """主函数"""
    print("=" * 70)
    print("🌐 网络连接测试 - 验证HTTPS连接可用性")
    print("=" * 70)
    print(f"📅 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 测试目标列表
    test_targets = [
        {
            'url': 'https://www.okx.com/api/v5/public/instruments?instType=SPOT',
            'name': 'OKX API (www.okx.com)',
            'critical': True
        },
        {
            'url': 'https://okx.com/api/v5/public/instruments?instType=SPOT',
            'name': 'OKX API (okx.com)',
            'critical': True
        },
        {
            'url': 'https://api.binance.com/api/v3/ping',
            'name': 'Binance API',
            'critical': True
        },
        {
            'url': 'https://api.huobi.pro/v1/common/symbols',
            'name': 'Huobi API',
            'critical': True
        },
        {
            'url': 'https://jsonplaceholder.typicode.com/posts/1',
            'name': 'JSONPlaceholder (通用API)',
            'critical': False
        },
        {
            'url': 'https://httpbin.org/get',
            'name': 'HTTPBin (网络诊断)',
            'critical': False
        },
        {
            'url': 'https://www.google.com',
            'name': 'Google (基础HTTPS)',
            'critical': False
        },
        {
            'url': 'https://api.coinbase.com/v2/exchange-rates',
            'name': 'Coinbase API',
            'critical': True
        }
    ]
    
    # 执行测试
    results = []
    for target in test_targets:
        result = test_https_connection(target['url'], target['name'])
        result['critical'] = target['critical']
        results.append(result)
        print()  # 空行分隔
        time.sleep(0.5)  # 避免请求过快
    
    # 分析结果
    print("=" * 70)
    print("📊 测试结果分析")
    print("=" * 70)
    
    successful_tests = [r for r in results if r['success']]
    failed_tests = [r for r in results if not r['success']]
    critical_failed = [r for r in failed_tests if r['critical']]
    
    print(f"✅ 成功连接: {len(successful_tests)}/{len(results)}")
    print(f"❌ 连接失败: {len(failed_tests)}/{len(results)}")
    print(f"🚨 关键服务失败: {len(critical_failed)}/{len([r for r in results if r['critical']])}")
    print()
    
    # 详细结果
    print("📋 详细结果:")
    print("-" * 70)
    for result in results:
        status = "✅ 成功" if result['success'] else "❌ 失败"
        critical_mark = " 🔴" if result['critical'] and not result['success'] else ""
        
        print(f"{status}{critical_mark} {result['name']}")
        if result['success']:
            print(f"   响应时间: {result['response_time']}ms")
            print(f"   状态码: {result['status_code']}")
        else:
            print(f"   错误: {result['error']}")
        print()
    
    # 问题诊断
    print("=" * 70)
    print("🔍 问题诊断")
    print("=" * 70)
    
    if len(critical_failed) == 0:
        print("🎉 所有关键服务都可以正常连接！")
        print("   如果OKX仍然有问题，可能是API密钥或认证问题。")
        
    elif len(failed_tests) == len(results):
        print("🚨 所有HTTPS连接都失败！")
        print("   这可能是:")
        print("   1. 网络配置问题")
        print("   2. DNS解析问题") 
        print("   3. 防火墙/安全软件阻止")
        print("   4. 代理设置问题")
        
    elif 'okx.com' in [r['url'] for r in critical_failed]:
        print("🌍 OKX连接失败，但其他服务正常！")
        print("   这很可能是地域限制问题。")
        print("   建议解决方案:")
        print("   1. 使用VPN或代理（如Clash）")
        print("   2. 切换到其他交易所API")
        print("   3. 使用备用网络环境")
        
    else:
        print("⚠️ 部分服务连接失败")
        print("   可能是特定网站的网络问题")
    
    print()
    print("💡 建议:")
    if critical_failed:
        print("   1. 如果是地域限制，使用Clash等代理工具")
        print("   2. 考虑切换到Binance或Huobi等其他交易所")
        print("   3. 检查系统时间和SSL证书设置")
    
    # 保存结果
    report = {
        'test_time': datetime.now().isoformat(),
        'summary': {
            'total_tests': len(results),
            'successful': len(successful_tests),
            'failed': len(failed_tests),
            'critical_failed': len(critical_failed)
        },
        'results': results
    }
    
    report_file = 'network_connectivity_report.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 详细报告已保存到: {report_file}")
    
    # 返回退出码
    if len(critical_failed) > 0:
        return 1
    else:
        return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️ 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 测试过程中发生错误: {e}")
        sys.exit(1)
