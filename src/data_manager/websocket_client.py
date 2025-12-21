import asyncio
import json
import logging
import time
import threading
import os
import hashlib
import hmac
import base64
import websockets
from typing import Optional, Dict, Any, Callable
from datetime import datetime
import redis
from src.utils.environment_utils import get_environment_config, get_api_credentials, log_environment_info

class OKXWebSocketClient:
    """OKX WebSocket客户端 - 支持环境区分、自动重连、心跳监控"""

    # 环境URL配置
    WS_URLS = {
        "demo": {
            "public": "wss://wspap.okx.com:8443/ws/v5/public",
            "private": "wss://wspap.okx.com:8443/ws/v5/private"
        },
        "live": {
            "public": "wss://ws.okx.com:8443/ws/v5/public",
            "private": "wss://ws.okx.com:8443/ws/v5/private"
        }
    }

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client
        self.logger = logging.getLogger(__name__)
        self.symbol = "BTC-USDT"  # OKX使用BTC-USDT格式
        self.timeframe = "5m"

        # 连接状态管理
        self.is_connected = False
        self.should_reconnect = True
        self.connection = None
        self.last_data_time = None
        self.last_heartbeat_time = None

        # 重连机制
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.base_reconnect_delay = 5  # 秒

        # 控制变量
        self._stop_event = threading.Event()
        self._loop = None
        self._thread = None
        self._heartbeat_task = None

        # 代理配置
        self.proxy_config = self._get_proxy_config()

        # 环境配置
        self.env_config = get_environment_config()
        self.credentials, self.has_credentials = get_api_credentials()
        self.ws_urls = self._get_ws_urls()

        self.logger.info(f"WebSocket客户端初始化完成 - 环境: {self.env_config['environment_type']}")

    def _get_proxy_config(self) -> Optional[Dict[str, str]]:
        """获取代理配置"""
        http_proxy = os.getenv('HTTP_PROXY')
        https_proxy = os.getenv('HTTPS_PROXY')

        if not http_proxy and not https_proxy:
            return None

        proxy = {}
        if http_proxy:
            proxy['http'] = http_proxy
            proxy['https'] = http_proxy
        if https_proxy and https_proxy != http_proxy:
            proxy['https'] = https_proxy

        self.logger.info(f"使用代理配置: {proxy}")
        return proxy

    def _get_ws_urls(self) -> Dict[str, str]:
        """根据环境获取WebSocket URL"""
        env_type = self.env_config["environment_type"]

        if env_type == "demo":
            return self.WS_URLS["demo"]
        elif env_type == "production" or env_type == "live":
            return self.WS_URLS["live"]
        else:
            # 默认使用demo环境（安全优先）
            self.logger.warning(f"未知环境类型: {env_type}，使用demo环境")
            return self.WS_URLS["demo"]

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """生成OKX API签名"""
        if not self.has_credentials:
            return ""

        # 构建签名字符串
        message = timestamp + method + request_path + body
        signature = hmac.new(
            self.credentials["secret"].encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()

        return base64.b64encode(signature).decode('utf-8')

    def _create_login_message(self) -> Dict[str, Any]:
        """创建登录消息"""
        if not self.has_credentials:
            self.logger.warning("无API凭据，跳过登录")
            return None

        timestamp = str(int(time.time()))
        sign = self._generate_signature(timestamp, "GET", "/users/self/verify")

        return {
            "op": "login",
            "args": [{
                "apiKey": self.credentials["api_key"],
                "passphrase": self.credentials["passphrase"],
                "timestamp": timestamp,
                "sign": sign
            }]
        }

    def _create_subscribe_message(self) -> Dict[str, Any]:
        """创建订阅消息"""
        return {
            "op": "subscribe",
            "args": [{
                "channel": f"tickers5m",
                "instId": self.symbol
            }]
        }

    async def _connect_websocket(self) -> bool:
        """建立WebSocket连接"""
        try:
            # 使用public URL进行连接
            ws_url = self.ws_urls["public"]
            self.logger.info(f"连接到WebSocket: {ws_url} (环境: {self.env_config['environment_type']})")

            # 创建WebSocket连接
            kwargs = {"ping_interval": 30}
            if self.proxy_config:
                # 注意：websockets库的代理支持可能有限
                self.logger.info("尝试使用代理连接WebSocket")
                # 如果websockets库不支持代理，这里可能需要使用其他方式

            self.connection = await websockets.connect(ws_url, **kwargs)

            # 发送登录消息（如果有凭据）
            login_msg = self._create_login_message()
            if login_msg:
                await self.connection.send(json.dumps(login_msg))
                self.logger.info("已发送登录消息")

            # 发送订阅消息
            subscribe_msg = self._create_subscribe_message()
            await self.connection.send(json.dumps(subscribe_msg))
            self.logger.info(f"已发送订阅消息: {self.symbol} {self.timeframe}")

            return True

        except Exception as e:
            self.logger.error(f"WebSocket连接失败: {e}")
            return False

    async def _handle_message(self, message: str):
        """处理接收到的消息"""
        try:
            data = json.loads(message)

            # 处理登录响应
            if "event" in data and data["event"] == "login":
                if data.get("code") == "0":
                    self.logger.info("WebSocket登录成功")
                else:
                    self.logger.error(f"WebSocket登录失败: {data}")
                return

            # 处理订阅响应
            if "event" in data and data["event"] == "subscribe":
                if data.get("code") == "0":
                    self.logger.info(f"订阅成功: {data.get('arg', {})}")
                else:
                    self.logger.error(f"订阅失败: {data}")
                return

            # 处理数据消息
            if "data" in data and isinstance(data["data"], list):
                for item in data["data"]:
                    if "instId" in item and item["instId"] == self.symbol:
                        self._process_ticker_data(item)

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析错误: {e}")
        except Exception as e:
            self.logger.error(f"消息处理错误: {e}")

    def _process_ticker_data(self, ticker: Dict[str, Any]):
        """处理ticker数据，转换为OHLCV格式"""
        try:
            # OKX ticker数据转换为OHLCV
            ohlcv_data = {
                "timestamp": int(ticker.get("ts", 0)),
                "open": float(ticker.get("open", 0)),
                "high": float(ticker.get("high", 0)),
                "low": float(ticker.get("low", 0)),
                "close": float(ticker.get("last", 0)),
                "volume": float(ticker.get("vol24h", 0))
            }

            # 更新最后数据时间
            self.last_data_time = time.time()

            # 存储到Redis
            if self.redis:
                redis_key = f"ohlcv:{self.symbol}:{self.timeframe}"
                self.redis.zadd(redis_key, {
                    str(ohlcv_data["timestamp"]): json.dumps(ohlcv_data)
                })

                # 保持最近1000条数据
                self.redis.zremrangebyrank(redis_key, 0, -1001)

                self.logger.debug(f"存储OHLCV数据: {self.symbol} {ohlcv_data}")

        except Exception as e:
            self.logger.error(f"ticker数据处理错误: {e}")

    async def _message_loop(self):
        """消息接收循环"""
        try:
            async for message in self.connection:
                if not self.is_connected:
                    break

                await self._handle_message(message)

        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("WebSocket连接已关闭")
        except Exception as e:
            self.logger.error(f"消息循环错误: {e}")

        self.is_connected = False

    async def _heartbeat_monitor(self):
        """心跳监控 - 每60秒记录状态"""
        while self.is_connected and not self._stop_event.is_set():
            try:
                await asyncio.sleep(60)

                current_time = time.time()
                last_data = self.last_data_time or "never"
                time_since_data = (current_time - (self.last_data_time or current_time))

                status = "connected" if self.is_connected else "disconnected"
                self.logger.info(
                    f"心跳监控 - 状态: {status}, "
                    f"最后数据: {last_data}, "
                    f"距最后数据: {time_since_data:.1f}秒"
                )

                # 如果超过5分钟没有数据，可能连接有问题
                if time_since_data > 300:
                    self.logger.warning("超过5分钟未收到数据，将重连")
                    await self.disconnect()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"心跳监控错误: {e}")

    async def connect(self) -> bool:
        """连接到WebSocket"""
        if self.is_connected:
            self.logger.warning("已经连接，跳过连接")
            return True

        try:
            # 尝试连接
            connected = await self._connect_websocket()

            if connected:
                self.is_connected = True
                self.reconnect_attempts = 0
                self.last_heartbeat_time = time.time()

                # 启动消息处理
                asyncio.create_task(self._message_loop())

                # 启动心跳监控
                if self._heartbeat_task:
                    self._heartbeat_task.cancel()
                self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())

                self.logger.info(f"WebSocket连接成功: {self.symbol}")
                return True
            else:
                return False

        except Exception as e:
            self.logger.error(f"连接失败: {e}")
            return False

    async def disconnect(self):
        """断开WebSocket连接"""
        self.is_connected = False
        self.should_reconnect = False

        try:
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                self._heartbeat_task = None

            if self.connection:
                await self.connection.close()
                self.connection = None

            self.logger.info("WebSocket连接已断开")

        except Exception as e:
            self.logger.error(f"断开连接错误: {e}")

    async def auto_reconnect(self):
        """自动重连机制"""
        while self.should_reconnect and not self._stop_event.is_set():
            if self.is_connected:
                await asyncio.sleep(10)  # 连接正常时每10秒检查一次
                continue

            # 计算重连延迟（指数退避）
            if self.reconnect_attempts == 0:
                delay = self.base_reconnect_delay
            else:
                delay = min(300, self.base_reconnect_delay * (2 ** min(self.reconnect_attempts - 1, 5)))

            self.logger.info(f"等待 {delay} 秒后重连 (尝试 {self.reconnect_attempts + 1}/{self.max_reconnect_attempts})")
            await asyncio.sleep(delay)

            # 检查是否应该停止重连
            if self._stop_event.is_set():
                break

            # 尝试重连
            self.reconnect_attempts += 1

            if self.reconnect_attempts > self.max_reconnect_attempts:
                self.logger.error(f"重连次数超过限制 ({self.max_reconnect_attempts})，停止重连")
                break

            success = await self.connect()
            if success:
                self.logger.info(f"重连成功 (尝试 {self.reconnect_attempts})")
            else:
                self.logger.warning(f"重连失败 (尝试 {self.reconnect_attempts})")

    def _run_async_loop(self):
        """运行异步事件循环"""
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
            self._loop = asyncio.get_event_loop()

            # 启动自动重连循环
            self._loop.run_until_complete(self.auto_reconnect())

        except Exception as e:
            self.logger.error(f"异步循环错误: {e}")
        finally:
            if self._loop and not self._loop.is_closed():
                self._loop.run_until_complete(self.disconnect())
                self._loop.close()

    def start(self):
        """启动WebSocket客户端"""
        if self._thread and self._thread.is_alive():
            self.logger.warning("WebSocket客户端已在运行")
            return

        self.logger.info("启动WebSocket客户端...")
        self._stop_event.clear()
        self.should_reconnect = True

        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()

        self.logger.info("WebSocket客户端已启动")

    def stop(self):
        """停止WebSocket客户端"""
        self.logger.info("停止WebSocket客户端...")
        self.should_reconnect = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)

        self.logger.info("WebSocket客户端已停止")

    def get_status(self) -> Dict[str, Any]:
        """获取连接状态"""
        return {
            "connected": self.is_connected,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "environment": self.env_config["environment_type"],
            "last_data_time": self.last_data_time,
            "reconnect_attempts": self.reconnect_attempts,
            "has_credentials": self.has_credentials,
            "ws_url": self.ws_urls["public"]
        }

    def _run_single_iteration(self):
        """兼容性方法 - 确保客户端运行"""
        if not self._thread or not self._thread.is_alive():
            self.start()
