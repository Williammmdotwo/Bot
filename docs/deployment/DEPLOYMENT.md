# Athena Trader Docker 部署指南

## 概述

Athena Trader 是一个完全容器化的专业加密货币交易平台，采用微服务架构，支持一键部署和扩展。

## 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Nginx (生产环境)                        │
│                 ┌─────────────┐                        │
│                 │   HTTPS     │                        │
│                 └─────────────┘                        │
│                        │                                │
│         ┌────────────────┴────────────────┐             │
│         │     Frontend (Next.js)        │             │
│         │     Port: 3000                │             │
│         └─────────────────────────────────┘             │
│                        │                                │
│  ┌─────────────────┬─────────────────┬─────────────┐ │
│  │ Risk Service    │ Executor Service │ Strategy    │ │
│  │ Port: 8001     │ Port: 8002     │ Service     │ │
│  │                │                │ Port: 8003   │ │
│  └─────────────────┴─────────────────┴─────────────┘ │
│                        │                                │
│  ┌─────────────────┬─────────────────┐             │
│  │ Data Service    │ Risk Manager    │             │
│  │ Port: 8004     │                │             │
│  └─────────────────┴─────────────────┘             │
│                        │                                │
│  ┌─────────────────┬─────────────────┐             │
│  │ PostgreSQL      │ Redis           │             │
│  │ Port: 5432     │ Port: 6379     │             │
│  └─────────────────┴─────────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd athena-trader

# 复制环境变量模板
cp .env.example .env

# 编辑环境变量（重要！）
nano .env
```

### 2. 一键部署

```bash
# 给部署脚本执行权限
chmod +x deploy.sh

# 开发环境部署
./deploy.sh deploy-dev

# 生产环境部署
./deploy.sh deploy-prod
```

### 3. 验证部署

```bash
# 检查服务状态
./deploy.sh status

# 查看服务日志
./deploy.sh logs
```

## 详细配置

### 环境变量配置

#### 必需配置项

```bash
# 数据库配置
POSTGRES_USER=athena
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=athena_trader
REDIS_PASSWORD=your_redis_password

# 服务间通信令牌
INTERNAL_SERVICE_TOKEN=your_internal_token_change_this

# API 密钥（外部获取）
DATA_API_KEY=your_data_api_key
RISK_API_KEY=your_risk_api_key
EXECUTOR_API_KEY=your_executor_api_key
STRATEGY_API_KEY=your_strategy_api_key

# 外部服务
ALERT_WEBHOOK_URL=https://your-webhook-url.com/alerts
WALLET_CONNECT_PROJECT_ID=your_walletconnect_project_id
```

#### 可选配置项

```bash
# 日志级别
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR

# 配置路径
CONFIG_PATH=/app/config
```

### 服务端口分配

| 服务 | 内部端口 | 外部端口 | 用途 |
|------|----------|----------|------|
| Frontend | 3000 | 3000 | Web 界面 |
| Risk Service | 8001 | 8001 | 风险管理 |
| Executor Service | 8002 | 8002 | 订单执行 |
| Strategy Service | 8003 | 8003 | 策略引擎 |
| Data Service | 8004 | 8004 | 数据管理 |
| PostgreSQL | 5432 | 5432 | 数据库 |
| Redis | 6379 | 6379 | 缓存 |

### 网络配置

#### 内部网络
- **网络名称**: `athena-network`
- **子网**: `172.20.0.0/16`
- **通信方式**: 服务名（如 `http://risk-service:8001`）

#### 外部访问
- **开发环境**: 所有端口暴露给宿主机
- **生产环境**: 仅 Frontend (3000) 和 HTTPS (80, 443) 暴露

## 部署模式

### 开发环境

```bash
# 启动所有服务（包括数据库端口）
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f [service-name]
```

### 生产环境

```bash
# 启动生产服务（包含 Nginx）
docker-compose --profile production up -d

# 仅启动 API 服务（内部网络）
docker-compose --profile api-only up -d
```

## 数据持久化

### 数据库数据

```bash
# PostgreSQL 数据
volumes:
  - postgres_data:/var/lib/postgresql/data

# Redis 数据
volumes:
  - redis_data:/data
```

### 应用数据

```bash
# 配置文件
volumes:
  - ./config:/app/config:ro

# 日志文件
volumes:
  - ./logs:/app/logs

# 缓存数据
volumes:
  - service_cache:/app/cache
```

## 健康检查

所有服务都配置了健康检查：

```bash
# 检查服务健康状态
docker-compose ps

# 查看健康检查日志
docker inspect --format='{{json .State.Health}}' [container-name]
```

### 健康检查端点

| 服务 | 端点 | 预期响应 |
|------|--------|----------|
| 所有后端服务 | `/health` | `{"status": "healthy"}` |
| Frontend | `/` | `200 OK` |
| PostgreSQL | `pg_isready` | 连接成功 |
| Redis | `redis-cli ping` | `PONG` |

## 安全配置

### 网络安全

1. **内部网络隔离**: 服务间仅通过内部网络通信
2. **最小权限暴露**: 生产环境仅暴露必要端口
3. **令牌认证**: 内部服务间使用 `INTERNAL_SERVICE_TOKEN`
4. **HTTPS 强制**: 生产环境强制 HTTPS

### 容器安全

1. **非 root 用户**: 所有服务使用非特权用户运行
2. **只读挂载**: 配置文件以只读方式挂载
3. **资源限制**: 可配置 CPU 和内存限制
4. **安全扫描**: 集成 Trivy/Snyk 安全扫描

## 监控和日志

### 日志管理

```bash
# 查看所有服务日志
./deploy.sh logs

# 查看特定服务日志
./deploy.sh logs risk-service

# 实时跟踪日志
docker-compose logs -f --tail=100
```

### 性能监控

```bash
# 查看资源使用情况
docker stats

# 查看容器详细信息
docker inspect [container-name]
```

## 备份和恢复

### 自动备份

```bash
# 创建备份
./deploy.sh backup

# 备份内容：
# - 数据库 SQL 转储
# - Redis 数据文件
# - 配置文件
# - 日志文件
```

### 手动备份

```bash
# 数据库备份
docker-compose exec postgres pg_dump -U athena athena_trader > backup.sql

# Redis 备份
docker-compose exec redis redis-cli --rdb /tmp/dump.rdb
docker cp $(docker-compose ps -q redis):/tmp/dump.rdb redis.rdb
```

## 故障排除

### 常见问题

#### 1. 服务启动失败

```bash
# 查看详细错误
docker-compose logs [service-name]

# 检查端口冲突
netstat -tulpn | grep [port]

# 重新构建镜像
docker-compose build --no-cache [service-name]
```

#### 2. 数据库连接失败

```bash
# 检查数据库状态
docker-compose exec postgres pg_isready -U athena

# 检查网络连接
docker-compose exec risk-service ping postgres
```

#### 3. 内存不足

```bash
# 查看内存使用
docker stats --no-stream

# 清理未使用的镜像
docker system prune -f
```

### 调试模式

```bash
# 进入容器调试
docker-compose exec [service-name] /bin/bash

# 查看容器环境
docker-compose exec [service-name] env

# 重启特定服务
docker-compose restart [service-name]
```

## 扩展和优化

### 水平扩展

```bash
# 扩展特定服务
docker-compose up -d --scale risk-service=3

# 负载均衡配置
# Nginx 自动配置多个后端实例
```

### 性能优化

```bash
# 构建优化镜像
docker-compose build --no-cache --parallel

# 使用多阶段构建
# 已在 Dockerfile 中配置
```

## 生产部署最佳实践

### 1. 环境准备

```bash
# 更新系统
apt update && apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# 安装 Docker Compose
curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
```

### 2. 安全配置

```bash
# 配置防火墙
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw enable

# SSL 证书配置
mkdir -p nginx/ssl
cp your-cert.pem nginx/ssl/cert.pem
cp your-key.pem nginx/ssl/key.pem
```

### 3. 监控设置

```bash
# 安装监控工具
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  prom/prometheus

docker run -d \
  --name grafana \
  -p 3001:3000 \
  grafana/grafana
```

## CI/CD 集成

### GitHub Actions 示例

```yaml
name: Deploy Athena Trader
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Environment
        run: |
          echo "${{ secrets.POSTGRES_PASSWORD }}" >> .env
          echo "${{ secrets.INTERNAL_TOKEN }}" >> .env
          
      - name: Deploy Services
        run: |
          chmod +x deploy.sh
          ./deploy.sh deploy-prod
          
      - name: Health Check
        run: |
          ./deploy.sh status
```

## 维护和更新

### 滚动更新

```bash
# 零停机更新
docker-compose pull
docker-compose up -d --no-deps [service-name]

# 备份后更新
./deploy.sh backup
docker-compose pull
docker-compose up -d
```

### 版本管理

```bash
# 查看当前版本
docker-compose images

# 回滚到上一版本
docker-compose down
docker-compose up -d --force-recreate
```

## 支持和文档

- **部署脚本**: `./deploy.sh menu` - 交互式菜单
- **详细日志**: `./deploy.sh logs [service]`
- **服务状态**: `./deploy.sh status`
- **故障排除**: 查看容器日志和健康检查

## 总结

Athena Trader 的 Docker 化部署提供了：

✅ **一键部署**: 简单的部署脚本
✅ **服务隔离**: 完全容器化的微服务
✅ **数据持久化**: 可靠的数据存储
✅ **健康监控**: 全面的健康检查
✅ **安全配置**: 生产级安全设置
✅ **扩展性**: 支持水平扩展
✅ **备份恢复**: 自动化备份方案
✅ **CI/CD**: 持续集成支持

通过这个部署方案，您可以快速、安全、可靠地部署 Athena Trader 交易平台。
