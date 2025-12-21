@echo off
setlocal enabledelayedexpansion

echo ========================================
echo    Athena Trader 本地开发管理器
echo ========================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误: Python 未安装或未在 PATH 中
    echo 请先安装 Python: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 切换到项目目录
cd /d "%~dp0..\.."
echo 📁 项目目录: %CD%
echo.

REM 显示菜单
:menu
echo 请选择操作:
echo 1. 启动所有服务
echo 2. 停止所有服务
echo 3. 重启所有服务
echo 4. 查看服务状态
echo 5. 运行测试
echo 6. 清理系统
echo 7. 退出
echo.
set /p choice="请输入选项 (1-7): "

if "%choice%"=="1" goto start
if "%choice%"=="2" goto stop
if "%choice%"=="3" goto restart
if "%choice%"=="4" goto status
if "%choice%"=="5" goto test
if "%choice%"=="6" goto cleanup
if "%choice%"=="7" goto exit

echo ❌ 无效选项，请重新选择
echo.
goto menu

:start
echo 🚀 启动本地开发服务...
python scripts\local_dev_manager.py start
if %errorlevel% equ 0 (
    echo ✅ 服务启动成功
) else (
    echo ❌ 服务启动失败
)
pause
goto menu

:stop
echo 🛑 停止所有服务...
python scripts\local_dev_manager.py stop
if %errorlevel% equ 0 (
    echo ✅ 所有服务已停止
) else (
    echo ❌ 停止服务失败
)
pause
goto menu

:restart
echo 🔄 重启所有服务...
python scripts\local_dev_manager.py restart
if %errorlevel% equ 0 (
    echo ✅ 所有服务重启成功
) else (
    echo ❌ 重启服务失败
)
pause
goto menu

:status
echo 📊 检查服务状态...
python scripts\local_dev_manager.py status
pause
goto menu

:test
echo 🧪 运行测试...
python scripts\local_dev_manager.py test
if %errorlevel% equ 0 (
    echo ✅ 测试通过
) else (
    echo ❌ 测试失败
)
pause
goto menu

:cleanup
echo 🧹 清理系统...
python scripts\local_dev_manager.py cleanup
if %errorlevel% equ 0 (
    echo ✅ 清理完成
) else (
    echo ❌ 清理失败
)
pause
goto menu

:exit
echo 👋 再见！
exit /b 0
