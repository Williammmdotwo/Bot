#!/usr/bin/env python3
"""
后台启动executor服务的脚本

该脚本用于在Windows环境下后台启动Athena Trader的executor服务。
executor服务负责执行交易订单和管理交易状态。

功能:
- 后台启动executor服务进程
- 等待服务初始化完成
- 执行健康检查验证服务状态
- 提供启动状态反馈

使用方法:
    python start_executor_background.py

作者: Athena Trader Team
版本: 1.0.0
"""

import os
import subprocess
import sys
import time

import requests


def start_executor():
    """
    在后台启动executor服务
    
    启动流程:
    1. 切换到项目根目录
    2. 启动executor服务进程
    3. 等待5秒让服务初始化
    4. 执行健康检查
    5. 返回启动结果
    
    Returns:
        bool: 启动成功返回True，失败返回False
    """
    try:
        # 切换到athena-trader目录
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        os.chdir(project_root)
        
        # 启动executor服务
        process = subprocess.Popen([
            sys.executable, "src/executor/main.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        print(f"Executor服务已启动，进程ID: {process.pid}")
        
        # 等待服务启动
        time.sleep(5)
        
        # 检查服务是否正常运行
        try:
            response = requests.get("http://localhost:8002/health", timeout=5)
            if response.status_code == 200:
                print("✅ Executor服务启动成功并运行正常")
                return True
            else:
                print(f"❌ Executor服务响应异常: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Executor服务健康检查失败: {e}")
            return False
            
    except Exception as e:
        print(f"❌ 启动Executor服务失败: {e}")
        return False

if __name__ == "__main__":
    success = start_executor()
    if success:
        print("🎉 Executor服务后台启动成功")
    else:
        print("⚠️ Executor服务启动失败，请检查日志")
