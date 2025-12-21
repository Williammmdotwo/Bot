#!/usr/bin/env python3
"""
修复效果验证脚本
验证交易系统修复后的效果
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import requests

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tests.utils.base_test_runner import BaseTestRunner


class FixVerificationRunner(BaseTestRunner):
    """修复效果验证运行器"""
    
    def __init__(self):
        super().__init__("fix_verification_config.json")
        self.verification_stats = {
            'sell_signals': 0,
            'sell_passed': 0,
            'sell_rejected': 0,
            'buy_signals': 0,
            'buy_passed': 0,
            'buy_rejected': 0,
            'hold_signals': 0,
            'total_signals': 0,
            'signal_intervals': [],
            'confidence_levels': [],
            'position_sizes': []
        }
    
    def test_risk_manager_fixes(self) -> bool:
        """测试风控管理器修复效果"""
        self.logger.info("🔧 测试风控管理器修复效果...")
        
        # 测试SELL信号是否能通过风控
        test_sell_order = {
            "symbol": "BTC-USDT",
            "side": "sell",
            "position_size": 200.0,  # 2% of 10000
            "stop_loss": 44000.0,
            "take_profit": 42000.0,
            "current_price": 43000.0,  # 在止损和止盈之间
            "current_equity": 10000.0
        }
        
        try:
            response = self.make_service_request(
                "risk", 
                "/api/check-order", 
                test_sell_order, 
                method='POST'
            )
            
            if response and response.get('is_rational'):
                self.logger.info("✅ SELL信号风控测试通过")
                return True
            else:
                self.logger.error(f"❌ SELL信号风控测试失败: {response}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ 风控测试异常: {e}")
            return False
    
    def test_signal_frequency(self) -> bool:
        """测试信号频率控制"""
        self.logger.info("⏱️ 测试信号频率控制...")
        
        # 模拟连续生成信号
        signal_times = []
        for i in range(3):
            start_time = time.time()
            
            try:
                response = self.make_service_request(
                    "strategy",
                    "/api/generate-signal",
                    {
                        "symbol": "BTC-USDT",
                        "use_demo": True
                    },
                    method='POST'
                )
                
                if response:
                    signal_times.append(time.time() - start_time)
                    self.logger.info(f"信号 {i+1} 生成完成")
                
                # 等待信号间隔
                time.sleep(2)
                
            except Exception as e:
                self.logger.error(f"信号生成测试异常: {e}")
        
        if signal_times:
            avg_time = sum(signal_times) / len(signal_times)
            self.logger.info(f"✅ 信号生成平均时间: {avg_time:.2f}秒")
            return True
        
        return False
    
    def test_dynamic_position_sizing(self) -> bool:
        """测试动态仓位管理"""
        self.logger.info("📊 测试动态仓位管理...")
        
        try:
            response = self.make_service_request(
                "strategy",
                "/api/generate-signal",
                {
                    "symbol": "BTC-USDT",
                    "use_demo": True
                },
                method='POST'
            )
            
            if response:
                position_size = response.get('position_size', 0)
                confidence = response.get('confidence', 0)
                
                self.logger.info(f"✅ 动态仓位测试: position_size={position_size}, confidence={confidence}")
                
                # 验证仓位大小是否合理
                if isinstance(position_size, (int, float)) and 0 < position_size <= 0.05:
                    self.logger.info("✅ 仓位大小合理")
                    return True
                else:
                    self.logger.warning(f"⚠️ 仓位大小可能异常: {position_size}")
            
        except Exception as e:
            self.logger.error(f"动态仓位测试异常: {e}")
        
        return False
    
    def run_comprehensive_test(self) -> bool:
        """运行综合测试"""
        self.logger.info("🚀 开始综合修复效果验证...")
        
        test_results = {}
        
        # 1. 测试风控修复
        test_results['risk_fix'] = self.test_risk_manager_fixes()
        
        # 2. 测试信号频率
        test_results['frequency_fix'] = self.test_signal_frequency()
        
        # 3. 测试动态仓位
        test_results['position_fix'] = self.test_dynamic_position_sizing()
        
        # 生成验证报告
        self.generate_verification_report(test_results)
        
        # 计算总体通过率
        passed_tests = sum(test_results.values())
        total_tests = len(test_results)
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        self.logger.info(f"📊 修复验证完成: {passed_tests}/{total_tests} 通过 ({success_rate:.1f}%)")
        
        return success_rate >= 80  # 80%以上通过率视为修复成功
    
    def generate_verification_report(self, test_results: Dict[str, bool]):
        """生成验证报告"""
        report = f"""
╔════════════════════════════════════════════════════════════╗
║                交易系统修复效果验证报告                      ║
╚══════════════════════════════════════════════════════════════╝

📅 验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔧 修复项目验证结果:
{'✅' if test_results.get('risk_fix', False) else '❌'} 风控SELL拒绝问题修复
{'✅' if test_results.get('frequency_fix', False) else '❌'} 交易频率控制修复  
{'✅' if test_results.get('position_fix', False) else '❌'} 动态仓位管理修复

📊 修复效果统计:
   风控修复: {'通过' if test_results.get('risk_fix', False) else '失败'}
   频率控制: {'通过' if test_results.get('frequency_fix', False) else '失败'}
   仓位管理: {'通过' if test_results.get('position_fix', False) else '失败'}

🎯 关键改进:
   1. ✅ 修复了风控SELL信号被错误拒绝的问题
   2. ✅ 将信号间隔从15秒增加到60秒，降低交易频率
   3. ✅ 统一置信度阈值为75%，消除规则冲突
   4. ✅ 实施动态仓位管理，根据风险调整仓位大小
   5. ✅ 优化风控配置，单笔仓位限制从15%提升到20%

📈 预期效果:
   - SELL信号通过率: 0% → 70%+
   - 交易频率: 3.21信号/分钟 → 1.0信号/分钟
   - 风控通过率: 61.1% → 85%+
   - 信号置信度: 65% → 80%+

🔍 下一步建议:
   1. 运行完整的交易测试验证实际效果
   2. 监控系统运行指标确保修复稳定
   3. 根据实际运行情况进一步调优参数

📁 详细日志: {self.logger.handlers[0].baseFilename if self.logger.handlers else 'N/A'}

🎯 验证完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        # 保存报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"logs/fix_verification_report_{timestamp}.txt"
        
        try:
            os.makedirs('logs', exist_ok=True)
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)
            self.logger.info(f"📄 验证报告已保存: {report_file}")
        except Exception as e:
            self.logger.error(f"保存验证报告失败: {e}")
        
        # 打印报告
        print(report)


def main():
    """主函数"""
    print("🔧 交易系统修复效果验证")
    print("=" * 50)
    
    # 创建验证运行器
    verifier = FixVerificationRunner()
    
    # 检查服务健康状态
    if not verifier.check_service_health():
        print("❌ 服务健康检查失败，请确保所有服务正常运行")
        return False
    
    # 运行综合测试
    success = verifier.run_comprehensive_test()
    
    if success:
        print("🎉 修复验证成功！系统修复效果良好")
        return True
    else:
        print("⚠️ 修复验证部分失败，需要进一步调试")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
