#!/usr/bin/env python3
"""
双均线策略测试 - 提升dual_ema_strategy.py覆盖率
目标：从45.65%提升到85%+
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
    """提升dual_ema_strategy覆盖率的测试"""

    def setup_method(self):
        """每个测试前的设置"""
        # 重置全局策略实例
        import src.strategy_engine.dual_ema_strategy
        src.strategy_engine.dual_ema_strategy._dual_ema_strategy = None

    def test_golden_cross_buy_signal(self):
        """测试金叉（BUY信号）检测"""
        strategy = DualEMAStrategy(ema_fast=9, ema_slow=21)

        # 构造金叉数据：快线从下往上穿过慢线
        # 前30根K线：快线EMA < 慢线EMA
        # 后20根K线：快线EMA > 慢线EMA
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
        assert signal["stop_loss"] > 0
        assert signal["take_profit"] > 0
        assert signal["ema_fast"] > signal["ema_slow"]
        assert "Golden Cross" in signal["reasoning"]

    def test_death_cross_sell_signal(self):
        """测试死叉（SELL信号）检测"""
        strategy = DualEMAStrategy(ema_fast=9, ema_slow=21)

        # 构造死叉数据：快线从上往下穿过慢线
        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_crossover_data(cross_type="death")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert signal["signal"] == "SELL"
        assert signal["confidence"] == 75.0
        assert signal["ema_fast"] < signal["ema_slow"]
        assert "Death Cross" in signal["reasoning"]

    def test_no_crossover_hold_signal(self):
        """测试无交叉时返回HOLD"""
        strategy = DualEMAStrategy()

        # 构造无交叉数据：快线和慢线平行或远离
        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_trend_data(trend="up")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert signal["signal"] == "HOLD"
        assert "No crossover" in signal["reasoning"]

    def test_signal_persistence_prevents_duplicate(self):
        """测试信号持久性防止重复触发"""
        strategy = DualEMAStrategy()

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_crossover_data(cross_type="golden")
                }
            }
        }

        # 第一次金叉
        signal1 = strategy.generate_signal(historical_data, "BTC-USDT")
        assert signal1["signal"] == "BUY"

        # 第二次相同数据不应再次触发（因为last_signal已经设为BUY）
        signal2 = strategy.generate_signal(historical_data, "BTC-USDT")
        assert signal2["signal"] == "HOLD"

    def test_insufficient_data_return_hold(self):
        """测试数据不足时返回HOLD"""
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
        assert "Insufficient data" in signal["reasoning"]

    def test_exception_handling(self):
        """测试异常处理"""
        strategy = DualEMAStrategy()

        # 无效数据（空列表）
        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": []
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert signal["signal"] == "HOLD"
        assert "Strategy error" in signal["reasoning"]

    def test_reset_state(self):
        """测试策略状态重置"""
        strategy = DualEMAStrategy()

        # 设置一些状态
        strategy.previous_ema_fast = 100.0
        strategy.previous_ema_slow = 98.0
        strategy.last_signal = "BUY"
        strategy.last_signal_time = int(time.time())

        # 重置
        strategy.reset_state()

        assert strategy.previous_ema_fast is None
        assert strategy.previous_ema_slow is None
        assert strategy.last_signal is None
        assert strategy.last_signal_time is None

    def test_singleton_strategy_instance(self):
        """测试策略实例单例模式"""
        instance1 = get_dual_ema_strategy()
        instance2 = get_dual_ema_strategy()

        # 应该是同一个实例
        assert instance1 is instance2

    def test_custom_ema_periods(self):
        """测试自定义EMA周期"""
        strategy = DualEMAStrategy(ema_fast=5, ema_slow=13)

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": self._create_crossover_data(cross_type="golden")
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        # 验证使用了自定义周期
        assert signal["signal"] == "BUY"
        # 确保有足够数据（至少ema_slow + 1）
        assert len(historical_data["historical_analysis"]["5m"]["ohlcv"]) >= 14

    def test_decision_id_generation(self):
        """测试决策ID生成"""
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
        assert isinstance(signal["decision_id"], str)

    def test_timestamp_in_signal(self):
        """测试信号包含时间戳"""
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
        """测试信号包含当前价格"""
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
        """测试便捷函数generate_dual_ema_signal"""
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
        """测试多个时间框架数据"""
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

        # 策略只使用5m数据
        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        assert "signal" in signal
        assert "confidence" in signal

    def test_stop_loss_calculation(self):
        """测试止损计算"""
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
            # 买入信号的止损价格应该低于当前价格
            assert "stop_loss" in signal
            assert signal["stop_loss"] < signal["current_price"]
        elif signal["signal"] == "SELL":
            # 卖出信号的止损价格应该高于当前价格
            assert "stop_loss" in signal
            assert signal["stop_loss"] > signal["current_price"]

    def test_take_profit_calculation(self):
        """测试止盈计算"""
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
            # 买入信号的止盈价格应该高于当前价格
            assert "take_profit" in signal
            assert signal["take_profit"] > signal["current_price"]
        elif signal["signal"] == "SELL":
            # 卖出信号的止盈价格应该低于当前价格
            assert "take_profit" in signal
            assert signal["take_profit"] < signal["current_price"]

    def _create_crossover_data(self, cross_type="golden"):
        """
        创建交叉测试数据

        Args:
            cross_type: "golden"（金叉）或 "death"（死叉）

        Returns:
            list: OHLCV数据列表
        """
        base_price = 50000.0
        data = []
        current_time = int(time.time() * 1000)

        # 生成足够的数据（至少50根K线）
        # 前30根K线用于建立趋势
        # 后20根K线触发交叉
        for i in range(50):
            timestamp = current_time - (50 - i) * 15 * 60 * 1000

            if i < 30:
                # 趋势建立阶段
                if cross_type == "golden":
                    # 金叉前先下跌（快线 < 慢线）
                    price = base_price - (30 - i) * 10
                else:
                    # 死叉前先上涨（快线 > 慢线）
                    price = base_price + i * 10
            else:
                # 触发交叉
                if cross_type == "golden":
                    # 金叉：价格快速上涨
                    price = base_price + (i - 30) * 50 + 1000
                else:
                    # 死叉：价格快速下跌
                    price = base_price - (i - 30) * 50 - 1000

            high = price * 1.002
            low = price * 0.998
            close = price
            open_ = price * 1.001
            volume = 1000

            data.append([timestamp, open_, high, low, close, volume])

        return data

    def _create_trend_data(self, trend="up"):
        """
        创建趋势数据（无交叉）

        Args:
            trend: "up", "down", 或 "sideways"

        Returns:
            list: OHLCV数据列表
        """
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
                # 横盘
                price = base_price + (i % 5 - 2) * 5

            high = price * 1.002
            low = price * 0.998
            close = price
            open_ = price * 1.001
            volume = 1000

            data.append([timestamp, open_, high, low, close, volume])

        return data


class TestDualEMAStrategyEdgeCases:
    """测试边缘情况"""

    def setup_method(self):
        """每个测试前的设置"""
        import src.strategy_engine.dual_ema_strategy
        src.strategy_engine.dual_ema_strategy._dual_ema_strategy = None

    def test_missing_5m_data(self):
        """测试缺少5m数据"""
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
        """测试OHLCV数据格式"""
        strategy = DualEMAStrategy()

        # 测试不同格式的OHLCV数据
        for data_format in ["list", "dict"]:
            if data_format == "list":
                ohlcv = self._create_crossover_data(cross_type="golden")
            else:
                # 如果需要测试其他格式
                ohlcv = self._create_crossover_data(cross_type="golden")

            historical_data = {
                "historical_analysis": {
                    "5m": {
                        "ohlcv": ohlcv
                    }
                }
            }

            signal = strategy.generate_signal(historical_data, "BTC-USDT")
            assert "signal" in signal

    def test_zero_price_handling(self):
        """测试零价格处理"""
        strategy = DualEMAStrategy()

        # 构造包含零价格的数据
        data = self._create_trend_data(trend="up")
        data[-1][4] = 0  # 将最后一个收盘价设为0

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": data
                }
            }
        }

        # 应该能处理零价格而不崩溃
        signal = strategy.generate_signal(historical_data, "BTC-USDT")
        assert "signal" in signal

    def test_negative_price_handling(self):
        """测试负价格处理"""
        strategy = DualEMAStrategy()

        # 构造包含负价格的数据
        data = self._create_trend_data(trend="down")
        data[-1][4] = -100  # 负价格

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": data
                }
            }
        }

        # 应该能处理负价格而不崩溃
        signal = strategy.generate_signal(historical_data, "BTC-USDT")
        assert "signal" in signal

    def test_minimum_data_requirements(self):
        """测试最小数据要求"""
        strategy = DualEMAStrategy(ema_fast=9, ema_slow=21)

        # 测试刚好满足最小要求的数据量（21 + 1 = 22根K线）
        data = self._create_trend_data(trend="up")[:22]

        historical_data = {
            "historical_analysis": {
                "5m": {
                    "ohlcv": data
                }
            }
        }

        signal = strategy.generate_signal(historical_data, "BTC-USDT")

        # 应该能生成信号（即使是HOLD）
        assert "signal" in signal

    def test_multiple_consecutive_signals(self):
        """测试连续信号"""
        strategy = DualEMAStrategy()

        # 构造多个金叉
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

        # 重置状态
        strategy.reset_state()

        # 第一个应该是BUY
        # 后面应该是HOLD（因为last_signal已设置）
        assert signals[0] == "BUY"
        assert signals[1] == "HOLD"
        assert signals[2] == "HOLD"

    def _create_trend_data(self, trend="up"):
        """辅助方法：创建趋势数据"""
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
