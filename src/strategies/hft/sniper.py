"""
狙击手策略 (Sniper Strategy)

大单追涨策略：监控微观资金流，在突破阻力位时追涨。

触发条件：
1. 最近 3 秒内交易笔数 >= min_trades（默认 20）
2. 最近 3 秒内净流量（买入-卖出）>= min_net_volume（默认 10000 USDT）
3. PRODUCTION 模式：price > resistance（严格突破）
   DEV 模式：price > resistance * 0.9995（放宽阻力位 0.05%）

动作：下达 IOC 买单（模拟市价单，带滑点）
"""

import logging
import time
from typing import Optional, Dict, Any, List
from ..base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class SniperStrategy(BaseStrategy):
    """
    狙击手策略 (Sniper)

    监控大单资金流，在突破阻力位时追涨。

    Attributes:
        flow_window (float): 流量分析窗口（秒），默认 3.0
        min_trades (int): 最小交易笔数，默认 20
        min_net_volume (float): 最小净流量（USDT），默认 10000.0
        slippage_pct (float): 滑点百分比（默认 0.002 = 0.2%）
        resistance (float): 阻力位

    Example:
        >>> strategy = SniperStrategy(
        ...     symbol="BTC-USDT-SWAP",
        ...     mode="PRODUCTION"
        ... )
        >>> await strategy.on_tick(price=50000.0, timestamp=1234567890000)
    """

    def __init__(
        self,
        symbol: str,
        mode: str = "PRODUCTION",
        flow_window: float = 3.0,
        min_trades: int = 20,
        min_net_volume: float = 10000.0,
        slippage_pct: float = 0.002
    ):
        """
        初始化狙击手策略

        Args:
            symbol (str): 交易对
            mode (str): 策略模式（PRODUCTION/DEV）
            flow_window (float): 流量分析窗口（秒），默认 3.0
            min_trades (int): 最小交易笔数，默认 20
            min_net_volume (float): 最小净流量（USDT），默认 10000.0
            slippage_pct (float): 滑点百分比（默认 0.002 = 0.2%）
        """
        super().__init__(symbol, mode)

        self.flow_window = flow_window
        self.min_trades = min_trades
        self.min_net_volume = min_net_volume
        self.slippage_pct = slippage_pct

        # 根据模式设置价格条件
        if self.mode == "DEV":
            self.price_condition_factor = 0.9995  # 放宽 0.05%
            self.mode_suffix = " [DEV MODE]"
        else:
            self.price_condition_factor = 1.0  # 严格
            self.mode_suffix = ""

        # 阻力位
        self.resistance: float = 0.0
        self._price_history: List[float] = []
        self._resistance_window = 50  # 阻力位窗口大小

        # 统计信息
        self.trigger_count = 0
        self.trade_executions = 0

        # 冷却时间
        self.last_trigger_time = 0.0

        logger.info(
            f"狙击手策略初始化: symbol={symbol}, mode={mode}, "
            f"flow_window={flow_window}, min_trades={min_trades}, "
            f"min_net_volume={min_net_volume}"
        )

    def _update_resistance(self, price: float):
        """
        更新阻力位

        阻力位定义为最近 50 笔交易中的最高价。

        Args:
            price (float): 当前价格
        """
        # 添加价格到历史记录
        self._price_history.append(price)

        # 只保留最近 N 个价格
        if len(self._price_history) > self._resistance_window:
            self._price_history.pop(0)

        # 更新阻力位（最大值）
        self.resistance = max(self._price_history)

        logger.debug(f"更新阻力位: {self.resistance}")

    async def on_tick(self, price: float, size: float = 0.0, side: str = "", timestamp: int = 0):
        """
        处理 Tick 数据

        Args:
            price (float): 当前价格
            size (float): 交易数量
            side (str): 交易方向
            timestamp (int): 时间戳（毫秒）
        """
        if not self.is_enabled():
            return

        # 更新阻力位
        self._update_resistance(price)

        # 检查触发条件
        await self._check_and_execute(price, timestamp)

    async def _check_and_execute(self, price: float, timestamp: int):
        """
        检查并执行交易

        Args:
            price (float): 当前价格
            timestamp (int): 当前时间戳（毫秒）
        """
        # 检查冷却时间
        current_time = time.time()
        if current_time - self.last_trigger_time < 5.0:  # 冷却 5 秒
            logger.debug(f"狙击手策略冷却中，跳过")
            return

        # TODO: 这里需要从市场状态获取流量数据
        # 暂时使用占位符，后续需要从事件总线订阅市场数据
        net_volume = 0.0
        trade_count = 0
        intensity = 0.0

        # 根据策略模式计算价格条件
        price_condition = price > (self.resistance * self.price_condition_factor)

        # 调试日志
        if net_volume >= self.min_net_volume:
            logger.debug(
                f"👀 发现大单! 净量:{net_volume:.0f} | 价格:{price:.2f} vs 阻力:{self.resistance * self.price_condition_factor:.4f} | "
                f"满足价格条件? {price_condition} | 交易笔数:{trade_count}"
            )

        # 检查触发条件
        if (trade_count >= self.min_trades and
            net_volume >= self.min_net_volume and
            price_condition):

            self.trigger_count += 1
            self.last_trigger_time = current_time

            logger.info(
                f"狙击手策略触发{self.mode_suffix}: trade_count={trade_count}, "
                f"net_volume={net_volume:.2f}, intensity={intensity:.2f}, "
                f"price={price}, resistance={self.resistance}, "
                f"trigger_count={self.trigger_count}"
            )

            # 生成买入信号
            signal = {
                'strategy': 'sniper',
                'signal': 'BUY',
                'symbol': self.symbol,
                'price': price,
                'type': 'ioc',  # IOC 订单
                'slippage_pct': self.slippage_pct,
                'timestamp': int(time.time() * 1000)
            }

            await self.on_signal(signal)

    async def on_signal(self, signal: Dict[str, Any]):
        """
        处理策略信号

        Args:
            signal (dict): 策略信号
        """
        if signal.get('signal') == 'BUY':
            self.trade_executions += 1
            logger.info(f"狙击手策略信号: {signal}")
        # 实际的订单执行由 OMS 处理

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取策略统计信息

        Returns:
            dict: 统计数据
        """
        stats = super().get_statistics()
        stats.update({
            'flow_window': self.flow_window,
            'min_trades': self.min_trades,
            'min_net_volume': self.min_net_volume,
            'trigger_count': self.trigger_count,
            'trade_executions': self.trade_executions,
            'resistance': self.resistance
        })
        return stats

    def reset_statistics(self):
        """重置统计信息"""
        old_triggers = self.trigger_count
        old_trades = self.trade_executions

        self.trigger_count = 0
        self.trade_executions = 0
        self.resistance = 0.0
        self._price_history = []

        logger.info(
            f"狙击手策略重置统计: triggers={old_triggers}, trades={old_trades}"
        )
