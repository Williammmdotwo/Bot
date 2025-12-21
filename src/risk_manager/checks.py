import logging
from typing import Dict, Any
from pydantic import BaseModel, field_validator, Field
from .config import get_config, Config

logger = logging.getLogger(__name__)


class OrderDetails(BaseModel):
    """订单详情模型，用于验证必填字段"""
    symbol: str = Field(..., description="交易对符号")
    side: str = Field(..., description="买卖方向")
    position_size: float = Field(..., gt=0, description="仓位大小(USDT计价)")
    stop_loss: float = Field(..., description="止损价格")
    take_profit: float = Field(..., description="止盈价格")
    
    @field_validator('side')
    def side_must_be_valid(cls, v):
        if v.lower() not in ['buy', 'sell']:
            raise ValueError('side必须是buy或sell')
        return v.lower()
    
    @field_validator('stop_loss', 'take_profit')
    def prices_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('价格必须为正数')
        return v


def is_order_rational(order_details: Dict[str, Any], current_equity: float, current_price: float = None, config: Config = None) -> bool:
    """
    检查订单是否合理
    
    Args:
        order_details: 订单详情字典
        current_equity: 当前账户权益
        current_price: 当前市价（可选）
        config: 风控配置对象，如果为None则使用全局配置
        
    Returns:
        bool: True表示订单合理，False表示不合理
    """
    try:
        # 使用全局配置如果没有传入config
        if config is None:
            config = get_config()
        
        # 验证订单详情字段
        try:
            order = OrderDetails(**order_details)
        except Exception as e:
            logger.critical(f"订单详情验证失败: {e}, 订单数据: {order_details}")
            return False
        
        # 1. 单笔仓位检查
        position_ratio = order.position_size / current_equity
        max_position_ratio = config.risk_limits.max_single_order_size_percent
        
        if position_ratio > max_position_ratio:
            logger.critical(
                f"单笔仓位超限: {position_ratio:.4f} > {max_position_ratio:.4f}, "
                f"订单金额: {order.position_size}, 当前权益: {current_equity}"
            )
            return False
        
        # 2. 止损止盈价格逻辑检查（传入当前价格）
        if not _validate_stop_take_profit_logic(order, current_price):
            logger.critical(
                f"止损止盈价格逻辑不合理: "
                f"side={order.side}, stop_loss={order.stop_loss}, take_profit={order.take_profit}, current_price={current_price}"
            )
            return False
        
        # 所有检查通过
        logger.info(
            f"订单合理性检查通过: symbol={order.symbol}, side={order.side}, "
            f"position_size={order.position_size}, position_ratio={position_ratio:.4f}"
        )
        
        return True
        
    except Exception as e:
        logger.critical(f"订单合理性检查异常: {e}, 订单数据: {order_details}")
        return False


def _validate_stop_take_profit_logic(order: OrderDetails, current_price: float = None) -> bool:
    """
    验证止损止盈价格逻辑是否合理
    
    Args:
        order: 订单详情对象
        current_price: 当前市价（可选，用于更精确验证）
        
    Returns:
        bool: True表示逻辑合理，False表示不合理
    """
    try:
        if order.side == 'buy':
            # 买单逻辑：止损 < 止盈，且当前价格在合理范围内
            if order.stop_loss >= order.take_profit:
                logger.warning(f"买单止损止盈价格关系异常: stop_loss({order.stop_loss}) >= take_profit({order.take_profit})")
                return False
            
            # 如果有当前价格，验证价格位置合理性
            if current_price:
                # 理想情况：止损 < 当前价格 < 止盈
                # 但允许一定容差，因为价格可能快速移动
                if not (order.stop_loss * 0.999 <= current_price <= order.take_profit * 1.001):
                    logger.info(f"买单价格位置检查: stop_loss={order.stop_loss}, current_price={current_price}, take_profit={order.take_profit}")
                    
        else:  # sell
            # 卖单逻辑：止损 > 止盈，且当前价格在合理范围内
            if order.stop_loss <= order.take_profit:
                logger.warning(f"卖单止损止盈价格关系异常: stop_loss({order.stop_loss}) <= take_profit({order.take_profit})")
                return False
            
            # 如果有当前价格，验证价格位置合理性
            if current_price:
                # 理想情况：止损 > 当前价格 > 止盈
                # 但允许一定容差，因为价格可能快速移动
                if not (order.take_profit * 0.999 <= current_price <= order.stop_loss * 1.001):
                    logger.info(f"卖单价格位置检查: stop_loss={order.stop_loss}, current_price={current_price}, take_profit={order.take_profit}")
        
        return True
        
    except Exception as e:
        logger.error(f"验证止损止盈逻辑异常: {e}")
        return False


def validate_order_size(order_amount: float, current_equity: float, max_percent: float) -> bool:
    """
    验证订单大小是否在限制范围内
    
    Args:
        order_amount: 订单金额
        current_equity: 当前权益
        max_percent: 最大允许百分比
        
    Returns:
        bool: True表示在范围内，False表示超限
    """
    try:
        if current_equity <= 0:
            logger.error(f"当前权益无效: {current_equity}")
            return False
        
        if order_amount <= 0:
            logger.error(f"订单金额无效: {order_amount}")
            return False
        
        position_ratio = order_amount / current_equity
        return position_ratio <= max_percent
        
    except Exception as e:
        logger.error(f"验证订单大小异常: {e}")
        return False


def get_position_ratio(order_amount: float, current_equity: float) -> float:
    """
    计算仓位占比
    
    Args:
        order_amount: 订单金额
        current_equity: 当前权益
        
    Returns:
        float: 仓位占比
    """
    try:
        if current_equity <= 0:
            return 0.0
        
        return order_amount / current_equity
        
    except Exception as e:
        logger.error(f"计算仓位占比异常: {e}")
        return 0.0
