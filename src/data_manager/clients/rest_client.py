"""
OKX REST API 客户端

提供与 OKX 交易所 REST API 的交互功能
支持模拟盘和实盘模式
"""

import ccxt
import logging
import json
import os  # 引入 os 模块读取环境变量

logger = logging.getLogger(__name__)


class RESTClient:
    """OKX REST API 客户端"""

    def __init__(self, api_key=None, secret_key=None, passphrase=None, use_demo=False):
        self.logger = logging.getLogger(__name__)
        self.is_demo = use_demo

        # === 自动补全凭证逻辑 ===
        # 如果外部没传 Key，尝试从环境变量读取
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
                'sandboxMode': use_demo  # 在配置阶段就开启 sandbox
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
            self.logger.info("RESTClient: 已加载 API 凭证 (Authenticated Mode)")
        else:
            self.has_credentials = False
            self.logger.warning("RESTClient: 未找到 API 凭证，初始化为匿名模式 (注意：OKX 模拟盘在匿名模式下可能会报错)")

        # 3. 初始化 CCXT
        try:
            self.exchange = ccxt.okx(exchange_config)

            # 4. 模拟盘特殊处理
            if self.is_demo:
                self.exchange.set_sandbox_mode(True)

                # === 强力补丁：手动修复 URL ===
                # 即使是匿名模式，也强行填入 URL，防止 NoneType 错误
                # OKX 模拟盘的 API 地址通常和实盘一样，只是 Header 不同，或者使用 aws 地址
                # 这里我们确保它不是 None
                if not self.exchange.urls.get('api'):
                    self.exchange.urls['api'] = {}

                base_url = 'https://www.okx.com/api'
                # 针对不同版本的 ccxt 结构进行防御性赋值
                if isinstance(self.exchange.urls['api'], dict):
                    for key in ['public', 'private', 'rest', 'v5']:
                        if not self.exchange.urls['api'].get(key):
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

            # 使用关键字参数调用
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
            # 模拟盘必须传 symbol
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
