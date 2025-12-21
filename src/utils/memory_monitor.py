#!/usr/bin/env python3
"""
内存监控模块
用于监控和优化系统内存使用
"""
import logging
import psutil
import os
import time
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class MemoryMonitor:
    """内存监控器"""

    def __init__(self, warning_threshold: float = 80.0, critical_threshold: float = 90.0):
        """
        初始化内存监控器

        Args:
            warning_threshold: 内存使用率警告阈值（百分比）
            critical_threshold: 内存使用率严重阈值（百分比）
        """
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.process = psutil.Process(os.getpid())

    def get_memory_info(self) -> Dict[str, Any]:
        """获取当前内存使用信息"""
        try:
            # 系统内存信息
            system_memory = psutil.virtual_memory()

            # 进程内存信息
            process_memory = self.process.memory_info()
            process_memory_percent = self.process.memory_percent()

            return {
                "timestamp": datetime.now().isoformat(),
                "system": {
                    "total": system_memory.total,
                    "available": system_memory.available,
                    "used": system_memory.used,
                    "percent": system_memory.percent
                },
                "process": {
                    "rss": process_memory.rss,  # 物理内存
                    "vms": process_memory.vms,  # 虚拟内存
                    "percent": process_memory_percent
                },
                "status": self._get_memory_status(system_memory.percent)
            }
        except Exception as e:
            logger.error(f"获取内存信息失败: {e}")
            return {"error": str(e)}

    def _get_memory_status(self, memory_percent: float) -> str:
        """根据内存使用率返回状态"""
        if memory_percent >= self.critical_threshold:
            return "CRITICAL"
        elif memory_percent >= self.warning_threshold:
            return "WARNING"
        else:
            return "NORMAL"

    def check_memory_health(self) -> Dict[str, Any]:
        """检查内存健康状态"""
        memory_info = self.get_memory_info()

        if "error" in memory_info:
            return {
                "healthy": False,
                "status": "ERROR",
                "message": f"内存监控错误: {memory_info['error']}"
            }

        system_percent = memory_info["system"]["percent"]
        process_percent = memory_info["process"]["percent"]

        # 检查系统内存
        if system_percent >= self.critical_threshold:
            return {
                "healthy": False,
                "status": "CRITICAL",
                "message": f"系统内存使用率过高: {system_percent:.1f}%",
                "system_percent": system_percent,
                "process_percent": process_percent
            }
        elif system_percent >= self.warning_threshold:
            return {
                "healthy": True,
                "status": "WARNING",
                "message": f"系统内存使用率较高: {system_percent:.1f}%",
                "system_percent": system_percent,
                "process_percent": process_percent
            }

        # 检查进程内存
        if process_percent >= 50:  # 进程内存使用超过50%也警告
            return {
                "healthy": True,
                "status": "WARNING",
                "message": f"进程内存使用率较高: {process_percent:.1f}%",
                "system_percent": system_percent,
                "process_percent": process_percent
            }

        return {
            "healthy": True,
            "status": "NORMAL",
            "message": "内存使用正常",
            "system_percent": system_percent,
            "process_percent": process_percent
        }

    def log_memory_usage(self, context: str = ""):
        """记录内存使用情况"""
        memory_info = self.get_memory_info()

        if "error" not in memory_info:
            system_percent = memory_info["system"]["percent"]
            process_percent = memory_info["process"]["percent"]
            process_mb = memory_info["process"]["rss"] / 1024 / 1024

            logger.info(
                f"内存使用 {context}: "
                f"系统 {system_percent:.1f}%, "
                f"进程 {process_percent:.1f}% ({process_mb:.1f}MB)"
            )

            # 如果内存使用过高，记录警告
            if system_percent >= self.warning_threshold:
                logger.warning(
                    f"系统内存使用率过高 {context}: {system_percent:.1f}% "
                    f"(阈值: {self.warning_threshold}%)"
                )

    def suggest_optimizations(self) -> list:
        """建议内存优化措施"""
        memory_info = self.get_memory_info()

        if "error" in memory_info:
            return ["无法获取内存信息，请检查系统状态"]

        system_percent = memory_info["system"]["percent"]
        suggestions = []

        if system_percent >= self.critical_threshold:
            suggestions.extend([
                "立即释放不必要的内存",
                "考虑重启高内存使用的服务",
                "检查内存泄漏",
                "增加系统内存或优化内存分配"
            ])
        elif system_percent >= self.warning_threshold:
            suggestions.extend([
                "监控内存使用趋势",
                "清理缓存和临时文件",
                "优化数据库连接池大小",
                "考虑调整Docker容器内存限制"
            ])

        process_percent = memory_info["process"]["percent"]
        if process_percent >= 30:
            suggestions.extend([
                "检查当前进程的内存使用模式",
                "优化代码中的内存分配",
                "考虑使用内存分析工具"
            ])

        if not suggestions:
            suggestions.append("内存使用正常，无需特别优化")

        return suggestions

# 全局内存监控器实例
memory_monitor = MemoryMonitor()

def monitor_memory_periodically(interval: int = 300, context: str = ""):
    """
    定期监控内存使用

    Args:
        interval: 监控间隔（秒）
        context: 监控上下文描述
    """
    def monitor_loop():
        while True:
            try:
                memory_monitor.log_memory_usage(context)
                health = memory_monitor.check_memory_health()

                if not health["healthy"]:
                    logger.error(f"内存健康检查失败: {health['message']}")

                    # 记录优化建议
                    suggestions = memory_monitor.suggest_optimizations()
                    for suggestion in suggestions:
                        logger.info(f"内存优化建议: {suggestion}")

                time.sleep(interval)
            except Exception as e:
                logger.error(f"内存监控循环错误: {e}")
                time.sleep(60)  # 出错时等待1分钟再重试

    import threading
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    logger.info(f"启动内存监控线程，间隔 {interval} 秒")

if __name__ == "__main__":
    # 测试内存监控
    logging.basicConfig(level=logging.INFO)

    monitor = MemoryMonitor()

    # 获取内存信息
    info = monitor.get_memory_info()
    logger.info(f"内存信息: {info}")

    # 检查内存健康
    health = monitor.check_memory_health()
    logger.info(f"内存健康: {health}")

    # 获取优化建议
    suggestions = monitor.suggest_optimizations()
    logger.info(f"优化建议: {suggestions}")
