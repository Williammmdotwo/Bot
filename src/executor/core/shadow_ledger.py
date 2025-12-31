"""
影子账本 (Shadow Ledger)

负责跟踪策略的"期望持仓"与交易所"实际持仓"之间的差异，
并计算需要进行的修正操作 (Resync)。
"""

import time
import logging
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)


class ShadowLedger:
    def __init__(self, sync_threshold_pct: float = 0.10, cooldown_seconds: int = 60):
        """
        初始化影子账本

        Args:
            sync_threshold_pct: 触发同步的差异阈值 (默认 10%)
            cooldown_seconds: 同步操作的冷却时间 (秒)，防止连续重复下单
        """
        # 存储策略期望的持仓: {symbol: {"side": "buy", "size": 1.5, "timestamp": 1234567890}}
        self.target_positions: Dict[str, Dict] = {}
        self.last_sync_time: Dict[str, float] = {}
        self.threshold = sync_threshold_pct
        self.cooldown = cooldown_seconds

    def update_target_position(self, symbol: str, side: str, size: float):
        """
        更新策略期望的持仓 (当策略产生信号时调用)
        """
        self.target_positions[symbol] = {
            "side": side.lower(),
            "size": float(size),
            "timestamp": time.time()
        }
        logger.debug(f"ShadowLedger updated target for {symbol}: {side} {size}")

    def get_target_position(self, symbol: str) -> Optional[Dict]:
        return self.target_positions.get(symbol)

    def check_and_calculate_delta(self, symbol: str, api_positions: List[Dict]) -> Tuple[bool, Dict]:
        """
        检查并计算差额

        Returns:
            needs_sync (bool): 是否需要同步
            action_plan (Dict): 同步计划 (包含需要补单的方向和数量)
        """
        target = self.target_positions.get(symbol)

        # 1. 如果策略没有设定目标，或者目标是空仓(size=0)，暂不处理 (简化逻辑，视为空仓)
        if not target or target['size'] <= 0:
            return False, {}

        # 2. 冷却时间检查
        last_sync = self.last_sync_time.get(symbol, 0)
        if time.time() - last_sync < self.cooldown:
            return False, {"reason": "In cooldown"}

        # 3. 计算 API 实际持仓 (将多空转换为有符号数值)
        # Long = 正数, Short = 负数
        actual_signed_size = 0.0

        for pos in api_positions:
            if pos.get('symbol') == symbol:
                size = float(pos.get('position_size', pos.get('size', 0)))  # 兼容不同字段名
                side = pos.get('side', '').lower()
                # OKX API: pos 模式下，long position 是正数，short position 是正数但 side='short'
                # net 模式下，pos 可能直接带符号
                if side == 'short':
                    actual_signed_size -= abs(size)
                else:
                    actual_signed_size += abs(size)

        # 4. 计算策略目标持仓 (有符号数值)
        target_signed_size = target['size'] if target['side'] == 'buy' else -target['size']

        # 5. 计算差额 (Delta)
        # Delta = 目标 - 实际
        # 例如：目标 +2.0 (Long), 实际 +0.5 (Long) -> Delta = +1.5 (需要买入 1.5)
        # 例如：目标 +2.0 (Long), 实际 0.0 (Empty) -> Delta = +2.0 (需要买入 2.0)
        # 例如：目标 +2.0 (Long), 实际 +2.5 (Over) -> Delta = -0.5 (需要卖出 0.5)
        delta = target_signed_size - actual_signed_size

        # 计算偏差百分比 (基于目标仓位)
        if abs(target_signed_size) > 0:
            diff_pct = abs(delta) / abs(target_signed_size)
        else:
            diff_pct = 0.0 if abs(actual_signed_size) == 0 else 1.0

        # 6. 判断是否触发阈值
        if diff_pct > self.threshold:
            action_side = 'buy' if delta > 0 else 'sell'
            action_amount = abs(delta)

            return True, {
                "symbol": symbol,
                "type": "RESYNC",
                "side": action_side,
                "amount": action_amount,
                "reason": f"Mismatch: Target {target_signed_size:.2f} vs Actual {actual_signed_size:.2f} (Diff: {diff_pct*100:.1f}%)"
            }

        return False, {}

    def mark_synced(self, symbol: str):
        """标记已完成同步，重置冷却时间"""
        self.last_sync_time[symbol] = time.time()
        logger.debug(f"ShadowLedger marked {symbol} as synced")
