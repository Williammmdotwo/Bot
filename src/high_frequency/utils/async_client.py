"""
异步 HTTP 客户端

本模块提供基于 aiohttp 的异步 REST API 客户端，用于高频交易场景。

关键特性：
- 持久 Session 复用（TCP Keep-Alive）
- 自动 OKX V5 API 签名
- 完整的异步上下文管理
- 低延迟，高吞吐量

设计原则：
- 不使用 ccxt，直接使用 aiohttp
- Session 在 __init__ 中创建，所有请求复用
- 支持模拟交易模式
"""

import json
import logging
from typing import Dict, Any, Optional
import aiohttp
from aiohttp import ClientSession, ClientTimeout, ClientError
from .auth import generate_headers_with_auto_timestamp

logger = logging.getLogger(__name__)


class RestClient:
    """
    异步 REST API 客户端

    使用 aiohttp.ClientSession 实现持久连接，支持 TCP Keep-Alive，
    适用于高频交易场景。

    Example:
        >>> async with RestClient(
        ...     api_key="your_api_key",
        ...     secret_key="your_secret_key",
        ...     passphrase="your_passphrase",
        ...     use_demo=True
        ... ) as client:
        ...     response = await client.post_signed(
        ...         "/api/v5/trade/order",
        ...         {"instId": "BTC-USDT-SWAP", "side": "buy", "ordType": "market", "sz": "0.01"}
        ...     )
        ...     print(response)
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        base_url: str = "https://www.okx.com",
        use_demo: bool = False,
        timeout: int = 10
    ):
        """
        初始化 REST 客户端

        Args:
            api_key (str): OKX API Key
            secret_key (str): OKX Secret Key
            passphrase (str): OKX Passphrase
            base_url (str): API 基础 URL，默认为 OKX 生产环境
            use_demo (bool): 是否使用模拟交易，默认为 False
            timeout (int): 请求超时时间（秒），默认为 10
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.base_url = base_url.rstrip('/')
        self.use_demo = use_demo
        self.timeout = timeout

        # 创建持久的 ClientSession
        # 关键：Session 在这里创建，所有请求复用，启用 TCP Keep-Alive
        self.session: Optional[ClientSession] = None
        self._closed = False

        logger.info(
            f"RestClient 初始化: base_url={self.base_url}, "
            f"use_demo={use_demo}, timeout={timeout}s"
        )

    async def _get_session(self) -> ClientSession:
        """
        获取或创建 ClientSession

        使用延迟初始化模式，确保在异步上下文中创建 Session。

        Returns:
            ClientSession: aiohttp ClientSession 实例
        """
        if self.session is None or self.session.closed:
            if self._closed:
                raise RuntimeError("ClientSession 已关闭，无法创建新连接")

            # 创建新的 Session
            timeout = ClientTimeout(total=self.timeout)
            connector = aiohttp.TCPConnector(
                limit=100,  # 连接池大小
                ttl_dns_cache=300,  # DNS 缓存 5 分钟
                keepalive_timeout=30,  # Keep-Alive 超时 30 秒
                enable_cleanup_closed=True  # 清理已关闭的连接
            )

            self.session = ClientSession(
                base_url=self.base_url,
                timeout=timeout,
                connector=connector
            )

            logger.debug("创建新的 ClientSession")

        return self.session

    def _get_timestamp(self) -> str:
        # [修复] 统一使用与 WebSocket 完全相同的时间戳生成方法
        from datetime import datetime, timezone
        # 获取当前 UTC 时间
        dt = datetime.now(timezone.utc)
        # 使用 strftime 精确控制格式，确保毫秒是 3 位
        # 格式：2023-01-01T12:00:00.123Z
        return dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    def _sign(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        # 拼接字符串：timestamp + method + requestPath + body
        message = f"{timestamp}{method.upper()}{request_path}{body}"

        import hmac
        import hashlib
        import base64

        # [新增] 详细的签名调试日志
        logger.debug(
            f"🔐 [签名计算] "
            f"timestamp={timestamp}, method={method.upper()}, "
            f"request_path={request_path}, body={body[:50] if len(body) > 50 else body}, "
            f"message={message[:100]}... (total={len(message)} chars)"
        )

        mac = hmac.new(
            bytes(self.secret_key, encoding="utf-8"),
            bytes(message, encoding="utf-8"),
            digestmod=hashlib.sha256
        )
        sign = base64.b64encode(mac.digest()).decode("utf-8")

        logger.debug(f"🔐 [签名结果] sign={sign}")

        return sign

    def _get_headers(self, request_method: str, request_path: str, body: str = "") -> dict:
        # [修复] 确保这里和 WebSocket 用的是完全一样的逻辑
        # 时间戳必须与签名字符串中的完全一致
        timestamp = self._get_timestamp()

        # [关键] x-simulated-trading 不参与签名计算，只放在 Header 里
        # 签名字符串 = timestamp + method + requestPath + body
        sign = self._sign(timestamp, request_method, request_path, body)

        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }

        # [修复] 确保模拟盘标志被正确添加
        # 注意：这个 Header 不参与签名计算！
        if self.use_demo:
            headers["x-simulated-trading"] = "1"

        # [新增] 调试日志：输出时间戳和签名
        logger.debug(
            f"REST 请求头: method={request_method}, path={request_path}, "
            f"timestamp={timestamp}, sign={sign[:20]}..."
        )

        return headers

    async def post_signed(
        self,
        endpoint: str,
        body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送签名的 POST 请求 (修复 POST Body 格式)

        OKX 要求 POST Body 的 JSON 不能包含空格。
        aiohttp 默认的 json 序列化可能有空格，需要强制手动序列化。

        Args:
            endpoint (str): API 端点路径（如：/api/v5/trade/order）
            body (Dict[str, Any]): 请求体字典

        Returns:
            Dict[str, Any]: API 响应数据

        Raises:
            RuntimeError: 如果 Session 已关闭
            ClientError: 如果网络请求失败
            ValueError: 如果 API 返回错误

        Example:
            >>> response = await client.post_signed(
            ...     "/api/v5/trade/order",
            ...     {"instId": "BTC-USDT-SWAP", "side": "buy", "ordType": "market", "sz": "0.01"}
            ... )
            >>> print(response['code'])
            '0'
        """
        if self._closed:
            raise RuntimeError("ClientSession 已关闭")

        # 获取 Session
        session = await self._get_session()

        # [修复] 1. 强制去除 JSON 中的空格 (separators=(',', ':'))
        # OKX 要求 JSON 不能有空格和换行
        json_body = json.dumps(body, separators=(',', ':'))

        # [修复] 2. 生成 Header (使用无空格的字符串 body)
        headers = self._get_headers("POST", endpoint, json_body)

        # [修复] 3. 构造完整的 URL
        url = f"{self.base_url}{endpoint}"

        # 发送请求
        try:
            async with session.post(
                url,  # [修复] 使用完整 URL 而不是相对路径
                data=json_body,  # [修复] 传入字符串而不是字典
                headers=headers,
                timeout=self.timeout
            ) as response:
                # 🚨 修复：读取响应文本（用于错误诊断）
                response_text = await response.text()

                # 尝试解析 JSON
                try:
                    response_data = json.loads(response_text)
                except json.JSONDecodeError:
                    # JSON 解析失败，使用原始文本
                    response_data = {'code': 'N/A', 'msg': response_text}

                # 记录请求日志
                logger.debug(
                    f"POST {url} - Status: {response.status}, "
                    f"Code: {response_data.get('code', 'N/A')}"
                )

                # 检查 HTTP 状态码
                if response.status != 200:
                    # 🚨 修复：打印详细的错误信息
                    error_msg = f"HTTP 错误 {response.status}: {response_text}"
                    logger.error(error_msg)

                    # 如果是 400 错误（参数错误），通常重试也没用，直接抛出
                    if response.status == 400:
                        raise ValueError(error_msg)

                    raise ClientError(error_msg)

                # 检查 API 错误码
                if response_data.get('code') != '0':
                    error_msg = response_data.get('msg', 'Unknown error')
                    # 🚨 修复：打印完整的 API 响应
                    logger.error(f"API 错误 {response_data['code']}: {response_text}")
                    raise ValueError(f"API 错误: {response_data['code']} - {error_msg}")

                return response_data

        except aiohttp.ClientError as e:
            logger.error(f"网络请求失败: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            raise
        except Exception as e:
            logger.error(f"未知错误: {e}")
            raise

    async def get_signed(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        发送签名的 GET 请求 (修复参数签名问题)

        Args:
            endpoint (str): API 端点路径（如：/api/v5/account/balance）
            params (Optional[Dict[str, Any]]): 查询参数字典

        Returns:
            Dict[str, Any]: API 响应数据

        Example:
            >>> response = await client.get_signed("/api/v5/account/balance")
            >>> print(response['data'])
            [...]
        """
        if self._closed:
            raise RuntimeError("ClientSession 已关闭")

        # 获取 Session
        session = await self._get_session()

        # [修复] 完全重写 get_signed 方法，手动处理查询参数的拼接
        from urllib.parse import urlencode

        # 1. 处理查询参数
        request_path = endpoint
        if params:
            # 将字典转换为 URL 查询字符串 (例如: ?instId=SOL-USDT-SWAP&instType=SWAP)
            # 注意：OKX 要求参数按字母顺序排序
            sorted_params = sorted(params.items())
            query_string = urlencode(sorted_params)
            request_path = f"{endpoint}?{query_string}"

        # 2. 生成 Header (注意：这里传入带参数的 request_path)
        # GET 请求的 body 为空字符串
        headers = self._get_headers("GET", request_path, "")

        # 3. 发送请求 (使用完整的 request_path)
        url = f"{self.base_url}{request_path}"

        # 发送请求
        try:
            async with session.get(
                url,
                headers=headers,
                timeout=self.timeout
            ) as response:
                # 🚨 修复：读取响应文本（用于错误诊断）
                response_text = await response.text()

                # 尝试解析 JSON
                try:
                    response_data = json.loads(response_text)
                except json.JSONDecodeError:
                    # JSON 解析失败，使用原始文本
                    response_data = {'code': 'N/A', 'msg': response_text}

                # 记录请求日志
                logger.debug(
                    f"GET {url} - Status: {response.status}, "
                    f"Code: {response_data.get('code', 'N/A')}"
                )

                # 检查 HTTP 状态码
                if response.status != 200:
                    # 🚨 修复：打印详细的错误信息
                    error_msg = f"HTTP 错误 {response.status}: {response_text}"
                    logger.error(error_msg)

                    # 如果是 400 错误（参数错误），通常重试也没用，直接抛出
                    if response.status == 400:
                        raise ValueError(error_msg)

                    raise ClientError(error_msg)

                # 检查 API 错误码
                if response_data.get('code') != '0':
                    error_msg = response_data.get('msg', 'Unknown error')
                    # 🚨 修复：打印完整的 API 响应
                    logger.error(f"API 错误 {response_data['code']}: {response_text}")
                    raise ValueError(f"API 错误: {response_data['code']} - {error_msg}")

                return response_data

        except aiohttp.ClientError as e:
            logger.error(f"网络请求失败: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            raise
        except Exception as e:
            logger.error(f"未知错误: {e}")
            raise

    async def close(self):
        """
        关闭 ClientSession

        释放网络资源，应在使用完毕后调用。

        Example:
            >>> await client.close()
        """
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("ClientSession 已关闭")
        self._closed = True

    async def __aenter__(self):
        """
        异步上下文管理器入口

        Returns:
            RestClient: 返回自身
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        异步上下文管理器退出

        自动关闭 ClientSession。
        """
        await self.close()
