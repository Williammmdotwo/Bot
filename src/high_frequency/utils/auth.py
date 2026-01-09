"""
OKX V5 API 签名工具

本模块提供 OKX V5 API 的签名功能，遵循以下原则：
- 纯函数实现，无状态，无副作用
- 不涉及任何网络请求
- 使用 Python 标准库，无额外依赖

OKX V5 API 签名算法：
1. 构造签名消息：timestamp + method + requestPath + body
2. 使用 SecretKey 进行 HMAC-SHA256 签名
3. Base64 编码签名结果
"""

import base64
import hmac
import hashlib
from datetime import datetime, timezone
from typing import Dict


def get_timestamp() -> str:
    """
    获取 ISO 8601 格式的时间戳

    格式示例：2023-01-01T00:00:00.000Z

    Returns:
        str: ISO 8601 格式的时间戳字符串
    """
    # [修复] 统一使用 strftime 方法，确保毫秒是 3 位
    # 例如: 2023-01-08T12:00:00.123Z
    dt = datetime.now(timezone.utc)
    # OKX 要求格式: YYYY-MM-DDThh:mm:ss.sssZ
    return dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


def _sign_message(timestamp: str, method: str, request_path: str, body: str, secret_key: str) -> str:
    """
    计算签名

    Args:
        timestamp (str): 请求时间戳
        method (str): HTTP 方法（GET, POST, PUT, DELETE）
        request_path (str): 请求路径（包含查询参数）
        body (str): 请求体（JSON 字符串）
        secret_key (str): API Secret Key

    Returns:
        str: Base64 编码的签名

    Example:
        >>> sign = _sign_message("2023-01-01T00:00:00.000Z", "POST", "/api/v5/trade/order", "{}", "secret")
        >>> print(sign)
        '...'
    """
    # [核对] 确保拼接顺序正确，且 method 必须大写
    message = str(timestamp) + str(method).upper() + str(request_path) + str(body)

    # 使用 SecretKey 进行 HMAC-SHA256 签名
    signature = hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()

    # Base64 编码签名结果
    signature_base64 = base64.b64encode(signature).decode('utf-8')

    return signature_base64


def generate_headers(
    timestamp: str,
    method: str,
    request_path: str,
    body: str,
    api_key: str,
    secret_key: str,
    passphrase: str
) -> Dict[str, str]:
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
        Dict[str, str]: 包含 OK-ACCESS-* 头的字典

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
    signature = _sign_message(timestamp, method, request_path, body, secret_key)

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
) -> Dict[str, str]:
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
        Dict[str, str]: 包含 OK-ACCESS-* 头的字典

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
    timestamp = get_timestamp()
    return generate_headers(
        timestamp=timestamp,
        method=method,
        request_path=request_path,
        body=body,
        api_key=api_key,
        secret_key=secret_key,
        passphrase=passphrase
    )
