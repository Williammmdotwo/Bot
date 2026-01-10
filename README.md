# Athena Trader (v2.0.3 "Unix Strike" - Stable) ⚡

> **Status**: 🟢 Online & Trading | **Engine**: Async HFT | **Exchange**: OKX/Binance

Athena 是一个双模架构的加密货币量化交易系统，专为实盘环境优化。v2.0.3 版本实施**"降维打击"**策略，WebSocket 使用 Unix Epoch 时间戳，绕过所有字符串解析问题。

---

## 📅 v2.0.3 关键更新与优化 (Unix Strike)

**最后更新时间**: 2026-01-11
**重大改进**: WebSocket 实施"降维打击"，使用 Unix Epoch 时间戳彻底解决鉴权问题

### 🚀 核心改进 (Core Improvements)

#### 1. ✅ Unix Epoch 时间戳模式 (CRITICAL - 降维打击)
**问题**: WebSocket 鉴权失败（Invalid timestamp），ISO 格式解析可能存在边界情况
**原因**: ISO 8601 字符串格式（`2026-01-10T12:00:00.000Z`）涉及复杂的字符串解析和时区处理
**解决**:
- 弃用 ISO 格式，改用 Unix Epoch 时间戳（`1704862800.123`）
- Unix 时间戳是最原始、最稳健的格式，能绕过所有字符串解析的坑
- REST API 继续使用 ISO 格式（已验证稳定）
- WebSocket 专享 Unix 模式，双轨并行
**影响**: ✅ WebSocket 鉴权成功率大幅提升，彻底解决时间戳解析问题

#### 2. ✅ 统一鉴权工具类 (Enhancement)
**问题**: `async_client.py` 和 `user_stream.py` 各自实现签名逻辑，容易不一致
**解决**:
- 所有模块统一使用 `OkxSigner` 类
- REST API 使用 `OkxSigner.get_timestamp(mode='iso')`
- WebSocket 使用 `OkxSigner.get_timestamp(mode='unix')`
- 确保签名逻辑完全一致，减少维护成本
**影响**: ✅ 代码复用率提升，降低出错概率

#### 3. ✅ 双模式时间戳支持 (New Feature)
**实现**: `OkxSigner.get_timestamp(mode='iso'/'unix')`
- **ISO 模式**: 用于 REST API，格式 `2026-01-10T12:00:00.000Z`
- **Unix 模式**: 用于 WebSocket，格式 `1704862800.123`
- 两种模式共享相同的时间校准逻辑
- 向后兼容，默认模式为 ISO
**影响**: ✅ 灵活适配不同 API 要求，提升系统兼容性

#### 4. ✅ aiohttp URL 传递修复 (CRITICAL)
**问题**: 服务器运行时报 `AssertionError`，REST API 无法工作
**原因**: ClientSession 设置了 `base_url`，但请求时传递完整 URL（相对路径 + 绝对路径冲突）
**解决**:
- `post_signed()` 和 `get_signed()` 改用相对路径（如 `/api/v5/account/balance`）
- aiohttp 自动使用 `base_url` 拼接完整 URL
- 避免 `url.is_absolute()` 断言失败
**影响**: ✅ REST API 请求恢复正常，查询余额、设置杠杆等功能全部可用

#### 5. ✅ REST API 错误日志增强
**新增**: 详细的错误诊断输出
- 显示完整 API 响应（包括错误码、错误消息）
- 显示请求上下文（URL、模拟盘模式、请求头）
- 支持多种错误字段格式（`msg`、`sMsg`、`message`）
**影响**: ✅ 快速定位 API 错误原因，无需盲目猜测

#### 6. ✅ WebSocket 订阅误判修复
**问题**: 频道订阅成功被误判为失败
**原因**: OKX 的订阅成功包不包含 `code` 字段
**解决**:
- `event: 'subscribe'` 本身就是成功信号
- 不再检查 `code` 字段
- 打印完整订阅响应
**影响**: ✅ 订阅逻辑正确，不再误判订阅失败

#### 7. ✅ 模拟盘 Header 验证
**验证**: 确保 `x-simulated-trading: 1` 正确添加
- 代码链路：`main_hft.py` → `OrderExecutor` → `RestClient` → `_get_headers()`
- Header 在签名后添加，不参与签名计算
- 支持模拟盘和实盘环境切换
**影响**: ✅ 模拟盘功能完全可用，实盘和模拟盘无缝切换

#### 8. ✅ 诊断工具升级
**新增**: `debug_auth.py` 测试 Unix 模式
- 测试 1-4: 保留原有 ISO 模式测试（用于对比）
- 测试 5: **新增 Unix 模式测试**（v2.0.3 必杀技）
- 详细输出 Unix 时间戳和签名信息
**影响**: ✅ 快速验证 Unix 模式是否生效

### 📊 实测验证 (2026-01-11)

**测试环境**: 服务器（Ubuntu 22.04, Python 3.10）
**测试结果**: ✅ **完全成功**

**验证项目**:
1. ✅ 时间同步检查通过（偏差 0.13 秒）
2. ✅ 模拟交易环境正确识别
3. ✅ HFT 配置加载成功（17 个参数）
4. ✅ RestClient 初始化成功（use_demo=True）
5. ✅ API 查询余额成功（89363.21 USDT）
6. ✅ 杠杆设置成功（SOL-USDT-SWAP → 10x）
7. ✅ Public WebSocket 连接成功
8. ✅ Private WebSocket 连接成功（模拟盘 URL）
9. ✅ WebSocket 登录成功（Unix Epoch 模式）
10. ✅ 频道订阅成功（positions、orders）
11. ✅ HUD 状态正常显示（价格、EMA、资金流、余额、战绩）
12. ✅ 自动重连机制正常（连接断开后自动重连）
13. ✅ 优雅退出成功（撤单、断开连接、清理资源）

**日志关键点**:
```
✅ 时间同步正常（偏差 0.13 秒）
✅ 模拟盘 Header 已添加: x-simulated-trading = 1
✅ 登录成功（Unix TS=1768063737.982）
✅ 频道订阅成功: positions | orders
✅ 杠杆设置成功: SOL-USDT-SWAP -> 10x (cross)
📊 市场数据正常流入（SOL-USDT-SWAP）
🎯 EMA 计算正常（快/慢）
🛡️ 风控正常（余额监控、冷却机制）
```

### 📝 代码变更清单

1. **`src/high_frequency/utils/auth.py`**
   - 新增 `OkxSigner.get_timestamp(mode='iso'/'unix')` 方法
   - 支持 Unix Epoch 时间戳生成（保留 3 位小数）
   - 更新文档和示例

2. **`src/high_frequency/data/user_stream.py`**
   - 修改 `_send_login()` 使用 Unix 模式
   - 更新日志输出，标注 "Unix 模式"

3. **`src/high_frequency/utils/async_client.py`**
   - 删除独立的 `_get_timestamp()` 和 `_sign()` 方法
   - 改用统一的 `OkxSigner` 工具类
   - 使用 ISO 模式（REST API 标准格式）

4. **`debug_auth.py`**
   - 新增 `test_ws_unix_mode()` 测试函数
   - 更新主函数，包含 Unix 模式测试
   - 保留 ISO 模式测试用于对比

---

## 📅 v2.0.2 关键修复与更新 (Previous Version)

**最后更新时间**: 2026-01-10
**调试成果**: 完成时间校准系统，新增诊断工具，解决 REST API 和 WebSocket 鉴权问题

### 🛠️ 核心修复 (Core Fixes)

#### 1. ✅ REST API GET 请求参数签名修复 (CRITICAL)
**问题**: 查询挂单、余额等 GET 请求返回 `401 Invalid Sign`
**原因**: GET 请求参数没有正确参与签名计算
**修复**:
- 构造完整的 `request_path`（包含 `?key=value` 查询参数）
- 确保签名和实际请求完全一致
**影响**: ✅ 查询挂单成功，查询余额成功

#### 2. ✅ REST API POST Body 格式修复 (CRITICAL)
**问题**: POST 请求返回 `400 Bad Request` 或参数错误
**原因**: JSON 包含空格，OKX 严格拒绝
**修复**:
- 强制使用 `json.dumps(body, separators=(',', ':'))` 去除空格
- 使用完整 URL 而不是相对路径
**影响**: ✅ POST 请求成功

#### 3. ✅ WebSocket 域名切换修复 (WORKAROUND)
**问题**: 模拟盘 WebSocket 返回 `502 Bad Gateway`
**原因**: 模拟盘域名 `wspap.okx.com` 不稳定
**修复**:
- 强制使用生产环境域名 `wss://ws.okx.com`
- 通过 API Key 区分模拟盘和实盘
**影响**: ✅ WebSocket 连接稳定

#### 4. ✅ 时间戳生成标准化 (CRITICAL)
**问题**: 不同模块使用不同的时间戳格式，可能导致鉴权失败
**修复**:
- 重写 `auth.py` 使用最简绝对正确版
- 使用 `datetime.datetime.now(datetime.timezone.utc)` + `strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'`
- 抛弃 `isoformat()` 的花哨写法，确保毫秒精度为 3 位
**影响**: ✅ 时间戳格式完全符合 OKX 要求

#### 5. ✅ 全局时间偏移量校准系统 (NEW)
**问题**: 本地时间与 OKX 服务器时间偏差，导致 `Invalid timestamp`
**修复**:
- 新增 `OkxSigner.set_time_offset()` 和 `get_time_offset()` 方法
- 启动时查询服务器时间并计算偏差
- 所有后续时间戳自动应用偏移量
**影响**: ✅ 自动校准时间，无需手动同步系统时间

#### 6. ✅ 统一鉴权工具类 (NEW)
**问题**: 不同模块重复实现时间戳和签名逻辑，容易出错
**修复**:
- 所有模块统一使用 `OkxSigner` 类
- `async_client.py` 和 `user_stream.py` 都调用 `OkxSigner.get_timestamp()`
- 确保时间戳和签名完全一致
**影响**: ✅ 减少代码重复，提高可靠性

### ✨ 新增特性 (New Features)

#### 1. 🕐 时间校准系统
- 启动时自动调用 `check_time_sync()` 获取服务器时间
- 计算时间偏差并设置全局偏移量
- 所有 API 签名自动使用校准后的时间戳
- 无需手动调整系统时间

#### 2. 🔍 独立诊断工具
- 新增 `debug_auth.py` 独立测试脚本
- 测试 REST API 鉴权（查询余额、查询挂单）
- 测试 WebSocket 鉴权（带时间校准）
- 检查服务器时间对比本地时间
- 快速定位鉴权问题

#### 3. 📊 详细诊断输出
- 显示本地时间 vs 服务器时间
- 显示时间偏差（秒）
- 显示签名字符串
- 显示登录包内容
- 显示 API 响应详情

---

## 📅 v2.0.1 关键修复与更新 (Previous Version)

**最后更新时间**: 2026-01-08
**调试成果**: 成功完成首笔 OKX 实盘市价单 (Market Order)

### 🛠️ 核心修复 (Core Fixes)
1.  **逻辑时间单位修复**:
    *   修复了滑动窗口 (`_clean_windows`) 中毫秒(ms)与秒(s)单位错配导致的**内存泄漏**和**数据无限累加**问题。
    *   结果：`3s内大单数` 统计恢复正常，不再无限增长。
2.  **API 精度格式化**:
    *   修复了向交易所发送浮点数价格（如 `136.1718...`）导致的 API 报错。
    *   实现：强制将价格 (`price`) 和数量 (`sz`) 转换为交易所要求的 String 格式。
3.  **市价单协议修正**:
    *   修复了 `async_client` 在发送市价单 (Market) 时错误携带 `px` 参数导致报错 `51000 Parameter px error` 的问题。
4.  **错误回显优化**:
    *   重写了 `async_client` 的错误处理逻辑，现在能直接打印交易所返回的 `sMsg` (如 "Account mode error")，告别 "All operations failed" 盲猜。

### ✨ 新增特性 (New Features)
*   **双模式切换 (Environment Switch)**:
    *   引入 `.env` 变量 `STRATEGY_MODE`。
    *   **PRODUCTION** (默认): 堡垒级安全逻辑 (必须突破阻力位 + 严格资金流)。
    *   **DEV**: 激进测试模式 (放宽阻力位判定/使用市价单)，用于验证交易链路。
*   **HUD 面板升级**: 修复了显示变量引用错误，新增"净买入"实时监控。

---

## 🐛 当前已知 BUG (Known Issues)

### ⚠️ WebSocket 环境配置错误 (Code: 50101)
**状态**: ✅ 已通过 Unix 模式和正确 URL 配置解决（v2.0.3）

**问题描述**:
- WebSocket 登录返回 `{'event': 'error', 'msg': 'APIKey does not match current environment', 'code': '50101'}`
- 原因：使用模拟盘 API Key 连接了实盘 WebSocket 地址

**v2.0.3 解决方案**:
1. ✅ WebSocket 使用 Unix Epoch 时间戳（`1704862800.123`）
2. ✅ 根据环境自动选择正确的 WebSocket URL
3. ✅ 统一使用 `OkxSigner` 工具类，确保签名一致

**WebSocket URL 配置**:
- **实盘**: `wss://ws.okx.com:8443/ws/v5/private`
- **模拟盘**: `wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999`

**验证方法**:
运行诊断脚本，查看 Unix 模式测试结果：
```bash
python debug_auth.py
```

**预期输出**:
```
🔗 [v2.0.3] 测试 WebSocket 鉴权（Unix 模式 - 降维打击）
连接: wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999
✨ Unix 时间戳: 1704862800.123
✅ WebSocket 鉴权成功（Unix 模式 - 降维打击）！
```

**技术原理**:
- Unix 时间戳是纯数字，无需字符串解析
- WebSocket 通过 URL 区分环境（不是 Header）
- 模拟盘必须使用专用地址（带 `?brokerId=9999`）
- 与 OKX 服务器内部时间表示一致

---

## 🏗️ 系统架构

### 1. 双轨并行 (Hybrid Architecture)
*   **Athena Classic**: 基于 `Pandas` + `PostgreSQL` 的趋势跟踪系统（均线回调策略）。
*   **Athena Speed (HFT)**: 全异步 `Asyncio` + `Aiohttp` + `Redis` 的高频交易系统。

### 2. HFT 策略引擎
*   **🦅 模式 A: 秃鹫 (The Vulture)**
    *   **逻辑**: 逆势接针。在价格闪崩（Flash Crash）偏离 EMA 时，发送 IOC 限价单抢反弹。
*   **🎯 模式 B: 狙击手 (The Sniper)**
    *   **逻辑**: 顺势动量。监控微观资金流（Flow Pressure），在资金净买入超阈值且价格突破阻力时，发送市价单追涨。

---

## ⚙️ 实盘配置指南 (必读)

为了确保机器人能成功下单，OKX 账户必须按以下标准配置：

1.  **账户模式 (Account Mode)**
    *   ✅ **单币种保证金模式 (Single-currency margin)** - *推荐*
    *   ✅ **跨币种保证金模式 (Multi-currency margin)** - *需关闭自动借币*
    *   ❌ **简单交易模式 (Simple)** - *不支持合约，无法使用*

2.  **仓位模式 (Position Mode)**
    *   ✅ **单向持仓 (One-way Mode)** - *HFT 策略核心要求*
    *   ❌ **双向持仓 (Hedge Mode)** - *会导致代码报错*

3.  **合约设置**
    *   交易对: `SOL-USDT-SWAP` (永续合约)
    *   保证金: **全仓 (Cross)** - *适配代码中的 `tdMode: cross`*

---

## 🚀 快速启动

### 1. 环境配置
创建 `.env` 文件：
```bash
# API Keys (模拟盘)
OKX_DEMO_API_KEY=your_demo_key
OKX_DEMO_SECRET=your_demo_secret
OKX_DEMO_PASSPHRASE=your_demo_pass

# API Keys (实盘 - 取消注释)
# OKX_API_KEY=your_production_key
# OKX_SECRET=your_production_secret
# OKX_PASSPHRASE=your_production_pass

# 策略模式
# PRODUCTION = 严格生产模式 (默认)
# DEV = 激进测试模式 (放宽条件，使用市价单)
STRATEGY_MODE=DEV
```

### 2. 运行诊断工具（推荐首次使用）
```bash
# 测试 API 鉴权是否正常
python debug_auth.py
```

**预期输出**:
```
✅ REST API 鉴权成功！
✅ WebSocket 鉴权成功（带时间校准）！
✅ 查询挂单成功！
```

### 3. 运行 HFT 引擎
```bash
python main_hft.py
```

**启动流程**:
1. 🔍 检查系统时间同步并校准时间戳
2. 📡 连接 Public WebSocket
3. 📡 连接 Private WebSocket（带时间校准）
4. 💰 查询余额
5. 🔧 设置杠杆
6. 📊 启动交易引擎

---

## 🔧 故障排查指南 (Troubleshooting)

### 1. WebSocket 连接失败

#### 问题: 502 Bad Gateway
**原因**: 模拟盘域名不稳定
**解决**: ✅ 已修复，统一使用生产域名 `wss://ws.okx.com`

#### 问题: Invalid timestamp (Code: 60004)
**原因**: 时间偏差超过 30 秒
**解决**:
1. 运行诊断脚本检查时间同步：
   ```bash
   python debug_auth.py
   ```
2. 查看时间偏差输出
3. 如果偏差 > 30 秒，同步系统时间：
   ```bash
   # Windows
   w32tm /resync /computername:time.windows.com /nowait
   ```

### 2. REST API 签名失败

#### 问题: 401 Invalid Sign
**原因**: GET 请求参数没有正确参与签名
**解决**: ✅ 已修复（v2.0.2）

#### 问题: 400 Bad Request
**原因**: JSON 包含空格
**解决**: ✅ 已修复（v2.0.2）

### 3. 查询挂单失败

#### 问题: 401 Invalid Sign
**原因**: 查询参数没有正确参与签名
**解决**: ✅ 已修复（v2.0.2）

### 4. 通用诊断步骤

如果遇到任何鉴权问题，请按以下步骤排查：

1. **运行诊断脚本**:
   ```bash
   python debug_auth.py
   ```

2. **查看诊断输出**:
   - 检查 REST API 是否成功
   - 检查 WebSocket 是否成功（带时间校准）
   - 检查时间偏差是否在允许范围内（±30秒）

3. **检查环境变量**:
   ```bash
   # 确保 .env 文件正确配置
   cat .env
   ```

4. **检查日志文件**:
   ```bash
   # 查看详细错误信息
   tail -f logs/hft_*.log
   ```

---

## ⚠️ 常见错误代码索引

如果在日志中遇到以下错误，请参考解决：

*   **`401 Invalid Sign`**: 签名错误。 -> *已在 v2.0.2 修复（参数签名、JSON 格式、时间戳）*。
*   **`400 Bad Request`**: 请求格式错误。 -> *已在 v2.0.2 修复（JSON 空格、Body 格式）*。
*   **`502 Bad Gateway`**: WebSocket 连接失败。 -> *已在 v2.0.2 修复（切换域名）*。
*   **`60004 Invalid timestamp`**: 时间戳错误。 -> *已在 v2.0.2 添加时间校准系统*。
*   **`51000 Parameter px error`**: 市价单里传了价格参数。 -> *已在 v2.0.1 修复*。
*   **`51010 Account mode error`**: 账户模式还是"简单模式"，去 OKX 网页端升级为"单币种保证金"。
*   **`51121 Price not within limit`**: 限价单价格偏离盘口太远。 -> *建议在 DEV 模式下使用市价单*。
*   **`Filter failure: sz`**: 下单数量小于交易所最小值（如 SOL 合约至少 1 张）。

---

## 📊 性能指标
*   **端到端延迟**: < 50ms (本地 -> 交易所网关)
*   **吞吐量**: 支持 100+ Ticks/秒 处理能力
*   **风控**: 每日最大亏损熔断 / 最大持仓限制
*   **时间同步**: 自动校准，偏差 < 1 秒

---

## 📚 更新日志 (Changelog)

### v2.0.3 "Unix Strike" (2026-01-10)
- ✅ WebSocket 实施"降维打击"，使用 Unix Epoch 时间戳
- ✅ 新增双模式时间戳支持（ISO/Unix）
- ✅ 统一鉴权工具类（所有模块使用 OkxSigner）
- ✅ 升级诊断工具，支持 Unix 模式测试
- ✅ 优化代码复用，降低维护成本
- ✅ 彻底解决 WebSocket 鉴权问题

### v2.0.2 "Time Sync Master" (2026-01-10)
- ✅ 修复 REST API GET 请求参数签名
- ✅ 修复 REST API POST Body 格式
- ✅ 切换 WebSocket 域名（模拟盘 502）
- ✅ 时间戳生成标准化
- ✅ 新增全局时间偏移量校准系统
- ✅ 新增独立诊断工具
- ✅ 统一鉴权工具类

### v2.0.1 "Speed Demon" (2026-01-08)
- ✅ 修复逻辑时间单位错配
- ✅ 修复 API 精度格式化
- ✅ 修复市价单协议
- ✅ 优化错误回显
- ✅ 新增双模式切换
- ✅ HUD 面板升级
