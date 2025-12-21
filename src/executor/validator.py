import os
import requests
import json
import logging
from typing import Dict, Any

# 导入配置管理器函数
try:
    from src.utils.config_loader import get_config_manager
except ImportError:
    get_config_manager = None

logger = logging.getLogger(__name__)

def validate_order_signal(order_details: Dict[str, Any], snapshot: Dict[str, Any]) -> bool:
    """
    Validate order signal by calling risk-service API
    
    Args:
        order_details: Dictionary containing order information
        snapshot: Dictionary containing market snapshot
    
    Returns:
        bool: True if order is rational, False otherwise
    
    Raises:
        ValueError: If network error, parsing error, or is_rational is False
    """
    
    # 从配置管理器获取风险服务URL
    try:
        from src.utils.config_loader import get_config_manager
        config_manager = get_config_manager()
        config = config_manager.get_config()
        risk_config = config['services']['risk_manager']
        risk_service_url = f"http://{risk_config['host']}:{risk_config['port']}/api/check-order"
    except Exception:
        # 回退到环境变量或默认值
        risk_host = os.getenv('RISK_SERVICE_HOST', 'risk-service')
        risk_port = os.getenv('RISK_SERVICE_PORT', '8001')
        risk_service_url = f"http://{risk_host}:{risk_port}/api/check-order"
    
    try:
        logger.info(f"Sending order validation request to risk-service: {order_details}")
        
        # Send POST request to risk-service
        response = requests.post(
            risk_service_url,
            json={"order_details": order_details},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        # Check if request was successful
        response.raise_for_status()
        
        # Parse response JSON
        response_data = response.json()
        
        # Check if order is rational
        is_rational = response_data.get("is_rational", False)
        
        if is_rational:
            logger.info(f"Order validation passed: {is_rational}")
            return True
        else:
            error_msg = response_data.get("error", "Order is not rational")
            logger.error(f"Order validation failed: {error_msg}")
            raise ValueError(f"Order validation failed: {error_msg}")
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error calling risk-service: {e}")
        raise ValueError(f"Network error calling risk-service: {e}")
    
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error from risk-service: {e}")
        raise ValueError(f"JSON parsing error from risk-service: {e}")
    
    except Exception as e:
        logger.error(f"Unexpected error in validate_order_signal: {e}")
        raise ValueError(f"Unexpected error in validate_order_signal: {e}")
