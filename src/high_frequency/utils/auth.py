"""
OKX V5 API 签名工具 (最简绝对正确版)

本模块提供 OKX V5 API 的签名功能，遵循以下原则：
- 使用 Python 最原始、最不会出错的 UTC 格式化方式
- 抛弃所有花哨的写法，确保绝对正确
- 支持时间校准功能

OKX V5 API 签名算法：
1. 构造签名消息：timestamp + method + requestPath + body
2. 使用 SecretKey 进行 HMAC-SHA256 签名
3. Base64 编码签名结果
"""

import hmac
import base64
import hashlib
import datetime

# 全局时间偏移量（秒）
_TIME_OFFSET = 0.0


class OkxSigner:
    """
    OKX V5 API 统一鉴权工具 (2026 兼容版)
    """

    @staticmethod
    def set_time_offset(offset_seconds: float):
        """
        设置全局时间偏移量

        Args:
            offset_seconds (float): 时间偏移量（秒），正数表示本地时间比服务器慢
        """
        global _TIME_OFFSET
        _TIME_OFFSET = offset_seconds

    @staticmethod
    def get_time_offset() -> float:
        """
        获取当前的全局时间偏移量

        Returns:
            float: 时间偏移量（秒）
        """
        global _TIME_OFFSET
        return _TIME_OFFSET

    @staticmethod
    def get_timestamp():
        """
        获取 ISO 8601 格式时间戳 (UTC)
        格式: YYYY-MM-DDThh:mm:ss.sssZ

        Returns:
            str: ISO 8601 格式的时间戳
        """
        # 使用 standard UTC
        dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=_TIME_OFFSET)

        # 强制格式化，确保毫秒为3位
        return dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    @staticmethod
    def sign(timestamp, method, request_path, body, secret_key):
        """
        生成签名

        Args:
            timestamp: 请求时间戳
            method: HTTP 方法
            request_path: 请求路径
            body: 请求体
            secret_key: API Secret Key

        Returns:
            str: Base64 编码的签名
        """
        # 1. 确保 body 是字符串
        if body is None:
            body = ''

        # 2. 拼接字符串 (这是最容易错的地方)
        # 必须严格按照: timestamp + METHOD + request_path + body
        message = f"{str(timestamp)}{str(method).upper()}{str(request_path)}{str(body)}"

        # 3. HMAC SHA256
        mac = hmac.new(
            bytes(secret_key, encoding='utf-8'),
            bytes(message, encoding='utf-8'),
            digestmod=hashlib.sha256
        )

        # 4. Base64
        return base64.b64encode(mac.digest()).decode('utf-8')


# 保留向后兼容的函数接口
def set_time_offset(offset_seconds: float):
    """设置全局时间偏移量（向后兼容）"""
    OkxSigner.set_time_offset(offset_seconds)


def get_time_offset() -> float:
    """获取当前的全局时间偏移量（向后兼容）"""
    return OkxSigner.get_time_offset()


def get_timestamp() -> str:
    """获取 ISO 8601 格式的时间戳（向后兼容）"""
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

    Args:
        timestamp (str): 请求时间戳（ISO 8601 格式）
        method (str): HTTP 方法（GET, POST, PUT, DELETE）
        request_path (str): 请求路径（包含查询参数）
        body (str): 请求体（JSON 字符串）
        api_key (str): API Key
        secret_key (str): API Secret Key
        passphrase (str): API Passphrase

    Returns:
        dict: 包含 OK-ACCESS-* 头的字典
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

    Args:
        method (str): HTTP 方法（GET, POST, PUT, DELETE）
        request_path (str): 请求路径（包含查询参数）
        body (str): 请求体（JSON 字符串）
        api_key (str): API Key
        secret_key (str): API Secret Key
        passphrase (str): API Passphrase

    Returns:
        dict: 包含 OK-ACCESS-* 头的字典
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
