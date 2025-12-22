# 生产环境部署指南

## 概述

本文档描述了如何在没有测试文件的情况下部署 Athena Trader 到生产环境。经过验证，核心程序完全独立于测试代码，可以在生产环境中正常运行。

## 验证结果

### ✅ 核心程序独立性验证

通过模拟删除 `tests/` 目录的测试，确认以下核心服务可以正常启动：

1. **数据管理器** (`src/data_manager/main.py`) - ✅ 启动成功
2. **执行器** (`src/executor/main.py`) - ✅ 启动成功
3. **策略引擎** (`src/strategy_engine/main.py`) - ✅ 启动成功
4. **风险管理器** (`src/risk_manager/main.py`) - ✅ 启动成功

### 📋 依赖关系检查

- **核心服务**：无对 `tests/` 目录的依赖
- **启动脚本**：核心功能不依赖测试文件
- **配置文件**：配置中无测试路径引用
- **导入语句**：所有核心模块导入正常

## 生产环境最小文件清单

### 必需的核心文件

```
athena-trader/
├── src/                           # 核心源代码
│   ├── data_manager/
│   ├── executor/
│   ├── risk_manager/
│   ├── strategy_engine/
│   └── utils/
├── scripts/                        # 启动脚本
│   ├── start.py                    # 统一启动入口
│   └── core/                       # 核心脚本
│       ├── local_dev_manager.py
│       └── start_trading.py
├── config/                        # 配置文件
│   ├── base.json
│   ├── development.json
│   ├── production.json
│   └── local.json
├── requirements.txt                 # Python依赖
├── .env                           # 环境变量
├── docker-compose.yml             # Docker编排
└── Dockerfile                      # Docker镜像
```

### 可选的辅助文件

```
├── docs/                          # 文档（可选）
├── nginx/                         # 反向代理（可选）
├── logs/                          # 日志目录（自动创建）
└── frontend/                      # 前端（可选）
```

### ❌ 可以排除的文件

```
├── tests/                         # 测试文件（生产不需要）
├── scripts/deprecated/              # 已弃用脚本
├── scripts/legacy/                # 遗留脚本
├── scripts/debug_tools/             # 调试工具
├── scripts/maintenance/             # 维护脚本
├── scripts/windows/                # Windows专用脚本
└── docs/reports/                 # 报告文档
```

## 部署步骤

### 1. 环境准备

#### 1.1 系统要求
- Python 3.8+
- Docker & Docker Compose（可选）
- 足够的磁盘空间和内存

#### 1.2 环境变量配置
创建 `.env` 文件：
```bash
# 生产环境配置
ATHENA_ENV=production
DATA_SOURCE_MODE=okx
USE_MOCK_DATA=false
OKX_ENVIRONMENT=production

# OKX 生产API密钥（必须）
OKX_PRODUCTION_API_KEY=your_production_api_key
OKX_PRODUCTION_SECRET=your_production_secret
OKX_PRODUCTION_PASSPHRASE=your_production_passphrase

# 服务配置
INTERNAL_SERVICE_TOKEN=your_secure_internal_token
DISABLE_REDIS=false
USE_DATABASE=true

# 数据库配置（如使用）
DATABASE_URL=your_database_url
```

### 2. 核心服务部署

#### 2.1 使用统一启动脚本（推荐）

```bash
# 开发模式（用于测试）
python scripts/start.py dev start

# 交易模式（生产）
python scripts/start.py trading
```

#### 2.2 使用单独启动脚本

```bash
# 数据管理器
python -m src.data_manager.main

# 执行器
python -m src.executor.main

# 策略引擎
python -m src.strategy_engine.main

# 风险管理器
python -m src.risk_manager.main
```

#### 2.3 使用 Docker 部署

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 3. 服务验证

#### 3.1 健康检查
```bash
# 检查各服务健康状态
curl http://localhost:8000/health  # 数据管理器
curl http://localhost:8001/health  # 风险管理器
curl http://localhost:8002/health  # 执行器
curl http://localhost:8003/health  # 策略引擎
```

#### 3.2 功能测试
```bash
# 使用统一启动脚本测试
python scripts/start.py dev status
```

## 配置优化

### 生产环境配置 (`config/production.json`)
```json
{
  "debug_mode": false,
  "enable_profiling": false,
  "log_level": "INFO",
  "security": {
    "enable_authentication": true,
    "rate_limiting": true
  },
  "performance": {
    "cache_enabled": true,
    "monitoring_enabled": true
  }
}
```

### 安全配置
1. **API密钥安全**：确保生产API密钥不泄露
2. **内部通信**：使用强密码作为 `INTERNAL_SERVICE_TOKEN`
3. **网络访问**：配置防火墙规则
4. **日志轮转**：配置日志大小和保留策略

## 监控和维护

### 1. 日志监控
- 服务日志：`logs/` 目录
- 使用统一启动脚本查看状态：`python scripts/start.py dev status`

### 2. 性能监控
- 内置性能监控：`src/utils/performance_monitor.py`
- 内存监控：`src/utils/memory_monitor.py`

### 3. 故障排除
```bash
# 查看服务状态
python scripts/start.py dev status

# 重启服务
python scripts/start.py dev restart

# 清理系统
python scripts/start.py dev cleanup
```

## 部署验证清单

### ✅ 部署前检查
- [ ] 环境变量配置正确
- [ ] API密钥有效性验证
- [ ] 端口 8000-8003 可用
- [ ] 依赖服务（Redis、数据库）可用
- [ ] 防火墙规则配置正确

### ✅ 部署后验证
- [ ] 所有核心服务启动成功
- [ ] 健康检查端点响应正常
- [ ] 服务间通信正常
- [ ] 日志记录功能正常
- [ ] 内存和CPU使用正常

### ✅ 功能测试
- [ ] 数据获取功能正常
- [ ] 交易信号生成正常
- [ ] 风险检查功能正常
- [ ] 订单执行功能正常

## 故障恢复

### 服务重启
```bash
# 重启所有服务
python scripts/start.py dev restart

# 单独重启服务（如需要）
# 杀死进程并重新启动对应的模块
```

### 紧急回滚
1. 保留旧版本配置文件
2. 快速替换核心文件
3. 重启服务验证
4. 检查日志确认恢复

## 最佳实践

1. **定期备份**：配置文件和日志文件
2. **监控告警**：设置服务异常告警
3. **更新策略**：渐进式更新，避免中断
4. **安全审计**：定期检查安全配置
5. **性能优化**：根据监控数据调整配置

## 总结

经过完整验证，Athena Trader 的核心程序完全独立于测试代码，可以在生产环境中稳定运行。建议使用统一启动脚本 `scripts/start.py` 进行部署和管理，它提供了简化的操作界面和完整的状态监控功能。

### 关键优势
- ✅ **独立部署**：无需测试文件即可运行
- ✅ **统一管理**：单一入口控制所有服务
- ✅ **状态监控**：实时查看服务健康状态
- ✅ **故障恢复**：快速重启和清理功能
- ✅ **配置灵活**：支持多环境配置
