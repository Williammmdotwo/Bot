import os
import json
import logging
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
    confidence: Optional[float] = None
    market_data: Optional[Dict[str, Any]] = None
    timestamp: int

class StrategyStartRequest(BaseModel):
    symbols: list
    timeframe: str = "15m"

class StrategyStatusResponse(BaseModel):
    status: str
    running: bool
    symbols: list
    timeframe: str
    last_signal: Optional[Dict[str, Any]] = None

# 全局依赖实例
_data_handler = None
_strategy_running = False

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
    # TODO: SECURITY - Re-enable token verification for production
    # WARNING: This is a temporary bypass for development only!
    # In production, implement proper token validation:
    # expected_token = os.getenv("INTERNAL_SERVICE_TOKEN")
    # if not expected_token or x_service_token != expected_token:
    #     logger.error("Invalid service token provided")
    #     raise HTTPException(status_code=401, detail="Invalid service token")
    logger.info(f"DEBUG: Token verification bypassed for development. Received token: {repr(x_service_token)}")
    return x_service_token

# 导入策略函数 - 延迟导入避免循环依赖
def get_main_strategy_loop():
    try:
        from .main import main_strategy_loop
        return main_strategy_loop
    except ImportError:
        from src.strategy_engine.main import main_strategy_loop
        return main_strategy_loop

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
        main_strategy_loop = get_main_strategy_loop()
        result = main_strategy_loop(
            data_manager=data_handler,
            symbol=request.symbol,
            use_demo=request.use_demo
        )

        logger.info(f"Generated signal: {result['signal']} for {request.symbol}")
        return StrategyResponse(**result)

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

@app.get("/api/strategy/status", response_model=StrategyStatusResponse)
async def get_strategy_status():
    """获取策略状态"""
    global _strategy_running

    return StrategyStatusResponse(
        status="running" if _strategy_running else "stopped",
        running=_strategy_running,
        symbols=["BTC-USDT"],  # 默认监控的币种
        timeframe="15m",  # 默认时间框架
        last_signal=None
    )

@app.post("/api/strategy/start")
async def start_strategy(
    request: StrategyStartRequest,
    token: str = Depends(verify_service_token)
):
    """启动策略循环"""
    global _strategy_running

    try:
        if _strategy_running:
            return {"status": "already_running", "message": "策略已在运行中"}

        _strategy_running = True
        logger.info(f"策略启动: symbols={request.symbols}, timeframe={request.timeframe}")

        return {
            "status": "started",
            "symbols": request.symbols,
            "timeframe": request.timeframe,
            "message": "策略启动成功"
        }

    except Exception as e:
        logger.error(f"启动策略失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动策略失败: {str(e)}")

@app.post("/api/strategy/stop")
async def stop_strategy(
    token: str = Depends(verify_service_token)
):
    """停止策略循环"""
    global _strategy_running

    try:
        if not _strategy_running:
            return {"status": "already_stopped", "message": "策略已停止"}

        _strategy_running = False
        logger.info("策略已停止")

        return {
            "status": "stopped",
            "message": "策略停止成功"
        }

    except Exception as e:
        logger.error(f"停止策略失败: {e}")
        raise HTTPException(status_code=500, detail=f"停止策略失败: {str(e)}")

# 服务器启动函数
def start_server(host: str = "0.0.0.0", port: int = 8003):
    """启动 API 服务器"""
    import uvicorn
    logger.info(f"Starting Strategy Engine API server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    start_server()
