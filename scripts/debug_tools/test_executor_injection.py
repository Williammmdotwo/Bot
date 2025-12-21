#!/usr/bin/env python3
"""
服务间联调测试 - Mock数据注入测试脚本

前置条件：
1. 确保executor-service已启动 (python src/executor/main.py)
2. 确保executor-service运行在localhost:8002端口
3. 确保环境变量INTERNAL_SERVICE_TOKEN已设置，或使用默认token

测试目标：
- 模拟strategy-service向executor-service发送BUY信号
- 验证executor-service能正确接收和处理信号
- 确认Mock交易执行流程正常
"""

import sys
import os
import json
import time
import uuid
import logging
import requests
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ExecutorInjectionTester:
    """Executor服务注入测试器"""
    
    def __init__(self):
        self.executor_url = "http://localhost:8002"
        self.service_token = self._get_service_token()
        
    def _get_service_token(self) -> str:
        """获取服务间认证token"""
        # 优先使用环境变量
        env_token = os.getenv("INTERNAL_SERVICE_TOKEN")
        if env_token:
            logger.info(f"✅ 使用环境变量中的服务token")
            return env_token
            
        # 使用默认调试token（与executor-service中的硬编码token一致）
        default_token = "athena-internal-token-change-in-production"
        logger.warning(f"⚠️ 使用默认调试token: {default_token}")
        logger.warning("⚠️ 生产环境请设置INTERNAL_SERVICE_TOKEN环境变量")
        return default_token
    
    def create_test_signal(self) -> Dict[str, Any]:
        """构造测试用的BUY信号"""
        print("🔧 正在构造测试信号...")
        
        current_time = int(time.time())
        decision_id = str(uuid.uuid4())
        
        # 构造符合双均线策略输出格式的信号
        signal_data = {
            "signal": "BUY",
            "symbol": "BTC-USDT",
            "decision_id": decision_id,
            "confidence": 75.0,
            "reasoning": "Golden Cross: EMA_9 crosses above EMA_21",
            "position_size": 0.02,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "timestamp": current_time,
            "ema_fast": 49500.0,
            "ema_slow": 48500.0,
            "current_price": 50000.0
        }
        
        print(f"✅ 测试信号构造完成:")
        print(f"   - 信号类型: {signal_data['signal']}")
        print(f"   - 交易对: {signal_data['symbol']}")
        print(f"   - 决策ID: {signal_data['decision_id']}")
        print(f"   - 置信度: {signal_data['confidence']}%")
        print(f"   - 当前价格: ${signal_data['current_price']}")
        print(f"   - 止损价格: ${signal_data['stop_loss']}")
        print(f"   - 止盈价格: ${signal_data['take_profit']}")
        
        return signal_data
    
    def check_executor_health(self) -> bool:
        """检查executor服务健康状态"""
        print("🏥 正在检查Executor服务健康状态...")
        
        try:
            response = requests.get(
                f"{self.executor_url}/api/health",
                timeout=5
            )
            
            if response.status_code == 200:
                health_data = response.json()
                print(f"✅ Executor服务健康检查通过: {health_data}")
                return True
            else:
                print(f"❌ Executor服务健康检查失败: HTTP {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            print("❌ 无法连接到Executor服务，请确保服务已启动在localhost:8002")
            return False
        except requests.exceptions.Timeout:
            print("❌ Executor服务健康检查超时")
            return False
        except Exception as e:
            print(f"❌ Executor服务健康检查异常: {e}")
            return False
    
    def send_signal_to_executor(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """向executor服务发送交易信号"""
        print(f"📡 正在发送请求到Executor ({self.executor_url})...")
        
        # 构造请求体
        request_body = {
            "signal": signal_data,
            "use_demo": True,  # 使用模拟交易模式
            "stop_loss_pct": 0.03,  # 3%止损
            "take_profit_pct": 0.06  # 6%止盈
        }
        
        # 设置请求头
        headers = {
            "Content-Type": "application/json",
            "x-service-token": self.service_token
        }
        
        try:
            print(f"📤 请求详情:")
            print(f"   - URL: {self.executor_url}/api/execute-trade")
            print(f"   - Method: POST")
            print(f"   - Token: {self.service_token[:10]}...")
            print(f"   - Body: {json.dumps(request_body, indent=2)}")
            
            # 发送请求
            response = requests.post(
                f"{self.executor_url}/api/execute-trade",
                json=request_body,
                headers=headers,
                timeout=10
            )
            
            print(f"📥 收到响应:")
            print(f"   - 状态码: {response.status_code}")
            print(f"   - 响应时间: {response.elapsed.total_seconds():.2f}s")
            
            if response.status_code == 200:
                response_data = response.json()
                print(f"✅ 请求成功!")
                print(f"   - 执行状态: {response_data.get('status')}")
                print(f"   - 订单ID: {response_data.get('order_id')}")
                print(f"   - 交易对: {response_data.get('symbol')}")
                print(f"   - 方向: {response_data.get('side')}")
                print(f"   - 数量: {response_data.get('amount')}")
                print(f"   - 价格: ${response_data.get('price')}")
                print(f"   - 消息: {response_data.get('message')}")
                return response_data
            else:
                print(f"❌ 请求失败!")
                print(f"   - 错误状态码: {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   - 错误详情: {error_data}")
                except:
                    print(f"   - 错误文本: {response.text}")
                return {"status": "failed", "error": response.text}
                
        except requests.exceptions.ConnectionError:
            print("❌ 连接失败，无法连接到Executor服务")
            return {"status": "failed", "error": "Connection failed"}
        except requests.exceptions.Timeout:
            print("❌ 请求超时")
            return {"status": "failed", "error": "Request timeout"}
        except Exception as e:
            print(f"❌ 请求异常: {e}")
            return {"status": "failed", "error": str(e)}
    
    def run_integration_test(self) -> bool:
        """运行完整的集成测试"""
        print("🚀 开始服务间联调测试")
        print("=" * 60)
        
        # 1. 健康检查
        if not self.check_executor_health():
            print("\n❌ 测试终止：Executor服务不可用")
            return False
        
        print("\n" + "-" * 60)
        
        # 2. 构造测试信号
        signal_data = self.create_test_signal()
        
        print("\n" + "-" * 60)
        
        # 3. 发送信号
        response_data = self.send_signal_to_executor(signal_data)
        
        print("\n" + "=" * 60)
        
        # 4. 结果评估
        if response_data.get("status") in ["executed", "simulated"]:
            print("🎉 集成测试成功!")
            print("✅ 信号发送成功")
            print("✅ Executor服务收到信号")
            print("✅ 模拟下单成功")
            print(f"✅ 订单ID: {response_data.get('order_id')}")
            return True
        else:
            print("❌ 集成测试失败!")
            print(f"❌ 错误信息: {response_data.get('error')}")
            return False

def main():
    """主函数"""
    print("🧪 Executor服务注入测试脚本")
    print("📋 测试目标: 验证Strategy -> Executor信号流转")
    print("🔧 前置条件: Executor服务需运行在localhost:8002")
    print()
    
    # 创建测试器
    tester = ExecutorInjectionTester()
    
    # 运行测试
    success = tester.run_integration_test()
    
    print("\n" + "=" * 60)
    if success:
        print("🏁 测试完成 - 全部通过!")
        print("🎯 服务间联调验证成功，可以部署使用")
        sys.exit(0)
    else:
        print("🏁 测试完成 - 存在问题!")
        print("⚠️ 请检查服务状态和配置后重试")
        sys.exit(1)

if __name__ == "__main__":
    main()
