@echo off
setlocal enabledelayedexpansion

echo ╔════════════════════════════════════════════════════════════╗
echo ║              Athena Trader 测试快速启动                        ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM 获取脚本目录
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..

REM 切换到项目根目录
cd /d "%PROJECT_ROOT%"

REM 检查Python是否可用
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未找到Python，请确保Python已安装并添加到PATH
    pause
    exit /b 1
)

REM 检查项目结构
if not exist "src\data_manager\main.py" (
    echo ❌ 错误: 未找到项目源代码文件
    echo 请确保在正确的项目目录中运行此脚本
    pause
    exit /b 1
)

if not exist "tests\system\simple_trading_test.py" (
    echo ❌ 错误: 未找到测试文件
    echo 请确保测试文件存在
    pause
    exit /b 1
)

echo 🔍 检查依赖包...
python -c "import requests, flask" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ 警告: 可能缺少必要的依赖包
    echo 尝试安装依赖...
    pip install requests flask
    if errorlevel 1 (
        echo ❌ 依赖安装失败
        pause
        exit /b 1
    )
)

echo 🚀 启动自动化测试...
echo.

REM 运行自动化测试脚本
python scripts\run_test_with_services.py --test simple_trading_test

if errorlevel 1 (
    echo.
    echo ❌ 测试失败
    echo.
    echo 🔧 故障排除建议:
    echo   1. 检查端口 8000-8003 是否被占用
    echo   2. 确保所有依赖包已正确安装
    echo   3. 查看上面的错误信息
    echo   4. 尝试手动启动服务: python scripts\start_test_services.py start --wait
    echo.
) else (
    echo.
    echo ✅ 测试完成
    echo.
)

pause
