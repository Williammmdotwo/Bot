"""
信号生成器

此模块负责生成交易信号
属于纯逻辑层，不包含网络调用
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def generate_fallback_signal(enhanced_analysis: Dict, market_data: Dict, symbol: str) -> Dict[str, Any]:
    """使用双均线策略生成交易信号"""
    try:
        logger.info("Generating signal using Dual EMA Crossover Strategy")

        # 动态导入防止循环依赖
        try:
            from ..dual_ema_strategy import generate_dual_ema_signal
        except ImportError:
            from src.strategy_engine.dual_ema_strategy import generate_dual_ema_signal

        # 构造策略需要的历史数据格式
        # 注意：这里我们确保传给策略的是它能读懂的格式
        historical_input = {
            "historical_analysis": enhanced_analysis
        }

        # 生成双均线信号
        ema_signal = generate_dual_ema_signal(historical_input, symbol)

        if not ema_signal:
            logger.warning("Dual EMA strategy failed to generate signal")
            return generate_emergency_hold_signal(symbol, "Strategy returned None")

        # 转换信号格式以匹配主逻辑
        signal = {
            "side": ema_signal.get("signal", "HOLD"),
            "confidence": ema_signal.get("confidence", 0),
            "reasoning": ema_signal.get("reasoning", ""),
            "position_size": ema_signal.get("position_size", 0),
            "stop_loss": ema_signal.get("stop_loss", 0),
            "take_profit": ema_signal.get("take_profit", 0)
        }

        return signal

    except Exception as e:
        logger.error(f"Failed to generate Dual EMA signal: {e}")
        return generate_emergency_hold_signal(symbol, f"Error: {str(e)}")


def generate_fallback_signal_with_details(
    enhanced_analysis: Dict,
    market_data: Dict,
    symbol: str
) -> Dict[str, Any]:
    """
    生成交易信号并添加详细信息

    Args:
        enhanced_analysis: 增强分析数据
        market_data: 市场数据
        symbol: 交易对符号

    Returns:
        Dict: 完整的交易信号
    """
    try:
        # 生成基础信号
        base_signal = generate_fallback_signal(enhanced_analysis, market_data, symbol)

        # 转换信号格式以兼容现有系统
        signal = {
            "side": base_signal.get("side", "HOLD"),
            "symbol": symbol,
            "decision_id": str(hash(str(enhanced_analysis)))[:8],  # 简单的决策ID
            "position_size": base_signal.get("position_size", 0.02),
            "confidence": base_signal.get("confidence", 60.0),
            "reasoning": base_signal.get("reasoning", "Dual EMA strategy"),
            "stop_loss": base_signal.get("stop_loss", 0),
            "take_profit": base_signal.get("take_profit", 0),
            "current_price": base_signal.get("current_price", market_data.get("current_price", 0)),
        }

        # 添加 EMA 信息
        if "historical_analysis" in enhanced_analysis:
            # 从第一个时间框架获取 EMA 值
            for timeframe in ["5m", "15m", "1h", "4h"]:
                if timeframe in enhanced_analysis["historical_analysis"]:
                    indicators = enhanced_analysis["historical_analysis"][timeframe].get("indicators", {})
                    signal["ema_fast"] = indicators.get("ema_fast", 0)
                    signal["ema_slow"] = indicators.get("ema_slow", 0)
                    break

        # 添加兼容性字段（保持与原有系统的兼容）
        signal["risk_assessment"] = {
            "risk_level": "MEDIUM",
            "stop_loss_distance": 0.02,
            "take_profit_ratio": 2.0,
            "historical_support_resistance": False
        }

        signal["technical_summary"] = {
            "trend_consistency": "moderate",
            "momentum_strength": "moderate",
            "volatility_state": "normal",
            "historical_confirmation": "partial"
        }

        signal["market_conditions"] = {
            "sentiment": "neutral",
            "liquidity": "medium",
            "volatility": "stable",
            "historical_pattern": "consolidation"
        }

        signal["historical_analysis"] = {
            "key_levels": [],
            "recent_turning_points": [],
            "trend_duration": "unknown",
            "pattern_recognition": "unknown"
        }

        signal["available_margin"] = 1000

        logger.info(f"Dual EMA signal generated: {signal['side']} with confidence {signal['confidence']}")

        # 日志输出
        if signal['side'] == 'HOLD':
            current_price = signal.get('current_price', 0)
            ema_fast = signal.get('ema_fast', 0)
            ema_slow = signal.get('ema_slow', 0)
            logger.info(f"[HEARTBEAT] 主策略循环返回 HOLD | 价格: {current_price:.2f} | "
                        f"快线: {ema_fast:.2f} | 慢线: {ema_slow:.2f} | "
                        f"状态: 等待交易机会")
        else:
            current_price = signal.get('current_price', 0)
            logger.info(f"🚀 [MAIN_SIGNAL] 主策略循环触发 {signal['side']} @ {current_price:.2f}!")

        return signal

    except Exception as e:
        logger.error(f"Failed to generate signal with details: {e}")
        return generate_emergency_hold_signal(symbol, f"Error: {str(e)}")


def generate_emergency_hold_signal(symbol: str, reason: str) -> Dict[str, Any]:
    """创建紧急持有信号"""
    return {
        "side": "HOLD",
        "symbol": symbol,
        "position_size": 0.0,
        "confidence": 50.0,
        "reasoning": reason,
        "stop_loss": 0,
        "take_profit": 0,
        "current_price": 0,
        "ema_fast": 0,
        "ema_slow": 0,
        "risk_assessment": {
            "risk_level": "LOW",
            "stop_loss_distance": 0.0,
            "take_profit_ratio": 0.0,
            "historical_support_resistance": False
        },
        "technical_summary": {
            "trend_consistency": "unknown",
            "momentum_strength": "unknown",
            "volatility_state": "unknown",
            "historical_confirmation": "none"
        },
        "market_conditions": {
            "sentiment": "neutral",
            "liquidity": "unknown",
            "volatility": "unknown",
            "historical_pattern": "unknown"
        },
        "historical_analysis": {
            "key_levels": [],
            "recent_turning_points": [],
            "trend_duration": "unknown",
            "pattern_recognition": "unknown"
        },
        "available_margin": 1000
    }
