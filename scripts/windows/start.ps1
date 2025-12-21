# Athena Trader PowerShell 启动脚本

# 检查PowerShell执行策略
$executionPolicy = Get-ExecutionPolicy -Scope CurrentUser
if ($executionPolicy -eq "Restricted") {
    Write-Host "⚠️  PowerShell执行策略受限，正在设置执行策略..." -ForegroundColor Yellow
    try {
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
        Write-Host "✅ 执行策略已设置为 RemoteSigned" -ForegroundColor Green
    } catch {
        Write-Host "❌ 无法设置执行策略，请以管理员身份运行" -ForegroundColor Red
        Write-Host "或者手动执行: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser" -ForegroundColor Yellow
        Read-Host "按任意键退出..."
        exit 1
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    启动 Athena Trader" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Docker
try {
    $dockerVersion = docker --version 2>$null
    Write-Host "✅ Docker 已安装: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker 未安装或未在 PATH 中" -ForegroundColor Red
    Write-Host "请先安装 Docker Desktop: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
    Read-Host "按任意键退出..."
    exit 1
}

# 检查 Docker Desktop 运行状态
try {
    $dockerInfo = docker info 2>$null
    Write-Host "✅ Docker Desktop 正在运行" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker Desktop 未运行" -ForegroundColor Red
    Write-Host "请启动 Docker Desktop" -ForegroundColor Yellow
    Read-Host "按任意键退出..."
    exit 1
}

# 切换到项目目录
Set-Location "d:\AI\B\athena-trader"
Write-Host "📁 切换到项目目录: $(Get-Location)" -ForegroundColor Blue

# 检查配置文件
if (Test-Path ".env") {
    Write-Host "✅ 配置文件 .env 存在" -ForegroundColor Green
} else {
    Write-Host "⚠️  配置文件 .env 不存在，将使用默认配置" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🚀 正在启动服务..." -ForegroundColor Yellow

# 尝试启动服务
try {
    $result = docker compose up -d 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ 服务启动成功！" -ForegroundColor Green
    } else {
        Write-Host "❌ docker compose 失败，尝试 docker-compose..." -ForegroundColor Red
        $result = docker-compose up -d 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ 服务启动成功！（使用 docker-compose）" -ForegroundColor Green
        } else {
            Write-Host "❌ 服务启动失败" -ForegroundColor Red
            Write-Host "错误信息: $result" -ForegroundColor Red
            Read-Host "按任意键退出..."
            exit 1
        }
    }
} catch {
    Write-Host "❌ 启动过程中发生异常" -ForegroundColor Red
    Write-Host "错误信息: $_" -ForegroundColor Red
    Read-Host "按任意键退出..."
    exit 1
}

Write-Host ""
Write-Host "📊 检查服务状态..." -ForegroundColor Blue

# 显示服务状态
try {
    docker compose ps
} catch {
    Write-Host "❌ 无法获取服务状态" -ForegroundColor Red
}

Write-Host ""
Write-Host "🌐 打开浏览器..." -ForegroundColor Blue

# 打开浏览器
try {
    Start-Process "http://localhost:3000"
    Write-Host "✅ 浏览器已打开: http://localhost:3000" -ForegroundColor Green
} catch {
    Write-Host "❌ 无法自动打开浏览器" -ForegroundColor Red
    Write-Host "请手动访问: http://localhost:3000" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    启动完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📱 访问地址:" -ForegroundColor Blue
Write-Host "   主界面: http://localhost:3000" -ForegroundColor White
Write-Host "   API 文档: http://localhost:8001/docs" -ForegroundColor White
Write-Host ""
Write-Host "🔧 管理命令:" -ForegroundColor Blue
Write-Host "   查看状态: docker compose ps" -ForegroundColor White
Write-Host "   查看日志: docker compose logs -f" -ForegroundColor White
Write-Host "   停止服务: docker compose down" -ForegroundColor White
Write-Host ""
Write-Host "按任意键关闭此窗口..." -ForegroundColor Gray
Read-Host
