"""
OKX REST API 客户端（修复版）

提供与 OKX 交易所 REST API 的交互功能
支持模拟盘和实盘模式
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

        # === 自动补全凭证逻辑 ===
        if not api_key:
            api_key = os.getenv('OKX_API_KEY')
            secret_key = os.getenv('OKX_SECRET_KEY')
            passphrase = os.getenv('OKX_PASSPHRASE')

        # 1. 基础配置（私有 exchange，用于需要认证的操作）
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
            self.logger.info("RESTClient: 已加载 API 凭证 (Authenticated Mode)")
        else:
            self.has_credentials = False
            self.logger.warning("RESTClient: 初始化为匿名模式 (无法交易)")

        # 3. 初始化私有 CCXT（用于需要认证的操作）
        try:
            self.exchange = ccxt.okx(exchange_config)

            # 4. 模拟盘特殊处理
            if self.is_demo:
                self.exchange.set_sandbox_mode(True)

                # 终极修复：完全替换整个 URLs 字典，不留任何 None 的死角
                # OKX 模拟盘的 API 地址
                demo_base_url = 'https://www.okx.com/api'

                # 强制替换整个 urls['api'] 字典
                self.exchange.urls['api'] = {
                    'public': demo_base_url,
                    'private': demo_base_url,
                    'rest': demo_base_url,
                    'v5': demo_base_url,
                    # 填充所有可能的 key，防止 NoneType 错误
                    'v5Public': demo_base_url,
                    'v5Private': demo_base_url,
                    'spot': demo_base_url,
                    'spotPublic': demo_base_url,
                    'future': demo_base_url,
                    'swap': demo_base_url,
                    'swapPublic': demo_base_url,
                    'default': demo_base_url,
                    # 确保 key 不是 None
                    None: demo_base_url,
                }

                self.logger.info(f"OKX Sandbox URLs completely replaced: {demo_base_url}")

        except Exception as e:
            self.logger.error(f"CCXT 初始化失败: {e}")
            raise

        # 5. 初始化公有 exchange（用于获取公开数据，如K线）
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
                    'adjustForTimeDifference': True
                }
            }

            # 实例化公有通道
            self.public_exchange = ccxt.okx(config_public)

            # 终极修复：完全替换整个 URLs 字典，强制指向实盘
            real_base_url = 'https://www.okx.com'
            self.public_exchange.urls['api'] = {
                'public': real_base_url,
                'private': real_base_url,
                'rest': real_base_url,
                # 填充所有可能的 key
                'v5': real_base_url,
                'v5Public': real_base_url,
                'v5Private': real_base_url,
                'spot': real_base_url,
                'spotPublic': real_base_url,
                'future': real_base_url,
                'swap': real_base_url,
                'swapPublic': real_base_url,
                'default': real_base_url,
                # 确保 key 不是 None
                None: real_base_url,
            }
            self.logger.info("Public exchange initialized (Real Market Data)")

        except Exception as e:
            self.logger.error(f"Public exchange 初始化失败: {e}")
            raise

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=100):
        """获取K线数据（走 Public 通道）"""
        try:
            limit = int(limit) if limit else 100
            if since:
                since = int(since)

            # 使用公有通道获取实盘数据
            exchange_to_use = self.public_exchange if hasattr(self, 'public_exchange') else self.exchange
            candles = exchange_to_use.fetch_ohlcv(
                symbol=symbol, timeframe=timeframe, since=since, limit=limit
            )
            return candles if isinstance(candles, list) else []
        except Exception as e:
            self.logger.exception(f"Failed to fetch OHLCV for {symbol}: {e}")
            return []

    def fetch_positions(self, symbol=None):
        """获取持仓（走 Private 通道）"""
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
