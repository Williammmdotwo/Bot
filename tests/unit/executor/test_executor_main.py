"""
Executor主模块单元测试
覆盖executor/main.py的核心功能
"""

import pytest
import asyncio
import json
import os
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime

# 导入测试目标
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../..'))

from src.executor.main import execute_order


class TestExecuteOrder:
    """execute_order函数测试"""
    
    @pytest.fixture
    def mock_signal(self):
        """模拟交易信号"""
        return {
            'symbol': 'BTC-USDT',
            'action': 'buy',
            'size': 0.001,
            'side': 'buy',
            'decision_id': 'test_decision_123'
        }
    
    @pytest.fixture
    def mock_ccxt_exchange(self):
        """模拟CCXT交易所实例"""
        mock_exchange = Mock()
        mock_exchange.create_market_order.return_value = {
            'id': 'order_123',
            'symbol': 'BTC-USDT',
            'side': 'buy',
            'amount': 0.001,
            'status': 'open'
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
    
    @pytest.fixture
    def mock_snapshot(self):
        """模拟市场快照"""
        return {
            'symbol': 'BTC-USDT',
            'klines': [[1609459200000, 50000, 50100, 49900, 50050, 100]],
            'indicators': {'rsi': 50},
            'account': {'balance': {'BTC': 1.0}, 'positions': []},
            'data_status': 'OK'
        }
    
    @pytest.mark.asyncio
    async def test_execute_order_success_demo_environment(self, mock_signal, mock_ccxt_exchange, 
                                                      mock_postgres_pool, mock_redis_client, mock_snapshot):
        """测试在demo环境下成功执行订单"""
        with patch.dict(os.environ, {
            'OKX_ENVIRONMENT': 'demo',
            'USE_DATABASE': 'true'
        }):
            with patch('src.executor.main.DataHandler') as mock_data_handler_class:
                mock_data_handler = Mock()
                mock_data_handler.get_snapshot.return_value = mock_snapshot
                mock_data_handler_class.return_value = mock_data_handler
                
                with patch('src.executor.main.validate_order_signal') as mock_validate:
                    mock_validate.return_value = True
                    
                    with patch('src.executor.main.track') as mock_track:
                        mock_track.return_value = AsyncMock()
                        
                        result = await execute_order(
                            mock_signal, mock_ccxt_exchange, mock_postgres_pool, mock_redis_client
                        )
                        
                        # 验证结果
                        assert result['id'] == 'order_123'
                        assert result['symbol'] == 'BTC-USDT'
                        assert result['side'] == 'buy'
                        
                        # 验证调用
                        mock_ccxt_exchange.create_market_order.assert_called_once_with(
                            symbol='BTC-USDT',
                            side='buy',
                            amount=0.001
                        )
                        
                        mock_postgres_pool.execute.assert_called_once()
                        mock_redis_client.publish.assert_called_once()
                        mock_track.assert_called_once_with('order_123', mock_ccxt_exchange, mock_postgres_pool)
    
    @pytest.mark.asyncio
    async def test_execute_order_production_environment_blocked(self, mock_signal, mock_ccxt_exchange, 
                                                           mock_postgres_pool, mock_redis_client):
        """测试在生产环境下阻止执行订单"""
        with patch.dict(os.environ, {
            'OKX_ENVIRONMENT': 'production'
        }):
            with pytest.raises(ValueError, match="Trading only allowed in demo environment"):
                await execute_order(
                    mock_signal, mock_ccxt_exchange, mock_postgres_pool, mock_redis_client
                )
    
    @pytest.mark.asyncio
    async def test_execute_order_validation_failure(self, mock_signal, mock_ccxt_exchange, 
                                                 mock_postgres_pool, mock_redis_client, mock_snapshot):
        """测试订单验证失败"""
        with patch.dict(os.environ, {
            'OKX_ENVIRONMENT': 'demo',
            'USE_DATABASE': 'true'
        }):
            with patch('src.executor.main.DataHandler') as mock_data_handler_class:
                mock_data_handler = Mock()
                mock_data_handler.get_snapshot.return_value = mock_snapshot
                mock_data_handler_class.return_value = mock_data_handler
                
                with patch('src.executor.main.validate_order_signal') as mock_validate:
                    mock_validate.side_effect = ValueError("Order validation failed")
                    
                    with pytest.raises(ValueError, match="Order validation failed"):
                        await execute_order(
                            mock_signal, mock_ccxt_exchange, mock_postgres_pool, mock_redis_client
                        )
                    
                    # 验证没有创建订单
                    mock_ccxt_exchange.create_market_order.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_execute_order_ccxt_error(self, mock_signal, mock_ccxt_exchange, 
                                          mock_postgres_pool, mock_redis_client, mock_snapshot):
        """测试CCXT创建订单失败"""
        with patch.dict(os.environ, {
            'OKX_ENVIRONMENT': 'demo',
            'USE_DATABASE': 'true'
        }):
            with patch('src.executor.main.DataHandler') as mock_data_handler_class:
                mock_data_handler = Mock()
                mock_data_handler.get_snapshot.return_value = mock_snapshot
                mock_data_handler_class.return_value = mock_data_handler
                
                with patch('src.executor.main.validate_order_signal') as mock_validate:
                    mock_validate.return_value = True
                    
                    mock_ccxt_exchange.create_market_order.side_effect = Exception("CCXT Error")
                    
                    with pytest.raises(Exception, match="CCXT Error"):
                        await execute_order(
                            mock_signal, mock_ccxt_exchange, mock_postgres_pool, mock_redis_client
                        )
    
    @pytest.mark.asyncio
    async def test_execute_order_database_disabled(self, mock_signal, mock_ccxt_exchange, 
                                               mock_postgres_pool, mock_redis_client):
        """测试数据库禁用时的执行"""
        with patch.dict(os.environ, {
            'OKX_ENVIRONMENT': 'demo',
            'USE_DATABASE': 'false'
        }):
            with patch('src.executor.main.validate_order_signal') as mock_validate:
                mock_validate.return_value = True
                
                with patch('src.executor.main.track') as mock_track:
                    mock_track.return_value = AsyncMock()
                    
                    result = await execute_order(
                        mock_signal, mock_ccxt_exchange, mock_postgres_pool, mock_redis_client
                    )
                    
                    # 验证结果
                    assert result['id'] == 'order_123'
                    
                    # 验证数据库操作被跳过
                    mock_postgres_pool.execute.assert_not_called()
                    
                    # 验证其他操作正常执行
                    mock_ccxt_exchange.create_market_order.assert_called_once()
                    mock_redis_client.publish.assert_called_once()
                    mock_track.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_order_database_error_continues(self, mock_signal, mock_ccxt_exchange, 
                                                        mock_postgres_pool, mock_redis_client, mock_snapshot):
        """测试数据库错误时继续执行"""
        with patch.dict(os.environ, {
            'OKX_ENVIRONMENT': 'demo',
            'USE_DATABASE': 'true'
        }):
            with patch('src.executor.main.DataHandler') as mock_data_handler_class:
                mock_data_handler = Mock()
                mock_data_handler.get_snapshot.return_value = mock_snapshot
                mock_data_handler_class.return_value = mock_data_handler
                
                with patch('src.executor.main.validate_order_signal') as mock_validate:
                    mock_validate.return_value = True
                    
                    # 模拟数据库错误
                    mock_postgres_pool.execute.side_effect = Exception("Database error")
                    
                    with patch('src.executor.main.track') as mock_track:
                        mock_track.return_value = AsyncMock()
                        
                        result = await execute_order(
                            mock_signal, mock_ccxt_exchange, mock_postgres_pool, mock_redis_client
                        )
                        
                        # 验证仍然成功执行
                        assert result['id'] == 'order_123'
                        
                        # 验证其他操作正常执行
                        mock_ccxt_exchange.create_market_order.assert_called_once()
                        mock_redis_client.publish.assert_called_once()
                        mock_track.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_order_redis_error_continues(self, mock_signal, mock_ccxt_exchange, 
                                                    mock_postgres_pool, mock_redis_client, mock_snapshot):
        """测试Redis错误时继续执行"""
        with patch.dict(os.environ, {
            'OKX_ENVIRONMENT': 'demo',
            'USE_DATABASE': 'true'
        }):
            with patch('src.executor.main.DataHandler') as mock_data_handler_class:
                mock_data_handler = Mock()
                mock_data_handler.get_snapshot.return_value = mock_snapshot
                mock_data_handler_class.return_value = mock_data_handler
                
                with patch('src.executor.main.validate_order_signal') as mock_validate:
                    mock_validate.return_value = True
                    
                    # 模拟Redis错误
                    mock_redis_client.publish.side_effect = Exception("Redis error")
                    
                    with patch('src.executor.main.track') as mock_track:
                        mock_track.return_value = AsyncMock()
                        
                        result = await execute_order(
                            mock_signal, mock_ccxt_exchange, mock_postgres_pool, mock_redis_client
                        )
                        
                        # 验证仍然成功执行
                        assert result['id'] == 'order_123'
                        
                        # 验证其他操作正常执行
                        mock_ccxt_exchange.create_market_order.assert_called_once()
                        mock_postgres_pool.execute.assert_called_once()
                        mock_track.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_order_tracking_error_continues(self, mock_signal, mock_ccxt_exchange, 
                                                       mock_postgres_pool, mock_redis_client, mock_snapshot):
        """测试跟踪错误时继续执行"""
        with patch.dict(os.environ, {
            'OKX_ENVIRONMENT': 'demo',
            'USE_DATABASE': 'true'
        }):
            with patch('src.executor.main.DataHandler') as mock_data_handler_class:
                mock_data_handler = Mock()
                mock_data_handler.get_snapshot.return_value = mock_snapshot
                mock_data_handler_class.return_value = mock_data_handler
                
                with patch('src.executor.main.validate_order_signal') as mock_validate:
                    mock_validate.return_value = True
                    
                    with patch('src.executor.main.track') as mock_track:
                        mock_track.side_effect = Exception("Tracking error")
                        
                        result = await execute_order(
                            mock_signal, mock_ccxt_exchange, mock_postgres_pool, mock_redis_client
                        )
                        
                        # 验证仍然成功执行
                        assert result['id'] == 'order_123'
                        
                        # 验证其他操作正常执行
                        mock_ccxt_exchange.create_market_order.assert_called_once()
                        mock_postgres_pool.execute.assert_called_once()
                        mock_redis_client.publish.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_order_no_postgres_pool(self, mock_signal, mock_ccxt_exchange, 
                                                 mock_redis_client, mock_snapshot):
        """测试没有PostgreSQL连接池时的执行"""
        with patch.dict(os.environ, {
            'OKX_ENVIRONMENT': 'demo',
            'USE_DATABASE': 'true'
        }):
            with patch('src.executor.main.DataHandler') as mock_data_handler_class:
                mock_data_handler = Mock()
                mock_data_handler.get_snapshot.return_value = mock_snapshot
                mock_data_handler_class.return_value = mock_data_handler
                
                with patch('src.executor.main.validate_order_signal') as mock_validate:
                    mock_validate.return_value = True
                    
                    with patch('src.executor.main.track') as mock_track:
                        mock_track.return_value = AsyncMock()
                        
                        result = await execute_order(
                            mock_signal, mock_ccxt_exchange, None, mock_redis_client
                        )
                        
                        # 验证仍然成功执行
                        assert result['id'] == 'order_123'
                        
                        # 验证其他操作正常执行
                        mock_ccxt_exchange.create_market_order.assert_called_once()
                        mock_redis_client.publish.assert_called_once()
                        mock_track.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_order_no_redis_client(self, mock_signal, mock_ccxt_exchange, 
                                               mock_postgres_pool, mock_snapshot):
        """测试没有Redis客户端时的执行"""
        with patch.dict(os.environ, {
            'OKX_ENVIRONMENT': 'demo',
            'USE_DATABASE': 'true'
        }):
            with patch('src.executor.main.DataHandler') as mock_data_handler_class:
                mock_data_handler = Mock()
                mock_data_handler.get_snapshot.return_value = mock_snapshot
                mock_data_handler_class.return_value = mock_data_handler
                
                with patch('src.executor.main.validate_order_signal') as mock_validate:
                    mock_validate.return_value = True
                    
                    with patch('src.executor.main.track') as mock_track:
                        mock_track.return_value = AsyncMock()
                        
                        result = await execute_order(
                            mock_signal, mock_ccxt_exchange, mock_postgres_pool, None
                        )
                        
                        # 验证仍然成功执行
                        assert result['id'] == 'order_123'
                        
                        # 验证其他操作正常执行
                        mock_ccxt_exchange.create_market_order.assert_called_once()
                        mock_postgres_pool.execute.assert_called_once()
                        mock_track.assert_called_once()


class TestExecutorMain:
    """Executor主模块其他功能测试"""
    
    def test_main_execution(self):
        """测试主函数执行"""
        with patch('src.executor.main.uvicorn.run') as mock_uvicorn:
            with patch('src.executor.main.get_config_manager') as mock_config_manager:
                mock_config = Mock()
                mock_config.get_config.return_value = {
                    'services': {
                        'executor': {
                            'host': 'localhost',
                            'port': 8003
                        }
                    }
                }
                mock_config_manager.return_value = mock_config
                
                # 模拟命令行执行
                with patch('sys.argv', ['main.py']):
                    with patch('src.executor.main.app'):
                        try:
                            from src.executor.main import __main__
                        except SystemExit:
                            pass  # uvicorn.run会调用sys.exit()
                        
                        # 验证uvicorn.run被调用
                        mock_uvicorn.assert_called_once()
    
    def test_main_fallback_to_env_vars(self):
        """测试回退到环境变量"""
        with patch('src.executor.main.uvicorn.run') as mock_uvicorn:
            with patch('src.executor.main.get_config_manager') as mock_config_manager:
                mock_config_manager.side_effect = Exception("Config error")
                
                with patch.dict(os.environ, {
                    'SERVICE_HOST': '0.0.0.0',
                    'SERVICE_PORT': '8003'
                }):
                    with patch('src.executor.main.app'):
                        try:
                            from src.executor.main import __main__
                        except SystemExit:
                            pass
                        
                        # 验证使用环境变量
                        mock_uvicorn.assert_called_once()
    
    def test_main_keyboard_interrupt(self):
        """测试键盘中断"""
        with patch('src.executor.main.uvicorn.run') as mock_uvicorn:
            mock_uvicorn.side_effect = KeyboardInterrupt()
            
            with patch('src.executor.main.get_config_manager'):
                with patch('src.executor.main.app'):
                    try:
                        from src.executor.main import __main__
                    except SystemExit:
                        pass
                    
                    # 验证优雅退出
                    mock_uvicorn.assert_called_once()
    
    def test_main_exception(self):
        """测试主函数异常"""
        with patch('src.executor.main.uvicorn.run') as mock_uvicorn:
            mock_uvicorn.side_effect = Exception("Server error")
            
            with patch('src.executor.main.get_config_manager'):
                with patch('src.executor.main.app'):
                    with pytest.raises(Exception, match="Server error"):
                        from src.executor.main import __main__


class TestExecutorIntegration:
    """Executor集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_order_execution_workflow(self):
        """测试完整订单执行工作流"""
        # 准备测试数据
        signal = {
            'symbol': 'BTC-USDT',
            'action': 'buy',
            'size': 0.001,
            'side': 'buy',
            'decision_id': 'test_decision_123'
        }
        
        mock_exchange = Mock()
        mock_exchange.create_market_order.return_value = {
            'id': 'order_123',
            'symbol': 'BTC-USDT',
            'side': 'buy',
            'amount': 0.001,
            'status': 'open'
        }
        
        mock_pool = AsyncMock()
        mock_redis = AsyncMock()
        
        with patch.dict(os.environ, {
            'OKX_ENVIRONMENT': 'demo',
            'USE_DATABASE': 'true'
        }):
            with patch('src.executor.main.DataHandler') as mock_data_handler_class:
                mock_data_handler = Mock()
                mock_data_handler.get_snapshot.return_value = {
                    'symbol': 'BTC-USDT',
                    'klines': [[1609459200000, 50000, 50100, 49900, 50050, 100]],
                    'indicators': {'rsi': 50},
                    'account': {'balance': {'BTC': 1.0}, 'positions': []},
                    'data_status': 'OK'
                }
                mock_data_handler_class.return_value = mock_data_handler
                
                with patch('src.executor.main.validate_order_signal') as mock_validate:
                    mock_validate.return_value = True
                    
                    with patch('src.executor.main.track') as mock_track:
                        mock_track.return_value = AsyncMock()
                        
                        result = await execute_order(signal, mock_exchange, mock_pool, mock_redis)
                        
                        # 验证完整工作流
                        assert result['id'] == 'order_123'
                        
                        # 验证所有步骤都被调用
                        mock_data_handler.get_snapshot.assert_called_once_with('BTC-USDT')
                        mock_validate.assert_called_once()
                        mock_exchange.create_market_order.assert_called_once()
                        mock_pool.execute.assert_called_once()
                        mock_redis.publish.assert_called_once()
                        mock_track.assert_called_once()
                        
                        # 验证数据库插入参数
                        insert_call = mock_pool.execute.call_args
                        assert insert_call[0][0]  # SQL语句
                        assert insert_call[0][1] == 'test_decision_123'  # decision_id
                        assert insert_call[0][2] == 'order_123'  # order_id
                        assert insert_call[0][3] == 'BTC-USDT'  # symbol
                        assert insert_call[0][4] == 'buy'  # side
                        assert insert_call[0][5] == 'market'  # order_type
                        assert insert_call[0][6] == 0.001  # amount
                        assert insert_call[0][7] is None  # price
                        assert insert_call[0][8] == 'open'  # status
                        
                        # 验证Redis发布参数
                        publish_call = mock_redis.publish.call_args
                        assert publish_call[0][0] == 'new_position_opened'
                        message = json.loads(publish_call[0][1])
                        assert message['symbol'] == 'BTC-USDT'
                        assert message['order_id'] == 'order_123'
