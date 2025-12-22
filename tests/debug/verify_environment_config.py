#!/usr/bin/env python3
"""
环境配置安全验证脚本
验证所有服务的交易模式配置是否正确和安全
"""

import os
import sys
import logging
from typing import Dict, List, Tuple

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("警告: 未安装python-dotenv，请运行: pip install python-dotenv")

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_environment_variables() -> Dict[str, any]:
    """检查所有环境变量"""
    env_vars = {}
    
    # 核心环境变量
    env_vars['OKX_ENVIRONMENT'] = os.getenv('OKX_ENVIRONMENT', 'NOT_SET')
    env_vars['ATHENA_ENV'] = os.getenv('ATHENA_ENV', 'NOT_SET')
    env_vars['USE_DATABASE'] = os.getenv('USE_DATABASE', 'false')
    
    # OKX API 密钥
    env_vars['OKX_DEMO_API_KEY'] = os.getenv('OKX_DEMO_API_KEY', 'NOT_SET')
    env_vars['OKX_DEMO_SECRET'] = os.getenv('OKX_DEMO_SECRET', 'NOT_SET')
    env_vars['OKX_DEMO_PASSPHRASE'] = os.getenv('OKX_DEMO_PASSPHRASE', 'NOT_SET')
    
    env_vars['OKX_API_KEY'] = os.getenv('OKX_API_KEY', 'NOT_SET')
    env_vars['OKX_SECRET'] = os.getenv('OKX_SECRET', 'NOT_SET')
    env_vars['OKX_PASSPHRASE'] = os.getenv('OKX_PASSPHRASE', 'NOT_SET')
    
    # 风控API密钥
    env_vars['OKX_RISK_API_KEY'] = os.getenv('OKX_RISK_API_KEY', 'NOT_SET')
    env_vars['OKX_RISK_SECRET'] = os.getenv('OKX_RISK_SECRET', 'NOT_SET')
    env_vars['OKX_RISK_PASSPHRASE'] = os.getenv('OKX_RISK_PASSPHRASE', 'NOT_SET')
    
    return env_vars

def validate_environment_config(env_vars: Dict[str, any]) -> List[Tuple[str, str, str]]:
    """验证环境配置"""
    issues = []
    
    # 1. 检查核心环境变量
    if env_vars['OKX_ENVIRONMENT'] == 'NOT_SET':
        issues.append(('CRITICAL', 'OKX_ENVIRONMENT', '环境变量未设置'))
    
    # 2. 检查环境值
    okx_env = env_vars['OKX_ENVIRONMENT'].lower()
    if okx_env not in ['demo', 'demo环境', 'demo-trading', 'production']:
        issues.append(('WARNING', 'OKX_ENVIRONMENT', f'无效的环境值: {env_vars["OKX_ENVIRONMENT"]}'))
    
    # 3. 检查API密钥配置
    is_demo = okx_env in ['demo', 'demo环境', 'demo-trading']
    
    if is_demo:
        # Demo环境检查
        if env_vars['OKX_DEMO_API_KEY'] == 'NOT_SET':
            issues.append(('CRITICAL', 'OKX_DEMO_API_KEY', 'Demo环境缺少API密钥'))
        if env_vars['OKX_DEMO_SECRET'] == 'NOT_SET':
            issues.append(('CRITICAL', 'OKX_DEMO_SECRET', 'Demo环境缺少Secret'))
        if env_vars['OKX_DEMO_PASSPHRASE'] == 'NOT_SET':
            issues.append(('CRITICAL', 'OKX_DEMO_PASSPHRASE', 'Demo环境缺少Passphrase'))
        
        # 检查是否意外配置了生产环境密钥
        if (env_vars['OKX_API_KEY'] != 'NOT_SET' and 
            env_vars['OKX_API_KEY'] != 'your_okx_api_key_here'):
            issues.append(('WARNING', 'OKX_API_KEY', 'Demo环境下配置了生产API密钥'))
    else:
        # 生产环境检查
        if env_vars['OKX_API_KEY'] == 'NOT_SET':
            issues.append(('CRITICAL', 'OKX_API_KEY', '生产环境缺少API密钥'))
        if env_vars['OKX_SECRET'] == 'NOT_SET':
            issues.append(('CRITICAL', 'OKX_SECRET', '生产环境缺少Secret'))
        if env_vars['OKX_PASSPHRASE'] == 'NOT_SET':
            issues.append(('CRITICAL', 'OKX_PASSPHRASE', '生产环境缺少Passphrase'))
    
    # 4. 检查风控密钥
    if env_vars['OKX_RISK_API_KEY'] == 'NOT_SET':
        issues.append(('CRITICAL', 'OKX_RISK_API_KEY', '风控API密钥未设置'))
    if env_vars['OKX_RISK_SECRET'] == 'NOT_SET':
        issues.append(('CRITICAL', 'OKX_RISK_SECRET', '风控Secret未设置'))
    if env_vars['OKX_RISK_PASSPHRASE'] == 'NOT_SET':
        issues.append(('CRITICAL', 'OKX_RISK_PASSPHRASE', '风控Passphrase未设置'))
    
    # 5. 安全检查
    if not is_demo:
        issues.append(('CRITICAL', 'SAFETY', '当前配置为生产交易环境，存在真实交易风险'))
    
    return issues

def check_code_consistency() -> List[Tuple[str, str, str]]:
    """检查代码中的环境判断一致性"""
    issues = []
    
    # 检查关键文件是否存在
    files_to_check = [
        'src/data_manager/websocket_client.py',
        'src/data_manager/rest_client.py',
        'src/risk_manager/actions.py',
        'src/executor/main.py',
        'src/strategy_engine/main.py'
    ]
    
    for file_path in files_to_check:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 检查是否使用了统一环境工具
            if 'from src.utils.environment_utils import' in content:
                # 使用统一工具的检查
                if 'get_environment_config()' not in content:
                    issues.append(('WARNING', file_path, '使用了统一环境工具但未调用get_environment_config'))
                if 'get_ccxt_config()' not in content and 'get_api_credentials()' not in content:
                    issues.append(('WARNING', file_path, '使用了统一环境工具但未调用配置函数'))
            else:
                # 未使用统一工具的检查
                if 'OKX_ENVIRONMENT' not in content:
                    issues.append(('WARNING', file_path, '未使用OKX_ENVIRONMENT或统一环境工具'))
                else:
                    # 检查是否有不安全的环境变量使用
                    if 'OKX_SANDBOX' in content:
                        issues.append(('CRITICAL', file_path, '使用了过时的OKX_SANDBOX变量'))
                    
                    # 检查默认值
                    if '"production"' in content and 'default' in content.lower():
                        issues.append(('WARNING', file_path, '使用了不安全的默认值production'))
                
        except FileNotFoundError:
            issues.append(('ERROR', file_path, '文件不存在'))
        except Exception as e:
            issues.append(('ERROR', file_path, f'读取失败: {e}'))
    
    return issues

def generate_security_report(env_vars: Dict[str, any], env_issues: List[Tuple[str, str, str]], code_issues: List[Tuple[str, str, str]]) -> str:
    """生成安全报告"""
    report = []
    report.append("=" * 80)
    report.append("Athena Trader 环境配置安全验证报告")
    report.append("=" * 80)
    report.append("")
    
    # 环境概览
    report.append("环境配置概览:")
    report.append(f"   OKX_ENVIRONMENT: {env_vars['OKX_ENVIRONMENT']}")
    report.append(f"   ATHENA_ENV: {env_vars['ATHENA_ENV']}")
    report.append(f"   USE_DATABASE: {env_vars['USE_DATABASE']}")
    report.append("")
    
    # 安全评估
    okx_env = env_vars['OKX_ENVIRONMENT'].lower()
    is_demo = okx_env in ['demo', 'demo环境', 'demo-trading']
    
    if is_demo:
        report.append("安全状态: 当前为模拟交易环境")
    else:
        report.append("安全状态: 当前为生产交易环境")
    
    report.append("")
    
    # 环境变量问题
    if env_issues:
        report.append("环境变量问题:")
        for level, var_name, desc in env_issues:
            if level == 'CRITICAL':
                report.append(f"   [CRITICAL] {var_name}: {desc}")
            elif level == 'WARNING':
                report.append(f"   [WARNING] {var_name}: {desc}")
            else:
                report.append(f"   [INFO] {var_name}: {desc}")
        report.append("")
    else:
        report.append("环境变量检查通过")
        report.append("")
    
    # 代码一致性问题
    if code_issues:
        report.append("代码一致性问题:")
        for level, file_path, desc in code_issues:
            if level == 'CRITICAL':
                report.append(f"   [CRITICAL] {file_path}: {desc}")
            elif level == 'WARNING':
                report.append(f"   [WARNING] {file_path}: {desc}")
            else:
                report.append(f"   [INFO] {file_path}: {desc}")
        report.append("")
    else:
        report.append("代码一致性检查通过")
        report.append("")
    
    # 安全建议
    report.append("安全建议:")
    if not is_demo:
        report.append("   1. 立即设置 OKX_ENVIRONMENT=demo")
        report.append("   2. 确保使用Demo API密钥")
        report.append("   3. 在测试环境中验证配置")
    else:
        report.append("   1. 定期验证环境配置")
        report.append("   2. 监控日志中的环境切换")
        report.append("   3. 保持API密钥安全")
    
    report.append("")
    report.append("=" * 80)
    
    return "\n".join(report)

def main():
    """主函数"""
    print("开始环境配置安全验证...")
    print()
    
    # 1. 检查环境变量
    env_vars = check_environment_variables()
    
    # 2. 验证环境配置
    env_issues = validate_environment_config(env_vars)
    
    # 3. 检查代码一致性
    code_issues = check_code_consistency()
    
    # 4. 生成报告
    report = generate_security_report(env_vars, env_issues, code_issues)
    print(report)
    
    # 5. 确定退出码
    critical_issues = [issue for issue in env_issues + code_issues if issue[0] == 'CRITICAL']
    
    if critical_issues:
        print(f"\n发现 {len(critical_issues)} 个严重问题，请立即修复！")
        return 1
    else:
        print(f"\n环境配置安全验证通过")
        return 0

if __name__ == "__main__":
    sys.exit(main())
