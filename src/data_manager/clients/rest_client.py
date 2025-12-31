"""
OKX REST API 客户端

提供与 OKX 交易所 REST API 的交互功能
支持模拟盘和实盘模式
"""

import ccxt
import logging
import json

logger = logging.getLogger(__name__)


class RESTClient:
    """OKX REST API 客户端"""

    def __init__(self, api_key=None, secret_key=None, passphrase=None, use_demo=False):
        self.logger = logging.getLogger(__name__)
        self.is_demo = use_demo
        self.has_credentials = False

        # 1. 基础配置
        exchange_config = {
            'timeout': 30000,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
                'adjustForTimeDifference': True,
                'sandboxMode': use_demo  # 在配置里直接传
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
            self.logger.info("RESTClient: 初始化为公共(匿名)模式")

        # 3. 初始化 CCXT
        try:
            self.exchange = ccxt.okx(exchange_config)

            # 4. 关键修复：显式开启 Sandbox
            if self.is_demo:
                self.exchange.set_sandbox_mode(True)

                # === 核心补丁：防止 NoneType + str 错误 ===
                # CCXT 在匿名 Sandbox 模式下有时会丢失 URL 配置，这里手动强制修复
                # 确保 api 字典里的所有关键 endpoint 都有值
                if not isinstance(self.exchange.urls['api'], dict):
                    self.exchange.urls['api'] = {
                        'public': 'https://www.okx.com/api',
                        'private': 'https://www.okx.com/api',
                        'rest': 'https://www.okx.com/api',
                    }
                else:
                    # 只要发现是 None，就填上默认值
                    base_url = 'https://www.okx.com/api'
                    for key in ['public', 'private', 'rest']:
                        if self.exchange.urls['api'].get(key) is None:
                            self.exchange.urls['api'][key] = base_url

                self.logger.info("OKX Exchange initialized in Sandbox mode (URLs patched)")

        except Exception as e:
            self.logger.error(f"CCXT 初始化失败: {e}")
            raise

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=100):
        """获取K线数据"""
        try:
            limit = int(limit) if limit else 100
            if since:
                since = int(since)

            # 使用关键字参数，确保安全
            if since:
                candles = self.exchange.fetch_ohlcv(symbol=symbol, timeframe=timeframe, since=since, limit=limit)
            else:
                candles = self.exchange.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)

            return candles if isinstance(candles, list) else []
        except Exception as e:
            self.logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
            return []

    def fetch_positions(self, symbol=None):
        """获取持仓"""
        if not self.has_credentials:
            return []
        try:
            if self.is_demo and not symbol:
                self.logger.warning("Demo mode requires symbol for fetch_positions")
                return []
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
        if not self.has_credentials:
            return {}
        try:
            return self.exchange.fetch_balance()
        except Exception as e:
            self.logger.error(f"Failed to fetch balance: {e}")
            return {}

    def fetch_ticker(self, symbol):
        """获取行情"""
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            self.logger.error(f"Failed to fetch ticker for {symbol}: {e}")
            return {}
