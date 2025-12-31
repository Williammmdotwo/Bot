"""
OKX REST API 客户端 (标准修复版)

回归标准的 sandboxMode=True 模式，
但修正了 URL 补丁中导致 404 的路径重复问题。
"""

import ccxt
import logging
import os

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
                'sandboxMode': use_demo  # ✅ 回归标准沙箱模式
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

            # 4. 🔥 模拟盘 URL 补丁 (Fix for NoneType & 404)
            if self.is_demo:
                self.exchange.set_sandbox_mode(True)

                # 关键修正：这里不能带 /api，因为 CCXT 会自动拼
                # 正确：https://www.okx.com
                # 错误：https://www.okx.com/api
                demo_url = 'https://www.okx.com'

                # 强制覆盖所有可能的 URL 键值
                self.exchange.urls['api'] = {
                    'public': demo_url,
                    'private': demo_url,
                    'rest': demo_url,
                    'v5': demo_url,
                }

                self.logger.info(f"OKX Sandbox URLs patched: {demo_url}")

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
            if symbol:
                positions = self.exchange.fetch_positions(symbol)
            else:
                positions = self.exchange.fetch_positions()
            return positions if isinstance(positions, list) else []
        except Exception as e:
            self.logger.error(f"Failed to fetch positions: {e}")
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
