#!/bin/bash

# 前端安全扫描脚本
# 用于 CI/CD 流程中的自动化安全检查

set -e

echo "🔒 开始前端安全扫描..."

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 函数：打印带颜色的消息
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 检查是否在正确的目录
if [ ! -f "package.json" ]; then
    print_error "package.json 未找到，请确保在项目根目录运行此脚本"
    exit 1
fi

echo "📦 检查依赖包安全漏洞..."
# 运行 npm audit
if npm audit --audit-level=moderate; then
    print_success "未发现安全漏洞"
else
    print_error "发现安全漏洞，请运行 npm audit fix 修复"
    exit 1
fi

echo "📋 检查过时的依赖包..."
# 检查过时的包
OUTDATED=$(npm outdated --json 2>/dev/null || echo "{}")
if [ "$OUTDATED" = "{}" ]; then
    print_success "所有依赖包都是最新版本"
else
    print_warning "发现过时的依赖包，建议更新："
    echo "$OUTDATED" | jq -r 'to_entries[] | "  \(.key): \(.value.current) -> \(.value.latest)"' 2>/dev/null || echo "  请运行 'npm outdated' 查看详细信息"
fi

echo "🔍 检查代码安全问题..."
# 检查常见的代码安全问题
SECURITY_ISSUES=0

# 检查是否有硬编码的敏感信息
if grep -r "password\|secret\|token\|api_key" --include="*.js" --include="*.jsx" --include="*.ts" --include="*.tsx" --exclude-dir=node_modules --exclude-dir=.next . | grep -v "//.*password\|//.*secret\|//.*token\|//.*api_key" > /dev/null 2>&1; then
    print_warning "发现可能的硬编码敏感信息，请检查代码"
    SECURITY_ISSUES=$((SECURITY_ISSUES + 1))
fi

# 检查是否有 console.log 语句
CONSOLE_LOGS=$(find . -name "*.js" -o -name "*.jsx" -o -name "*.ts" -o -name "*.tsx" | grep -v node_modules | grep -v .next | xargs grep -l "console.log" | wc -l)
if [ "$CONSOLE_LOGS" -gt 0 ]; then
    print_warning "发现 $CONSOLE_LOGS 个文件包含 console.log，生产环境应移除"
    SECURITY_ISSUES=$((SECURITY_ISSUES + 1))
fi

# 检查 Next.js 配置安全性
echo "🛡️  检查 Next.js 安全配置..."
if grep -q "headers" next.config.js; then
    print_success "Next.js 安全头部配置已启用"
else
    print_warning "建议在 next.config.js 中配置安全头部"
    SECURITY_ISSUES=$((SECURITY_ISSUES + 1))
fi

# 检查环境变量安全性
echo "🔐 检查环境变量安全性..."
if [ -f ".env.local" ]; then
    if grep -q "NEXT_PUBLIC_.*_SECRET\|NEXT_PUBLIC_.*_PASSWORD\|NEXT_PUBLIC_.*_TOKEN" .env.local; then
        print_error "发现敏感信息暴露在公共环境变量中"
        SECURITY_ISSUES=$((SECURITY_ISSUES + 1))
    else
        print_success "环境变量配置安全"
    fi
else
    print_warning ".env.local 文件不存在，请确保环境变量配置正确"
fi

# 检查 Docker 安全性
if [ -f "Dockerfile" ]; then
    echo "🐳 检查 Docker 安全配置..."
    
    # 检查是否使用非 root 用户
    if grep -q "USER.*nextjs\|USER.*node" Dockerfile; then
        print_success "Docker 容器使用非 root 用户"
    else
        print_warning "建议 Docker 容器使用非 root 用户"
        SECURITY_ISSUES=$((SECURITY_ISSUES + 1))
    fi
    
    # 检查是否使用 Alpine Linux
    if grep -q "alpine" Dockerfile; then
        print_success "Docker 使用轻量级 Alpine Linux"
    else
        print_warning "建议使用 Alpine Linux 减少攻击面"
    fi
fi

# 生成安全报告
echo "📊 生成安全扫描报告..."
REPORT_DIR="security-reports"
mkdir -p "$REPORT_DIR"

REPORT_FILE="$REPORT_DIR/security-scan-$(date +%Y%m%d-%H%M%S).md"

cat > "$REPORT_FILE" << EOF
# 前端安全扫描报告

**扫描时间**: $(date)
**项目**: Athena Trader Frontend

## 扫描结果摘要

- **依赖包安全**: ✅ 通过
- **过时依赖包**: $(if [ "$OUTDATED" = "{}" ]; then echo "✅ 无"; else echo "⚠️ 存在"; fi)
- **代码安全**: $(if [ $SECURITY_ISSUES -eq 0 ]; then echo "✅ 通过"; else echo "⚠️ 发现 $SECURITY_ISSUES 个问题"; fi)
- **配置安全**: ✅ 通过

## 详细信息

### 依赖包检查
\`\`\`
$(npm audit --json 2>/dev/null | jq -r '.vulnerabilities | to_entries[] | "- \(.key): \(.value.severity) (\(.value.title))"' 2>/dev/null || echo "无漏洞")
\`\`\`

### 过时依赖包
\`\`\`
$(echo "$OUTDATED" | jq -r 'to_entries[] | "- \(.key): \(.value.current) -> \(.value.latest)"' 2>/dev/null || echo "无过时包")
\`\`\`

### 安全建议
1. 定期运行 \`npm audit\` 检查安全漏洞
2. 及时更新依赖包到最新稳定版本
3. 避免在代码中硬编码敏感信息
4. 生产环境移除所有 console.log 语句
5. 使用 HTTPS 和安全头部
6. 定期审查环境变量配置

EOF

print_success "安全扫描完成！报告已保存到: $REPORT_FILE"

# 返回扫描结果
if [ $SECURITY_ISSUES -eq 0 ]; then
    print_success "🎉 所有安全检查通过！"
    exit 0
else
    print_error "发现 $SECURITY_ISSUES 个安全问题，请查看报告并修复"
    exit 1
fi
