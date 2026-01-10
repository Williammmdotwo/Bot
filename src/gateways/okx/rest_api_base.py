"""
OKX REST API 客户端 (Full Bypass & Patch)

1. fetch_positions: 使用 requests 绕过。
2. signer: 初始化时强制打上 URL 补丁，确保 trade_executor 调用 create_order 时能正常工作。
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

        # 1. 基础配置
        # 强制关闭 sandboxMode，防止 CCXT 内部 URL 逻辑干扰
        exchange_config = {
            'apiKey': api_key,
            'secret': secret_key,
            'password': passphrase,
            'options': {
                'defaultType': 'swap',
                'sandboxMode': False
            }
        }

        # 2. 初始化 CCXT Signer
        self.signer = ccxt.okx(exchange_config)

        # 🔥 关键修复：给 signer 打上 URL 补丁
        # 这样 trade_executor 调用 create_market_order 时就不会崩
        base_url = 'https://www.okx.com'
        universal_urls = {
            'public': base_url, 'private': base_url, 'rest': base_url, 'v5': base_url,
            'test': base_url, 'spot': base_url, 'swap': base_url, 'future': base_url
        }
        self.signer.urls['api'] = universal_urls
        self.signer.urls['test'] = universal_urls

        # 注入 Header
        if self.is_demo:
            if self.signer.headers is None:
                self.signer.headers = {}
            self.signer.headers['x-simulated-trading'] = '1'

        self.has_credentials = bool(api_key and secret_key and passphrase)
        self.logger.info(f"RESTClient initialized. Credentials present: {self.has_credentials}")

        # 3. 初始化公有 Exchange
        try:
            config_public = {
                'timeout': 30000,
                'enableRateLimit': True,
                'options': {'defaultType': 'swap'}
            }
            self.public_exchange = ccxt.okx(config_public)
            self.public_exchange.urls['api'] = universal_urls # 同样打补丁
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
        """获取持仓 - Requests Bypass"""
        if not self.has_credentials:
            return []

        try:
            params = {}
            params['instType'] = 'SWAP'
            if symbol: params['instId'] = symbol

            # 签名
            request = self.signer.sign('account/positions', 'private', 'GET', params)
            signed_url = request['url']
            headers = request['headers']

            # 发送
            response = requests.get(signed_url, headers=headers, params=None, timeout=10)

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
            return []

        except Exception as e:
            self.logger.error(f"Failed to fetch positions: {str(e)}")
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
