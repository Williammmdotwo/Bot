@echo off
chcp 65001 >nul
echo ╔══════════════════════════════════════════════════════════════════════════════╗
echo ║                                                                              ║
echo ║   🚀 Athena OS v3.0 - 模拟运行模式                                           ║
echo ║                                                                              ║
echo ║   ⚠️  当前运行在 OKX Demo Trading 环境                                        ║
echo ║   💰 不涉及真实资金，仅用于测试和验证                                           ║
echo ║                                                                              ║
echo ╚══════════════════════════════════════════════════════════════════════════════╝
echo.
echo 正在启动模拟运行...
echo.

python "%~dp0run_simulation.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ 启动失败，错误代码: %ERRORLEVEL%
    echo.
    echo 请检查:
    echo   1. .env 文件是否已配置（必须设置 IS_SIMULATION=true）
    echo   2. OKX API 密钥是否正确
    echo   3. 依赖是否已安装（python-dotenv, psutil）
    echo.
    pause
)
