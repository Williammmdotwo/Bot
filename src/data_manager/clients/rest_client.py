"""
OKX REST API 客户端 (实例热补丁版)

修复逻辑：
1. 继承 ccxt.okx
2. 在 __init__ 执行完毕后，立即暴力覆盖实例的 self.urls 属性
3. 保持 sandboxMode=True 以确保签名逻辑正确
"""

import ccxt
import logging
import os
import json

logger = logging.getLogger(__name__)


class InvincibleOKX(ccxt.okx):
    """
    一个在初始化后强制重写 URL 的 OKX 类
    """
    def __init__(self, config={}):
        # 1. 正常初始化父类
        super().__init__(config)

        # 2. 🔥 初始化完成后，直接修改实例内存中的属性
        # 这会覆盖掉父类初始化过程中做出的任何错误决定
        base_url = 'https://www.okx.com'

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
            'test': base_url,
        }

        # 强制覆盖 api 和 test，不留死角
        self.urls['api'] = universal_urls
        self.urls['test'] = universal_urls

        # 确保 headers 存在
        if self.headers is None:
            self.headers = {}

        # 如果开启了沙箱，确保 header 存在 (虽然 ccxt 应该会自动加)
        if self.safe_value(self.options, 'sandboxMode', False):
            self.headers['x-simulated-trading'] = '1'


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
                'sandboxMode': use_demo  # ✅ 必须开启，为了正确的签名逻辑
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
            # 🔥 使用 InvincibleOKX
            self.exchange = InvincibleOKX(exchange_config)

            # 记录一下最终的 URL 配置，以供调试
            # self.logger.info(f"Final URL Config: {json.dumps(self.exchange.urls)}")
            self.logger.info("Private Exchange initialized (InvincibleOKX Class)")

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
                    'sandboxMode': False, # 公有数据强制实盘
                }
            }
            # 公有通道也用 InvincibleOKX，稳一点
            self.public_exchange = InvincibleOKX(config_public)
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
            # 🔥 确保 Markets 已加载
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
