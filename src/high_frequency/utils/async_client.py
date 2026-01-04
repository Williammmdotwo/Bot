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

    async def post_signed(
        self,
        endpoint: str,
        body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送签名的 POST 请求

        自动调用 auth.py 进行签名，添加 OK-ACCESS-* 头。

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

        # 转换请求体为 JSON 字符串
        body_json = json.dumps(body, separators=(',', ':'))  # 紧凑格式，减少体积

        # 生成签名头
        headers = generate_headers_with_auto_timestamp(
            method="POST",
            request_path=endpoint,
            body=body_json,
            api_key=self.api_key,
            secret_key=self.secret_key,
            passphrase=self.passphrase
        )

        # 如果是模拟交易，添加模拟交易头
        if self.use_demo:
            headers['x-simulated-trading'] = '1'

        # 发送请求
        try:
            async with session.post(
                endpoint,
                data=body_json,
                headers=headers
            ) as response:
                # 读取响应
                response_data = await response.json()

                # 记录请求日志
                logger.debug(
                    f"POST {endpoint} - Status: {response.status}, "
                    f"Code: {response_data.get('code', 'N/A')}"
                )

                # 检查 HTTP 状态码
                if response.status != 200:
                    raise ClientError(
                        f"HTTP 错误: {response.status} - {response_data.get('msg', 'Unknown error')}"
                    )

                # 检查 API 错误码
                if response_data.get('code') != '0':
                    error_msg = response_data.get('msg', 'Unknown error')
                    logger.error(f"API 错误: {response_data['code']} - {error_msg}")
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
        发送签名的 GET 请求

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

        # 构造请求路径（包含查询参数）
        request_path = endpoint
        if params:
            # 对查询参数进行排序和编码
            from urllib.parse import urlencode
            sorted_params = sorted(params.items())
            query_string = urlencode(sorted_params)
            request_path = f"{endpoint}?{query_string}"

        # GET 请求的 body 为空字符串
        body_json = ""

        # 生成签名头
        headers = generate_headers_with_auto_timestamp(
            method="GET",
            request_path=request_path,
            body=body_json,
            api_key=self.api_key,
            secret_key=self.secret_key,
            passphrase=self.passphrase
        )

        # 如果是模拟交易，添加模拟交易头
        if self.use_demo:
            headers['x-simulated-trading'] = '1'

        # 发送请求
        try:
            async with session.get(
                endpoint,
                params=params,
                headers=headers
            ) as response:
                # 读取响应
                response_data = await response.json()

                # 记录请求日志
                logger.debug(
                    f"GET {endpoint} - Status: {response.status}, "
                    f"Code: {response_data.get('code', 'N/A')}"
                )

                # 检查 HTTP 状态码
                if response.status != 200:
                    raise ClientError(
                        f"HTTP 错误: {response.status} - {response_data.get('msg', 'Unknown error')}"
                    )

                # 检查 API 错误码
                if response_data.get('code') != '0':
                    error_msg = response_data.get('msg', 'Unknown error')
                    logger.error(f"API 错误: {response_data['code']} - {error_msg}")
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
