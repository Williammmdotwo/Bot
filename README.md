# Athena Trader

## 📊 项目交付状态

**项目状态**: ✅ 已上线运行 (Running)
**运行环境**: OKX 模拟盘 (Demo/Sandbox) + 实盘数据馈送
**核心标的**: SOL-USDT-SWAP (永续合约)
**服务器配置**: 1 vCPU / 1GB RAM / Ubuntu

---

## 🚀 专业的量化交易系统

Athena Trader 是一个基于 Python 的量化交易系统，支持多种交易策略和仓位管理模型，集成了OKX交易所API，提供完整的交易执行、风险管理和监控功能。

---

## ✨ 核心特性

### 🎯 交易策略
- **趋势回调策略 (Trend Pullback Strategy)** - 基于EMA趋势跟踪和RSI超卖超买的趋势策略
  - 顺势而为，只在明确趋势中交易
  - 回调入场，提高盈亏比
  - 支持"不死鸟"仓位管理模型

### 🦅 仓位管理
- **"不死鸟"模型 (Fixed Risk Model)** - 推荐的仓位管理模型
  - 每单最多只亏本金的 2%
  - 杠杆率控制在 2x-3x
  - 基于止损距离动态计算仓位
  - 确保即使连续亏损50次，仍有36%本金继续交易

### ⚙️ 技术指标
- EMA（指数移动平均线）
- RSI（相对强弱指数）
- 布林带
- ATR（平均真实范围）
- 支持自定义指标

**技术实现**
- **Pandas原生计算**：使用 `df.ewm()`、`df.rolling()` 等原生方法
- **无重型依赖**：完全剥离Ta-Lib和Pandas-TA库
- **高性能**：针对低配环境优化，计算速度快
- **易扩展**：添加新指标只需使用Pandas原生方法

### 🔧 系统架构

**模块化单体架构**
- 专为低资源配置（1GB RAM）优化
- 所有模块在一个进程中运行，内存占用降低60%
- 模块间通过Python函数调用，延迟降至微秒级
- 去HTTP化：不再使用API调用进行模块间通信
- 去数据库化：移除Redis和PostgreSQL依赖

**关键设计决策**
- **依赖注入**：DataHandler和MarketDataFetcher共享同一个RESTClient实例
- **内存处理**：K线数据直接在内存中处理（Pandas DataFrame）
- **日志持久化**：使用RotatingFileHandler管理日志作为持久化记录
- **接口规范**：所有模块对外只暴露interface.py或核心类方法

**部署模式**
- 开发环境：单体应用模式（推荐）
- 生产环境：可扩展为微服务模式（通过docker-compose部署）
- FastAPI 提供RESTful API（可选）
- WebSocket 实时数据推送（可选）

---

## 🔄 混合数据方案

### 问题背景
OKX的模拟盘（Sandbox）环境经常出现以下问题：
- 历史K线数据缺失或更新极慢
- 在非交易时段或维护时，K线接口报错
- 鉴权系统在请求公有数据时偶尔触发NoneType签名错误

### 解决方案：实盘看盘 + 模拟交易
我们在 `src/data_manager/clients/rest_client.py` 中实现了双通道客户端：

**通道 A：Public Exchange（实盘/只读）**
- 指向：`https://www.okx.com/api` (Real)
- 配置：`sandboxMode=False`，无API Key
- 用途：专门用于 `fetch_ohlcv`（获取K线）
- 优势：保证了技术指标计算的是真实市场的价格

**通道 B：Private Exchange（模拟/交易）**
- 指向：`https://www.okx.com/api` (Demo header)
- 配置：`sandboxMode=True`，带模拟盘API Key
- 用途：专门用于 `fetch_positions`（查持仓）和 `create_order`（下单）
- 优势：在安全环境中测试交易逻辑

### 注意事项
- **滑点风险**：实盘价格和模拟盘价格可能存在微小偏差（0.1%~0.5%）
- **实盘迁移**：切换到实盘时，只需修改 `config/production.json`，不需要修改代码逻辑
- **数据一致性**：策略使用实盘价格决策，在模拟盘执行订单

---

## ⚠️ 关键注意事项

### 1. 模拟盘的"幽灵持仓"问题
**现象**：调用 `fetch_positions()` 返回空列表，但网页上显示有持仓

**原因**：OKX模拟盘接口必须指定symbol才能精确查到

**解决方案**：代码中已强制要求 `get_account_positions(symbol="SOL-USDT-SWAP")`，严禁传空值

### 2. 混合数据的"滑点"风险
**风险**：用实盘价格计算信号，但在模拟盘下单。实盘价格和模拟盘价格可能存在微小偏差

**影响**：在模拟测试中，可能会出现"实盘触发了止损，但模拟盘没成交"的情况

**实盘迁移**：切换到真金白银实盘时，这个问题会自动消失（因为看盘和交易都是实盘）

### 3. 内存泄漏防范
虽然去掉了Redis和PostgreSQL，但Python的logging如果不加限制，长期运行会吃满磁盘

**现状**：已配置RotatingFileHandler
- 单个日志文件限制：10MB
- 最多保留：5个文件
- **请勿随意更改此配置**

### 4. 依赖库陷阱
**Ta-Lib / Pandas-TA**：这两个库在低配Linux环境下安装极其困难

**对策**：项目已完全剥离这些依赖。如果未来要加新指标：
- 继续使用Pandas原生写法（`df.ewm`, `df.rolling`）
- 或使用轻量级的ta库
- **不要引入重型依赖库**

### 5. 日志配置重要性
- 使用 `RotatingFileHandler` 自动轮转日志
- 防止日志文件无限增长占用磁盘空间
- 建议定期检查 `logs/` 目录大小

### 6. 接口开发规范
- 所有模块对外只暴露 `interface.py` 或核心类方法
- 严禁跨层级调用私有方法
- 数据层：`data_handler.get_latest_data(symbol)`
- 策略层：`signal_generator.analyze(df)`（纯函数，无副作用）
- 执行层：`executor.execute_trade(signal)`

---

## 📋 快速开始

### 环境要求

- Python 3.9+
- 1GB RAM（单体应用模式）
- Docker (可选，用于微服务模式)
- Linux/Windows/macOS

### 系统要求
- **最低配置**：1 vCPU / 1GB RAM（已测试）
- **推荐配置**：2 vCPU / 2GB RAM
- **磁盘空间**：至少500MB（包括日志）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置

复制环境变量模板并修改：

```bash
cp .env.template .env
```

编辑 `.env` 文件，设置你的OKX API密钥：

```env
OKX_API_KEY=your_api_key
OKX_API_SECRET=your_api_secret
OKX_PASSPHRASE=your_passphrase
OKX_SANDBOX=true  # 使用模拟环境
```

### 启动

#### 开发模式（单体应用）

```bash
python main_monolith.py
```

#### 生产模式（Docker Compose）

```bash
docker-compose up -d
```

---

## 📖 文档

### 快速入门
- [本地开发指南](docs/LOCAL_DEVELOPMENT.md) - 推荐新用户从这里开始
- [生产部署指南](docs/PRODUCTION_DEPLOYMENT_GUIDE.md) - 生产环境部署完整指南

### 策略文档
- [趋势回调策略](docs/strategy/TREND_PULLBACK_STRATEGY.md) - 完整的策略文档
- [仓位管理模型](docs/strategy/POSITION_MANAGEMENT.md) - 仓位管理模型详解

### 架构文档
- [系统架构](docs/architecture/OKX_TRADING_SYSTEM_ARCHITECTURE.md) - 整体架构设计
- [历史K线架构](docs/architecture/HISTORICAL_KLINE_ARCHITECTURE.md) - 数据架构

### 其他文档
- [测试指南](docs/TESTING_GUIDE.md) - 测试套件使用说明
- [编码规范](docs/CODING_STANDARDS.md) - 项目编码标准

---

## 🧪 测试

### 运行所有测试

```bash
python -m pytest tests/ -v
```

### 运行特定测试

```bash
# 趋势回调策略测试
python -m pytest tests/unit/strategy_engine/test_trend_pullback_strategy.py -v -s

# 数据管理器测试
python -m pytest tests/unit/data_manager/ -v

# 集成测试
python -m pytest tests/integration/ -v
```

### 测试覆盖率

```bash
pytest --cov=src --cov-report=html
```

---

## 📊 项目结构

```
athena-trader/
├── config/                 # 配置文件
│   ├── local.json         # 本地环境配置
│   ├── development.json   # 开发环境配置
│   └── production.json    # 生产环境配置
├── docs/                  # 文档
│   ├── strategy/         # 策略文档
│   ├── architecture/     # 架构文档
│   └── deployment/      # 部署文档
├── scripts/              # 脚本工具
│   ├── start.py          # 统一启动脚本
│   └── core/            # 核心脚本
├── src/                  # 源代码
│   ├── data_manager/     # 数据管理
│   ├── executor/         # 交易执行
│   ├── risk_manager/     # 风险管理
│   ├── strategy_engine/  # 策略引擎
│   └── utils/           # 工具函数
├── tests/               # 测试
│   ├── unit/            # 单元测试
│   ├── integration/     # 集成测试
│   └── system/          # 系统测试
├── main_monolith.py     # 单体应用入口
├── docker-compose.yml    # Docker Compose 配置
└── requirements.txt     # Python 依赖
```

---

## 🎯 策略配置示例

### 趋势回调策略配置

```json
{
  "trading": {
    "capital": 100.0,
    "max_risk_pct": 0.02,
    "trading_symbol": "SOL-USDT-SWAP",
    "use_demo": true
  },
  "strategy": {
    "type": "trend_pullback",
    "enabled": true,
    "ema_period": 144,
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "stop_loss_pct": 0.03,
    "take_profit_pct": 0.06,
    "use_bollinger_exit": true,
    "only_long": true,
    "max_leverage": 3.0,
    "min_leverage": 2.0
  }
}
```

---

## 🔧 API 端点

### 健康检查
```bash
curl http://localhost:8000/health
```

### 获取市场数据
```bash
curl http://localhost:8000/market/klines?symbol=SOL-USDT-SWAP&limit=100
```

### 获取策略信号
```bash
curl http://localhost:8000/strategy/analyze
```

---

## 📈 "不死鸟"仓位管理示例

### 场景：SOL 价格 $150，止损 $145

**计算过程**:
```
最大风险 = $100 × 2% = $2
风险/单位 = $150 - $145 = $5
仓位数量 = $2 / $5 = 0.4 SOL
仓位价值 = 0.4 × $150 = $60
杠杆率 = $60 / $100 = 0.6x
实际风险 = 0.4 × $5 = $2 (2%)
```

**结果**:
- 仓位数量: 0.4 SOL
- 仓位价值: $60
- 杠杆率: 0.6x
- 最大亏损: $2 (2%)

---

## 🛠️ 常用命令

### 统一启动脚本
```bash
# 开发环境
python scripts/start.py dev --action start

# 交易环境
python scripts/start.py trading

# 测试环境
python scripts/start.py test
```

### 本地开发管理器
```bash
# 启动所有服务
python scripts/core/local_dev_manager.py start

# 停止所有服务
python scripts/core/local_dev_manager.py stop

# 查看状态
python scripts/core/local_dev_manager.py status
```

### Windows 用户
```bash
# 一键启动开发环境
scripts\windows\local_dev.bat

# 一键停止开发环境
scripts\windows\stop.bat
```

---

## 📊 监控和日志

### 查看日志
```bash
# 查看所有日志
tail -f logs/athena_trader.log

# 查看策略日志
tail -f logs/strategy_engine.log

# 查看交易日志
tail -f logs/executor.log
```

### 性能监控
```bash
curl http://localhost:8000/metrics
```

---

## 🔒 安全建议

1. **永远不要在代码中硬编码API密钥**
2. **使用环境变量或配置文件存储敏感信息**
3. **在生产环境中使用HTTPS**
4. **定期更新依赖包以修复安全漏洞**
5. **限制API访问IP**
6. **使用OKX的IP白名单功能**

---

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出改进建议！

### 贡献流程
1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### 代码规范
- 遵循 [PEP 8](https://www.python.org/dev/peps/pep-0008/) 编码规范
- 添加单元测试
- 更新相关文档
- 确保所有测试通过

---

## 📝 更新日志

### v1.1.0 (2024-12-28)
- ✨ 新增趋势回调策略
- ✨ 新增"不死鸟"仓位管理模型
- ✨ 新增交易循环集成
- ✨ 新增完整的策略文档
- ✨ 新增仓位管理文档
- ✨ 改进单元测试覆盖
- 🐛 修复多个测试问题

### v1.0.0 (2024-12-05)
- 🎉 初始版本发布
- ✨ 基础架构实现
- ✨ OKX API集成
- ✨ 双EMA策略实现
- ✨ Docker支持

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 📞 联系方式

- 项目主页: [GitHub](https://github.com/Williammmdotwo/Bot)
- 问题反馈: [Issues](https://github.com/Williammmdotwo/Bot/issues)
- 讨论区: [Discussions](https://github.com/Williammmdotwo/Bot/discussions)

---

## 🙏 致谢

感谢所有为本项目做出贡献的开发者和用户！

---

## ⚠️ 免责声明

**重要提示**: 本项目仅用于学习和研究目的。量化交易涉及高风险，可能导致资金损失。使用本系统进行实盘交易的风险由用户自行承担。作者不对任何因使用本系统而导致的损失负责。

**请务必**:
1. 先在模拟环境中充分测试
2. 使用风险可控的资金
3. 理解策略原理和风险
4. 不要投入超出承受能力的资金

---

**最后更新**: 2025年12月29日
