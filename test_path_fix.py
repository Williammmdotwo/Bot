#!/usr/bin/env python3
"""
测试日志路径修复效果
验证环境变量和路径配置是否正常工作
"""

import os
import sys
sys.path.insert(0, '.')

def test_path_configuration():
    """测试路径配置"""
    print("🔍 测试日志路径配置...")

    # 测试环境变量读取
    logs_dir_env = os.getenv('LOGS_DIRECTORY')
    print(f"环境变量 LOGS_DIRECTORY: {logs_dir_env}")

    # 测试日志配置模块
    try:
        from src.utils.logging_config import setup_logging
        import logging

        print("✅ 日志配置模块导入成功")

        # 测试日志初始化
        setup_logging()
        logger = logging.getLogger(__name__)
        logger.info("🧪 测试日志路径配置")

        # 检查实际使用的日志文件路径
        handlers = logger.handlers
        for handler in handlers:
            if hasattr(handler, 'baseFilename'):
                print(f"📝 实际日志文件路径: {handler.baseFilename}")
                break

        print("✅ 日志系统初始化成功")

    except Exception as e:
        print(f"❌ 日志配置失败: {e}")
        return False

    return True

def test_cleanup_config():
    """测试清理配置"""
    print("\n🧹 测试清理配置...")

    try:
        import json
        with open('scripts/log_cleanup_config.json', 'r') as f:
            config = json.load(f)

        logs_dir = config['cleanup_settings']['logs_directory']
        print(f"📁 清理配置中的日志目录: '{logs_dir}' (空表示使用默认)")

        # 获取当前环境变量
        logs_dir_env = os.getenv('LOGS_DIRECTORY')

        # 测试环境变量优先级
        effective_dir = logs_dir_env or logs_dir or "logs"
        print(f"🎯 实际使用的日志目录: {effective_dir}")

        return True

    except Exception as e:
        print(f"❌ 清理配置读取失败: {e}")
        return False

def test_server_path_simulation():
    """模拟服务器环境测试"""
    print("\n🖥️ 模拟服务器环境配置...")

    # 模拟服务器环境变量
    original_env = os.environ.get('LOGS_DIRECTORY')

    # 设置为服务器路径
    os.environ['LOGS_DIRECTORY'] = '/home/eon/bot/logs'

    print(f"🔧 设置服务器路径: /home/eon/bot/logs")

    # 重新测试
    success = test_path_configuration()

    # 恢复原始环境
    if original_env:
        os.environ['LOGS_DIRECTORY'] = original_env
    else:
        os.environ.pop('LOGS_DIRECTORY', None)

    return success

def main():
    """主测试函数"""
    print("🚀 开始日志路径修复验证测试")
    print("=" * 50)

    # 测试当前环境
    test1 = test_path_configuration()
    test2 = test_cleanup_config()
    test3 = test_server_path_simulation()

    print("\n" + "=" * 50)
    print("📋 测试总结:")

    if test1 and test2 and test3:
        print("✅ 所有路径配置测试通过")
        print("\n🎯 使用说明:")
        print("1. 开发环境: LOGS_DIRECTORY 留空，自动使用 ./logs")
        print("2. 服务器环境: LOGS_DIRECTORY=/home/eon/bot/logs")
        print("3. 系统会自动创建目录和处理路径问题")
        print("4. 日志文件会根据配置写入正确位置")
    else:
        print("❌ 部分测试失败，请检查配置")

    print("\n🔧 服务器部署步骤:")
    print("1. 在服务器上编辑 .env 文件")
    print("2. 添加: LOGS_DIRECTORY=/home/eon/bot/logs")
    print("3. 重启服务或运行清理脚本")

if __name__ == "__main__":
    main()
