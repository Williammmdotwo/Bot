"""
Trade Parser - 处理交易数据逻辑

负责解析 OKX 的 Trade WebSocket 消息，推送到事件总线。
"""

import logging
from typing import Optional, Dict, Any
from ....core.event_types import Event, EventType

logger = logging.getLogger(__name__)


class TradeParser:
    """
    Trade 数据解析器

    负责：
    - 解析 Trade 数据
    - 计算 USDT 价值
    - 推送 TICK 事件到事件总线
    """

    def __init__(self, symbol: str, event_bus):
        """
        初始化 Trade Parser

        Args:
            symbol (str): 交易对
            event_bus: 事件总线实例
        """
        self.symbol = symbol
        self.event_bus = event_bus

    async def process(self, data: dict) -> Optional[Dict[str, Any]]:
        """
        处理 Trade 数据

        Args:
            data (dict): 解析后的 JSON 数据，格式：{"arg": {"channel": "trades", "instId": "BTC-USDT-SWAP"}, "data": [...]}

        Returns:
            Optional[Dict[str, Any]]: 处理后的数据，返回 None 或标准化的交易数据
        """
        try:
            # 提取 trades 数据数组
            trades_data = data.get("data", [])

            if not isinstance(trades_data, list) or len(trades_data) == 0:
                logger.debug(f"Trade 数据为空或格式不正确: {trades_data}")
                return None

            # 处理每笔交易
            for trade_item in trades_data[:50]:  # 限制最多处理 50 笔交易（高频场景）
                price = None
                size = None
                timestamp = None
                side = None

                # 解析字典格式（新格式）
                if isinstance(trade_item, dict):
                    price = float(trade_item.get("px", "0"))
                    size = float(trade_item.get("sz", "0"))
                    timestamp = int(trade_item.get("ts", "0"))
                    side = trade_item.get("side", "")

                # 解析数组格式（旧格式）
                elif isinstance(trade_item, list) and len(trade_item) >= 4:
                    price = float(trade_item[0])  # price
                    size = float(trade_item[1])  # size
                    timestamp = int(trade_item[3])  # ts
                    side = str(trade_item[4])  # side
                else:
                    logger.debug(f"Trade 数据格式未知: {trade_item}")
                    continue

                # 验证数据完整性
                if price <= 0 or size <= 0 or timestamp == 0 or side == "":
                    logger.warning(f"Trade 数据不完整: price={price}, size={size}, ts={timestamp}, side={side}")
                    continue

                # 验证交易方向
                if side not in ["buy", "sell"]:
                    logger.warning(f"无效的交易方向: {side}")
                    continue

                # 计算交易金额 (USDT)
                usdt_value = price * size

                # 高频数据流不记录详细日志，仅保留错误日志
                if usdt_value >= 10000.0:
                    logger.info(
                        f"🐋 [大单] {self.symbol}: {side} {size:.4f} @ {price:.4f} = {usdt_value:.2f} USDT"
                    )

                # 推送 TICK 事件到事件总线（用于 Maker 策略的入场检测）
                if self.event_bus:
                    from ....core.event_types import Event, EventType

                    event = Event(
                        type=EventType.TICK,
                        data={
                            'symbol': self.symbol,
                            'price': price,
                            'size': size,
                            'side': side,
                            'timestamp': timestamp,
                            'usdt_value': usdt_value
                        },
                        source="trade_parser"
                    )
                    self.event_bus.put_nowait(event)

            logger.debug(f"已处理 {len(trades_data[:50])} 笔 Trade 数据")

        except Exception as e:
            logger.error(f"处理 Trade 数据异常: {e}", exc_info=True)
            return None
