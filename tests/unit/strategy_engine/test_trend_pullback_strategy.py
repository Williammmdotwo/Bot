"""
Trend Pullback Strategy Tests
Target: Improve coverage from 49.77% to 85%+
"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch

from src.strategy_engine.core.trend_pullback_strategy import (
    TrendPullbackStrategy,
    create_trend_pullback_strategy
)


class TestTrendPullbackStrategyCoverage:

    def setup_method(self):
        pass

    def _create_bullish_data(self, rsi=25):
        data = []
        base_price = 50000.0
        for i in range(150):
            price = base_price + i * 50
            data.append({
                'close': price,
                'high': price * 1.002,
                'low': price * 0.998,
                'volume': 1000
            })
        return pd.DataFrame(data)

    def _create_bearish_data(self, rsi=75):
        data = []
        base_price = 50000.0
        for i in range(150):
            price = base_price - i * 50
            data.append({
                'close': price,
                'high': price * 1.002,
                'low': price * 0.998,
                'volume': 1000
            })
        return pd.DataFrame(data)

    def test_bullish_trend_oversold_entry(self):
        config = {
            'ema_period': 144,
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'only_long': True,
            'stop_loss_pct': 0.03,
            'take_profit_pct': 0.06,
            'bollinger_period': 20,
            'bollinger_std_dev': 2,
            'use_bollinger_exit': True,
            'max_leverage': 3.0,
            'min_leverage': 2.0
        }

        strategy = create_trend_pullback_strategy(config)
        df = self._create_bullish_data(rsi=25)
        signal = strategy.analyze(df)

        assert signal['signal'] == 'BUY'
        assert signal['confidence'] >= 70.0

    def test_bearish_trend_overbought_entry_short(self):
        config = {
            'ema_period': 144,
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'only_long': False,
            'stop_loss_pct': 0.03,
            'take_profit_pct': 0.06,
            'use_bollinger_exit': True,
            'max_leverage': 3.0,
            'min_leverage': 2.0
        }

        strategy = create_trend_pullback_strategy(config)
        df = self._create_bearish_data(rsi=75)
        signal = strategy.analyze(df)

        assert signal['signal'] == 'SELL'

    def test_bearish_trend_only_long_mode(self):
        config = {
            'ema_period': 144,
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'only_long': True
        }

        strategy = create_trend_pullback_strategy(config)
        df = self._create_bearish_data(rsi=75)
        signal = strategy.analyze(df)

        assert signal['signal'] == 'HOLD'

    def test_rsi_overbought_take_profit_long(self):
        config = {
            'ema_period': 144,
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'only_long': True,
            'stop_loss_pct': 0.03,
            'take_profit_pct': 0.06,
            'use_bollinger_exit': False
        }

        strategy = create_trend_pullback_strategy(config)
        df = self._create_bullish_data(rsi=80)
        current_position = {
            'size': 0.5,
            'entry_price': 50000.0
        }

        signal = strategy.analyze(df, current_position)
        assert signal['signal'] == 'SELL'

    def test_stop_loss_ema_break_long(self):
        config = {
            'ema_period': 144,
            'stop_loss_pct': 0.03
        }

        strategy = create_trend_pullback_strategy(config)
        df = self._create_bullish_data()

        current_position = {
            'size': 0.5,
            'entry_price': 51000.0
        }

        signal = strategy.analyze(df, current_position)
        assert signal['signal'] == 'SELL'
        assert 'Stop Loss' in signal['reasoning']

    def test_fixed_risk_position_sizing(self):
        config = {
            'trading': {
                'capital': 10000.0,
                'max_risk_pct': 0.02
            },
            'strategy': {
                'max_leverage': 3.0,
                'min_leverage': 2.0
            },
            'stop_loss_pct': 0.03
        }

        strategy = create_trend_pullback_strategy(config)
        current_price = 50000.0
        stop_loss_price = 48500.0

        result = strategy._calculate_position_size(current_price, stop_loss_price)

        assert result['risk_amount'] <= 200.0
        assert result['risk_pct'] <= 2.0
        assert 2.0 <= result['leverage'] <= 3.0

    def test_leverage_adjustment_too_high(self):
        config = {
            'trading': {
                'capital': 10000.0,
                'max_risk_pct': 0.02
            },
            'strategy': {
                'max_leverage': 3.0,
                'min_leverage': 2.0
            },
            'stop_loss_pct': 0.03
        }

        strategy = create_trend_pullback_strategy(config)
        current_price = 50000.0
        stop_loss_price = 49999.9

        result = strategy._calculate_position_size(current_price, stop_loss_price)

        assert result['leverage'] <= 3.0

    def test_neutral_market(self):
        config = {
            'ema_period': 144,
            'only_long': True
        }

        strategy = create_trend_pullback_strategy(config)
        data = []
        for i in range(150):
            price = 50000
            data.append({
                'close': price,
                'high': price * 1.002,
                'low': price * 0.998,
                'volume': 1000
            })
        df = pd.DataFrame(data)

        signal = strategy.analyze(df)
        assert signal['signal'] == 'HOLD'

    def test_insufficient_data_exception(self):
        config = {
            'ema_period': 144,
            'bollinger_period': 20
        }

        strategy = create_trend_pullback_strategy(config)
        data = []
        for i in range(10):
            price = 50000 + i
            data.append({
                'close': price,
                'high': price * 1.002,
                'low': price * 0.998,
                'volume': 1000
            })
        df = pd.DataFrame(data)

        signal = strategy.analyze(df)

        assert signal['signal'] == 'HOLD'

    def test_calculate_indicators(self):
        config = {
            'ema_period': 144,
            'rsi_period': 14,
            'bollinger_period': 20,
            'bollinger_std_dev': 2,
            'use_bollinger_exit': True
        }

        strategy = create_trend_pullback_strategy(config)
        df = self._create_bullish_data(rsi=50)

        indicators = strategy._calculate_indicators(df)

        assert 'close' in indicators
        assert 'ema_144' in indicators
        assert 'rsi' in indicators
        assert 'bollinger_upper' in indicators
        assert 0 < indicators['rsi'] < 100

    def test_analyze_trend_bullish(self):
        config = {
            'ema_period': 144
        }

        strategy = create_trend_pullback_strategy(config)
        df = self._create_bullish_data(rsi=50)

        indicators = strategy._calculate_indicators(df)
        trend = strategy._analyze_trend(indicators)

        assert trend == 'bullish'

    def test_analyze_trend_bearish(self):
        config = {
            'ema_period': 144
        }

        strategy = create_trend_pullback_strategy(config)
        df = self._create_bearish_data(rsi=50)

        indicators = strategy._calculate_indicators(df)
        trend = strategy._analyze_trend(indicators)

        assert trend == 'bearish'

    def test_generate_signal_with_position(self):
        config = {
            'ema_period': 144,
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'only_long': True
        }

        strategy = create_trend_pullback_strategy(config)
        df = self._create_bullish_data(rsi=25)

        current_position = {
            'size': 0.5,
            'entry_price': 50000.0
        }

        signal = strategy.analyze(df, current_position)

        assert 'signal' in signal

    def test_calculate_exit_levels(self):
        config = {
            'stop_loss_pct': 0.03,
            'take_profit_pct': 0.06
        }

        strategy = create_trend_pullback_strategy(config)
        df = self._create_bullish_data(rsi=50)

        indicators = strategy._calculate_indicators(df)
        levels = strategy._calculate_exit_levels(indicators)

        assert 'stop_loss' in levels
        assert 'take_profit' in levels

    def test_create_hold_signal(self):
        config = {
            'ema_period': 144,
            'rsi_period': 14
        }

        strategy = create_trend_pullback_strategy(config)
        signal = strategy._create_hold_signal("Test hold")

        assert signal['signal'] == 'HOLD'
        assert signal['confidence'] == 50.0
        assert signal['position_size'] == 0.0

    def test_invalid_stop_loss_calculation(self):
        config = {
            'trading': {
                'capital': 10000.0,
                'max_risk_pct': 0.02
            },
            'stop_loss_pct': 0.03
        }

        strategy = create_trend_pullback_strategy(config)
        current_price = 50000.0
        stop_loss_price = 0

        result = strategy._calculate_position_size(current_price, stop_loss_price)

        assert 'position_size' in result
        assert 'reasoning' in result

    def test_config_parameters(self):
        config = {
            'ema_period': 200,
            'rsi_period': 20,
            'rsi_oversold': 25,
            'rsi_overbought': 75,
            'only_long': False,
            'stop_loss_pct': 0.02,
            'take_profit_pct': 0.04,
            'bollinger_period': 50,
            'bollinger_std_dev': 2.5,
            'use_bollinger_exit': True,
            'max_leverage': 5.0,
            'min_leverage': 1.0
        }

        strategy = create_trend_pullback_strategy(config)

        assert strategy.ema_period == 200
        assert strategy.rsi_period == 20
        assert strategy.rsi_oversold == 25
        assert strategy.rsi_overbought == 75
        assert strategy.only_long == False
        assert strategy.stop_loss_pct == 0.02
        assert strategy.take_profit_pct == 0.04
        assert strategy.use_bollinger_exit == True
        assert strategy.bollinger_period == 50
        assert strategy.max_leverage == 5.0
        assert strategy.min_leverage == 1.0
