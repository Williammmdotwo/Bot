"""
OKX V5 API 签名工具

本模块提供 OKX V5 API 的签名功能，遵循以下原则：
- 参考官方 SDK 标准实现
- 使用标准的 datetime 方法
- 确保时间戳格式严格符合 OKX 要求

OKX V5 API 签名算法：
1. 构造签名消息：timestamp + method + requestPath + body
2. 使用 SecretKey 进行 HMAC-SHA256 签名
3. Base64 编码签名结果

时间校准功能：
- 支持全局时间偏移量，用于校准本地时间与服务器时间的差异
- 在 main_hft.py 启动时从时间同步检查中获取偏移量
- 所有签名请求自动使用校准后的时间戳
"""

import hmac
import base64
import hashlib
import datetime

# [修复] 全局时间偏移量（秒）
_TIME_OFFSET = 0.0


class OkxSigner:
    """OKX V5 API 统一鉴权工具"""

    @staticmethod
    def set_time_offset(offset_seconds: float):
        """
        设置全局时间偏移量

        Args:
            offset_seconds (float): 时间偏移量（秒），正数表示本地时间比服务器慢

        Example:
            >>> # 如果本地时间比服务器慢 2 秒
            >>> OkxSigner.set_time_offset(2.0)
            >>> # 现在所有 get_timestamp() 调用都会自动加 2 秒
        """
        global _TIME_OFFSET
        _TIME_OFFSET = offset_seconds

    @staticmethod
    def get_time_offset() -> float:
        """
        获取当前的全局时间偏移量

        Returns:
            float: 时间偏移量（秒）

        Example:
            >>> offset = OkxSigner.get_time_offset()
            >>> print(f"当前时间偏移量: {offset} 秒")
        """
        global _TIME_OFFSET
        return _TIME_OFFSET

    @staticmethod
    def get_timestamp():
        """
        生成 OKX 要求的 ISO 8601 时间戳 (UTC)
        使用官方 SDK 推荐的标准写法

        Returns:
            str: ISO 8601 格式的时间戳，例如: 2023-01-01T12:00:00.123Z

        Example:
            >>> ts = OkxSigner.get_timestamp()
            >>> print(ts)
            '2023-01-01T12:00:00.123Z'
        """
        # 使用 timezone.utc 确保是 UTC 时间
        # [修复] 加上时间偏移量进行校准
        dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=_TIME_OFFSET)

        # 格式化: 2023-01-01T12:00:00.123Z
        # timespec='milliseconds' 确保只有3位小数（毫秒精度）
        # replace('+00:00', 'Z') 替换时区后缀为 Z
        return dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    @staticmethod
    def sign(timestamp: str, method: str, request_path: str, body: str, secret_key: str) -> str:
        """
        生成签名

        Args:
            timestamp (str): 请求时间戳
            method (str): HTTP 方法（GET, POST, PUT, DELETE）
            request_path (str): 请求路径（包含查询参数）
            body (str): 请求体（JSON 字符串）
            secret_key (str): API Secret Key

        Returns:
            str: Base64 编码的签名

        Example:
            >>> sign = OkxSigner.sign(
            ...     "2023-01-01T00:00:00.000Z",
            ...     "POST",
            ...     "/api/v5/trade/order",
            ...     "{}",
            ...     "secret"
            ... )
            >>> print(sign)
            '...'
        """
        # 确保 body 不为 None
        if not body:
            body = ''

        # 构造签名字符串: timestamp + method + request_path + body
        # 注意：method 必须大写
        message = f"{timestamp}{method.upper()}{request_path}{body}"

        # 使用 SecretKey 进行 HMAC-SHA256 签名
        mac = hmac.new(
            bytes(secret_key, encoding='utf-8'),
            bytes(message, encoding='utf-8'),
            digestmod=hashlib.sha256
        )

        # Base64 编码签名结果
        signature = base64.b64encode(mac.digest()).decode('utf-8')

        return signature


# 保留向后兼容的函数接口
def set_time_offset(offset_seconds: float):
    """设置全局时间偏移量（向后兼容）"""
    OkxSigner.set_time_offset(offset_seconds)


def get_time_offset() -> float:
    """获取当前的全局时间偏移量（向后兼容）"""
    return OkxSigner.get_time_offset()


def get_timestamp() -> str:
    """
    获取 ISO 8601 格式的时间戳（向后兼容）

    Returns:
        str: ISO 8601 格式的时间戳字符串
    """
    return OkxSigner.get_timestamp()


def _sign_message(timestamp: str, method: str, request_path: str, body: str, secret_key: str) -> str:
    """计算签名（向后兼容）"""
    return OkxSigner.sign(timestamp, method, request_path, body, secret_key)


def generate_headers(
    timestamp: str,
    method: str,
    request_path: str,
    body: str,
    api_key: str,
    secret_key: str,
    passphrase: str
) -> dict:
    """
    生成 OKX V5 API 请求头

    此函数是一个纯函数，不涉及任何网络请求或外部状态。

    Args:
        timestamp (str): 请求时间戳（ISO 8601 格式）
        method (str): HTTP 方法（GET, POST, PUT, DELETE）
        request_path (str): 请求路径（包含查询参数，如：/api/v5/trade/order?param1=value1）
        body (str): 请求体（JSON 字符串，如：{"instId": "BTC-USDT-SWAP"}）
        api_key (str): API Key
        secret_key (str): API Secret Key
        passphrase (str): API Passphrase

    Returns:
        dict: 包含 OK-ACCESS-* 头的字典

    Raises:
        ValueError: 如果必需参数为空

    Example:
        >>> headers = generate_headers(
        ...     timestamp="2023-01-01T00:00:00.000Z",
        ...     method="POST",
        ...     request_path="/api/v5/trade/order",
        ...     body='{"instId": "BTC-USDT-SWAP"}',
        ...     api_key="your-api-key",
        ...     secret_key="your-secret-key",
        ...     passphrase="your-passphrase"
        ... )
        >>> print(headers['OK-ACCESS-SIGN'])
        '...'
    """
    # 参数验证
    if not all([timestamp, method, request_path, api_key, secret_key, passphrase]):
        raise ValueError("所有参数都不能为空")

    if method.upper() not in ['GET', 'POST', 'PUT', 'DELETE']:
        raise ValueError(f"不支持的 HTTP 方法: {method}")

    # 如果 body 为 None，转换为空字符串
    if body is None:
        body = ""

    # 计算签名
    signature = OkxSigner.sign(timestamp, method, request_path, body, secret_key)

    # 构造请求头
    headers = {
        'OK-ACCESS-KEY': api_key,
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASSPHRASE': passphrase,
        'Content-Type': 'application/json'
    }

    return headers


def generate_headers_with_auto_timestamp(
    method: str,
    request_path: str,
    body: str,
    api_key: str,
    secret_key: str,
    passphrase: str
) -> dict:
    """
    生成 OKX V5 API 请求头（自动生成时间戳）

    便捷函数，自动生成当前时间戳。

    Args:
        method (str): HTTP 方法（GET, POST, PUT, DELETE）
        request_path (str): 请求路径（包含查询参数）
        body (str): 请求体（JSON 字符串）
        api_key (str): API Key
        secret_key (str): API Secret Key
        passphrase (str): API Passphrase

    Returns:
        dict: 包含 OK-ACCESS-* 头的字典

    Example:
        >>> headers = generate_headers_with_auto_timestamp(
        ...     method="POST",
        ...     request_path="/api/v5/trade/order",
        ...     body='{"instId": "BTC-USDT-SWAP"}',
        ...     api_key="your-api-key",
        ...     secret_key="your-secret-key",
        ...     passphrase="your-passphrase"
        ... )
        >>> print(headers['OK-ACCESS-TIMESTAMP'])
        '2023-01-01T00:00:00.000Z'
    """
    timestamp = OkxSigner.get_timestamp()
    return generate_headers(
        timestamp=timestamp,
        method=method,
        request_path=request_path,
        body=body,
        api_key=api_key,
        secret_key=secret_key,
        passphrase=passphrase
    )
