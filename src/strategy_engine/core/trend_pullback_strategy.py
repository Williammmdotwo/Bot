"""
趋势回调策略 (Trend Pullback Strategy)

策略规则：
1. 大趋势判断（过滤器）：
   - 计算 EMA 144（144周期指数移动平均线）
   - 如果 当前价格 > EMA 144，判定为牛市，只做多
   - 如果 当前价格 < EMA 144，判定为熊市，只做空（可配置）

2. 入场信号（扳机）：
   - 在牛市背景下，等待回调
   - 计算 RSI (14)
   - 如果 RSI < 30（超卖），说明回调到位，买入（BUY）

3. 出场信号（止盈/止损）：
   - 止盈：当 RSI > 70（超买），或者价格触碰布林带上轨，卖出（SELL）
   - 止损：价格跌破买入价的 -3%，或者跌破 EMA 144，止损离场

4. "不死鸟"仓位管理（Fixed Risk Model）：
   - 每单最多只亏本金的 2%（Fixed Risk per Trade）
   - 杠杆率保持在 2x-3x，绝不超过 5x
   - 基于止损距离计算精确的仓位大小
   - 确保即使连续亏损也能继续交易
"""

import logging
from typing import Dict, Any, Optional, List
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    logger.warning("pandas-ta not available, using fallback calculations")


class TrendPullbackStrategy:
    """趋势回调策略实现"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化策略

        Args:
            config: 策略配置字典
        """
        self.config = config
        self.ema_period = config.get('ema_period', 144)
        self.rsi_period = config.get('rsi_period', 14)
        self.rsi_oversold = config.get('rsi_oversold', 30)
        self.rsi_overbought = config.get('rsi_overbought', 70)
        self.stop_loss_pct = config.get('stop_loss_pct', 0.03)
        self.take_profit_pct = config.get('take_profit_pct', 0.06)
        self.use_bollinger_exit = config.get('use_bollinger_exit', True)
        self.bollinger_period = config.get('bollinger_period', 20)
        self.bollinger_std_dev = config.get('bollinger_std_dev', 2)
        self.only_long = config.get('only_long', True)
        self.max_leverage = config.get('max_leverage', 3.0)
        self.min_leverage = config.get('min_leverage', 2.0)

        logger.info(f"TrendPullbackStrategy initialized: EMA={self.ema_period}, "
                   f"RSI=[{self.rsi_oversold}, {self.rsi_overbought}], "
                   f"Only Long={self.only_long}, "
                   f"Leverage=[{self.min_leverage}x-{self.max_leverage}x]")

    def analyze(self, df: pd.DataFrame, current_position: Optional[Dict] = None) -> Dict[str, Any]:
        """
        分析市场并生成交易信号

        Args:
            df: 市场数据DataFrame（OHLCV）
            current_position: 当前持仓信息（如果有）

        Returns:
            Dict: 包含信号、理由、止损、止盈等信息的字典
        """
        try:
            # 1. 计算技术指标
            indicators = self._calculate_indicators(df)

            # 2. 判断大趋势
            trend = self._analyze_trend(indicators)

            # 3. 生成交易信号
            signal = self._generate_signal(indicators, trend, current_position)

            # 4. 计算止损止盈
            if signal['signal'] in ['BUY', 'SELL']:
                signal.update(self._calculate_exit_levels(indicators))

            # 5. 添加调试信息
            signal.update({
                'trend': trend,
                'current_price': indicators['close'],
                'ema_144': indicators.get('ema_144', 0),
                'rsi': indicators.get('rsi', 0),
                'bollinger_upper': indicators.get('bollinger_upper', 0),
                'bollinger_lower': indicators.get('bollinger_lower', 0),
            })

            logger.info(f"TrendPullback Signal: {signal['signal']} | "
                       f"Price: {indicators['close']:.2f} | "
                       f"Trend: {trend} | "
                       f"RSI: {indicators.get('rsi', 0):.2f} | "
                       f"Reason: {signal['reasoning']}")

            return signal

        except Exception as e:
            logger.error(f"Error in TrendPullbackStrategy.analyze: {e}")
            return self._create_hold_signal(f"Analysis error: {str(e)}")

    def _calculate_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        计算技术指标

        Args:
            df: OHLCV数据

        Returns:
            Dict: 指标值字典
        """
        # 确保有足够的数据
        min_required = max(self.ema_period, self.bollinger_period if self.use_bollinger_exit else self.ema_period)
        if len(df) < min_required:
            raise ValueError(f"Insufficient data: need at least {min_required} candles, got {len(df)}")

        indicators = {
            'close': float(df['close'].iloc[-1]),
            'high': float(df['high'].iloc[-1]),
            'low': float(df['low'].iloc[-1]),
        }

        # 计算EMA 144
        if PANDAS_TA_AVAILABLE:
            indicators['ema_144'] = float(df.ta.ema(length=self.ema_period).iloc[-1])
        else:
            indicators['ema_144'] = self._calculate_ema_fallback(df['close'], self.ema_period)

        # 计算RSI
        if PANDAS_TA_AVAILABLE:
            indicators['rsi'] = float(df.ta.rsi(length=self.rsi_period).iloc[-1])
        else:
            indicators['rsi'] = self._calculate_rsi_fallback(df['close'], self.rsi_period)

        # 计算布林带
        if self.use_bollinger_exit:
            if PANDAS_TA_AVAILABLE:
                bb = df.ta.bbands(length=self.bollinger_period, std=self.bollinger_std_dev)
                indicators['bollinger_upper'] = float(bb[f'BBL_{self.bollinger_period}_{self.bollinger_std_dev}'].iloc[-1])
                indicators['bollinger_lower'] = float(bb[f'BBU_{self.bollinger_period}_{self.bollinger_std_dev}'].iloc[-1])
                indicators['bollinger_middle'] = float(bb[f'BBM_{self.bollinger_period}_{self.bollinger_std_dev}'].iloc[-1])
            else:
                bb = self._calculate_bollinger_bands_fallback(df['close'], self.bollinger_period, self.bollinger_std_dev)
                indicators.update(bb)

        return indicators

    def _analyze_trend(self, indicators: Dict[str, float]) -> str:
        """
        判断趋势方向

        Args:
            indicators: 技术指标字典

        Returns:
            str: 'bullish', 'bearish', 或 'neutral'
        """
        current_price = indicators['close']
        ema_144 = indicators.get('ema_144', 0)

        if ema_144 == 0:
            return 'neutral'

        # 价格高于EMA 144 = 牛市
        if current_price > ema_144:
            return 'bullish'
        # 价格低于EMA 144 = 熊市
        elif current_price < ema_144:
            return 'bearish'
        else:
            return 'neutral'

    def _generate_signal(self, indicators: Dict[str, float],
                      trend: str,
                      current_position: Optional[Dict] = None) -> Dict[str, Any]:
        """
        生成交易信号

        Args:
            indicators: 技术指标
            trend: 趋势方向
            current_position: 当前持仓

        Returns:
            Dict: 信号信息
        """
        signal = {
            'signal': 'HOLD',
            'confidence': 50.0,
            'reasoning': '',
            'position_size': 0.0,
        }

        has_position = current_position is not None and current_position.get('size', 0) > 0

        # 牛市：只做多
        if trend == 'bullish':
            if not has_position:
                # 没有持仓，检查入场条件
                rsi = indicators.get('rsi', 50)
                if rsi < self.rsi_oversold:
                    signal['signal'] = 'BUY'
                    signal['confidence'] = 70.0
                    signal['reasoning'] = f"Bullish trend + RSI oversold ({rsi:.2f} < {self.rsi_oversold})"

                    # 计算止损价格
                    stop_loss_price = indicators['close'] * (1 - self.stop_loss_pct)

                    # 使用"不死鸟"仓位管理
                    position_info = self._calculate_position_size(
                        indicators['close'],
                        stop_loss_price
                    )
                    signal['position_size'] = position_info['position_size']
                    signal['position_value'] = position_info['position_value']
                    signal['leverage'] = position_info['leverage']
                    signal['risk_amount'] = position_info['risk_amount']
                    signal['risk_pct'] = position_info['risk_pct']
                else:
                    signal['reasoning'] = f"Bullish trend but no oversold signal (RSI: {rsi:.2f})"
            else:
                # 有持仓，检查出场条件
                exit_signal = self._check_exit_conditions(indicators, current_position, 'long')
                if exit_signal:
                    signal.update(exit_signal)
                else:
                    signal['reasoning'] = "Long position open, waiting for exit signal"

        # 熊市：只做空（如果允许）
        elif trend == 'bearish' and not self.only_long:
            if not has_position:
                rsi = indicators.get('rsi', 50)
                # 熊市中，RSI > 70 超买时做空
                if rsi > self.rsi_overbought:
                    signal['signal'] = 'SELL'
                    signal['confidence'] = 70.0
                    signal['reasoning'] = f"Bearish trend + RSI overbought ({rsi:.2f} > {self.rsi_overbought})"

                    # 计算止损价格
                    stop_loss_price = indicators['close'] * (1 + self.stop_loss_pct)

                    # 使用"不死鸟"仓位管理
                    position_info = self._calculate_position_size(
                        indicators['close'],
                        stop_loss_price
                    )
                    signal['position_size'] = position_info['position_size']
                    signal['position_value'] = position_info['position_value']
                    signal['leverage'] = position_info['leverage']
                    signal['risk_amount'] = position_info['risk_amount']
                    signal['risk_pct'] = position_info['risk_pct']
                else:
                    signal['reasoning'] = f"Bearish trend but no overbought signal (RSI: {rsi:.2f})"
            else:
                # 有持仓，检查出场条件
                exit_signal = self._check_exit_conditions(indicators, current_position, 'short')
                if exit_signal:
                    signal.update(exit_signal)
                else:
                    signal['reasoning'] = "Short position open, waiting for exit signal"

        # 只做多模式下的熊市
        elif trend == 'bearish' and self.only_long:
            signal['reasoning'] = f"Bearish trend (only long mode enabled), waiting for bullish trend"

        # 中性市场
        else:
            signal['reasoning'] = "Neutral market, waiting for clear trend"

        return signal

    def _check_exit_conditions(self, indicators: Dict[str, float],
                           position: Dict, position_type: str) -> Optional[Dict]:
        """
        检查出場条件

        Args:
            indicators: 技术指标
            position: 持仓信息
            position_type: 'long' 或 'short'

        Returns:
            Optional[Dict]: 出場信号或None
        """
        entry_price = position.get('entry_price', 0)
        current_price = indicators['close']
        rsi = indicators.get('rsi', 50)

        if entry_price == 0:
            return None

        # 检查止盈条件
        if position_type == 'long':
            # 多头止盈
            if rsi > self.rsi_overbought:
                return {
                    'signal': 'SELL',
                    'confidence': 80.0,
                    'reasoning': f"Take profit: RSI overbought ({rsi:.2f} > {self.rsi_overbought})",
                    'position_size': 0.0
                }

            if self.use_bollinger_exit:
                bollinger_upper = indicators.get('bollinger_upper', 0)
                if current_price >= bollinger_upper:
                    return {
                        'signal': 'SELL',
                        'confidence': 75.0,
                        'reasoning': f"Take profit: Price hit Bollinger Upper Band ({current_price:.2f} >= {bollinger_upper:.2f})",
                        'position_size': 0.0
                    }

        # 检查止损条件
        ema_144 = indicators.get('ema_144', 0)

        # 止损1: 跌破EMA 144（多头）或涨破EMA 144（空头）
        if position_type == 'long' and current_price < ema_144:
            return {
                'signal': 'SELL',
                'confidence': 90.0,
                'reasoning': f"Stop Loss: Price broke below EMA {self.ema_period} ({current_price:.2f} < {ema_144:.2f})",
                'position_size': 0.0,
                'stop_loss_triggered': True
            }
        elif position_type == 'short' and current_price > ema_144:
            return {
                'signal': 'BUY',
                'confidence': 90.0,
                'reasoning': f"Stop Loss: Price broke above EMA {self.ema_period} ({current_price:.2f} > {ema_144:.2f})",
                'position_size': 0.0,
                'stop_loss_triggered': True
            }

        # 止损2: 百分比止损
        price_change_pct = (current_price - entry_price) / entry_price
        if position_type == 'long' and price_change_pct < -self.stop_loss_pct:
            return {
                'signal': 'SELL',
                'confidence': 85.0,
                'reasoning': f"Stop Loss: {self.stop_loss_pct*100}% loss reached ({price_change_pct*100:.2f}%)",
                'position_size': 0.0,
                'stop_loss_triggered': True
            }
        elif position_type == 'short' and price_change_pct > self.stop_loss_pct:
            return {
                'signal': 'BUY',
                'confidence': 85.0,
                'reasoning': f"Stop Loss: {self.stop_loss_pct*100}% loss reached ({price_change_pct*100:.2f}%)",
                'position_size': 0.0,
                'stop_loss_triggered': True
            }

        return None

    def _calculate_exit_levels(self, indicators: Dict[str, float]) -> Dict[str, float]:
        """
        计算止损和止盈价格

        Args:
            indicators: 技术指标

        Returns:
            Dict: 止损止盈价格
        """
        current_price = indicators['close']

        # 百分比止损止盈
        stop_loss_price = current_price * (1 - self.stop_loss_pct)
        take_profit_price = current_price * (1 + self.take_profit_pct)

        return {
            'stop_loss': float(stop_loss_price),
            'take_profit': float(take_profit_price)
        }

    def _calculate_position_size(self, current_price: float, stop_loss_price: float) -> Dict[str, float]:
        """
        "不死鸟"仓位管理 - 基于固定风险计算精确仓位

        核心公式：每单最多只亏本金的 2%

        Args:
            current_price: 当前价格
            stop_loss_price: 止损价格

        Returns:
            Dict: 包含仓位数量、仓位价值、杠杆率等信息
        """
        trading_config = self.config.get('trading', {})
        risk_config = self.config.get('strategy', {})

        capital = trading_config.get('capital', 100.0)
        max_risk_pct = trading_config.get('max_risk_pct', 0.02)  # 默认2%风险
        max_leverage = risk_config.get('max_leverage', 3.0)  # 最大3倍杠杆
        min_leverage = risk_config.get('min_leverage', 2.0)  # 最小2倍杠杆

        # 1. 计算允许的最大亏损金额
        max_risk_amount = capital * max_risk_pct

        # 2. 计算每单位的止损金额
        if stop_loss_price > 0 and stop_loss_price < current_price:
            risk_per_unit = current_price - stop_loss_price
        else:
            # 如果止损价格无效，使用百分比止损
            risk_per_unit = current_price * self.stop_loss_pct

        if risk_per_unit <= 0:
            logger.warning("Invalid risk per unit, using fallback position size")
            return {
                'position_size': 0.0,
                'position_value': 0.0,
                'leverage': 0.0,
                'risk_amount': 0.0,
                'reasoning': 'Invalid stop loss calculation'
            }

        # 3. 计算应该买入的数量（核心公式）
        # 数量 = 允许亏损金额 / 每单位止损金额
        position_size = max_risk_amount / risk_per_unit

        # 4. 计算仓位价值
        position_value = position_size * current_price

        # 5. 计算实际杠杆率
        # 杠杆率 = 仓位价值 / 本金
        leverage = position_value / capital if capital > 0 else 0

        # 6. 杠杆率调整（确保在2x-3x之间）
        if leverage > max_leverage:
            # 杠杆过高，降低仓位
            target_position_value = capital * max_leverage
            position_size = target_position_value / current_price
            position_value = target_position_value
            leverage = max_leverage
            logger.info(f"Leverage too high ({leverage:.2f}x), adjusting to {max_leverage}x")
        elif leverage < min_leverage:
            # 杠杆过低，可以提高仓位（可选）
            logger.info(f"Leverage low ({leverage:.2f}x), could increase to {min_leverage}x")

        # 7. 计算实际风险金额
        actual_risk = position_size * risk_per_unit

        result = {
            'position_size': float(position_size),
            'position_value': float(position_value),
            'leverage': float(leverage),
            'risk_amount': float(actual_risk),
            'risk_pct': float(actual_risk / capital * 100),
            'max_risk_amount': float(max_risk_amount),
            'max_risk_pct': float(max_risk_pct * 100),
            'risk_per_unit': float(risk_per_unit),
            'reasoning': f'Fixed Risk: ${actual_risk:.2f} ({actual_risk/capital*100:.2f}%) | '
                        f'Position: {position_size:.4f} units | '
                        f'Value: ${position_value:.2f} | '
                        f'Leverage: {leverage:.2f}x'
        }

        logger.info(f"不死鸟仓位计算: {result['reasoning']}")

        return result

    # ========== Fallback 方法（当pandas-ta不可用时） ==========

    def _calculate_ema_fallback(self, prices: pd.Series, period: int) -> float:
        """计算EMA的备用方法"""
        return float(prices.ewm(span=period, adjust=False).mean().iloc[-1])

    def _calculate_rsi_fallback(self, prices: pd.Series, period: int = 14) -> float:
        """计算RSI的备用方法"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return float(rsi.iloc[-1])

    def _calculate_bollinger_bands_fallback(self, prices: pd.Series, period: int = 20, std_dev: float = 2) -> Dict[str, float]:
        """计算布林带的备用方法"""
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()

        return {
            'bollinger_upper': float((sma + std * std_dev).iloc[-1]),
            'bollinger_lower': float((sma - std * std_dev).iloc[-1]),
            'bollinger_middle': float(sma.iloc[-1])
        }

    def _create_hold_signal(self, reason: str = "No clear trading signal") -> Dict[str, Any]:
        """创建持有信号"""
        return {
            'signal': 'HOLD',
            'confidence': 50.0,
            'reasoning': reason,
            'position_size': 0.0,
            'stop_loss': 0.0,
            'take_profit': 0.0,
            'trend': 'unknown',
            'current_price': 0.0,
            'ema_144': 0.0,
            'rsi': 50.0,
            'bollinger_upper': 0.0,
            'bollinger_lower': 0.0
        }


# 便捷函数
def create_trend_pullback_strategy(config: Dict[str, Any]) -> TrendPullbackStrategy:
    """
    创建趋势回调策略实例

    Args:
        config: 策略配置

    Returns:
        TrendPullbackStrategy: 策略实例
    """
    return TrendPullbackStrategy(config)
