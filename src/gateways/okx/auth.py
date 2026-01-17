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
from datetime import datetime, timezone


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
        # 🔥 修复：使用 datetime.now(timezone.utc) 替代 datetime.utcnow()
        # 这样可以确保时间戳与 UTC 时区正确对齐，避免时间戳过期错误
        now = datetime.now(timezone.utc)

        if mode == 'iso':
            # 🔥 关键修复：使用 isoformat(timespec='milliseconds') 确保毫秒精度
            # 然后替换时区后缀为 'Z'（UTC 标准格式）
            iso_str = now.isoformat(timespec='milliseconds')
            # 将 +00:00 替换为 Z（OKX 要求的标准 UTC 格式）
            return iso_str.replace('+00:00', 'Z')
        else:
            # Unix 时间戳（毫秒字符串格式）
            # 🔥 关键：返回字符串格式，确保签名和 payload 使用完全相同的时间戳
            return str(int(now.timestamp() * 1000))

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
