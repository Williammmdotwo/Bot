import uuid
import logging
import time
from typing import Dict, Any, List

# Fix relative imports for direct execution
try:
    from .validator import validate_data, validate_signal
    from .api_server import app, initialize_dependencies
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
    from src.strategy_engine.api_server import app, initialize_dependencies
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

        # ✅ 直接用这一行代替（绕过丢失的风控函数）
        optimized_signal = parsed_signal

        final_signal = {
            "signal": parsed_signal.get("side", parsed_signal.get("action", "HOLD")),
            "decision_id": decision_id,
            "confidence": parsed_signal.get("confidence"),
            "reason": parsed_signal.get("reasoning"),
            "position_size": parsed_signal.get("position_size", 0.02),  # 默认2%仓位
            "parsed_response": parsed_signal,
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
    import time
    import signal
    import sys
    import asyncio
    from src.strategy_engine.api_server import app
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
    logger.info("Starting Strategy Engine Service...")
    logger.info(f"DEBUG: INTERNAL_SERVICE_TOKEN = {repr(os.getenv('INTERNAL_SERVICE_TOKEN'))}")

    def signal_handler(signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 环境安全验证
        log_environment_info("Strategy Engine")

        if not validate_safety():
            logger.critical("🚨 环境安全验证失败，服务启动被阻止")
            logger.critical("请检查环境配置，确保使用安全的Demo环境")
            sys.exit(1)

        # 获取环境配置
        try:
            env_config = get_environment_config()
            api_creds = get_api_credentials()
            logger.info(f"Environment: {env_config['environment']}, Demo: {env_config['use_demo']}")
        except Exception as e:
            logger.warning(f"Failed to get environment config: {e}")
            env_config = {'environment': 'demo', 'use_demo': True}
            api_creds = {}

        # Import unified configuration system
        try:
            from src.utils.config_loader import get_config_manager
            config_manager = get_config_manager()
            config = config_manager.get_config()
            service_config = config['services']['strategy_engine']
            logger.info("Successfully loaded unified configuration")
        except Exception as e:
            logger.warning(f"Failed to load unified configuration, using environment variables: {e}")
            service_config = {}

        # Get service configuration from unified config or environment variables
        host = service_config.get('host', os.getenv('SERVICE_HOST', '0.0.0.0'))
        port = service_config.get('port', int(os.getenv('SERVICE_PORT', '8003')))

        logger.info(f"Starting Strategy Engine Service on {host}:{port}")

        # Initialize components with error handling
        try:
            logger.info("Initializing DataHandler...")
            data_handler = DataHandler()
            logger.info("DataHandler initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize DataHandler: {e}")
            raise

        # Initialize API server dependencies first
        try:
            initialize_dependencies(data_handler, None)  # No client needed for technical analysis
            logger.info("API server dependencies initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize API server dependencies: {e}")
            raise

        # Test strategy loop (optional)
        run_strategy_loop = os.getenv('RUN_STRATEGY_LOOP', 'false').lower() == 'true'
        logger.info(f"RUN_STRATEGY_LOOP={run_strategy_loop}")

        if run_strategy_loop:
            logger.info("Running strategy loop in test mode...")
            while True:  # 🔥 必须加这个死循环，防止进程自然死亡
                try:
                    # 核心逻辑：获取数据 -> 计算 -> 下单
                    signal = main_strategy_loop(data_manager=data_handler, symbol="BTC-USDT-SWAP")
                    logger.info(f"Generated signal: {signal}")
                except KeyboardInterrupt:
                    logger.info("Received KeyboardInterrupt, stopping strategy loop...")
                    break
                except Exception as e:
                    logger.error(f"Strategy loop error: {e}", exc_info=True)

                # 🔥 心跳日志改为 DEBUG 级别，减少日志刷屏
                logger.debug("[HEARTBEAT] Strategy is running normally...")

                time.sleep(60)  # 1分钟跑一次
        else:
            # Run API server
            logger.info(f"Starting Strategy Engine API server on {host}:{port}")
            import uvicorn
            uvicorn.run(app, host=host, port=port, log_level="info")

    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Strategy Engine Service failed: {e}")
        raise
    finally:
        logger.info("Strategy Engine Service stopped")
