"""
Trade Parser - 处理交易数据逻辑

负责解析 OKX 的 Trade WebSocket 消息，推送到事件总线。

🔥 [防御性解析] 使用 Pydantic 模型验证数据格式
- 即使 OKX API 增加额外字段，也不会崩溃
- 自动类型转换和范围检查
- 清晰的验证错误信息
"""

import logging
import os
from typing import Optional, Dict, Any
from ....core.event_types import Event, EventType
from ..models import TradeModel

logger = logging.getLogger(__name__)


class TradeParser:
    """
    Trade 数据解析器（Pydantic 版本）

    负责：
    - 解析 Trade 数据（使用 Pydantic 验证）
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

        # 🔥 [修复] 从环境变量读取大单日志阈值
        # 默认值: 500000 USDT (BTC 约 0.56 BTC)
        # 可通过 .env 文件配置: SCALPER_MIN_FLOW
        try:
            self.big_order_threshold = float(os.getenv('SCALPER_MIN_FLOW', '500000'))
            logger.info(f"📊 大单日志阈值已配置: {self.big_order_threshold:,.0f} USDT")
        except (ValueError, TypeError) as e:
            logger.warning(f"配置读取失败，使用默认值 500000 USDT: {e}")
            self.big_order_threshold = 500000.0

    async def process(self, data: dict) -> Optional[Dict[str, Any]]:
        """
        处理 Trade 数据（Pydantic 验证版本）

        Args:
            data (dict): 解析后的 JSON 数据，格式：{"arg": {"channel": "trades", "instId": "BTC-USDT-SWAP"}, "data": [...]}

        Returns:
            Optional[Dict[str, Any]]: 处理后的数据，返回 None 或标准化的交易数据
        """
        try:
            # 提取 trades 数据数组
            trades_data = data.get("data", [])

            # 🔥 [调试] 打印前3条数据，诊断数据格式问题
            if trades_data and len(trades_data) > 0:
                logger.debug(f"接收到 Trade 数据样本: {trades_data[:3]}")

            if not isinstance(trades_data, list) or len(trades_data) == 0:
                logger.debug(f"Trade 数据为空或格式不正确: {trades_data}")
                return None

            # 处理每笔交易
            for trade_item in trades_data[:50]:  # 限制最多处理 50 笔交易（高频场景）
                try:
                    # 🔥 [防御性解析] 尝试使用 Pydantic 验证字典格式
                    if isinstance(trade_item, dict):
                        # 使用 Pydantic 模型验证
                        trade_model = TradeModel(
                            instId=trade_item.get('instId', self.symbol),
                            tradeId=trade_item.get('tradeId', ''),
                            price=float(trade_item.get('px', 0)),
                            size=float(trade_item.get('sz', 0)),
                            side=trade_item.get('side', ''),
                            timestamp=int(trade_item.get('ts', 0))
                        )

                        # 验证通过，提取数据
                        price = trade_model.price
                        size = trade_model.size
                        timestamp = trade_model.timestamp
                        side = trade_model.side

                    # 解析数组格式（旧格式）
                    elif isinstance(trade_item, list) and len(trade_item) >= 4:
                        try:
                            price = float(trade_item[0])  # price
                            size = float(trade_item[1])  # size
                        except (ValueError, TypeError) as e:
                            logger.error(f"数组格式解析错误: {trade_item}, error={e}")
                            continue
                        timestamp = int(trade_item[3])  # ts
                        side = str(trade_item[4])  # side
                    else:
                        logger.debug(f"Trade 数据格式未知: {trade_item}")
                        continue

                    # 🔥 [修复] 验证数据完整性并添加价格合理性检查
                    if price <= 0 or price > 1000000:
                        logger.warning(f"异常价格: {price}, 原始数据: {trade_item}")
                        continue
                    if size <= 0:
                        logger.warning(f"异常数量: {size}, 原始数据: {trade_item}")
                        continue
                    if timestamp == 0:
                        logger.warning(f"无效时间戳: {timestamp}, 原始数据: {trade_item}")
                        continue
                    if side == "":
                        logger.warning(f"空交易方向: 原始数据: {trade_item}")
                        continue

                    # 验证交易方向
                    if side not in ["buy", "sell"]:
                        logger.warning(f"无效的交易方向: {side}")
                        continue

                    # 计算交易金额 (USDT)
                    usdt_value = price * size

                    # 🔥 [修复] 移除大单日志
                    # 大单日志已移到策略中，只在满足所有开仓条件时才打印
                    # 这里只推送 TICK 事件

                    # 推送 TICK 事件到事件总线（用于 Maker 策略的入场检测）
                    if self.event_bus:
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

                except Exception as e:
                    # 🔥 [防御性解析] Pydantic 验证失败时，记录警告但继续处理
                    logger.warning(f"⚠️ [TradeParser] 单笔交易解析失败: {e}, 数据: {trade_item}")
                    continue

            logger.debug(f"已处理 {len(trades_data[:50])} 笔 Trade 数据")

        except Exception as e:
            logger.error(f"处理 Trade 数据异常: {e}", exc_info=True)
            return None
