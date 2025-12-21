import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def validate_data(snapshot: Dict[str, Any]) -> bool:
    """Validate snapshot data completeness and format"""
    try:
        required_fields = ["klines", "indicators", "account", "symbol"]
        for field in required_fields:
            if field not in snapshot or snapshot[field] is None:
                logger.error(f"Missing required field: {field}")
                return False
        return True
    except Exception as e:
        logger.error(f"Error during data validation: {e}")
        return False

def validate_signal(signal: Dict[str, Any], current_price: float) -> bool:
    """Validate trading signal for safety and logic with enhanced field support"""
    try:
        # Support both "side" and "action" fields for flexibility
        side_field = signal.get("side") or signal.get("action")
        if not side_field:
            logger.error("Signal missing both 'side' and 'action' fields")
            return False
        
        # Validate side field value
        if side_field not in ["BUY", "SELL", "HOLD"]:
            logger.error(f"Invalid side/action value: {side_field}")
            return False
        
        required_signal_fields = ["position_size", "stop_loss", "take_profit"]
        for field in required_signal_fields:
            if field not in signal or signal[field] is None:
                logger.error(f"Signal missing required field: {field}")
                return False
        
        # Additional validation for price reasonableness
        stop_loss = float(signal.get("stop_loss", 0))
        take_profit = float(signal.get("take_profit", 0))
        
        if stop_loss <= 0 or take_profit <= 0:
            logger.error(f"Invalid price values: stop_loss={stop_loss}, take_profit={take_profit}")
            return False
        
        # Validate price ranges (basic sanity check)
        if current_price > 0:
            sl_distance_pct = abs(current_price - stop_loss) / current_price * 100
            tp_distance_pct = abs(take_profit - current_price) / current_price * 100
            
            if sl_distance_pct > 20:  # More than 20% stop loss
                logger.warning(f"Very large stop loss distance: {sl_distance_pct:.2f}%")
            if tp_distance_pct > 50:  # More than 50% take profit
                logger.warning(f"Very large take profit distance: {tp_distance_pct:.2f}%")
        
        logger.info(f"Signal validation passed: side={side_field}, position_size={signal.get('position_size')}")
        return True
    except Exception as e:
        logger.error(f"Error during signal validation: {e}")
        return False
