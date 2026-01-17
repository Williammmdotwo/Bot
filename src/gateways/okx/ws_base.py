"""
WebSocket 基类 (WebSocket Base Gateway)

OKX WebSocket 连接的基类，提供：
- 自动重连机制（指数退避）
- 心跳保活
- 并发连接保护（asyncio.Lock）
- 资源清理机制

修复内容：
- 🔥 引入 asyncio.Lock 防止并发竞争
- 🔥 实现 _disconnect_cleanup 强制清理旧资源
- 🔥 修复消息循环，避免阻塞重连
- 🔥 实现指数退避重连策略（Exponential Backoff）

使用 aiohttp ClientWebSocketResponse（与现有代码兼容）
"""

import asyncio
import json
import logging
import time
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from aiohttp import ClientSession, WSMessage, ClientError

logger = logging.getLogger(__name__)


class WsBaseGateway:
    """
    WebSocket 基类（使用 aiohttp）

    提供标准的 WebSocket 连接管理，包括：
    - 自动重连（指数退避）
    - 心跳保活
    - 并发连接保护
    - 资源清理
    """

    def __init__(self, name: str, ws_url: Optional[str] = None, event_bus=None):
        """
        初始化 WebSocket 基类

        Args:
            name (str): 网关名称
            ws_url (str): WebSocket URL
            event_bus: 事件总线（可选）
        """
        self.name = name
        self._ws_url = ws_url
        self._event_bus = event_bus
        self._logger = logging.getLogger(self.__class__.__name__)

        # HTTP Session（aiohttp）
        self._session: Optional[ClientSession] = None

        # WebSocket 连接对象
        self._ws: Optional[ClientWebSocketResponse] = None

        # 消息接收任务
        self._receive_task = None

        # 连接状态
        self._connected = False
        self._running = False

        # 🔥 新增：连接锁（防止并发竞争）
        self._connect_lock = asyncio.Lock()

        # 🔥 新增：重连状态
        self._reconnect_task = None
        self._reconnect_attempt = 0
        self._max_reconnect_attempts = 10  # 最大重连次数
        self._base_backoff = 1.0  # 初始退避时间（秒）
        self._max_backoff = 60.0  # 最大退避时间（秒）

        # 心跳管理
        self._last_heartbeat = 0
        self._heartbeat_interval = 20  # 心跳间隔（秒）
        self._heartbeat_task = None

        self._logger.info(f"WebSocket 基类初始化: {name}, url={ws_url}")

    def is_connected(self) -> bool:
        """
        检查连接状态

        Returns:
            bool: 是否已连接
        """
        return self._connected and self._ws is not None and not self._ws.closed

    async def connect(self) -> bool:
        """
        连接到 WebSocket（带并发保护）

        Returns:
            bool: 是否连接成功
        """
        # 🔥 关键修复：使用锁防止并发竞争
        async with self._connect_lock:
            # 再次检查（可能在等待锁的过程中已经被其他任务连接了）
            if self.is_connected():
                self._logger.warning("已经连接，跳过连接")
                return True

            # 🔥 关键修复：建立新连接前，强制清理旧资源
            await self._disconnect_cleanup()

            try:
                self._logger.info(f"连接到 WebSocket: {self._ws_url}")

                # 创建或复用 Session
                if self._session is None or self._session.closed:
                    self._session = ClientSession()

                # 建立连接（aiohttp）
                self._ws = await self._session.ws_connect(
                    self._ws_url,
                    receive_timeout=30.0
                )

                self._connected = True
                self._running = True

                # 🔥 关键修复：在连接成功后，启动消息接收任务
                self._receive_task = asyncio.create_task(self._message_loop())

                # 🔥 关键修复：启动心跳任务
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                # 重置重连计数
                self._reconnect_attempt = 0

                self._logger.info(f"✅ WebSocket 连接成功: {self._ws_url}")

                # 调用子类的连接后钩子
                await self._on_connected()

                return True

            except ClientError as e:
                self._logger.error(f"WebSocket 连接失败: {e}")
                self._connected = False

                # 🔥 关键修复：连接失败后，清理资源
                await self._disconnect_cleanup()

                return False
            except Exception as e:
                self._logger.error(f"WebSocket 连接异常: {e}")
                self._connected = False

                # 🔥 关键修复：连接失败后，清理资源
                await self._disconnect_cleanup()

                return False

    async def disconnect(self):
        """
        断开 WebSocket 连接
        """
        self._logger.info("断开 WebSocket 连接...")

        # 停止运行标志
        self._running = False

        # 🔥 关键修复：强制清理所有资源
        await self._disconnect_cleanup()

        self._logger.info("WebSocket 连接已断开")

    async def _disconnect_cleanup(self):
        """
        🔥 强制清理旧资源（关键修复）

        在建立新连接前，必须强制清理旧资源：
        1. 取消消息接收任务
        2. 关闭 WebSocket 连接
        3. 关闭 HTTP Session
        4. 重置心跳任务
        """
        try:
            # 1. 取消消息接收任务
            if self._receive_task is not None:
                if not self._receive_task.done():
                    self._logger.debug("取消消息接收任务")
                    self._receive_task.cancel()

                    # 等待任务取消完成
                    try:
                        await self._receive_task
                    except asyncio.CancelledError:
                        # 预期的取消错误，忽略
                        pass
                    except Exception as e:
                        self._logger.error(f"取消消息接收任务异常: {e}")

                self._receive_task = None

            # 2. 关闭 WebSocket 连接
            if self._ws is not None:
                try:
                    if not self._ws.closed:
                        self._logger.debug("关闭 WebSocket 连接")
                        await self._ws.close()
                except Exception as e:
                    self._logger.error(f"关闭 WebSocket 连接异常: {e}")

                self._ws = None

            # 3. 关闭 HTTP Session（aiohttp）
            if self._session is not None:
                try:
                    if not self._session.closed:
                        self._logger.debug("关闭 HTTP Session")
                        await self._session.close()
                except Exception as e:
                    self._logger.error(f"关闭 HTTP Session 异常: {e}")

                self._session = None

            # 4. 取消心跳任务
            if self._heartbeat_task is not None:
                if not self._heartbeat_task.done():
                    self._logger.debug("取消心跳任务")
                    self._heartbeat_task.cancel()

                    try:
                        await self._heartbeat_task
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        self._logger.error(f"取消心跳任务异常: {e}")

                self._heartbeat_task = None

            # 5. 重置连接状态
            self._connected = False

            self._logger.debug("资源清理完成")

        except Exception as e:
            self._logger.error(f"资源清理异常: {e}", exc_info=True)

    async def _message_loop(self):
        """
        消息接收循环（修复阻塞问题）

        🔥 关键修复：
        - 使用 try...finally 结构
        - 在 finally 块中，不直接调用 connect()，而是通过 _reconnect() 触发重连
        - 避免阻塞消息循环
        """
        try:
            self._logger.info("消息接收循环已启动")

            while self._running and self._connected:
                try:
                    msg = await asyncio.wait_for(
                        self._ws.receive(),
                        timeout=30.0
                    )

                    # 更新最后数据时间
                    self._last_heartbeat = time.time()

                    # 处理消息
                    await self._on_message(msg)

                except asyncio.TimeoutError:
                    self._logger.warning("接收消息超时，可能连接已断开")
                    self._connected = False
                    break
                except asyncio.CancelledError:
                    self._logger.info("消息接收循环被取消")
                    break
                except ClientError as e:
                    self._logger.warning(f"WebSocket 连接错误: {e}")
                    self._connected = False
                    break
                except Exception as e:
                    self._logger.error(f"消息循环异常: {e}", exc_info=True)
                    self._connected = False
                    break

        finally:
            self._logger.info("消息接收循环已停止")

            # 🔥 关键修复：连接断开后，触发重连（非阻塞）
            if self._running:
                # 不直接调用 connect()，而是创建任务触发重连
                # 这样不会阻塞 finally 块
                asyncio.create_task(self._reconnect())

    async def _heartbeat_loop(self):
        """
        心跳发送循环

        每隔一定时间发送心跳包，保持连接活跃。
        """
        try:
            self._logger.info("心跳循环已启动")

            while self._running and self._ws is not None and not self._ws.closed:
                await asyncio.sleep(self._heartbeat_interval)

                if not self._running or self._ws is None or self._ws.closed:
                    break

                try:
                    # 发送心跳（aiohttp 使用 send_str）
                    await self._ws.send_str("ping")
                    self._logger.debug("心跳已发送")

                except ClientError as e:
                    self._logger.error(f"心跳发送失败: {e}")
                    # 心跳发送失败，触发重连
                    break
                except Exception as e:
                    self._logger.error(f"心跳发送失败: {e}")
                    break

        except asyncio.CancelledError:
            self._logger.info("心跳循环被取消")
        except Exception as e:
            self._logger.error(f"心跳循环异常: {e}", exc_info=True)
        finally:
            self._logger.info("心跳循环已停止")

    async def _reconnect(self):
        """
        🔥 指数退避重连机制（关键修复）

        重连逻辑：
        1. 如果获取不到锁（已有任务在处理连接），直接返回
        2. 计算退避时间（指数增长，最大 60 秒）
        3. 等待退避时间后尝试重连
        4. 如果重连失败，继续循环（递增退避时间）
        5. 如果重连成功，退出循环
        """
        try:
            # 🔥 防止重连风暴：如果已有任务在处理连接，直接返回
            if self._connect_lock.locked():
                self._logger.debug("已有任务在处理连接，跳过本次重连")
                return

            # 🔥 计算退避时间（指数增长）
            wait_seconds = self._base_backoff * (2 ** min(self._reconnect_attempt, 5))
            wait_seconds = min(wait_seconds, self._max_backoff)

            self._logger.info(
                f"等待 {wait_seconds:.1f} 秒后重连 "
                f"(尝试 {self._reconnect_attempt + 1}/{self._max_reconnect_attempts})"
            )

            # 等待退避时间
            await asyncio.sleep(wait_seconds)

            # 尝试重连
            self._reconnect_attempt += 1

            if self._reconnect_attempt > self._max_reconnect_attempts:
                self._logger.error(
                    f"重连次数超过限制 ({self._max_reconnect_attempts})，停止重连"
                )
                self._running = False
                return

            success = await self.connect()
            if success:
                self._logger.info(f"✅ 重连成功 (尝试 {self._reconnect_attempt})")
            else:
                self._logger.warning(f"重连失败 (尝试 {self._reconnect_attempt})")
                # 继续循环，递增退避时间
                asyncio.create_task(self._reconnect())

        except Exception as e:
            self._logger.error(f"重连异常: {e}", exc_info=True)

    async def send_message(self, message: str):
        """
        发送消息

        Args:
            message (str): 消息内容（JSON 字符串）
        """
        if not self.is_connected():
            self._logger.warning("WebSocket 未连接，无法发送消息")
            return False

        try:
            await self._ws.send_str(message)
            return True
        except ClientError as e:
            self._logger.error(f"发送消息失败: {e}")
            return False
        except Exception as e:
            self._logger.error(f"发送消息失败: {e}")
            return False

    # ==================== 子类必须实现的方法 ====================

    async def _on_connected(self):
        """
        连接成功后的钩子（子类实现）

        子类可以在这里实现：
        - 发送登录消息
        - 发送订阅消息
        """
        pass

    async def _on_message(self, message: WSMessage):
        """
        消息处理钩子（子类实现）

        Args:
            message (WSMessage): aiohttp WebSocket 消息
        """
        pass

    # ==================== 兼容性方法 ====================

    async def publish_event(self, event):
        """
        发布事件到事件总线

        Args:
            event: 要发布的事件
        """
        if self._event_bus:
            self._event_bus.put_nowait(event)

    def get_status(self) -> Dict[str, Any]:
        """
        获取连接状态

        Returns:
            dict: 状态信息
        """
        return {
            'connected': self.is_connected(),
            'url': self._ws_url,
            'reconnect_attempt': self._reconnect_attempt,
            'last_heartbeat': self._last_heartbeat
        }


# ==================== 旧版本兼容（废弃） ====================

class OKXWebSocketClient:
    """
    🔥 已废弃：使用新的 WsBaseGateway 替代

    保留此类仅用于向后兼容，新代码不应使用。
    """

    def __init__(self, redis_client=None):
        self.logger = logging.getLogger(__name__)
        self.logger.warning("OKXWebSocketClient 已废弃，请使用 WsBaseGateway")

    async def connect(self):
        return False

    def start(self):
        pass

    def stop(self):
        pass
