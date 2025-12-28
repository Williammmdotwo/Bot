"""
Athena Trader - Monolith Application Entry Point
统一的单体应用入口，整合所有交易模块
"""

import asyncio
import logging
import os
import sys
import signal
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

# 设置环境变量
os.environ.setdefault("PYTHONPATH", os.path.dirname(os.path.abspath(__file__)))

# 导入工具函数
try:
    from src.utils.logging_config import setup_logging
    from src.utils.config_loader import get_config_manager
except ImportError:
    print("Warning: Failed to import utility modules, using basic logging")
    logging.basicConfig(level=logging.INFO)
    setup_logging = None
    get_config_manager = None

logger = logging.getLogger(__name__)


# 全局模块实例
modules = {
    "data_manager": None,
    "strategy_engine": None,
    "risk_manager": None,
    "executor": None,
    "monitoring": None
}


class AthenaMonolith:
    """Athena单体应用主类"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._running = False
        self._shutdown_event = asyncio.Event()
        self.config = None

    async def initialize(self):
        """初始化所有模块"""
        self.logger.info("=" * 80)
        self.logger.info("Initializing Athena Trader Monolith...")
        self.logger.info("=" * 80)

        # 加载配置
        try:
            if get_config_manager:
                config_manager = get_config_manager()
                self.config = config_manager.get_config()
                self.logger.info(f"Loaded configuration: {self.config.get('app', {}).get('name', 'unknown')}")
            else:
                self.config = {"app": {"name": "athena_trader", "port": 8000}}
                self.logger.warning("Using default configuration")
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            self.config = {"app": {"name": "athena_trader", "port": 8000}}

        # 初始化各个模块
        await self._initialize_modules()

        self._running = True
        self.logger.info("=" * 80)
        self.logger.info("Athena Trader Monolith initialized successfully")
        self.logger.info("=" * 80)

    async def _initialize_modules(self):
        """初始化各个交易模块"""
        app_config = self.config.get('app', {})
        modules_config = self.config.get('modules', {})

        # 1. 初始化DataManager（数据管理器）
        if modules_config.get('data_manager', {}).get('enabled', True):
            try:
                from src.data_manager.main import DataHandler
                modules["data_manager"] = DataHandler()
                self.logger.info("✓ Data Manager initialized")
            except Exception as e:
                self.logger.error(f"✗ Data Manager initialization failed: {e}")

        # 2. 初始化StrategyEngine（策略引擎）
        if modules_config.get('strategy_engine', {}).get('enabled', True):
            try:
                from src.strategy_engine.dual_ema_strategy import DualEMAStrategy
                modules["strategy_engine"] = DualEMAStrategy()
                self.logger.info("✓ Strategy Engine initialized")
            except Exception as e:
                self.logger.error(f"✗ Strategy Engine initialization failed: {e}")

        # 3. 初始化Executor（执行器）
        if modules_config.get('executor', {}).get('enabled', True):
            try:
                from src.executor.interface import initialize_dependencies, health_check
                modules["executor"] = {
                    "initialize": initialize_dependencies,
                    "health": health_check,
                    "execute": None  # 将在运行时注入
                }
                self.logger.info("✓ Executor interface initialized")
            except Exception as e:
                self.logger.error(f"✗ Executor initialization failed: {e}")

        # 4. 初始化RiskManager（风险管理器）
        if modules_config.get('risk_manager', {}).get('enabled', True):
            try:
                from src.risk_manager.interface import health_check
                modules["risk_manager"] = {
                    "health": health_check,
                    "check_order": None,  # 将在运行时注入
                    "emergency_close": None  # 将在运行时注入
                }
                self.logger.info("✓ Risk Manager interface initialized")
            except Exception as e:
                self.logger.error(f"✗ Risk Manager initialization failed: {e}")

        # 5. 初始化Monitoring（监控）
        if modules_config.get('monitoring', {}).get('enabled', True):
            try:
                from src.monitoring.dashboard import PerformanceDashboard, get_dashboard
                modules["monitoring"] = get_dashboard()
                modules["monitoring"].start_monitoring(interval=5)
                self.logger.info("✓ Monitoring initialized")
            except Exception as e:
                self.logger.error(f"✗ Monitoring initialization failed: {e}")

    async def shutdown(self):
        """关闭所有模块"""
        self.logger.info("=" * 80)
        self.logger.info("Shutting down Athena Trader Monolith...")
        self.logger.info("=" * 80)

        self._running = False

        # 关闭各个模块
        for module_name, module_instance in modules.items():
            if module_instance is not None:
                try:
                    if hasattr(module_instance, 'close'):
                        await module_instance.close()
                    elif hasattr(module_instance, 'stop'):
                        module_instance.stop()
                    self.logger.info(f"✓ {module_name} shutdown complete")
                except Exception as e:
                    self.logger.error(f"✗ {module_name} shutdown failed: {e}")

        self._shutdown_event.set()
        self.logger.info("=" * 80)
        self.logger.info("Athena Trader Monolith shutdown complete")
        self.logger.info("=" * 80)

    def is_running(self) -> bool:
        """检查应用是否在运行"""
        return self._running

    async def wait_for_shutdown(self):
        """等待关闭信号"""
        await self._shutdown_event.wait()


# 全局应用实例
monolith_app: Optional[AthenaMonolith] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI生命周期管理"""
    global monolith_app

    # 启动时初始化
    monolith_app = AthenaMonolith()
    await monolith_app.initialize()

    yield

    # 关闭时清理
    await monolith_app.shutdown()


# 创建FastAPI应用
app = FastAPI(
    title="Athena Trader",
    description="Algorithmic Trading System - Monolith Architecture",
    version="1.0.0",
    lifespan=lifespan
)


# ==================== 健康检查端点 ====================

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "athena-trader",
        "architecture": "monolith",
        "running": monolith_app.is_running() if monolith_app else False,
        "modules": {
            name: module is not None
            for name, module in modules.items()
        }
    }


@app.get("/")
async def root():
    """根端点"""
    return {
        "service": "Athena Trader",
        "version": "1.0.0",
        "architecture": "monolith",
        "status": "running" if monolith_app and monolith_app.is_running() else "initializing"
    }


# ==================== 数据管理端点 ====================

@app.get("/api/market-data/{symbol}")
async def get_market_data(symbol: str, use_demo: bool = False):
    """获取市场数据"""
    if not modules["data_manager"]:
        raise HTTPException(status_code=503, detail="Data Manager not available")

    try:
        data = modules["data_manager"].get_comprehensive_market_data(symbol, use_demo)
        return data
    except Exception as e:
        logger.error(f"Error fetching market data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/account/balance")
async def get_account_balance(use_demo: bool = False):
    """获取账户余额"""
    if not modules["data_manager"]:
        raise HTTPException(status_code=503, detail="Data Manager not available")

    try:
        balance = modules["data_manager"].get_account_balance(use_demo)
        return balance
    except Exception as e:
        logger.error(f"Error fetching account balance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/account/positions")
async def get_account_positions(use_demo: bool = False):
    """获取账户持仓"""
    if not modules["data_manager"]:
        raise HTTPException(status_code=503, detail="Data Manager not available")

    try:
        positions = modules["data_manager"].get_account_positions(use_demo)
        return positions
    except Exception as e:
        logger.error(f"Error fetching account positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 策略端点 ====================

@app.get("/api/strategy/signals")
async def get_strategy_signals():
    """获取策略信号"""
    if not modules["strategy_engine"]:
        raise HTTPException(status_code=503, detail="Strategy Engine not available")

    try:
        signals = modules["strategy_engine"].get_signals()
        return {"signals": signals}
    except Exception as e:
        logger.error(f"Error fetching strategy signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 风险管理端点 ====================

@app.get("/api/risk/limits")
async def get_risk_limits():
    """获取风险限制"""
    if not modules["risk_manager"]:
        raise HTTPException(status_code=503, detail="Risk Manager not available")

    try:
        limits = modules["risk_manager"].get_limits()
        return {"limits": limits}
    except Exception as e:
        logger.error(f"Error fetching risk limits: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 执行端点 ====================

@app.post("/api/executor/order")
async def execute_order(order_data: dict):
    """执行订单"""
    if not modules["executor"]:
        raise HTTPException(status_code=503, detail="Executor not available")

    try:
        result = modules["executor"].execute_order(order_data)
        return result
    except Exception as e:
        logger.error(f"Error executing order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 监控端点 ====================

@app.get("/api/monitoring/metrics")
async def get_metrics():
    """获取监控指标"""
    if not modules["monitoring"]:
        raise HTTPException(status_code=503, detail="Monitoring not available")

    try:
        metrics = modules["monitoring"].get_metrics()
        return {"metrics": metrics}
    except Exception as e:
        logger.error(f"Error fetching metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 全局异常处理 ====================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理器"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "path": str(request.url)
        }
    )


# ==================== 主函数 ====================

def main():
    """主函数"""
    global monolith_app

    # 设置日志
    if setup_logging:
        setup_logging()

    logger.info("=" * 80)
    logger.info("Starting Athena Trader Monolith...")
    logger.info("=" * 80)

    # 获取配置
    if get_config_manager:
        try:
            config_manager = get_config_manager()
            config = config_manager.get_config()
        except Exception:
            config = None
    else:
        config = None

    # 获取主机和端口配置
    if config:
        host = config.get('app', {}).get('host', '0.0.0.0')
        port = config.get('app', {}).get('port', 8000)
    else:
        host = os.getenv('APP_HOST', '0.0.0.0')
        port = int(os.getenv('APP_PORT', '8000'))

    # 设置信号处理
    def signal_handler(signum, frame):
        """信号处理器"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        asyncio.create_task(monolith_app.shutdown()) if monolith_app else None
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 启动Uvicorn服务器
    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run(
        "main_monolith:app",
        host=host,
        port=port,
        log_level=os.getenv('LOG_LEVEL', 'info').lower(),
        access_log=True,
        reload=False
    )


if __name__ == "__main__":
    main()
