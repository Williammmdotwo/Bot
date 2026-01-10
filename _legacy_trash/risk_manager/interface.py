"""
Risk Manager模块对外接口
提供Python函数调用接口，替代FastAPI
"""
import logging
from typing import Dict, Any, Optional
from .checks import is_order_rational
from .actions import emergency_close_position

logger = logging.getLogger(__name__)


async def check_order(
    order_details: Dict[str, Any],
    current_equity: float,
    current_price: Optional[float] = None
) -> Dict[str, Any]:
    """
    检查订单是否合理（替代 /api/check-order 接口）

    Args:
        order_details: 订单详情
        current_equity: 当前账户权益
        current_price: 当前市价（可选）

    Returns:
        dict: 检查结果
        {
            "is_rational": bool,
            "error": str | None
        }
    """
    try:
        logger.info(f"Checking order: {order_details}")

        is_rational = is_order_rational(
            order_details,
            current_equity,
            current_price
        )

        if is_rational:
            logger.info("Order is rational")
            return {
                "is_rational": True,
                "error": None
            }
        else:
            logger.warning("Order is not rational")
            return {
                "is_rational": False,
                "error": "Order validation failed"
            }

    except Exception as e:
        logger.error(f"Order check failed: {e}")
        return {
            "is_rational": False,
            "error": str(e)
        }


async def trigger_emergency_close(
    symbol: str,
    side: str,
    postgres_pool
) -> Dict[str, Any]:
    """
    触发紧急平仓（替代 /api/emergency-close 接口）

    Args:
        symbol: 交易对符号
        side: 持仓方向
        postgres_pool: PostgreSQL连接池

    Returns:
        dict: 平仓结果
    """
    try:
        logger.critical(f"Emergency close triggered: {symbol} {side}")

        success = await emergency_close_position(
            symbol, side, postgres_pool
        )

        if success:
            return {
                "status": "success",
                "message": "Emergency close completed",
                "symbol": symbol,
                "side": side
            }
        else:
            return {
                "status": "failed",
                "message": "Emergency close failed",
                "symbol": symbol,
                "side": side
            }

    except Exception as e:
        logger.error(f"Emergency close failed: {e}")
        return {
            "status": "failed",
            "message": str(e),
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
        "service": "risk_manager"
    }
