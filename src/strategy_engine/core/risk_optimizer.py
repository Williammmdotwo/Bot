"""
风险优化器

此模块负责基于风险分析优化交易信号
属于纯逻辑层，不包含网络调用
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def optimize_signal_with_risk(signal: Dict[str, Any], enhanced_analysis: Dict, current_price: float) -> Dict[str, Any]:
    """基于风险分析优化交易信号"""
    try:
        optimized_signal = signal.copy()

        # 获取波动性信息
        volatility_data = get_volatility_metrics(enhanced_analysis)
        volatility_multiplier = volatility_data.get("multiplier", 1.0)

        # 动态调整止损止盈
        if optimized_signal.get("side") in ["BUY", "SELL"]:
            base_stop_distance = 0.02  # 基础2%止损
            base_take_profit_ratio = 2.0  # 基础1:2风险回报比

            # 根据波动性调整
            adjusted_stop_distance = base_stop_distance * volatility_multiplier
            adjusted_take_profit_ratio = base_take_profit_ratio * (2.0 - volatility_multiplier + 1.0)

            if optimized_signal["side"] == "BUY":
                optimized_signal["stop_loss"] = current_price * (1 - adjusted_stop_distance)
                optimized_signal["take_profit"] = current_price * (1 + adjusted_stop_distance * adjusted_take_profit_ratio)
            else:  # SELL
                optimized_signal["stop_loss"] = current_price * (1 + adjusted_stop_distance)
                optimized_signal["take_profit"] = current_price * (1 - adjusted_stop_distance * adjusted_take_profit_ratio)

            # 更新风险评估
            if "risk_assessment" in optimized_signal:
                optimized_signal["risk_assessment"]["stop_loss_distance"] = adjusted_stop_distance
                optimized_signal["risk_assessment"]["take_profit_ratio"] = adjusted_take_profit_ratio

                # 根据波动性调整风险等级
                if volatility_multiplier > 1.5:
                    optimized_signal["risk_assessment"]["risk_level"] = "HIGH"
                elif volatility_multiplier > 1.2:
                    optimized_signal["risk_assessment"]["risk_level"] = "MEDIUM"
                else:
                    optimized_signal["risk_assessment"]["risk_level"] = "LOW"

        # 根据趋势一致性调整置信度
        try:
            from .data_merger import merge_historical_with_current
            # 这里需要导入 analyze_trend_consistency 函数
            # 由于该函数在 main.py 中，我们需要临时实现或导入
        except ImportError:
            pass

        logger.info(f"Signal optimized with risk adjustment: volatility_multiplier={volatility_multiplier}")
        return optimized_signal

    except Exception as e:
        logger.error(f"Failed to optimize signal with risk: {e}")
        return signal


def apply_conservative_adjustment(signal: Dict[str, Any], current_price: float) -> Dict[str, Any]:
    """应用保守调整到交易信号"""
    try:
        adjusted_signal = signal.copy()

        # 降低置信度
        adjusted_signal["confidence"] = max(65.0, adjusted_signal.get("confidence", 70) - 10)

        # 减小仓位大小
        adjusted_signal["position_size"] = max(0.01, adjusted_signal.get("position_size", 0.02) * 0.7)

        # 收紧止损止盈
        if adjusted_signal.get("side") in ["BUY", "SELL"]:
            if adjusted_signal["side"] == "BUY":
                adjusted_signal["stop_loss"] = current_price * 0.99  # 1%止损
                adjusted_signal["take_profit"] = current_price * 1.03  # 3%止盈
            else:  # SELL
                adjusted_signal["stop_loss"] = current_price * 1.01  # 1%止损
                adjusted_signal["take_profit"] = current_price * 0.97  # 3%止盈

            # 更新风险评估
            if "risk_assessment" in adjusted_signal:
                adjusted_signal["risk_assessment"]["risk_level"] = "LOW"
                adjusted_signal["risk_assessment"]["stop_loss_distance"] = 0.01
                adjusted_signal["risk_assessment"]["take_profit_ratio"] = 3.0

        # 更新推理
        adjusted_signal["reasoning"] = f"Conservative adjustment applied: {adjusted_signal.get('reasoning', '')}"

        logger.info("Applied conservative adjustment to signal")
        return adjusted_signal

    except Exception as e:
        logger.error(f"Failed to apply conservative adjustment: {e}")
        return signal


def get_volatility_metrics(enhanced_analysis: Dict) -> Dict[str, float]:
    """获取波动性指标"""
    try:
        volatility_values = []

        for timeframe, data in enhanced_analysis.items():
            if data and "volatility" in data:
                vol = data["volatility"]
                if isinstance(vol, (int, float)):
                    volatility_values.append(vol)

        if not volatility_values:
            return {"multiplier": 1.0, "average_volatility": 0.0}

        avg_volatility = sum(volatility_values) / len(volatility_values)

        # 计算波动性倍数（基于历史平均值）
        normal_volatility = 0.02  # 假设正常波动性为2%
        multiplier = min(2.0, max(0.8, avg_volatility / normal_volatility))

        return {
            "multiplier": multiplier,
            "average_volatility": avg_volatility,
            "volatility_values": volatility_values
        }

    except Exception as e:
        logger.error(f"Failed to get volatility metrics: {e}")
        return {"multiplier": 1.0, "average_volatility": 0.0}
