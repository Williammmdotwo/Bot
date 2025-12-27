"""
技术指标格式化器

此模块负责将技术指标数据格式化为可读的字符串
属于纯逻辑层，不包含业务逻辑
"""

from typing import Dict


def format_indicators_for_display(indicators: Dict) -> str:
    """
    格式化技术指标用于显示

    Args:
        indicators: 技术指标字典

    Returns:
        str: 格式化的指标字符串
    """
    if not indicators or "error" in indicators:
        return "技术指标数据不足"

    formatted = []

    # 安全格式化函数，处理字符串值
    def safe_format_float(value, default='N/A', decimals=2):
        try:
            if value is None or value == 'N/A':
                return default
            return f"{float(value):.{decimals}f}"
        except (ValueError, TypeError):
            return default

    # 当前价格
    formatted.append(f"当前价格: {safe_format_float(indicators.get('current_price'))}")

    # RSI
    formatted.append(f"RSI: {safe_format_float(indicators.get('rsi'), decimals=2)}")

    # MACD
    macd_data = indicators.get('macd', {})
    macd_val = safe_format_float(macd_data.get('macd', 0), decimals=4)
    macd_signal = safe_format_float(macd_data.get('signal', 0), decimals=4)
    formatted.append(f"MACD: {macd_val}, 信号: {macd_signal}")

    # 布林带
    bollinger_data = indicators.get('bollinger', {})
    bb_upper = safe_format_float(bollinger_data.get('upper', 0))
    bb_middle = safe_format_float(bollinger_data.get('middle', 0))
    bb_lower = safe_format_float(bollinger_data.get('lower', 0))
    formatted.append(f"布林带: 上轨 {bb_upper}, 中轨 {bb_middle}, 下轨 {bb_lower}")

    # EMA
    ema_20 = safe_format_float(indicators.get('ema_20'))
    ema_50 = safe_format_float(indicators.get('ema_50'))
    formatted.append(f"EMA20: {ema_20}, EMA50: {ema_50}")

    # 文本字段
    trend_value = indicators.get('trend', 'N/A')
    momentum_value = indicators.get('momentum', 'N/A')
    volatility_value = indicators.get('volatility', 'N/A')

    # 处理 None 值
    formatted.append(f"趋势: {trend_value if trend_value is not None else 'N/A'}")
    formatted.append(f"动量: {momentum_value if momentum_value is not None else 'N/A'}")
    formatted.append(f"波动性: {volatility_value if volatility_value is not None else 'N/A'}")

    # 支撑/阻力位
    sr_data = indicators.get('support_resistance', {})
    support = safe_format_float(sr_data.get('support'))
    resistance = safe_format_float(sr_data.get('resistance'))
    formatted.append(f"支撑位: {support}")
    formatted.append(f"阻力位: {resistance}")

    return "\n".join(formatted)
