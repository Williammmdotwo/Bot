import json
import logging
import os
import uvicorn
from typing import Dict, Any

# Fix relative imports for direct execution
try:
    from .validator import validate_order_signal
    from .tracker import track
    from .api_server import app, initialize_dependencies
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
    from src.executor.validator import validate_order_signal
    from src.executor.tracker import track
    from src.executor.api_server import app, initialize_dependencies

from src.data_manager.main import DataHandler

logger = logging.getLogger(__name__)

async def execute_order(signal: Dict[str, Any], ccxt_exchange, postgres_pool, redis_client):
    """
    Execute a trading order based on the provided signal
    
    Args:
        signal: Dictionary containing order signal information
        ccxt_exchange: CCXT exchange instance
        postgres_pool: PostgreSQL connection pool (asyncpg)
        redis_client: Redis client (redis.asyncio.Redis)
        
    Returns:
        dict: Order information from exchange
        
    Raises:
        ValueError: If order validation fails
        Exception: For other execution errors
    """
    try:
        logger.info(f"Starting order execution for signal: {signal}")
        
        # 安全检查：验证当前运行环境
        okx_environment = os.getenv("OKX_ENVIRONMENT", "production").lower()
        use_demo = okx_environment in ["demo", "demo环境", "demo-trading"]
        
        if not use_demo:
            logger.critical(f"🚨 安全阻止: 拒绝在非模拟环境下执行交易订单")
            logger.critical(f"当前环境: {okx_environment}, 要求: demo环境")
            raise ValueError("Trading only allowed in demo environment for safety")
        
        logger.info(f"✅ 环境安全检查通过: {okx_environment} (模拟模式: {use_demo})")
        
        # 1. Get market snapshot and account equity
        logger.info("Fetching market snapshot and account data")
        use_database = os.getenv('USE_DATABASE', 'false').lower() == 'true'
        
        if use_database:
            data_handler = DataHandler()
            snapshot = data_handler.get_snapshot(signal['symbol'])
        else:
            # Fallback when database is disabled
            snapshot = {
                "symbol": signal['symbol'],
                "klines": [],
                "indicators": {},
                "account": {"balance": {}, "positions": []},
                "data_status": "DEGRADED"
            }
            logger.info("Database disabled, using minimal snapshot")
        
        # 2. Validate order signal
        logger.info("Validating order signal")
        try:
            validate_order_signal(signal, snapshot)
            logger.info("Order validation passed")
        except ValueError as e:
            logger.error(f"Order validation failed: {e}")
            raise
        
        # 3. Create market order
        logger.info(f"Creating market order: {signal['action']} {signal['size']} {signal['symbol']}")
        try:
            order = ccxt_exchange.create_market_order(
                symbol=signal['symbol'],
                side=signal['action'].lower(),  # 'buy' or 'sell'
                amount=signal['size']
            )
            logger.info(f"Order created successfully: {order['id']}")
        except Exception as e:
            logger.error(f"Failed to create market order: {e}")
            raise
        
        # 4. Insert initial order information into trades table
        if postgres_pool:
            logger.info("Inserting order into database")
            try:
                insert_sql = """
                INSERT INTO trades (decision_id, order_id, symbol, side, order_type, amount, price, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                """
                await postgres_pool.execute(
                    insert_sql, 
                    signal.get('decision_id'), 
                    order['id'], 
                    signal['symbol'],
                    signal['side'], 
                    'market', 
                    signal['size'], 
                    None, 
                    'open'
                )
                logger.info(f"Order {order['id']} inserted into trades table")
            except Exception as e:
                logger.error(f"Failed to insert order into database: {e}")
                # Continue without database insertion
        else:
            logger.info("Database disabled, skipping order insertion")
        
        # 5. Publish new position opened message to Redis
        logger.info("Publishing position opened message to Redis")
        try:
            message = {
                'symbol': signal['symbol'], 
                'order_id': order['id']
            }
            await redis_client.publish('new_position_opened', json.dumps(message))
            logger.info(f"Published message to Redis: {message}")
        except Exception as e:
            logger.error(f"Failed to publish message to Redis: {e}")
            # Continue with tracking even if Redis publish fails
        
        # 6. Start order tracking
        logger.info("Starting order tracking")
        try:
            tracking_task = await track(order['id'], ccxt_exchange, postgres_pool)
            logger.info(f"Order tracking started for {order['id']}")
        except Exception as e:
            logger.error(f"Failed to start order tracking: {e}")
            # Continue even if tracking fails, as order is already placed
        
        logger.info(f"Order execution completed successfully for {order['id']}")
        return order
        
    except ValueError as e:
        logger.error(f"Order execution failed due to validation error: {e}")
        raise
    except Exception as e:
        logger.error(f"Order execution failed with unexpected error: {e}")
        raise


if __name__ == "__main__":
    import logging
    import os
    import time
    import signal
    import sys
    import asyncio
    import uvicorn
    
    # Fix relative imports for direct execution
    try:
        from .api_server import app, initialize_dependencies
    except ImportError:
        from src.executor.api_server import app, initialize_dependencies
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Starting Executor Service...")
    
    def signal_handler(signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Import unified configuration system
        try:
            from src.utils.config_loader import get_config_manager
            config_manager = get_config_manager()
            config = config_manager.get_config()
            service_config = config['services']['executor']
            logger.info("Successfully loaded unified configuration")
        except Exception as e:
            logger.warning(f"Failed to load unified configuration, using environment variables: {e}")
            service_config = {}
        
        # Get service configuration from unified config or environment variables
        host = service_config.get('host', os.getenv('SERVICE_HOST', '0.0.0.0'))
        port = service_config.get('port', int(os.getenv('SERVICE_PORT', '8002')))
        
        logger.info(f"Starting Executor Service on {host}:{port}")
        
        # Initialize real DemoCCXTExchange for testing
        # Import the real DemoCCXTExchange from api_server
        try:
            from .api_server import DemoCCXTExchange
        except ImportError:
            from src.executor.api_server import DemoCCXTExchange
        
        class MockPostgresPool:
            async def execute(self, query, *args):
                return None
            async def fetch(self, query, *args):
                return None
            async def fetchrow(self, query, *args):
                return None
        
        class MockRedisClient:
            async def publish(self, channel, message):
                return None
        
        initialize_dependencies(DemoCCXTExchange(), MockPostgresPool(), MockRedisClient())
        
        # Run API server
        import uvicorn
        uvicorn.run(app, host=host, port=port, log_level="info")
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Executor Service failed: {e}")
        raise
    finally:
        logger.info("Executor Service stopped")
