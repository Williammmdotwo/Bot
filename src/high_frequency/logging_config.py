"""
HFT 模块日志配置

提供高性能的日志配置管理，支持：
- 日志级别控制
- 日志输出格式化
- 日志性能优化
- 模块化日志管理
- 从环境变量读取配置

设计原则：
- 低开销（日志不应影响交易性能）
- 可配置（支持通过环境变量配置）
- 结构化（便于日志分析和监控）

环境变量配置：
- HFT_LOG_LEVEL: 全局日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
- HFT_LOG_FILE: 日志文件路径（可选）
- HFT_LOG_FILE_MAX_SIZE_MB: 日志文件最大大小（MB）
- HFT_LOG_FILE_BACKUP_COUNT: 日志文件备份数量
- HFT_MODULE_LOG_LEVELS: 模块日志级别（逗号分隔，如 core.engine:DEBUG,data.memory:INFO）
"""

import os
import logging
import sys
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler

# 日志级别映射
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

# 模块日志级别配置（默认配置）
MODULE_LOG_LEVELS = {
    'src.high_frequency': logging.INFO,
    'src.high_frequency.core': logging.INFO,
    'src.high_frequency.data': logging.INFO,
    'src.high_frequency.execution': logging.INFO,
    'src.high_frequency.monitoring': logging.INFO,
}


def load_logging_config_from_env() -> Dict[str, Any]:
    """
    从环境变量加载日志配置

    Returns:
        Dict[str, Any]: 日志配置字典

    Example:
        >>> config = load_logging_config_from_env()
        >>> print(config['log_level'])
        'INFO'
    """
    config = {
        'log_level': os.getenv('HFT_LOG_LEVEL', 'INFO'),
        'log_file': os.getenv('HFT_LOG_FILE'),
        'max_bytes': int(os.getenv('HFT_LOG_FILE_MAX_SIZE_MB', 10)) * 1024 * 1024,
        'backup_count': int(os.getenv('HFT_LOG_FILE_BACKUP_COUNT', 5))
    }

    # 解析模块日志级别
    module_levels_str = os.getenv('HFT_MODULE_LOG_LEVELS', '')
    if module_levels_str:
        module_levels = {}
        for item in module_levels_str.split(','):
            if ':' in item:
                module_name, level = item.strip().split(':')
                module_levels[module_name] = LOG_LEVELS.get(level.upper(), logging.INFO)
        config['module_levels'] = module_levels

    return config


class HFTLogger:
    """
    HFT 模块日志管理器

    提供统一的日志接口，支持性能优化和模块化配置。

    Example:
        >>> # 从环境变量加载配置
        >>> HFTLogger.configure_from_env()
        >>>
        >>> logger = HFTLogger.get_logger('core.engine')
        >>> logger.info("引擎初始化完成")
        >>> logger.debug(f"Tick 价格: {price}")
        >>> logger.error(f"订单执行失败: {error}")
    """

    _loggers: Dict[str, logging.Logger] = {}
    _configured = False

    @classmethod
    def configure(
        cls,
        log_level: str = 'INFO',
        log_format: Optional[str] = None,
        log_file: Optional[str] = None,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5
    ):
        """
        配置日志系统

        Args:
            log_level (str): 全局日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
            log_format (str): 日志格式（None 使用默认格式）
            log_file (str): 日志文件路径（None 不输出到文件）
            max_bytes (int): 日志文件最大大小（字节）
            backup_count (int): 日志文件备份数量

        Example:
            >>> HFTLogger.configure(
            ...     log_level='INFO',
            ...     log_file='logs/hft.log'
            ... )
        """
        if cls._configured:
            return

        # 设置日志级别
        level = LOG_LEVELS.get(log_level.upper(), logging.INFO)

        # 设置默认日志格式
        if log_format is None:
            # 简洁格式（生产环境）
            log_format = (
                '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
            )

        # 配置根日志记录器
        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        # 移除所有现有的处理器
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(log_format))
        root_logger.addHandler(console_handler)

        # 文件处理器（可选）
        if log_file:
            try:
                file_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding='utf-8'
                )
                file_handler.setLevel(level)
                file_handler.setFormatter(logging.Formatter(log_format))
                root_logger.addHandler(file_handler)
            except Exception as e:
                # 文件创建失败不影响系统运行
                print(f"警告：无法创建日志文件 {log_file}: {e}")

        # 配置模块日志级别
        for module_name, module_level in MODULE_LOG_LEVELS.items():
            module_logger = logging.getLogger(module_name)
            module_logger.setLevel(module_level)

        cls._configured = True
        print(f"HFT 日志系统已配置，级别: {log_level}")

    @classmethod
    def configure_from_env(cls):
        """
        从环境变量配置日志系统

        自动读取以下环境变量：
        - HFT_LOG_LEVEL: 全局日志级别
        - HFT_LOG_FILE: 日志文件路径
        - HFT_LOG_FILE_MAX_SIZE_MB: 日志文件最大大小
        - HFT_LOG_FILE_BACKUP_COUNT: 日志文件备份数量
        - HFT_MODULE_LOG_LEVELS: 模块日志级别

        Example:
            >>> HFTLogger.configure_from_env()
        """
        config = load_logging_config_from_env()

        # 配置日志系统
        cls.configure(
            log_level=config['log_level'],
            log_file=config['log_file'],
            max_bytes=config['max_bytes'],
            backup_count=config['backup_count']
        )

        # 配置模块日志级别
        if 'module_levels' in config:
            for module_name, level in config['module_levels'].items():
                cls.set_module_level(module_name, level)

        print(f"HFT 日志系统已从环境变量配置")

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """
        获取日志记录器

        Args:
            name (str): 日志记录器名称（如 'core.engine'）

        Returns:
            logging.Logger: 日志记录器实例

        Example:
            >>> logger = HFTLogger.get_logger('core.engine')
            >>> logger.info("信息")
        """
        if name not in cls._loggers:
            logger = logging.getLogger(f'src.high_frequency.{name}')
            cls._loggers[name] = logger

        return cls._loggers[name]

    @classmethod
    def set_module_level(cls, module_name: str, level: str):
        """
        设置模块日志级别

        Args:
            module_name (str): 模块名称（如 'core.engine'）
            level (str): 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）

        Example:
            >>> HFTLogger.set_module_level('core.engine', 'DEBUG')
        """
        log_level = LOG_LEVELS.get(level.upper(), logging.INFO)
        full_name = f'src.high_frequency.{module_name}'
        logger = logging.getLogger(full_name)
        logger.setLevel(log_level)
        print(f"模块 {module_name} 日志级别设置为 {level}")


class PerformanceLogger:
    """
    性能优化的日志记录器

    在高性能场景下，减少日志开销：
- 仅在必要时记录日志
- 支持条件日志（仅在满足条件时记录）
- 支持采样日志（仅记录部分日志）

    Example:
        >>> perf_logger = PerformanceLogger('core.engine')
        >>> perf_logger.info("重要事件")  # 总是记录
        >>> perf_logger.debug(f"Tick 价格: {price}")  # 可能不记录（取决于级别）
        >>> perf_logger.log_every(1000, "已处理 1000 个 Tick")
    """

    def __init__(self, name: str):
        """
        初始化性能日志记录器

        Args:
            name (str): 日志记录器名称
        """
        self.logger = HFTLogger.get_logger(name)
        self._counter = 0

    def info(self, msg: str, *args, **kwargs):
        """
        记录 INFO 级别日志

        Args:
            msg (str): 日志消息
        """
        self.logger.info(msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        """
        记录 DEBUG 级别日志（仅在 DEBUG 级别下记录）

        Args:
            msg (str): 日志消息
        """
        self.logger.debug(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        """
        记录 WARNING 级别日志

        Args:
            msg (str): 日志消息
        """
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        """
        记录 ERROR 级别日志

        Args:
            msg (str): 日志消息
        """
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        """
        记录 CRITICAL 级别日志

        Args:
            msg (str): 日志消息
        """
        self.logger.critical(msg, *args, **kwargs)

    def log_every(self, n: int, msg: str, *args, **kwargs):
        """
        每 N 次记录一次日志（采样日志）

        Args:
            n (int): 采样间隔
            msg (str): 日志消息

        Example:
            >>> perf_logger.log_every(1000, "已处理 1000 个 Tick")
        """
        self._counter += 1
        if self._counter % n == 0:
            self.info(msg, *args, **kwargs)

    def log_if(self, condition: bool, msg: str, *args, **kwargs):
        """
        条件日志（仅在满足条件时记录）

        Args:
            condition (bool): 条件
            msg (str): 日志消息

        Example:
            >>> perf_logger.log_if(price < 50000, f"价格跌破 50000: {price}")
        """
        if condition:
            self.info(msg, *args, **kwargs)

    def log_performance(self, operation: str, duration: float):
        """
        记录性能指标

        Args:
            operation (str): 操作名称
            duration (float): 耗时（秒）

        Example:
            >>> perf_logger.log_performance("Tick 处理", 0.0005)
        """
        duration_ms = duration * 1000
        self.debug(f"{operation}: {duration_ms:.3f}ms")


def configure_hft_logging(
    log_level: str = 'INFO',
    log_file: Optional[str] = None,
    log_format: Optional[str] = None
):
    """
    配置 HFT 模块日志（便捷函数）

    Args:
        log_level (str): 全局日志级别（默认 INFO）
        log_file (str): 日志文件路径（可选）
        log_format (str): 日志格式（可选）

    Example:
        >>> configure_hft_logging(
        ...     log_level='INFO',
        ...     log_file='logs/hft.log'
        ... )
    """
    HFTLogger.configure(
        log_level=log_level,
        log_file=log_file,
        log_format=log_format
    )


def get_hft_logger(name: str) -> logging.Logger:
    """
    获取 HFT 模块日志记录器（便捷函数）

    Args:
        name (str): 日志记录器名称

    Returns:
        logging.Logger: 日志记录器实例

    Example:
        >>> logger = get_hft_logger('core.engine')
        >>> logger.info("信息")
    """
    return HFTLogger.get_logger(name)


def get_performance_logger(name: str) -> PerformanceLogger:
    """
    获取性能日志记录器（便捷函数）

    Args:
        name (str): 日志记录器名称

    Returns:
        PerformanceLogger: 性能日志记录器实例

    Example:
        >>> perf_logger = get_performance_logger('core.engine')
        >>> perf_logger.log_every(1000, "已处理 1000 个 Tick")
    """
    return PerformanceLogger(name)
