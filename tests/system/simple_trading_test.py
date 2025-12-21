#!/usr/bin/env python3
"""
简化的交易测试脚本
基于BaseTestRunner，专注于核心交易流程测试
支持三层标签系统：模拟数据、OKX模拟交易、OKX真实交易
"""

import logging
import sys
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.utils.base_test_runner import BaseTestRunner
from src.utils.environment_utils import get_data_source_label, get_data_source_config


class SimpleTradingTest(BaseTestRunner):
    """简化的交易测试类"""
    
    def __init__(self):
        super().__init__()
        
        # 交易特定统计
        self.stats.update({
            'total_signals': 0,
            'buy_signals': 0,
            'sell_signals': 0,
            'hold_signals': 0,
            'valid_trading_signals': 0,
            'risk_approved_trades': 0,
            'executed_trades': 0,
            'signals': []
        })
        
        # 测试配置
        self.test_duration = timedelta(minutes=self.config['trading']['test_duration_minutes'])
        self.signal_interval = self.config['trading']['signal_interval_seconds']
        self.progress_interval = self.config['trading']['progress_interval_seconds']
        
        self.logger.info(f"[{self._get_data_source()}] 🚀 简化交易测试初始化完成")
    
    def _get_data_source(self) -> str:
        """获取数据来源标识"""
        return get_data_source_label()
    
    def get_current_price(self, symbol: str = "BTC-USDT") -> float:
        """获取当前市场价格"""
        try:
            # 直接使用数据管理器而不是通过API调用
            from src.data_manager.main import DataHandler
            data_handler = DataHandler()
            
            # 获取综合市场数据
            market_data = data_handler.get_comprehensive_market_data(symbol, use_demo=True)
            
            if market_data and market_data.get('data_status') != 'ERROR':
                current_price = market_data.get('current_price')
                
                if current_price and current_price > 0:
                    self.logger.info(f"成功获取{symbol}价格: {current_price}")
                    return float(current_price)
                else:
                    # 如果没有current_price字段，尝试从ticker获取
                    ticker = market_data.get('ticker', {})
                    if ticker:
                        last_price = ticker.get('last')
                        if last_price and last_price > 0:
                            self.logger.info(f"从ticker获取{symbol}价格: {last_price}")
                            return float(last_price)
                    
                    self.logger.warning(f"无法从市场数据中获取{symbol}价格")
                    return None
            else:
                self.logger.warning(f"无法获取{symbol}市场数据，状态: {market_data.get('data_status', 'UNKNOWN')}")
                return None
                
        except Exception as e:
            self.logger.error(f"获取{symbol}价格异常: {str(e)}")
            return None
    
    def generate_trading_signal(self, symbol: str = "BTC-USDT") -> Dict[str, Any]:
        """生成交易信号"""
        try:
            # 使用新的数据源配置
            data_source_config = get_data_source_config()
            data = {
                'symbol': symbol,
                'use_demo': data_source_config['use_demo']
            }
            
            response = self.make_service_request('strategy', '/api/generate-signal', data, 'POST')
            
            if response and 'signal' in response:
                signal = response.get('signal', 'HOLD')
                confidence = response.get('confidence', 0.0)
                decision_id = response.get('decision_id', '')
                reasoning = response.get('reasoning', '')
                
                # 更新统计
                self.stats['total_signals'] += 1
                if signal == 'BUY':
                    self.stats['buy_signals'] += 1
                elif signal == 'SELL':
                    self.stats['sell_signals'] += 1
                else:
                    self.stats['hold_signals'] += 1
                
                # 记录信号详情
                signal_record = {
                    'timestamp': datetime.now(),
                    'symbol': symbol,
                    'signal': signal,
                    'confidence': confidence,
                    'decision_id': decision_id,
                    'reasoning': reasoning[:100] + '...' if reasoning else ''
                }
                self.stats['signals'].append(signal_record)
                
                # 判断是否为有效交易信号
                if signal in ['BUY', 'SELL'] and confidence > 0:
                    self.stats['valid_trading_signals'] += 1
                    self.logger.info(f"[{self._get_data_source()}] 🎯 交易信号: {signal} (置信度: {confidence:.2f})")
                else:
                    self.logger.info(f"[{self._get_data_source()}] 🤚 持有信号: {signal} (置信度: {confidence:.2f})")
                
                return response
            else:
                self.update_stats(False, f"策略引擎响应失败: {response}")
                return None
                
        except Exception as e:
            self.update_stats(False, f"生成交易信号异常: {str(e)}")
            return None
    
    def validate_risk(self, signal_data: Dict[str, Any]) -> bool:
        """风险验证"""
        try:
            # 提取信号信息
            signal = signal_data.get('signal', 'HOLD')
            confidence = signal_data.get('confidence', 0.0)
            symbol = signal_data.get('symbol', 'BTC-USDT')
            
            # 获取当前市场价格
            current_price = self.get_current_price(symbol)
            if current_price is None:
                # 如果无法获取当前价格，使用默认值
                current_price = 90000.0  # 默认BTC价格
                self.logger.warning(f"无法获取{symbol}当前价格，使用默认值: {current_price}")
            
            # 根据当前价格动态计算止损止盈价格
            stop_loss_pct = self.config['trading']['stop_loss_pct']  # 0.04 = 4%
            take_profit_pct = self.config['trading']['take_profit_pct']  # 0.08 = 8%
            
            if signal.lower() == 'buy':
                # 买单：止损在当前价格下方，止盈在上方
                stop_loss = current_price * (1 - stop_loss_pct)
                take_profit = current_price * (1 + take_profit_pct)
            else:  # sell
                # 卖单：止损在当前价格上方，止盈在下方
                stop_loss = current_price * (1 + stop_loss_pct)
                take_profit = current_price * (1 - take_profit_pct)
            
            # 构建符合OrderCheckRequest格式的数据
            data = {
                'symbol': symbol,
                'side': signal.lower(),  # buy/sell
                'position_size': 100.0,  # 模拟仓位大小(USDT)
                'stop_loss': round(stop_loss, 2),  # 动态计算的止损价格
                'take_profit': round(take_profit, 2),  # 动态计算的止盈价格
                'current_price': current_price,  # 当前市价（必需字段）
                'current_equity': 10000.0  # 模拟账户权益
            }
            
            self.logger.info(f"动态计算{signal}订单参数: 当前价格={current_price}, 止损={stop_loss:.2f}, 止盈={take_profit:.2f}")
            
            response = self.make_service_request('risk', '/api/check-order', data, 'POST')
            
            if response:
                is_rational = response.get('is_rational', False)
                if is_rational:
                    self.stats['risk_approved_trades'] += 1
                    self.logger.info(f"[{self._get_data_source()}] ✅ 风险验证通过")
                else:
                    self.logger.info(f"[{self._get_data_source()}] 🛡️ 风险验证拒绝: {response.get('reason', '未知原因')}")
                return is_rational
            else:
                self.update_stats(False, "风险验证服务无响应")
                return False
                
        except Exception as e:
            self.update_stats(False, f"风险验证异常: {str(e)}")
            return False
    
    def execute_trade(self, signal_data: Dict[str, Any]) -> bool:
        """执行交易"""
        try:
            # 使用新的数据源配置
            data_source_config = get_data_source_config()
            data = {
                'signal': signal_data,
                'use_demo': data_source_config['use_demo'],
                'stop_loss_pct': self.config['trading']['stop_loss_pct'],
                'take_profit_pct': self.config['trading']['take_profit_pct']
            }
            
            response = self.make_service_request('executor', '/api/execute-trade', data, 'POST')
            
            if response:
                status = response.get('status', 'unknown')
                if status in ['executed', 'simulated']:
                    self.stats['executed_trades'] += 1
                    self.logger.info(f"[{self._get_data_source()}] 💼 交易执行成功: {status}")
                    return True
                else:
                    self.logger.info(f"[{self._get_data_source()}] ⏳ 交易执行状态: {status}")
                    return False
            else:
                self.update_stats(False, "交易执行服务无响应")
                return False
                
        except Exception as e:
            self.update_stats(False, f"交易执行异常: {str(e)}")
            return False
    
    def test_data_quality(self, symbol: str = "BTC-USDT") -> bool:
        """测试数据质量"""
        try:
            # 直接使用数据管理器测试数据质量
            from src.data_manager.main import DataHandler
            data_handler = DataHandler()
            
            # 获取综合市场数据
            market_data = data_handler.get_comprehensive_market_data(symbol, use_demo=True)
            
            if market_data and market_data.get('data_status') != 'ERROR':
                data_status = market_data.get('data_status', 'UNKNOWN')
                technical_analysis = market_data.get('technical_analysis', {})
                
                available_timeframes = list(technical_analysis.keys())
                if not available_timeframes:
                    self.update_stats(False, f"无技术指标数据: {symbol}")
                    return False
                
                self.logger.info(f"[{self._get_data_source()}] 📊 数据质量检查通过: {symbol} (状态: {data_status}, 时间框架: {available_timeframes})")
                return True
            else:
                self.update_stats(False, f"数据状态错误: {symbol}")
                return False
                
        except Exception as e:
            self.update_stats(False, f"数据质量检查异常: {str(e)}")
            return False
    
    def run_trading_test(self) -> bool:
        """运行交易测试"""
        self.logger.info(f"[{self._get_data_source()}] 🚀 开始简化交易测试")
        self.logger.info(f"[{self._get_data_source()}] 测试时长: {self.test_duration}")
        self.logger.info(f"[{self._get_data_source()}] 信号间隔: {self.signal_interval}秒")
        
        # 检查服务健康状态
        if not self.check_service_health():
            self.logger.error("服务健康检查失败，无法开始测试")
            return False
        
        # 测试数据质量
        self.logger.info(f"[{self._get_data_source()}] 📊 测试数据质量...")
        data_quality_ok = self.test_data_quality()
        if not data_quality_ok:
            self.logger.warning("数据质量测试失败，但继续执行交易测试")
        
        self.logger.info(f"[{self._get_data_source()}] ✅ 开始交易测试循环")
        
        last_progress_time = time.time()
        last_signal_time = time.time()
        
        try:
            while self.should_continue(self.test_duration):
                current_time = time.time()
                
                # 生成交易信号
                if current_time - last_signal_time >= self.signal_interval:
                    signal_data = self.generate_trading_signal()
                    
                    if signal_data and signal_data.get('signal') in ['BUY', 'SELL']:
                        # 风险验证
                        if self.validate_risk(signal_data):
                            # 执行交易
                            self.execute_trade(signal_data)
                    
                    last_signal_time = current_time
                
                # 打印进度
                if current_time - last_progress_time >= self.progress_interval:
                    self.print_trading_progress()
                    last_progress_time = current_time
                
                # 短暂休眠
                time.sleep(1)
            
            # 生成最终报告
            self.generate_trading_report()
            
            self.logger.info(f"[{self._get_data_source()}] 🎉 简化交易测试完成")
            return True
            
        except Exception as e:
            self.logger.error(f"交易测试过程中发生错误: {e}")
            return False
    
    def print_trading_progress(self):
        """打印交易测试进度"""
        custom_info = {
            "交易信号": f"{self.stats['total_signals']} (买入: {self.stats['buy_signals']}, 卖出: {self.stats['sell_signals']}, 持有: {self.stats['hold_signals']})",
            "有效交易信号": self.stats['valid_trading_signals'],
            "风险通过": self.stats['risk_approved_trades'],
            "执行交易": self.stats['executed_trades']
        }
        
        self.print_progress(custom_info)
    
    def generate_trading_report(self):
        """生成交易测试报告"""
        report = self.generate_basic_report("简化交易测试报告")
        
        # 添加交易特定统计
        elapsed = self.get_test_duration()
        
        trading_stats = f"""
🎯 交易统计:
   📊 总信号数: {self.stats['total_signals']}
   📈 买入信号: {self.stats['buy_signals']}
   📉 卖出信号: {self.stats['sell_signals']}
   🤚 持有信号: {self.stats['hold_signals']}
   ✅ 有效交易信号: {self.stats['valid_trading_signals']}
   🛡️ 风险通过: {self.stats['risk_approved_trades']}
   💼 执行交易: {self.stats['executed_trades']}

📈 信号分析:
"""
        
        if self.stats['total_signals'] > 0:
            trading_signal_rate = (self.stats['valid_trading_signals'] / self.stats['total_signals']) * 100
            risk_approval_rate = (self.stats['risk_approved_trades'] / max(self.stats['valid_trading_signals'], 1)) * 100
            execution_rate = (self.stats['executed_trades'] / max(self.stats['risk_approved_trades'], 1)) * 100
            
            trading_stats += f"   📊 交易信号率: {trading_signal_rate:.1f}%\n"
            trading_stats += f"   🛡️ 风险通过率: {risk_approval_rate:.1f}%\n"
            trading_stats += f"   💼 交易执行率: {execution_rate:.1f}%\n"
            
            # 信号频率
            signal_frequency = self.stats['total_signals'] / elapsed.total_seconds() * 60  # 每分钟
            trading_stats += f"   ⏱️ 信号频率: {signal_frequency:.2f} 信号/分钟\n"
        
        # 添加最近信号
        if self.stats['signals']:
            trading_stats += "\n📋 最近5个信号:\n"
            for i, signal in enumerate(self.stats['signals'][-5:], 1):
                trading_stats += f"   {i}. {signal['timestamp'].strftime('%H:%M:%S')} - {signal['signal']} (置信度: {signal['confidence']:.2f})\n"
        
        # 插入到报告中
        report = report.replace("❌ 错误数量:", trading_stats + "\n❌ 错误数量:")
        
        print(report)
        self.save_report(report, "trading")
        
        # 评估测试结果
        self.evaluate_test_results()
    
    def evaluate_test_results(self):
        """评估测试结果"""
        self.logger.info("🎯 测试结果评估:")
        
        #评估系统稳定性
        total_requests = self.stats['successful_requests'] + self.stats['failed_requests']
        if total_requests > 0:
            success_rate = (self.stats['successful_requests'] / total_requests) * 100
            if success_rate > 95:
                self.logger.info("✅ 系统稳定性优秀 - 成功率超过95%")
            elif success_rate > 85:
                self.logger.info("✅ 系统稳定性良好 - 成功率超过85%")
            else:
                self.logger.warning("⚠️ 系统稳定性需要改进 - 成功率低于85%")
        
        # 评估信号生成
        if self.stats['total_signals'] > 0:
            trading_signal_rate = (self.stats['valid_trading_signals'] / self.stats['total_signals']) * 100
            if trading_signal_rate > 20:
                self.logger.info("✅ 信号生成活跃 - 交易信号率超过20%")
            elif trading_signal_rate > 10:
                self.logger.info("✅ 信号生成正常 - 交易信号率超过10%")
            else:
                self.logger.info("ℹ️ 信号生成保守 - 交易信号率低于10%")
        
        # 评估风险控制
        if self.stats['valid_trading_signals'] > 0:
            risk_approval_rate = (self.stats['risk_approved_trades'] / self.stats['valid_trading_signals']) * 100
            if risk_approval_rate > 80:
                self.logger.info("✅ 风险控制合理 - 通过率超过80%")
            elif risk_approval_rate > 50:
                self.logger.info("✅ 风险控制严格 - 通过率超过50%")
            else:
                self.logger.warning("⚠️ 风险控制过于严格 - 通过率低于50%")


def main():
    """主函数"""
    print("╔══════════════════════════════════════════════════════════╗")
    print("║              Athena Trader 简化交易测试                   ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    
    test = SimpleTradingTest()
    
    try:
        success = test.run_trading_test()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        test.stop_event = True
        test.generate_trading_report()
        print("\n测试被用户中断")
    except Exception as e:
        logging.error(f"测试启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
