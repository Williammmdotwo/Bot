"""
Safety Module

安全模块，包含熔断守护进程等安全机制。
"""

from .guardian import Guardian

__all__ = ['Guardian']
