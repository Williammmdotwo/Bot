# Athena OS v3.0

高性能加密货币量化交易系统，专为 HFT（高频交易）和剥头皮策略优化。

## 🚀 快速开始

### 前置要求

- Python 3.10+
- OKX 账户（支持 Demo Trading）
- OKX API 密钥

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量

1. 复制环境变量模板：
```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，填入你的 OKX API 密钥：
```bash
OKX_API_KEY=your_api_key_here
OKX_SECRET_KEY=your_secret_key_here
OKX_PASSPHRASE=your_passphrase_here
USE_DEMO=true  # 模拟盘模式
```

### 运行系统

#### 普通模式

```bash
python main.py
```

#### 模拟运行模式（推荐用于测试）

```bash
python scripts/run_simulation.py
```

模拟运行模式特点：
- ✅ 强制连接到 OKX Demo Trading
- ✅ 健康监控（每分钟心跳）
- ✅ 日志轮转（100MB × 10）
- ✅ 资源监控（CPU/内存）
- ✅ 安全检查（需要 `IS_SIMULATION=true`）

详细说明请参考：[模拟运行指南](docs/SIMULATION_RUNNER.md)

---

## 📊 测试

### 运行所有测试

```bash
pytest tests/ -v
```

### 运行特定测试套件

```bash
# ScalperV1 策略测试
pytest tests/test_scalper_v1.py -v

# 订单管理器测试
pytest tests/test_order_manager.py -v

# 持仓管理器测试
pytest tests/test_position_manager.py -v
```

### 测试覆盖率

```bash
pytest --cov=src --cov-report=html tests/
```

查看覆盖率报告：
```bash
open htmlcov/index.html  # Mac
start htmlcov/index.html  # Windows
```

---

## 📁 项目结构

```
athena-trader/
├── src/                      # 源代码
│   ├── core/                 # 核心组件（引擎、事件总线）
│   ├── gateways/             # 交易所网关（OKX REST/WebSocket）
│   ├── oms/                 # 订单管理系统
│   ├── risk/                 # 风控模块
│   ├── strategies/           # 交易策略
│   │   └── hft/           # 高频交易策略
│   │       └── scalper_v1.py  # 极速剥头皮策略
│   ├── config/              # 配置管理
│   └── utils/              # 工具函数
├── tests/                  # 测试套件
│   ├── test_scalper_v1.py   # ScalperV1 策略测试
│   ├── test_order_manager.py
│   ├── test_position_manager.py
│   └── conftest.py        # pytest fixtures
├── scripts/               # 脚本
│   └── run_simulation.py  # 模拟运行脚本
├── docs/                 # 文档
│   └── SIMULATION_RUNNER.md  # 模拟运行指南
├── logs/                 # 日志文件
├── config/               # 配置文件
├── main.py              # 主入口
├── .env                # 环境变量（不提交到 Git）
└── .env.example         # 环境变量模板
```

---

## 🛡️ 安全特性

### ScalperV1 策略安全机制

1. **Fix 16: Timeout Lock (平仓锁超时)**
   - 防止重复平仓导致的多订单问题
   - 超时自动释放锁（默认 10 秒）

2. **Fix 17: One-Way Valve (单向阀门)**
   - 有持仓时绝对禁止开新仓
   - 防止仓位累积风险

3. **Fix 10: Abnormal Reset (异常仓位重置)**
   - 异常仓位自动重置为 0
   - 防止状态异常

### 测试覆盖

所有安全机制均通过完整测试验证：
- ✅ 19/19 测试通过（100% 覆盖率）
- 详细测试报告：[tests/SCALPER_V1_TEST_REPORT.md](tests/SCALPER_V1_TEST_REPORT.md)

---

## 📈 策略说明

### ScalperV1 - 极速剥头皮策略

**特点**：
- Maker 模式（降低手续费）
- 基于微观结构失衡（买量 >> 卖量）
- 光速离场（止盈 0.2% / 止损 1% / 时间止损 5 秒）
- O(1) 时间复杂度，极速计算

**适用场景**：
- 流动性好的交易对（如 SOL-USDT-SWAP）
- 高频交易环境
- 低延迟网络（建议 < 10ms）

**风险提示**：
- 高杠杆策略（默认 5x）
- 需要稳定网络连接
- 建议先在 Demo 环境测试

---

## 🔧 配置说明

### 关键环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `IS_SIMULATION` | 模拟运行安全检查（必须为 true） | false |
| `USE_DEMO` | 使用模拟盘 | true |
| `ACTIVE_STRATEGY` | 启用的策略 | scalper_v1 |
| `TOTAL_CAPITAL` | 总资金（USDT） | 10000.0 |
| `SCALPER_SYMBOL` | 交易对 | SOL-USDT-SWAP |
| `LOG_LEVEL` | 日志级别 | INFO |

### ScalperV1 策略参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `imbalance_ratio` | 买卖失衡阈值（倍数） | 3.0 |
| `min_flow_usdt` | 最小流速（USDT/秒） | 1000.0 |
| `take_profit_pct` | 止盈百分比 | 0.002 (0.2%) |
| `stop_loss_pct` | 止损百分比 | 0.01 (1.0%) |
| `time_limit_seconds` | 时间止损（秒） | 5 |
| `cooldown_seconds` | 冷却时间（秒） | 0 |

详细配置请参考：[.env.example](.env.example)

---

## 📝 日志

### 日志位置

- **普通模式**: `logs/app.log`
- **模拟运行**: `logs/simulation/simulation.log`

### 日志轮转

- 普通模式：10MB × 5 备份
- 模拟运行：100MB × 10 备份

### 查看日志

```bash
# 实时查看
tail -f logs/app.log

# Windows PowerShell
Get-Content logs\app.log -Wait -Tail 50
```

---

## 🐛 故障排查

### 问题 1: 无法连接到 OKX

**检查项**：
1. API 密钥是否正确
2. 是否启用了模拟盘（`USE_DEMO=true`）
3. 网络连接是否正常

### 问题 2: 策略无信号

**可能原因**：
1. 市场流动性不足
2. 触发阈值设置过高
3. 交易对选择不当

**解决方法**：
- 降低 `min_flow_usdt` 和 `imbalance_ratio`
- 选择流动性更好的交易对
- 查看 DEBUG 日志了解详细情况

### 问题 3: 内存使用持续增长

**排查步骤**：
1. 查看健康监控输出（模拟运行模式）
2. 检查是否有未关闭的连接
3. 查看 `logs/simulation/simulation.log` 寻找内存泄漏迹象

---

## 📞 支持

如有问题，请查看：
1. [模拟运行指南](docs/SIMULATION_RUNNER.md)
2. [ScalperV1 测试报告](tests/SCALPER_V1_TEST_REPORT.md)
3. [项目架构文档](项目架构.md)

---

## ⚠️ 免责声明

本系统仅供学习和研究使用。

- ❌ 不构成投资建议
- ❌ 不保证盈利
- ❌ 使用者需自行承担风险

请确保：
1. ✅ 先在 Demo 环境充分测试
2. ✅ 理解策略逻辑和风险
3. ✅ 使用可承受损失的资金

---

## 📄 许可证

MIT License

---

## 🙏 致谢

感谢所有贡献者的支持！

祝交易顺利！ 🚀
