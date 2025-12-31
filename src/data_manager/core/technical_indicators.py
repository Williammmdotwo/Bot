"""
技术指标计算模块
Technical Indicators Calculator for Athena Trader
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class TechnicalIndicators:
    """技术指标计算类"""

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        """计算 RSI (Relative Strength Index) - Pandas 优化版本"""
        if len(prices) < period + 1:
            return 50.0  # 默认中性值

        # 使用 Pandas 向量化计算
        s = pd.Series(prices)
        delta = s.diff()

        # 分离上涨和下跌
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return float(rsi.iloc[-1])


    @staticmethod
    def _calculate_macd_signal_line(macd_history: List[float], signal_period: int = 9) -> float:
        """计算MACD signal线（EMA of MACD line）"""
        if len(macd_history) < signal_period:
            return macd_history[-1] if macd_history else 0.0

        return TechnicalIndicators.calculate_ema(macd_history, signal_period)

    @staticmethod
    def _calculate_macd_history(prices: List[float], fast: int = 12, slow: int = 26) -> List[float]:
        """
        计算MACD历史数据（完全优化的Pandas版本）

        直接使用 Pandas 原生方法计算快速EMA和慢速EMA，然后相减
        充分利用 Pandas 的 C 语言底层加速
        """
        if len(prices) < slow:
            return []

        # 转换为 Pandas Series
        s = pd.Series(prices)

        # 直接使用 Pandas 原生方法计算完整的 EMA 序列
        # adjust=False 匹配传统的递归计算方式
        fast_ema_series = s.ewm(span=fast, adjust=False).mean()
        slow_ema_series = s.ewm(span=slow, adjust=False).mean()

        # 计算MACD历史（从slow-1个点开始有效）
        macd_series = fast_ema_series - slow_ema_series

        # 转换为列表，跳过前slow-1个无效值
        return macd_series[slow-1:].tolist()

    @staticmethod
    def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, float]:
        """计算 MACD (Moving Average Convergence Divergence) - 优化版本"""
        if len(prices) < slow:
            return {"macd": 0, "signal": 0, "histogram": 0}

        # 优化：直接计算当前MACD值，不需要完整历史
        multiplier_fast = 2 / (fast + 1)
        multiplier_slow = 2 / (slow + 1)

        fast_ema = prices[0]
        slow_ema = prices[0]

        for price in prices[1:]:
            fast_ema = (price * multiplier_fast) + (fast_ema * (1 - multiplier_fast))
            slow_ema = (price * multiplier_slow) + (slow_ema * (1 - multiplier_slow))

        macd_line = fast_ema - slow_ema

        # 计算Signal线需要MACD历史，但可以只计算最近signal个点
        # 为了准确性，还是需要计算MACD历史，但使用优化的_calculate_macd_history
        macd_history = TechnicalIndicators._calculate_macd_history(prices, fast, slow)

        if not macd_history:
            return {"macd": float(macd_line), "signal": float(macd_line), "histogram": 0.0}

        # 当前MACD线值（应该和上面计算的一致）
        macd_line = macd_history[-1]

        # 计算Signal线（MACD线的EMA）
        signal_line = TechnicalIndicators._calculate_macd_signal_line(macd_history, signal)

        # 计算Histogram
        histogram = macd_line - signal_line

        return {
            "macd": float(macd_line),
            "signal": float(signal_line),
            "histogram": float(histogram)
        }
    @staticmethod
    def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: float = 2) -> Dict[str, float]:
        """计算布林带 Bollinger Bands - Pandas 优化版本"""
        if len(prices) < period:
            return {"upper": 0, "middle": 0, "lower": 0}

        s = pd.Series(prices)
        rolling_mean = s.rolling(window=period).mean()
        rolling_std = s.rolling(window=period).std()

        middle = float(rolling_mean.iloc[-1])
        std = float(rolling_std.iloc[-1])

        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)

        return {
            "upper": float(upper),
            "middle": float(middle),
            "lower": float(lower),
            "width": float(upper - lower)
        }

    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> float:
        """计算指数移动平均线 EMA - Pandas 原生方法"""
        if not prices:
            return 0.0

        # 如果数据不足，返回最后一个价格（向后兼容）
        if len(prices) < period:
            return float(prices[-1])

        # 转换为 Series 并在内存中计算
        s = pd.Series(prices)
        # adjust=False 匹配传统的递归计算方式
        ema = s.ewm(span=period, adjust=False).mean()
        return float(ema.iloc[-1])

    @staticmethod
    def _ema(prices: List[float], period: int) -> float:
        """EMA 计算的内部方法"""
        return TechnicalIndicators.calculate_ema(prices, period)

    @staticmethod
    def calculate_sma(prices: List[float], period: int) -> float:
        """计算简单移动平均线 SMA - Pandas 优化版本"""
        if not prices:
            return 0.0

        # 如果数据不足，返回最后一个价格（向后兼容）
        if len(prices) < period:
            return float(prices[-1])

        s = pd.Series(prices)
        sma = s.rolling(window=period).mean()
        return float(sma.iloc[-1])

    @staticmethod
    def calculate_atr(highs: List[float], lows: List[float], period: int = 14) -> float:
        """计算平均真实范围 ATR - Pandas 向量化版本"""
        if len(highs) < 2 or len(lows) < 2:
            return 0.0

        # 如果数据不足，返回 0.0（向后兼容）
        if len(highs) < period + 1 or len(lows) < period + 1:
            return 0.0

        h_series = pd.Series(highs)
        l_series = pd.Series(lows)
        c_series = pd.Series(highs).shift(1)  # 前一日收盘价（用 high 近似）

        # 计算真实范围
        high_low = h_series - l_series
        high_close = (h_series - c_series).abs()
        low_close = (l_series - l_series.shift(1)).abs()

        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        return float(atr.iloc[-1])

    @staticmethod
    def calculate_obv(prices: List[float], volumes: List[float]) -> List[float]:
        """计算能量潮 OBV"""
        if len(prices) != len(volumes) or len(prices) < 2:
            return []

        obv = [0]
        for i in range(1, len(prices)):
            if prices[i] > prices[i-1]:
                obv.append(obv[-1] + volumes[i])
            elif prices[i] < prices[i-1]:
                obv.append(obv[-1] - volumes[i])
            else:
                obv.append(obv[-1])

        return obv

    @staticmethod
    def calculate_vwap(prices: List[float], volumes: List[float]) -> float:
        """计算成交量加权平均价 VWAP - Pandas 优化版本"""
        if len(prices) != len(volumes) or not prices:
            return 0.0

        price_series = pd.Series(prices)
        volume_series = pd.Series(volumes)

        total_pv = (price_series * volume_series).sum()
        total_volume = volume_series.sum()

        return float(total_pv / total_volume) if total_volume > 0 else 0.0

    @staticmethod
    def calculate_support_resistance(prices: List[float], lookback: int = 20) -> Dict[str, float]:
        """计算支撑位和阻力位"""
        if len(prices) < lookback:
            return {"support": 0, "resistance": 0}

        recent_prices = prices[-lookback:]
        support = float(np.min(recent_prices))
        resistance = float(np.max(recent_prices))

        return {
            "support": support,
            "resistance": resistance,
            "midpoint": (support + resistance) / 2
        }

    @staticmethod
    def analyze_volume_profile(trades: List[Dict]) -> Dict[str, Any]:
        """分析成交量分布"""
        if not trades:
            return {"volume_profile": {}, "poc": 0, "value_area": {"high": 0, "low": 0}}

        # 按价格分组统计成交量
        volume_by_price = {}
        for trade in trades:
            price = trade.get('price', 0)
            amount = trade.get('amount', 0)
            volume_by_price[price] = volume_by_price.get(price, 0) + amount

        # 找到最大成交量价格 (Point of Control)
        poc = max(volume_by_price.items(), key=lambda x: x[1])[0] if volume_by_price else 0

        # 计算价值区域 (70% 的成交量)
        total_volume = sum(volume_by_price.values())
        sorted_prices = sorted(volume_by_price.items(), key=lambda x: x[1], reverse=True)

        cumulative_volume = 0
        va_high = va_low = poc

        for price, volume in sorted_prices:
            cumulative_volume += volume
            if cumulative_volume >= total_volume * 0.7:
                break
            va_high = price

        return {
            "volume_profile": volume_by_price,
            "poc": poc,
            "value_area": {"high": va_high, "low": va_low}
        }

    @staticmethod
    def calculate_all_indicators(ohlcv_data: List) -> Dict[str, Any]:
        """计算所有技术指标

        支持两种格式:
        1. List[List]: [[timestamp, open, high, low, close, volume], ...]
        2. List[Dict]: [{"timestamp": ..., "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}, ...]
        """
        if not ohlcv_data:
            logger.error("OHLCV data is empty")
            return {"error": "No OHLCV data available"}

        # 统一数据格式为 List[List]
        normalized_data = []
        for i, candle in enumerate(ohlcv_data):
            if isinstance(candle, dict):
                # Dict格式转换为List格式
                normalized_data.append([
                    candle.get('timestamp', 0),
                    candle.get('open', 0),
                    candle.get('high', 0),
                    candle.get('low', 0),
                    candle.get('close', 0),
                    candle.get('volume', 0)
                ])
            elif isinstance(candle, list) and len(candle) >= 6:
                # 已经是List格式
                normalized_data.append(candle[:6])

        ohlcv_data = normalized_data
        data_length = len(ohlcv_data)

        if data_length < 10:
            logger.warning(f"Insufficient data for technical analysis: {data_length} candles (minimum 10 required)")
            return {"error": f"Insufficient data for technical analysis: {data_length} candles (minimum 10 required)"}

        # 数据质量检查
        if data_length < 20:
            logger.warning(f"Using limited data for technical analysis: {data_length} candles (20+ recommended for full accuracy)")

        # 数据质量验证
        quality_issues = []
        for i, candle in enumerate(ohlcv_data):
            if len(candle) < 6:
                quality_issues.append(f"Candle {i}: incomplete data (expected 6 values, got {len(candle)})")
                continue

            timestamp, open_price, high_price, low_price, close_price, volume = candle[0], candle[1], candle[2], candle[3], candle[4], candle[5]

            # 检查价格合理性
            if high_price < low_price:
                quality_issues.append(f"Candle {i}: high < low ({high_price} < {low_price})")
            if close_price > high_price or close_price < low_price:
                quality_issues.append(f"Candle {i}: close outside high-low range ({close_price})")
            if volume < 0:
                quality_issues.append(f"Candle {i}: negative volume ({volume})")

        if quality_issues:
            logger.warning(f"Data quality issues detected: {len(quality_issues)} problems")
            for issue in quality_issues[:5]:  # 只记录前5个问题
                logger.warning(f"  {issue}")
            if len(quality_issues) > 5:
                logger.warning(f"  ... and {len(quality_issues) - 5} more issues")

        # 提取价格数据
        closes = [candle[4] for candle in ohlcv_data]  # Close prices
        highs = [candle[2] for candle in ohlcv_data]   # High prices
        lows = [candle[3] for candle in ohlcv_data]    # Low prices
        volumes = [candle[5] for candle in ohlcv_data]  # Volumes

        current_price = closes[-1]

        # 计算各种指标
        indicators = {
            "current_price": current_price,
            "rsi": TechnicalIndicators.calculate_rsi(closes),
            "macd": TechnicalIndicators.calculate_macd(closes),
            "bollinger": TechnicalIndicators.calculate_bollinger_bands(closes),
            "ema_20": TechnicalIndicators.calculate_ema(closes, 20),
            "ema_50": TechnicalIndicators.calculate_ema(closes, 50),
            "sma_20": TechnicalIndicators.calculate_sma(closes, 20),
            "sma_50": TechnicalIndicators.calculate_sma(closes, 50),
            "atr": TechnicalIndicators.calculate_atr(highs, lows),
            "obv": TechnicalIndicators.calculate_obv(closes, volumes)[-10:] if len(TechnicalIndicators.calculate_obv(closes, volumes)) >= 10 else [],
            "vwap": TechnicalIndicators.calculate_vwap(closes[-50:], volumes[-50:]) if len(closes) >= 50 else current_price,
            "support_resistance": TechnicalIndicators.calculate_support_resistance(closes),
            "price_change_24h": ((current_price - closes[0]) / closes[0] * 100) if len(closes) > 1 else 0,
            "volume_change": ((volumes[-1] - np.mean(volumes[-20:])) / np.mean(volumes[-20:]) * 100) if len(volumes) >= 20 else 0
        }

        # 添加趋势分析
        indicators["trend"] = TechnicalIndicators._analyze_trend(indicators)
        indicators["momentum"] = TechnicalIndicators._analyze_momentum(indicators)
        indicators["volatility"] = TechnicalIndicators._analyze_volatility(indicators)

        return indicators

    @staticmethod
    def _analyze_trend(indicators: Dict) -> str:
        """分析趋势方向"""
        current = indicators["current_price"]
        ema_20 = indicators["ema_20"]
        ema_50 = indicators["ema_50"]

        if current > ema_20 > ema_50:
            return "strong_uptrend"
        elif current > ema_20 and ema_20 < ema_50:
            return "weak_uptrend"
        elif current < ema_20 < ema_50:
            return "strong_downtrend"
        elif current < ema_20 and ema_20 > ema_50:
            return "weak_downtrend"
        else:
            return "sideways"

    @staticmethod
    def _analyze_momentum(indicators: Dict) -> str:
        """分析动量"""
        rsi = indicators["rsi"]
        macd = indicators["macd"]

        if rsi > 70 and macd["histogram"] > 0:
            return "strong_bullish"
        elif rsi > 50 and macd["histogram"] > 0:
            return "bullish"
        elif rsi < 30 and macd["histogram"] < 0:
            return "strong_bearish"
        elif rsi < 50 and macd["histogram"] < 0:
            return "bearish"
        else:
            return "neutral"

    @staticmethod
    def _analyze_volatility(indicators: Dict) -> str:
        """分析波动性"""
        atr = indicators["atr"]
        current_price = indicators["current_price"]
        bollinger = indicators["bollinger"]

        if current_price > bollinger["upper"]:
            return "high_volatility_breakout"
        elif current_price < bollinger["lower"]:
            return "high_volatility_breakdown"
        elif bollinger["width"] / current_price > 0.05:
            return "high_volatility"
        elif bollinger["width"] / current_price < 0.02:
            return "low_volatility"
        else:
            return "normal_volatility"
