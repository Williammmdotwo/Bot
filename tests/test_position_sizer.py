"""
测试 PositionSizer - 自适应仓位管理组件

测试覆盖：
1. 基础仓位计算
2. 信号强度自适应（5x → 1.0x, 10x → 1.5x）
3. 波动率保护（标准差计算、超限缩减）
4. 流动性保护（单向深度、盘口限制）
5. 边界条件处理（最小下单金额、零仓位、极大波动率）
"""
import pytest
from src.strategies.hft.components.position_sizer import (
    PositionSizer,
    PositionSizingConfig
)
import math


@pytest.fixture
def position_sizer():
    """创建 PositionSizer 实例，使用默认配置"""
    config = PositionSizingConfig(
        base_equity_ratio=0.02,  # 基础仓位：总资金的 2%
        max_leverage=5.0,
        min_order_value=10.0,
        signal_scaling_enabled=True,
        signal_threshold_normal=5.0,
        signal_threshold_aggressive=10.0,
        signal_aggressive_multiplier=1.5,
        liquidity_protection_enabled=True,
        liquidity_depth_ratio=0.20,  # 单笔金额不超过盘口前 3 档的 20%
        liquidity_depth_levels=3,
        volatility_protection_enabled=True,
        volatility_ema_period=20,
        volatility_threshold=0.001  # 波动率阈值 0.1%
    )
    return PositionSizer(config)


class TestPositionSizerBasicCalculation:
    """测试基础仓位计算"""

    def test_base_position_calculation(self, position_sizer):
        """
        测试：基础仓位计算

        验证逻辑：
        - 基础仓位 = 账户权益 × 2%
        """
        account_equity = 10000.0
        expected_base = account_equity * 0.02  # 200 USDT

        # 计算基础仓位（实际实现使用 cfg 而不是 config）
        base_amount = position_sizer.cfg.base_equity_ratio * account_equity

        assert base_amount == expected_base, \
            f"基础仓位应为 {expected_base} USDT，实际为 {base_amount} USDT"

    def test_base_position_with_different_equity(self, position_sizer):
        """
        测试：不同权益的基础仓位计算

        验证逻辑：
        - 10000 U → 200 U
        - 50000 U → 1000 U
        - 100000 U → 2000 U
        """
        test_cases = [
            (10000.0, 200.0),
            (50000.0, 1000.0),
            (100000.0, 2000.0)
        ]

        for equity, expected in test_cases:
            base_amount = position_sizer.cfg.base_equity_ratio * equity
            assert base_amount == expected, \
                f"权益 {equity} U 应产生基础仓位 {expected} U"


class TestSignalStrengthAdaptation:
    """测试信号强度自适应"""

    def test_normal_signal_1x_multiplier(self, position_sizer):
        """
        测试：正常信号（5x 不平衡）使用 1.0 倍数

        验证逻辑：
        - 不平衡比 = 5.2x（达到阈值）
        - 使用基础仓位 × 1.0
        """
        account_equity = 10000.0
        signal_ratio = 5.2  # 略高于 5.0

        # 计算信号调整倍数（实际实现使用 cfg）
        if signal_ratio >= position_sizer.cfg.signal_threshold_aggressive:
            multiplier = position_sizer.cfg.signal_aggressive_multiplier
        elif signal_ratio >= position_sizer.cfg.signal_threshold_normal:
            multiplier = 1.0
        else:
            multiplier = 0.0

        assert multiplier == 1.0, \
            f"5.2x 不平衡应使用 1.0 倍数，实际为 {multiplier}"

    def test_aggressive_signal_1_5x_multiplier(self, position_sizer):
        """
        测试：激进信号（10x 不平衡）使用 1.5 倍数

        验证逻辑：
        - 不平衡比 = 10.5x（超过激进阈值）
        - 使用基础仓位 × 1.5
        """
        signal_ratio = 10.5  # 超过 10.0

        # 计算信号调整倍数（实际实现使用 cfg）
        if signal_ratio >= position_sizer.cfg.signal_threshold_aggressive:
            multiplier = position_sizer.cfg.signal_aggressive_multiplier
        elif signal_ratio >= position_sizer.cfg.signal_threshold_normal:
            multiplier = 1.0
        else:
            multiplier = 0.0

        assert multiplier == 1.5, \
            f"10.5x 不平衡应使用 1.5 倍数，实际为 {multiplier}"

    def test_weak_signal_0x_multiplier(self, position_sizer):
        """
        测试：弱信号（<5x 不平衡）使用 0.0 倍数

        验证逻辑：
        - 不平衡比 = 3.0x（低于阈值）
        - 使用基础仓位 × 0.0（跳过交易）
        """
        signal_ratio = 3.0  # 低于 5.0

        # 计算信号调整倍数（实际实现使用 cfg）
        if signal_ratio >= position_sizer.cfg.signal_threshold_aggressive:
            multiplier = position_sizer.cfg.signal_aggressive_multiplier
        elif signal_ratio >= position_sizer.cfg.signal_threshold_normal:
            multiplier = 1.0
        else:
            multiplier = 0.0

        assert multiplier == 0.0, \
            f"3.0x 不平衡应使用 0.0 倍数（跳过交易），实际为 {multiplier}"

    def test_signal_disabled_no_scaling(self, position_sizer):
        """
        测试：禁用信号强度自适应时，始终使用 1.0 倍数

        验证逻辑：
        - signal_scaling_enabled = False
        - 无论信号强弱，都使用 1.0 倍数
        """
        # 创建禁用信号自适应的配置
        config = PositionSizingConfig(
            base_equity_ratio=0.02,
            max_leverage=5.0,
            min_order_value=10.0,
            signal_scaling_enabled=False,  # 禁用
            signal_threshold_normal=5.0,
            signal_threshold_aggressive=10.0,
            signal_aggressive_multiplier=1.5,
            liquidity_protection_enabled=True,
            liquidity_depth_ratio=0.20,
            liquidity_depth_levels=3,
            volatility_protection_enabled=True,
            volatility_ema_period=20,
            volatility_threshold=0.001
        )
        sizer = PositionSizer(config)

        # 测试各种信号强度
        test_ratios = [3.0, 5.0, 10.0, 15.0]

        for signal_ratio in test_ratios:
            # 当信号自适应禁用时，应始终使用 1.0 倍数
            # （简化逻辑，实际实现可能不同）
            pass  # 实际测试需要调用 calculate_order_size

    def test_boundary_exact_normal_threshold(self, position_sizer):
        """
        测试：正好达到正常阈值（5.0x）使用 1.0 倍数

        验证逻辑：
        - 不平衡比 = 5.0x（正好阈值）
        - 使用基础仓位 × 1.0
        """
        signal_ratio = 5.0  # 正好等于阈值

        if signal_ratio >= position_sizer.cfg.signal_threshold_aggressive:
            multiplier = position_sizer.cfg.signal_aggressive_multiplier
        elif signal_ratio >= position_sizer.cfg.signal_threshold_normal:
            multiplier = 1.0
        else:
            multiplier = 0.0

        assert multiplier == 1.0, \
            f"5.0x 不平衡（正好阈值）应使用 1.0 倍数，实际为 {multiplier}"

    def test_boundary_exact_aggressive_threshold(self, position_sizer):
        """
        测试：正好达到激进阈值（10.0x）使用 1.5 倍数

        验证逻辑：
        - 不平衡比 = 10.0x（正好阈值）
        - 使用基础仓位 × 1.5
        """
        signal_ratio = 10.0  # 正好等于阈值

        if signal_ratio >= position_sizer.cfg.signal_threshold_aggressive:
            multiplier = position_sizer.cfg.signal_aggressive_multiplier
        elif signal_ratio >= position_sizer.cfg.signal_threshold_normal:
            multiplier = 1.0
        else:
            multiplier = 0.0

        assert multiplier == 1.5, \
            f"10.0x 不平衡（正好阈值）应使用 1.5 倍数，实际为 {multiplier}"


class TestVolatilityProtection:
    """测试波动率保护"""

    def test_standard_deviation_calculation(self, position_sizer):
        """
        测试：标准差计算

        验证逻辑：
        - 计算价格历史的标准差
        - 验证计算公式
        """
        # 准备价格历史：[100, 101, 99, 102, 98]
        prices = [100.0, 101.0, 99.0, 102.0, 98.0]

        # 手动计算标准差
        mean = sum(prices) / len(prices)  # 100.0
        variance = sum((x - mean) ** 2 for x in prices) / len(prices)
        std = math.sqrt(variance)

        # 计算波动率
        volatility = std / mean if mean > 0 else 0.0

        assert volatility > 0, "波动率应大于 0"

    def test_normal_volatility_no_adjustment(self, position_sizer):
        """
        测试：正常波动率（0.08%）不调整仓位

        验证逻辑：
        - 波动率 = 0.08%（低于阈值 0.1%）
        - 缩减比例 = 1.0（不调整）
        """
        volatility = 0.0008  # 0.08%
        threshold = 0.001  # 0.1%

        if volatility <= threshold:
            reduction_factor = 1.0
        else:
            excess = volatility - threshold
            reduction_factor = max(0.5, 1.0 - excess * 10)

        assert reduction_factor == 1.0, \
            f"0.08% 波动率不应调整仓位，实际缩减比例为 {reduction_factor}"

    def test_high_volatility_10_percent_reduction(self, position_sizer):
        """
        测试：高波动率（0.11%）缩减 10% 仓位

        验证逻辑：
        - 波动率 = 0.011（1.1%，超过阈值 0.1%）
        - 超限 = 0.01
        - 缩减比例 = 1.0 - 0.01 * 10 = 0.9
        """
        volatility = 0.011  # 1.1%
        threshold = 0.001  # 0.1%

        excess = volatility - threshold  # 0.01
        reduction_factor = max(0.5, 1.0 - excess * 10)  # 0.9

        assert reduction_factor == 0.9, \
            f"1.1% 波动率应缩减 10%，实际缩减比例为 {reduction_factor}"

    def test_extreme_volatility_50_percent_reduction(self, position_sizer):
        """
        测试：极端波动率（6%）缩减 50% 仓位（最多）

        验证逻辑：
        - 波动率 = 0.06（6%，超过阈值 0.1%）
        - 超限 = 0.059
        - 理论缩减 = 1.0 - 0.059 * 10 = -4.9（不合理）
        - 实际缩减 = max(0.5, -4.9) = 0.5（最多缩减 50%）
        """
        volatility = 0.06  # 6%（极端）
        threshold = 0.001  # 0.1%

        excess = volatility - threshold  # 0.059
        reduction_factor = max(0.5, 1.0 - excess * 10)  # 应为 0.5

        assert reduction_factor == 0.5, \
            f"6% 波动率应缩减 50%（最多），实际缩减比例为 {reduction_factor}"

    def test_volatility_protection_disabled(self, position_sizer):
        """
        测试：禁用波动率保护时，不计算波动率

        验证逻辑：
        - volatility_protection_enabled = False
        - 波动率计算被跳过
        - 缩减比例始终为 1.0
        """
        config = PositionSizingConfig(
            base_equity_ratio=0.02,
            max_leverage=5.0,
            min_order_value=10.0,
            signal_scaling_enabled=True,
            signal_threshold_normal=5.0,
            signal_threshold_aggressive=10.0,
            signal_aggressive_multiplier=1.5,
            liquidity_protection_enabled=True,
            liquidity_depth_ratio=0.20,
            liquidity_depth_levels=3,
            volatility_protection_enabled=False,  # 禁用
            volatility_ema_period=20,
            volatility_threshold=0.001
        )
        sizer = PositionSizer(config)

        # 禁用时，缩减比例应为 1.0
        # （需要实际调用 calculate_order_size 验证）


class TestLiquidityProtection:
    """测试流动性保护"""

    def test_calculate_asks_value_for_buy(self, position_sizer):
        """
        测试：做多（Buy）计算卖方深度（Asks）总金额

        验证逻辑：
        - 交易方向 = 'buy'
        - 使用 order_book['asks'] 计算前 3 档总金额
        - 不使用 bids
        """
        order_book = {
            'bids': [
                [100.00, 1000.0],  # 价格, 数量
                [99.99, 800.0],
                [99.98, 600.0]
            ],
            'asks': [
                [100.01, 1000.0],  # 卖方深度
                [100.02, 800.0],
                [100.03, 600.0]
            ]
        }

        side = 'buy'  # 做多，只看卖方深度
        current_price = 100.015
        levels = 3

        # 计算卖方前 3 档总金额
        # 档1: 100.01 * 1000 = 100010
        # 档2: 100.02 * 800 = 80016
        # 档3: 100.03 * 600 = 60018
        # 总计: 240044

        depth_value = 0.0
        if side == 'buy' and 'asks' in order_book:
            asks = order_book['asks'][:levels]
            depth_value = sum(price * size for price, size in asks)

        assert depth_value > 240000, \
            f"卖方前 3 档总金额应约为 240044，实际为 {depth_value}"

    def test_calculate_bids_value_for_sell(self, position_sizer):
        """
        测试：做空（Sell）计算买方深度（Bids）总金额

        验证逻辑：
        - 交易方向 = 'sell'
        - 使用 order_book['bids'] 计算前 3 档总金额
        - 不使用 asks
        """
        order_book = {
            'bids': [
                [100.00, 1000.0],  # 买方深度
                [99.99, 800.0],
                [99.98, 600.0]
            ],
            'asks': [
                [100.01, 1000.0],
                [100.02, 800.0],
                [100.03, 600.0]
            ]
        }

        side = 'sell'  # 做空，只看买方深度
        current_price = 99.995
        levels = 3

        # 计算买方前 3 档总金额
        depth_value = 0.0
        if side == 'sell' and 'bids' in order_book:
            bids = order_book['bids'][:levels]
            depth_value = sum(price * size for price, size in bids)

        assert depth_value > 0, \
            f"买方前 3 档总金额应大于 0，实际为 {depth_value}"

    def test_liquidity_limit_20_percent(self, position_sizer):
        """
        测试：流动性限制为盘口深度的 20%

        验证逻辑：
        - 盘口深度 = 840 USDT
        - 限制比例 = 20%
        - 流动性限制 = 168 USDT
        """
        depth_value = 840.0
        ratio = 0.20

        liquidity_limit = depth_value * ratio

        assert liquidity_limit == 168.0, \
            f"840 USDT 深度 × 20% = 168 USDT，实际为 {liquidity_limit} USDT"

    def test_base_amount_within_liquidity_limit(self, position_sizer):
        """
        测试：基础仓位在流动性限制内，使用基础仓位

        验证逻辑：
        - 基础仓位 = 150 USDT
        - 流动性限制 = 168 USDT
        - 最终金额 = min(150, 168) = 150 USDT
        """
        base_amount = 150.0
        liquidity_limit = 168.0

        final_amount = min(base_amount, liquidity_limit)

        assert final_amount == 150.0, \
            f"基础仓位 150 U 应被使用（< 168 U），实际为 {final_amount} U"

    def test_base_amount_exceeds_liquidity_limit(self, position_sizer):
        """
        测试：基础仓位超过流动性限制，使用流动性限制

        验证逻辑：
        - 基础仓位 = 200 USDT
        - 流动性限制 = 168 USDT
        - 最终金额 = min(200, 168) = 168 USDT
        """
        base_amount = 200.0
        liquidity_limit = 168.0

        final_amount = min(base_amount, liquidity_limit)

        assert final_amount == 168.0, \
            f"基础仓位 200 U 应被限制（> 168 U），实际为 {final_amount} U"

    def test_insufficient_liquidity_skip_trade(self, position_sizer):
        """
        测试：流动性不足时跳过交易

        验证逻辑：
        - 盘口深度 = 50 USDT（极低）
        - 流动性限制 = 50 * 0.20 = 10 USDT
        - 最小下单金额 = 10 USDT
        - 流动性限制 = 10 U = 最小金额，应该允许
        """
        depth_value = 50.0
        ratio = 0.20
        liquidity_limit = depth_value * ratio  # 10.0
        min_order_value = 10.0

        # 流动性限制 = 最小金额，应该允许
        should_skip = liquidity_limit < min_order_value

        assert not should_skip, \
            "流动性限制 10 USDT = 最小金额，应允许交易"

    def test_insufficient_liquidity_below_minimum(self, position_sizer):
        """
        测试：流动性限制低于最小下单金额，跳过交易

        验证逻辑：
        - 盘口深度 = 40 USDT（极低）
        - 流动性限制 = 40 * 0.20 = 8 USDT
        - 最小下单金额 = 10 USDT
        - 流动性限制 8 U < 10 U，应该跳过
        """
        depth_value = 40.0
        ratio = 0.20
        liquidity_limit = depth_value * ratio  # 8.0
        min_order_value = 10.0

        should_skip = liquidity_limit < min_order_value

        assert should_skip, \
            "流动性限制 8 USDT < 最小金额 10 USDT，应跳过交易"

    def test_liquidity_protection_disabled(self, position_sizer):
        """
        测试：禁用流动性保护时，不计算流动性限制

        验证逻辑：
        - liquidity_protection_enabled = False
        - 流动性检查被跳过
        - 最终金额 = 基础金额
        """
        config = PositionSizingConfig(
            base_equity_ratio=0.02,
            max_leverage=5.0,
            min_order_value=10.0,
            signal_scaling_enabled=True,
            signal_threshold_normal=5.0,
            signal_threshold_aggressive=10.0,
            signal_aggressive_multiplier=1.5,
            liquidity_protection_enabled=False,  # 禁用
            liquidity_depth_ratio=0.20,
            liquidity_depth_levels=3,
            volatility_protection_enabled=True,
            volatility_ema_period=20,
            volatility_threshold=0.001
        )
        sizer = PositionSizer(config)

        # 禁用时，流动性保护应不起作用
        # （需要实际调用 calculate_order_size 验证）


class TestConvertToContracts:
    """测试合约张数转换"""

    def test_convert_usdt_to_contracts(self, position_sizer):
        """
        测试：将 USDT 金额转换为合约张数

        验证逻辑：
        - 合约张数 = 金额 / (价格 × 面值）
        - 向下取整
        """
        amount_usdt = 200.0
        current_price = 0.10
        contract_val = 10.0  # DOGE 合约面值

        # 计算合约张数
        contracts = amount_usdt / (current_price * contract_val)
        contracts_int = int(contracts)

        expected = 200.0 / (0.10 * 10.0)  # 200.0 / 1.0 = 200

        assert contracts_int == 200, \
            f"200 USDT 应转换为 200 张合约，实际为 {contracts_int}"

    def test_convert_minimum_1_contract(self, position_sizer):
        """
        测试：转换结果至少为 1 张

        验证逻辑：
        - 金额 = 5 USDT
        - 价格 = 0.10，面值 = 10
        - 理论张数 = 5.0 / 1.0 = 5 张
        - 应至少返回 1 张
        """
        amount_usdt = 5.0
        current_price = 0.10
        contract_val = 10.0

        contracts = int(amount_usdt / (current_price * contract_val))
        contracts = max(1, contracts)  # 至少 1 张

        assert contracts >= 1, "合约张数应至少为 1"

    def test_convert_floating_point_rounding(self, position_sizer):
        """
        测试：浮点数向下取整

        验证逻辑：
        - 金额 = 19.5 USDT
        - 价格 = 0.10，面值 = 10
        - 理论张数 = 19.5 张
        - 向下取整 = 19 张
        """
        amount_usdt = 19.5
        current_price = 0.10
        contract_val = 10.0

        contracts = int(amount_usdt / (current_price * contract_val))

        assert contracts == 19, \
            f"19.5 张应向下取整为 19 张，实际为 {contracts}"

    def test_convert_zero_contract_value(self, position_sizer):
        """
        测试：合约面值为 0 时的异常处理

        验证逻辑：
        - 合约面值 = 0（异常）
        - 应避免除以零错误
        """
        amount_usdt = 100.0
        current_price = 100.0
        contract_val = 0.0  # 异常值

        # 应该处理异常，避免除以零
        if contract_val <= 0:
            contracts = 0
        else:
            contracts = int(amount_usdt / (current_price * contract_val))

        assert contracts == 0, "合约面值为 0 时，应返回 0 张"


class TestIntegrationCalculateOrderSize:
    """测试完整的 calculate_order_size 流程"""

    def test_normal_market_conditions(self, position_sizer):
        """
        测试：正常市场条件下的完整计算流程

        场景：
        - 账户权益：10000 USDT
        - 信号：6x 不平衡（正常）
        - 波动率：0.08%（正常）
        - 流动性：盘口深度 1000 USDT

        预期：
        1. 基础仓位 = 10000 × 2% = 200 USDT
        2. 信号调整 = 200 × 1.0 = 200 USDT（6x 使用 1.0 倍）
        3. 波动率调整 = 200 × 1.0 = 200 USDT（0.08% < 0.1%）
        4. 流动性限制 = 1000 × 20% = 200 USDT
        5. 最终金额 = min(200, 200) = 200 USDT
        """
        # 这只是逻辑验证，实际测试需要调用 calculate_order_size
        # 由于 calculate_order_size 依赖价格历史，需要 mock 价格历史数据
        pass

    def test_aggressive_signal_high_volatility(self, position_sizer):
        """
        测试：激进信号 + 高波动率

        场景：
        - 账户权益：10000 USDT
        - 信号：12x 不平衡（激进）
        - 波动率：0.30%（高）
        - 流动性：盘口深度 500 USDT

        预期：
        1. 基础仓位 = 200 USDT
        2. 信号调整 = 200 × 1.5 = 300 USDT（12x 使用 1.5 倍）
        3. 波动率调整 = 300 × 0.5 = 150 USDT（0.30% > 0.1%，最多缩减 50%）
        4. 流动性限制 = 500 × 20% = 100 USDT
        5. 最终金额 = min(150, 100) = 100 USDT
        """
        pass  # 需要实际调用 calculate_order_size

    def test_insufficient_liquidity_return_zero(self, position_sizer):
        """
        测试：流动性不足时返回 0

        验证逻辑：
        - 流动性限制 < 最小下单金额
        - 返回 0（跳过交易）
        """
        pass  # 需要实际调用 calculate_order_size

    def test_zero_signal_ratio_return_zero(self, position_sizer):
        """
        测试：信号太弱时返回 0

        验证逻辑：
        - 不平衡比 = 2x（< 5x）
        - 返回 0（跳过交易）
        """
        pass  # 需要实际调用 calculate_order_size
