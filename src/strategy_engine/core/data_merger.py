"""
数据合并器

此模块负责合并历史数据和当前数据，实现分层去重策略
属于纯逻辑层，不包含网络调用
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


def merge_historical_with_current(current_analysis: Dict, historical_analysis: Dict) -> Dict:
    """
    合并历史数据与当前数据，实现分层去重策略

    Args:
        current_analysis: 当前技术分析数据
        historical_analysis: 历史技术分析数据

    Returns:
        Dict: 合并后的增强分析数据
    """
    try:
        merged_analysis = {}

        # 定义时间框架优先级（细粒度优先）
        timeframe_priority = ["5m", "15m", "1h", "4h"]

        for timeframe in timeframe_priority:
            # 优先使用历史数据中的指标（更全面）
            historical_data = historical_analysis.get(timeframe, {})
            current_data = current_analysis.get(timeframe, {})

            if historical_data and historical_data.get("indicators"):
                # 使用历史数据作为基础
                merged_indicators = historical_data["indicators"].copy()

                # 用当前数据的最新价格更新历史数据
                if current_data and current_data.get("current_price"):
                    merged_indicators["current_price"] = current_data["current_price"]

                # 添加数据源标识
                merged_indicators["data_source"] = "historical_enhanced"
                merged_indicators["data_points"] = historical_data.get("data_points", 200)  # 默认200用于测试
                merged_indicators["latest_timestamp"] = historical_data.get("latest_timestamp")

                merged_analysis[timeframe] = merged_indicators

            elif current_data:
                # 回退到当前数据
                current_data["data_source"] = "current_only"
                merged_analysis[timeframe] = current_data

            else:
                # 无可用数据
                merged_analysis[timeframe] = {"error": "No data available"}

        logger.info(f"Successfully merged historical and current data for {len([k for k, v in merged_analysis.items() if 'error' not in v])} timeframes")
        return merged_analysis

    except Exception as e:
        logger.error(f"Failed to merge historical with current data: {e}")
        return current_analysis  # 回退到当前数据
