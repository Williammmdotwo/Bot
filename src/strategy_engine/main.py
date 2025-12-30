import uuid
import logging
import time
from typing import Dict, Any, List

# Fix relative imports for direct execution
try:
    from .validator import validate_data, validate_signal
    # Import formatters
    from .formatters import (
        format_indicators_for_display,
        format_orderbook_for_display,
        format_volume_profile_for_display,
        format_sentiment_for_display,
        format_historical_trends_for_display
    )
    # Import core business logic
    from .core import (
        merge_historical_with_current,
        generate_fallback_signal_with_details,
        generate_emergency_hold_signal,
        optimize_signal_with_risk,
        apply_conservative_adjustment,
        get_volatility_metrics
    )
except ImportError:
    from src.strategy_engine.validator import validate_data, validate_signal
    # Import formatters
    from src.strategy_engine.formatters import (
        format_indicators_for_display,
        format_orderbook_for_display,
        format_volume_profile_for_display,
        format_sentiment_for_display,
        format_historical_trends_for_display
    )
    # Import core business logic
    from src.strategy_engine.core import (
        merge_historical_with_current,
        generate_fallback_signal_with_details,
        generate_emergency_hold_signal,
        optimize_signal_with_risk,
        apply_conservative_adjustment,
        get_volatility_metrics
    )
from src.strategy_engine.core import (
    merge_historical_with_current,
    generate_fallback_signal_with_details,
    generate_emergency_hold_signal,
    optimize_signal_with_risk,
    apply_conservative_adjustment,
    get_volatility_metrics
)
from src.strategy_engine.formatters import (
    analyze_trend_consistency,
    identify_key_turning_points,
    analyze_volatility_across_timeframes
)

from src.utils.environment_utils import get_environment_config, get_api_credentials, validate_safety, log_environment_info

logger = logging.getLogger(__name__)

def main_strategy_loop(data_manager, symbol="BTC-USDT", use_demo=False, postgres_db=None):
    """Main strategy loop that analyzes market data and generates trading signals using technical analysis"""
    try:
        decision_id = str(uuid.uuid4())

        # Get comprehensive market data
        market_data = data_manager.get_comprehensive_market_data(symbol, use_demo=use_demo)

        if not market_data or market_data.get("data_status") == "ERROR":
            return {"signal": "HOLD", "reason": "Failed to fetch market data", "decision_id": decision_id, "timestamp": int(time.time())}

        # Get historical data with indicators for enhanced analysis
        historical_data = data_manager.get_historical_with_indicators(
            symbol,
            timeframes=["5m", "15m", "1h", "4h"],
            limit=200,
            use_demo=use_demo
        )

        # Extract technical analysis for different timeframes
        technical_analysis = market_data.get("technical_analysis", {})

        # 合并历史数据和当前数据
        enhanced_analysis = merge_historical_with_current(
            technical_analysis,
            historical_data.get("historical_analysis", {})
        )

        # Generate trading signal based on technical analysis
        parsed_signal = generate_fallback_signal_with_details(enhanced_analysis, market_data, symbol)

        if not parsed_signal:
            return {"signal": "HOLD", "reason": "Technical analysis failed", "decision_id": decision_id, "timestamp": int(time.time())}

        current_price = market_data.get("current_price", 0)

        # 如果当前价格为0，使用默认价格避免计算错误
        if current_price <= 0:
            current_price = 50000  # 默认BTC价格
            logger.warning(f"Current price is 0, using default price: {current_price}")

        # 应用风控优化
        try:
            optimized_signal = optimize_signal_with_risk(parsed_signal, enhanced_analysis, current_price)
            logger.info(f"Risk optimization applied successfully: volatility_adjusted=True")
        except Exception as e:
            logger.warning(f"Risk optimization failed, using original signal: {e}")
            optimized_signal = parsed_signal

        final_signal = {
            "signal": optimized_signal.get("side", optimized_signal.get("action", "HOLD")),
            "decision_id": decision_id,
            "confidence": optimized_signal.get("confidence"),
            "reason": optimized_signal.get("reasoning"),
            "position_size": optimized_signal.get("position_size", 0.02),  # 默认2%仓位
            "stop_loss": optimized_signal.get("stop_loss"),
            "take_profit": optimized_signal.get("take_profit"),
            "risk_assessment": optimized_signal.get("risk_assessment"),
            "parsed_response": optimized_signal,
            "market_data": market_data,
            "historical_data": historical_data,
            "enhanced_analysis": enhanced_analysis,
            "timestamp": int(time.time())
        }

        logger.info(f"Generated trading signal: {final_signal['signal']} for {symbol}")
        return final_signal

    except Exception as e:
        logger.error(f"Strategy loop error: {e}")
        return {"signal": "HOLD", "reason": f"Unexpected error: {str(e)}", "decision_id": decision_id if "decision_id" in locals() else "unknown", "timestamp": int(time.time())}

if __name__ == "__main__":
    import logging
    import os
    from src.data_manager.main import DataHandler

    # Configure comprehensive logging system
    try:
        from src.utils.logging_config import setup_logging
        setup_logging()
        logger = logging.getLogger(__name__)
        logger.info("Comprehensive logging system initialized successfully")
    except Exception as e:
        # Fallback to basic logging
        logging.basicConfig(
            level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to initialize comprehensive logging, using basic config: {e}")
    logger.info("Starting Strategy Engine...")

    # Initialize components with error handling
    try:
        logger.info("Initializing DataHandler...")
        data_handler = DataHandler()
        logger.info("DataHandler initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize DataHandler: {e}")
        raise

    # Test strategy generation
    try:
        signal = main_strategy_loop(data_manager=data_handler, symbol="BTC-USDT")
        logger.info(f"Generated test signal: {signal}")
    except Exception as e:
        logger.error(f"Strategy test failed: {e}", exc_info=True)
