@echo off
REM 日志文件清理批处理脚本
REM 清理7天前的历史日志文件

echo ========================================
echo Athena Trader 日志清理脚本
echo ========================================
echo.

REM 获取脚本所在目录
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%\..\..
set LOG_DIR=%PROJECT_ROOT%\logs

echo 项目根目录: %PROJECT_ROOT%
echo 日志目录: %LOG_DIR%
echo.

REM 检查Python是否可用
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: Python 未安装或不在PATH中
    pause
    exit /b 1
)

REM 检查日志目录是否存在
if not exist "%LOG_DIR%" (
    echo 错误: 日志目录不存在: %LOG_DIR%
    pause
    exit /b 1
)

REM 执行日志清理脚本
echo 开始执行日志清理...
echo.

cd /d "%PROJECT_ROOT%"
python scripts\cleanup_logs.py --execute

if errorlevel 1 (
    echo.
    echo 错误: 日志清理失败
    pause
    exit /b 1
) else (
    echo.
    echo 日志清理完成!
)

echo.
echo ========================================
echo 清理完成时间: %date% %time%
echo ========================================
echo.

REM 可选: 暂停以查看结果（手动运行时使用）
REM pause

exit /b 0
