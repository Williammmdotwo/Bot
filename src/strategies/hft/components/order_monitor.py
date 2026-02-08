"""
订单监控模块

负责监控挂单状态：
- 追单逻辑（Chasing）
- 深度感知撤单（Depth Protection）
- 挂单状态维护
"""

import time
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class OrderMonitor:
    """
    订单监控器

    职责：
    1. 检查是否需要追单（挂单价格落后）
    2. 检查深度感知撤单条件
    3. 提供统一的订单监控接口
    """

    def __init__(self, execution_algo, config: Dict[str, Any]):
        """
        初始化订单监控器

        Args:
            execution_algo: 执行算法实例
            config: 配置字典，包含：
                - enable_depth_protection: 是否启用深度保护
                - anti_flipping_threshold: 反转阈值（倍数）
                - tick_size: 最小价格变动单位
        """
        self.execution_algo = execution_algo
        self.config = config
        self._last_ask_snapshot: Dict[str, Dict[str, Any]] = {}

    def check_chase_conditions(
        self,
        order_id: str,
        maker_order_price: float,
        current_price: float,
        order_age: float
    ) -> bool:
        """
        检查是否需要追单

        策略：
        1. 挂单价格落后于当前价格超过阈值
        2. 挂单存活时间超过最小存活时间

        Args:
            order_id (str): 订单ID
            maker_order_price (float): 挂单价格
            current_price (float): 当前最优价格
            order_age (float): 订单存活时间（秒）

        Returns:
            bool: 是否需要追单
        """
        if not self.execution_algo:
            logger.warning("⚠️ [订单监控] execution_algo 未初始化")
            return False

        # 检查是否应该追单
        should_chase = self.execution_algo.should_chase(
            current_maker_price=maker_order_price,
            current_price=current_price,
            order_age=order_age
        )

        if should_chase:
            logger.info(
                f"🔥 [订单监控-追单] order_id={order_id}: "
                f"挂单价={maker_order_price:.6f}, "
                f"当前价={current_price:.6f}, "
                f"存活时间={order_age:.1f}s"
            )

        return should_chase

    def check_depth_protection(
        self,
        order_id: str,
        maker_order_price: float,
        order_book: Dict[str, list],
        order_size: float
    ) -> Tuple[bool, str]:
        """
        检查深度感知撤单条件

        策略：
        1. 压单保护：前方突然出现巨大的挂单量
        2. 删单保护：前方档位在短时间内发生剧烈删单

        Args:
            order_id (str): 订单ID
            maker_order_price (float): 挂单价格
            order_book (dict): 订单簿深度数据 {'bids': [...], 'asks': [...]}
            order_size (float): 订单数量

        Returns:
            tuple: (should_cancel, reason)
                - should_cancel: 是否应该撤单
                - reason: 撤单原因
        """
        if not self.config.get('enable_depth_protection', False):
            return (False, "")

        tick_size = self.config.get('tick_size', 0.01)
        anti_flipping_threshold = self.config.get('anti_flipping_threshold', 10.0)

        # 检查订单簿数据
        if not order_book or 'bids' not in order_book or len(order_book['bids']) == 0:
            return (False, "")

        # 查找我们订单所在的档位
        our_price_level = None
        volume_ahead = 0.0

        for i, bid in enumerate(order_book['bids']):
            bid_price = bid[0]
            bid_size = bid[1]

            # 价格匹配（考虑tick_size精度）
            if abs(bid_price - maker_order_price) < tick_size:
                our_price_level = i
                break
            # 在我们订单之前的档位
            elif bid_price > maker_order_price:
                volume_ahead += bid_size

        # 如果没找到我们的档位，返回 False
        if our_price_level is None:
            return (False, "")

        # 获取我们档位的订单量
        our_bid = order_book['bids'][our_price_level]
        our_size = our_bid[1]

        # 获取上次快照用于检测删单
        last_snapshot = self._last_ask_snapshot.get(order_id, {})
        last_volume_ahead = last_snapshot.get('volume_ahead', 0.0)

        # 策略1：压单保护
        # 前方突然出现巨大的挂单量 > 我们订单的 anti_flipping_threshold 倍
        if volume_ahead > order_size * anti_flipping_threshold:
            reason = (
                f"压单量={volume_ahead:.0f} (我们的={order_size:.0f}), "
                f"超过{anti_flipping_threshold}倍阈值"
            )
            logger.warning(
                f"🚨 [订单监控-压单] order_id={order_id}: {reason}, 立即撤单"
            )
            return (True, reason)

        # 策略2：删单保护
        # 前方档位在短时间内发生剧烈删单
        if len(last_snapshot) > 0:
            volume_change = abs(volume_ahead - last_volume_ahead)
            time_since_snapshot = time.time() - last_snapshot.get('timestamp', 0)

            # 如果删单量超过我们订单的 anti_flipping_threshold 倍，且时间 < 100ms
            if (volume_change > order_size * anti_flipping_threshold and
                time_since_snapshot < 0.1):
                reason = (
                    f"删单量={volume_change:.0f} (我们的={order_size:.0f}), "
                    f"超过{anti_flipping_threshold}倍阈值, "
                    f"时间={time_since_snapshot*1000:.0f}ms"
                )
                logger.warning(
                    f"🚨 [订单监控-删单] order_id={order_id}: {reason}, 立即撤单"
                )
                return (True, reason)

        # 保存快照
        self._last_ask_snapshot[order_id] = {
            'volume_ahead': volume_ahead,
            'timestamp': time.time()
        }

        return (False, "")

    def clear_order_snapshot(self, order_id: str):
        """
        清除订单的快照数据（订单成交或撤单后调用）

        Args:
            order_id (str): 订单ID
        """
        if order_id in self._last_ask_snapshot:
            del self._last_ask_snapshot[order_id]
            logger.debug(f"🗑️ [订单监控] 已清除订单 {order_id} 的快照数据")

    def clear_all_snapshots(self):
        """清除所有快照数据"""
        self._last_ask_snapshot.clear()
        logger.debug("🗑️ [订单监控] 已清除所有快照数据")

    def monitor_order(
        self,
        order_id: str,
        maker_order_price: float,
        current_price: float,
        order_age: float,
        order_book: Dict[str, list],
        order_size: float
    ) -> Tuple[bool, Optional[str]]:
        """
        统一的订单监控接口

        检查：
        1. 是否需要追单
        2. 是否需要深度感知撤单

        Args:
            order_id (str): 订单ID
            maker_order_price (float): 挂单价格
            current_price (float): 当前价格
            order_age (float): 订单存活时间（秒）
            order_book (dict): 订单簿深度数据
            order_size (float): 订单数量

        Returns:
            tuple: (should_cancel, reason)
                - should_cancel: 是否应该撤单
                - reason: 撤单原因（None 表示不撤单）
        """
        # 1. 检查追单条件
        should_chase = self.check_chase_conditions(
            order_id=order_id,
            maker_order_price=maker_order_price,
            current_price=current_price,
            order_age=order_age
        )

        if should_chase:
            return (True, "追单")

        # 2. 检查深度感知撤单条件
        should_cancel, reason = self.check_depth_protection(
            order_id=order_id,
            maker_order_price=maker_order_price,
            order_book=order_book,
            order_size=order_size
        )

        if should_cancel:
            return (True, reason)

        return (False, None)
