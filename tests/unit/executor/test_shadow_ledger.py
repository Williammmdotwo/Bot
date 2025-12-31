"""
Shadow Ledger 单元测试
"""

import pytest
import time
from src.executor.core.shadow_ledger import ShadowLedger


class TestShadowLedger:
    """测试 Shadow Ledger 核心功能"""

    @pytest.fixture
    def shadow_ledger(self):
        """创建 Shadow Ledger 实例"""
        # 使用较小的冷却时间以便测试
        return ShadowLedger(sync_threshold_pct=0.10, cooldown_seconds=2)

    def test_update_target_position(self, shadow_ledger):
        """测试更新目标持仓"""
        shadow_ledger.update_target_position(
            symbol="SOL-USDT-SWAP",
            side="BUY",
            size=2.5
        )

        target = shadow_ledger.get_target_position("SOL-USDT-SWAP")
        assert target is not None
        assert target["side"] == "buy"
        assert target["size"] == 2.5

    def test_check_no_mismatch(self, shadow_ledger):
        """测试无偏差情况"""
        # 设置目标：买入 2.0 SOL
        shadow_ledger.update_target_position(
            symbol="SOL-USDT-SWAP",
            side="BUY",
            size=2.0
        )

        # 实际持仓：2.0 SOL（完全匹配）
        api_positions = [
            {"symbol": "SOL-USDT-SWAP", "side": "long", "position_size": 2.0}
        ]

        needs_sync, resync_plan = shadow_ledger.check_and_calculate_delta(
            "SOL-USDT-SWAP", api_positions
        )

        assert needs_sync is False
        assert resync_plan == {}

    def test_check_mismatch_short_position(self, shadow_ledger):
        """测试持仓不足情况"""
        # 设置目标：买入 2.5 SOL
        shadow_ledger.update_target_position(
            symbol="SOL-USDT-SWAP",
            side="BUY",
            size=2.5
        )

        # 实际持仓：0.5 SOL（不足）
        api_positions = [
            {"symbol": "SOL-USDT-SWAP", "side": "long", "position_size": 0.5}
        ]

        needs_sync, resync_plan = shadow_ledger.check_and_calculate_delta(
            "SOL-USDT-SWAP", api_positions
        )

        # 偏差: 2.5 - 0.5 = 2.0 (80% > 10%)
        assert needs_sync is True
        assert resync_plan["symbol"] == "SOL-USDT-SWAP"
        assert resync_plan["side"] == "buy"
        assert abs(resync_plan["amount"] - 2.0) < 0.01  # 应该补单 2.0

    def test_check_mismatch_over_position(self, shadow_ledger):
        """测试持仓过多情况"""
        # 设置目标：买入 2.0 SOL
        shadow_ledger.update_target_position(
            symbol="SOL-USDT-SWAP",
            side="BUY",
            size=2.0
        )

        # 实际持仓：2.5 SOL（过多）
        api_positions = [
            {"symbol": "SOL-USDT-SWAP", "side": "long", "position_size": 2.5}
        ]

        needs_sync, resync_plan = shadow_ledger.check_and_calculate_delta(
            "SOL-USDT-SWAP", api_positions
        )

        # 偏差: 2.0 - 2.5 = -0.5 (25% > 10%)
        assert needs_sync is True
        assert resync_plan["side"] == "sell"  # 需要卖出
        assert abs(resync_plan["amount"] - 0.5) < 0.01

    def test_check_no_position(self, shadow_ledger):
        """测试空仓情况"""
        # 设置目标：买入 2.0 SOL
        shadow_ledger.update_target_position(
            symbol="SOL-USDT-SWAP",
            side="BUY",
            size=2.0
        )

        # 实际持仓：空仓
        api_positions = []

        needs_sync, resync_plan = shadow_ledger.check_and_calculate_delta(
            "SOL-USDT-SWAP", api_positions
        )

        # 偏差: 2.0 - 0 = 2.0 (100% > 10%)
        assert needs_sync is True
        assert resync_plan["side"] == "buy"
        assert abs(resync_plan["amount"] - 2.0) < 0.01

    def test_cooldown_mechanism(self, shadow_ledger):
        """测试冷却机制"""
        # 设置目标
        shadow_ledger.update_target_position(
            symbol="SOL-USDT-SWAP",
            side="BUY",
            size=2.0
        )

        # 第一次检查（有偏差）
        api_positions = []
        needs_sync1, _ = shadow_ledger.check_and_calculate_delta(
            "SOL-USDT-SWAP", api_positions
        )
        assert needs_sync1 is True

        # 标记已同步
        shadow_ledger.mark_synced("SOL-USDT-SWAP")

        # 立即再次检查（应该在冷却中）
        needs_sync2, resync2 = shadow_ledger.check_and_calculate_delta(
            "SOL-USDT-SWAP", api_positions
        )
        assert needs_sync2 is False
        assert resync2.get("reason") == "In cooldown"

        # 等待冷却时间后
        time.sleep(2.1)

        # 再次检查（应该可以触发同步）
        needs_sync3, resync3 = shadow_ledger.check_and_calculate_delta(
            "SOL-USDT-SWAP", api_positions
        )
        assert needs_sync3 is True

    def test_short_position_sync(self, shadow_ledger):
        """测试空头持仓同步"""
        # 设置目标：做空 1.5 SOL
        shadow_ledger.update_target_position(
            symbol="SOL-USDT-SWAP",
            side="SELL",
            size=1.5
        )

        # 实际持仓：空仓
        api_positions = []

        needs_sync, resync_plan = shadow_ledger.check_and_calculate_delta(
            "SOL-USDT-SWAP", api_positions
        )

        assert needs_sync is True
        assert resync_plan["side"] == "sell"
        assert abs(resync_plan["amount"] - 1.5) < 0.01

    def test_threshold_not_exceeded(self, shadow_ledger):
        """测试未超过阈值的情况"""
        # 设置目标：买入 2.0 SOL
        shadow_ledger.update_target_position(
            symbol="SOL-USDT-SWAP",
            side="BUY",
            size=2.0
        )

        # 实际持仓：1.85 SOL（偏差7.5%，未超过10%阈值）
        api_positions = [
            {"symbol": "SOL-USDT-SWAP", "side": "long", "position_size": 1.85}
        ]

        needs_sync, resync_plan = shadow_ledger.check_and_calculate_delta(
            "SOL-USDT-SWAP", api_positions
        )

        assert needs_sync is False
        assert resync_plan == {}

    def test_multiple_positions(self, shadow_ledger):
        """测试多个交易对的情况"""
        # 设置两个目标
        shadow_ledger.update_target_position(
            symbol="SOL-USDT-SWAP",
            side="BUY",
            size=2.0
        )
        shadow_ledger.update_target_position(
            symbol="BTC-USDT-SWAP",
            side="BUY",
            size=0.1
        )

        # 实际持仓：只有 SOL
        api_positions = [
            {"symbol": "SOL-USDT-SWAP", "side": "long", "position_size": 2.0}
        ]

        # 检查 SOL（应该不触发同步）
        needs_sync_sol, _ = shadow_ledger.check_and_calculate_delta(
            "SOL-USDT-SWAP", api_positions
        )
        assert needs_sync_sol is False

        # 检查 BTC（应该触发同步）
        needs_sync_btc, resync_btc = shadow_ledger.check_and_calculate_delta(
            "BTC-USDT-SWAP", api_positions
        )
        assert needs_sync_btc is True
        assert resync_btc["symbol"] == "BTC-USDT-SWAP"
        assert resync_btc["side"] == "buy"
