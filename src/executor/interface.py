"""
Executor模块对外接口
提供Python函数调用接口，替代FastAPI
"""
import logging
from typing import Dict, Any, Optional
from .core.trade_executor import execute_trade_logic
from .core.position_manager import execute_force_close, check_position_exists, get_position_size
from .validation import validate_order_signal

logger = logging.getLogger(__name__)

# 全局依赖实例（通过初始化函数注入）
_ccxt_exchange = None
_postgres_pool = None
_redis_client = None


def initialize_dependencies(ccxt_exchange, postgres_pool, redis_client):
    """初始化全局依赖实例"""
    global _ccxt_exchange, _postgres_pool, _redis_client
    _ccxt_exchange = ccxt_exchange
    _postgres_pool = postgres_pool
    _redis_client = redis_client
    logger.info("Executor dependencies initialized")


async def execute_trade(
    signal_data: Dict[str, Any],
    use_demo: bool = True,
    stop_loss_pct: float = 0.03,
    take_profit_pct: float = 0.06
) -> Dict[str, Any]:
    """
    执行交易（替代 /api/execute-trade 接口）

    Args:
        signal_data: 交易信号数据
        use_demo: 是否使用模拟交易
        stop_loss_pct: 止损百分比
        take_profit_pct: 止盈百分比

    Returns:
        dict: 执行结果
        {
            "status": "executed" | "simulated" | "failed" | "ignored",
            "order_id": str | None,
            "symbol": str,
            "side": str,
            "amount": float,
            "price": float | None,
            "message": str
        }
    """
    try:
        logger.info(f"Executing trade: {signal_data}")

        # 调用核心逻辑
        result = await execute_trade_logic(
            signal_data,
            use_demo,
            stop_loss_pct,
            take_profit_pct,
            _ccxt_exchange,
            _postgres_pool,
            _redis_client
        )

        logger.info(f"Trade execution result: {result}")
        return result

    except Exception as e:
        logger.error(f"Trade execution failed: {e}")
        return {
            "status": "failed",
            "message": f"Trade execution failed: {str(e)}",
            "symbol": signal_data.get('symbol', 'UNKNOWN'),
            "side": signal_data.get('signal', 'UNKNOWN').lower()
        }


async def force_close_position(
    symbol: str,
    side: str
) -> Dict[str, Any]:
    """
    强制平仓（替代 /api/force-close 接口）

    Args:
        symbol: 交易对符号
        side: 持仓方向 ('buy' or 'sell')

    Returns:
        dict: 平仓结果
    """
    try:
        logger.info(f"Force close request: {symbol} {side}")

        # 1. 检查持仓是否存在
        if not await check_position_exists(symbol, side, _postgres_pool):
            logger.warning(f"No position found for {symbol} {side}")
            return {
                "status": "failed",
                "message": "No position found for forced close",
                "symbol": symbol,
                "side": side
            }

        # 2. 获取持仓数量
        position_size = await get_position_size(symbol, side, _postgres_pool)
        if position_size <= 0:
            logger.warning(f"No position size to close for {symbol} {side}")
            return {
                "status": "failed",
                "message": "No position size to close",
                "symbol": symbol,
                "side": side
            }

        # 3. 执行平仓逻辑
        result = await execute_force_close(
            symbol, side, position_size,
            _ccxt_exchange, _postgres_pool, _redis_client
        )

        logger.info(f"Force close result: {result}")
        return {
            "status": "success",
            "message": "Position closed successfully",
            "data": result
        }

    except Exception as e:
        logger.error(f"Force close failed: {e}")
        return {
            "status": "failed",
            "message": f"Force close failed: {str(e)}",
            "symbol": symbol,
            "side": side
        }


def health_check() -> Dict[str, str]:
    """
    健康检查（替代 /api/health 接口）

    Returns:
        dict: 健康状态
    """
    return {
        "status": "healthy",
        "service": "executor"
    }
