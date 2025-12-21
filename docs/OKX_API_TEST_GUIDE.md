# OKX Demo API 连接测试指南

## 概述

本指南介绍如何使用 `test_okx_api_connection.py` 脚本来验证 OKX Demo API 的连接和数据获取功能。

## 功能特性

该测试脚本验证以下功能：

1. **API连接测试** - 验证能否成功连接到 OKX Demo API
2. **市场数据测试** - 验证能否获取 BTC-USDT 的实时市场数据
3. **OHLCV数据测试** - 验证能否获取足够的历史K线数据
4. **数据质量评估** - 验证数据量是否足够进行技术指标计算

## 前置条件

### 1. 环境配置

确保已安装所需的Python依赖：

```bash
cd athena-trader
pip install -r requirements.txt
```

### 2. API凭证配置

在 `.env` 文件中配置 OKX Demo API 凭证：

```env
# OKX Demo API Configuration (Simulated Trading)
OKX_DEMO_API_KEY=your_okx_demo_api_key_here
OKX_DEMO_SECRET=your_okx_demo_secret_here
OKX_DEMO_PASSPHRASE=your_okx_demo_passphrase_here
```

**获取API凭证步骤：**

1. 访问 [OKX官网](https://www.okx.com) 并注册账户
2. 进入 API管理 页面
3. 创建新的API密钥，选择 "Demo Trading" 环境
4. 记录 API Key、Secret 和 Passphrase
5. 将凭证填入 `.env` 文件

## 使用方法

### 基本用法

```bash
cd athena-trader
python test_okx_api_connection.py
```

### 测试输出

脚本会显示详细的测试过程和结果：

```
╔════════════════════════════════════════════════════════════╗
║                OKX Demo API 连接测试工具                      ║
╚════════════════════════════════════════════════════════════╝

🚀 开始 OKX Demo API 连接测试
============================================================

🔗 测试 OKX Demo API 连接...
✅ REST客户端初始化成功
✅ API连接成功 - 服务器时间: 2024-12-01 10:30:45

📊 测试 BTC-USDT 市场数据获取...
✅ Ticker数据获取成功:
   当前价格: 96500.5
   24h变化: 2.34%
   24h成交量: 12345.67
✅ 订单簿数据获取成功:
   最佳买价: 96500.0
   最佳卖价: 96501.0
   买盘深度: 10
   卖盘深度: 10
✅ 最近交易数据获取成功: 5 笔交易

📈 测试 OHLCV 数据获取...
获取 BTC-USDT 1m 数据...
✅ 1m: 获取到 100 根K线
   ✅ 数据量充足，适合技术指标计算
   最新3根K线:
     10:25 - O:96500.0 H:96510.0 L:96495.0 C:96505.0 V:123.45
     10:26 - O:96505.0 H:96515.0 L:96500.0 C:96508.0 V:98.76
     10:27 - O:96508.0 H:96520.0 L:96503.0 C:96512.0 V:156.78
...
```

## 测试结果解读

### 成功情况

所有测试通过时会显示：

```
🎉 所有测试通过！OKX Demo API 连接正常
```

### 失败情况

如果测试失败，脚本会提供详细的错误信息和建议：

```
❌ API连接测试失败
💡 建议:
   • 检查 .env 文件中的 OKX Demo API 凭证配置
   • 确认网络连接正常
   • 验证 API 密钥是否有效且未过期
```

## 日志和报告

### 日志文件

测试过程中会生成详细的日志文件：
- 位置：`logs/okx_api_test_YYYYMMDD_HHMMSS.log`
- 包含：完整的测试过程和调试信息

### 测试报告

测试完成后会生成格式化的报告：
- 位置：`logs/okx_api_test_report_YYYYMMDD_HHMMSS.txt`
- 内容：测试结果统计、错误详情、改进建议

## 故障排除

### 常见问题

#### 1. 环境变量未设置

**错误：** `❌ 错误: 未找到 OKX_DEMO_API_KEY 环境变量`

**解决方案：**
- 检查 `.env` 文件是否存在
- 确认环境变量名称正确
- 重启终端或重新加载环境变量

#### 2. API凭证无效

**错误：** `API连接测试失败: Invalid API credentials`

**解决方案：**
- 验证 API Key、Secret、Passphrase 是否正确
- 确认使用的是 Demo 环境的凭证
- 检查 API 密钥是否已过期

#### 3. 网络连接问题

**错误：** `NetworkError: Connection timeout`

**解决方案：**
- 检查网络连接
- 确认防火墙设置
- 尝试使用代理或VPN

#### 4. 数据获取失败

**错误：** `无法获取ticker数据`

**解决方案：**
- 确认交易对符号正确（BTC-USDT）
- 检查 Demo 环境是否支持该交易对
- 稍后重试（可能是临时服务问题）

### 调试技巧

1. **查看详细日志**
   ```bash
   tail -f logs/okx_api_test_*.log
   ```

2. **单独测试连接**
   ```python
   from src.data_manager.rest_client import RESTClient
   client = RESTClient(use_demo=True)
   print(client.exchange.fetch_time())
   ```

3. **检查API权限**
   - 确认API密钥具有读取市场数据的权限
   - 验证IP白名单设置（如果启用）

## 扩展使用

### 自定义测试参数

可以修改脚本中的以下参数：

```python
# 测试交易对
symbol = "BTC-USDT"  # 可改为 ETH-USDT, BNB-USDT 等

# 时间框架
timeframes = ["1m", "5m", "15m", "1h", "4h"]  # 可增减

# 数据量
limit = 100  # 可调整获取的K线数量
```

### 集成到CI/CD

可以将测试脚本集成到持续集成流程中：

```bash
# 在CI脚本中
python test_okx_api_connection.py
if [ $? -eq 0 ]; then
    echo "✅ API连接测试通过"
else
    echo "❌ API连接测试失败"
    exit 1
fi
```

## 技术细节

### 依赖库

- `ccxt`: 加密货币交易所API库
- `requests`: HTTP请求库
- `python-dotenv`: 环境变量管理

### API限制

- Demo环境有请求频率限制
- 建议在测试之间添加适当延迟
- 避免在短时间内发送大量请求

### 数据验证

脚本包含以下数据验证逻辑：

1. **价格合理性检查** - 确保高价≥低价
2. **时间戳验证** - 检查数据时间范围
3. **数据完整性** - 验证OHLCV字段完整性
4. **重复数据检测** - 移除重复的K线数据

## 相关文档

- [OKX API官方文档](https://www.okx.com/docs-v5/)
- [CCXT库文档](https://github.com/ccxt/ccxt)
- [Athena Trader架构文档](./architecture/OKX_TRADING_SYSTEM_ARCHITECTURE.md)

## 支持

如果遇到问题，请：

1. 查看日志文件获取详细错误信息
2. 检查本指南的故障排除部分
3. 提交Issue到项目仓库
4. 联系开发团队获取支持
