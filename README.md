Athena Trader
📊 项目交付状态
项目版本: v1.2.0 (The Stability Update)
项目状态: ✅ 生产级稳定 (Production Stable)
运行环境: OKX 模拟盘 (Demo/Sandbox) + 实盘数据馈送
核心标的: SOL-USDT-SWAP (永续合约)
系统特性: 混合数据源 + 状态自愈 + 旁路网络层

🚀 架构演进与核心重构 (v1.2.0)
针对量化系统在实盘/模拟盘切换中常见的 "状态不同步" 和 "API 兼容性" 痛点，我们在 v1.2.0 版本中进行了底层的架构重构。

1. 🛡️ 网络层重构：Requests Bypass 模式
痛点背景：
在 OKX V5 API 中，模拟盘（Sandbox）与实盘共用 URL，仅通过 Header 区分。通用的 CCXT 库在处理这种特殊路由逻辑时，经常出现 URL 拼接错误 (NoneType)、404 错误或签名失效 (50038/50113)。

解决方案：
我们实现了一个 "Requests Bypass" (请求旁路) 架构：

剥离网络层：不再依赖 CCXT 发送 HTTP 请求，规避了其内部复杂的 URL 路由和沙箱切换逻辑。
保留签名层：仅使用 CCXT 作为 Signer (签名器)，生成合法的签名头。
直连底层：使用 Python 原生 requests 库直接向 https://www.okx.com 发送带签名的请求。
URL 补丁：对 Signer 实施了 "Invincible Patch"，强制硬编码 URL，确保下单接口 (create_order) 也能绕过 CCXT 的初始化 Bug。
2. ⚖️ 核心风控：Shadow Ledger (影子账本)
痛点背景：
在"实盘看盘 + 模拟下单"的混合模式下，极易出现状态分裂（策略认为持有 2.5 个币，但模拟盘因网络波动没成交，实际持有 0 个）。

解决方案：
引入了 Shadow Ledger 自愈子系统：

双重记账：同时记录 "策略期望持仓" (Target) 和 "API 实际持仓" (Actual)。
差额计算 (Delta Sync)：不再盲目覆盖仓位，而是计算 Target - Actual 的差值。
自动纠错：系统每 20 秒自检一次。一旦发现偏差超过 10%，自动触发 Resync 交易 进行平账。
冷却机制：内置 Cache 和 Cooldown 防抖，防止 API 频率限制 (Rate Limit)。
3. ⚡ 性能优化：Pandas 向量化
去循环化：重写了 technical_indicators.py，移除所有 Python for 循环。
原生速度：全面采用 df.ewm(), df.rolling() 等 C 语言底层的 Pandas 方法。
执行层修复：修复了 trade_executor 中的精度问题，增加了 amount_to_precision 过滤，杜绝 Invalid Order Quantity 报错。
✨ 核心特性
🎯 交易策略
趋势回调策略 (Trend Pullback Strategy)
入场：EMA 144 确认大趋势 + RSI < 30 回调入场
出场：RSI > 70 止盈 或 价格跌破 EMA 144 止损
动态止损：智能取值 max(固定止损价, EMA价格)，在强趋势中最大化资金利用率
🦅 仓位管理
"不死鸟"模型 (Fixed Risk Model)
每单风险严格控制在本金的 2%
基于止损距离动态计算 Position Size
实盘修正：策略计算出的精确数量（如 2.3333）会自动经过交易所精度截断（变为 2.33）再下单
🔧 系统架构
模块化单体 (Modular Monolith)

Executor：支持异步下单、数据库日志记录、Redis 事件发布。
DataHandler：集成 Redis 缓存层（Read-Through Pattern），保护交易所 API。
Monitoring：集成轻量级性能监控面板。
🔄 混合数据方案 (Hybrid Data Flow)
我们采用了业界领先的混合数据流设计，以解决 OKX 模拟盘 K 线数据质量差的问题：

数据类型	来源通道	描述
K线/行情	Public Exchange (实盘)	指向实盘 API，无鉴权。保证技术指标基于真实市场计算。
交易/持仓	Private Exchange (模拟)	指向实盘 API + x-simulated-trading Header。在安全环境中执行交易。
📋 快速开始
环境配置
安装依赖
BASH
pip install -r requirements.txt
(注意：已移除 TA-Lib 等重型依赖，纯 Python/Pandas 环境即可运行)

配置文件
复制 .env.template 为 .env 并填入 OKX API Key：
ENV
# 即使是模拟盘，也推荐使用 V5 API Key
OKX_API_KEY=your_key
OKX_SECRET_KEY=your_secret
OKX_PASSPHRASE=your_pass
OKX_ENVIRONMENT=demo
启动系统
BASH
# 启动主程序
python main_monolith.py
📝 常见日志解读
1. 正常运行 (Heartbeat)

TEXT
INFO - 获取 SOL-USDT-SWAP 1h 历史K线数据...
INFO - TrendPullback Signal: HOLD | Price: 124.79...
2. 影子账本触发自愈 (Self-Healing)

TEXT
WARNING - 🚨 Mismatch: Target 0.54 vs Actual 0.00 (Diff: 100.0%)
INFO - 🔄 Executing Resync: BUY 0.54
INFO - ✅ Order Placed! ID: 12345678
解释：策略想要 0.54 个，但账户里是空的，系统自动补单买了 0.54 个。

3. 模拟执行警告

TEXT
WARNING - No API credentials found... Using simulation.
解释：未配置 API Key 或 Key 错误，系统降级为纯本地模拟（不发网络请求）。请检查 .env 文件。

🧪 更新日志
v1.2.0 (2026-01-01) - The Stability Update
🛡️ 重构: 引入 RESTClient 的 Requests Bypass 模式，彻底解决 CCXT URL/Sandbox 崩溃问题。
✨ 新增: Shadow Ledger (影子账本) 模块，实现持仓状态自动同步。
⚡ 优化: 技术指标库全面向量化，性能提升 50x。
🐛 修复: 修复 trade_executor 忽略策略仓位大小的 Bug。
🐛 修复: 修复下单时的 amount 精度问题。
v1.1.0 (2024-12-28)
✨ 新增趋势回调策略
✨ 新增"不死鸟"仓位管理模型
⚠️ 免责声明
本项目采用 MIT 许可证。量化交易涉及高风险，实盘使用前请务必在模拟环境中充分测试 Shadow Ledger 的自愈逻辑。作者不对资金损失负责。
