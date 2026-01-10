"""
HFT 模块异常定义

本模块定义了 HFT 模块的所有异常类，用于细化和分类错误类型。

设计原则：
- 清晰的异常继承层次
- 详细的错误信息
- 便于上层处理和日志记录
"""


class HFTError(Exception):
    """
    HFT 模块基础异常类

    所有 HFT 模块异常的基类，便于统一捕获和处理。

    Example:
        >>> try:
        ...     # HFT 操作
        ...     pass
        ... except HFTError as e:
        ...     logger.error(f"HFT 错误: {e}")
    """
    pass


class OrderExecutionError(HFTError):
    """
    订单执行异常

    当订单执行失败时抛出，包括：
    - 下单失败
    - 撤单失败
    - 订单状态异常

    Example:
        >>> try:
        ...     await executor.place_ioc_order(...)
        ... except OrderExecutionError as e:
        ...     logger.error(f"订单执行失败: {e}")
        ...     # 重试或记录
    """
    pass


class PositionSyncError(HFTError):
    """
    持仓同步异常

    当持仓同步失败时抛出，包括：
    - WebSocket 持仓推送解析失败
    - REST API 持仓查询失败
    - 持仓数据不一致

    Example:
        >>> try:
        ...     await engine.update_position_state(positions)
        ... except PositionSyncError as e:
        ...     logger.error(f"持仓同步失败: {e}")
        ...     # 强制重新查询 REST API
    """
    pass


class RiskControlError(HFTError):
    """
    风控拒绝异常

    当交易被风控拒绝时抛出，包括：
    - 冷却期内
    - 超过亏损限制
    - 风控检查失败

    Example:
        >>> try:
        ...     if not risk_guard.can_trade():
        ...         raise RiskControlError("风控拒绝交易")
        ... except RiskControlError as e:
        ...     logger.warning(f"风控拒绝: {e}")
    """
    pass


class MarketDataError(HFTError):
    """
    市场数据异常

    当市场数据处理失败时抛出，包括：
    - WebSocket 连接失败
    - 数据解析失败
    - 数据格式错误

    Example:
        >>> try:
        ...     await tick_stream.connect()
        ... except MarketDataError as e:
        ...     logger.error(f"市场数据错误: {e}")
        ...     # 重新连接
    """
    pass


class ConfigurationError(HFTError):
    """
    配置异常

    当配置错误时抛出，包括：
    - 配置文件不存在
    - 配置参数无效
    - 配置格式错误

    Example:
        >>> try:
        ...     config = load_hft_config(config_path)
        ... except ConfigurationError as e:
        ...     logger.error(f"配置错误: {e}")
    """
    pass


class InsufficientBalanceError(OrderExecutionError):
    """
    余额不足异常

    当账户余额不足时抛出，包括：
    - USDT 余额不足
    - 杠杆倍数设置错误
    - 保证金不足

    Example:
        >>> try:
        ...     await executor.place_ioc_order(...)
        ... except InsufficientBalanceError as e:
        ...     logger.warning(f"余额不足: {e}")
        ...     # 调整仓位或充值
    """
    pass


class NetworkError(HFTError):
    """
    网络异常

    当网络请求失败时抛出，包括：
    - 连接超时
    - 网络不可达
    - API 限流

    Example:
        >>> try:
        ...     await rest_client.post_signed(...)
        ... except NetworkError as e:
        ...     logger.error(f"网络错误: {e}")
        ...     # 重试或切换节点
    """
    pass


class AuthenticationError(HFTError):
    """
    认证异常

    当 API 认证失败时抛出，包括：
    - API Key 无效
    - 签名错误
    - 权限不足

    Example:
        >>> try:
        ...     await rest_client.get_signed(...)
        ... except AuthenticationError as e:
        ...     logger.critical(f"认证失败: {e}")
        ...     # 检查 API 配置
    """
    pass
