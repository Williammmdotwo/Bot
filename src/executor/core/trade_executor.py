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

        # === 凭证检查修复 ===
        # 获取 API Key (兼容各种 ccxt 版本)
        api_key = getattr(ccxt_exchange, 'apiKey', None)

        # 检查是否应该使用模拟模式
        should_use_simulation = False

        # 1. 检查 mock 模式 (测试用)
        if hasattr(ccxt_exchange, 'mock_mode') and ccxt_exchange.mock_mode:
            should_use_simulation = True
            logger.warning("DemoCCXTExchange is in mock mode, using simulation")

        # 2. 检查 API Key 是否存在
        elif not api_key:
            should_use_simulation = True
            logger.warning(f"⚠️ No API credentials found in exchange object! (apiKey={api_key}) Using simulation.")

        if should_use_simulation:
            logger.info(f"Simulating {signal} trade for {symbol} (confidence: {confidence})")
            return {
                "status": "simulated",
                "order_id": f"demo_{decision_id}_{int(time.time())}",
                "symbol": symbol,
                "side": signal.lower(),
                "amount": signal_data.get('position_size', 0.0),
                "price": 90000.0 if signal == "BUY" else 91000.0,
                "message": f"Simulated {signal} order for {symbol}"
            }

        # === 真实交易执行 ===
        logger.info(f"🚀 Executing {signal} trade on OKX ({'Demo' if use_demo else 'Real'}) for {symbol}")
        side = signal.lower()

        # 1. 获取仓位大小
        raw_amount = signal_data.get('position_size', None)

        # 向后兼容默认值
        if raw_amount is None or raw_amount <= 0:
            raw_amount = 0.001
            logger.warning(f"No valid position_size provided, using default: {raw_amount}")

        # 2. 精度处理 (注意：这里不能用 await，因为 rest_client 初始化的是同步 ccxt)
        try:
            # 确保 markets 已加载
            if not ccxt_exchange.markets:
                logger.info("Loading markets for precision info...")
                ccxt_exchange.load_markets() # 同步调用，无 await

            # market = ccxt_exchange.market(symbol) # 可选检查
            amount = ccxt_exchange.amount_to_precision(symbol, raw_amount)

            # 确保 amount 是数值类型
            if not isinstance(amount, (int, float)):
                try:
                    amount = float(amount)
                except:
                    logger.warning(f"amount_to_precision returned non-numeric: {amount}")
                    amount = float(raw_amount)

            logger.info(f"Precision applied: {raw_amount} -> {amount}")

        except Exception as precision_error:
            amount = float(raw_amount)
            logger.warning(f"Precision handling failed ({precision_error}), using raw amount: {amount}")

        logger.info(f"Creating {signal.upper()} Market Order: {symbol} x {amount}")

        # 3. 创建市价单 (同步调用，无 await)
        # 注意：这里调用的是 RESTClient.signer，我们已经给它打过 URL 补丁了
        order = ccxt_exchange.create_market_order(
            symbol=symbol,
            side=side,
            amount=amount
        )

        logger.info(f"✅ Order Placed! ID: {order['id']}")

        # 4. 数据库记录
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
                # execute 是 asyncpg 的方法，需要 await
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
            except Exception as db_error:
                logger.error(f"Failed to log trade to database: {db_error}")
        else:
            logger.warning("Database pool not available, skipping log")

        # 5. Redis 事件
        if redis_client:
            trade_message = {
                "event": "trade_executed",
                "symbol": symbol,
                "side": side,
                "order_id": order['id'],
                "amount": amount,
                "decision_id": decision_id
            }
            try:
                # publish 是 redis 的方法，需要 await
                await redis_client.publish('trade_events', json.dumps(trade_message))
            except Exception as redis_error:
                logger.error(f"Failed to publish to Redis: {redis_error}")

        # 6. 订单跟踪
        try:
            await track(order['id'], ccxt_exchange, postgres_pool)
        except Exception as track_error:
            logger.error(f"Failed to start order tracking: {track_error}")

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
