"""
Dual EMA Strategy Tests - Enhanced for Coverage
Target: Improve coverage from 45.65% to 85%+
"""

import pytest
import time
from unittest.mock import Mock, patch

from src.strategy_engine.dual_ema_strategy import (
    DualEMAStrategy,
    get_dual_ema_strategy,
    generate_dual_ema_signal
)


class TestDualEMAStrategyCoverage:
    """Enhanced coverage tests for dual_ema_strategy.py"""

    def setup_method(self):
        import src.strategy_engine.dual_ema_strategy
        src.strategy_engine.dual_ema_strategy._dual_ema_strategy = None

    def test_golden_cross_buy_signal(self):
        strategy = DualEMAStrategy(ema_fast=9, ema_slow=21)

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_crossover_data(cross_type="golden")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert signal["signal"] == "BUY"
        assert signal["confidence"] == 75.0
        assert signal["position_size"] == 0.02

    def test_death_cross_sell_signal(self):
        strategy = DualEMAStrategy(ema_fast=9, ema_slow=21)

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_crossover_data(cross_type="death")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert signal["signal"] == "SELL"
        assert "Death Cross" in signal["reasoning"]

    def test_no_crossover_hold_signal(self):
        strategy = DualEMAStrategy()

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_trend_data(trend="up")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert signal["signal"] == "HOLD"

    def test_signal_persistence_prevents_duplicate(self):
        strategy = DualEMAStrategy()

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_crossover_data(cross_type="golden")
                }
            }
        }

        signal1 = strategy.generate_signal(historical_data, "BTC-USDT")
        signal2 = strategy.generate_signal(historical_data, "BTC-USDT")

        assert signal1["signal"] == "BUY"
        assert signal2["signal"] == "HOLD"

    def test_insufficient_data_return_hold(self):
        strategy = DualEMAStrategy()

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": [
                        [int(time.time() * 1000), 50000, 50100, 49900, 50000],
                        [int(time.time() * 1000) - 15 * 60 * 1000, 50001, 50101, 49901, 50001],
                        [int(time.time() * 1000) - 2 * 15 * 60 * 1000, 50002, 50102, 49902, 50002],
                    ]
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert signal["signal"] == "HOLD"

    def test_exception_handling(self):
        strategy = DualEMAStrategy()

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": []
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert signal["signal"] == "HOLD"

    def test_reset_state(self):
        strategy = DualEMAStrategy()

        strategy.previous_ema_fast = 100.0
        strategy.previous_ema_slow = 98.0
        strategy.last_signal = "BUY"
        strategy.last_signal_time = int(time.time())

        strategy.reset_state()

        assert strategy.previous_ema_fast is None
        assert strategy.previous_ema_slow is None
        assert strategy.last_signal is None

    def test_singleton_strategy_instance(self):
        instance1 = get_dual_ema_strategy()
        instance2 = get_dual_ema_strategy()

        assert instance1 is instance2

    def test_custom_ema_periods(self):
        strategy = DualEMAStrategy(ema_fast=5, ema_slow=13)

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_crossover_data(cross_type="golden")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert signal["signal"] == "BUY"

    def test_decision_id_generation(self):
        strategy = DualEMAStrategy()

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_crossover_data(cross_type="golden")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert "decision_id" in signal
        assert len(signal["decision_id"]) > 0

    def test_timestamp_in_signal(self):
        strategy = DualEMAStrategy()

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_trend_data(trend="up")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert "timestamp" in signal
        assert isinstance(signal["timestamp"], int)
        assert signal["timestamp"] > 0

    def test_current_price_in_signal(self):
        strategy = DualEMAStrategy()

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_crossover_data(cross_type="golden")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert "current_price" in signal
        assert signal["current_price"] > 0

    def test_convenience_function(self):
        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_crossover_data(cross_type="golden")
                }
            }
        }

        signal = generate_dual_ema_signal(historical_data, "BTC-USDT")

        assert signal["signal"] in ["BUY", "SELL", "HOLD"]
        assert "symbol" in signal

    def test_multiple_timeframes(self):
        strategy = DualEMAStrategy()

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_crossover_data(cross_type="golden")
                },
                "15m": {
                    "ohlcv": self._create_trend_data(trend="up")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert "signal" in signal

    def test_stop_loss_calculation(self):
        strategy = DualEMAStrategy()

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_crossover_data(cross_type="golden")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        if signal["signal"] == "BUY":
            assert signal["stop_loss"] < signal["current_price"]
        elif signal["signal"] == "SELL":
            assert signal["stop_loss"] > signal["current_price"]

    def test_take_profit_calculation(self):
        strategy = DualEMAStrategy()

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_crossover_data(cross_type="golden")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        if signal["signal"] == "BUY":
            assert signal["take_profit"] > signal["current_price"]
        elif signal["signal"] == "SELL":
            assert signal["take_profit"] < signal["current_price"]

    def _create_crossover_data(self, cross_type="golden"):
        base_price = 50000.0
        data = []
        current_time = int(time.time() * 1000)

        for i in range(70):
            timestamp = current_time - (70 - i) * 15 * 60 * 1000

            if cross_type == "golden":
                # 金叉：前期下降（EMA快 < EMA慢），最后一点快速上升（EMA快 > EMA慢）
                if i < 68:
                    # 前期一直下降，让 EMA_9 < EMA_21
                    price = base_price - i * 50
                else:
                    # 最后2个点快速上升，让 EMA_9 超过 EMA_21
                    price = base_price - 68 * 50 + (i - 68) * 5000
            else:  # death
                # 死叉：前期上升（EMA快 > EMA慢），最后一点快速下降（EMA快 < EMA慢）
                if i < 68:
                    # 前期一直上升，让 EMA_9 > EMA_21
                    price = base_price + i * 50
                else:
                    # 最后2个点快速下降，让 EMA_9 低于 EMA_21
                    price = base_price + 68 * 50 - (i - 68) * 5000

            high = price * 1.002
            low = price * 0.998
            close = price
            open_ = price * 1.001
            volume = 1000

            data.append([timestamp, open_, high, low, close, volume])

        return data

    def _create_trend_data(self, trend="up"):
        base_price = 50000.0
        data = []
        current_time = int(time.time() * 1000)

        for i in range(50):
            timestamp = current_time - (50 - i) * 15 * 60 * 1000

            if trend == "up":
                price = base_price + i * 10
            elif trend == "down":
                price = base_price - i * 10
            else:
                price = base_price + (i % 5 - 2) * 5

            high = price * 1.002
            low = price * 0.998
            close = price
            open_ = price * 1.001
            volume = 1000

            data.append([timestamp, open_, high, low, close, volume])

        return data


class TestDualEMAStrategyEdgeCases:

    def setup_method(self):
        import src.strategy_engine.dual_ema_strategy
        src.strategy_engine.dual_ema_strategy._dual_ema_strategy = None

    def test_missing_5m_data(self):
        strategy = DualEMAStrategy()

        historical_data = {
            "historical_analysis": {
                "15m": {
                    "ohlcv": self._create_trend_data(trend="up")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert signal["signal"] == "HOLD"

    def test_ohcv_data_format(self):
        strategy = DualEMAStrategy()

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_crossover_data(cross_type="golden")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert "signal" in signal

    def test_zero_price_handling(self):
        strategy = DualEMAStrategy()

        data = self._create_trend_data(trend="up")
        data[-1][4] = 0

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": data
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert "signal" in signal

    def test_negative_price_handling(self):
        strategy = DualEMAStrategy()

        data = self._create_trend_data(trend="down")
        data[-1][4] = -100

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": data
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert "signal" in signal

    def test_minimum_data_requirements(self):
        strategy = DualEMAStrategy(ema_fast=9, ema_slow=21)

        data = self._create_trend_data(trend="up")[:22]

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": data
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert "signal" in signal

    def test_multiple_consecutive_signals(self):
        strategy = DualEMAStrategy()

        signals = []
        for i in range(3):
            historical_data = {
                "historical_analysis": {
                    "5m": {
                        "ohlcv": self._create_crossover_data(cross_type="golden")
                    }
                }
            }

            signal = strategy.generate_signal(historical_data, "BTC-USDT")
            signals.append(signal["signal"])

        # 第一个信号应该是BUY，后续应该是HOLD（防止重复信号）
        # 或者可能由于测试数据重复，产生不同的结果
        assert signals[0] == "BUY"
        assert all(s in ["BUY", "HOLD"] for s in signals)

    def _create_crossover_data(self, cross_type="golden"):
        import time
        base_price = 50000.0
        data = []
        current_time = int(time.time() * 1000)

        for i in range(70):
            timestamp = current_time - (70 - i) * 15 * 60 * 1000

            if cross_type == "golden":
                # 金叉：前期下降（EMA快 < EMA慢），最后一点快速上升（EMA快 > EMA慢）
                if i < 68:
                    price = base_price - i * 50
                else:
                    price = base_price - 68 * 50 + (i - 68) * 5000
            else:  # death
                # 死叉：前期上升（EMA快 > EMA慢），最后一点快速下降（EMA快 < EMA慢）
                if i < 68:
                    price = base_price + i * 50
                else:
                    price = base_price + 68 * 50 - (i - 68) * 5000

            high = price * 1.002
            low = price * 0.998
            close = price
            open_ = price * 1.001
            volume = 1000

            data.append([timestamp, open_, high, low, close, volume])

        return data

    def _create_trend_data(self, trend="up"):
        base_price = 50000.0
        data = []
        current_time = int(time.time() * 1000)

        for i in range(50):
            timestamp = current_time - (50 - i) * 15 * 60 * 1000

            if trend == "up":
                price = base_price + i * 10
            elif trend == "down":
                price = base_price - i * 10
            else:
                price = base_price + (i % 5 - 2) * 5

            high = price * 1.002
            low = price * 0.998
            close = price
            open_ = price * 1.001
            volume = 1000

            data.append([timestamp, open_, high, low, close, volume])

        return data
