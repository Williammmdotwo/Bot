"""
OKX REST API 客户端 (源头重写版)

终极方案：通过子类化重写 describe() 方法，
在配置生成的源头直接硬编码正确的 URL，
彻底规避 CCXT 内部任何动态 URL 逻辑错误。
"""

import ccxt
import logging
import os
import json

logger = logging.getLogger(__name__)


class HardcodedOKX(ccxt.okx):
    """
    一个 URL 被焊死的 OKX 类
    """
    def describe(self):
        # 1. 获取父类配置
        config = super().describe()

        # 2. 定义正确的 Base URL (不带 /api)
        base_url = 'https://www.okx.com'

        # 3. 构造全能 URL 字典
        # 无论 CCXT 想访问什么 endpoint，都给它这个 base_url
        universal_urls = {
            'public': base_url,
            'private': base_url,
            'rest': base_url,
            'v5': base_url,
            'spot': base_url,
            'swap': base_url,
            'future': base_url,
            'option': base_url,
            'index': base_url,
            'test': base_url, # 某些旧版逻辑
        }

        # 4. 暴力覆盖 'api' 和 'test' 根节点
        # 这样无论 sandboxMode 是 True 还是 False，它读到的都是这个字典
        config['urls']['api'] = universal_urls
        config['urls']['test'] = universal_urls

        return config


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
                # 关键：我们依然开启 sandboxMode 以启用签名逻辑
                # 但因为我们在 describe() 里劫持了 URL，所以它的副作用（改 URL）无效了
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

        # 3. 初始化私有 Exchange (使用硬编码类)
        try:
            # 🔥 使用 HardcodedOKX
            self.exchange = HardcodedOKX(exchange_config)

            # 手动注入模拟盘 Header (双重保险)
            if self.is_demo:
                if self.exchange.headers is None:
                    self.exchange.headers = {}
                self.exchange.headers['x-simulated-trading'] = '1'

            self.logger.info("Private Exchange initialized (HardcodedOKX Class)")

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
            # 公有通道也用 HardcodedOKX
            self.public_exchange = HardcodedOKX(config_public)
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
            # 🔥 确保 Markets 已加载 (防止 markets not loaded 错误)
            if not self.exchange.markets:
                # self.logger.info("Loading markets...")
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
