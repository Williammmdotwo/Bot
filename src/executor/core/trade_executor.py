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

        # 1. 获取仓位大小（策略提供或使用默认值）
        raw_amount = signal_data.get('position_size', None)

        # 如果策略没有提供 position_size，使用默认的小额交易量
        if raw_amount is None or raw_amount <= 0:
            # 向后兼容：使用默认的小额交易量
            estimated_price = 90000.0 if signal == "BUY" else 91000.0
            raw_amount = 0.001  # 默认值
            logger.warning(f"No valid position_size provided, using default: {raw_amount}")

        # 2. 精度处理 (必须!)
        # 从交易所获取 market 信息并进行精度截断
        try:
            # 确保 markets 已加载
            if not ccxt_exchange.markets:
                await ccxt_exchange.load_markets()

            market = ccxt_exchange.market(symbol)
            amount = ccxt_exchange.amount_to_precision(symbol, raw_amount)

            # 确保 amount 是数值类型
            if not isinstance(amount, (int, float)):
                logger.warning(f"amount_to_precision returned non-numeric type: {type(amount)}, using raw_amount")
                amount = raw_amount
            else:
                logger.info(f"Applied precision from exchange: {raw_amount} -> {amount}")
        except Exception as precision_error:
            # 降级处理：保留8位小数（适用于大多数加密货币）
            amount = round(raw_amount, 8)
            logger.warning(f"Failed to apply exchange precision: {precision_error}, using fallback precision: {raw_amount} -> {amount}")

        # 确保 amount 是 float 类型，避免序列化问题
        try:
            amount = float(amount)
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to convert amount to float: {amount}, error: {e}")
            amount = 0.0

        logger.info(f"Creating {signal} market order for {symbol}, amount: {amount} (raw: {raw_amount})")

        # 创建市价单
        order = ccxt_exchange.create_market_order(
            symbol=symbol,
            side=side,
            amount=amount
        )

        # 4. 安全的数据库记录 (防止 Crash)
        if postgres_pool:
            try:
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
                logger.info(f"Trade logged to database: {order['id']}")
            except Exception as db_error:
                logger.error(f"Failed to log trade to database: {db_error}")
                # 不中断交易流程，只记录错误
        else:
            logger.warning("Database pool not available, skipping trade log insertion")

        # 发布交易事件
        trade_message = {
            "event": "trade_executed",
            "symbol": symbol,
            "side": side,
            "order_id": order['id'],
            "amount": amount,
            "decision_id": decision_id
        }

        try:
            await redis_client.publish('trade_events', json.dumps(trade_message))
        except Exception as redis_error:
            logger.error(f"Failed to publish trade event to Redis: {redis_error}")
            # 不中断交易流程，只记录错误

        # 启动订单跟踪
        try:
            await track(order['id'], ccxt_exchange, postgres_pool)
        except Exception as track_error:
            logger.error(f"Failed to start order tracking: {track_error}")
            # 不中断交易流程，只记录错误

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
