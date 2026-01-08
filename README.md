```markdown
# Athena Trader (v2.0.1 "Speed Demon" - Stable) ⚡

> **Status**: 🟢 Online & Trading | **Engine**: Async HFT | **Exchange**: OKX/Binance

Athena 是一个双模架构的加密货币量化交易系统，专为实盘环境优化。v2.0.1 版本在 "Speed Demon" 的基础上修复了核心逻辑漏洞，并打通了 OKX 实盘交易链路。

---

## 📅 v2.0.1 关键修复与更新 (Critical Patches)

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
*   **HUD 面板升级**: 修复了显示变量引用错误，新增“净买入”实时监控。

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
    *   ✅ 跨币种保证金模式 (Multi-currency margin) - *需关闭自动借币*
    *   ❌ 简单交易模式 (Simple) - *不支持合约，无法使用*

2.  **仓位模式 (Position Mode)**
    *   ✅ **单向持仓 (One-way Mode)** - *HFT 策略核心要求*
    *   ❌ 双向持仓 (Hedge Mode) - *会导致代码报错*

3.  **合约设置**
    *   交易对: `SOL-USDT-SWAP` (永续合约)
    *   保证金: **全仓 (Cross)** - *适配代码中的 `tdMode: cross`*

---

## 🚀 快速启动

### 1. 环境配置
创建 `.env` 文件：
```bash
# API Keys
OKX_API_KEY=your_key
OKX_SECRET_KEY=your_secret
OKX_PASSPHRASE=your_pass

# 策略模式
# PRODUCTION = 严格生产模式 (默认)
# DEV = 激进测试模式 (放宽条件，使用市价单)
STRATEGY_MODE=DEV
```

### 2. 运行 HFT 引擎
```bash
python main_hft.py
```

---

## ⚠️ 常见错误代码索引

如果在日志中遇到以下错误，请参考解决：

*   **`51000 Parameter px error`**: 市价单里传了价格参数。 -> *已在 v2.0.1 修复*。
*   **`51010 Account mode error`**: 账户模式还是“简单模式”，去 OKX 网页端升级为“单币种保证金”。
*   **`51121 Price not within limit`**: 限价单价格偏离盘口太远。 -> *建议在 DEV 模式下使用市价单*。
*   **`Filter failure: sz`**: 下单数量小于交易所最小值（如 SOL 合约至少 1 张）。

---

## 📊 性能指标
*   **端到端延迟**: < 50ms (本地 -> 交易所网关)
*   **吞吐量**: 支持 100+ Ticks/秒 处理能力
*   **风控**: 每日最大亏损熔断 / 最大持仓限制
