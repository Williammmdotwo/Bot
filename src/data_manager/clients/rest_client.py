"""
OKX REST API 客户端 (终极修复版)

采用"伪装实盘"策略：
关闭 CCXT 的 sandboxMode 以防止 URL 错误，
通过手动注入 Header 或配置来连接模拟盘。
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
        # 核心改动：sandboxMode 永远设为 False，防止 CCXT 破坏 URL
        exchange_config = {
            'timeout': 30000,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
                'adjustForTimeDifference': True,
                'sandboxMode': False,  # 🚫 禁用 CCXT 沙箱逻辑
            }
        }

        # 2. 模拟盘特殊处理 (手动模式)
        if self.is_demo:
            self.logger.info("RESTClient: 启用模拟盘模式 (通过 Header 注入)")
            # OKX V5 标准：在实盘 URL 上添加此 Header 即为模拟盘
            if 'headers' not in exchange_config:
                exchange_config['headers'] = {}
            exchange_config['headers']['x-simulated-trading'] = '1'

        # 3. 凭证配置
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

        # 4. 初始化私有 Exchange
        try:
            self.exchange = ccxt.okx(exchange_config)

            # 双重保险：强制设置 URL 为实盘地址 (虽然 sandboxMode=False 应该已经保证了这点)
            # 这能解决某些网络环境下 DNS 解析问题，或 CCXT 版本过旧的问题
            base_url = 'https://www.okx.com'
            self.exchange.urls['api'] = {
                'public': base_url,
                'private': base_url,
                'rest': base_url,
                'v5': base_url,
            }

            if self.is_demo:
                self.logger.info("Private Exchange initialized (Demo Mode via Header)")
            else:
                self.logger.info("Private Exchange initialized (Real Trading Mode)")

        except Exception as e:
            self.logger.error(f"CCXT 初始化失败: {e}")
            raise

        # 5. 初始化公有 Exchange (用于获取 K 线)
        try:
            public_config = {
                'apiKey': '',
                'secret': '',
                'password': '',
                'timeout': 30000,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                    'sandboxMode': False, # 必须 False
                }
            }
            self.public_exchange = ccxt.okx(public_config)

            # 同样强制 URL
            self.public_exchange.urls['api'] = {
                'public': base_url,
                'private': base_url,
                'rest': base_url,
                'v5': base_url,
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
            # 使用带 Header 的私有 Exchange
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
