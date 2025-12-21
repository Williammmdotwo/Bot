@echo off
echo Starting Athena Trader Services in Background...
echo.

REM Start Data Manager
start "Data Manager" cmd /k "cd /d D:\AI\B\athena-trader && set CONFIG_PATH=D:\AI\B\athena-trader\config && set DISABLE_REDIS=true && set PYTHONPATH=D:\AI\B\athena-trader\src && python -m src.data_manager.main"
timeout /t 2 >nul

REM Start Risk Manager  
start "Risk Manager" cmd /k "cd /d D:\AI\B\athena-trader && set CONFIG_PATH=D:\AI\B\athena-trader\config && set DISABLE_REDIS=true && set PYTHONPATH=D:\AI\B\athena-trader\src && python -m src.risk_manager.main"
timeout /t 2 >nul

REM Start Executor
start "Executor" cmd /k "cd /d D:\AI\B\athena-trader && set CONFIG_PATH=D:\AI\B\athena-trader\config && set DISABLE_REDIS=true && set PYTHONPATH=D:\AI\B\athena-trader\src && python -m src.executor.main"
timeout /t 2 >nul

REM Start Strategy Engine
start "Strategy Engine" cmd /k "cd /d D:\AI\B\athena-trader && set CONFIG_PATH=D:\AI\B\athena-trader\config && set DISABLE_REDIS=true && set PYTHONPATH=D:\AI\B\athena-trader\src && set INTERNAL_SERVICE_TOKEN=athena-internal-token-change-in-production && set AI_API_BASE_URL=https://api.siliconflow.cn/v1 && set AI_API_KEY=sk-yopmfraxjyivhczjcjkvxxsksdzkvkzwsgdmernikxeavutu && set AI_MODEL_NAME=Pro/deepseek-ai/DeepSeek-V3.1-Terminus && python -m src.strategy_engine.main"

echo.
echo All services started in separate windows!
echo Wait 30 seconds for services to fully initialize, then run the test.
echo.
echo To test, open a new cmd window and run:
echo cd /d D:\AI\B\athena-trader
echo python -m tests.system.simple_trading_test
echo.
pause
