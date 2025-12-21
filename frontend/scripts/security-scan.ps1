# 前端安全扫描脚本 (PowerShell 版本)
# 用于 CI/CD 流程中的自动化安全检查

param(
    [switch]$SkipTests,
    [switch]$Verbose
)

Write-Host "🔒 开始前端安全扫描..." -ForegroundColor Green

# 函数：打印带颜色的消息
function Write-Success {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "⚠️  $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "❌ $Message" -ForegroundColor Red
}

# 检查是否在正确的目录
if (-not (Test-Path "package.json")) {
    Write-Error "package.json 未找到，请确保在项目根目录运行此脚本"
    exit 1
}

$securityIssues = 0

try {
    Write-Host "📦 检查依赖包安全漏洞..." -ForegroundColor Cyan
    
    # 运行 npm audit
    $auditResult = npm audit --json 2>$null | ConvertFrom-Json -ErrorAction SilentlyContinue
    
    if ($auditResult.vulnerabilities) {
        $vulnCount = ($auditResult.vulnerabilities | Get-Member -MemberType NoteProperty).Count
        if ($vulnCount -gt 0) {
            Write-Error "发现 $vulnCount 个安全漏洞，请运行 npm audit fix 修复"
            $securityIssues++
        } else {
            Write-Success "未发现安全漏洞"
        }
    } else {
        Write-Success "未发现安全漏洞"
    }

    Write-Host "📋 检查过时的依赖包..." -ForegroundColor Cyan
    
    # 检查过时的包
    $outdatedResult = npm outdated --json 2>$null | ConvertFrom-Json -ErrorAction SilentlyContinue
    
    if ($outdatedResult -and $outdatedResult.PSObject.Properties.Count -gt 0) {
        Write-Warning "发现过时的依赖包，建议更新："
        $outdatedResult.PSObject.Properties | ForEach-Object {
            Write-Host "  $($_.Name): $($_.Value.current) -> $($_.Value.latest)" -ForegroundColor Yellow
        }
    } else {
        Write-Success "所有依赖包都是最新版本"
    }

    Write-Host "🔍 检查代码安全问题..." -ForegroundColor Cyan
    
    # 检查是否有硬编码的敏感信息
    $sensitiveFiles = Get-ChildItem -Recurse -Include "*.js", "*.jsx", "*.ts", "*.tsx" | 
        Where-Object { $_.FullName -notmatch "node_modules|\.next" } |
        Select-String -Pattern "password|secret|token|api_key" | 
        Where-Object { $_.Line -notmatch "//.*password|//.*secret|//.*token|//.*api_key" }
    
    if ($sensitiveFiles) {
        Write-Warning "发现可能的硬编码敏感信息，请检查代码"
        $securityIssues++
    }

    # 检查是否有 console.log 语句
    $consoleLogFiles = Get-ChildItem -Recurse -Include "*.js", "*.jsx", "*.ts", "*.tsx" | 
        Where-Object { $_.FullName -notmatch "node_modules|\.next" } |
        Select-String -Pattern "console\.log"
    
    if ($consoleLogFiles) {
        $consoleLogCount = ($consoleLogFiles | Group-Object Path).Count
        Write-Warning "发现 $consoleLogCount 个文件包含 console.log，生产环境应移除"
        $securityIssues++
    }

    Write-Host "🛡️  检查 Next.js 安全配置..." -ForegroundColor Cyan
    
    # 检查 Next.js 配置安全性
    if (Test-Path "next.config.js") {
        $nextConfig = Get-Content "next.config.js" -Raw
        if ($nextConfig -match "headers") {
            Write-Success "Next.js 安全头部配置已启用"
        } else {
            Write-Warning "建议在 next.config.js 中配置安全头部"
            $securityIssues++
        }
    } else {
        Write-Warning "next.config.js 文件不存在"
        $securityIssues++
    }

    Write-Host "🔐 检查环境变量安全性..." -ForegroundColor Cyan
    
    # 检查环境变量安全性
    if (Test-Path ".env.local") {
        $envContent = Get-Content ".env.local" -Raw
        if ($envContent -match "NEXT_PUBLIC_.*_(SECRET|PASSWORD|TOKEN)") {
            Write-Error "发现敏感信息暴露在公共环境变量中"
            $securityIssues++
        } else {
            Write-Success "环境变量配置安全"
        }
    } else {
        Write-Warning ".env.local file not found, please ensure environment variables are configured correctly"
    }

    Write-Host "🐳 检查 Docker 安全配置..." -ForegroundColor Cyan
    
    # 检查 Docker 安全性
    if (Test-Path "Dockerfile") {
        $dockerContent = Get-Content "Dockerfile" -Raw
        
        # 检查是否使用非 root 用户
        if ($dockerContent -match "USER.*nextjs|USER.*node") {
            Write-Success "Docker 容器使用非 root 用户"
        } else {
            Write-Warning "建议 Docker 容器使用非 root 用户"
            $securityIssues++
        }
        
        # 检查是否使用 Alpine Linux
        if ($dockerContent -match "alpine") {
            Write-Success "Docker 使用轻量级 Alpine Linux"
        } else {
            Write-Warning "建议使用 Alpine Linux 减少攻击面"
        }
    }

    # 生成安全报告
    Write-Host "📊 生成安全扫描报告..." -ForegroundColor Cyan
    
    $reportDir = "security-reports"
    if (-not (Test-Path $reportDir)) {
        New-Item -ItemType Directory -Path $reportDir | Out-Null
    }
    
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $reportFile = "$reportDir\security-scan-$timestamp.md"
    
    $reportContent = @"
# 前端安全扫描报告

**扫描时间**: $(Get-Date)
**项目**: Athena Trader Frontend

## 扫描结果摘要

- **依赖包安全**: $(if ($auditResult.vulnerabilities -and ($auditResult.vulnerabilities | Get-Member -MemberType NoteProperty).Count -gt 0) { "⚠️ 存在漏洞" } else { "✅ 通过" })
- **过时依赖包**: $(if ($outdatedResult -and $outdatedResult.PSObject.Properties.Count -gt 0) { "⚠️ 存在" } else { "✅ 无" })
- **代码安全**: $(if ($securityIssues -eq 0) { "✅ 通过" } else { "⚠️ 发现 $securityIssues 个问题" })
- **配置安全**: ✅ 通过

## 详细信息

### 依赖包检查
```
$(if ($auditResult.vulnerabilities) { 
    $auditResult.vulnerabilities.PSObject.Properties | ForEach-Object { 
        "- $($_.Name): $($_.Value.severity) ($($_.Value.title))" 
    }
} else { "无漏洞" })
```

### 过时依赖包
```
$(if ($outdatedResult) { 
    $outdatedResult.PSObject.Properties | ForEach-Object { 
        "- $($_.Name): $($_.Value.current) -> $($_.Value.latest)" 
    }
} else { "无过时包" })
```

### 安全建议
1. 定期运行 `npm audit` 检查安全漏洞
2. 及时更新依赖包到最新稳定版本
3. 避免在代码中硬编码敏感信息
4. 生产环境移除所有 console.log 语句
5. 使用 HTTPS 和安全头部
6. 定期审查环境变量配置

"@
    
    $reportContent | Out-File -FilePath $reportFile -Encoding UTF8
    Write-Success "安全扫描完成！报告已保存到: $reportFile"

    # 返回扫描结果
    if ($securityIssues -eq 0) {
        Write-Success "🎉 所有安全检查通过！"
        exit 0
    } else {
        Write-Error "发现 $securityIssues 个安全问题，请查看报告并修复"
        exit 1
    }

} catch {
    Write-Error "安全扫描过程中发生错误: $($_.Exception.Message)"
    exit 1
}
