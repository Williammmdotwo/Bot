import logging
import json
from typing import Any

from ..tracking import track

logger = logging.getLogger(__name__)


async def check_position_exists(symbol: str, side: str, postgres_pool: Any) -> bool:
    """检查指定 symbol 和 side 是否有持仓"""
    try:
        query = """
        SELECT order_id, amount, filled_amount
        FROM trades
        WHERE symbol = $1 AND side = $2 AND status = 'open'
        """
        result = await postgres_pool.fetch(query, symbol, side)
        return len(result) > 0
    except Exception as e:
        logger.error(f"Error checking position existence: {e}")
        raise


async def get_position_size(symbol: str, side: str, postgres_pool: Any) -> float:
    """获取当前持仓数量"""
    try:
        query = """
        SELECT COALESCE(SUM(filled_amount), 0) as total_filled
        FROM trades
        WHERE symbol = $1 AND side = $2 AND status = 'open'
        """
        result = await postgres_pool.fetchrow(query, symbol, side)
        return float(result['total_filled']) if result and result['total_filled'] else 0.0
    except Exception as e:
        logger.error(f"Error getting position size: {e}")
        raise


async def execute_force_close(
    symbol: str,
    side: str,
    position_size: float,
    ccxt_exchange: Any,
    postgres_pool: Any,
    redis_client: Any
) -> dict:
    """执行强制平仓的核心逻辑"""
    try:
        logger.info(f"Executing force close for {symbol} {side} position, size: {position_size}")

        # 1. 创建平仓订单（反向方向）
        close_side = 'sell' if side == 'buy' else 'buy'
        logger.info(f"Creating {close_side} market order for {symbol}, amount: {position_size}")

        close_order = ccxt_exchange.create_market_order(
            symbol=symbol,
            side=close_side,
            amount=position_size
        )

        logger.info(f"Close order created: {close_order['id']}")

        # 2. 更新原始开仓记录
        logger.info("Updating original position records")
        update_original_sql = """
        UPDATE trades
        SET status = 'closed',
            filled_amount = $1,
            filled_price = $2,
            fee = $3,
            updated_at = NOW()
        WHERE symbol = $4 AND side = $5 AND status = 'open'
        """

        await postgres_pool.execute(
            update_original_sql,
            close_order.get('filled', 0),
            close_order.get('price', 0),
            close_order.get('fee', {}).get('cost', 0) if close_order.get('fee') else 0,
            symbol,
            side
        )

        # 3. 插入平仓记录
        logger.info("Inserting close position record")
        insert_close_sql = """
        INSERT INTO trades (
            decision_id, order_id, symbol, side, order_type, amount, price,
            status, reason, filled_amount, filled_price, fee, created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW()
        )
        """

        await postgres_pool.execute(
            insert_close_sql,
            None,  # decision_id for close orders
            close_order['id'],
            symbol,
            close_side,
            'market',
            position_size,
            close_order.get('price', 0),
            close_order.get('status', 'open'),
            'FORCED_CLOSE',
            close_order.get('filled', 0),
            close_order.get('price', 0),
            close_order.get('fee', {}).get('cost', 0) if close_order.get('fee') else 0
        )

        # 4. 发布消息通知
        logger.info("Publishing position close message")
        close_message = {
            "event": "position_closed",
            "symbol": symbol,
            "reason": "RISK_STOP_LOSS",
            "order_id": close_order['id']
        }

        await redis_client.publish('position_events', json.dumps(close_message))

        # 5. 启动订单跟踪
        logger.info("Starting order tracking for close order")
        await track(close_order['id'], ccxt_exchange, postgres_pool)

        return {
            "close_order_id": close_order['id'],
            "symbol": symbol,
            "side": side,
            "close_side": close_side,
            "position_size": position_size,
            "status": close_order.get('status', 'open')
        }

    except Exception as e:
        logger.error(f"Error executing force close: {e}")
        raise
