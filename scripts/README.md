# 脚本目录

本目录包含 Athena Trader 项目的各种脚本文件。

## 📁 目录结构

### testing/ - 测试脚本
用于自动化测试和验证的脚本。

### deployment/ - 部署脚本
- `deploy.sh` - 系统部署脚本

### maintenance/ - 维护脚本
- `init-db.sql` - 数据库初始化脚本

## 🚀 脚本使用

### 部署脚本
```bash
# 运行部署脚本
chmod +x scripts/deployment/deploy.sh
./scripts/deployment/deploy.sh
```

### 数据库初始化
```bash
# 执行数据库初始化
psql -U username -d database -f scripts/maintenance/init-db.sql
```

## 📋 脚本说明

### 🔧 部署脚本
自动化系统部署流程，包括：
- 环境检查
- 依赖安装
- 服务启动
- 配置验证

### 🗄️ 数据库脚本
数据库相关的操作脚本：
- 表结构创建
- 初始数据导入
- 索引优化

### 🧪 测试脚本
自动化测试执行：
- 单元测试
- 集成测试
- 性能测试

## 🔧 环境要求

运行脚本前请确保：
1. 具有相应的执行权限
2. 环境变量已配置
3. 依赖服务已启动

## 📝 脚本维护

脚本会随着系统需求变化而更新，请使用最新版本。
