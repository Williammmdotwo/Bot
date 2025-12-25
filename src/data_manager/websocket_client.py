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
            "public": "wss://wspap.okx.com:8443/ws/v5/public",    # 🔥 修复：K线数据使用public端点
            "private": "wss://wspap.okx.com:8443/ws/v5/private"
        },
        "live": {
            "public": "wss://ws.okx.com:8443/ws/v5/public",       # 🔥 修复：K线数据使用public端点
            "private": "wss://ws.okx.com:8443/ws/v5/private"
        }
    }

    # ✅ 强制使用business频道
    BUSINESS_URL = "wss://ws.okx.com:8443/ws/v5/business"

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
        self._heartbeat_sender_task = None

        # 环境配置
        self.env_config = get_environment_config()
        self.credentials, self.has_credentials = get_api_credentials()
        self.ws_urls = self._get_ws_urls()

        self.logger.info(f"WebSocket客户端初始化完成 - 环境: {self.env_config['environment_type']}")

    def _get_ws_urls(self) -> Dict[str, str]:
        """根据环境获取WebSocket URL - 已废弃，强制使用business频道"""
        # 🚨 注释掉所有动态URL判断逻辑
        # env_type = self.env_config["environment_type"]
        #
        # if env_type == "demo":
        #     return self.WS_URLS["demo"]
        # elif env_type == "production" or env_type == "live":
        #     return self.WS_URLS["live"]
        # else:
        #     # 默认使用demo环境（安全优先）
        #     self.logger.warning(f"未知环境类型: {env_type}，使用demo环境")
        #     return self.WS_URLS["demo"]

        # 🚨 不管原来的代码是怎么根据 is_demo 自动判断 URL 的，全部注释掉
        # 🚨 不管是 ws.okx.com 还是 wspap.okx.com，全部禁用

        # 强制使用实盘业务频道（这是唯一能通的路）
        return {"public": self.BUSINESS_URL, "private": self.BUSINESS_URL}

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
                "channel": "candle5m",  # 修复：使用正确的OKX v5 API频道名
                "instId": self.symbol
            }]
        }

    async def _send_subscribe_message(self):
        """发送订阅消息 - 确保每次重连都会重新订阅"""
        try:
            if not self.connection or self.connection.closed:
                self.logger.warning("WebSocket连接不可用，无法发送订阅消息")
                return False

            subscribe_msg = self._create_subscribe_message()
            await self.connection.send(json.dumps(subscribe_msg))
            self.logger.info(f"📡 已发送订阅消息: {self.symbol} {self.timeframe}")
            return True

        except Exception as e:
            self.logger.error(f"发送订阅消息失败: {e}")
            return False

    async def _connect_websocket(self) -> bool:
        """建立WebSocket连接 - 修复死锁问题"""
        try:
            # ✅ 强制使用business频道
            ws_url = self.BUSINESS_URL
            self.logger.info(f"连接到WebSocket: {ws_url} (环境: {self.env_config['environment_type']}) - 使用BUSINESS频道")

            # 🔥 使用 async with 上下文管理器 - 修复死锁问题
            async with websockets.connect(ws_url) as ws:
                self.connection = ws
                self.is_connected = True
                self.logger.info("🔓 WebSocket连接建立成功")

                # ==========================================
                # ✅ 必须放在这里 (循环之前)
                # ==========================================
                # 1. 构造字典对象（绝对标准格式）
                subscribe_payload = {
                    "op": "subscribe",
                    "args": [
                        {
                            "channel": "candle5m",
                            "instId": "BTC-USDT"
                        }
                    ]
                }

                # 2. 转换成 JSON 字符串
                # ensure_ascii=False 防止中文乱码（虽然这里没中文）
                # separators=(',', ':') 去掉多余空格，压缩体积，防止有些服务器对空格敏感
                json_str = json.dumps(subscribe_payload, ensure_ascii=False, separators=(',', ':'))

                # 💥 暴力调试法（最稳）- 用 print 确保一定显示
                print(f"\n\n{'='*50}")
                print(f"!!! 正在执行发送代码 !!!")
                print(f"!!! 发送内容: {json_str}")
                print(f"{'='*50}\n\n")

                # 4. 发送订阅消息
                await ws.send(json_str)

                # 双重保险：也用 logger 记录
                self.logger.info(f"🚀 [DEBUG] 正在发送订阅: {json_str}")
                self.logger.info("✅ 订阅消息发送完成")

                # ==========================================

                # 🔄 现在才进入接收循环
                async for message in ws:
                    if not self.is_connected:
                        break

                    # 🔍 调试输出：打印原始消息前200个字符
                    print(f"DEBUG_RAW: {message[:200]}")

                    await self._handle_message(message)

                # 🔥 如果循环正常结束，标记连接关闭
                self.is_connected = False
                self.logger.info("📊 WebSocket连接正常结束")

            return True

        except Exception as e:
            self.logger.error(f"WebSocket连接失败: {e}")
            return False

    async def _handle_message(self, message: str):
        """处理接收到的消息"""
        try:
            # 处理服务器返回的 "pong" 响应
            if message.strip() == "pong":
                self.logger.debug("收到OKX服务器的pong响应")
                return

            data = json.loads(message)

            # 修复：检查OKX错误消息
            if "event" in data and data["event"] == "error":
                self.logger.error(f"OKX API错误: {data}")
                return

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

            # 处理K线数据消息
            if "data" in data and isinstance(data["data"], list):
                for item in data["data"]:
                    if isinstance(item, list) and len(item) >= 6:  # OKX K线数据是数组格式
                        self._process_candle_data(item)
                    elif "instId" in item and item["instId"] == self.symbol:
                        # 兼容处理（如果收到的是对象格式）
                        self._process_ticker_data(item)

        except json.JSONDecodeError:
            # 如果不是JSON格式，检查是否是 "pong" 响应
            if message.strip() == "pong":
                self.logger.debug("收到OKX服务器的pong响应")
            else:
                self.logger.debug(f"收到非JSON消息: {message}")
        except Exception as e:
            self.logger.error(f"消息处理错误: {e}")

    def _process_candle_data(self, candle: list):
        """处理K线数据，转换为OHLCV格式"""
        try:
            # OKX K线数据格式: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
            if isinstance(candle, list) and len(candle) >= 6:
                ohlcv_data = {
                    "timestamp": int(candle[0]),
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5])
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

                    self.logger.info(f"✅ 成功存储K线数据: {self.symbol} OHLCV={ohlcv_data}")
                else:
                    self.logger.debug(f"✅ 收到K线数据: {self.symbol} OHLCV={ohlcv_data}")
            else:
                self.logger.debug(f"❌ K线数据格式错误: {candle}")

        except Exception as e:
            self.logger.error(f"❌ K线数据处理错误: {e}")

    def _process_ticker_data(self, ticker: Dict[str, Any]):
        """处理ticker数据，转换为OHLCV格式（兼容性方法）"""
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

                self.logger.debug(f"存储ticker数据: {self.symbol} {ohlcv_data}")

        except Exception as e:
            self.logger.error(f"ticker数据处理错误: {e}")

    # 🚨 删除分离的_message_loop函数，避免多线程混乱
    # 现在消息处理逻辑已经集成到_connect_websocket中

    async def _heartbeat_sender(self):
        """OKX心跳发送 - 每20秒向服务器发送'ping'"""
        while self.is_connected and not self._stop_event.is_set():
            try:
                await asyncio.sleep(20)  # 每20秒发送一次心跳

                if self.is_connected and self.connection and not self.connection.closed:
                    # OKX要求发送纯字符串"ping"
                    await self.connection.send("ping")
                    self.last_heartbeat_time = time.time()
                    self.logger.debug("已发送心跳ping到OKX服务器")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"心跳发送错误: {e}")
                # 心跳发送失败，可能连接有问题
                await self.disconnect()

    async def _heartbeat_monitor(self):
        """心跳监控 - 每60秒记录状态和处理pong响应"""
        while self.is_connected and not self._stop_event.is_set():
            try:
                await asyncio.sleep(60)

                current_time = time.time()
                last_data = self.last_data_time or "never"
                time_since_data = (current_time - (self.last_data_time or current_time))
                last_ping = self.last_heartbeat_time or "never"
                time_since_ping = (current_time - (self.last_heartbeat_time or current_time))

                status = "connected" if self.is_connected else "disconnected"
                self.logger.debug(
                    f"心跳监控 - 状态: {status}, "
                    f"最后数据: {last_data}, "
                    f"距最后数据: {time_since_data:.1f}秒, "
                    f"最后ping: {last_ping}, "
                    f"距最后ping: {time_since_ping:.1f}秒"
                )

                # 如果超过5分钟没有数据，可能连接有问题
                if time_since_data > 300:
                    self.logger.warning("超过5分钟未收到数据，将重连")
                    await self.disconnect()

                # 如果心跳发送失败超过2分钟，可能连接有问题
                if time_since_ping > 120:
                    self.logger.warning("超过2分钟未成功发送心跳，将重连")
                    await self.disconnect()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"心跳监控错误: {e}")

    async def connect(self) -> bool:
        """连接到WebSocket - 修复死锁问题"""
        if self.is_connected:
            self.logger.warning("已经连接，跳过连接")
            return True

        try:
            # 🔥 直接运行_connect_websocket，因为它已经包含了完整的连接和消息处理逻辑
            # 不再需要额外的消息处理循环，因为已经集成在_connect_websocket中
            connected = await self._connect_websocket()

            if connected:
                self.reconnect_attempts = 0
                self.last_heartbeat_time = time.time()
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
            # 清理心跳发送任务
            if self._heartbeat_sender_task:
                self._heartbeat_sender_task.cancel()
                self._heartbeat_sender_task = None

            # 清理心跳监控任务
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
