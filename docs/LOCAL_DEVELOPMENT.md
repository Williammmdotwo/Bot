# Athena Trader 本地开发指南

本指南提供在本地环境中开发和调试 Athena Trader 的完整说明。

## 🚀 快速开始

### 前置要求
- Python 3.8+
- Git
- 本地开发环境（Windows/Linux/macOS）

### 一键启动
```bash
# Windows用户
scripts\windows\local_dev.bat

# Linux/macOS用户
python scripts/local_dev_manager.py start
```

## 📋 开发环境配置

### 环境变量设置
```bash
# 设置本地开发环境
export ATHENA_ENV=local
export CONFIG_PATH=./config
export PYTHONPATH=./src
```

### 本地配置文件
项目使用 `config/local.json` 作为本地开发配置，包含：
- 禁用数据库和Redis（使用模拟数据）
- 启用调试模式和详细日志
- 配置本地服务端口
- 设置开发友好的风险限制

## 🔧 开发工具

### 统一开发管理器
`scripts/local_dev_manager.py` 是本地开发的核心工具：

```bash
# 查看所有服务状态
python scripts/local_dev_manager.py status

# 启动所有开发服务
python scripts/local_dev_manager.py start

# 停止所有服务
python scripts/local_dev_manager.py stop

# 重启服务
python scripts/local_dev_manager.py restart

# 运行测试
python scripts/local_dev_manager.py test

# 清理系统（日志、缓存、临时文件）
python scripts/local_dev_manager.py cleanup

# 清理特定类型
python scripts/local_dev_manager.py cleanup --cleanup-type logs
python scripts/local_dev_manager.py cleanup --cleanup-type temp
python scripts/local_dev_manager.py cleanup --cleanup-type cache
```

### Windows用户友好界面
Windows用户可以使用 `scripts/windows/local_dev.bat` 获得图形化菜单：

1. 双击运行 `local_dev.bat`
2. 选择所需操作（1-7）
3. 按提示操作

## 🏗️ 服务架构

### 本地服务端口
- **数据管理器**: http://localhost:8000
- **风险管理器**: http://localhost:8001  
- **执行器**: http://localhost:8002
- **策略引擎**: http://localhost:8003
- **前端界面**: http://localhost:3000

### 服务依赖关系
```
data_manager (8000)
    ↓
risk_manager (8001)
    ↓
executor (8002)
    ↓
strategy_engine (8003)
```

## 🧪 开发和测试

### 运行测试
```bash
# 运行默认测试
python scripts/local_dev_manager.py test

# 运行特定测试
python scripts/local_dev_manager.py test --test simple_trading_test
```

### 调试模式
本地环境自动启用调试模式：
- 详细日志输出
- 控制台日志显示
- 错误堆栈跟踪
- 性能监控

### 日志查看
```bash
# 查看实时日志
tail -f logs/local_dev.log

# 查看特定服务日志
tail -f logs/data_manager.log
tail -f logs/risk_manager.log
```

## 📁 项目结构

### 核心目录
```
athena-trader/
├── src/                    # 源代码
│   ├── data_manager/        # 数据管理服务
│   ├── risk_manager/        # 风险管理服务
│   ├── executor/            # 交易执行服务
│   ├── strategy_engine/      # 策略引擎服务
│   └── utils/              # 工具模块
├── config/                 # 配置文件
│   ├── base.json           # 基础配置
│   ├── local.json          # 本地开发配置
│   ├── development.json    # 开发环境配置
│   ├── test.json          # 测试环境配置
│   └── production.json    # 生产环境配置
├── scripts/                # 脚本工具
│   ├── local_dev_manager.py # 本地开发管理器
│   ├── windows/           # Windows脚本
│   └── deprecated/       # 已弃用的脚本
├── tests/                  # 测试代码
├── docs/                   # 文档
└── logs/                   # 日志文件
```

## 🔧 配置管理

### 配置继承体系
配置按以下优先级加载：
1. `base.json` (基础配置)
2. `{environment}.json` (环境配置)
3. `local.json` (本地覆盖配置)

### 配置验证
所有配置都会自动验证：
- 端口冲突检测
- 数据类型验证
- 业务规则检查
- 环境特定要求

### 配置热重载
配置文件修改后自动重载，无需重启服务。

## 🛠️ 常见开发任务

### 添加新服务
1. 在 `src/` 下创建服务目录
2. 在 `config/local.json` 中添加服务配置
3. 更新 `local_dev_manager.py` 中的服务列表
4. 添加相应的测试

### 修改配置
1. 编辑 `config/local.json`（本地开发）
2. 或编辑对应环境的配置文件
3. 配置会自动验证和重载

### 调试服务
```bash
# 单独启动服务进行调试
cd src/data_manager
python -m src.data_manager.main

# 查看服务健康状态
curl http://localhost:8000/health
```

## 🐛 故障排除

### 常见问题

#### 端口被占用
```bash
# 查看端口占用
netstat -ano | findstr :8000

# 杀死占用进程
taskkill /PID <进程ID> /F
```

#### 服务启动失败
1. 检查配置文件语法
2. 查看日志文件
3. 验证Python依赖
4. 检查环境变量

#### 配置错误
```bash
# 验证配置
python -c "from src.utils.config_loader import get_config_manager; get_config_manager().validate_config_only()"
```

### 获取帮助
```bash
# 查看管理器帮助
python scripts/local_dev_manager.py --help

# 查看配置帮助
python scripts/local_dev_manager.py status
```

## 📚 相关文档

- [系统架构](./architecture/OKX_TRADING_SYSTEM_ARCHITECTURE.md)
- [API文档](./api/)
- [部署指南](./deployment/DEPLOYMENT.md)
- [测试指南](./TESTING_GUIDE.md)

## 🔄 从旧版本迁移

如果你之前使用的是分散的脚本，这里是对应关系：

| 旧脚本 | 新命令 |
|---------|---------|
| `python scripts/start_test_services.py start` | `python scripts/local_dev_manager.py start` |
| `python scripts/cleanup_logs.py` | `python scripts/local_dev_manager.py cleanup --cleanup-type logs` |
| `python scripts/run_test_with_services.py` | `python scripts/local_dev_manager.py test` |
| `scripts/windows/start_services_background.bat` | `scripts/windows/local_dev.bat` (选项1) |

## 📈 性能优化

### 本地开发优化
- 使用模拟数据减少网络依赖
- 禁用不必要的数据库连接
- 启用缓存和性能监控
- 优化日志级别

### 内存管理
```bash
# 清理内存和缓存
python scripts/local_dev_manager.py cleanup --cleanup-type cache
```

## 🔒 安全注意事项

### 本地开发安全
- 使用模拟交易数据，避免真实资金风险
- 本地认证令牌仅用于开发
- 不要提交真实的API密钥
- 定期清理敏感日志

## 📞 获取支持

如果遇到问题：
1. 查看本文档的故障排除部分
2. 检查 `logs/` 目录中的日志文件
3. 运行 `python scripts/local_dev_manager.py status` 检查系统状态
4. 查看项目的 GitHub Issues

---

**提示**: 本地开发环境专为快速迭代和调试设计，生产部署请参考部署指南。
