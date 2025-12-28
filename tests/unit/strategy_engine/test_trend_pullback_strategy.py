"""
趋势回调策略单元测试
测试策略逻辑、指标计算、"不死鸟"仓位管理
"""

import pytest
import pandas as pd
import numpy as np
from src.strategy_engine.core.trend_pullback_strategy import TrendPullbackStrategy


class TestTrendPullbackStrategy:
    """趋势回调策略测试类"""

    @pytest.fixture
    def config(self):
        """测试配置"""
        return {
            'trading': {
                'capital': 100.0,
                'max_risk_pct': 0.02,
                'position_size_pct': 0.5,
                'trading_symbol': 'SOL-USDT-SWAP',
                'use_demo': True
            },
            'strategy': {
                'type': 'trend_pullback',
                'enabled': True,
                'ema_period': 144,
                'rsi_period': 14,
                'rsi_oversold': 30,
                'rsi_overbought': 70,
                'stop_loss_pct': 0.03,
                'take_profit_pct': 0.06,
                'use_bollinger_exit': True,
                'bollinger_period': 20,
                'bollinger_std_dev': 2,
                'only_long': True,
                'max_leverage': 3.0,
                'min_leverage': 2.0
            }
        }

    @pytest.fixture
    def strategy(self, config):
        """策略实例"""
        return TrendPullbackStrategy(config)

    @pytest.fixture
    def sample_dataframe(self):
        """示例市场数据"""
        # 创建200个数据点（足够计算EMA 144）
        np.random.seed(42)

        dates = pd.date_range(start='2024-01-01', periods=200, freq='1h')

        # 生成上涨趋势的价格数据
        close_prices = 100 + np.cumsum(np.random.randn(200) * 0.5)

        df = pd.DataFrame({
            'timestamp': dates,
            'open': close_prices + np.random.randn(200) * 0.1,
            'high': close_prices + np.abs(np.random.randn(200) * 0.5),
            'low': close_prices - np.abs(np.random.randn(200) * 0.5),
            'close': close_prices,
            'volume': np.random.randint(1000, 10000, 200)
        })

        return df

    def test_strategy_initialization(self, strategy, config):
        """测试策略初始化"""
        assert strategy.config == config
        assert strategy.ema_period == 144
        assert strategy.rsi_period == 14
        assert strategy.rsi_oversold == 30
        assert strategy.rsi_overbought == 70
        assert strategy.stop_loss_pct == 0.03
        assert strategy.take_profit_pct == 0.06
        assert strategy.only_long == True
        assert strategy.max_leverage == 3.0

    def test_analyze_trend_bullish(self, strategy, sample_dataframe):
        """测试牛市趋势判断"""
        # 创建明显的牛市数据：最近的价格显著高于历史平均水平
        df = sample_dataframe.copy()

        # 最后50根K线价格显著提高
        df.loc[150:, 'close'] = df['close'].iloc[:50].mean() * 2.0
        df.loc[150:, 'high'] = df['close'].iloc[150:] * 1.02
        df.loc[150:, 'low'] = df['close'].iloc[150:] * 0.98
        df.loc[150:, 'open'] = df['close'].iloc[150:] * 1.0

        indicators = strategy._calculate_indicators(df)
        trend = strategy._analyze_trend(indicators)

        assert trend == 'bullish'
        assert indicators['ema_144'] > 0
        assert indicators['close'] > indicators['ema_144']

    def test_analyze_trend_bearish(self, strategy, sample_dataframe):
        """测试熊市趋势判断"""
        # 确保价格低于EMA 144
        df = sample_dataframe.copy()
        df['close'] = df['close'] * 0.8  # 降低价格

        indicators = strategy._calculate_indicators(df)
        trend = strategy._analyze_trend(indicators)

        assert trend == 'bearish'
        assert indicators['close'] < indicators['ema_144']

    def test_calculate_position_size_fixed_risk(self, strategy):
        """测试'不死鸟'仓位计算 - 固定风险模型"""
        current_price = 150.0
        stop_loss_price = 145.0  # 止损距离 $5

        result = strategy._calculate_position_size(current_price, stop_loss_price)

        # 验证计算
        assert result['position_size'] > 0
        assert result['position_value'] > 0
        assert result['leverage'] > 0
        assert result['risk_amount'] > 0

        # 核心验证：每单风险不超过2%
        capital = strategy.config['trading']['capital']
        max_risk = capital * 0.02  # $2

        # 实际风险应该接近最大风险
        assert abs(result['risk_amount'] - max_risk) < 0.01

        print(f"\n仓位计算结果：")
        print(f"  当前价格：${current_price}")
        print(f"  止损价格：${stop_loss_price}")
        print(f"  风险/单位：${result['risk_per_unit']:.2f}")
        print(f"  仓位数量：{result['position_size']:.4f}")
        print(f"  仓位价值：${result['position_value']:.2f}")
        print(f"  杠杆率：{result['leverage']:.2f}x")
        print(f"  实际风险：${result['risk_amount']:.2f} ({result['risk_pct']:.2f}%)")

    def test_calculate_position_size_leverage_cap(self, strategy):
        """测试杠杆率上限"""
        # 创建一个极端场景：止损非常小
        current_price = 150.0
        stop_loss_price = 149.9  # 止损距离仅 $0.1

        result = strategy._calculate_position_size(current_price, stop_loss_price)

        # 杠杆率不应超过3x
        assert result['leverage'] <= 3.0
        assert result['leverage'] == 3.0  # 应该被调整到3x

        print(f"\n杠杆率限制测试：")
        print(f"  计算杠杆率：{result['leverage']:.2f}x")
        print(f"  上限：3.0x")

    def test_buy_signal_generation(self, strategy, sample_dataframe):
        """测试买入信号生成"""
        # 创建牛市 + 超卖场景
        df = sample_dataframe.copy()
        df['close'] = df['close'] * 1.5  # 牛市

        # 模拟RSI超卖（通过调整价格）
        # 注意：这里我们测试信号生成逻辑，不精确控制RSI值
        signal = strategy.analyze(df, current_position=None)

        # 应该生成某种信号（BUY/SELL/HOLD）
        assert 'signal' in signal
        assert 'reasoning' in signal
        assert 'confidence' in signal
        assert signal['signal'] in ['BUY', 'SELL', 'HOLD']

    def test_sell_signal_with_position(self, strategy, sample_dataframe):
        """测试有持仓时的卖出信号"""
        # 模拟有持仓
        current_position = {
            'symbol': 'SOL-USDT-SWAP',
            'size': 10.0,
            'entry_price': 150.0,
            'side': 'long'
        }

        df = sample_dataframe.copy()
        df['close'] = df['close'] * 1.5

        signal = strategy.analyze(df, current_position=current_position)

        # 有持仓时应该检查出场条件
        assert 'signal' in signal
        assert signal['signal'] in ['BUY', 'SELL', 'HOLD']

    def test_only_long_mode(self, strategy, sample_dataframe):
        """测试只做多模式"""
        # 确保只做多模式已启用
        assert strategy.only_long == True

        # 创建熊市场景
        df = sample_dataframe.copy()
        df['close'] = df['close'] * 0.8  # 熊市

        indicators = strategy._calculate_indicators(df)
        trend = strategy._analyze_trend(indicators)

        assert trend == 'bearish'

        # 在只做多模式下，不应该有SELL信号
        signal = strategy.analyze(df, current_position=None)
        if signal['signal'] == 'SELL':
            # 如果有SELL信号，应该是因为有持仓需要平仓，而不是开空头
            assert 'overbought' not in signal['reasoning'].lower()

    def test_insufficient_data(self, strategy):
        """测试数据不足的情况"""
        # 创建不足的数据（少于144根K线）
        df = pd.DataFrame({
            'timestamp': pd.date_range(start='2024-01-01', periods=100, freq='1h'),
            'open': [100] * 100,
            'high': [105] * 100,
            'low': [95] * 100,
            'close': [100] * 100,
            'volume': [5000] * 100
        })

        # 应该返回HOLD信号而不是抛出异常
        signal = strategy.analyze(df)

        assert signal['signal'] == 'HOLD'
        assert 'Insufficient data' in signal['reasoning'] or 'error' in signal['reasoning'].lower()

    def test_stop_loss_levels(self, strategy):
        """测试止损止盈水平计算"""
        current_price = 150.0
        stop_loss_price = current_price * (1 - strategy.stop_loss_pct)
        take_profit_price = current_price * (1 + strategy.take_profit_pct)

        expected_stop_loss = 150.0 * 0.97  # 145.5
        expected_take_profit = 150.0 * 1.06  # 159.0

        assert abs(stop_loss_price - expected_stop_loss) < 0.01
        assert abs(take_profit_price - expected_take_profit) < 0.01

    def test_risk_calculation_scenario_1(self, strategy):
        """测试风险计算场景1：正常情况"""
        # SOL $150，止损 $145，本金 $100
        current_price = 150.0
        stop_loss_price = 145.0

        result = strategy._calculate_position_size(current_price, stop_loss_price)

        # 风险/单位 = $5
        # 最大风险 = $2 (2% of $100)
        # 仓位数量 = $2 / $5 = 0.4 SOL
        # 仓位价值 = 0.4 * $150 = $60
        # 杠杆率 = $60 / $100 = 0.6x

        assert result['risk_per_unit'] == 5.0
        assert abs(result['position_size'] - 0.4) < 0.001
        assert abs(result['position_value'] - 60.0) < 0.01
        assert abs(result['leverage'] - 0.6) < 0.01

    def test_risk_calculation_scenario_2(self, strategy):
        """测试风险计算场景2：小止损距离"""
        # SOL $150，止损 $149，本金 $100
        current_price = 150.0
        stop_loss_price = 149.0

        result = strategy._calculate_position_size(current_price, stop_loss_price)

        # 风险/单位 = $1
        # 最大风险 = $2
        # 仓位数量 = $2 / $1 = 2 SOL
        # 仓位价值 = 2 * $150 = $300
        # 杠杆率 = $300 / $100 = 3x (被限制)

        assert result['risk_per_unit'] == 1.0
        assert abs(result['position_size'] - 2.0) < 0.001
        assert abs(result['position_value'] - 300.0) < 0.01
        assert result['leverage'] == 3.0  # 被限制到最大值

    def test_fallback_ema_calculation(self, strategy, sample_dataframe):
        """测试EMA fallback计算"""
        ema = strategy._calculate_ema_fallback(sample_dataframe['close'], 144)

        assert ema is not None
        assert ema > 0
        assert isinstance(ema, float)

    def test_fallback_rsi_calculation(self, strategy, sample_dataframe):
        """测试RSI fallback计算"""
        rsi = strategy._calculate_rsi_fallback(sample_dataframe['close'], 14)

        assert rsi is not None
        assert 0 <= rsi <= 100  # RSI应该在0-100之间
        assert isinstance(rsi, float)

    def test_fallback_bollinger_bands(self, strategy, sample_dataframe):
        """测试布林带fallback计算"""
        bb = strategy._calculate_bollinger_bands_fallback(sample_dataframe['close'], 20, 2)

        assert 'bollinger_upper' in bb
        assert 'bollinger_lower' in bb
        assert 'bollinger_middle' in bb
        assert bb['bollinger_upper'] > bb['bollinger_middle']
        assert bb['bollinger_middle'] > bb['bollinger_lower']

    def test_hold_signal_creation(self, strategy):
        """测试HOLD信号创建"""
        hold_signal = strategy._create_hold_signal("Test reason")

        assert hold_signal['signal'] == 'HOLD'
        assert hold_signal['reasoning'] == "Test reason"
        assert hold_signal['confidence'] == 50.0
        assert hold_signal['position_size'] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
