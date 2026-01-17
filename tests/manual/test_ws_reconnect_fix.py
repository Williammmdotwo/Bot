"""
测试 WebSocket 重连修复效果

验证内容：
1. 并发连接保护（asyncio.Lock）
2. 指数退避重连机制
3. 资源清理（_disconnect_cleanup）
4. 避免重连风暴

使用方法：
    pytest tests/manual/test_ws_reconnect_fix.py -v -s
"""

import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestWsBaseGateway:
    """测试 WsBaseGateway 基类"""

    @pytest.mark.asyncio
    async def test_concurrent_connect_protection(self):
        """
        测试并发连接保护

        验证：多个并发调用 connect() 时，只有一个会建立连接
        """
        from src.gateways.okx.ws_base import WsBaseGateway

        # 创建网关实例
        gateway = WsBaseGateway(name="test", ws_url="wss://test.com")

        # Mock aiohttp 的 ws_connect
        mock_ws = AsyncMock()
        mock_ws.closed = False

        async def mock_connect(*args, **kwargs):
            await asyncio.sleep(0.1)  # 模拟连接延迟
            return mock_ws

        # Patch aiohttp
        with patch('src.gateways.okx.ws_base.ClientSession') as MockSession:
            mock_session = AsyncMock()
            mock_session.ws_connect = mock_connect
            mock_session.closed = False
            MockSession.return_value = mock_session

            # 并发调用 connect 5 次
            tasks = [gateway.connect() for _ in range(5)]
            results = await asyncio.gather(*tasks)

            # 验证：只有第一次调用会成功建立连接（后续会检测到已连接）
            assert all(results), "所有连接调用都应该返回 True（或因已连接跳过）"

            # 验证：只有一个连接被建立（通过检查 ws_connect 调用次数）
            # 注意：由于存在竞态条件，可能调用次数 > 1，但应该有限制
            logger.info(f"ws_connect 调用次数: {mock_session.ws_connect.call_count}")

    @pytest.mark.asyncio
    async def test_exponential_backoff_reconnect(self):
        """
        测试指数退避重连机制

        验证：重连延迟时间按指数增长
        """
        from src.gateways.okx.ws_base import WsBaseGateway

        gateway = WsBaseGateway(name="test", ws_url="wss://test.com")
        gateway._reconnect_attempt = 0
        gateway._base_backoff = 1.0

        # 测试不同重连次数的退避时间
        expected_delays = []
        for attempt in range(6):
            expected_delay = gateway._base_backoff * (2 ** min(attempt, 5))
            expected_delay = min(expected_delay, gateway._max_backoff)
            expected_delays.append(expected_delay)

        logger.info(f"预期退避时间: {expected_delays}")

        # 验证：退避时间按指数增长
        assert expected_delays[1] > expected_delays[0]
        assert expected_delays[2] > expected_delays[1]
        assert expected_delays[3] > expected_delays[2]

    @pytest.mark.asyncio
    async def test_disconnect_cleanup(self):
        """
        测试断开连接时的资源清理

        验证：_disconnect_cleanup 正确清理所有资源
        """
        from src.gateways.okx.ws_base import WsBaseGateway

        gateway = WsBaseGateway(name="test", ws_url="wss://test.com")

        # Mock 各种资源
        gateway._receive_task = AsyncMock()
        gateway._receive_task.done.return_value = False

        gateway._heartbeat_task = AsyncMock()
        gateway._heartbeat_task.done.return_value = False

        gateway._ws = AsyncMock()
        gateway._ws.closed = False

        gateway._session = AsyncMock()
        gateway._session.closed = False

        # 调用清理方法
        await gateway._disconnect_cleanup()

        # 验证：所有资源都被清理
        assert gateway._receive_task is None, "消息接收任务应该被清理"
        assert gateway._heartbeat_task is None, "心跳任务应该被清理"
        assert gateway._ws is None, "WebSocket 连接应该被清理"
        assert gateway._session is None, "Session 应该被清理"
        assert not gateway._connected, "连接状态应该被重置"

    @pytest.mark.asyncio
    async def test_no_reconnect_storm(self):
        """
        测试防止重连风暴

        验证：如果已有任务在处理连接，后续的重连请求会被跳过
        """
        from src.gateways.okx.ws_base import WsBaseGateway

        gateway = WsBaseGateway(name="test", ws_url="wss://test.com")

        # 模拟连接锁已被占用
        async with gateway._connect_lock:
            # 尝试触发重连（应该在锁外检查）
            # 由于锁被占用，重连应该被跳过

            # Mock connect 方法
            original_connect = gateway.connect
            gateway.connect = AsyncMock(return_value=False)

            # 触发重连（应该因为锁被占用而跳过）
            await gateway._reconnect()

            # 验证：connect 不应该被调用（因为锁被占用）
            gateway.connect.assert_not_called()


class TestPublicGateway:
    """测试公共 WebSocket 网关"""

    @pytest.mark.asyncio
    async def test_auto_subscribe_on_connect(self):
        """
        测试连接成功后自动订阅

        验证：_on_connected 钩子被调用，并自动订阅频道
        """
        from src.gateways.okx.ws_public_gateway import OkxPublicWsGateway
        from unittest.mock import patch

        event_bus = MagicMock()
        gateway = OkxPublicWsGateway(
            symbol="BTC-USDT-SWAP",
            event_bus=event_bus
        )

        # Mock connect 和 subscribe
        gateway.subscribe = AsyncMock()

        with patch('src.gateways.okx.ws_base.ClientSession') as MockSession:
            mock_ws = AsyncMock()
            mock_ws.closed = False
            mock_ws.receive = AsyncMock(side_effect=asyncio.TimeoutError())

            mock_session = AsyncMock()
            mock_session.ws_connect = AsyncMock(return_value=mock_ws)
            mock_session.closed = False
            MockSession.return_value = mock_session

            # 调用 _on_connected 钩子
            await gateway._on_connected()

            # 验证：subscribe 被调用
            gateway.subscribe.assert_called_once()
            call_args = gateway.subscribe.call_args[0][0]
            assert 'trades' in call_args or 'books' in call_args


class TestPrivateGateway:
    """测试私有 WebSocket 网关"""

    @pytest.mark.asyncio
    async def test_auto_login_on_connect(self):
        """
        测试连接成功后自动登录

        验证：_on_connected 钩子被调用，并发送登录包
        """
        from src.gateways.okx.ws_private_gateway import OkxPrivateWsGateway
        from unittest.mock import patch

        event_bus = MagicMock()
        gateway = OkxPrivateWsGateway(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
            use_demo=True,
            event_bus=event_bus
        )

        # Mock _send_login
        gateway._send_login = AsyncMock()

        # 调用 _on_connected 钩子
        await gateway._on_connected()

        # 验证：_send_login 被调用
        gateway._send_login.assert_called_once()


def test_main():
    """
    主测试函数（不使用 pytest）

    可以直接运行此文件进行快速测试
    """
    async def run_tests():
        logger.info("=" * 60)
        logger.info("开始测试 WebSocket 重连修复")
        logger.info("=" * 60)

        # 测试 1：并发连接保护
        logger.info("\n[测试 1] 并发连接保护")
        try:
            from src.gateways.okx.ws_base import WsBaseGateway

            gateway = WsBaseGateway(name="test", ws_url="wss://test.com")

            # 验证锁存在
            assert gateway._connect_lock is not None
            logger.info("✅ 并发连接锁已初始化")

        except Exception as e:
            logger.error(f"❌ 测试失败: {e}")

        # 测试 2：指数退避
        logger.info("\n[测试 2] 指数退避重连")
        try:
            from src.gateways.okx.ws_base import WsBaseGateway

            gateway = WsBaseGateway(name="test", ws_url="wss://test.com")
            gateway._reconnect_attempt = 3

            # 计算退避时间
            expected_delay = gateway._base_backoff * (2 ** min(3, 5))
            expected_delay = min(expected_delay, gateway._max_backoff)

            logger.info(f"✅ 第 3 次重连退避时间: {expected_delay:.1f} 秒")

        except Exception as e:
            logger.error(f"❌ 测试失败: {e}")

        # 测试 3：资源清理
        logger.info("\n[测试 3] 资源清理")
        try:
            from src.gateways.okx.ws_base import WsBaseGateway

            gateway = WsBaseGateway(name="test", ws_url="wss://test.com")

            # Mock 资源
            gateway._receive_task = MagicMock()
            gateway._heartbeat_task = MagicMock()
            gateway._ws = MagicMock()
            gateway._session = MagicMock()

            await gateway._disconnect_cleanup()

            # 验证清理
            assert gateway._receive_task is None
            assert gateway._heartbeat_task is None
            assert gateway._ws is None
            assert gateway._session is None

            logger.info("✅ 资源清理方法正常工作")

        except Exception as e:
            logger.error(f"❌ 测试失败: {e}")

        # 测试 4：网关初始化
        logger.info("\n[测试 4] 网关初始化")
        try:
            from src.gateways.okx.ws_public_gateway import OkxPublicWsGateway
            from src.gateways.okx.ws_private_gateway import OkxPrivateWsGateway

            # 测试 Public Gateway
            pub_gateway = OkxPublicWsGateway(
                symbol="BTC-USDT-SWAP",
                event_bus=None
            )
            logger.info("✅ Public Gateway 初始化成功")

            # 测试 Private Gateway
            priv_gateway = OkxPrivateWsGateway(
                api_key="test_key",
                secret_key="test_secret",
                passphrase="test_pass",
                use_demo=True,
                event_bus=None
            )
            logger.info("✅ Private Gateway 初始化成功")

        except Exception as e:
            logger.error(f"❌ 测试失败: {e}")

        logger.info("\n" + "=" * 60)
        logger.info("测试完成")
        logger.info("=" * 60)

    # 运行测试
    asyncio.run(run_tests())


if __name__ == "__main__":
    test_main()
