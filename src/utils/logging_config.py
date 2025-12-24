import os
import logging
import logging.config
import logging.handlers
import sys
import json
import requests
import asyncio
import threading
from typing import Optional, Dict, List
from collections import deque
import time


class WebhookErrorHandler(logging.Handler):
    """自定义 Webhook 错误处理器"""

    def __init__(self, webhook_url: Optional[str] = None):
        super().__init__()
        self.webhook_url = webhook_url
        self.session = requests.Session()
        self.session.timeout = 3  # 3秒超时

        # 🔥 强制禁用代理，避免代理连接问题
        self.session.proxies = {
            'http': None,
            'https': None,
        }

        # 防循环机制：记录上次发送时间
        self.last_send_time = 0
        self.min_send_interval = 60  # 最小发送间隔60秒

    def emit(self, record: logging.LogRecord):
        """发送日志记录到 webhook"""
        # 只处理 ERROR 及以上级别
        if record.levelno < logging.ERROR:
            return

        if not self.webhook_url:
            return

        # 🔥 防循环机制：避免webhook错误引发更多webhook调用
        current_time = time.time()
        if current_time - self.last_send_time < self.min_send_interval:
            return  # 跳过频繁发送

        # 🔥 防止处理自己的错误日志
        if 'Webhook 发送' in record.getMessage():
            return  # 跳过webhook相关的错误日志

        try:
            # 格式化日志消息
            log_message = self.format(record)

            # 发送到 webhook
            payload = {
                "message": log_message,
                "level": record.levelname,
                "timestamp": record.created,
                "module": record.name,
                "pathname": record.pathname,
                "lineno": record.lineno
            }

            response = self.session.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=3
            )

            # 更新最后发送时间
            self.last_send_time = current_time

            if response.status_code != 200:
                # 🔥 静默处理，避免循环记录错误
                print(f"Webhook 发送失败: {response.status_code}", file=sys.stderr)

        except Exception as e:
            # 🔥 静默处理，避免循环记录错误
            print(f"Webhook 发送异常: {e}", file=sys.stderr)
            self.last_send_time = current_time

    def close(self):
        """关闭处理器"""
        if hasattr(self, 'session'):
            self.session.close()


def setup_logging():
    """设置日志系统配置"""
    try:
        # 从环境变量获取配置
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        webhook_url = os.getenv('ALERT_WEBHOOK_URL')

        # 🔥 获取日志目录配置
        logs_directory = os.getenv('LOGS_DIRECTORY')
        if logs_directory:
            # 使用自定义日志目录
            log_file = os.path.join(logs_directory, 'app.log')
        else:
            # 使用默认日志目录
            log_file = 'logs/app.log'

        # 确保日志目录存在
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        # 验证日志级别
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if log_level not in valid_levels:
            print(f"无效的日志级别: {log_level}，使用默认 INFO", file=sys.stderr)
            log_level = 'INFO'

        # 创建日志配置字典
        config = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'standard': {
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    'datefmt': '%Y-%m-%d %H:%M:%S'
                }
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'level': log_level,
                    'formatter': 'standard',
                    'stream': sys.stdout
                },
                'rotating_file': {
                    'class': 'logging.handlers.RotatingFileHandler',
                    'level': 'DEBUG',
                    'formatter': 'standard',
                    'filename': log_file,  # 🔥 使用动态路径
                    'maxBytes': 10485760,  # 10MB
                    'backupCount': 5,
                    'encoding': 'utf-8'
                }
            },
            'loggers': {
                '': {  # root logger
                    'level': 'DEBUG',
                    'handlers': ['console', 'rotating_file']
                }
            }
        }

        # 如果有 webhook URL，添加 webhook handler
        if webhook_url:
            config['handlers']['webhook_error'] = {
                '()': WebhookErrorHandler,
                'level': 'ERROR',
                'formatter': 'standard',
                'webhook_url': webhook_url
            }
            config['loggers']['']['handlers'].append('webhook_error')

        # 应用配置
        logging.config.dictConfig(config)

        # 记录配置信息
        setup_logger = logging.getLogger(__name__)
        setup_logger.info("日志系统初始化完成:")
        setup_logger.info(f"  - 日志级别: {log_level}")
        setup_logger.info(f"  - 控制台输出: {'启用' if log_level != 'DEBUG' else '禁用'}")
        setup_logger.info(f"  - 文件输出: {log_file} (轮转，最大10MB，保留5个备份)")
        if webhook_url:
            setup_logger.info(f"  - Webhook 告警: {webhook_url} (ERROR及以上级别)")
        else:
            setup_logger.info("  - Webhook 告警: 禁用")

    except Exception as e:
        # 配置失败时的备用方案
        setup_logger = logging.getLogger(__name__)
        setup_logger.error(f"日志配置失败: {e}")
        setup_logger.warning("使用基本日志配置...")

        # 基本备用配置
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 在基本配置后，使用root logger记录
        basic_logger = logging.getLogger(__name__)
        basic_logger.info("基本日志配置已应用")


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志器"""
    return logging.getLogger(name)


def set_log_level(level: str):
    """动态设置日志级别"""
    try:
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if level.upper() not in valid_levels:
            print(f"无效的日志级别: {level}", file=sys.stderr)
            return False

        # 设置根日志器级别
        logging.getLogger().setLevel(getattr(logging, level.upper()))
        print(f"日志级别已设置为: {level.upper()}")
        return True

    except Exception as e:
        print(f"设置日志级别失败: {e}", file=sys.stderr)
        return False


def add_webhook_handler(webhook_url: str):
    """动态添加 webhook 处理器"""
    try:
        # 创建 webhook handler
        webhook_handler = WebhookErrorHandler(webhook_url)
        webhook_handler.setLevel(logging.ERROR)

        # 获取标准格式器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        webhook_handler.setFormatter(formatter)

        # 添加到根日志器
        root_logger = logging.getLogger()
        root_logger.addHandler(webhook_handler)

        print(f"Webhook 处理器已添加: {webhook_url}")
        return True

    except Exception as e:
        print(f"添加 Webhook 处理器失败: {e}", file=sys.stderr)
        return False


def remove_webhook_handler():
    """移除 webhook 处理器"""
    try:
        root_logger = logging.getLogger()

        # 查找并移除 webhook handler
        for handler in root_logger.handlers[:]:
            if isinstance(handler, WebhookErrorHandler):
                root_logger.removeHandler(handler)
                handler.close()
                print("Webhook 处理器已移除")
                return True

        print("未找到 Webhook 处理器")
        return False

    except Exception as e:
        print(f"移除 Webhook 处理器失败: {e}", file=sys.stderr)
        return False


class StreamingLogReader:
    """流式日志读取器 - 避免一次性读取大量日志导致卡顿"""

    def __init__(self, log_file_path: str = 'logs/app.log', buffer_size: int = 1000):
        self.log_file_path = log_file_path
        self.buffer_size = buffer_size
        self.log_buffer = deque(maxlen=buffer_size)
        self.last_position = 0
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def start_monitoring(self):
        """开始监控日志文件"""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitor_log_file, daemon=True)
        self._thread.start()

    def stop_monitoring(self):
        """停止监控日志文件"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)

    def _monitor_log_file(self):
        """监控日志文件变化"""
        while self._running:
            try:
                if os.path.exists(self.log_file_path):
                    with open(self.log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        f.seek(self.last_position)
                        new_lines = f.readlines()

                        if new_lines:
                            with self._lock:
                                for line in new_lines:
                                    # 只存储ERROR和WARNING级别的日志
                                    if any(level in line for level in ['ERROR', 'CRITICAL', 'WARNING']):
                                        self.log_buffer.append({
                                            'timestamp': time.time(),
                                            'level': self._extract_level(line),
                                            'message': line.strip(),
                                            'raw': line
                                        })

                            self.last_position = f.tell()

                time.sleep(0.1)  # 100ms检查间隔

            except Exception as e:
                print(f"日志监控异常: {e}", file=sys.stderr)
                time.sleep(1)  # 出错时等待1秒

    def _extract_level(self, line: str) -> str:
        """从日志行中提取级别"""
        for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            if level in line:
                return level
        return 'UNKNOWN'

    def get_recent_logs(self, count: int = 100, level_filter: Optional[str] = None) -> List[Dict]:
        """获取最近的日志"""
        with self._lock:
            logs = list(self.log_buffer)

        if level_filter:
            logs = [log for log in logs if log['level'] == level_filter.upper()]

        return logs[-count:] if count > 0 else logs

    def get_error_logs(self, count: int = 50) -> List[Dict]:
        """获取错误日志"""
        return self.get_recent_logs(count, 'ERROR')

    def get_warning_logs(self, count: int = 50) -> List[Dict]:
        """获取警告日志"""
        return self.get_recent_logs(count, 'WARNING')

    def clear_buffer(self):
        """清空缓冲区"""
        with self._lock:
            self.log_buffer.clear()

    def get_buffer_status(self) -> Dict:
        """获取缓冲区状态"""
        with self._lock:
            return {
                'buffer_size': len(self.log_buffer),
                'max_buffer_size': self.buffer_size,
                'last_position': self.last_position,
                'monitoring': self._running
            }


# 全局日志读取器实例
_log_reader: Optional[StreamingLogReader] = None


def get_log_reader() -> StreamingLogReader:
    """获取全局日志读取器实例"""
    global _log_reader
    if _log_reader is None:
        _log_reader = StreamingLogReader()
        _log_reader.start_monitoring()
    return _log_reader


def start_log_monitoring():
    """启动日志监控"""
    reader = get_log_reader()
    reader.start_monitoring()
    print("日志监控已启动")


def stop_log_monitoring():
    """停止日志监控"""
    global _log_reader
    if _log_reader:
        _log_reader.stop_monitoring()
        print("日志监控已停止")


def get_recent_errors(count: int = 50) -> List[Dict]:
    """获取最近的错误日志"""
    reader = get_log_reader()
    return reader.get_error_logs(count)


def get_recent_warnings(count: int = 50) -> List[Dict]:
    """获取最近的警告日志"""
    reader = get_log_reader()
    return reader.get_warning_logs(count)


def test_logging():
    """测试日志系统"""
    logger = get_logger('test')

    logger.debug("这是一条 DEBUG 消息")
    logger.info("这是一条 INFO 消息")
    logger.warning("这是一条 WARNING 消息")
    logger.error("这是一条 ERROR 消息")
    logger.critical("这是一条 CRITICAL 消息")

    print("日志测试完成，请检查控制台、文件和 webhook 输出")


if __name__ == '__main__':
    # 测试日志配置
    setup_logging()
    test_logging()
