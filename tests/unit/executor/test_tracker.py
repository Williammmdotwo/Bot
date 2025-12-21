"""
Executor跟踪器模块单元测试
覆盖executor/tracker.py的核心功能
"""

import pytest
import asyncio
import os
from unittest.mock import Mock, patch, AsyncMock

# 导入测试目标
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../..'))

from src.executor.tracker import track, _order_tracking_loop


class TestOrderTrackingLoop:
    """_order_tracking_loop函数测试"""
    
    @pytest.fixture
    def mock_ccxt_exchange(self):
        """模拟CCXT交易所实例"""
        mock_exchange = Mock()
        mock_exchange.fetch_order.return_value = {
            'id': 'order_123',
            'status': 'closed',
            'filled': 0.001,
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
    
    @pytest.mark.asyncio
    async def test_order_tracking_loop_success_closed(self, mock_ccxt_exchange, mock_postgres_pool):
        """测试订单跟踪成功 - 订单已关闭"""
        with patch('asyncio.sleep', side_effect=[None, StopIteration]) as mock_sleep:
            with patch('src.executor.tracker.logger') as mock_logger:
                try:
                    await _order_tracking_loop('order_123', mock_ccxt_exchange, mock_postgres_pool)
                except StopIteration:
                    pass  # 正常退出
                
                # 验证订单状态查询
                mock_ccxt_exchange.fetch_order.assert_called_once_with('order_123')
                
                # 验证数据库更新
                mock_postgres_pool.execute.assert_called_once()
                call_args = mock_postgres_pool.execute.call_args
                assert call_args[0][0]  # SQL语句
                assert call_args[0][1] == 0.001  # filled_amount
                assert call_args[0][2] == 50000.0  # filled_price
                assert call_args[0][3] == 0.0001  # fee
                assert call_args[0][4] == 'closed'  # status
                assert call_args[0][5] == 'order_123'  # order_id
                
                # 验证日志记录
                mock_logger.info.assert_called()
    
    @pytest.mark.asyncio
    async def test_order_tracking_loop_success_canceled(self, mock_ccxt_exchange, mock_postgres_pool):
        """测试订单跟踪成功 - 订单已取消"""
        mock_ccxt_exchange.fetch_order.return_value = {
            'id': 'order_123',
            'status': 'canceled',
            'filled': 0.0,
            'price': 0.0,
            'fee': {'cost': 0.0}
        }
        
        with patch('asyncio.sleep', side_effect=[None, StopIteration]) as mock_sleep:
            with patch('src.executor.tracker.logger') as mock_logger:
                try:
                    await _order_tracking_loop('order_123', mock_ccxt_exchange, mock_postgres_pool)
                except StopIteration:
                    pass  # 正常退出
                
                # 验证订单状态查询
                mock_ccxt_exchange.fetch_order.assert_called_once_with('order_123')
                
                # 验证数据库更新
                mock_postgres_pool.execute.assert_called_once()
                call_args = mock_postgres_pool.execute.call_args
                assert call_args[0][4] == 'canceled'  # status
    
    @pytest.mark.asyncio
    async def test_order_tracking_loop_open_status_continues(self, mock_ccxt_exchange, mock_postgres_pool):
        """测试订单跟踪 - 订单仍开放状态"""
        mock_ccxt_exchange.fetch_order.return_value = {
            'id': 'order_123',
            'status': 'open',
            'filled': 0.0005,
            'price': 50000.0,
            'fee': {'cost': 0.00005}
        }
        
        with patch('asyncio.sleep', side_effect=[None, StopIteration]) as mock_sleep:
            with patch('src.executor.tracker.logger') as mock_logger:
                try:
                    await _order_tracking_loop('order_123', mock_ccxt_exchange, mock_postgres_pool)
                except StopIteration:
                    pass  # 模拟退出
                
                # 验证订单状态查询
                mock_ccxt_exchange.fetch_order.assert_called_once_with('order_123')
                
                # 验证数据库更新
                mock_postgres_pool.execute.assert_called_once()
                call_args = mock_postgres_pool.execute.call_args
                assert call_args[0][4] == 'open'  # status
                
                # 验证sleep被调用
                mock_sleep.assert_called_once_with(5)
    
    @pytest.mark.asyncio
    async def test_order_tracking_loop_multiple_iterations(self, mock_ccxt_exchange, mock_postgres_pool):
        """测试订单跟踪 - 多次迭代"""
        # 第一次返回open，第二次返回closed
        mock_ccxt_exchange.fetch_order.side_effect = [
            {
                'id': 'order_123',
                'status': 'open',
                'filled': 0.0005,
                'price': 50000.0,
                'fee': {'cost': 0.00005}
            },
            {
                'id': 'order_123',
                'status': 'closed',
                'filled': 0.001,
                'price': 50000.0,
                'fee': {'cost': 0.0001}
            }
        ]
        
        with patch('asyncio.sleep', side_effect=[None, None, StopIteration]) as mock_sleep:
            with patch('src.executor.tracker.logger') as mock_logger:
                try:
                    await _order_tracking_loop('order_123', mock_ccxt_exchange, mock_postgres_pool)
                except StopIteration:
                    pass  # 正常退出
                
                # 验证订单状态查询被调用两次
                assert mock_ccxt_exchange.fetch_order.call_count == 2
                
                # 验证数据库更新被调用两次
                assert mock_postgres_pool.execute.call_count == 2
                
                # 验证sleep被调用两次
                assert mock_sleep.call_count == 2
    
    @pytest.mark.asyncio
    async def test_order_tracking_loop_exchange_error_continues(self, mock_ccxt_exchange, mock_postgres_pool):
        """测试订单跟踪 - 交易所错误时继续"""
        mock_ccxt_exchange.fetch_order.side_effect = [
            Exception("Exchange error"),
            {
                'id': 'order_123',
                'status': 'closed',
                'filled': 0.001,
                'price': 50000.0,
                'fee': {'cost': 0.0001}
            }
        ]
        
        with patch('asyncio.sleep', side_effect=[None, None, StopIteration]) as mock_sleep:
            with patch('src.executor.tracker.logger') as mock_logger:
                try:
                    await _order_tracking_loop('order_123', mock_ccxt_exchange, mock_postgres_pool)
                except StopIteration:
                    pass  # 正常退出
                
                # 验证订单状态查询被调用两次
                assert mock_ccxt_exchange.fetch_order.call_count == 2
                
                # 验证数据库更新被调用一次（第二次成功时）
                assert mock_postgres_pool.execute.call_count == 1
                
                # 验证错误日志
                mock_logger.error.assert_called()
    
    @pytest.mark.asyncio
    async def test_order_tracking_loop_database_error_continues(self, mock_ccxt_exchange, mock_postgres_pool):
        """测试订单跟踪 - 数据库错误时继续"""
        mock_ccxt_exchange.fetch_order.return_value = {
            'id': 'order_123',
            'status': 'closed',
            'filled': 0.001,
            'price': 50000.0,
            'fee': {'cost': 0.0001}
        }
        
        # 模拟数据库错误
        mock_postgres_pool.execute.side_effect = Exception("Database error")
        
        with patch('asyncio.sleep', side_effect=[None, StopIteration]) as mock_sleep:
            with patch('src.executor.tracker.logger') as mock_logger:
                try:
                    await _order_tracking_loop('order_123', mock_ccxt_exchange, mock_postgres_pool)
                except StopIteration:
                    pass  # 正常退出
                
                # 验证订单状态查询被调用
                mock_ccxt_exchange.fetch_order.assert_called_once_with('order_123')
                
                # 验证数据库更新被调用（即使失败）
                mock_postgres_pool.execute.assert_called_once()
                
                # 验证错误日志
                mock_logger.error.assert_called()
    
    @pytest.mark.asyncio
    async def test_order_tracking_loop_missing_fee(self, mock_ccxt_exchange, mock_postgres_pool):
        """测试订单跟踪 - 缺少费用信息"""
        mock_ccxt_exchange.fetch_order.return_value = {
            'id': 'order_123',
            'status': 'closed',
            'filled': 0.001,
            'price': 50000.0
            # 没有fee字段
        }
        
        with patch('asyncio.sleep', side_effect=[None, StopIteration]) as mock_sleep:
            with patch('src.executor.tracker.logger') as mock_logger:
                try:
                    await _order_tracking_loop('order_123', mock_ccxt_exchange, mock_postgres_pool)
                except StopIteration:
                    pass  # 正常退出
                
                # 验证数据库更新使用默认值
                mock_postgres_pool.execute.assert_called_once()
                call_args = mock_postgres_pool.execute.call_args
                assert call_args[0][3] == 0  # fee默认为0
    
    @pytest.mark.asyncio
    async def test_order_tracking_loop_zero_filled_amount(self, mock_ccxt_exchange, mock_postgres_pool):
        """测试订单跟踪 - 成交量为0"""
        mock_ccxt_exchange.fetch_order.return_value = {
            'id': 'order_123',
            'status': 'closed',
            'filled': 0,
            'price': 0,
            'fee': {'cost': 0}
        }
        
        with patch('asyncio.sleep', side_effect=[None, StopIteration]) as mock_sleep:
            with patch('src.executor.tracker.logger') as mock_logger:
                try:
                    await _order_tracking_loop('order_123', mock_ccxt_exchange, mock_postgres_pool)
                except StopIteration:
                    pass  # 正常退出
                
                # 验证数据库更新使用0值
                mock_postgres_pool.execute.assert_called_once()
                call_args = mock_postgres_pool.execute.call_args
                assert call_args[0][1] == 0  # filled_amount
                assert call_args[0][2] == 0  # filled_price
                assert call_args[0][3] == 0  # fee


class TestTrack:
    """track函数测试"""
    
    @pytest.fixture
    def mock_ccxt_exchange(self):
        """模拟CCXT交易所实例"""
        return Mock()
    
    @pytest.fixture
    def mock_postgres_pool(self):
        """模拟PostgreSQL连接池"""
        return AsyncMock()
    
    @pytest.mark.asyncio
    async def test_track_success(self, mock_ccxt_exchange, mock_postgres_pool):
        """测试创建跟踪任务成功"""
        with patch('asyncio.create_task') as mock_create_task:
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task
            
            with patch('src.executor.tracker.logger') as mock_logger:
                result = await track('order_123', mock_ccxt_exchange, mock_postgres_pool)
                
                # 验证返回任务
                assert result == mock_task
                
                # 验证创建任务
                mock_create_task.assert_called_once()
                
                # 验证日志记录
                mock_logger.info.assert_called_once_with("Starting background tracking for order order_123")
    
    @pytest.mark.asyncio
    async def test_track_different_order_ids(self, mock_ccxt_exchange, mock_postgres_pool):
        """测试不同订单ID的跟踪"""
        order_ids = ['order_1', 'order_2', 'order_123', 'order_abc']
        
        with patch('asyncio.create_task') as mock_create_task:
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task
            
            with patch('src.executor.tracker.logger') as mock_logger:
                for order_id in order_ids:
                    result = await track(order_id, mock_ccxt_exchange, mock_postgres_pool)
                    
                    # 验证返回任务
                    assert result == mock_task
                    
                    # 验证创建任务
                    mock_create_task.assert_called()
                    
                    # 验证日志记录
                    mock_logger.info.assert_called_with(f"Starting background tracking for order {order_id}")
    
    @pytest.mark.asyncio
    async def test_track_task_creation_parameters(self, mock_ccxt_exchange, mock_postgres_pool):
        """测试任务创建参数"""
        with patch('asyncio.create_task') as mock_create_task:
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task
            
            with patch('src.executor.tracker.logger'):
                result = await track('order_123', mock_ccxt_exchange, mock_postgres_pool)
                
                # 验证任务创建参数
                mock_create_task.assert_called_once()
                call_args = mock_create_task.call_args[0][0]
                
                # 验证协程函数
                assert asyncio.iscoroutinefunction(call_args)
    
    @pytest.mark.asyncio
    async def test_track_with_different_exchanges(self, mock_postgres_pool):
        """测试不同交易所的跟踪"""
        exchanges = [Mock() for _ in range(3)]
        
        with patch('asyncio.create_task') as mock_create_task:
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task
            
            with patch('src.executor.tracker.logger'):
                for i, exchange in enumerate(exchanges):
                    result = await track(f'order_{i}', exchange, mock_postgres_pool)
                    
                    # 验证返回任务
                    assert result == mock_task
                    
                    # 验证创建任务
                    assert mock_create_task.call_count == i + 1
    
    @pytest.mark.asyncio
    async def test_track_with_different_pools(self, mock_ccxt_exchange):
        """测试不同连接池的跟踪"""
        pools = [AsyncMock() for _ in range(3)]
        
        with patch('asyncio.create_task') as mock_create_task:
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task
            
            with patch('src.executor.tracker.logger'):
                for i, pool in enumerate(pools):
                    result = await track(f'order_{i}', mock_ccxt_exchange, pool)
                    
                    # 验证返回任务
                    assert result == mock_task
                    
                    # 验证创建任务
                    assert mock_create_task.call_count == i + 1


class TestTrackerIntegration:
    """跟踪器集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_tracking_workflow(self):
        """测试完整跟踪工作流"""
        # 模拟订单状态变化
        order_status_sequence = [
            {'status': 'open', 'filled': 0.0, 'price': 0.0, 'fee': {'cost': 0.0}},
            {'status': 'open', 'filled': 0.0005, 'price': 50000.0, 'fee': {'cost': 0.00005}},
            {'status': 'closed', 'filled': 0.001, 'price': 50000.0, 'fee': {'cost': 0.0001}}
        ]
        
        mock_exchange = Mock()
        mock_exchange.fetch_order.side_effect = order_status_sequence
        
        mock_pool = AsyncMock()
        mock_pool.execute = AsyncMock()
        
        # 创建跟踪任务
        with patch('asyncio.create_task') as mock_create_task:
            # 直接调用跟踪循环来测试
            with patch('asyncio.sleep', side_effect=[None, None, StopIteration]):
                with patch('src.executor.tracker.logger') as mock_logger:
                    try:
                        await _order_tracking_loop('order_123', mock_exchange, mock_pool)
                    except StopIteration:
                        pass  # 正常退出
                    
                    # 验证订单状态查询次数
                    assert mock_exchange.fetch_order.call_count == 3
                    
                    # 验证数据库更新次数
                    assert mock_pool.execute.call_count == 3
                    
                    # 验证最后一次更新是closed状态
                    last_call = mock_pool.execute.call_args_list[-1]
                    assert last_call[0][4] == 'closed'
                    assert last_call[0][1] == 0.001  # 最终成交数量
                    
                    # 验证日志记录
                    assert mock_logger.info.call_count >= 3
    
    @pytest.mark.asyncio
    async def test_tracking_with_error_recovery(self):
        """测试错误恢复"""
        # 模拟错误和恢复
        mock_exchange = Mock()
        mock_exchange.fetch_order.side_effect = [
            Exception("Network error"),
            {'status': 'open', 'filled': 0.0, 'price': 0.0, 'fee': {'cost': 0.0}},
            Exception("Database error"),  # 这会在数据库更新时发生
            {'status': 'closed', 'filled': 0.001, 'price': 50000.0, 'fee': {'cost': 0.0001}}
        ]
        
        mock_pool = AsyncMock()
        mock_pool.execute.side_effect = [
            None,  # 第一次成功
            Exception("Database error"),  # 第二次失败
            None   # 第三次成功
        ]
        
        with patch('asyncio.sleep', side_effect=[None, None, None, StopIteration]):
            with patch('src.executor.tracker.logger') as mock_logger:
                try:
                    await _order_tracking_loop('order_123', mock_exchange, mock_pool)
                except StopIteration:
                    pass  # 正常退出
                
                # 验证最终成功
                assert mock_exchange.fetch_order.call_count == 4
                assert mock_pool.execute.call_count == 3
                
                # 验证错误日志
                assert mock_logger.error.call_count >= 2  # 网络错误 + 数据库错误
    
    @pytest.mark.asyncio
    async def test_track_and_loop_integration(self):
        """测试track函数和循环的集成"""
        mock_exchange = Mock()
        mock_exchange.fetch_order.return_value = {
            'status': 'closed',
            'filled': 0.001,
            'price': 50000.0,
            'fee': {'cost': 0.0001}
        }
        
        mock_pool = AsyncMock()
        mock_pool.execute = AsyncMock()
        
        # 创建真实的任务
        with patch('src.executor.tracker.logger'):
            task = await track('order_123', mock_exchange, mock_pool)
            
            # 验证返回的是任务对象
            assert hasattr(task, 'cancel')  # asyncio.Task应该有cancel方法
            
            # 取消任务以避免无限循环
            task.cancel()
            
            # 等待一小段时间让任务开始
            await asyncio.sleep(0.01)
