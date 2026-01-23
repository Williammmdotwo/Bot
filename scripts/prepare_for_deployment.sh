#!/bin/bash

# Athena OS - 服务器部署准备脚本
# 此脚本用于清理项目，准备上传到服务器

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                              ║"
echo "║   🚀 Athena OS - 服务器部署准备脚本                                        ║"
echo "║                                                                              ║"
echo "║   此脚本将清理项目，准备上传到新加坡服务器                                   ║"
echo "║                                                                              ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "📂 项目目录: $PROJECT_DIR"
echo ""

# 进入项目目录
cd "$PROJECT_DIR"

# 步骤 1: 清理 Python 缓存
echo "🧹 步骤 1/5: 清理 Python 缓存..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
echo "   ✅ __pycache__ 已清理"
echo ""

# 步骤 2: 清理 pytest 缓存
echo "🧹 步骤 2/5: 清理 pytest 缓存..."
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache 2>/dev/null || true
echo "   ✅ .pytest_cache 已清理"
echo ""

# 步骤 3: 删除覆盖率文件
echo "🧹 步骤 3/5: 删除覆盖率文件..."
rm -f .coverage 2>/dev/null || true
rm -rf htmlcov/ 2>/dev/null || true
rm -rf tests/reports/html/ 2>/dev/null || true
echo "   ✅ 覆盖率文件已删除"
echo ""

# 步骤 4: 删除日志文件
echo "🧹 步骤 4/5: 删除日志文件..."
rm -f logs/*.log 2>/dev/null || true
rm -rf logs/simulation/ 2>/dev/null || true
echo "   ✅ 日志文件已删除"
echo ""

# 步骤 5: 检查项目结构
echo "🔍 步骤 5/5: 检查项目结构..."
ERRORS=0

# 检查不应该存在的文件
if [ -f "conftest.py" ]; then
    echo "   ❌ 错误: 根目录存在 conftest.py"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ 根目录没有 conftest.py"
fi

if [ -d ".pytest_cache" ]; then
    echo "   ❌ 错误: 根目录存在 .pytest_cache"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ 根目录没有 .pytest_cache"
fi

if [ -d "tests_legacy_archive_"* ]; then
    echo "   ❌ 错误: 根目录存在 tests_legacy_archive_*"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ 根目录没有 tests_legacy_archive_*"
fi

# 检查必要文件是否存在
if [ -f "main.py" ]; then
    echo "   ✅ main.py 存在"
else
    echo "   ❌ 错误: main.py 不存在"
    ERRORS=$((ERRORS + 1))
fi

if [ -f "requirements.txt" ]; then
    echo "   ✅ requirements.txt 存在"
else
    echo "   ❌ 错误: requirements.txt 不存在"
    ERRORS=$((ERRORS + 1))
fi

if [ -f ".env.example" ]; then
    echo "   ✅ .env.example 存在"
else
    echo "   ❌ 错误: .env.example 不存在"
    ERRORS=$((ERRORS + 1))
fi

if [ -f "scripts/run_simulation.py" ]; then
    echo "   ✅ scripts/run_simulation.py 存在"
else
    echo "   ❌ 错误: scripts/run_simulation.py 不存在"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# 总结
if [ $ERRORS -eq 0 ]; then
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║                                                                              ║"
    echo "║   ✅ 项目准备完成！可以安全上传到服务器                                     ║"
    echo "║                                                                              ║"
    echo "║   下一步：                                                                   ║"
    echo "║   1. 压缩项目：tar -czf athena-trader-clean.tar.gz --exclude='.git' .        ║"
    echo "║   2. 上传到服务器：scp athena-trader-clean.tar.gz user@server:/path/          ║"
    echo "║   3. 查看部署指南：docs/DEPLOYMENT_CHECKLIST.md                             ║"
    echo "║                                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    exit 0
else
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║                                                                              ║"
    echo "║   ❌ 发现 $ERRORS 个错误，请修复后再上传                                     ║"
    echo "║                                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    exit 1
fi
