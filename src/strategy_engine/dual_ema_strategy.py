"""
双均线突破策略 (Dual EMA Crossover Strategy) - 简化版
使用9周期EMA和21周期EMA的交叉信号生成交易信号
"""

import logging
import time
import uuid
from typing import Dict, Any, List, Optional
from src.data_manager.core.technical_indicators import TechnicalIndicators

logger = logging.getLogger(__name__)

class DualEMAStrategy:
    """双均线突破策略类"""

    def __init__(self, ema_fast: int = 9, ema_slow: int = 21):
        """
        初始化双均线策略

        Args:
            ema_fast: 快线周期，默认9
            ema_slow: 慢线周期，默认21
        """
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.previous_ema_fast = None
        self.previous_ema_slow = None
        self.last_signal = None
        self.last_signal_time = None

        logger.info(f"Dual EMA Strategy initialized: EMA_{ema_fast} / EMA_{ema_slow}")

    def generate_signal(self, historical_data: Dict[str, Any], symbol: str) -> Dict[str, Any]:
        """
        生成交易信号

        Args:
            historical_data: 包含历史数据的字典
            symbol: 交易对符号

        Returns:
            Dict: 交易信号字典
        """
        try:
            # 获取5分钟时间框架的数据
            timeframe_data = historical_data.get("historical_analysis", {}).get("5m", {})

            if not timeframe_data or "ohlcv" not in timeframe_data:
                logger.warning(f"No 5m OHLCV data available for {symbol}")
                return self._create_hold_signal(symbol, "No 5m data available")

            ohlcv_data = timeframe_data["ohlcv"]

            # 检查数据量是否足够
            if len(ohlcv_data) < self.ema_slow + 1:
                # 🔥 加上这句
                logger.info(f"⏳ [LOADING] 数据积累中: 当前 {len(ohlcv_data)} / 需要 {self.ema_slow + 1}")

                logger.warning(f"Insufficient 5m data for {symbol}: {len(ohlcv_data)} candles (need {self.ema_slow + 1})")
                return self._create_hold_signal(symbol, f"Insufficient data: {len(ohlcv_data)} candles")

            # 提取收盘价
            closes = [candle[4] for candle in ohlcv_data]
            current_price = closes[-1]

            # 计算当前EMA值
            current_ema_fast = TechnicalIndicators.calculate_ema(closes, self.ema_fast)
            current_ema_slow = TechnicalIndicators.calculate_ema(closes, self.ema_slow)

            # 计算上一时刻的EMA值（去掉最后一根K线）
            if len(closes) >= self.ema_slow + 1:
                prev_closes = closes[:-1]  # 去掉最后一根K线
                prev_ema_fast = TechnicalIndicators.calculate_ema(prev_closes, self.ema_fast)
                prev_ema_slow = TechnicalIndicators.calculate_ema(prev_closes, self.ema_slow)
            else:
                # 如果数据不够，使用当前值作为前一个值
                prev_ema_fast = current_ema_fast
                prev_ema_slow = current_ema_slow

            logger.info(f"[STRATEGY] {symbol} 5m分析: 当前价格={current_price:.2f} | "
                        f"快线EMA_{self.ema_fast}={current_ema_fast:.2f} | "
                        f"慢线EMA_{self.ema_slow}={current_ema_slow:.2f} | "
                        f"差值={(current_ema_fast - current_ema_slow):.4f}")

            # 检测交叉信号
            signal = self._detect_crossover(
                current_ema_fast, current_ema_slow,
                prev_ema_fast, prev_ema_slow,
                current_price, symbol
            )

            # --- 新增代码：让机器人每分钟都报个平安 ---
            # 哪怕是 HOLD，也打印出来，但为了不刷屏，可以只打印关键信息
            if signal['signal'] == 'HOLD':
                # 使用 INFO 级别，这样肯定能被记录下来
                # 打印当前的 EMA 值，让你知道离交叉还有多远
                logger.info(f"[HEARTBEAT] {symbol} 正在监控 | 价格: {current_price:.2f} | "
                            f"快线: {current_ema_fast:.2f} | 慢线: {current_ema_slow:.2f} | "
                            f"状态: 等待交叉")
            else:
                # 如果是交易信号，加倍醒目
                logger.info(f"🚀 [SIGNAL] 触发交易！{signal['signal']} @ {current_price}")
            # ----------------------------------------

            # 更新历史状态
            self.previous_ema_fast = current_ema_fast
            self.previous_ema_slow = current_ema_slow

            return signal

        except Exception as e:
            logger.error(f"Error generating signal for {symbol}: {e}")
            return self._create_hold_signal(symbol, f"Strategy error: {str(e)}")

    def _detect_crossover(self, current_fast: float, current_slow: float,
                         prev_fast: float, prev_slow: float,
                         current_price: float, symbol: str) -> Dict[str, Any]:
        """
        检测EMA交叉信号

        Args:
            current_fast: 当前快线EMA值
            current_slow: 当前慢线EMA值
            prev_fast: 前一时刻快线EMA值
            prev_slow: 前一时刻慢线EMA值
            current_price: 当前价格
            symbol: 交易对符号

        Returns:
            Dict: 交易信号
        """
        decision_id = str(uuid.uuid4())
        current_time = int(time.time())

        # 金叉：快线从下往上穿过慢线
        if (current_fast > current_slow and
            prev_fast <= prev_slow and
            self.last_signal != "BUY"):

            logger.info(f"🟢 GOLDEN CROSS detected for {symbol}: EMA_{self.ema_fast} ({current_fast:.2f}) > EMA_{self.ema_slow} ({current_slow:.2f})")

            self.last_signal = "BUY"
            self.last_signal_time = current_time

            return {
                "signal": "BUY",
                "symbol": symbol,
                "decision_id": decision_id,
                "confidence": 75.0,
                "reasoning": f"Golden Cross: EMA_{self.ema_fast} crosses above EMA_{self.ema_slow}",
                "position_size": 0.02,
                "stop_loss": current_price * 0.98,  # 2%止损
                "take_profit": current_price * 1.04,  # 4%止盈
                "timestamp": current_time,
                "ema_fast": current_fast,
                "ema_slow": current_slow,
                "current_price": current_price
            }

        # 死叉：快线从上往下穿过慢线
        elif (current_fast < current_slow and
              prev_fast >= prev_slow and
              self.last_signal != "SELL"):

            logger.info(f"🔴 DEATH CROSS detected for {symbol}: EMA_{self.ema_fast} ({current_fast:.2f}) < EMA_{self.ema_slow} ({current_slow:.2f})")

            self.last_signal = "SELL"
            self.last_signal_time = current_time

            return {
                "signal": "SELL",
                "symbol": symbol,
                "decision_id": decision_id,
                "confidence": 75.0,
                "reasoning": f"Death Cross: EMA_{self.ema_fast} crosses below EMA_{self.ema_slow}",
                "position_size": 0.02,
                "stop_loss": current_price * 1.02,  # 2%止损
                "take_profit": current_price * 0.96,  # 4%止盈
                "timestamp": current_time,
                "ema_fast": current_fast,
                "ema_slow": current_slow,
                "current_price": current_price
            }

        # 无信号
        else:
            return self._create_hold_signal(
                symbol,
                f"No crossover: EMA_{self.ema_fast}={current_fast:.2f}, EMA_{self.ema_slow}={current_slow:.2f}",
                current_price,
                current_fast,
                current_slow
            )

    def _create_hold_signal(self, symbol: str, reason: str, current_price: float = 0,
                           ema_fast: float = 0, ema_slow: float = 0) -> Dict[str, Any]:
        """
        创建持有信号

        Args:
            symbol: 交易对符号
            reason: 持有原因
            current_price: 当前价格
            ema_fast: 快线EMA值
            ema_slow: 慢线EMA值

        Returns:
            Dict: 持有信号
        """
        return {
            "signal": "HOLD",
            "symbol": symbol,
            "decision_id": str(uuid.uuid4()),
            "confidence": 50.0,
            "reasoning": reason,
            "position_size": 0.0,
            "stop_loss": 0,
            "take_profit": 0,
            "timestamp": int(time.time()),
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "current_price": current_price
        }

    def reset_state(self):
        """重置策略状态"""
        self.previous_ema_fast = None
        self.previous_ema_slow = None
        self.last_signal = None
        self.last_signal_time = None
        logger.info("Dual EMA Strategy state reset")

# 全局策略实例
_dual_ema_strategy = None

def get_dual_ema_strategy() -> DualEMAStrategy:
    """获取双均线策略实例（单例模式）"""
    global _dual_ema_strategy
    if _dual_ema_strategy is None:
        _dual_ema_strategy = DualEMAStrategy()
    return _dual_ema_strategy

def generate_dual_ema_signal(historical_data: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    """
    生成双均线交易信号的便捷函数

    Args:
        historical_data: 历史数据
        symbol: 交易对符号

    Returns:
        Dict: 交易信号
    """
    strategy = get_dual_ema_strategy()
    return strategy.generate_signal(historical_data, symbol)
