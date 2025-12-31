"""
OKX REST API 客户端 (重写底层版)

针对 CCXT URL 路由逻辑异常的终极方案：
直接子类化 ccxt.okx 并重写 fetch_positions，
强制调用底层 API，绕过所有 URL 拼接逻辑。
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
        # 继承原有配置
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
                # 关键：即便使用了 Patched 类，也要关闭 sandboxMode，
                # 因为我们要完全接管 URL 控制权，不让 CCXT 内部逻辑干扰
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

        # 3. 初始化私有 Exchange (使用我们自定义的类)
        try:
            # 🔥 使用 PatchedOKX 而不是 ccxt.okx
            self.exchange = PatchedOKX(exchange_config)

            # 手动注入模拟盘逻辑
            if self.is_demo:
                self.logger.info("Enabling Demo Mode via Header Injection")
                if self.exchange.headers is None:
                    self.exchange.headers = {}
                self.exchange.headers['x-simulated-trading'] = '1'

            self.logger.info("Private Exchange initialized (PatchedOKX Class)")

        except Exception as e:
            self.logger.error(f"CCXT 初始化失败: {e}")
            raise

        # 5. 初始化公有 Exchange (只读)
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
            # 公有通道也用 PatchedOKX，保持一致性
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
            # 🔥 绕过 CCXT 标准 fetch_positions，直接调用底层隐式方法
            # OKX V5 获取持仓的 endpoint 是 /api/v5/account/positions
            # CCXT 自动映射为 private_get_account_positions

            params = {}
            if symbol:
                market = self.exchange.market(symbol)
                params['instId'] = market['id']
                # 某些情况下可能需要 instType
                if market['type'] == 'swap':
                    params['instType'] = 'SWAP'

            # 直接调用底层，它会使用我们在 describe() 里硬编码的 URL
            response = self.exchange.private_get_account_positions(params)

            # 手动解析响应 (因为绕过了 CCXT 的解析层)
            # OKX V5 响应格式: {'code': '0', 'data': [...], ...}
            if response and 'data' in response:
                raw_positions = response['data']
                # 为了兼容性，我们需要把它转换成 CCXT 标准格式吗？
                # ShadowLedger 需要: position_size (or size), side
                # OKX V5 data 包含: pos (持仓数量), posSide (方向 long/short/net)

                parsed_positions = []
                for raw in raw_positions:
                    # 简单转换以适配 ShadowLedger
                    pos = {
                        'symbol': symbol if symbol else raw.get('instId'),
                        'size': float(raw.get('pos', 0)),
                        'side': raw.get('posSide', 'net'),
                        # 其他字段按需添加
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
