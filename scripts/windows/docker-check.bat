@echo off
chcp 65001 >nul
echo.
echo ========================================
echo    Docker 环境检查工具
echo ========================================
echo.

echo [1] 检查 Docker Desktop 是否安装...
docker --version >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Docker 已安装
    docker --version
) else (
    echo ❌ Docker 未安装或未在 PATH 中
    echo.
    echo 请先安装 Docker Desktop: https://www.docker.com/products/docker-desktop/
    pause
    exit /b
)

echo.
echo [2] 检查 Docker Desktop 是否运行...
docker info >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Docker Desktop 正在运行
) else (
    echo ❌ Docker Desktop 未运行
    echo.
    echo 请启动 Docker Desktop
    pause
    exit /b
)

echo.
echo [3] 检查 docker-compose 命令...
docker-compose --version >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ docker-compose 可用
    docker-compose --version
) else (
    echo ❌ docker-compose 不可用，尝试 docker compose...
    docker compose version >nul 2>&1
    if %errorlevel% equ 0 (
        echo ✅ docker compose 可用
        docker compose version
    ) else (
        echo ❌ Docker Compose 不可用
        pause
        exit /b
    )
)

echo.
echo [4] 检查项目文件...
if exist "docker-compose.yml" (
    echo ✅ docker-compose.yml 存在
) else (
    echo ❌ docker-compose.yml 不存在
    pause
    exit /b
)

if exist ".env" (
    echo ✅ .env 配置文件存在
) else (
    echo ⚠️  .env 配置文件不存在，将使用默认配置
    echo.
    echo 是否要复制示例配置文件？(Y/N)
    set /p copy_env=
    if /i "%copy_env%"=="Y" (
        copy .env.example .env
        echo ✅ 已复制 .env.example 到 .env
    )
)

echo.
echo [5] 检查端口占用...
netstat -ano | findstr :3000 >nul 2>&1
if %errorlevel% equ 0 (
    echo ⚠️  端口 3000 被占用
) else (
    echo ✅ 端口 3000 可用
)

netstat -ano | findstr :8001 >nul 2>&1
if %errorlevel% equ 0 (
    echo ⚠️  端口 8001 被占用
) else (
    echo ✅ 端口 8001 可用
)

echo.
echo ========================================
echo    检查完成！
echo ========================================
echo.
echo 如果所有检查都通过，可以运行 start.bat 启动服务
echo.
pause
