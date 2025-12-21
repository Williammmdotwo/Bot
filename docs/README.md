# 文档目录

本目录包含 Athena Trader 项目的核心文档资料。

## 📁 目录结构

### 🚀 快速开始
- `LOCAL_DEVELOPMENT.md` - **本地开发指南**（推荐新用户从这里开始）

### architecture/ - 架构文档
- `OKX_TRADING_SYSTEM_ARCHITECTURE.md` - OKX 交易系统架构文档
- `HISTORICAL_KLINE_ARCHITECTURE.md` - 历史K线数据架构文档

### api/ - API 文档
- `AI_MODEL_SETUP.md` - AI 模型配置文档

### deployment/ - 部署文档
- `DEPLOYMENT.md` - 系统部署指南

### reports/ - 项目报告
- 包含各种优化和修复报告（历史记录）

## 📖 文档说明

### 🚀 本地开发（推荐）
**`LOCAL_DEVELOPMENT.md`** - 本地开发的完整指南，包含：
- 一键启动开发环境
- 统一开发工具使用
- 服务管理和调试
- 常见问题解决

### 🏗️ 架构文档
详细描述了系统的整体架构、组件设计和数据流程。

### 🔌 API 文档
说明了各种 API 的配置和使用方法。

### 🚀 部署文档
提供了系统部署的详细步骤和配置说明。

## 🔍 快速导航

### 🎯 推荐阅读顺序
1. **新用户**: `LOCAL_DEVELOPMENT.md` → `architecture/OKX_TRADING_SYSTEM_ARCHITECTURE.md`
2. **本地开发者**: `LOCAL_DEVELOPMENT.md`
3. **部署人员**: `deployment/DEPLOYMENT.md` → `LOCAL_DEVELOPMENT.md`
4. **API集成**: `api/AI_MODEL_SETUP.md` → `LOCAL_DEVELOPMENT.md`

### 🛠️ 快速操作
```bash
# 启动本地开发环境
python scripts/local_dev_manager.py start

# Windows用户一键启动
scripts/windows/local_dev.bat

# 查看服务状态
python scripts/local_dev_manager.py status
```

## 📝 文档维护

文档会随着系统更新而持续维护，请定期查看最新版本。

## 🔄 最近更新

- **2025-12-04**: 新增本地开发指南，统一开发工具
- **配置优化**: 实现配置继承和验证机制
- **脚本整合**: 替换分散的脚本为统一管理器
