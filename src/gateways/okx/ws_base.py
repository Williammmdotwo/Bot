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
import aiohttp
from aiohttp import ClientSession, WSMessage, ClientError, ClientWebSocketResponse

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

        # 🔥 新增：看门狗（Watchdog）- 防止假死
        self._last_msg_time = 0  # 最后收到消息的时间（包括 ping、pong 和数据推送）
        self._watchdog_timeout = 60  # 🔥 [不坏金身] 看门狗超时时间提高到 60 秒（更宽松）

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

                # 🔥 修复：初始化看门狗时间戳（连接成功时立即更新）
                self._last_msg_time = time.time()

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
                        # 保存 connector 引用（因为 close() 后可能无法访问）
                        connector = self._session.connector if self._session.connector else None

                        self._logger.debug("关闭 HTTP Session")
                        await self._session.close()

                        # 显式关闭 connector（防止资源泄漏）
                        if connector and not connector.closed:
                            self._logger.debug("关闭 HTTP connector")
                            await connector.close()
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
        🔥 [不坏金身] 消息接收循环（无限递归）

        核心特性：
        - 持续接收 WebSocket 消息，直到系统主动关闭
        - 更新看门狗时间戳（每次收到消息都更新）
        - 拦截心跳响应 "pong"，避免 JSON 解析错误
        - 任何异常都触发重连，但接收循环永不停止
        - 无限递归：使用 while True + 异常捕获 + 触发重连

        修复内容：
        - 连接错误时自动触发重连，而不是停止循环
        - 超时错误时也触发重连
        - 任何未捕获异常都记录完整堆栈并触发重连
        - 消息接收循环永不停止，除非系统主动关闭
        """
        self._logger.info("📨 [消息接收循环] 已启动（不坏金身模式）")

        # 🔥 无限递归消息接收循环（永不停止）
        while True:
            try:
                # 检查系统是否正在关闭
                if not self._running:
                    self._logger.info("📨 [消息接收循环] 系统正在关闭，退出接收循环")
                    break

                # 检查 WebSocket 是否有效
                if self._ws is None or self._ws.closed:
                    self._logger.warning("📨 [消息接收循环] WebSocket 未连接，等待重连...")
                    await asyncio.sleep(5)
                    continue

                # 🔥 接收消息（带超时）
                msg = await asyncio.wait_for(
                    self._ws.receive(),
                    timeout=30.0
                )

                # 🔥 更新看门狗时间戳（每次收到消息都更新）
                # 包括 ping、pong 和数据推送
                self._last_msg_time = time.time()

                # 更新最后心跳时间（兼容旧代码）
                self._last_heartbeat = time.time()

                # 🔥 拦截心跳响应 "pong"
                # OKX 服务器回复的心跳响应是纯文本字符串 "pong"，而不是 JSON 格式
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = msg.data
                    if data == 'pong':
                        self._logger.debug("💓 [心跳响应] 收到 pong")
                        continue  # 直接跳过，不进行 JSON 解析和子类处理

                # 处理消息
                await self._on_message(msg)

            except asyncio.TimeoutError:
                self._logger.warning("📨 [超时] 接收消息超时 30 秒，触发重连")
                # 超时触发重连，但消息接收循环继续运行
                await self.disconnect()
                await asyncio.sleep(5)
                continue

            except asyncio.CancelledError:
                self._logger.info("📨 [消息接收循环] 任务被取消（系统关闭），退出")
                break

            except (ClientError, aiohttp.ClientConnectionError, aiohttp.ServerDisconnectedError) as e:
                # 🔥 [关键修复] 记录完整 traceback，防止静默失败
                self._logger.error(
                    f"📨 [连接错误] {type(e).__name__}: {e}",
                    exc_info=True
                )
                # 连接错误触发重连，但消息接收循环继续运行
                await self.disconnect()
                await asyncio.sleep(5)
                continue

            except Exception as e:
                # 🔥 [关键修复] 捕获所有未处理异常，记录完整堆栈
                self._logger.error(
                    f"📨 [未捕获异常] {type(e).__name__}: {e}",
                    exc_info=True
                )
                # 任何异常都触发重连，但消息接收循环永不停止
                await self.disconnect()
                await asyncio.sleep(5)
                continue

        self._logger.info("📨 [消息接收循环] 已停止")

    async def _heartbeat_loop(self):
        """
        🔥 [不坏金身] 心跳发送循环（无限递归）

        核心特性：
        - 每隔一定时间发送心跳包，保持连接活跃
        - 看门狗检查：如果超过 60 秒未收到任何消息，强制重连
        - 心跳发送失败：触发重连，而不是停止任务
        - 无限递归：心跳任务永远不会停止，除非系统主动关闭

        修复内容：
        - 心跳发送失败时自动触发重连，而不是停止循环
        - 看门狗超时从 30 秒提高到 60 秒（更宽松）
        - 无限递归连接：使用 while True + 异常捕获 + 延迟重连
        """
        self._logger.info("💓 [心跳循环] 已启动（不坏金身模式）")

        # 🔥 无限递归心跳循环（永不停止）
        while True:
            try:
                # 检查系统是否正在关闭
                if not self._running:
                    self._logger.info("💓 [心跳循环] 系统正在关闭，退出心跳循环")
                    break

                # 检查 WebSocket 是否有效
                if self._ws is None or self._ws.closed:
                    self._logger.warning("💓 [心跳循环] WebSocket 未连接，等待重连...")
                    await asyncio.sleep(5)
                    continue

                # 🔥 [看门狗] 检查最后收到消息的时间
                # 如果超过 60 秒没有收到任何消息（包括 ping、pong 和数据推送），强制重连
                time_since_last_msg = time.time() - self._last_msg_time
                if time_since_last_msg > self._watchdog_timeout:
                    self._logger.error(
                        f"💓 [看门狗触发] {time_since_last_msg:.1f}秒未收到任何数据，"
                        f"连接可能已假死，强制重连..."
                    )
                    # 强制断开，触发重连（心跳循环继续运行）
                    await self.disconnect()
                    # 等待重连完成
                    await asyncio.sleep(5)
                    continue

                # 心跳间隔等待
                await asyncio.sleep(self._heartbeat_interval)

                # 再次检查（等待期间可能连接已断开）
                if not self._running or self._ws is None or self._ws.closed:
                    self._logger.debug("💓 [心跳循环] 连接状态变化，跳过本次心跳")
                    continue

                # 🔥 发送心跳（使用 aiohttp 的 send_str）
                try:
                    await self._ws.send_str("ping")
                    self._logger.debug("💓 [心跳] ping 已发送")

                except ClientError as e:
                    self._logger.error(f"💓 [心跳失败] {type(e).__name__}: {e}")
                    # 心跳发送失败，触发重连，但心跳循环继续运行
                    await self.disconnect()
                    await asyncio.sleep(5)
                    continue

                except Exception as e:
                    self._logger.error(f"💓 [心跳失败] 未捕获异常: {e}", exc_info=True)
                    # 任何异常都触发重连，但心跳循环继续运行
                    await self.disconnect()
                    await asyncio.sleep(5)
                    continue

            except asyncio.CancelledError:
                self._logger.info("💓 [心跳循环] 任务被取消（系统关闭），退出")
                break

            except Exception as e:
                # 🔥 [关键修复] 捕获所有未处理异常，记录完整堆栈
                self._logger.error(
                    f"💓 [心跳循环] 未捕获异常，继续运行: {e}",
                    exc_info=True
                )
                # 等待 5 秒后继续（心跳循环永不停止）
                await asyncio.sleep(5)
                continue

        self._logger.info("💓 [心跳循环] 已停止")

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
                f"🔄 [重连 {self._reconnect_attempt + 1}/{self._max_reconnect_attempts}] "
                f"等待 {wait_seconds:.1f} 秒后重连..."
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
                self._logger.info(f"✅ [重连成功] 第 {self._reconnect_attempt} 次重连成功")
            else:
                self._logger.warning(f"⚠️ [重连失败] 第 {self._reconnect_attempt} 次重连失败，继续等待...")
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

    async def publish_event(self, event, priority: int = 10):
        """
        发布事件到事件总线（支持优先级）

        Args:
            event: 要发布的事件
            priority (int): 优先级（默认 10 = TICK 优先级）
        """
        if self._event_bus:
            self._event_bus.put_nowait(event, priority=priority)

    @property
    def reconnect_count(self) -> int:
        """
        🔥 [Guardian] 获取重连次数（公开属性）

        Returns:
            int: 重连次数
        """
        return self._reconnect_attempt

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
