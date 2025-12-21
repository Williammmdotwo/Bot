"""
Executor API服务器模块单元测试
覆盖executor/api_server.py的核心功能
"""

import pytest
import asyncio
import json
import os
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

# 导入测试目标
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../..'))

from src.executor.api_server import app, ForceCloseRequest, initialize_dependencies, \
    verify_service_token, check_position_exists, get_position_size, execute_force_close


class TestForceCloseRequest:
    """ForceCloseRequest模型测试"""
    
    def test_force_close_request_valid(self):
        """测试有效的强制平仓请求"""
        request = ForceCloseRequest(symbol="BTC-USDT", side="buy")
        assert request.symbol == "BTC-USDT"
        assert request.side == "buy"
    
    def test_force_close_request_sell(self):
        """测试卖出平仓请求"""
        request = ForceCloseRequest(symbol="ETH-USDT", side="sell")
        assert request.symbol == "ETH-USDT"
        assert request.side == "sell"
    
    def test_force_close_request_json_serialization(self):
        """测试JSON序列化"""
        request = ForceCloseRequest(symbol="BTC-USDT", side="buy")
        json_data = request.model_dump()
        expected = {"symbol": "BTC-USDT", "side": "buy"}
        assert json_data == expected


class TestDependencyManagement:
    """依赖管理测试"""
    
    def test_initialize_dependencies(self):
        """测试初始化依赖"""
        mock_ccxt = Mock()
        mock_pool = AsyncMock()
        mock_redis = AsyncMock()
        
        # 初始化依赖
        initialize_dependencies(mock_ccxt, mock_pool, mock_redis)
        
        # 验证全局变量被设置
        from src.executor.api_server import _ccxt_exchange, _postgres_pool, _redis_client
        assert _ccxt_exchange == mock_ccxt
        assert _postgres_pool == mock_pool
        assert _redis_client == mock_redis
    
    def test_get_ccxt_exchange_success(self):
        """测试获取CCXT交易所实例成功"""
        mock_exchange = Mock()
        initialize_dependencies(mock_exchange, None, None)
        
        # 测试依赖提供者
        async def test_get():
            from src.executor.api_server import get_ccxt_exchange
            return await get_ccxt_exchange()
        
        result = asyncio.run(test_get())
        assert result == mock_exchange
    
    def test_get_ccxt_exchange_not_initialized(self):
        """测试CCXT交易所实例未初始化"""
        # 清空全局变量
        initialize_dependencies(None, None, None)
        
        async def test_get():
            from src.executor.api_server import get_ccxt_exchange
            return await get_ccxt_exchange()
        
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(test_get())
        assert exc_info.value.status_code == 500
        assert "CCXT exchange not initialized" in str(exc_info.value.detail)
    
    def test_get_postgres_pool_success(self):
        """测试获取PostgreSQL连接池成功"""
        mock_pool = AsyncMock()
        initialize_dependencies(None, mock_pool, None)
        
        async def test_get():
            from src.executor.api_server import get_postgres_pool
            return await get_postgres_pool()
        
        result = asyncio.run(test_get())
        assert result == mock_pool
    
    def test_get_postgres_pool_not_initialized(self):
        """测试PostgreSQL连接池未初始化"""
        initialize_dependencies(None, None, None)
        
        async def test_get():
            from src.executor.api_server import get_postgres_pool
            return await get_postgres_pool()
        
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(test_get())
        assert exc_info.value.status_code == 500
        assert "PostgreSQL pool not initialized" in str(exc_info.value.detail)
    
    def test_get_redis_client_success(self):
        """测试获取Redis客户端成功"""
        mock_redis = AsyncMock()
        initialize_dependencies(None, None, mock_redis)
        
        async def test_get():
            from src.executor.api_server import get_redis_client
            return await get_redis_client()
        
        result = asyncio.run(test_get())
        assert result == mock_redis
    
    def test_get_redis_client_not_initialized(self):
        """测试Redis客户端未初始化"""
        initialize_dependencies(None, None, None)
        
        async def test_get():
            from src.executor.api_server import get_redis_client
            return await get_redis_client()
        
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(test_get())
        assert exc_info.value.status_code == 500
        assert "Redis client not initialized" in str(exc_info.value.detail)


class TestServiceTokenVerification:
    """服务令牌验证测试"""
    
    def test_verify_service_token_success(self):
        """测试服务令牌验证成功"""
        with patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "test_token_123"}):
            result = asyncio.run(verify_service_token("test_token_123"))
            assert result == "test_token_123"
    
    def test_verify_service_token_missing_env(self):
        """测试服务令牌环境变量缺失"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(verify_service_token("any_token"))
            assert exc_info.value.status_code == 500
            assert "Service token not configured" in str(exc_info.value.detail)
    
    def test_verify_service_token_invalid(self):
        """测试无效服务令牌"""
        with patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "correct_token"}):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(verify_service_token("wrong_token"))
            assert exc_info.value.status_code == 401
            assert "Invalid service token" in str(exc_info.value.detail)


class TestPositionManagement:
    """持仓管理测试"""
    
    @pytest.mark.asyncio
    async def test_check_position_exists_true(self):
        """测试检查持仓存在 - 存在"""
        mock_pool = AsyncMock()
        mock_pool.fetch.return_value = [
            {'order_id': 'order1', 'amount': 0.001, 'filled_amount': 0.001}
        ]
        
        result = await check_position_exists("BTC-USDT", "buy", mock_pool)
        assert result is True
        
        mock_pool.fetch.assert_called_once()
        call_args = mock_pool.fetch.call_args
        assert call_args[0][0] == "BTC-USDT"  # symbol
        assert call_args[0][1] == "buy"      # side
    
    @pytest.mark.asyncio
    async def test_check_position_exists_false(self):
        """测试检查持仓存在 - 不存在"""
        mock_pool = AsyncMock()
        mock_pool.fetch.return_value = []
        
        result = await check_position_exists("BTC-USDT", "buy", mock_pool)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_check_position_exists_error(self):
        """测试检查持仓存在 - 数据库错误"""
        mock_pool = AsyncMock()
        mock_pool.fetch.side_effect = Exception("Database error")
        
        with pytest.raises(Exception, match="Database error"):
            await check_position_exists("BTC-USDT", "buy", mock_pool)
    
    @pytest.mark.asyncio
    async def test_get_position_size_success(self):
        """测试获取持仓数量 - 成功"""
        mock_pool = AsyncMock()
        mock_pool.fetchrow.return_value = {'total_filled': 0.001}
        
        result = await get_position_size("BTC-USDT", "buy", mock_pool)
        assert result == 0.001
        
        mock_pool.fetchrow.assert_called_once()
        call_args = mock_pool.fetchrow.call_args
        assert call_args[0][0] == "BTC-USDT"  # symbol
        assert call_args[0][1] == "buy"      # side
    
    @pytest.mark.asyncio
    async def test_get_position_size_zero(self):
        """测试获取持仓数量 - 零持仓"""
        mock_pool = AsyncMock()
        mock_pool.fetchrow.return_value = None
        
        result = await get_position_size("BTC-USDT", "buy", mock_pool)
        assert result == 0.0
    
    @pytest.mark.asyncio
    async def test_get_position_size_error(self):
        """测试获取持仓数量 - 数据库错误"""
        mock_pool = AsyncMock()
        mock_pool.fetchrow.side_effect = Exception("Database error")
        
        with pytest.raises(Exception, match="Database error"):
            await get_position_size("BTC-USDT", "buy", mock_pool)


class TestExecuteForceClose:
    """强制平仓执行测试"""
    
    @pytest.fixture
    def mock_ccxt_exchange(self):
        """模拟CCXT交易所实例"""
        mock_exchange = Mock()
        mock_exchange.create_market_order.return_value = {
            'id': 'close_order_123',
            'symbol': 'BTC-USDT',
            'side': 'sell',
            'amount': 0.001,
            'status': 'open',
            'price': 50000.0,
            'fee': {'cost': 0.0001}
        }
        return mock_exchange
    
    @pytest.fixture
    def mock_postgres_pool(self):
        """模拟PostgreSQL连接池"""
        mock_pool = AsyncMock()
        mock_pool.execute = AsyncMock()
        return mock_pool
    
    @pytest.fixture
    def mock_redis_client(self):
        """模拟Redis客户端"""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()
        return mock_redis
    
    @pytest.mark.asyncio
    async def test_execute_force_close_success(self, mock_ccxt_exchange, 
                                           mock_postgres_pool, mock_redis_client):
        """测试强制平仓成功"""
        with patch('src.executor.api_server.track') as mock_track:
            mock_track.return_value = AsyncMock()
            
            result = await execute_force_close(
                "BTC-USDT", "buy", 0.001,
                mock_ccxt_exchange, mock_postgres_pool, mock_redis_client
            )
            
            # 验证结果
            assert result["close_order_id"] == "close_order_123"
            assert result["symbol"] == "BTC-USDT"
            assert result["side"] == "buy"
            assert result["close_side"] == "sell"
            assert result["position_size"] == 0.001
            assert result["status"] == "open"
            
            # 验证平仓订单创建
            mock_ccxt_exchange.create_market_order.assert_called_once_with(
                symbol="BTC-USDT",
                side="sell",
                amount=0.001
            )
            
            # 验证数据库操作
            assert mock_postgres_pool.execute.call_count == 2  # 更新原订单 + 插入平仓记录
            
            # 验证Redis发布
            mock_redis_client.publish.assert_called_once()
            
            # 验证跟踪启动
            mock_track.assert_called_once_with("close_order_123", mock_ccxt_exchange, mock_postgres_pool)
    
    @pytest.mark.asyncio
    async def test_execute_force_close_sell_position(self, mock_ccxt_exchange, 
                                                mock_postgres_pool, mock_redis_client):
        """测试强制平仓卖出持仓"""
        with patch('src.executor.api_server.track') as mock_track:
            mock_track.return_value = AsyncMock()
            
            result = await execute_force_close(
                "ETH-USDT", "sell", 0.1,
                mock_ccxt_exchange, mock_postgres_pool, mock_redis_client
            )
            
            # 验证平仓方向是buy（反向）
            assert result["close_side"] == "buy"
            
            # 验证平仓订单创建
            mock_ccxt_exchange.create_market_order.assert_called_once_with(
                symbol="ETH-USDT",
                side="buy",
                amount=0.1
            )
    
    @pytest.mark.asyncio
    async def test_execute_force_close_ccxt_error(self, mock_ccxt_exchange, 
                                                mock_postgres_pool, mock_redis_client):
        """测试强制平仓 - CCXT错误"""
        mock_ccxt_exchange.create_market_order.side_effect = Exception("Exchange error")
        
        with pytest.raises(Exception, match="Exchange error"):
            await execute_force_close(
                "BTC-USDT", "buy", 0.001,
                mock_ccxt_exchange, mock_postgres_pool, mock_redis_client
            )
    
    @pytest.mark.asyncio
    async def test_execute_force_close_database_error(self, mock_ccxt_exchange, 
                                                  mock_postgres_pool, mock_redis_client):
        """测试强制平仓 - 数据库错误"""
        mock_postgres_pool.execute.side_effect = Exception("Database error")
        
        with pytest.raises(Exception, match="Database error"):
            await execute_force_close(
                "BTC-USDT", "buy", 0.001,
                mock_ccxt_exchange, mock_postgres_pool, mock_redis_client
            )
    
    @pytest.mark.asyncio
    async def test_execute_force_close_redis_error_continues(self, mock_ccxt_exchange, 
                                                          mock_postgres_pool, mock_redis_client):
        """测试强制平仓 - Redis错误时继续"""
        mock_redis_client.publish.side_effect = Exception("Redis error")
        
        with patch('src.executor.api_server.track') as mock_track:
            mock_track.return_value = AsyncMock()
            
            # 应该成功执行，即使Redis失败
            result = await execute_force_close(
                "BTC-USDT", "buy", 0.001,
                mock_ccxt_exchange, mock_postgres_pool, mock_redis_client
            )
            
            # 验证结果
            assert result["close_order_id"] == "close_order_123"
            
            # 验证其他操作正常执行
            mock_ccxt_exchange.create_market_order.assert_called_once()
            assert mock_postgres_pool.execute.call_count == 2
            mock_track.assert_called_once()


class TestAPIEndpoints:
    """API端点测试"""
    
    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return TestClient(app)
    
    @pytest.fixture
    def setup_dependencies(self):
        """设置依赖"""
        mock_ccxt = Mock()
        mock_pool = AsyncMock()
        mock_redis = AsyncMock()
        initialize_dependencies(mock_ccxt, mock_pool, mock_redis)
        return mock_ccxt, mock_pool, mock_redis
    
    def test_health_check(self, client):
        """测试健康检查端点"""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "executor-api"
    
    def test_health_check_root(self, client):
        """测试根健康检查端点"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "executor-api"
    
    def test_force_close_success(self, client, setup_dependencies):
        """测试强制平仓端点成功"""
        mock_ccxt, mock_pool, mock_redis = setup_dependencies
        
        # 模拟持仓存在
        mock_pool.fetch.return_value = [{'order_id': 'order1'}]
        mock_pool.fetchrow.return_value = {'total_filled': 0.001}
        
        # 模拟平仓订单创建
        mock_ccxt.create_market_order.return_value = {
            'id': 'close_order_123',
            'status': 'open'
        }
        
        with patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "test_token"}):
            with patch('src.executor.api_server.execute_force_close') as mock_execute:
                mock_execute.return_value = {
                    "close_order_id": "close_order_123",
                    "symbol": "BTC-USDT",
                    "status": "success"
                }
                
                response = client.post(
                    "/api/force-close",
                    json={"symbol": "BTC-USDT", "side": "buy"},
                    headers={"X-Service-Token": "test_token"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert "data" in data
    
    def test_force_close_no_position(self, client, setup_dependencies):
        """测试强制平仓 - 无持仓"""
        mock_ccxt, mock_pool, mock_redis = setup_dependencies
        
        # 模拟无持仓
        mock_pool.fetch.return_value = []
        
        with patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "test_token"}):
            response = client.post(
                "/api/force-close",
                json={"symbol": "BTC-USDT", "side": "buy"},
                headers={"X-Service-Token": "test_token"}
            )
            
            assert response.status_code == 404
            data = response.json()
            assert "No position found" in data["detail"]
    
    def test_force_close_zero_position(self, client, setup_dependencies):
        """测试强制平仓 - 零持仓"""
        mock_ccxt, mock_pool, mock_redis = setup_dependencies
        
        # 模拟持仓存在但数量为0
        mock_pool.fetch.return_value = [{'order_id': 'order1'}]
        mock_pool.fetchrow.return_value = {'total_filled': 0.0}
        
        with patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "test_token"}):
            response = client.post(
                "/api/force-close",
                json={"symbol": "BTC-USDT", "side": "buy"},
                headers={"X-Service-Token": "test_token"}
            )
            
            assert response.status_code == 400
            data = response.json()
            assert "No position size to close" in data["detail"]
    
    def test_force_close_invalid_token(self, client, setup_dependencies):
        """测试强制平仓 - 无效令牌"""
        with patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "correct_token"}):
            response = client.post(
                "/api/force-close",
                json={"symbol": "BTC-USDT", "side": "buy"},
                headers={"X-Service-Token": "wrong_token"}
            )
            
            assert response.status_code == 401
            data = response.json()
            assert "Invalid service token" in data["detail"]
    
    def test_force_close_missing_token(self, client, setup_dependencies):
        """测试强制平仓 - 缺失令牌"""
        response = client.post(
            "/api/force-close",
            json={"symbol": "BTC-USDT", "side": "buy"}
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "Invalid service token" in data["detail"]
    
    def test_force_close_execution_error(self, client, setup_dependencies):
        """测试强制平仓 - 执行错误"""
        mock_ccxt, mock_pool, mock_redis = setup_dependencies
        
        # 模拟持仓存在
        mock_pool.fetch.return_value = [{'order_id': 'order1'}]
        mock_pool.fetchrow.return_value = {'total_filled': 0.001}
        
        with patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "test_token"}):
            with patch('src.executor.api_server.execute_force_close') as mock_execute:
                mock_execute.side_effect = Exception("Execution error")
                
                response = client.post(
                    "/api/force-close",
                    json={"symbol": "BTC-USDT", "side": "buy"},
                    headers={"X-Service-Token": "test_token"}
                )
                
                assert response.status_code == 500
                data = response.json()
                assert "Force close failed" in data["detail"]


class TestAPIIntegration:
    """API集成测试"""
    
    def test_full_force_close_workflow(self):
        """测试完整强制平仓工作流"""
        # 设置依赖
        mock_ccxt = Mock()
        mock_pool = AsyncMock()
        mock_redis = AsyncMock()
        initialize_dependencies(mock_ccxt, mock_pool, mock_redis)
        
        # 模拟持仓数据
        mock_pool.fetch.return_value = [{'order_id': 'order1', 'amount': 0.001}]
        mock_pool.fetchrow.return_value = {'total_filled': 0.001}
        
        # 模拟平仓订单
        mock_ccxt.create_market_order.return_value = {
            'id': 'close_order_123',
            'symbol': 'BTC-USDT',
            'side': 'sell',
            'amount': 0.001,
            'status': 'open',
            'price': 50000.0,
            'fee': {'cost': 0.0001}
        }
        
        with patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "test_token"}):
            with patch('src.executor.api_server.track') as mock_track:
                mock_track.return_value = AsyncMock()
                
                client = TestClient(app)
                response = client.post(
                    "/api/force-close",
                    json={"symbol": "BTC-USDT", "side": "buy"},
                    headers={"X-Service-Token": "test_token"}
                )
                
                # 验证响应
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                
                # 验证数据库操作
                assert mock_pool.fetch.call_count == 2  # 检查持仓 + 获取持仓大小
                assert mock_pool.execute.call_count == 2  # 更新原订单 + 插入平仓记录
                
                # 验证Redis发布
                mock_redis.publish.assert_called_once()
                publish_call = mock_redis.publish.call_args
                assert publish_call[0][0] == 'position_events'
                message = json.loads(publish_call[0][1])
                assert message["event"] == "position_closed"
                assert message["symbol"] == "BTC-USDT"
                assert message["reason"] == "RISK_STOP_LOSS"
                
                # 验证跟踪启动
                mock_track.assert_called_once_with("close_order_123", mock_ccxt, mock_pool)
