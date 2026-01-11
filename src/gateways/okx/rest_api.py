"""
OKX REST API 网关 (Unified Gateway)

统一的 OKX REST API 客户端，整合了 HFT 客户端的异步特性和基类的 K线功能。

关键特性：
- 持久 Session 复用（TCP Keep-Alive）
- 自动 OKX V5 API 签名（使用 OkxSigner）
- 完整的异步上下文管理
- 低延迟，高吞吐量
- 统一的 K线获取功能

设计原则：
- 继承 RestGateway 基类
- 使用 aiohttp（高性能异步）
- 支持 REST 和 WebSocket 双网关
- 集成 K线、持仓、订单等功能
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List
import aiohttp
from aiohttp import ClientSession, ClientTimeout, ClientError
from .auth import OkxSigner
from ..base_gateway import RestGateway
from ...core.event_types import Event, EventType

logger = logging.getLogger(__name__)


class OkxRestGateway(RestGateway):
    """
    OKX REST API 网关

    整合了 HFT 客户端的异步特性和基类的 K线功能。

    Example:
        >>> async with OkxRestGateway(
        ...     api_key="your_api_key",
        ...     secret_key="your_secret",
        ...     passphrase="your_passphrase",
        ...     use_demo=True
        ... ) as gateway:
        ...     await gateway.connect()
        ...     balance = await gateway.get_balance()
        ...     print(balance)
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        base_url: str = "https://www.okx.com",
        use_demo: bool = False,
        timeout: int = 10,
        event_bus=None
    ):
        """
        初始化 OKX REST 网关

        Args:
            api_key (str): OKX API Key
            secret_key (str): OKX Secret Key
            passphrase (str): OKX Passphrase
            base_url (str): API 基础 URL
            use_demo (bool): 是否使用模拟交易
            timeout (int): 请求超时时间（秒）
            event_bus: 事件总线实例
        """
        super().__init__(
            name="okx_rest",
            event_bus=event_bus
        )

        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.base_url = base_url.rstrip('/')
        self.use_demo = use_demo
        self.timeout = timeout

        # 创建持久的 ClientSession
        self.session: Optional[ClientSession] = None
        self._closed = False

        logger.info(
            f"OkxRestGateway 初始化: base_url={self.base_url}, "
            f"use_demo={use_demo}, timeout={timeout}s"
        )

    async def connect(self) -> bool:
        """
        连接网关

        Returns:
            bool: 连接是否成功
        """
        try:
            # 创建 Session
            await self._get_session()
            self._connected = True
            logger.info(f"OkxRestGateway 已连接: {self.base_url}")
            return True
        except Exception as e:
            logger.error(f"OkxRestGateway 连接失败: {e}")
            return False

    async def disconnect(self):
        """断开连接"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("OkxRestGateway 已断开")
        self._connected = False

    async def is_connected(self) -> bool:
        """
        检查连接状态

        Returns:
            bool: 是否已连接
        """
        return self._connected and self.session and not self.session.closed

    async def _get_session(self) -> ClientSession:
        """
        获取或创建 ClientSession

        Returns:
            ClientSession: aiohttp ClientSession 实例
        """
        if self.session is None or self.session.closed:
            if self._closed:
                raise RuntimeError("ClientSession 已关闭，无法创建新连接")

            timeout = ClientTimeout(total=self.timeout)
            connector = aiohttp.TCPConnector(
                limit=100,
                ttl_dns_cache=300,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )

            self.session = ClientSession(
                base_url=self.base_url,
                timeout=timeout,
                connector=connector
            )

            logger.debug("创建新的 ClientSession")

        return self.session

    def _get_headers(self, request_method: str, request_path: str, body: str = "") -> dict:
        """
        生成 REST API 请求头

        Args:
            request_method (str): 请求方法（GET/POST）
            request_path (str): 请求路径
            body (str): 请求体

        Returns:
            dict: 请求头
        """
        # 使用 OkxSigner 生成时间戳和签名
        timestamp = OkxSigner.get_timestamp(mode='iso')
        sign = OkxSigner.sign(timestamp, request_method, request_path, body, self.secret_key)

        logger.debug(
            f"🔐 [REST 签名] timestamp={timestamp}, method={request_method}, "
            f"path={request_path}"
        )

        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }

        if self.use_demo:
            headers["x-simulated-trading"] = "1"

        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        发送 HTTP 请求（内部方法）

        Args:
            method (str): 请求方法（GET/POST）
            endpoint (str): API 端点
            data (dict): POST 数据
            params (dict): GET 参数

        Returns:
            dict: API 响应
        """
        if self._closed:
            raise RuntimeError("ClientSession 已关闭")

        session = await self._get_session()

        # 构造请求路径
        request_path = endpoint
        if params:
            from urllib.parse import urlencode
            clean_params = {k: v for k, v in params.items() if v is not None}
            if clean_params:
                query_string = urlencode(clean_params, safe=',')
                request_path = f"{endpoint}?{query_string}"

        # 生成请求头
        body_str = ""
        if data:
            body_str = json.dumps(data, separators=(',', ':'))
        headers = self._get_headers(method, request_path, body_str)

        try:
            if method == "GET":
                async with session.get(request_path, headers=headers, timeout=self.timeout) as response:
                    return await self._parse_response(response)
            elif method == "POST":
                async with session.post(
                    request_path,
                    data=body_str,
                    headers=headers,
                    timeout=self.timeout
                ) as response:
                    return await self._parse_response(response)
            else:
                raise ValueError(f"不支持的 HTTP 方法: {method}")

        except aiohttp.ClientError as e:
            logger.error(f"网络请求失败: {e}")
            raise
        except Exception as e:
            logger.error(f"未知错误: {e}")
            raise

    async def _parse_response(self, response) -> Dict[str, Any]:
        """
        解析 API 响应

        Args:
            response: aiohttp 响应对象

        Returns:
            dict: 解析后的数据
        """
        response_text = await response.text()

        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError:
            response_data = {'code': 'N/A', 'msg': response_text}

        logger.debug(
            f"响应: status={response.status}, code={response_data.get('code')}"
        )

        if response.status != 200:
            error_msg = f"HTTP 错误 {response.status}: {response_text}"
            logger.error(error_msg)
            raise ClientError(error_msg)

        if response_data.get('code') != '0':
            error_code = response_data.get('code')
            error_msg = response_data.get('msg') or 'Unknown error'
            logger.error(f"API 错误: {error_code} - {error_msg}")
            raise ValueError(f"API 错误: {error_code} - {error_msg}")

        return response_data

    # ========== RestGateway 接口实现 ==========

    async def get_balance(self, currency: str = "USDT") -> Dict[str, Any]:
        """
        获取账户余额

        Args:
            currency (str): 货币符号

        Returns:
            dict: 余额信息
        """
        try:
            response = await self._request(
                "GET",
                "/api/v5/account/balance",
                params={"ccy": currency}
            )
            data_list = response.get('data', [])
            if data_list:
                return data_list[0]
            return {}
        except Exception as e:
            logger.error(f"获取余额失败: {e}")
            return {}

    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取持仓信息

        Args:
            symbol (str): 交易对（可选）

        Returns:
            list: 持仓列表
        """
        try:
            params = {'instType': 'SWAP'}
            if symbol:
                params['instId'] = symbol

            response = await self._request(
                "GET",
                "/api/v5/account/positions",
                params=params
            )

            raw_positions = response.get('data', [])
            parsed_positions = []

            for raw in raw_positions:
                pos = {
                    'symbol': raw.get('instId'),
                    'size': float(raw.get('pos', 0)),
                    'entry_price': float(raw.get('avgPx', 0)) if raw.get('avgPx') else 0.0,
                    'unrealized_pnl': float(raw.get('upl', 0)) if raw.get('upl') else 0.0,
                    'leverage': int(raw.get('lever', 1)) if raw.get('lever') else 1,
                    'side': raw.get('posSide', 'net'),
                    'raw': raw
                }
                parsed_positions.append(pos)

            return parsed_positions

        except Exception as e:
            logger.error(f"获取持仓失败: {e}")
            return []

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        size: float,
        price: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        下单

        Args:
            symbol (str): 交易对
            side (str): 方向（buy/sell）
            order_type (str): 订单类型（market/limit/ioc）
            size (float): 数量
            price (float): 价格
            **kwargs: 其他参数

        Returns:
            dict: 订单响应
        """
        try:
            # 构造订单数据
            # 1. 确保 ordType 小写（OKX V5 API 需要 market/limit）
            ord_type_lower = order_type.lower() if order_type else 'market'

            # 2. 确保 sz 是整数（SWAP/FUTURES 合约必须整数）
            size_int = int(size) if size is not None else 1
            if size_int < 1:
                logger.warning(f"⚠️  size {size} 小于 1，强制设为 1")
                size_int = 1

            body = {
                'instId': symbol,
                'tdMode': 'cross',  # ✅ 必须有
                'side': side,
                'sz': str(size_int)
            }

            # ✅ 处理止损单（stop_market / stop_limit）
            if order_type in ['stop_market', 'stop_limit']:
                # OKX V5 使用 conditional 订单类型实现止损
                body['ordType'] = 'conditional'
                body['slTriggerType'] = 'last'  # 使用最新价触发
                body['slOrdPx'] = str(price)  # 止损触发价格

                if order_type == 'stop_limit':
                    # 止损限价单：设置限价价格
                    tp_price = kwargs.get('tp_price')
                    if tp_price:
                        body['tpOrdPx'] = str(tp_price)

                logger.info(f"🛡️  止损单: slOrdPx={price}, ordType=conditional")
            else:
                # 普通订单（market/limit/ioc）
                body['ordType'] = ord_type_lower

                # limit/ioc 订单需要价格
                if order_type in ['limit', 'ioc'] and price:
                    body['px'] = str(price)

            # 生成 Client Order ID (clOrdId) 用于标识策略来源
            # clOrdId 限制：1-32 位字符，必须是纯字母数字
            if 'clOrdId' not in body:
                strategy_id = kwargs.get('strategy_id', 'manual')
                # 取策略 ID 前缀（最多 4 位）
                prefix = strategy_id[:4].lower()
                # 加上时间戳后缀（确保唯一性）
                ts_suffix = str(int(time.time() * 1000))[-8:]
                # ✅ 去掉下划线，确保是纯字母数字
                body['clOrdId'] = f"{prefix}{ts_suffix}"
                logger.debug(f"🏷️  生成 clOrdId: {body['clOrdId']} (strategy_id={strategy_id})")

            # 添加额外参数，但只保留 OKX API 支持的字段
            # OKX V5 API 支持的下单字段白名单
            # ✅ 必须包含 tdMode，❌ 绝对不要包含 posSide
            okx_order_fields = {
                'instId', 'tdMode', 'side', 'ordType', 'sz', 'px',
                'reduceOnly', 'clOrdId', 'ccy'
            }

            # 过滤：只保留 OKX API 支持的字段
            # 注意：不包含 'tag' 和 'strategy_id'
            for key in list(kwargs.keys()):
                if key in okx_order_fields:
                    body[key] = kwargs[key]

            # ❌ 确保没有 posSide
            body.pop('posSide', None)

            logger.info(f"下单: {body}")

            response = await self._request(
                "POST",
                "/api/v5/trade/order",
                data=body
            )

            data_list = response.get('data', [])
            if data_list:
                order_data = data_list[0]

                # 发布订单更新事件
                if self._event_bus:
                    event = Event(
                        type=EventType.ORDER_UPDATE,
                        data={
                            'order_id': order_data.get('ordId'),
                            'symbol': symbol,
                            'side': side,
                            'order_type': order_type,
                            'price': float(price) if price else 0.0,
                            'size': float(size),
                            'status': 'live',
                            'raw': order_data
                        },
                        source="okx_rest"
                    )
                    self.publish_event(event)

                return order_data

            return {}

        except Exception as e:
            logger.error(f"下单失败: {e}")
            raise

    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """
        撤单

        Args:
            order_id (str): 订单 ID
            symbol (str): 交易对

        Returns:
            dict: 撤单响应
        """
        try:
            body = {
                'instId': symbol,
                'ordId': order_id
            }

            response = await self._request(
                "POST",
                "/api/v5/trade/cancel-order",
                data=body
            )

            data_list = response.get('data', [])
            if data_list:
                # 发布订单取消事件
                if self._event_bus:
                    event = Event(
                        type=EventType.ORDER_CANCELLED,
                        data={
                            'order_id': order_id,
                            'symbol': symbol,
                            'raw': data_list[0]
                        },
                        source="okx_rest"
                    )
                    self.publish_event(event)

                return data_list[0]

            return {}

        except Exception as e:
            logger.error(f"撤单失败: {e}")
            raise

    async def get_order_status(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """
        查询订单状态

        Args:
            order_id (str): 订单 ID
            symbol (str): 交易对

        Returns:
            dict: 订单状态
        """
        try:
            response = await self._request(
                "GET",
                "/api/v5/trade/order",
                params={'instId': symbol, 'ordId': order_id}
            )

            data_list = response.get('data', [])
            if data_list:
                return data_list[0]
            return {}

        except Exception as e:
            logger.error(f"查询订单状态失败: {e}")
            return {}

    async def get_kline(
        self,
        symbol: str,
        interval: str = "1m",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取 K线数据

        Args:
            symbol (str): 交易对
            interval (str): 周期（1m, 5m, 1h, 1d）
            limit (int): 数量限制

        Returns:
            list: K线数据列表
        """
        try:
            # 映射 OKX 的周期格式
            interval_map = {
                '1m': '1m',
                '5m': '5m',
                '15m': '15m',
                '30m': '30m',
                '1h': '1H',
                '4h': '4H',
                '1d': '1D'
            }
            okx_interval = interval_map.get(interval, interval)

            response = await self._request(
                "GET",
                "/api/v5/market/candles",
                params={
                    'instId': symbol,
                    'bar': okx_interval,
                    'limit': str(limit)
                }
            )

            raw_candles = response.get('data', [])
            candles = []

            for candle in raw_candles:
                candles.append({
                    'timestamp': int(candle[0]),
                    'open': float(candle[1]),
                    'high': float(candle[2]),
                    'low': float(candle[3]),
                    'close': float(candle[4]),
                    'volume': float(candle[5])
                })

            # 返回倒序（最新的在最后）
            return candles[::-1]

        except Exception as e:
            logger.error(f"获取 K线失败: {e}")
            return []

    async def get_instruments(
        self,
        inst_type: Optional[str] = "SWAP"
    ) -> List[Dict[str, Any]]:
        """
        获取交易对信息（动态加载交易对配置）

        Args:
            inst_type (str): 合约类型（默认 "SWAP" 永续合约）

        Returns:
            list: 交易对信息列表，每个元素包含：
                - instId: 交易对 ID（如 "BTC-USDT-SWAP"）
                - lotSz: 数量精度
                - minSz: 最小下单数量
                - tickSz: 价格精度
                - state: 交易状态（live, suspend, etc.）
        """
        try:
            # 构造请求参数
            params = {'instType': inst_type}

            response = await self._request(
                "GET",
                "/api/v5/public/instruments",
                params=params
            )

            raw_instruments = response.get('data', [])
            parsed_instruments = []

            for raw in raw_instruments:
                # 只返回交易状态正常的交易对
                state = raw.get('state', '')
                if state != 'live':
                    continue

                instrument = {
                    'instId': raw.get('instId'),
                    'lotSz': float(raw.get('lotSz', 0)) if raw.get('lotSz') else 0.0,
                    'minSz': float(raw.get('minSz', 0)) if raw.get('minSz') else 0.0,
                    'tickSz': float(raw.get('tickSz', 0)) if raw.get('tickSz') else 0.0,
                    'state': state,
                    'raw': raw
                }
                parsed_instruments.append(instrument)

            logger.info(
                f"获取交易对信息成功: {len(parsed_instruments)} 个交易对 "
                f"(instType={inst_type})"
            )

            return parsed_instruments

        except Exception as e:
            logger.error(f"获取交易对信息失败: {e}", exc_info=True)
            return []

    async def set_leverage(
        self,
        symbol: str,
        leverage: int,
        mgn_mode: str = "cross"
    ) -> Dict[str, Any]:
        """
        设置杠杆

        Args:
            symbol (str): 交易对
            leverage (int): 杠杆倍数
            mgn_mode (str): 保证金模式（cross/isolated）

        Returns:
            dict: 设置结果
        """
        try:
            body = {
                'instId': symbol,
                'lever': str(leverage),
                'mgnMode': mgn_mode
            }

            response = await self._request(
                "POST",
                "/api/v5/account/set-leverage",
                data=body
            )

            data_list = response.get('data', [])
            if data_list:
                logger.info(f"✅ 杠杆已设置: {symbol} {leverage}x ({mgn_mode})")
                return data_list[0]

            return {}

        except Exception as e:
            logger.error(f"设置杠杆失败: {e}")
            raise

    async def close(self):
        """关闭网关"""
        await self.disconnect()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()
