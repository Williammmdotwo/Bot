# 文档目录

本目录包含 Athena Trader 项目的核心文档资料。

## 📁 目录结构

### 🚀 快速开始
- `LOCAL_DEVELOPMENT.md` - **本地开发指南**（推荐新用户从这里开始）
- `PRODUCTION_DEPLOYMENT_GUIDE.md` - 生产环境部署指南

### strategy/ - 策略文档
- `TREND_PULLBACK_STRATEGY.md` - **趋势回调策略**完整文档（推荐）
- `POSITION_MANAGEMENT.md` - **仓位管理模型**文档

### architecture/ - 架构文档
- `OKX_TRADING_SYSTEM_ARCHITECTURE.md` - OKX 交易系统架构文档
- `HISTORICAL_KLINE_ARCHITECTURE.md` - 历史K线数据架构文档

### deployment/ - 部署文档
- `DEPLOYMENT.md` - Docker 容器化部署指南

### 📝 其他文档
- `TESTING_GUIDE.md` - 测试指南
- `CODING_STANDARDS.md` - 编码规范

## 📖 文档说明

### 🚀 本地开发（推荐）
**`LOCAL_DEVELOPMENT.md`** - 本地开发的完整指南，包含：
- 一键启动开发环境
- 统一开发工具使用
- 服务管理和调试
- 常见问题解决

### 🏗️ 架构文档
详细描述了系统的整体架构、组件设计和数据流程。

### 🚀 部署文档
- **`PRODUCTION_DEPLOYMENT_GUIDE.md`** - 生产环境部署的完整指南
  - 环境准备和配置
  - 核心服务部署
  - 服务验证和监控
- **`deployment/DEPLOYMENT.md`** - Docker 容器化部署详细指南
  - 快速部署步骤
  - 安全配置
  - 监控和维护

### 🧪 测试指南
**`TESTING_GUIDE.md`** - 测试套件的使用说明

### 📝 编码规范
**`CODING_STANDARDS.md`** - 项目编码标准和最佳实践

## 🔍 快速导航

### 🎯 推荐阅读顺序
1. **新用户**: `LOCAL_DEVELOPMENT.md` → `architecture/OKX_TRADING_SYSTEM_ARCHITECTURE.md`
2. **本地开发者**: `LOCAL_DEVELOPMENT.md`
3. **部署人员**: `PRODUCTION_DEPLOYMENT_GUIDE.md` → `deployment/DEPLOYMENT.md`
4. **测试人员**: `TESTING_GUIDE.md`

### 🛠️ 快速操作
```bash
# 统一启动脚本（推荐）
python scripts/start.py dev --action start  # 开发环境
python scripts/start.py trading            # 交易环境
python scripts/start.py test               # 测试环境

# 本地开发管理器
python scripts/core/local_dev_manager.py start

# Windows用户一键启动
scripts\windows\local_dev.bat

# 部署验证
python scripts/verify_deployment.py
```

## 🏗️ 系统架构

Athena Trader 支持两种运行模式：

### 1. 单体应用模式（`main_monolith.py`）
所有模块在一个进程中运行，使用 FastAPI 提供统一接口。
- **端口**: 8000
- **适用**: 开发和简化部署
- **启动命令**: `python main_monolith.py`

### 2. 微服务模式（Docker Compose）
各服务独立运行，通过内部网络通信。
- **端口**: 8000-8003
- **适用**: 生产环境和扩展部署
- **启动命令**: `docker-compose up -d`

## 🔄 最近更新

- **2025-12-28**: 文档清理和重构
  - 删除过时的API测试和修复报告
  - 更新启动命令以反映新的统一脚本
  - 添加单体应用架构说明
- **2025-12-05**: 新增本地开发指南，统一开发工具
- **配置优化**: 实现配置继承和验证机制
- **脚本整合**: 替换分散的脚本为统一管理器

## 📝 文档维护

文档会随着系统更新而持续维护，请定期查看最新版本。
