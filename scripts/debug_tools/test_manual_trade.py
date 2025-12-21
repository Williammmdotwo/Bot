#!/usr/bin/env python3
"""
手动交易测试脚本
用于向 Executor Service 发送交易信号进行测试
"""

import requests
import json
import time
import logging
from typing import Dict, Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ManualTradeTester:
    """手动交易测试器"""
    
    def __init__(self, executor_url: str = "http://localhost:8002", service_token: str = "athena-trading-token"):
        self.executor_url = executor_url
        self.service_token = service_token
        self.headers = {
            "Content-Type": "application/json",
            "X-Service-Token": service_token
        }
    
    def send_trade_signal(self, signal: str, symbol: str = "BTC-USDT", confidence: float = 0.8, 
                         use_demo: bool = True, stop_loss_pct: float = 0.03, 
                         take_profit_pct: float = 0.06) -> Dict[str, Any]:
        """
        发送交易信号到 Executor Service
        
        Args:
            signal: 交易信号 ("BUY", "SELL", "HOLD")
            symbol: 交易对
            confidence: 信号置信度
            use_demo: 是否使用模拟交易
            stop_loss_pct: 止损百分比
            take_profit_pct: 止盈百分比
        
        Returns:
            API响应结果
        """
        url = f"{self.executor_url}/api/execute-trade"
        
        payload = {
            "signal": {
                "signal": signal,
                "symbol": symbol,
                "confidence": confidence,
                "decision_id": f"manual_test_{int(time.time())}"
            },
            "use_demo": use_demo,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct
        }
        
        try:
            logger.info(f"发送交易信号: {signal} {symbol}")
            logger.info(f"请求URL: {url}")
            logger.info(f"请求载荷: {json.dumps(payload, indent=2)}")
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=10)
            
            logger.info(f"响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"交易执行成功: {json.dumps(result, indent=2)}")
                return result
            else:
                logger.error(f"交易执行失败: {response.status_code} - {response.text}")
                return {"error": response.text, "status_code": response.status_code}
                
        except requests.exceptions.RequestException as e:
            logger.error(f"请求异常: {e}")
            return {"error": str(e)}
    
    def check_executor_health(self) -> bool:
        """检查 Executor Service 健康状态"""
        try:
            url = f"{self.executor_url}/health"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                logger.info("✅ Executor Service 健康状态正常")
                return True
            else:
                logger.error(f"❌ Executor Service 健康检查失败: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 无法连接到 Executor Service: {e}")
            return False
    
    def test_buy_signal(self):
        """测试买入信号"""
        logger.info("🟢 测试买入信号...")
        return self.send_trade_signal("BUY", "BTC-USDT", 0.85)
    
    def test_sell_signal(self):
        """测试卖出信号"""
        logger.info("🔴 测试卖出信号...")
        return self.send_trade_signal("SELL", "BTC-USDT", 0.75)
    
    def test_hold_signal(self):
        """测试持有信号"""
        logger.info("⚪ 测试持有信号...")
        return self.send_trade_signal("HOLD", "BTC-USDT", 0.5)
    
    def run_full_test_cycle(self):
        """运行完整的测试周期"""
        logger.info("🚀 开始完整交易测试周期...")
        
        # 1. 检查服务健康状态
        if not self.check_executor_health():
            logger.error("❌ Executor Service 不可用，终止测试")
            return False
        
        # 2. 测试买入信号
        buy_result = self.test_buy_signal()
        if "error" in buy_result:
            logger.error("❌ 买入信号测试失败")
            return False
        
        # 等待一段时间
        logger.info("⏳ 等待 3 秒...")
        time.sleep(3)
        
        # 3. 测试持有信号
        hold_result = self.test_hold_signal()
        if "error" in hold_result:
            logger.error("❌ 持有信号测试失败")
            return False
        
        # 等待一段时间
        logger.info("⏳ 等待 3 秒...")
        time.sleep(3)
        
        # 4. 测试卖出信号
        sell_result = self.test_sell_signal()
        if "error" in sell_result:
            logger.error("❌ 卖出信号测试失败")
            return False
        
        logger.info("✅ 完整交易测试周期完成")
        return True


def main():
    """主函数"""
    print("🎯 Athena Trader 手动交易测试工具")
    print("=" * 50)
    
    # 创建测试器实例
    tester = ManualTradeTester()
    
    # 检查命令行参数
    import sys
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "buy":
            tester.test_buy_signal()
        elif command == "sell":
            tester.test_sell_signal()
        elif command == "hold":
            tester.test_hold_signal()
        elif command == "health":
            tester.check_executor_health()
        elif command == "full":
            tester.run_full_test_cycle()
        else:
            print(f"未知命令: {command}")
            print_usage()
    else:
        # 默认运行完整测试
        tester.run_full_test_cycle()


def print_usage():
    """打印使用说明"""
    print("\n📖 使用说明:")
    print("  python test_manual_trade.py [command]")
    print("\n📋 可用命令:")
    print("  buy    - 测试买入信号")
    print("  sell   - 测试卖出信号")
    print("  hold   - 测试持有信号")
    print("  health - 检查服务健康状态")
    print("  full   - 运行完整测试周期 (默认)")
    print("\n💡 示例:")
    print("  python test_manual_trade.py buy")
    print("  python test_manual_trade.py full")


if __name__ == "__main__":
    main()
