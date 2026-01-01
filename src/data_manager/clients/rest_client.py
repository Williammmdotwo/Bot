"""
OKX REST API 客户端 (Requests Bypass Mode - Signature Fix)

1. 使用 requests 绕过 CCXT 网络层。
2. 使用 CCXT sign() 生成签名。
3. 关键修复：直接使用 sign() 返回的完整 URL，确保请求参数顺序与签名完全一致。
"""

import ccxt
import logging
import os
import json
import requests

logger = logging.getLogger(__name__)

class RESTClient:
    """OKX REST API 客户端"""

    def __init__(self, api_key=None, secret_key=None, passphrase=None, use_demo=False):
        self.logger = logging.getLogger(__name__)
        self.is_demo = use_demo

        # === 自动补全凭证 ===
        if not api_key:
            api_key = os.getenv('OKX_API_KEY')
            secret_key = os.getenv('OKX_SECRET_KEY')
            passphrase = os.getenv('OKX_PASSPHRASE')

        # 1. 基础配置 (仅用于签名)
        exchange_config = {
            'apiKey': api_key,
            'secret': secret_key,
            'password': passphrase,
            'options': {'defaultType': 'swap'}
        }

        # 2. 初始化 CCXT (仅作为签名器)
        self.signer = ccxt.okx(exchange_config)
        self.has_credentials = bool(api_key and secret_key and passphrase)

        # 3. 初始化公有 Exchange
        try:
            config_public = {
                'timeout': 30000,
                'enableRateLimit': True,
                'options': {'defaultType': 'swap'}
            }
            self.public_exchange = ccxt.okx(config_public)
            base_url = 'https://www.okx.com'
            self.public_exchange.urls['api'] = {
                'public': base_url, 'private': base_url, 'rest': base_url, 'v5': base_url
            }
            self.logger.info("Public Exchange initialized")

        except Exception as e:
            self.logger.error(f"Public Exchange 初始化失败: {e}")
            raise

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=100):
        """获取K线数据"""
        try:
            limit = int(limit) if limit else 100
            if since: since = int(since)
            candles = self.public_exchange.fetch_ohlcv(
                symbol=symbol, timeframe=timeframe, since=since, limit=limit
            )
            return candles if isinstance(candles, list) else []
        except Exception as e:
            self.logger.error(f"Failed to fetch OHLCV: {e}")
            return []

    def fetch_positions(self, symbol=None):
        """
        获取持仓 - 使用 requests 直接发送请求
        """
        if not self.has_credentials:
            return []

        try:
            # 1. 准备参数
            params = {}
            # OKX V5 建议必须带 instType，否则可能报错或查不到
            params['instType'] = 'SWAP'
            if symbol:
                 params['instId'] = symbol

            # 2. 准备签名素材
            # endpoint 必须是路径，不能带域名
            path = '/api/v5/account/positions'

            # 3. 签名 (Magic Happens Here)
            # CCXT 会把 params 拼接到 path 后面，并生成 signature
            # 返回的 request['url'] 包含了完整的 query string
            # ⚠️ 注意：我们要给 sign 传完整的 url 还是 path？
            # ccxt.okx 的 sign 方法期望传入 path (e.g. 'account/positions')
            # 并且它会自动处理 api/v5 前缀吗？这取决于 ccxt 版本。
            # 最稳妥的方式：直接模仿 ccxt 内部逻辑，只传 path 的核心部分，或者使用全路径

            # 修正：CCXT 的 sign 方法对于 OKX，通常期望 path 是不带 api/v5 的？
            # 不，CCXT 内部 urls['api']['public'] 都有定义。
            # 这里我们手动 hack 一下：
            # 我们直接把 signer 的 urls 覆盖掉，确保 sign() 生成正确的完整 URL
            self.signer.urls['api'] = {
                'public': 'https://www.okx.com',
                'private': 'https://www.okx.com',
                'rest': 'https://www.okx.com',
            }

            # 签名
            # sign(path, api='public', method='GET', params={}, headers=None, body=None)
            request = self.signer.sign('account/positions', 'private', 'GET', params)

            # 4. 提取最终的 URL 和 Headers
            signed_url = request['url'] # 这里已经是 https://www.okx.com/api/v5/account/positions?instType=SWAP...
            headers = request['headers']

            # 5. 注入模拟盘 Header
            if self.is_demo:
                headers['x-simulated-trading'] = '1'

            # 6. 发送请求
            # ⚠️ 关键：这里 params 传 None，因为参数已经在 signed_url 里了！
            # 这样避免了 requests 重新排序参数导致签名失效
            response = requests.get(signed_url, headers=headers, params=None, timeout=10)

            # 7. 处理响应
            if response.status_code == 200:
                data = response.json()
                if data['code'] == '0':
                    raw_positions = data['data']
                    parsed_positions = []
                    for raw in raw_positions:
                        pos = {
                            'symbol': raw.get('instId'),
                            'size': float(raw.get('pos', 0)),
                            'side': raw.get('posSide', 'net'),
                            'raw': raw
                        }
                        parsed_positions.append(pos)
                    return parsed_positions
                else:
                    self.logger.error(f"OKX API Error: {data['code']} - {data['msg']}")
                    return []
            else:
                self.logger.error(f"HTTP Error: {response.status_code} - {response.text}")
                return []

        except Exception as e:
            self.logger.error(f"Failed to fetch positions (Manual Request): {str(e)}")
            return []

    def fetch_balance(self):
        """获取余额"""
        return {}

    def fetch_ticker(self, symbol):
        """获取行情"""
        try:
            return self.public_exchange.fetch_ticker(symbol)
        except Exception as e:
            self.logger.error(f"Failed to fetch ticker: {e}")
            return {}

    @property
    def exchange(self):
        return self.signer
