"""
高频交易策略模块 (High Frequency Trading Module)

本模块提供高频交易策略的核心功能，包括：
- 数据流处理（WebSocket）
- 交易执行与风控
- 策略核心逻辑
- 专用工具函数

模块设计原则：
- 完全独立，不破坏现有代码
- 不引入 ccxt 或 pandas 等外部依赖
- 支持异步处理，满足高频交易需求
"""

from .config_loader import load_hft_config

__version__ = "1.0.0"
__all__ = ["load_hft_config"]
