"""
简化的策略引擎 API 服务器
"""
import os
import json
import logging
import asyncio
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# FastAPI 应用
app = FastAPI(
    title="Strategy Engine API",
    description="Trading Strategy Engine Service",
    version="1.0.0"
)

# Pydantic 模型
class StrategyRequest(BaseModel):
    symbol: str
    use_demo: bool = False

class StrategyResponse(BaseModel):
    signal: str
    decision_id: str
    reason: Optional[str] = None
    market_data: Optional[Dict[str, Any]] = None
    timestamp: int
    confidence: Optional[float] = 75.0

# 全局依赖实例
_data_handler = None

def initialize_dependencies(data_handler, ai_client=None):
    """初始化全局依赖实例"""
    global _data_handler
    _data_handler = data_handler
    logger.info("Dependencies initialized successfully")

# 依赖提供者
async def get_data_handler():
    """获取数据处理器实例"""
    if _data_handler is None:
        raise HTTPException(status_code=500, detail="Data handler not initialized")
    return _data_handler

# 安全验证
async def verify_service_token(x_service_token: str = Header(...)):
    """验证内部服务令牌"""
    expected_token = os.getenv("INTERNAL_SERVICE_TOKEN")
    if not expected_token:
        logger.error("INTERNAL_SERVICE_TOKEN environment variable not set")
        raise HTTPException(status_code=500, detail="Service token not configured")
    
    if x_service_token != expected_token:
        logger.warning(f"Invalid service token received: {x_service_token}")
        raise HTTPException(status_code=401, detail="Invalid service token")
    
    logger.info("Service token verified successfully")
    return x_service_token

# 导入策略函数
from .main import main_strategy_loop
import inspect

# 打印函数签名以确认
logger.info(f"main_strategy_loop function signature: {inspect.signature(main_strategy_loop)}")

# API 端点
@app.post("/api/generate-signal", response_model=StrategyResponse)
async def generate_trading_signal(
    request: StrategyRequest,
    token: str = Depends(verify_service_token),
    data_handler = Depends(get_data_handler)
):
    """
    生成交易信号端点
    """
    try:
        logger.info(f"Received strategy request for {request.symbol}")
        
        # 调用主策略循环
        logger.info(f"Calling main_strategy_loop with data_manager={type(data_handler)}")
        result = main_strategy_loop(
            data_manager=data_handler,
            symbol=request.symbol,
            use_demo=request.use_demo
        )
        
        logger.info(f"Generated signal: {result['signal']} for {request.symbol}")
        
        # 确保响应包含置信度字段
        if 'parsed_response' in result and 'confidence' in result['parsed_response']:
            result['confidence'] = result['parsed_response']['confidence']
        elif 'confidence' not in result:
            result['confidence'] = 75.0  # 默认置信度
        
        # 创建符合StrategyResponse模型的响应
        response_data = {
            "signal": result.get("signal", "HOLD"),
            "decision_id": result.get("decision_id", ""),
            "reason": result.get("reason", ""),
            "market_data": result.get("market_data"),
            "timestamp": result.get("timestamp", 0),
            "confidence": result.get("confidence", 75.0)
        }
        
        return StrategyResponse(**response_data)
        
    except Exception as e:
        logger.error(f"Signal generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Signal generation failed: {str(e)}")

@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "service": "strategy-engine-api"}

@app.get("/health")
async def health_check_root():
    """根健康检查端点"""
    return {"status": "healthy", "service": "strategy-engine-api"}

@app.get("/")
async def root():
    """根端点"""
    return {"service": "strategy-engine", "status": "running"}

# 服务器启动函数
def start_server(host: str = "0.0.0.0", port: int = 8003):
    """启动 API 服务器"""
    import uvicorn
    logger.info(f"Starting Strategy Engine API server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    start_server()
