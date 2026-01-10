import asyncio
import logging
import inspect
from typing import Any

logger = logging.getLogger(__name__)

def _is_coroutine_function(func):
    """检查是否为协程函数，兼容Python 3.14+"""
    try:
        return inspect.iscoroutinefunction(func)
    except AttributeError:
        # Python 3.14+ 中 asyncio.iscoroutinefunction 被弃用
        return hasattr(func, '__code__') and asyncio.iscoroutinefunction(func)

async def _order_tracking_loop(order_id: str, ccxt_exchange: Any, postgres_pool: Any):
    """
    Internal coroutine to track order status
    """

    while True:
        try:
            # Fetch order status from exchange
            order_info = await ccxt_exchange.fetch_order(order_id)
            order_status = order_info.get("status")

            logger.info(f"Order {order_id} status: {order_status}")

            # Update database with new status and filled information
            try:
                # Extract filled information from order
                filled_amount = order_info.get("filled", 0)
                filled_price = order_info.get("price", 0) if order_info.get("price") else 0
                fee = order_info.get("fee", {})
                fee_cost = fee.get("cost", 0) if fee else 0

                # Use specified UPDATE statement
                update_sql = """
                UPDATE trades
                SET filled_amount = $1, filled_price = $2, fee = $3, status = $4, updated_at = NOW()
                WHERE order_id = $5
                """

                await postgres_pool.execute(
                    update_sql, filled_amount, filled_price, fee_cost, order_status, order_id
                )

                logger.info(f"Updated order {order_id} in database. Status: {order_status}, Filled: {filled_amount}, Price: {filled_price}, Fee: {fee_cost}")

            except Exception as db_error:
                logger.error(f"Database error updating order {order_id}: {db_error}")
                # Continue with tracking even if DB update fails

            # Check if order is finished
            if order_status in ['closed', 'canceled']:
                logger.info(f"Order {order_id} finished with status: {order_status}")
                break

            # Wait 5 seconds before next poll
            await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Error tracking order {order_id}: {e}")
            await asyncio.sleep(5)

async def track(order_id: str, ccxt_exchange, postgres_pool):
    """
    Create a background task to track order status

    Args:
        order_id: The order ID to track
        ccxt_exchange: CCXT exchange instance
        postgres_pool: PostgreSQL connection pool

    Returns:
        asyncio.Task: The background tracking task
    """
    logger.info(f"Starting background tracking for order {order_id}")

    # Create background task
    task = asyncio.create_task(_order_tracking_loop(order_id, ccxt_exchange, postgres_pool))

    return task
