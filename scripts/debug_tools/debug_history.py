#!/usr/bin/env python3
"""
双均线策略历史信号诊断脚本
用于验证过去17小时内是否漏掉了交易信号

作者: Athena Trader Team
日期: 2025-12-19
功能: 连接OKX Demo获取历史数据，重演双均线策略，检测信号
"""

import sys
import os
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import colorama
from colorama import Fore, Back, Style

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.data_manager.rest_client import RESTClient
from src.data_manager.technical_indicators import TechnicalIndicators
from src.strategy_engine.dual_ema_strategy import DualEMAStrategy

# 初始化colorama用于彩色输出
colorama.init()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('debug_history.log', mode='w', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class HistorySignalDebugger:
    """历史信号调试器"""
    
    def __init__(self, symbol: str = "BTC-USDT", use_demo: bool = True):
        """
        初始化调试器
        
        Args:
            symbol: 交易对符号
            use_demo: 是否使用Demo环境
        """
        self.symbol = symbol
        self.use_demo = use_demo
        self.ema_fast = 9
        self.ema_slow = 21
        
        # 初始化组件
        try:
            self.rest_client = RESTClient(use_demo=use_demo)
            self.strategy = DualEMAStrategy(self.ema_fast, self.ema_slow)
            logger.info(f"调试器初始化完成 - 交易对: {symbol}, Demo模式: {use_demo}")
        except Exception as e:
            logger.error(f"调试器初始化失败: {e}")
            raise
    
    def fetch_historical_data(self, limit: int = 100) -> List[List]:
        """
        获取历史K线数据
        
        Args:
            limit: 获取K线数量
            
        Returns:
            List: K线数据列表
        """
        try:
            logger.info(f"开始获取 {self.symbol} 的历史K线数据，数量: {limit}")
            
            # 计算100根15分钟K线覆盖的时间范围（约25小时）
            timeframe_minutes = 15
            since_ms = int((time.time() - timeframe_minutes * limit * 60) * 1000)
            
            # 获取15分钟K线数据
            ohlcv_data = self.rest_client.fetch_ohlcv(
                self.symbol, 
                since_ms, 
                limit, 
                "15m"
            )
            
            if not ohlcv_data:
                logger.error("未获取到历史数据")
                return []
            
            logger.info(f"成功获取 {len(ohlcv_data)} 根K线数据")
            logger.info(f"数据时间范围: {self._format_timestamp(ohlcv_data[0][0])} 到 {self._format_timestamp(ohlcv_data[-1][0])}")
            
            return ohlcv_data
            
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}")
            return []
    
    def replay_strategy(self, ohlcv_data: List[List]) -> Dict[str, Any]:
        """
        重演双均线策略
        
        Args:
            ohlcv_data: 历史K线数据
            
        Returns:
            Dict: 重演结果和信号统计
        """
        if not ohlcv_data:
            logger.error("没有历史数据可用于重演")
            return {"signals": [], "statistics": {}}
        
        logger.info("开始重演双均线策略...")
        logger.info(f"使用参数: EMA{self.ema_fast} / EMA{self.ema_slow}")
        
        signals = []
        ema_fast_values = []
        ema_slow_values = []
        previous_ema_fast = None
        previous_ema_slow = None
        last_signal = None
        
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"{Fore.CYAN}双均线策略历史重演报告 - {self.symbol}")
        print(f"{Fore.CYAN}数据时间范围: {self._format_timestamp(ohlcv_data[0][0])} 到 {self._format_timestamp(ohlcv_data[-1][0])}")
        print(f"{Fore.CYAN}K线数量: {len(ohlcv_data)} 根 (15分钟)")
        print(f"{Fore.CYAN}策略参数: EMA{self.ema_fast} / EMA{self.ema_slow}")
        print(f"{'='*80}{Style.RESET_ALL}\n")
        
        # 表头
        print(f"{Fore.YELLOW}{'时间':<20} {'价格':<12} {'EMA9':<12} {'EMA21':<12} {'信号':<15} {'说明'}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}{'-'*20} {'-'*12} {'-'*12} {'-'*12} {'-'*15} {'-'*30}{Style.RESET_ALL}")
        
        # 逐根K线重演策略
        for i, candle in enumerate(ohlcv_data):
            try:
                timestamp, open_price, high_price, low_price, close_price, volume = candle
                current_price = close_price
                
                # 计算当前EMA值
                if i >= self.ema_slow - 1:
                    # 获取到目前为止的所有收盘价
                    closes = [c[4] for c in ohlcv_data[:i+1]]
                    
                    current_ema_fast = TechnicalIndicators.calculate_ema(closes, self.ema_fast)
                    current_ema_slow = TechnicalIndicators.calculate_ema(closes, self.ema_slow)
                    
                    ema_fast_values.append(current_ema_fast)
                    ema_slow_values.append(current_ema_slow)
                    
                    # 计算前一时刻EMA值
                    if i >= self.ema_slow:
                        prev_closes = [c[4] for c in ohlcv_data[:i]]
                        prev_ema_fast = TechnicalIndicators.calculate_ema(prev_closes, self.ema_fast)
                        prev_ema_slow = TechnicalIndicators.calculate_ema(prev_closes, self.ema_slow)
                    else:
                        prev_ema_fast = current_ema_fast
                        prev_ema_slow = current_ema_slow
                    
                    # 检测交叉信号
                    signal_type, signal_reason = self._detect_crossover_signal(
                        current_ema_fast, current_ema_slow,
                        prev_ema_fast, prev_ema_slow,
                        last_signal
                    )
                    
                    # 格式化输出
                    time_str = self._format_timestamp(timestamp)
                    price_str = f"{current_price:.2f}"
                    ema9_str = f"{current_ema_fast:.2f}"
                    ema21_str = f"{current_ema_slow:.2f}"
                    
                    if signal_type == "BUY":
                        signal_display = f"{Fore.GREEN}🟢 BUY{Style.RESET_ALL}"
                        last_signal = "BUY"
                        signals.append({
                            "time": timestamp,
                            "time_str": time_str,
                            "type": "BUY",
                            "price": current_price,
                            "ema9": current_ema_fast,
                            "ema21": current_ema_slow,
                            "reason": signal_reason,
                            "candle_index": i
                        })
                    elif signal_type == "SELL":
                        signal_display = f"{Fore.RED}🔴 SELL{Style.RESET_ALL}"
                        last_signal = "SELL"
                        signals.append({
                            "time": timestamp,
                            "time_str": time_str,
                            "type": "SELL",
                            "price": current_price,
                            "ema9": current_ema_fast,
                            "ema21": current_ema_slow,
                            "reason": signal_reason,
                            "candle_index": i
                        })
                    else:
                        signal_display = f"{Fore.WHITE}HOLD{Style.RESET_ALL}"
                    
                    # 特殊标记凌晨1点左右的数据
                    time_obj = datetime.fromtimestamp(timestamp / 1000)
                    if 0 <= time_obj.hour <= 2:
                        time_str = f"{Fore.MAGENTA}{time_str}{Style.RESET_ALL}"
                    
                    print(f"{time_str:<20} {price_str:<12} {ema9_str:<12} {ema21_str:<12} {signal_display:<15} {signal_reason}")
                    
                    previous_ema_fast = current_ema_fast
                    previous_ema_slow = current_ema_slow
                    
                else:
                    # 数据不足，显示等待状态
                    time_str = self._format_timestamp(timestamp)
                    price_str = f"{current_price:.2f}"
                    print(f"{time_str:<20} {price_str:<12} {'--':<12} {'--':<12} {Fore.YELLOW}WAIT{Style.RESET_ALL:<15} 数据积累中...")
                
            except Exception as e:
                logger.error(f"处理第{i}根K线时出错: {e}")
                continue
        
        # 统计信息
        statistics = {
            "total_candles": len(ohlcv_data),
            "signals_found": len(signals),
            "buy_signals": len([s for s in signals if s["type"] == "BUY"]),
            "sell_signals": len([s for s in signals if s["type"] == "SELL"]),
            "data_start": self._format_timestamp(ohlcv_data[0][0]),
            "data_end": self._format_timestamp(ohlcv_data[-1][0]),
            "ema_fast_values": ema_fast_values,
            "ema_slow_values": ema_slow_values
        }
        
        return {
            "signals": signals,
            "statistics": statistics
        }
    
    def _detect_crossover_signal(self, current_fast: float, current_slow: float,
                                prev_fast: float, prev_slow: float,
                                last_signal: Optional[str]) -> tuple:
        """
        检测EMA交叉信号
        
        Args:
            current_fast: 当前快线EMA值
            current_slow: 当前慢线EMA值
            prev_fast: 前一时刻快线EMA值
            prev_slow: 前一时刻慢线EMA值
            last_signal: 上一个信号类型
            
        Returns:
            tuple: (信号类型, 信号说明)
        """
        # 金叉：快线从下往上穿过慢线
        if (current_fast > current_slow and 
            prev_fast <= prev_slow and 
            last_signal != "BUY"):
            return "BUY", f"金叉: EMA{self.ema_fast}({current_fast:.2f}) > EMA{self.ema_slow}({current_slow:.2f})"
        
        # 死叉：快线从上往下穿过慢线
        elif (current_fast < current_slow and 
              prev_fast >= prev_slow and 
              last_signal != "SELL"):
            return "SELL", f"死叉: EMA{self.ema_fast}({current_fast:.2f}) < EMA{self.ema_slow}({current_slow:.2f})"
        
        # 无信号
        else:
            return "HOLD", f"无交叉: EMA{self.ema_fast}={current_fast:.2f}, EMA{self.ema_slow}={current_slow:.2f}"
    
    def _format_timestamp(self, timestamp: int) -> str:
        """
        格式化时间戳
        
        Args:
            timestamp: 毫秒时间戳
            
        Returns:
            str: 格式化的时间字符串
        """
        try:
            dt = datetime.fromtimestamp(timestamp / 1000)
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception as e:
            return f"Invalid timestamp: {timestamp}"
    
    def generate_report(self, replay_result: Dict[str, Any]) -> None:
        """
        生成详细报告
        
        Args:
            replay_result: 重演结果
        """
        signals = replay_result["signals"]
        stats = replay_result["statistics"]
        
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"{Fore.CYAN}信号检测统计报告")
        print(f"{'='*80}{Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}📊 基本统计:{Style.RESET_ALL}")
        print(f"  总K线数: {stats['total_candles']} 根")
        print(f"  发现信号: {stats['signals_found']} 个")
        print(f"  买入信号: {Fore.GREEN}{stats['buy_signals']}{Style.RESET_ALL} 个")
        print(f"  卖出信号: {Fore.RED}{stats['sell_signals']}{Style.RESET_ALL} 个")
        print(f"  数据范围: {stats['data_start']} 到 {stats['data_end']}")
        
        if signals:
            print(f"\n{Fore.YELLOW}🎯 信号详情:{Style.RESET_ALL}")
            for i, signal in enumerate(signals, 1):
                signal_color = Fore.GREEN if signal["type"] == "BUY" else Fore.RED
                signal_icon = "🟢" if signal["type"] == "BUY" else "🔴"
                print(f"\n  {signal_color}信号 {i}: {signal['type']} {signal_icon}{Style.RESET_ALL}")
                print(f"    时间: {signal['time_str']}")
                print(f"    价格: ${signal['price']:.2f}")
                print(f"    EMA9: {signal['ema9']:.2f}")
                print(f"    EMA21: {signal['ema21']:.2f}")
                print(f"    说明: {signal['reason']}")
                print(f"    K线索引: {signal['candle_index']}")
                
                # 检查是否在凌晨1点左右
                signal_time = datetime.fromtimestamp(signal['time'] / 1000)
                if 0 <= signal_time.hour <= 2:
                    print(f"    {Fore.MAGENTA}⚠️  这是凌晨时段的信号！{Style.RESET_ALL}")
        
        else:
            print(f"\n{Fore.YELLOW}📋 信号分析:{Style.RESET_ALL}")
            print("  在检测的时间范围内没有发现任何买卖信号。")
            print("  这可能意味着：")
            print("    1. 市场处于盘整状态，没有明显的趋势")
            print("    2. EMA线没有发生交叉")
            print("    3. 策略参数可能需要调整")
        
        print(f"\n{Fore.YELLOW}🔍 关键时间段检查 (凌晨0-2点):{Style.RESET_ALL}")
        early_morning_signals = [s for s in signals 
                               if 0 <= datetime.fromtimestamp(s['time'] / 1000).hour <= 2]
        
        if early_morning_signals:
            print(f"  {Fore.RED}发现 {len(early_morning_signals)} 个凌晨时段的信号！{Style.RESET_ALL}")
            for signal in early_morning_signals:
                print(f"    {signal['time_str']} - {signal['type']} - {signal['reason']}")
        else:
            print(f"  {Fore.GREEN}凌晨0-2点没有发现信号{Style.RESET_ALL}")
        
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"{Fore.CYAN}报告完成 - 详细日志已保存到 debug_history.log")
        print(f"{'='*80}{Style.RESET_ALL}\n")
    
    def run_debug(self) -> None:
        """
        运行完整的调试流程
        """
        try:
            print(f"{Fore.CYAN}🚀 启动双均线策略历史信号调试器{Style.RESET_ALL}")
            print(f"{Fore.CYAN}交易对: {self.symbol}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Demo模式: {self.use_demo}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}时间范围: 最近约25小时 (100根15分钟K线){Style.RESET_ALL}")
            print(f"{Fore.CYAN}策略参数: EMA{self.ema_fast} / EMA{self.ema_slow}{Style.RESET_ALL}\n")
            
            # 1. 获取历史数据
            ohlcv_data = self.fetch_historical_data(limit=100)
            
            if not ohlcv_data:
                print(f"{Fore.RED}❌ 无法获取历史数据，调试终止{Style.RESET_ALL}")
                return
            
            # 2. 重演策略
            replay_result = self.replay_strategy(ohlcv_data)
            
            # 3. 生成报告
            self.generate_report(replay_result)
            
            # 4. 日志记录
            logger.info("双均线策略历史调试完成")
            logger.info(f"统计信息: {replay_result['statistics']}")
            if replay_result['signals']:
                logger.info(f"发现的信号: {replay_result['signals']}")
            
        except Exception as e:
            logger.error(f"调试过程中发生错误: {e}")
            print(f"{Fore.RED}❌ 调试失败: {e}{Style.RESET_ALL}")

def main():
    """主函数"""
    try:
        # 创建调试器实例
        debugger = HistorySignalDebugger(
            symbol="BTC-USDT",
            use_demo=True
        )
        
        # 运行调试
        debugger.run_debug()
        
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⚠️  用户中断调试过程{Style.RESET_ALL}")
        logger.info("调试被用户中断")
    except Exception as e:
        print(f"{Fore.RED}❌ 程序异常退出: {e}{Style.RESET_ALL}")
        logger.error(f"程序异常退出: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
