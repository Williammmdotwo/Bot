"""
NotificationManager - 非阻塞型全局告警中心

职责：
- 异步发送告警，不阻塞交易循环
- 支持多种 Webhook 接口（钉钉、飞书、Telegram）
- 紧急告警：Engine 崩溃、持仓不一致、WebSocket 断线
- 战报推送：每笔交易后推送格式化战报
- 心跳盘点：每 4 小时发送一次平安报

设计原则：
- 绝对异步：使用 asyncio.create_task 确保不阻塞主循环
- 高可用：发送失败不影响交易
- 可扩展：易于添加新的通知渠道
"""

import asyncio
import aiohttp
import json
import logging
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class AlertLevel:
    """告警级别"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class AlertType:
    """告警类型"""
    ENGINE_CRASH = "engine_crash"          # Engine 崩溃
    POSITION_MISMATCH = "position_mismatch"  # 持仓不一致
    WS_DISCONNECT = "ws_disconnect"           # WebSocket 断线
    ORDER_FILLED = "order_filled"            # 订单成交
    HEARTBEAT = "heartbeat"                # 心跳


@dataclass
class AlertConfig:
    """告警配置"""
    enabled: bool = False                      # 是否启用
    webhook_url: Optional[str] = None         # Webhook URL
    webhook_timeout: float = 5.0               # Webhook 超时时间（秒）
    max_retries: int = 3                      # 最大重试次数
    heartbeat_interval_hours: int = 4         # 心跳间隔（小时）


class NotificationManager:
    """
    通知管理器（非阻塞型全局告警中心）

    核心特性：
    - 绝对异步：使用 asyncio.create_task 发送请求
    - 高可用：发送失败不影响交易
    - 可扩展：支持多种 Webhook 接口

    集成点：
    1. 紧急告警：Engine 崩溃、持仓不一致、WebSocket 断线
    2. 战报推送：订单成交后推送
    3. 心跳盘点：定期发送平安报
    """

    def __init__(self, config: AlertConfig):
        """
        初始化通知管理器

        Args:
            config (AlertConfig): 告警配置
        """
        self.config = config
        self._enabled = config.enabled
        self._webhook_url = config.webhook_url
        self._heartbeat_task = None
        self._start_time = time.time()
        self._last_heartbeat = 0.0

        logger.info(
            f"📢 [NotificationManager] 初始化: "
            f"enabled={self._enabled}, "
            f"webhook={'configured' if self._webhook_url else 'none'}"
        )

    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self._enabled and self._webhook_url is not None

    async def send_alert(
        self,
        alert_type: str,
        level: str,
        title: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        发送告警（非阻塞）

        🔥 关键：使用 asyncio.create_task 确保发送请求不阻塞交易循环

        Args:
            alert_type (str): 告警类型
            level (str): 告警级别（INFO/WARNING/ERROR/CRITICAL）
            title (str): 告警标题
            message (str): 告警内容
            metadata (Optional[Dict]): 附加元数据
        """
        if not self.is_enabled():
            logger.debug(f"📢 [通知跳过] 告警已禁用: {title}")
            return

        # 🔥 [关键] 异步发送，不阻塞主循环
        asyncio.create_task(self._send_alert_async(
            alert_type=alert_type,
            level=level,
            title=title,
            message=message,
            metadata=metadata or {}
        ))

    async def _send_alert_async(
        self,
        alert_type: str,
        level: str,
        title: str,
        message: str,
        metadata: Dict[str, Any]
    ):
        """
        异步发送告警（内部方法）

        Args:
            alert_type (str): 告警类型
            level (str): 告警级别
            title (str): 告警标题
            message (str): 告警内容
            metadata (Dict): 附加元数据
        """
        payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "alert_type": alert_type,
            "level": level,
            "title": title,
            "message": message,
            "metadata": metadata,
            "source": "athena-trader"
        }

        # 尝试发送，最多重试 3 次
        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.config.webhook_timeout)) as session:
                    async with session.post(
                        self._webhook_url,
                        json=payload,
                        headers={"Content-Type": "application/json"}
                    ) as response:
                        if response.status == 200:
                            logger.info(
                                f"✅ [通知成功] [{level}] {title}: {message}"
                            )
                            return
                        else:
                            logger.warning(
                                f"⚠️ [通知失败] [{level}] 状态码={response.status}, "
                                f"重试={attempt}/{self.config.max_retries}"
                            )

            except asyncio.TimeoutError:
                logger.warning(
                    f"⚠️ [通知超时] [{level}] 超时={self.config.webhook_timeout}s, "
                    f"重试={attempt}/{self.config.max_retries}"
                )
            except Exception as e:
                logger.error(
                    f"❌ [通知异常] [{level}] {e}, "
                    f"重试={attempt}/{self.config.max_retries}"
                )

            # 重试前等待
            if attempt < self.config.max_retries:
                await asyncio.sleep(1.0)

        # 最终失败
        logger.error(
            f"❌ [通知失败] [{level}] {title} - 所有重试均失败"
        )

    # ========== 紧急告警 ==========

    async def alert_engine_crash(
        self,
        strategy_id: str,
        error_message: str,
        stack_trace: Optional[str] = None
    ):
        """
        Engine 崩溃告警

        Args:
            strategy_id (str): 策略 ID
            error_message (str): 错误信息
            stack_trace (Optional[str]): 堆栈跟踪
        """
        await self.send_alert(
            alert_type=AlertType.ENGINE_CRASH,
            level=AlertLevel.CRITICAL,
            title=f"🚨 [紧急] Strategy {strategy_id} 崩溃",
            message=error_message,
            metadata={
                "strategy_id": strategy_id,
                "stack_trace": stack_trace,
                "action": "立即检查日志并重启策略"
            }
        )

    async def alert_position_mismatch(
        self,
        strategy_id: str,
        local_position: float,
        remote_position: float,
        diff_pct: float
    ):
        """
        持仓不一致告警

        Args:
            strategy_id (str): 策略 ID
            local_position (float): 本地持仓
            remote_position (float): 远程持仓
            diff_pct (float): 差异百分比
        """
        await self.send_alert(
            alert_type=AlertType.POSITION_MISMATCH,
            level=AlertLevel.ERROR,
            title=f"⚠️ [风控] Strategy {strategy_id} 持仓不一致",
            message=f"本地={local_position}, 远程={remote_position}, 差异={diff_pct:.2%}",
            metadata={
                "strategy_id": strategy_id,
                "local_position": local_position,
                "remote_position": remote_position,
                "diff_pct": diff_pct,
                "action": "检查持仓同步逻辑，可能需要手动修复"
            }
        )

    async def alert_ws_disconnect(
        self,
        symbol: str,
        retry_count: int
    ):
        """
        WebSocket 断线告警

        Args:
            symbol (str): 交易对
            retry_count (int): 重试次数
        """
        await self.send_alert(
            alert_type=AlertType.WS_DISCONNECT,
            level=AlertLevel.WARNING if retry_count < 3 else AlertLevel.ERROR,
            title=f"📡 [网络] {symbol} WebSocket 断线",
            message=f"重连失败 {retry_count} 次",
            metadata={
                "symbol": symbol,
                "retry_count": retry_count,
                "action": "检查网络连接和 API Key 有效性"
            }
        )

    # ========== 战报推送 ==========

    async def report_order_filled(
        self,
        strategy_id: str,
        symbol: str,
        side: str,
        price: float,
        size: float,
        pnl: Optional[float] = None,
        win_rate: Optional[float] = None,
        total_equity: Optional[float] = None
    ):
        """
        订单成交战报推送

        格式：[策略成交] Symbol | 收益率 | 预估盈亏 | 当前总权益

        Args:
            strategy_id (str): 策略 ID
            symbol (str): 交易对
            side (str): 交易方向（buy/sell）
            price (float): 成交价格
            size (float): 成交数量
            pnl (Optional[float]): 盈亏金额
            win_rate (Optional[float]): 收益率
            total_equity (Optional[float]): 当前总权益
        """
        # 格式化盈亏
        pnl_str = f"{pnl:+.2f} USDT" if pnl is not None else "N/A"
        win_rate_str = f"{win_rate:.2%}" if win_rate is not None else "N/A"
        equity_str = f"{total_equity:,.2f} USDT" if total_equity is not None else "N/A"

        title = f"📊 [策略成交] {strategy_id}"
        message = f"Symbol={symbol} | 收益率={win_rate_str} | 盈亏={pnl_str} | 总权益={equity_str}"

        await self.send_alert(
            alert_type=AlertType.ORDER_FILLED,
            level=AlertLevel.INFO,
            title=title,
            message=message,
            metadata={
                "strategy_id": strategy_id,
                "symbol": symbol,
                "side": side,
                "price": price,
                "size": size,
                "pnl": pnl,
                "win_rate": win_rate,
                "total_equity": total_equity
            }
        )

    # ========== 心跳盘点 ==========

    def start_heartbeat(self):
        """
        启动心跳任务

        每 4 小时发送一次平安报
        """
        if not self.is_enabled():
            logger.debug("📢 [心跳] 告警已禁用，跳过启动")
            return

        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info(
            f"💓 [心跳] 已启动，间隔={self.config.heartbeat_interval_hours} 小时"
        )

    async def _heartbeat_loop(self):
        """
        心跳循环

        定期发送平安报，包含：
        - 当前运行时间
        - 处理的 Tick 总量
        - 资金余额
        """
        while True:
            try:
                # 等待心跳间隔
                await asyncio.sleep(self.config.heartbeat_interval_hours * 3600)

                # 发送心跳
                uptime_seconds = time.time() - self._start_time
                uptime_hours = uptime_seconds / 3600

                title = f"💓 [心跳] 系统运行正常"
                message = (
                    f"运行时间={uptime_hours:.1f}h | "
                    f"上次心跳={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}"
                )

                await self.send_alert(
                    alert_type=AlertType.HEARTBEAT,
                    level=AlertLevel.INFO,
                    title=title,
                    message=message,
                    metadata={
                        "uptime_seconds": uptime_seconds,
                        "uptime_hours": uptime_hours,
                        "status": "healthy"
                    }
                )

                self._last_heartbeat = time.time()

            except asyncio.CancelledError:
                logger.info("💓 [心跳] 已停止")
                break
            except Exception as e:
                logger.error(f"❌ [心跳异常] {e}", exc_info=True)

    def stop_heartbeat(self):
        """
        停止心跳任务
        """
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            logger.info("💓 [心跳] 已停止")


# ========== 单例模式 ==========

_notifier_instance: Optional[NotificationManager] = None


def get_notifier() -> Optional[NotificationManager]:
    """
    获取通知管理器单例

    Returns:
        NotificationManager: 通知管理器实例
    """
    global _notifier_instance
    return _notifier_instance


def create_notifier(config: AlertConfig) -> NotificationManager:
    """
    创建通知管理器单例

    Args:
        config (AlertConfig): 告警配置

    Returns:
        NotificationManager: 通知管理器实例
    """
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = NotificationManager(config)
        logger.info("📢 [NotificationManager] 单例已创建")
    return _notifier_instance
