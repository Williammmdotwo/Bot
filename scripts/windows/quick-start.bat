@echo off
:: 设置控制台编码为UTF-8
chcp 65001 >nul 2>&1
:: 如果UTF-8失败，尝试GBK
if %errorlevel% neq 0 chcp 936 >nul 2>&1
:: 设置窗口标题
title Athena Trader 快速启动

echo.
echo ========================================
echo    Athena Trader 快速启动
echo ========================================
echo.

cd /d d:\AI\B\athena-trader

echo [1] 检查 Docker 环境...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker 未安装或未在 PATH 中
    echo.
    echo 请先安装 Docker Desktop: https://www.docker.com/products/docker-desktop/
    pause
    exit /b
)

docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker Desktop 未运行
    echo.
    echo 请启动 Docker Desktop
    pause
    exit /b
)

echo ✅ Docker 环境正常
echo.

echo [2] 启动服务...
docker compose up -d >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ 服务启动成功
) else (
    echo ❌ docker compose 失败，尝试 docker-compose...
    docker-compose up -d >nul 2>&1
    if %errorlevel% equ 0 (
        echo ✅ 服务启动成功（使用 docker-compose）
    ) else (
        echo ❌ 服务启动失败
        pause
        exit /b
    )
)

echo.
echo [3] 检查服务状态...
timeout /t 3 /nobreak >nul
docker compose ps

echo.
echo [4] 打开浏览器...
timeout /t 2 /nobreak >nul
start http://localhost:3000

echo.
echo ========================================
echo    启动完成！
echo ========================================
echo.
echo 访问地址: http://localhost:3000
echo API 文档: http://localhost:8001/docs
echo.
echo 按任意键关闭此窗口...
pause >nul
