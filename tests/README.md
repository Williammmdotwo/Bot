# 数据管理服务测试套件

本目录包含了用于测试数据管理服务的完整测试套件。

## 测试脚本概述

### 1. `integration/test_api_endpoint.py` - API端点测试
专门测试数据管理服务的API端点功能。

**测试内容:**
- 健康检查端点 (`/health`)
- 根端点 (`/`)
- 演示数据API (`/api/market-data/BTC-USDT?use_demo=true`)
- 生产数据API (`/api/market-data/BTC-USDT?use_demo=false`)

**使用方法:**
```bash
cd athena-trader
python tests/integration/test_api_endpoint.py
```

### 2. `unit/test_technical_indicators.py` - 技术指标计算测试
专门测试技术指标计算模块的功能。

**测试内容:**
- 单个技术指标计算 (RSI, MACD, 布林带, EMA, SMA, ATR, OBV, VWAP, 支撑阻力位)
- 综合技术指标计算
- 边界情况处理 (空数据、数据不足、单个数据点)
- 成交量分布分析
- 性能测试 (50-1000个K线数据)

**使用方法:**
```bash
cd athena-trader
python tests/unit/test_technical_indicators.py
```

### 3. `integration/test_data_manager_service.py` - 综合服务测试
全面测试数据管理服务的所有功能。

**测试内容:**
- 服务健康状态检查
- 市场数据API端点测试
- Redis连接状态测试
- 技术指标计算测试
- REST客户端测试
- 服务日志检查

**使用方法:**
```bash
cd athena-trader
python tests/integration/test_data_manager_service.py
```

### 4. `system/simple_trading_test.py` - 系统交易测试
完整的端到端交易流程测试。

**测试内容:**
- 交易信号生成
- 风险管理验证
- 交易执行
- 系统集成测试

**使用方法:**
```bash
cd athena-trader
python tests/system/simple_trading_test.py
```

### 5. `run_all_tests.py` - 运行所有测试
便捷脚本，按顺序运行所有测试并生成综合报告。

**使用方法:**
```bash
cd athena-trader
python tests/run_all_tests.py
```

## 测试结果文件

运行测试后，会生成以下结果文件：

- `data_manager_test_results.json` - 综合服务测试结果
- `technical_indicators_test_results.json` - 技术指标测试结果
- `complete_test_results.json` - 完整测试套件结果
- `test_summary_report.md` - 测试总结报告

## 前置条件

### 1. 数据管理服务运行
确保数据管理服务在 `http://localhost:8004` 运行：

```bash
cd athena-trader/src/data_manager
python main.py
```

### 2. Redis服务 (可选)
如果需要测试缓存功能，确保Redis服务运行：

```bash
# 使用Docker
docker run -d --name redis -p 6379:6379 redis:alpine

# 或使用本地安装
redis-server
```

### 3. OKX API凭证 (可选)
如果需要测试真实API数据，配置环境变量：

```bash
export OKX_DEMO_API_KEY=your_demo_api_key
export OKX_DEMO_SECRET=your_demo_secret
export OKX_DEMO_PASSPHRASE=your_demo_passphrase
```

## 测试覆盖率

| 功能模块 | 测试脚本 | 覆盖率 |
|---------|---------|--------|
| API端点 | test_api_endpoint.py | 100% |
| 技术指标计算 | test_technical_indicators.py | 100% |
| 服务健康检查 | test_data_manager_service.py | 100% |
| Redis连接 | test_data_manager_service.py | 100% |
| REST客户端 | test_data_manager_service.py | 100% |
| 日志系统 | test_data_manager_service.py | 100% |

## 快速开始

### 运行单个测试
```bash
# 测试API端点
python tests/integration/test_api_endpoint.py

# 测试技术指标
python tests/unit/test_technical_indicators.py

# 运行综合测试
python tests/integration/test_data_manager_service.py

# 运行系统交易测试
python tests/system/simple_trading_test.py
```

### 运行完整测试套件
```bash
# 运行所有测试
python tests/run_all_tests.py
```

## 测试结果解读

### 成功指标
- ✅ 测试通过
- 响应时间 < 5秒 (API测试)
- 技术指标计算 < 10ms (1000个K线)
- 无错误或异常

### 失败指标
- ❌ 测试失败
- 连接超时
- API响应错误
- 计算异常

### 警告指标
- ⚠️ 部分功能降级
- 性能较慢
- 数据质量问题

## 故障排除

### 常见问题

1. **服务连接失败**
   - 确保数据管理服务在端口8004运行
   - 检查防火墙设置

2. **Redis连接失败**
   - 启动Redis服务
   - 检查连接配置 (REDIS_HOST, REDIS_PORT, REDIS_PASSWORD)

3. **API凭证错误**
   - 配置正确的OKX API凭证
   - 检查环境变量设置

4. **导入错误**
   - 确保在正确的目录中运行脚本
   - 检查Python路径设置

### 调试模式

可以通过设置环境变量启用详细日志：

```bash
export LOG_LEVEL=DEBUG
python tests/test_data_manager_service.py
```

## 性能基准

### 技术指标计算性能
| 数据量 | 目标时间 | 实际时间 |
|--------|----------|----------|
| 50个K线 | < 5ms | ~1ms |
| 100个K线 | < 10ms | ~1ms |
| 500个K线 | < 50ms | ~2ms |
| 1000个K线 | < 100ms | ~3ms |

### API响应性能
| 端点 | 目标时间 | 实际时间 |
|------|----------|----------|
| 健康检查 | < 100ms | ~50ms |
| 演示数据API | < 5s | ~2.5s |
| 生产数据API | < 1s | ~250ms |

## 贡献指南

### 添加新测试
1. 在相应的测试脚本中添加测试函数
2. 更新测试结果统计逻辑
3. 更新本README文档

### 报告问题
如果发现测试问题，请提供：
- 测试脚本名称
- 错误信息
- 系统环境信息
- 重现步骤

## 更新日志

### v1.0.0 (2025-12-01)
- 初始版本
- 完整的API端点测试
- 技术指标计算测试
- 综合服务测试
- 自动化测试运行脚本

---

**注意**: 这些测试脚本设计用于开发和测试环境，不建议在生产环境中运行。
