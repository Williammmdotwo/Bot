"""
OKX REST API 客户端 (官方沙箱修复版)

回归 CCXT 官方 sandboxMode=True，
但通过暴力递归替换 urls 字典，修复所有潜在的 NoneType 和 URL 错误。
"""

import ccxt
import logging
import os
import json

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
        exchange_config = {
            'timeout': 30000,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
                'adjustForTimeDifference': True,
                'sandboxMode': use_demo  # ✅ 回归官方沙箱模式
            }
        }

        # 2. 凭证配置
        if api_key and secret_key and passphrase:
            exchange_config.update({
                'apiKey': api_key,
                'secret': secret_key,
                'password': passphrase
            })
            self.has_credentials = True
        else:
            self.has_credentials = False
            self.logger.warning("RESTClient: 初始化为匿名模式")

        # 3. 初始化私有 Exchange
        try:
            self.exchange = ccxt.okx(exchange_config)

            # 🔥 暴力修复 URL (Recursive Fix)
            if self.is_demo:
                self.exchange.set_sandbox_mode(True)

                # 定义正确的基础 URL
                correct_url = 'https://www.okx.com'

                # 递归函数：把字典里所有字符串值替换为 correct_url
                def recursive_url_fix(d):
                    for k, v in d.items():
                        if isinstance(v, dict):
                            recursive_url_fix(v)
                        elif isinstance(v, str):
                            # 只要是 URL，统统替换，不管它是 api 还是 test
                            d[k] = correct_url

                # 对 api 和 test 字典进行暴力清洗
                if 'api' in self.exchange.urls:
                    recursive_url_fix(self.exchange.urls['api'])

                if 'test' in self.exchange.urls:
                    recursive_url_fix(self.exchange.urls['test'])

                # 额外保险：确保 test 字典存在
                if 'test' not in self.exchange.urls:
                    self.exchange.urls['test'] = self.exchange.urls['api']

                self.logger.info(f"OKX Sandbox URLs recursively patched to: {correct_url}")

        except Exception as e:
            self.logger.error(f"CCXT 初始化失败: {e}")
            raise

        # 5. 初始化公有 Exchange
        try:
            config_public = {
                'apiKey': '',
                'secret': '',
                'password': '',
                'timeout': 30000,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                    'sandboxMode': False,
                }
            }
            self.public_exchange = ccxt.okx(config_public)

            # 强制指向实盘 URL
            real_url = 'https://www.okx.com'
            self.public_exchange.urls['api'] = {
                'public': real_url,
                'private': real_url,
                'rest': real_url,
                'v5': real_url,
            }
            self.logger.info("Public Exchange initialized (Market Data)")

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
        """获取持仓"""
        if not self.has_credentials:
            return []
        try:
            # 确保 Markets 已加载
            if not self.exchange.markets:
                self.exchange.load_markets()

            if symbol:
                positions = self.exchange.fetch_positions(symbol)
            else:
                positions = self.exchange.fetch_positions()
            return positions if isinstance(positions, list) else []
        except Exception as e:
            self.logger.error(f"Failed to fetch positions: {str(e)}")
            return []

    def fetch_balance(self):
        """获取余额"""
        if not self.has_credentials: return {}
        try:
            return self.exchange.fetch_balance()
        except Exception as e:
            self.logger.error(f"Failed to fetch balance: {e}")
            return {}

    def fetch_ticker(self, symbol):
        """获取行情"""
        try:
            return self.public_exchange.fetch_ticker(symbol)
        except Exception as e:
            self.logger.error(f"Failed to fetch ticker: {e}")
            return {}
