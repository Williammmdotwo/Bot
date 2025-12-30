"""
pytest全局配置文件
pytest Global Configuration File
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Generator
from unittest.mock import Mock, AsyncMock

import pytest
import redis
import psycopg2
from fastapi.testclient import TestClient

# 测试配置
TEST_CONFIG = {
    "database": {
        "url": "postgresql://athena:athena123@localhost:5432/athena_trader_test",
        "pool_size": 5,
        "max_overflow": 10
    },
    "redis": {
        "host": "localhost",
        "port": 6379,
        "db": 1,  # 使用测试数据库
        "password": "redis123"
    },
    "services": {
        "data_manager": {
            "url": "http://localhost:8000",
            "timeout": 30
        },
        "risk_manager": {
            "url": "http://localhost:8001",
            "timeout": 30
        },
        "executor": {
            "url": "http://localhost:8002",
            "timeout": 30
        },
        "strategy_engine": {
            "url": "http://localhost:8003",
            "timeout": 30
        }
    },
    "test_symbols": ["BTC-USDT", "ETH-USDT"],
    "test_timeframes": ["5m", "15m", "1h"],
    "mock_external_apis": True
}

@pytest.fixture(scope="session")
def test_config() -> Dict[str, Any]:
    """测试配置fixture"""
    return TEST_CONFIG

@pytest.fixture(scope="function")
def event_loop():
    """创建事件循环用于异步测试"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="function")
def mock_redis():
    """模拟Redis连接"""
    mock_client = Mock(spec=redis.Redis)
    mock_client.ping.return_value = True
    mock_client.get.return_value = None
    mock_client.set.return_value = True
    mock_client.delete.return_value = 1
    mock_client.exists.return_value = 0
    mock_client.keys.return_value = []
    mock_client.flushdb.return_value = True
    return mock_client

@pytest.fixture(scope="function")
def mock_database():
    """模拟数据库连接"""
    mock_conn = Mock(spec=psycopg2.extensions.connection)
    mock_cursor = Mock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.execute.return_value = None
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []
    mock_cursor.rowcount = 0
    return mock_conn

@pytest.fixture(scope="function")
def sample_ohlcv_data():
    """示例OHLCV数据"""
    return [
        [1609459200000, 29000.0, 29500.0, 29250.0, 1000.5],
        [1609459500000, 29250.0, 29800.0, 29000.0, 1200.3],
        [1609459800000, 29800.0, 30000.0, 29000.0, 1500.4],
        [1609460100000, 30000.0, 30200.0, 29000.0, 1800.5],
        [1609460400000, 30200.0, 30500.0, 29000.0, 2400.6],
        [1609460700000, 30500.0, 30800.0, 29000.0, 3000.7],
        [1609461000000, 30800.0, 31000.0, 29000.0, 3600.8],
        ]
    ]

@pytest.fixture(scope="function")
def sample_strategy_config():
    """示例策略配置"""
    return {
        "name": "test_strategy",
        "version": "1.0.0",
        "description": "测试策略",
        "symbols": ["BTC-USDT"],
        "timeframes": ["5m", "15m"],
        "indicators": {
            "rsi": {"period": 14},
            "macd": {"fast": 12, "slow": 26, "signal": 9},
            "bollinger": {"period": 20, "std": 2}
        },
        "rules": [
            {
                "name": "buy_signal",
                "condition": "rsi < 30 AND macd.signal > macd.macd",
                "action": "buy",
                "parameters": {"amount": 0.1}
            },
            {
                "name": "sell_signal",
                "condition": "rsi > 70 OR macd.signal < macd.macd",
                "action": "sell",
                "parameters": {"amount": 0.1}
            }
        ],
        "risk_management": {
            "max_position_size": 0.5,
            "stop_loss": 0.02,
            "take_profit": 0.05
        }
    }

@pytest.fixture(scope="function")
def mock_ai_response():
    """模拟AI响应"""
    return {
        "status": "success",
        "response": "基于当前市场分析，BTC-USDT呈现上涨趋势，建议谨慎买入。",
        "confidence": 0.85,
        "analysis": {
            "trend": "bullish",
            "strength": "moderate",
            "key_factors": ["RSI超卖", "MACD金叉", "成交量放大"]
        }
    }

@pytest.fixture(scope="function")
def mock_external_api():
    """模拟外部API响应"""
    return {
        "okx_ticker": {
            "symbol": "BTC-USDT",
            "last": 30000.0,
            "bid": 29950.0,
            "ask": 30050.0,
            "volume": 1234567.89,
            "timestamp": 1609460400000
        },
        "okx_ohlcv": [
            [1609459200000, 29000.0, 29500.0, 29250.0, 1000.5],
            [1609459500000, 29250.0, 29800.0, 29000.0, 1200.3],
            [1609459800000, 29800.0, 30000.0, 29000.0, 980.7],
            [1609460100000, 30200.0, 30500.0, 29800.0, 3000.1],
            [1609460400000, 30200.0, 30500.0, 29800.0, 1800.5],
            [1609460700000, 30500.0, 30800.0, 29000.0, 2400.6],
            [1609461000000, 30800.0, 31000.0, 29000.0, 3000.7],
            ]
    }

@pytest.fixture(scope="function")
def temp_config_file(tmp_path, sample_strategy_config):
    """创建临时配置文件"""
    config_file = tmp_path / "test_strategy.json"
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(sample_strategy_config, f, indent=2, ensure_ascii=False)
    return config_file

@pytest.fixture(scope="function")
def mock_logger():
    """模拟日志记录器"""
    logger = Mock(spec=logging.Logger)
    logger.debug = Mock()
    logger.info = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    logger.critical = Mock()
    return logger

@pytest.fixture(scope="function")
def test_client_factory():
    """测试客户端工厂函数"""
    def _create_client(app):
        return TestClient(app)
    return _create_client

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """设置测试环境"""
    reports_dir = Path("tests/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    (reports_dir / "html").mkdir(exist_ok=True)
    (reports_dir / "coverage").mkdir(exist_ok=True)
    (reports_dir / "benchmarks").mkdir(exist_ok=True)

    yield

    pass

# 测试标记定义
def pytest_configure(config):
    """配置pytest标记"""
    config.addinivalue_line("markers", "unit: 单元测试")
    config.addinivalue_line("markers", "integration: 集成测试")
    config.addinivalue_line("markers", "system: 系统测试")
    config.addinivalue_line("markers", "slow: 慢速测试")
    config.addinivalue_line("markers", "performance: 性能测试")
    config.addinivalue_line("markers", "security: 安全测试")
    config.addinivalue_line("markers", "database: 数据库相关测试")
    config.addinivalue_line("markers", "redis: Redis相关测试")
    config.addinivalue_line("markers", "external_api: 外部API测试")
    config.addinivalue_line("markers", "benchmark: 基准测试")

# 测试收集钩子
def pytest_collection_modifyitems(config, items):
    """修改测试收集"""
    for item in items:
        if not any(item.iter_markers()):
            item.add_marker(pytest.mark.unit)

# 测试会话钩子
def pytest_sessionstart(session):
    """测试会话开始"""
    print("\n" + "="*60)
    print("Athena Trader 测试套件启动")
    print("="*60)

def pytest_sessionfinish(session, exitstatus):
    """测试会话结束"""
    print("\n" + "="*60)
    print(f"测试套件完成，退出码: {exitstatus}")
    print("="*60)
