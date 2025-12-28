"""
Athena Trader - Monolith Application Entry Point
统一的单体应用入口，整合所有交易模块
"""

import asyncio
import logging
import os
import sys
import signal
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import pandas as pd

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


class TradingLoop:
    """交易循环类 - 持续监控市场并执行交易策略"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._running = False
        self._task = None
        self._last_signal = None

        # 策略实例
        self.strategy = None

        # 交易参数
        self.trading_config = config.get('trading', {})
        self.symbol = self.trading_config.get('trading_symbol', 'SOL-USDT-SWAP')
        self.use_demo = self.trading_config.get('use_demo', True)
        self.interval = self.trading_config.get('signal_interval_seconds', 60)

    async def initialize(self):
        """初始化交易循环"""
        self.logger.info("=" * 80)
        self.logger.info("Initializing Trading Loop...")
        self.logger.info("=" * 80)

        # 初始化趋势回调策略
        try:
            from src.strategy_engine.core.trend_pullback_strategy import create_trend_pullback_strategy
            self.strategy = create_trend_pullback_strategy(self.config)
            self.logger.info("✓ Trend Pullback Strategy initialized")
        except Exception as e:
            self.logger.error(f"✗ Strategy initialization failed: {e}")
            raise

        self.logger.info("Trading Loop initialized successfully")
        self.logger.info(f"  Symbol: {self.symbol}")
        self.logger.info(f"  Demo Mode: {self.use_demo}")
        self.logger.info(f"  Interval: {self.interval}s")

    async def start(self):
        """启动交易循环"""
        if self._running:
            self.logger.warning("Trading loop is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._trading_loop())
        self.logger.info("Trading loop started")

    async def stop(self):
        """停止交易循环"""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self.logger.info("Trading loop stopped")

    async def _trading_loop(self):
        """主交易循环"""
        self.logger.info(f"Starting trading loop for {self.symbol}...")

        while self._running:
            try:
                # 1. 获取市场数据
                market_data = await self._get_market_data()

                if market_data is None:
                    self.logger.warning("Failed to get market data, retrying...")
                    await asyncio.sleep(self.interval)
                    continue

                # 2. 转换为DataFrame
                df = self._convert_to_dataframe(market_data)

                # 3. 查询当前持仓
                current_position = await self._get_current_position()

                # 4. 策略分析
                signal = self.strategy.analyze(df, current_position)

                self.logger.info(f"Strategy Signal: {signal['signal']} | "
                               f"Reason: {signal['reasoning']}")

                # 5. 执行交易决策
                await self._execute_decision(signal, current_position)

                # 6. 等待下一次循环
                await asyncio.sleep(self.interval)

            except asyncio.CancelledError:
                self.logger.info("Trading loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in trading loop: {e}", exc_info=True)
                await asyncio.sleep(self.interval)

    async def _get_market_data(self) -> Optional[Dict[str, Any]]:
        """获取市场数据"""
        try:
            if not modules["data_manager"]:
                self.logger.error("Data Manager not available")
                return None

            # 获取历史K线数据
            data = modules["data_manager"].get_historical_klines(
                symbol=self.symbol,
                timeframe='1h',  # 使用1小时周期
                limit=200,        # 获取足够的数据用于计算EMA 144
                use_demo=self.use_demo
            )

            if not data or len(data) == 0:
                self.logger.warning(f"No market data received for {self.symbol}")
                return None

            return data

        except Exception as e:
            self.logger.error(f"Error fetching market data: {e}")
            return None

    def _convert_to_dataframe(self, data: Dict[str, Any]) -> pd.DataFrame:
        """转换市场数据为DataFrame"""
        try:
            # 提取K线数据
            klines = data.get('klines', [])

            if not klines:
                raise ValueError("No klines data available")

            # 转换为DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'quote_volume', 'trades', 'taker_buy_base', 'taker_buy_quote'
            ])

            # 转换数值类型
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            # 转换时间戳
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            return df

        except Exception as e:
            self.logger.error(f"Error converting data to DataFrame: {e}")
            raise

    async def _get_current_position(self) -> Optional[Dict[str, Any]]:
        """获取当前持仓"""
        try:
            if not modules["data_manager"]:
                return None

            # 获取账户持仓
            positions = modules["data_manager"].get_account_positions(use_demo=self.use_demo)

            if not positions:
                return None

            # 查找目标交易对的持仓
            for position in positions:
                if position.get('symbol') == self.symbol:
                    size = float(position.get('size', 0))
                    if abs(size) > 0:
                        return {
                            'symbol': position['symbol'],
                            'size': size,
                            'entry_price': float(position.get('avg_entry_price', 0)),
                            'side': 'long' if size > 0 else 'short'
                        }

            return None

        except Exception as e:
            self.logger.error(f"Error fetching current position: {e}")
            return None

    async def _execute_decision(self, signal: Dict[str, Any], current_position: Optional[Dict]):
        """执行交易决策"""
        signal_type = signal['signal']

        # BUY 信号
        if signal_type == 'BUY':
            if current_position is None or current_position.get('size', 0) == 0:
                await self._execute_buy_order(signal)
            else:
                self.logger.info("Already have a position, ignoring BUY signal")

        # SELL 信号
        elif signal_type == 'SELL':
            if current_position is not None and current_position.get('size', 0) != 0:
                await self._execute_sell_order(signal, current_position)
            else:
                self.logger.info("No position to sell, ignoring SELL signal")

        # HOLD 信号
        elif signal_type == 'HOLD':
            self.logger.info("HOLD signal - no action taken")

    async def _execute_buy_order(self, signal: Dict[str, Any]):
        """执行买入订单"""
        try:
            # 检查执行器是否可用
            if not modules["executor"]:
                self.logger.error("Executor not available")
                return

            # 准备订单数据
            order_data = {
                'symbol': self.symbol,
                'side': 'buy',
                'amount': signal.get('position_size', 0),
                'type': 'market',
                'use_demo': self.use_demo,
                'stop_loss': signal.get('stop_loss', 0),
                'take_profit': signal.get('take_profit', 0),
                'leverage': signal.get('leverage', 1.0),
                'risk_amount': signal.get('risk_amount', 0)
            }

            self.logger.info(f"Executing BUY order: {order_data}")

            # 调用执行器
            result = await modules["executor"]["execute_trade"](
                order_data,
                use_demo=self.use_demo,
                stop_loss_pct=self.config.get('strategy', {}).get('stop_loss_pct', 0.03),
                take_profit_pct=self.config.get('strategy', {}).get('take_profit_pct', 0.06)
            )

            if result.get('status') in ['executed', 'simulated']:
                self.logger.info(f"✓ BUY order executed successfully: {result}")
            else:
                self.logger.error(f"✗ BUY order failed: {result}")

        except Exception as e:
            self.logger.error(f"Error executing buy order: {e}", exc_info=True)

    async def _execute_sell_order(self, signal: Dict[str, Any], position: Dict):
        """执行卖出订单（平仓）"""
        try:
            # 检查执行器是否可用
            if not modules["executor"]:
                self.logger.error("Executor not available")
                return

            # 调用强制平仓接口
            result = await modules["executor"]["force_close_position"](
                symbol=self.symbol,
                side=position.get('side', 'long')
            )

            if result.get('status') == 'success':
                self.logger.info(f"✓ Position closed successfully: {result}")
            else:
                self.logger.error(f"✗ Position close failed: {result}")

        except Exception as e:
            self.logger.error(f"Error executing sell order: {e}", exc_info=True)


class AthenaMonolith:
    """Athena单体应用主类"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._running = False
        self._shutdown_event = asyncio.Event()
        self.config = None
        self.trading_loop = None

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

        # 6. 初始化TradingLoop（交易循环）
        trading_config = self.config.get('trading', {})
        strategy_config = self.config.get('strategy', {})

        if strategy_config.get('enabled', True) and trading_config.get('use_demo', True):
            try:
                self.trading_loop = TradingLoop(self.config)
                await self.trading_loop.initialize()
                self.logger.info("✓ Trading Loop initialized")
            except Exception as e:
                self.logger.error(f"✗ Trading Loop initialization failed: {e}")

    async def shutdown(self):
        """关闭所有模块"""
        self.logger.info("=" * 80)
        self.logger.info("Shutting down Athena Trader Monolith...")
        self.logger.info("=" * 80)

        self._running = False

        # 关闭交易循环
        if self.trading_loop is not None:
            try:
                await self.trading_loop.stop()
                self.logger.info("✓ Trading Loop shutdown complete")
            except Exception as e:
                self.logger.error(f"✗ Trading Loop shutdown failed: {e}")

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

    # 启动交易循环
    if monolith_app.trading_loop is not None:
        await monolith_app.trading_loop.start()
        logger.info("Trading loop started in background")

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
