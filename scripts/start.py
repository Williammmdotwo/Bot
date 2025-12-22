#!/usr/bin/env python3
"""
Athena Trader 统一启动脚本
提供简化的启动入口，内部调用核心脚本
"""

import sys
import os
import subprocess
from pathlib import Path

# 项目根目录
project_root = Path(__file__).parent.parent

def main():
    """主启动函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Athena Trader 启动器")
    parser.add_argument("mode", choices=["dev", "trading", "test"],
                       help="启动模式: dev=开发环境, trading=交易环境, test=测试环境")
    parser.add_argument("--action", default="start",
                       choices=["start", "stop", "status", "restart", "cleanup"],
                       help="操作类型")
    parser.add_argument("--test", default="simple_trading_test",
                       help="测试名称 (仅用于test模式)")

    # 解析已知参数，其余参数传递给子脚本
    args, remaining = parser.parse_known_args()

    try:
        if args.mode == "dev":
            # 开发环境管理
            cmd = [
                sys.executable,
                str(project_root / "scripts" / "core" / "local_dev_manager.py"),
                args.action
            ]

            if args.action == "test":
                cmd.extend(["--test", args.test])

        elif args.mode == "trading":
            # 交易环境
            if args.action != "start":
                print("交易模式只支持 start 操作")
                sys.exit(1)

            cmd = [
                sys.executable,
                str(project_root / "scripts" / "core" / "start_trading.py")
            ]

        elif args.mode == "test":
            # 测试环境
            if args.action != "start":
                print("测试模式只支持 start 操作")
                sys.exit(1)

            cmd = [
                sys.executable,
                str(project_root / "tests" / "run_all_tests.py")
            ]

            if args.test != "simple_trading_test":
                cmd.extend([args.test])

        # 设置环境变量
        env = os.environ.copy()
        env['PYTHONPATH'] = str(project_root / "src")

        # 执行命令
        print(f"🚀 启动 Athena Trader [{args.mode}] 模式...")
        result = subprocess.run(cmd, cwd=project_root, env=env)

        if result.returncode != 0:
            print(f"❌ 启动失败，退出码: {result.returncode}")
            sys.exit(result.returncode)

    except KeyboardInterrupt:
        print("\n👋 用户中断操作")
    except Exception as e:
        print(f"❌ 启动过程中发生错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
