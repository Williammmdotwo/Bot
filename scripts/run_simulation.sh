#!/bin/bash

# Athena OS v3.0 - 模拟运行启动脚本 (Linux/Mac)

# 打印横幅
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                              ║"
echo "║   🚀 Athena OS v3.0 - 模拟运行模式                                           ║"
echo "║                                                                              ║"
echo "║   ⚠️  当前运行在 OKX Demo Trading 环境                                        ║"
echo "║   💰 不涉及真实资金，仅用于测试和验证                                           ║"
echo "║                                                                              ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "正在启动模拟运行..."
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 运行 Python 脚本
python3 "$SCRIPT_DIR/run_simulation.py"

# 检查退出代码
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ 启动失败"
    echo ""
    echo "请检查:"
    echo "  1. .env 文件是否已配置（必须设置 IS_SIMULATION=true）"
    echo "  2. OKX API 密钥是否正确"
    echo "  3. 依赖是否已安装（python-dotenv, psutil）"
    echo ""
    echo "安装依赖："
    echo "  pip install python-dotenv psutil"
    echo ""
    exit 1
fi
