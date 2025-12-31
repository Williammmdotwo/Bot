"""
OKX REST API 客户端 (完结版)

1. PatchedOKX: 强制修复 URL。
2. RESTClient: 增加了 load_markets 检查，修复 "markets not loaded" 错误。
"""

import ccxt
import logging
import os
import json

logger = logging.getLogger(__name__)


class PatchedOKX(ccxt.okx):
    """
    打补丁的 OKX 类，强制修复 URL 问题
    """
    def describe(self):
        config = super().describe()
        # 强制写死 URL，不留任何动态拼接的空间
        config['urls']['api'] = {
            'public': 'https://www.okx.com',
            'private': 'https://www.okx.com',
            'rest': 'https://www.okx.com',
        }
        config['urls']['test'] = config['urls']['api']
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
                'sandboxMode': False
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
            self.exchange = PatchedOKX(exchange_config)

            if self.is_demo:
                self.logger.info("Enabling Demo Mode via Header Injection")
                if self.exchange.headers is None:
                    self.exchange.headers = {}
                self.exchange.headers['x-simulated-trading'] = '1'

            self.logger.info("Private Exchange initialized (PatchedOKX Class)")

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
            self.public_exchange = PatchedOKX(config_public)
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
        """获取持仓 - 直接调用 OKX V5 私有接口"""
        if not self.has_credentials:
            return []
        try:
            params = {}
            if symbol:
                # 🔥 修复核心：确保市场数据已加载
                if not self.exchange.markets:
                    # self.logger.info("Loading markets info for the first time...")
                    self.exchange.load_markets()

                market = self.exchange.market(symbol)
                params['instId'] = market['id']
                if market['type'] == 'swap':
                    params['instType'] = 'SWAP'

            # 直接调用底层
            response = self.exchange.private_get_account_positions(params)

            if response and 'data' in response:
                raw_positions = response['data']
                parsed_positions = []
                for raw in raw_positions:
                    pos = {
                        'symbol': symbol if symbol else raw.get('instId'),
                        'size': float(raw.get('pos', 0)),
                        'side': raw.get('posSide', 'net'),
                        'raw': raw
                    }
                    parsed_positions.append(pos)

                return parsed_positions

            return []

        except Exception as e:
            self.logger.error(f"Failed to fetch positions (Direct API): {str(e)}")
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
