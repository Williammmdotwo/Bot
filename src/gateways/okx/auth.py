"""
OKX API 签名工具 (OkxSigner)

提供 OKX API V5 的签名和时间戳生成功能。

签名逻辑：
1. 生成 ISO 时间戳
2. 拼接签名字符串: timestamp + method + path + body
3. 使用 HMAC-SHA256 签名
4. Base64 编码
"""

import base64
import hmac
import hashlib
import time
from datetime import datetime


class OkxSigner:
    """
    OKX API 签名器

    Example:
        >>> timestamp = OkxSigner.get_timestamp()
        >>> sign = OkxSigner.sign(timestamp, "GET", "/api/v5/account/balance", "", "your_secret")
    """

    @staticmethod
    def get_timestamp(mode: str = 'iso') -> str:
        """
        获取时间戳

        Args:
            mode (str): 模式
                - 'iso': ISO 8601 格式（YYYY-MM-DDTHH:MM:SS.sssZ）
                - 'unix': Unix 时间戳（毫秒）

        Returns:
            str: 时间戳字符串
        """
        if mode == 'iso':
            # ISO 8601 格式（UTC）
            now = datetime.utcnow()
            return now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        else:
            # Unix 时间戳（毫秒）
            return str(int(time.time() * 1000))

    @staticmethod
    def sign(
        timestamp: str,
        request_method: str,
        request_path: str,
        body: str,
        secret_key: str
    ) -> str:
        """
        生成 OKX API 签名

        Args:
            timestamp (str): 时间戳（ISO 8601 格式）
            request_method (str): 请求方法（GET/POST）
            request_path (str): 请求路径（包含查询参数）
            body (str): 请求体（JSON 字符串）
            secret_key (str): API Secret Key

        Returns:
            str: Base64 编码的签名

        签名步骤：
        1. 拼接字符串: timestamp + request_method + request_path + body
        2. 使用 HMAC-SHA256 签名
        3. Base64 编码
        """
        # 拼接签名字符串
        message = timestamp + request_method + request_path + body

        # HMAC-SHA256 签名
        mac = hmac.new(
            secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        )

        # Base64 编码
        signature = base64.b64encode(mac.digest()).decode('utf-8')

        return signature
