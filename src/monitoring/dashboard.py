"""
Athena Trader 性能监控仪表板
Performance Monitoring Dashboard for Athena Trader
"""

try:
    import psutil
except ImportError:
    psutil = None
    import logging
    logger = logging.getLogger(__name__)
