# Athena Trader 测试指南

## 概述

本指南说明如何运行 Athena Trader 的测试套件。我们已经修复了端口配置不一致的问题，并提供了自动化测试脚本。

## 问题修复

### 修复的问题
- **端口配置不一致**: 修复了测试运行器中data服务端口从8004改为8000
- **配置管理改进**: 测试运行器现在从配置文件动态读取端口配置
- **服务启动自动化**: 提供了自动启动和管理测试服务的脚本

### 修复的文件
1. `tests/utils/base_test_runner.py` - 修复端口配置和配置加载逻辑
2. 新增 `scripts/start_test_services.py` - 服务管理脚本
3. 新增 `scripts/run_test_with_services.py` - 自动化测试运行器
4. 新增 `scripts/windows/run_test.bat` - Windows快速启动脚本

## 快速开始

### 方法1: 使用统一启动脚本（推荐）

```bash
# 开发环境测试
python scripts/start.py dev --action test

# 测试环境测试
python scripts/start.py test

# 部署验证测试
python scripts/verify_deployment.py
```

### 方法2: 手动步骤

#### 1. 启动服务
```bash
# 使用本地开发管理器启动服务
python scripts/core/local_dev_manager.py start
```

#### 2. 运行测试（新终端）
```bash
# 运行所有测试
python -m pytest

# 运行特定测试文件
python -m pytest tests/system/simple_trading_test.py

# 运行特定测试类
python -m pytest tests/unit/data_manager/test_main.py

# 显示详细输出
python -m pytest -v
```

#### 3. 停止服务
```bash
# 停止所有服务
python scripts/core/local_dev_manager.py stop
```

## 服务端口配置

当前测试环境的服务端口配置：

| 服务 | 端口 | 状态 |
|------|------|------|
| data_manager | 8000 | ✅ 已修复 |
| risk_manager | 8002 | ✅ 正常 |
| executor | 8001 | ✅ 正常 |
| strategy_engine | 8003 | ✅ 正常 |

## 配置文件

### 测试配置 (`config/test.json`)
```json
{
  "environment": "test",
  "services": {
    "data_manager": {
      "port": 8000,
      "enabled": true
    },
    "strategy_engine": {
      "port": 8003,
      "enabled": true
    },
    "risk_manager": {
      "port": 8002,
      "enabled": true
    },
    "executor": {
      "port": 8001,
      "enabled": true
    }
  }
}
```

## 故障排除

### 常见问题

#### 1. 端口被占用
```bash
# 检查端口占用
netstat -ano | findstr :8000
netstat -ano | findstr :8001
netstat -ano | findstr :8002
netstat -ano | findstr :8003

# 或者使用脚本检查
python scripts/start_test_services.py check
```

#### 2. 服务启动失败
- 检查Python依赖是否安装
- 确保项目目录结构正确
- 查看服务日志输出

#### 3. 测试连接失败
- 确保所有服务都已启动
- 检查防火墙设置
- 验证服务健康状态

### 调试命令

```bash
# 检查服务状态
python scripts/start_test_services.py check

# 重启所有服务
python scripts/start_test_services.py restart

# 查看服务日志
python scripts/start_test_services.py start --wait
```

## 环境要求

### 必需依赖
```bash
pip install requests flask
```

### 可选依赖
```bash
pip install redis asyncpg  # 如果使用数据库功能
```

## 测试类型

### 1. 简化交易测试
```bash
python -m tests.system.simple_trading_test
```

### 2. API端点测试
```bash
python -m tests.integration.test_api_endpoint
```

### 3. 微服务集成测试
```bash
python -m tests.integration.test_microservices
```

## 日志和报告

### 日志位置
- 测试日志: `logs/`
- 服务日志: 控制台输出

### 测试报告
- 自动生成在 `logs/` 目录
- 文件名格式: `{test_class}_{timestamp}.txt`

## 开发建议

### 修改服务端口
1. 编辑 `config/test.json`
2. 更新相应服务的端口配置
3. 重启服务

### 添加新测试
1. 继承 `BaseTestRunner` 类
2. 实现测试逻辑
3. 使用 `make_service_request()` 方法调用服务API

### 服务开发
- 确保服务实现 `/health` 端点
- 使用 `x-service-token` 头进行内部认证
- 遵循统一的错误响应格式

## 联系支持

如果遇到问题，请：
1. 查看本文档的故障排除部分
2. 检查日志文件中的错误信息
3. 确保环境配置正确

---

**注意**: 测试环境使用模拟数据，不会进行真实交易。
