import logging
import time
import json
from typing import Any

from ..tracking import track

logger = logging.getLogger(__name__)


async def execute_trade_logic(
    signal_data: dict,
    use_demo: bool,
    stop_loss_pct: float,
    take_profit_pct: float,
    ccxt_exchange: Any,
    postgres_pool: Any,
    redis_client: Any
) -> dict:
    """执行交易的核心逻辑"""
    try:
        # 提取信号信息
        signal = signal_data.get('signal', 'HOLD')
        symbol = signal_data.get('symbol', 'BTC-USDT')
        confidence = signal_data.get('confidence', 0.0)
        decision_id = signal_data.get('decision_id', '')

        if signal not in ['BUY', 'SELL']:
            return {
                "status": "ignored",
                "order_id": None,
                "symbol": symbol,
                "side": signal.lower(),
                "amount": 0.0,
                "price": None,
                "message": f"Signal {signal} is not a trading signal"
            }

        # 检查是否应该使用模拟模式
        should_use_simulation = False

        # 如果ccxt_exchange是DemoCCXTExchange且处于mock模式，则使用模拟
        if hasattr(ccxt_exchange, 'mock_mode') and ccxt_exchange.mock_mode:
            should_use_simulation = True
            logger.warning("DemoCCXTExchange is in mock mode, using simulation")

        # 如果是普通ccxt实例但没有API密钥，也使用模拟
        elif not hasattr(ccxt_exchange, 'mock_mode') and not hasattr(ccxt_exchange, 'apiKey'):
            should_use_simulation = True
            logger.warning("No API credentials available, using simulation")

        if should_use_simulation:
            logger.info(f"Simulating {signal} trade for {symbol} (confidence: {confidence})")
            return {
                "status": "simulated",
                "order_id": f"demo_{decision_id}_{int(time.time())}",
                "symbol": symbol,
                "side": signal.lower(),
                "amount": 100.0,
                "price": 90000.0 if signal == "BUY" else 91000.0,
                "message": f"Simulated {signal} order for {symbol}"
            }

        # 真实交易执行（Demo或Production）
        logger.info(f"Executing {signal} trade in {'Demo' if use_demo else 'Production'} mode for {symbol} (confidence: {confidence})")
        side = signal.lower()

        # 动态计算交易数量，确保订单金额不超过100万USDT
        # 获取当前价格（简化处理，使用固定估算价格）
        estimated_price = 90000.0 if signal == "BUY" else 91000.0
        max_amount = 1000000.0 / estimated_price  # 100万USDT限制
        amount = min(0.001, max_amount)  # 使用较小值，约90-91 USDT

        logger.info(f"Creating {signal} market order for {symbol}, amount: {amount} (estimated value: {amount * estimated_price:.2f} USDT)")

        # 创建市价单
        order = ccxt_exchange.create_market_order(
            symbol=symbol,
            side=side,
            amount=amount
        )

        # 记录到数据库
        insert_sql = """
        INSERT INTO trades (
            decision_id, order_id, symbol, side, order_type, amount, price,
            status, reason, created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, NOW()
        )
        """

        await postgres_pool.execute(
            insert_sql,
            decision_id,
            order['id'],
            symbol,
            side,
            'market',
            amount,
            order.get('price', 0),
            order.get('status', 'open'),
            f'TRADE_SIGNAL_{signal}'
        )

        # 发布交易事件
        trade_message = {
            "event": "trade_executed",
            "symbol": symbol,
            "side": side,
            "order_id": order['id'],
            "amount": amount,
            "decision_id": decision_id
        }

        await redis_client.publish('trade_events', json.dumps(trade_message))

        # 启动订单跟踪
        await track(order['id'], ccxt_exchange, postgres_pool)

        return {
            "status": "executed",
            "order_id": order['id'],
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": order.get('price'),
            "message": f"Successfully executed {signal} order for {symbol}"
        }

    except Exception as e:
        logger.error(f"Error executing trade: {e}")
        return {
            "status": "failed",
            "message": f"Trade execution failed: {str(e)}",
            "symbol": signal_data.get('symbol', 'UNKNOWN'),
            "side": signal_data.get('signal', 'UNKNOWN').lower()
        }
