import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

async def validate_order_signal(order_details: Dict[str, Any], current_equity: float, current_price: float = None) -> bool:
    """
    Validate order signal by calling risk manager directly

    Args:
        order_details: Dictionary containing order information
        current_equity: Current account equity
        current_price: Current market price (optional)

    Returns:
        bool: True if order is rational, False otherwise

    Raises:
        ValueError: If validation fails or order is not rational
    """
    try:
        # 导入risk manager模块
        from src.risk_manager import is_order_rational

        logger.info(f"Validating order: {order_details}")

        # 直接调用risk manager的检查函数
        is_rational = is_order_rational(
            order_details,
            current_equity,
            current_price
        )

        if is_rational:
            logger.info("Order validation passed")
            return True
        else:
            logger.error("Order validation failed")
            raise ValueError("Order validation failed: Order is not rational")

    except ImportError as e:
        logger.error(f"Failed to import risk_manager: {e}")
        raise ValueError(f"Risk manager not available: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in validate_order_signal: {e}")
        raise ValueError(f"Unexpected error in validate_order_signal: {e}")
