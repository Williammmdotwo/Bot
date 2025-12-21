import logging
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from .checks import is_order_rational

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("Risk Manager API 服务启动")
    yield
    # 关闭时执行
    logger.info("Risk Manager API 服务关闭")

# 创建 FastAPI 应用
app = FastAPI(
    title="Risk Manager API",
    description="风控管理服务 - 订单合理性检查",
    version="1.0.0",
    lifespan=lifespan
)


class OrderCheckRequest(BaseModel):
    """订单检查请求模型"""
    symbol: str = Field(..., description="交易对符号")
    side: str = Field(..., description="买卖方向")
    position_size: float = Field(..., gt=0, description="仓位大小(USDT计价)")
    stop_loss: float = Field(..., description="止损价格")
    take_profit: float = Field(..., description="止盈价格")
    current_price: float = Field(..., gt=0, description="当前市价")
    current_equity: float = Field(..., gt=0, description="当前账户权益")
    
    @field_validator('side')
    @classmethod
    def side_must_be_valid(cls, v):
        if v.lower() not in ['buy', 'sell']:
            raise ValueError('side必须是buy或sell')
        return v.lower()
    
    @field_validator('stop_loss', 'take_profit', 'current_price')
    @classmethod
    def prices_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('价格必须为正数')
        return v


class OrderCheckResponse(BaseModel):
    """订单检查响应模型"""
    is_rational: bool = Field(..., description="订单是否合理")
    reason: Optional[str] = Field(None, description="失败原因说明")


@app.post("/api/check-order", response_model=OrderCheckResponse)
async def check_order(request: OrderCheckRequest) -> OrderCheckResponse:
    """
    检查订单是否合理
    
    Args:
        request: 订单检查请求
        
    Returns:
        OrderCheckResponse: 检查结果
    """
    try:
        # 记录请求日志
        logger.info(f"收到订单检查请求: {request.dict()}")
        
        # 准备订单详情字典
        order_details = {
            'symbol': request.symbol,
            'side': request.side,
            'position_size': request.position_size,
            'stop_loss': request.stop_loss,
            'take_profit': request.take_profit
        }
        
        # 调用订单合理性检查（传入当前价格）
        is_rational_result = is_order_rational(
            order_details=order_details,
            current_equity=request.current_equity,
            current_price=request.current_price
        )
        
        # 准备响应
        response = OrderCheckResponse(
            is_rational=is_rational_result,
            reason=None if is_rational_result else "订单不符合风控规则"
        )
        
        # 记录响应日志
        if is_rational_result:
            logger.info(f"订单检查通过: {response.dict()}")
        else:
            logger.warning(f"订单检查失败: {response.dict()}")
        
        return response
        
    except ValueError as e:
        # 验证错误
        logger.warning(f"订单验证失败: {e}, 请求: {request.dict()}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"参数验证失败: {str(e)}"
        )
        
    except Exception as e:
        # 内部异常
        logger.error(f"订单检查异常: {e}, 请求: {request.dict()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="内部服务器错误"
        )


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    健康检查端点 - 用于Docker健康检查
    
    Returns:
        Dict[str, Any]: 健康状态
    """
    return {
        "status": "healthy",
        "service": "risk-manager-api",
        "version": "1.0.0"
    }


@app.get("/api/health")
async def api_health_check() -> Dict[str, Any]:
    """
    API健康检查端点
    
    Returns:
        Dict[str, Any]: 健康状态
    """
    return {
        "status": "healthy",
        "service": "risk-manager-api",
        "version": "1.0.0"
    }


@app.get("/")
async def root() -> Dict[str, Any]:
    """
    根路径
    
    Returns:
        Dict[str, Any]: 服务信息
    """
    return {
        "service": "Risk Manager API",
        "version": "1.0.0",
        "endpoints": {
            "check_order": "/api/check-order",
            "health": "/api/health",
            "docs": "/docs"
        }
    }




if __name__ == "__main__":
    import uvicorn
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 启动服务
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )
