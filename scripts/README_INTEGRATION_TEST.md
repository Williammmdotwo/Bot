# 服务间联调测试指南

## 📋 概述

`test_executor_injection.py` 是一个专门用于测试 Strategy-Service 与 Executor-Service 之间信号流转的集成测试脚本。

## 🎯 测试目标

验证完整的信号流转流程：
```
Strategy Service (模拟) → HTTP请求 → Executor Service → Mock交易执行
```

## 🚀 使用方法

### 1. 启动 Executor Service

```bash
# 在项目根目录下
cd athena-trader
python src/executor/main.py
```

Executor Service 将启动在 `localhost:8002`

### 2. 运行集成测试

```bash
# 在新终端中
cd athena-trader
python scripts/test_executor_injection.py
```

## 📊 预期输出

```
🧪 Executor服务注入测试脚本
📋 测试目标: 验证Strategy -> Executor信号流转
🔧 前置条件: Executor服务需运行在localhost:8002

🚀 开始服务间联调测试
============================================================
🏥 正在检查Executor服务健康状态...
✅ Executor服务健康检查通过: {'status': 'healthy', 'service': 'executor-api'}

------------------------------------------------------------
🔧 正在构造测试信号...
✅ 测试信号构造完成:
   - 信号类型: BUY
   - 交易对: BTC-USDT
   - 决策ID: 123e4567-e89b-12d3-a456-426614174000
   - 置信度: 75.0%
   - 当前价格: $50000.0
   - 止损价格: $49000.0
   - 止盈价格: $52000.0

------------------------------------------------------------
📡 正在发送请求到Executor (http://localhost:8002)...
📤 请求详情:
   - URL: http://localhost:8002/api/execute-trade
   - Method: POST
   - Token: athena-int...
   - Body: {
     "signal": {
       "signal": "BUY",
       "symbol": "BTC-USDT",
       "decision_id": "123e4567-e89b-12d3-a456-426614174000",
       ...
     },
     "use_demo": true,
     "stop_loss_pct": 0.03,
     "take_profit_pct": 0.06
   }
📥 收到响应:
   - 状态码: 200
   - 响应时间: 0.15s
✅ 请求成功!
   - 执行状态: simulated
   - 订单ID: demo_123e4567-e89b-12d3-a456-426614174000_1703123456
   - 交易对: BTC-USDT
   - 方向: buy
   - 数量: 100.0
   - 价格: 90000.0
   - 消息: Simulated BUY order for BTC-USDT

============================================================
🎉 集成测试成功!
✅ 信号发送成功
✅ Executor服务收到信号
✅ 模拟下单成功
✅ 订单ID: demo_123e4567-e89b-12d3-a456-426614174000_1703123456

============================================================
🏁 测试完成 - 全部通过!
🎯 服务间联调验证成功，可以部署使用
```

## 🔧 配置说明

### 服务认证Token

脚本会自动处理认证token：

1. **环境变量优先**: 如果设置了 `INTERNAL_SERVICE_TOKEN` 环境变量，将使用该值
2. **默认Token**: 如果未设置环境变量，使用默认调试token `athena-internal-token-change-in-production`

### 设置环境变量（可选）

```bash
# Windows
set INTERNAL_SERVICE_TOKEN=your-production-token

# Linux/Mac
export INTERNAL_SERVICE_TOKEN=your-production-token
```

## 🐛 故障排除

### 1. 连接失败
```
❌ 无法连接到Executor服务，请确保服务已启动在localhost:8002
```
**解决方案**: 确保executor-service正在运行
```bash
python src/executor/main.py
```

### 2. 认证失败
```
❌ 请求失败!
   - 错误状态码: 401
   - 错误详情: {"detail": "Invalid service token"}
```
**解决方案**: 检查token配置，确保与executor-service中的token一致

### 3. 端口冲突
```
❌ 连接失败，无法连接到Executor服务
```
**解决方案**: 
- 检查端口8002是否被占用
- 修改脚本中的 `self.executor_url` 为正确的端口

## 📝 测试信号格式

脚本发送的信号完全符合双均线策略的输出格式：

```json
{
  "signal": "BUY",
  "symbol": "BTC-USDT", 
  "decision_id": "uuid-string",
  "confidence": 75.0,
  "reasoning": "Golden Cross: EMA_9 crosses above EMA_21",
  "position_size": 0.02,
  "stop_loss": 49000.0,
  "take_profit": 52000.0,
  "timestamp": 1703123456,
  "ema_fast": 49500.0,
  "ema_slow": 48500.0,
  "current_price": 50000.0
}
```

## 🎯 验证要点

成功的测试应该验证：

- ✅ **服务健康检查**: Executor服务响应正常
- ✅ **信号格式正确**: 符合executor期望的格式
- ✅ **认证通过**: 服务间token验证成功
- ✅ **请求处理**: executor正确解析信号
- ✅ **模拟执行**: Mock交易逻辑正常工作
- ✅ **响应格式**: 返回标准的执行结果

## 🔄 扩展测试

可以修改脚本中的 `create_test_signal()` 方法来测试不同场景：

- **SELL信号**: 将 `"signal": "BUY"` 改为 `"signal": "SELL"`
- **不同交易对**: 修改 `"symbol": "BTC-USDT"` 为其他交易对
- **不同参数**: 调整价格、数量、止损止盈等参数

---

**注意**: 这个测试使用Mock模式，不会进行真实交易。生产环境使用前请确保正确配置了真实的交易所API。
