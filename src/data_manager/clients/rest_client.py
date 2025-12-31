"""
OKX REST API 客户端 (全面覆盖版)

针对 CCXT Sandbox 模式下 URL 解析异常的终极修复：
1. 启用 sandboxMode
2. 强制覆盖所有可能的 URL 键值 (防止 NoneType)
3. 显式注入模拟盘 Header (双重保险)
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
                'sandboxMode': use_demo
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

            # 🔥 模拟盘 URL 与 Header 强力补丁
            if self.is_demo:
                self.exchange.set_sandbox_mode(True)

                # OKX V5 模拟盘正确的基础 URL (不带 /api，CCXT 会自动拼)
                base_url = 'https://www.okx.com'

                # 显式注入模拟盘 Header (防止 CCXT 漏发)
                if self.exchange.headers is None:
                    self.exchange.headers = {}
                self.exchange.headers['x-simulated-trading'] = '1'

                # 地毯式覆盖所有 URL Keys
                # 防止 fetch_positions 访问特定 key (如 'swap') 时遇到 None
                patched_urls = {
                    'public': base_url,
                    'private': base_url,
                    'rest': base_url,
                    'v5': base_url,
                    'spot': base_url,
                    'swap': base_url,
                    'future': base_url,
                    'option': base_url,
                    'index': base_url,
                }

                # 应用补丁
                self.exchange.urls['api'] = patched_urls

                self.logger.info(f"OKX Sandbox URLs Patched: {base_url}")
                self.logger.debug(f"Applied URL Config: {json.dumps(self.exchange.urls['api'])}")

        except Exception as e:
            self.logger.error(f"CCXT 初始化失败: {e}")
            raise

        # 5. 初始化公有 Exchange (只读，强制实盘)
        try:
            config_public = {
                'apiKey': '',
                'secret': '',
                'password': '',
                'timeout': 30000,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                    'sandboxMode': False,  # 🔥 强制实盘
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

            # 使用 Public Exchange
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
            # 兼容性处理：OKX 模拟盘在 load_markets 时可能会因为 instrument 类型报错
            # 我们先尝试直接获取
            if symbol:
                positions = self.exchange.fetch_positions(symbol)
            else:
                positions = self.exchange.fetch_positions()
            return positions if isinstance(positions, list) else []
        except Exception as e:
            # 详细记录错误堆栈，方便调试
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
