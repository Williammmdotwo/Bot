@echo off
:: 设置控制台编码为UTF-8
chcp 65001 >nul 2>&1
:: 如果UTF-8失败，尝试GBK
if %errorlevel% neq 0 chcp 936 >nul 2>&1
:: 设置窗口标题
title Athena Trader 管理工具

:menu
cls
echo.
echo  Athena Trader 管理菜单
echo.
echo  1. 启动服务
echo  2. 停止服务
echo  3. 重启服务
echo  4. 查看状态
echo  5. 查看日志
echo  6. 打开界面
echo  7. 退出
echo.
set /p choice=请选择操作 (1-7): 

if "%choice%"=="1" goto start
if "%choice%"=="2" goto stop
if "%choice%"=="3" goto restart
if "%choice%"=="4" goto status
if "%choice%"=="5" goto logs
if "%choice%"=="6" goto open
if "%choice%"=="7" goto exit

:start
cd /d d:\AI\B\athena-trader
echo 正在启动服务...
docker compose up -d >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ 启动完成！
) else (
    echo ❌ docker compose 失败，尝试 docker-compose...
    docker-compose up -d >nul 2>&1
    if %errorlevel% equ 0 (
        echo ✅ 启动完成！（使用 docker-compose）
    ) else (
        echo ❌ 启动失败
    )
)
pause
goto menu

:stop
cd /d d:\AI\B\athena-trader
echo 正在停止服务...
docker compose down >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ 停止完成！
) else (
    echo ❌ docker compose 失败，尝试 docker-compose...
    docker-compose down >nul 2>&1
    if %errorlevel% equ 0 (
        echo ✅ 停止完成！（使用 docker-compose）
    ) else (
        echo ❌ 停止失败
    )
)
pause
goto menu

:restart
cd /d d:\AI\B\athena-trader
echo 正在重启服务...
docker compose restart >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ 重启完成！
) else (
    echo ❌ docker compose 失败，尝试 docker-compose...
    docker-compose restart >nul 2>&1
    if %errorlevel% equ 0 (
        echo ✅ 重启完成！（使用 docker-compose）
    ) else (
        echo ❌ 重启失败
    )
)
pause
goto menu

:status
cd /d d:\AI\B\athena-trader
echo 正在查看服务状态...
docker compose ps >nul 2>&1
if %errorlevel% neq 0 (
    echo docker compose 失败，尝试 docker-compose...
    docker-compose ps
) else (
    docker compose ps
)
pause
goto menu

:logs
cd /d d:\AI\B\athena-trader
echo 正在查看日志...
docker compose logs -f >nul 2>&1
if %errorlevel% neq 0 (
    echo docker compose 失败，尝试 docker-compose...
    docker-compose logs -f
) else (
    docker compose logs -f
)
goto menu

:open
start http://localhost:3000
goto menu

:exit
exit
