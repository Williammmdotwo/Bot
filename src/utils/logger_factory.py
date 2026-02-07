"""
LoggerFactory - 统一日志管理系统

职责：
- 提供统一的日志记录器接口
- 支持模块级别的日志配置
- 提供性能监控日志功能
- 标准化日志格式（可选 emoji）

设计原则：
- 统一接口：所有模块使用相同的日志获取方式
- 灵活配置：支持环境变量配置日志级别
- 性能监控：内置计时功能
- 结构化日志：支持 JSON 格式输出（可选）
"""

import logging
import os
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict


# ========== 日志级别映射 ==========

LEVEL_MAP = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

# ========== 模块级别默认配置 ==========

MODULE_LEVELS = {
    'position_sizer': 'WARNING',      # 生产环境关闭详细日志
    'signal_generator': 'INFO',
    'event_bus': 'WARNING',
    'execution_algo': 'INFO',
    'strategy': 'INFO',
    'gateway': 'INFO',
    'risk': 'INFO',
}


# ========== 日志格式配置 ==========

class LogFormat:
    """日志格式常量"""

    # 标准格式（带 emoji）
    STANDARD = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # 简洁格式（无 emoji）
    SIMPLE = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'

    # JSON 格式（用于 ELK Stack）
    JSON = None  # 使用自定义 JSONFormatter

    # 日期格式
    DATE_FMT = '%Y-%m-%d %H:%M:%S'


class JSONFormatter(logging.Formatter):
    """JSON 格式化器（用于结构化日志）"""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # 添加额外字段
        if hasattr(record, 'extra'):
            log_obj.update(record.extra)

        # 添加异常信息
        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)

        import json
        return json.dumps(log_obj, ensure_ascii=False)


# ========== LoggerFactory ==========

class LoggerFactory:
    """统一日志工厂"""

    _initialized = False
    _loggers: Dict[str, logging.Logger] = {}
    _use_emoji = True

    @classmethod
    def initialize(cls, level: str = "INFO", use_emoji: bool = True):
        """
        初始化日志系统（全局只需调用一次）

        Args:
            level: 默认日志级别
            use_emoji: 是否使用 emoji（默认 True）
        """
        if cls._initialized:
            return

        cls._use_emoji = use_emoji

        # 获取根 Logger
        root_logger = logging.getLogger()
        root_logger.setLevel(LEVEL_MAP.get(level.upper(), logging.INFO))

        # 设置格式
        formatter = logging.Formatter(
            LogFormat.STANDARD if use_emoji else LogFormat.SIMPLE,
            datefmt=LogFormat.DATE_FMT
        )

        # 控制台 Handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(LEVEL_MAP.get(level.upper(), logging.INFO))
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        # 降低第三方库日志级别
        cls._suppress_third_party_logs()

        cls._initialized = True
        logging.getLogger(__name__).info(f"✅ 日志系统初始化完成: level={level}, emoji={use_emoji}")

    @classmethod
    def get_logger(cls, name: str, level: Optional[str] = None) -> logging.Logger:
        """
        获取日志记录器

        Args:
            name: Logger 名称（通常使用 __name__）
            level: 可选的日志级别（覆盖默认配置）

        Returns:
            logging.Logger: Logger 实例

        使用示例：
            >>> logger = LoggerFactory.get_logger(__name__)
            >>> logger.info("这是一条日志")
        """
        # 如果已缓存，直接返回
        if name in cls._loggers:
            return cls._loggers[name]

        # 创建新的 Logger
        logger = logging.getLogger(name)

        # 从环境变量或模块配置读取级别
        if level is None:
            module_name = name.split('.')[-1]
            env_key = f"{module_name.upper()}_LOG_LEVEL"
            level = os.getenv(env_key, MODULE_LEVELS.get(module_name, 'INFO'))

        logger.setLevel(LEVEL_MAP.get(level.upper(), logging.INFO))

        # 缓存
        cls._loggers[name] = logger

        return logger

    @classmethod
    def create_performance_logger(cls, name: str) -> 'PerformanceLogger':
        """
        创建性能日志记录器

        Args:
            name: Logger 名称

        Returns:
            PerformanceLogger: 性能日志记录器实例

        使用示例：
            >>> perf_logger = LoggerFactory.create_performance_logger(__name__)
            >>> perf_logger.start_timer('on_tick')
            >>> # ... 执行业务逻辑 ...
            >>> perf_logger.end_timer('on_tick', threshold_ms=30.0)
        """
        return PerformanceLogger(name)

    @classmethod
    def _suppress_third_party_logs(cls):
        """降低第三方库的日志级别"""
        suppress_list = [
            'aiohttp',
            'websockets',
            'urllib3',
            'httpx',
            'ccxt',
            'asyncio',
        ]

        for lib in suppress_list:
            logging.getLogger(lib).setLevel(logging.WARNING)

    @classmethod
    def set_level(cls, name: str, level: str):
        """
        动态设置日志级别

        Args:
            name: Logger 名称（"*" 表示所有）
            level: 日志级别

        使用示例：
            >>> LoggerFactory.set_level('*', 'DEBUG')
            >>> LoggerFactory.set_level('position_sizer', 'WARNING')
        """
        if name == '*':
            logging.getLogger().setLevel(LEVEL_MAP.get(level.upper(), logging.INFO))
        else:
            logging.getLogger(name).setLevel(LEVEL_MAP.get(level.upper(), logging.INFO))


# ========== PerformanceLogger ==========

class PerformanceLogger:
    """性能日志记录器（带计时功能）"""

    def __init__(self, name: str):
        """
        初始化性能日志记录器

        Args:
            name: Logger 名称
        """
        self.logger = LoggerFactory.get_logger(name)
        self._timers: Dict[str, float] = {}

    def start_timer(self, event: str):
        """
        开始计时

        Args:
            event: 事件名称

        使用示例：
            >>> perf_logger.start_timer('on_tick')
        """
        self._timers[event] = time.perf_counter()

    def end_timer(self, event: str, threshold_ms: float = 50.0, log_all: bool = False):
        """
        结束计时并记录

        Args:
            event: 事件名称
            threshold_ms: 超过此阈值才记录警告（默认 50ms）
            log_all: 是否记录所有计时（默认 False）

        使用示例：
            >>> perf_logger.end_timer('on_tick', threshold_ms=30.0)
        """
        if event not in self._timers:
            self.logger.warning(f"⚠️ [性能] 未找到计时器: {event}")
            return

        elapsed_ms = (time.perf_counter() - self._timers[event]) * 1000.0

        if log_all or elapsed_ms > threshold_ms:
            level = logging.WARNING if elapsed_ms > threshold_ms else logging.INFO
            emoji = "⚠️" if elapsed_ms > threshold_ms else "✅"
            self.logger.log(
                level,
                f"{emoji} [性能] {event}: {elapsed_ms:.2f}ms"
                f"{f' > {threshold_ms}ms' if elapsed_ms > threshold_ms else ''}"
            )

        # 清理计时器
        del self._timers[event]

    def log_latency(self, event: str, latency_ms: float, threshold_ms: float = 50.0):
        """
        直接记录延迟（无需计时）

        Args:
            event: 事件名称
            latency_ms: 延迟时间（毫秒）
            threshold_ms: 超过此阈值记录警告

        使用示例：
            >>> perf_logger.log_latency('on_tick', 45.5, threshold_ms=30.0)
        """
        if latency_ms > threshold_ms:
            self.logger.warning(
                f"⚠️ [性能] {event}: {latency_ms:.2f}ms > {threshold_ms}ms"
            )
        elif self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(
                f"✅ [性能] {event}: {latency_ms:.2f}ms"
            )


# ========== StructuredLogger ==========

class StructuredLogger:
    """结构化日志记录器"""

    def __init__(self, name: str):
        """
        初始化结构化日志记录器

        Args:
            name: Logger 名称
        """
        self.logger = LoggerFactory.get_logger(name)

    def log_trade(self, symbol: str, side: str, price: float, size: float, **kwargs):
        """
        记录交易日志（结构化格式）

        Args:
            symbol: 交易对
            side: 方向（buy/sell）
            price: 价格
            size: 数量
            **kwargs: 额外信息

        使用示例：
            >>> struct_logger.log_trade(
            ...     'DOGE-USDT-SWAP',
            ...     'buy',
            ...     0.0850,
            ...     1000,
            ...     order_id='12345',
            ...     strategy='scalper_v2'
            ... )
        """
        import time
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

        self.logger.info(
            f"📊 [交易] {symbol} {side.upper()} "
            f"{size:.4f} @ {price:.6f} "
            f"| {kwargs}"
        )

    def log_order(self, action: str, order_id: str, **kwargs):
        """
        记录订单日志

        Args:
            action: 动作（submit/cancel/fill）
            order_id: 订单 ID
            **kwargs: 额外信息

        使用示例：
            >>> struct_logger.log_order(
            ...     'submit',
            ...     '12345',
            ...     symbol='DOGE-USDT-SWAP',
            ...     side='buy',
            ...     price=0.0850
            ... )
        """
        emoji_map = {
            'submit': '📤',
            'cancel': '❌',
            'fill': '✅',
            'reject': '🚫',
            'error': '⚠️',
        }
        emoji = emoji_map.get(action.lower(), '📋')

        self.logger.info(
            f"{emoji} [订单-{action.upper()}] ID={order_id} | {kwargs}"
        )

    def log_position(self, symbol: str, position: float, pnl: float = 0.0, **kwargs):
        """
        记录持仓日志

        Args:
            symbol: 交易对
            position: 持仓数量
            pnl: 盈亏
            **kwargs: 额外信息
        """
        emoji = "📈" if pnl > 0 else "📉"

        self.logger.info(
            f"{emoji} [持仓] {symbol}: {position:.4f} "
            f"PnL: {pnl:.2f}USDT | {kwargs}"
        )


# ========== 便捷函数 ==========

def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    便捷函数：获取日志记录器

    Args:
        name: Logger 名称
        level: 可选的日志级别

    Returns:
        logging.Logger: Logger 实例
    """
    return LoggerFactory.get_logger(name, level)


def get_performance_logger(name: str) -> PerformanceLogger:
    """
    便捷函数：获取性能日志记录器

    Args:
        name: Logger 名称

    Returns:
        PerformanceLogger: 性能日志记录器实例
    """
    return LoggerFactory.create_performance_logger(name)


def get_structured_logger(name: str) -> StructuredLogger:
    """
    便捷函数：获取结构化日志记录器

    Args:
        name: Logger 名称

    Returns:
        StructuredLogger: 结构化日志记录器实例
    """
    return StructuredLogger(name)


# ========== 测试代码 ==========

if __name__ == '__main__':
    # 初始化日志系统
    LoggerFactory.initialize(level='DEBUG', use_emoji=True)

    # 测试普通日志
    logger = get_logger('test')
    logger.debug("这是一条 DEBUG 消息")
    logger.info("这是一条 INFO 消息")
    logger.warning("这是一条 WARNING 消息")
    logger.error("这是一条 ERROR 消息")
    logger.critical("这是一条 CRITICAL 消息")

    # 测试性能日志
    perf_logger = get_performance_logger('test_perf')
    perf_logger.start_timer('test_operation')
    time.sleep(0.02)  # 模拟耗时操作
    perf_logger.end_timer('test_operation', threshold_ms=10.0)

    # 测试结构化日志
    struct_logger = get_structured_logger('test_struct')
    struct_logger.log_trade(
        'DOGE-USDT-SWAP',
        'buy',
        0.0850,
        1000,
        order_id='12345',
        strategy='scalper_v2'
    )

    struct_logger.log_order(
        'submit',
        '12345',
        symbol='DOGE-USDT-SWAP',
        side='buy',
        price=0.0850
    )

    struct_logger.log_position(
        'DOGE-USDT-SWAP',
        1000,
        pnl=50.5
    )

    print("✅ 日志系统测试完成")
