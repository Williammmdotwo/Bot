"""
HFT 性能监控模块

本模块提供性能指标收集和分析功能，用于监控 HFT 系统运行状态。

核心功能：
- Tick 处理延迟监控
- 订单执行延迟监控
- 交易频率监控
- 盈亏统计
- 性能指标导出

设计原则：
- 低开销（不影响交易性能）
- 线程安全
- 支持多维度分析
"""

import time
import logging
from typing import List, Dict, Any, Optional
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """
    性能指标收集器

    收集和分析 HFT 系统的性能指标。

    Example:
        >>> metrics = PerformanceMetrics(max_samples=1000)
        >>> metrics.record_tick_latency(0.5)  # 0.5ms
        >>> metrics.record_order_latency(100.0)  # 100ms
        >>> avg_latency = metrics.get_avg_tick_latency()
        >>> print(f"平均 Tick 延迟: {avg_latency:.3f}ms")
    """

    # 最大样本数（避免内存无限增长）
    max_samples: int = 1000

    # Tick 延迟（毫秒）
    tick_latency: deque = field(default_factory=lambda: deque(maxlen=1000))

    # 订单执行延迟（毫秒）
    order_latency: deque = field(default_factory=lambda: deque(maxlen=100))

    # 交易时间戳（用于计算交易频率）
    trade_timestamps: deque = field(default_factory=lambda: deque(maxlen=1000))

    # 盈亏历史（USDT）
    pnl_history: deque = field(default_factory=lambda: deque(maxlen=100))

    # 统计信息
    total_ticks: int = 0
    total_orders: int = 0
    total_trades: int = 0
    total_pnl: float = 0.0

    # 策略触发统计
    vulture_triggers: int = 0
    sniper_triggers: int = 0
    hard_stop_exits: int = 0
    trailing_stop_exits: int = 0
    time_stop_exits: int = 0

    # 错误统计
    order_errors: int = 0
    position_sync_errors: int = 0
    network_errors: int = 0

    def record_tick_latency(self, latency_ms: float):
        """
        记录 Tick 处理延迟

        Args:
            latency_ms (float): 延迟（毫秒）
        """
        self.tick_latency.append(latency_ms)
        self.total_ticks += 1

        # 每 1000 个 tick 记录一次日志
        if self.total_ticks % 1000 == 0:
            p95 = self.get_percentile_tick_latency(95)
            logger.info(
                f"Tick 延迟统计: avg={self.get_avg_tick_latency():.3f}ms, "
                f"p95={p95:.3f}ms, max={self.get_max_tick_latency():.3f}ms"
            )

    def record_order_latency(self, latency_ms: float):
        """
        记录订单执行延迟

        Args:
            latency_ms (float): 延迟（毫秒）
        """
        self.order_latency.append(latency_ms)
        self.total_orders += 1

        logger.debug(
            f"订单延迟: {latency_ms:.3f}ms, "
            f"avg={self.get_avg_order_latency():.3f}ms"
        )

    def record_trade(self, pnl: float, strategy: str = "unknown"):
        """
        记录交易

        Args:
            pnl (float): 盈亏（USDT）
            strategy (str): 策略类型（vulture/sniper/unknown）
        """
        timestamp = time.time()
        self.trade_timestamps.append(timestamp)
        self.pnl_history.append(pnl)
        self.total_trades += 1
        self.total_pnl += pnl

        logger.info(
            f"记录交易: strategy={strategy}, pnl={pnl:.2f}, "
            f"total_pnl={self.total_pnl:.2f}, total_trades={self.total_trades}"
        )

    def record_strategy_trigger(self, strategy: str):
        """
        记录策略触发

        Args:
            strategy (str): 策略类型（vulture/sniper）
        """
        if strategy == "vulture":
            self.vulture_triggers += 1
        elif strategy == "sniper":
            self.sniper_triggers += 1

    def record_exit(self, exit_type: str):
        """
        记录出场类型

        Args:
            exit_type (str): 出场类型（hard_stop/trailing_stop/time_stop）
        """
        if exit_type == "hard_stop":
            self.hard_stop_exits += 1
        elif exit_type == "trailing_stop":
            self.trailing_stop_exits += 1
        elif exit_type == "time_stop":
            self.time_stop_exits += 1

    def record_error(self, error_type: str):
        """
        记录错误

        Args:
            error_type (str): 错误类型（order/position_sync/network）
        """
        if error_type == "order":
            self.order_errors += 1
        elif error_type == "position_sync":
            self.position_sync_errors += 1
        elif error_type == "network":
            self.network_errors += 1

    def get_avg_tick_latency(self) -> float:
        """
        获取平均 Tick 延迟

        Returns:
            float: 平均延迟（毫秒）
        """
        if not self.tick_latency:
            return 0.0
        return sum(self.tick_latency) / len(self.tick_latency)

    def get_percentile_tick_latency(self, percentile: float = 95) -> float:
        """
        获取 Tick 延迟百分位数

        Args:
            percentile (float): 百分位数（0-100）

        Returns:
            float: 百分位延迟（毫秒）
        """
        if not self.tick_latency:
            return 0.0

        sorted_latency = sorted(self.tick_latency)
        index = int(len(sorted_latency) * percentile / 100)
        return sorted_latency[index]

    def get_max_tick_latency(self) -> float:
        """
        获取最大 Tick 延迟

        Returns:
            float: 最大延迟（毫秒）
        """
        if not self.tick_latency:
            return 0.0
        return max(self.tick_latency)

    def get_avg_order_latency(self) -> float:
        """
        获取平均订单延迟

        Returns:
            float: 平均延迟（毫秒）
        """
        if not self.order_latency:
            return 0.0
        return sum(self.order_latency) / len(self.order_latency)

    def get_trade_frequency(self, window_seconds: float = 60.0) -> float:
        """
        获取交易频率（交易数/秒）

        Args:
            window_seconds (float): 时间窗口（秒）

        Returns:
            float: 交易频率（交易数/秒）
        """
        if not self.trade_timestamps:
            return 0.0

        current_time = time.time()
        time_threshold = current_time - window_seconds

        # 筛选时间窗口内的交易
        recent_trades = [
            ts for ts in self.trade_timestamps
            if ts >= time_threshold
        ]

        if not recent_trades:
            return 0.0

        frequency = len(recent_trades) / window_seconds
        return frequency

    def get_win_rate(self) -> float:
        """
        获取胜率

        Returns:
            float: 胜率（0.0-1.0）
        """
        if not self.pnl_history:
            return 0.0

        wins = sum(1 for pnl in self.pnl_history if pnl > 0)
        win_rate = wins / len(self.pnl_history)

        return win_rate

    def get_profit_factor(self) -> float:
        """
        获取盈亏比（盈利总额/亏损总额）

        Returns:
            float: 盈亏比
        """
        if not self.pnl_history:
            return 0.0

        total_profit = sum(pnl for pnl in self.pnl_history if pnl > 0)
        total_loss = abs(sum(pnl for pnl in self.pnl_history if pnl < 0))

        if total_loss == 0:
            return float('inf') if total_profit > 0 else 0.0

        return total_profit / total_loss

    def get_summary(self) -> Dict[str, Any]:
        """
        获取性能指标汇总

        Returns:
            Dict[str, Any]: 包含所有性能指标的字典

        Example:
            >>> summary = metrics.get_summary()
            >>> print(f"Tick 延迟: {summary['avg_tick_latency']}ms")
            >>> print(f"交易频率: {summary['trade_frequency']} trades/sec")
            >>> print(f"胜率: {summary['win_rate']:.2%}")
            >>> print(f"盈亏比: {summary['profit_factor']:.2f}")
        """
        summary = {
            # Tick 处理性能
            'total_ticks': self.total_ticks,
            'avg_tick_latency': self.get_avg_tick_latency(),
            'p95_tick_latency': self.get_percentile_tick_latency(95),
            'p99_tick_latency': self.get_percentile_tick_latency(99),
            'max_tick_latency': self.get_max_tick_latency(),

            # 订单执行性能
            'total_orders': self.total_orders,
            'avg_order_latency': self.get_avg_order_latency(),
            'order_success_rate': 1.0 - (self.order_errors / max(self.total_orders, 1)),

            # 交易统计
            'total_trades': self.total_trades,
            'total_pnl': self.total_pnl,
            'win_rate': self.get_win_rate(),
            'profit_factor': self.get_profit_factor(),
            'trade_frequency': self.get_trade_frequency(window_seconds=60.0),

            # 策略触发
            'vulture_triggers': self.vulture_triggers,
            'sniper_triggers': self.sniper_triggers,
            'vulture_trigger_rate': self.vulture_triggers / max(self.total_ticks, 1),
            'sniper_trigger_rate': self.sniper_triggers / max(self.total_ticks, 1),

            # 出场统计
            'hard_stop_exits': self.hard_stop_exits,
            'trailing_stop_exits': self.trailing_stop_exits,
            'time_stop_exits': self.time_stop_exits,

            # 错误统计
            'order_errors': self.order_errors,
            'position_sync_errors': self.position_sync_errors,
            'network_errors': self.network_errors,
            'total_errors': (
                self.order_errors +
                self.position_sync_errors +
                self.network_errors
            )
        }

        return summary

    def reset(self):
        """
        重置所有指标

        Example:
            >>> metrics.reset()
        """
        self.tick_latency.clear()
        self.order_latency.clear()
        self.trade_timestamps.clear()
        self.pnl_history.clear()

        self.total_ticks = 0
        self.total_orders = 0
        self.total_trades = 0
        self.total_pnl = 0.0

        self.vulture_triggers = 0
        self.sniper_triggers = 0
        self.hard_stop_exits = 0
        self.trailing_stop_exits = 0
        self.time_stop_exits = 0

        self.order_errors = 0
        self.position_sync_errors = 0
        self.network_errors = 0

        logger.info("性能指标已重置")

    def export_prometheus(self) -> str:
        """
        导出 Prometheus 格式的指标

        Returns:
            str: Prometheus 格式的指标字符串

        Example:
            >>> prometheus_metrics = metrics.export_prometheus()
            >>> print(prometheus_metrics)
        """
        summary = self.get_summary()

        lines = [
            # Tick 性能
            f"hft_ticks_total {summary['total_ticks']}",
            f"hft_tick_latency_avg {summary['avg_tick_latency']}",
            f"hft_tick_latency_p95 {summary['p95_tick_latency']}",
            f"hft_tick_latency_p99 {summary['p99_tick_latency']}",

            # 订单性能
            f"hft_orders_total {summary['total_orders']}",
            f"hft_order_latency_avg {summary['avg_order_latency']}",
            f"hft_order_success_rate {summary['order_success_rate']}",

            # 交易统计
            f"hft_trades_total {summary['total_trades']}",
            f"hft_pnl_total {summary['total_pnl']}",
            f"hft_win_rate {summary['win_rate']}",
            f"hft_profit_factor {summary['profit_factor']}",
            f"hft_trade_frequency {summary['trade_frequency']}",

            # 策略触发
            f"hft_vulture_triggers_total {summary['vulture_triggers']}",
            f"hft_sniper_triggers_total {summary['sniper_triggers']}",

            # 出场统计
            f"hft_hard_stop_exits_total {summary['hard_stop_exits']}",
            f"hft_trailing_stop_exits_total {summary['trailing_stop_exits']}",
            f"hft_time_stop_exits_total {summary['time_stop_exits']}",

            # 错误统计
            f"hft_order_errors_total {summary['order_errors']}",
            f"hft_position_sync_errors_total {summary['position_sync_errors']}",
            f"hft_network_errors_total {summary['network_errors']}",
        ]

        return '\n'.join(lines)

    def __str__(self) -> str:
        """
        格式化输出性能指标

        Returns:
            str: 格式化的指标字符串
        """
        summary = self.get_summary()

        lines = [
            "=" * 60,
            "HFT 性能指标汇总",
            "=" * 60,
            "",
            "【Tick 处理性能】",
            f"  总 Tick 数: {summary['total_ticks']}",
            f"  平均延迟: {summary['avg_tick_latency']:.3f}ms",
            f"  P95 延迟: {summary['p95_tick_latency']:.3f}ms",
            f"  P99 延迟: {summary['p99_tick_latency']:.3f}ms",
            f"  最大延迟: {summary['max_tick_latency']:.3f}ms",
            "",
            "【订单执行性能】",
            f"  总订单数: {summary['total_orders']}",
            f"  平均延迟: {summary['avg_order_latency']:.3f}ms",
            f"  成功率: {summary['order_success_rate']:.2%}",
            "",
            "【交易统计】",
            f"  总交易数: {summary['total_trades']}",
            f"  总盈亏: {summary['total_pnl']:.2f} USDT",
            f"  胜率: {summary['win_rate']:.2%}",
            f"  盈亏比: {summary['profit_factor']:.2f}",
            f"  交易频率: {summary['trade_frequency']:.2f} trades/sec",
            "",
            "【策略触发】",
            f"  秃鹫触发: {summary['vulture_triggers']} 次",
            f"  狙击触发: {summary['sniper_triggers']} 次",
            f"  秃鹫触发率: {summary['vulture_trigger_rate']:.4%}",
            f"  狙击触发率: {summary['sniper_trigger_rate']:.4%}",
            "",
            "【出场统计】",
            f"  硬止损: {summary['hard_stop_exits']} 次",
            f"  追踪止盈: {summary['trailing_stop_exits']} 次",
            f"  时间止损: {summary['time_stop_exits']} 次",
            "",
            "【错误统计】",
            f"  订单错误: {summary['order_errors']} 次",
            f"  持仓同步错误: {summary['position_sync_errors']} 次",
            f"  网络错误: {summary['network_errors']} 次",
            f"  总错误数: {summary['total_errors']} 次",
            "",
            "=" * 60,
        ]

        return '\n'.join(lines)
