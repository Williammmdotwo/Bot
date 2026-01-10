"""
日志配置模块 (Logging Configuration)

提供统一的日志配置和管理功能。

核心功能：
- 配置根 Logger（所有模块自动继承）
- 控制台输出（强制输出到 Stdout）
- 文件输出（轮转日志）
- 避免重复添加 Handler
- 格式化标准
"""

import os
import sys
import logging
import logging.handlers


def setup_logging(level: str = "INFO"):
    """
    配置根 Logger

    Args:
        level (str): 日志级别（DEBUG/INFO/WARNING/ERROR）
    """
    # 获取根 Logger
    root_logger = logging.getLogger()

    # 清理旧 Handlers（避免重复）
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    # 设置日志级别
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # 创建格式器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 添加控制台 Handler（强制输出到 Stdout）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 添加文件 Handler（可选）
    logs_directory = os.getenv('LOGS_DIRECTORY')
    if logs_directory:
        # 使用自定义日志目录
        log_file = os.path.join(logs_directory, 'app.log')
    else:
        # 使用默认日志目录
        log_file = 'logs/app.log'

    try:
        # 确保日志目录存在
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        # 创建文件 Handler（轮转日志）
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=10485760,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    except Exception as e:
        # 文件 Handler 失败不影响系统运行
        print(f"警告: 无法创建日志文件: {e}", file=sys.stderr)

    # 降低第三方库的日志级别
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('websockets').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('ccxt').setLevel(logging.WARNING)

    # 记录配置信息
    setup_logger = logging.getLogger(__name__)
    setup_logger.info(f"日志系统初始化完成: level={level}")


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的 Logger

    Args:
        name (str): Logger 名称（通常用 __name__）

    Returns:
        logging.Logger: Logger 实例
    """
    return logging.getLogger(name)


def set_log_level(level: str):
    """
    动态设置日志级别

    Args:
        level (str): 日志级别（DEBUG/INFO/WARNING/ERROR）
    """
    try:
        log_level = getattr(logging, level.upper(), logging.INFO)
        logging.getLogger().setLevel(log_level)
        print(f"✅ 日志级别已设置为: {level.upper()}")
    except Exception as e:
        print(f"❌ 设置日志级别失败: {e}", file=sys.stderr)


if __name__ == '__main__':
    # 测试日志配置
    setup_logging(level="INFO")

    test_logger = get_logger('test')
    test_logger.debug("这是一条 DEBUG 消息")
    test_logger.info("这是一条 INFO 消息")
    test_logger.warning("这是一条 WARNING 消息")
    test_logger.error("这是一条 ERROR 消息")
    test_logger.critical("这是一条 CRITICAL 消息")

    print("✅ 日志测试完成")
