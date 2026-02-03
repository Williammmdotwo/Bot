"""
智能熔断守护进程 (Guardian Daemon)

监控系统异常，触发熔断机制，保护资金安全。

核心功能：
- 死循环检测
- 连续报错检测
- 资金雪崩检测
- WebSocket 死亡螺旋检测

设计原则：
- 非侵入式监控
- 快速响应（5秒检查周期）
- 自动熔断保护
- 详细日志记录
"""

import asyncio
import logging
import os
import json
import time
from typing import Dict, List, Optional, Any
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class Guardian:
    """
    智能熔断守护进程

    监控系统异常，触发熔断机制，保护资金安全。

    Example:
        >>> guardian = Guardian(config, engine, capital_commander, rest_gateway, ...)
        >>> await guardian.start()
        >>>
        >>> # 系统会自动监控，异常时触发熔断
        >>> await guardian.stop()
    """

    def __init__(
        self,
        config: dict,
        engine: Any,
        capital_commander: Any,
        rest_gateway: Any,
        event_bus: Any,
        public_ws: Optional[Any] = None,
        private_ws: Optional[Any] = None,
        log_file: Optional[str] = None
    ):
        """
        初始化守护进程

        Args:
            config (dict): 配置字典
            engine: 主引擎实例
            capital_commander: 资金指挥官实例
            rest_gateway: REST Gateway 实例
            event_bus: 事件总线实例
            public_ws: 公共 WebSocket 实例（可选）
            private_ws: 私有 WebSocket 实例（可选）
            log_file: 日志文件路径（可选）
        """
        self.config = config
        self.engine = engine
        self.capital_commander = capital_commander
        self.rest_gateway = rest_gateway
        self.event_bus = event_bus
        self.public_ws = public_ws
        self.private_ws = private_ws
        self.log_file = log_file or 'logs/bot.log'

        # 安全配置
        safety_config = config.get('safety', {})
        self.enabled = safety_config.get('guardian_enabled', True)
        self.check_interval = safety_config.get('check_interval_seconds', 5)

        # 检测阈值
        self.event_loop_threshold = safety_config.get('event_loop_threshold', 10000)
        self.error_log_threshold = safety_config.get('error_log_threshold', 20)
        self.critical_log_threshold = safety_config.get('critical_log_threshold', 5)
        self.equity_drop_threshold_pct = safety_config.get('equity_drop_threshold_pct', 0.10)
        self.ws_reconnect_threshold = safety_config.get('websocket_reconnect_threshold', 30)
        self.auto_close_on_meltdown = safety_config.get('auto_close_on_meltdown', False)

        # 快照保存路径
        self.snapshot_path = safety_config.get('meltdown_snapshot_path', 'data/meltdown_snapshots/')
        Path(self.snapshot_path).mkdir(parents=True, exist_ok=True)

        # 运行状态
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # 监控数据
        self._equity_history: deque = deque(maxlen=120)  # 10分钟窗口（5秒一个点）
        self._last_check_time = time.time()

        # 熔断状态
        self._meltdown_triggered = False
        self._meltdown_reason = None
        self._meltdown_time = None

        logger.info(
            f"🛡️ Guardian 初始化: "
            f"enabled={self.enabled}, "
            f"interval={self.check_interval}s, "
            f"event_threshold={self.event_loop_threshold}, "
            f"equity_drop={self.equity_drop_threshold_pct*100:.1f}%, "
            f"auto_close={self.auto_close_on_meltdown}"
        )

    async def start(self):
        """
        启动守护进程
        """
        if not self.enabled:
            logger.info("🛡️ Guardian 已禁用，跳过启动")
            return

        if self._running:
            logger.warning("Guardian 已在运行")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info(f"🛡️ Guardian 已启动（检查间隔: {self.check_interval}秒）")

    async def stop(self):
        """
        停止守护进程
        """
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("🛡️ Guardian 已停止")

    async def _monitoring_loop(self):
        """
        监控循环（每 5 秒检查一次）
        """
        logger.info("🛡️ Guardian 监控循环已启动")

        while self._running:
            try:
                # 等待检查间隔
                await asyncio.sleep(self.check_interval)

                # 记录当前权益（用于资金雪崩检测）
                self._record_equity()

                # 执行所有检测
                await self._check_all_detections()

            except asyncio.CancelledError:
                logger.info("🛡️ Guardian 监控循环被取消")
                break

            except Exception as e:
                logger.error(f"🛡️ Guardian 监控循环异常: {e}", exc_info=True)
                # 继续运行，不退出

        logger.info("🛡️ Guardian 监控循环已停止")

    def _record_equity(self):
        """
        记录当前权益（用于资金雪崩检测）
        """
        try:
            current_equity = self.capital_commander.get_total_equity()
            self._equity_history.append({
                'timestamp': time.time(),
                'equity': current_equity
            })
        except Exception as e:
            logger.error(f"🛡️ 记录权益失败: {e}")

    async def _check_all_detections(self):
        """
        执行所有检测逻辑

        Returns:
            bool: 是否触发熔断
        """
        # 如果已经触发熔断，不再检测
        if self._meltdown_triggered:
            return True

        # 依次执行检测
        checks = [
            ('死循环检测', self._check_event_loop),
            ('连续报错检测', self._check_error_logs),
            ('资金雪崩检测', self._check_equity_drop),
            ('WebSocket 死亡螺旋检测', self._check_websocket_reconnects),
        ]

        for check_name, check_func in checks:
            try:
                result = await check_func()
                if result:
                    logger.critical(f"🛡️ Guardian 检测到异常: {check_name}")
                    await self._trigger_meltdown(f"🛡️ [{check_name}] {result}")
                    return True
            except Exception as e:
                logger.error(f"🛡️ 执行检测失败 [{check_name}]: {e}", exc_info=True)

        return False

    async def _check_event_loop(self) -> Optional[str]:
        """
        A. 死循环检测

        监控 EventBus._event_stats（需要你在 EventBus 中暴露统计接口）。
        如果任一事件类型在 5 秒内触发超过 10,000 次，判定为死循环。

        Returns:
            Optional[str]: 触发原因，None 表示未触发
        """
        try:
            # 获取事件统计
            stats = self._get_event_stats()

            # 检查每个事件类型
            for event_type, count in stats.items():
                if count > self.event_loop_threshold:
                    message = f"🚨 [死循环] {event_type} 在 5秒内触发 {count} 次"
                    logger.critical(message)
                    return message

            return None

        except Exception as e:
            logger.error(f"🛡️ 死循环检测失败: {e}", exc_info=True)
            return None

    async def _check_error_logs(self) -> Optional[str]:
        """
        B. 连续报错检测

        每 5 秒读取日志文件的最后 1000 行。
        统计 ERROR 和 CRITICAL 级别日志：
        - 如果相同错误消息出现 ≥ 20 次，触发熔断。
        - 如果 CRITICAL 日志 ≥ 5 条，触发熔断。

        Returns:
            Optional[str]: 触发原因，None 表示未触发
        """
        try:
            # 读取日志文件最后 1000 行
            error_lines = self._read_recent_logs(1000, ['ERROR', 'CRITICAL'])

            if not error_lines:
                return None

            # 统计 CRITICAL 日志
            critical_count = sum(1 for line in error_lines if 'CRITICAL' in line)
            if critical_count >= self.critical_log_threshold:
                message = f"🚨 [严重错误] CRITICAL 日志 {critical_count} 条 ≥ {self.critical_log_threshold}"
                logger.critical(message)
                return message

            # 统计相同错误消息
            error_messages = {}
            for line in error_lines:
                if 'ERROR' in line:
                    # 提取错误消息（去掉时间戳和日志级别）
                    # 格式：2026-02-03 18:50:33,385 - module - ERROR - message
                    parts = line.split(' - ', 3)
                    if len(parts) >= 4:
                        error_msg = parts[3].strip()
                        error_messages[error_msg] = error_messages.get(error_msg, 0) + 1

            # 检查是否有重复错误
            for error_msg, count in error_messages.items():
                if count >= self.error_log_threshold:
                    message = f"🚨 [连续报错] 错误消息重复 {count} 次 ≥ {self.error_log_threshold}: {error_msg[:100]}..."
                    logger.critical(message)
                    return message

            return None

        except Exception as e:
            logger.error(f"🛡️ 连续报错检测失败: {e}", exc_info=True)
            return None

    async def _check_equity_drop(self) -> Optional[str]:
        """
        C. 资金雪崩检测

        每 5 秒查询 CapitalCommander.get_total_equity()。
        维护一个 10 分钟的滑动窗口（使用 deque(maxlen=120)，每 5 秒一个点）。
        如果 (current_equity - max_equity_in_window) / max_equity_in_window < -0.10，触发熔断。

        Returns:
            Optional[str]: 触发原因，None 表示未触发
        """
        try:
            if len(self._equity_history) < 2:
                return None

            # 获取当前权益和窗口内最大权益
            current_data = self._equity_history[-1]
            current_equity = current_data['equity']

            max_equity = max(data['equity'] for data in self._equity_history)

            # 计算回撤百分比
            if max_equity > 0:
                drop_pct = (current_equity - max_equity) / max_equity
                if drop_pct < -self.equity_drop_threshold_pct:
                    message = (
                        f"🚨 [资金雪崩] 权益从 {max_equity:.2f} 降至 {current_equity:.2f} "
                        f"({drop_pct*100:.2f}%)，超过阈值 {self.equity_drop_threshold_pct*100:.1f}%"
                    )
                    logger.critical(message)
                    return message

            return None

        except Exception as e:
            logger.error(f"🛡️ 资金雪崩检测失败: {e}", exc_info=True)
            return None

    async def _check_websocket_reconnects(self) -> Optional[str]:
        """
        D. WebSocket 死亡螺旋

        监控 OkxPublicWsGateway 和 OkxPrivateWsGateway 的重连计数器
        （需要在 WS Gateway 中暴露 reconnect_count 属性）。
        如果 5 分钟内重连次数 ≥ 30，触发熔断。

        Returns:
            Optional[str]: 触发原因，None 表示未触发
        """
        try:
            total_reconnects = 0

            # 检查 Public WebSocket
            if self.public_ws:
                reconnects = self._get_ws_reconnect_count(self.public_ws)
                total_reconnects += reconnects
                logger.debug(f"🛡️ Public WebSocket 重连次数: {reconnects}")

            # 检查 Private WebSocket
            if self.private_ws:
                reconnects = self._get_ws_reconnect_count(self.private_ws)
                total_reconnects += reconnects
                logger.debug(f"🛡️ Private WebSocket 重连次数: {reconnects}")

            # 检查是否超过阈值
            if total_reconnects >= self.ws_reconnect_threshold:
                message = (
                    f"🚨 [WebSocket 死亡螺旋] "
                    f"5分钟内重连 {total_reconnects} 次 ≥ {self.ws_reconnect_threshold} 次"
                )
                logger.critical(message)
                return message

            return None

        except Exception as e:
            logger.error(f"🛡️ WebSocket 死亡螺旋检测失败: {e}", exc_info=True)
            return None

    def _read_recent_logs(self, num_lines: int, levels: List[str]) -> List[str]:
        """
        读取日志文件的最近 N 行（只包含指定级别的日志）

        Args:
            num_lines (int): 读取行数
            levels (List[str]): 日志级别列表，例如 ['ERROR', 'CRITICAL']

        Returns:
            List[str]: 日志行列表
        """
        try:
            if not os.path.exists(self.log_file):
                return []

            lines = []
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                # 读取最后 num_lines 行
                all_lines = f.readlines()
                recent_lines = all_lines[-num_lines:] if len(all_lines) > num_lines else all_lines

                # 过滤指定级别的日志
                for line in recent_lines:
                    if any(level in line for level in levels):
                        lines.append(line.strip())

            return lines

        except Exception as e:
            logger.error(f"读取日志文件失败: {e}")
            return []

    def _get_event_stats(self) -> Dict[str, int]:
        """
        获取事件统计（从 EventBus）

        Returns:
            Dict[str, int]: 事件类型 -> 触发次数
        """
        try:
            # 尝试获取事件统计
            if hasattr(self.event_bus, 'get_event_stats'):
                return self.event_bus.get_event_stats()
            else:
                # 如果没有 get_event_stats 方法，使用 published 统计
                stats = self.event_bus.get_stats()
                return {'all_events': stats['published']}

        except Exception as e:
            logger.error(f"获取事件统计失败: {e}")
            return {}

    def _get_ws_reconnect_count(self, ws_gateway: Any) -> int:
        """
        获取 WebSocket 重连次数

        Args:
            ws_gateway: WebSocket Gateway 实例

        Returns:
            int: 重连次数
        """
        try:
            # 尝试不同的属性名
            if hasattr(ws_gateway, 'reconnect_count'):
                return ws_gateway.reconnect_count
            elif hasattr(ws_gateway, '_reconnect_attempt'):
                return ws_gateway._reconnect_attempt
            elif hasattr(ws_gateway, 'get_status'):
                status = ws_gateway.get_status()
                return status.get('reconnect_attempt', 0)
            else:
                return 0

        except Exception as e:
            logger.error(f"获取 WebSocket 重连次数失败: {e}")
            return 0

    async def _trigger_meltdown(self, reason: str):
        """
        触发熔断

        当任一检测触发时：
        1. 调用 notifier.send_alert(level='CRITICAL', message=...)。
        2. 调用 engine.disable_all_strategies()（需要你在 Engine 中实现此方法）。
        3. 调用 rest_gateway.cancel_all_orders()。
        4. 不调用 close_all_positions()（因为 auto_close_on_meltdown=false）。
        5. 保存快照到 data/meltdown_snapshots/snapshot_{timestamp}.json。

        Args:
            reason (str): 触发原因
        """
        logger.critical(f"🚨🚨🚨 熔断触发！🚨🚨🚨")
        logger.critical(f"原因: {reason}")

        # 标记熔断状态
        self._meltdown_triggered = True
        self._meltdown_reason = reason
        self._meltdown_time = datetime.now()

        try:
            # 1. 发送告警（如果有 notifier）
            if hasattr(self.engine, 'notifier'):
                await self.engine.notifier.send_alert(
                    level='CRITICAL',
                    message=f"🚨 熔断触发！{reason}"
                )
                logger.info("🛡️ 告警已发送")
            else:
                logger.warning("🛡️ 未找到 notifier，跳过告警")

            # 2. 禁用所有策略
            if hasattr(self.engine, 'disable_all_strategies'):
                await self.engine.disable_all_strategies()
                logger.info("🛡️ 所有策略已禁用")
            else:
                logger.error("🛡️ Engine 缺少 disable_all_strategies() 方法")
                # 尝试手动停止策略
                for strategy in getattr(self.engine, '_strategies', []):
                    try:
                        await strategy.stop()
                        logger.info(f"🛡️ 策略 {strategy.strategy_id} 已停止")
                    except Exception as e:
                        logger.error(f"停止策略失败: {e}")

            # 3. 取消所有订单
            if self.rest_gateway:
                try:
                    cancelled_count = await self.rest_gateway.cancel_all_orders()
                    logger.info(f"🛡️ 已取消 {cancelled_count} 个订单")
                except Exception as e:
                    logger.error(f"🛡️ 取消订单失败: {e}", exc_info=True)
            else:
                logger.error("🛡️ 未找到 rest_gateway，无法取消订单")

            # 4. 不平仓（auto_close_on_meltdown=false）
            logger.info(f"🛡️ auto_close_on_meltdown={self.auto_close_on_meltdown}，不平仓")

            # 5. 保存快照
            await self._save_snapshot(reason)

            logger.critical("🚨🚨🚨 熔断执行完成！🚨🚨🚨")

        except Exception as e:
            logger.critical(f"🛡️ 熔断执行失败: {e}", exc_info=True)

    async def _save_snapshot(self, reason: str):
        """
        保存熔断快照

        包含：
        - 触发原因
        - 当前持仓
        - 活动订单
        - 最近 100 条日志
        - 资金余额

        Args:
            reason (str): 触发原因
        """
        try:
            snapshot = {
                'timestamp': datetime.now().isoformat(),
                'trigger_reason': reason,
                'meltdown_time': self._meltdown_time.isoformat() if self._meltdown_time else None,
            }

            # 1. 资金余额
            try:
                snapshot['capital'] = self.capital_commander.get_summary()
                snapshot['total_equity'] = self.capital_commander.get_total_equity()
            except Exception as e:
                logger.error(f"获取资金信息失败: {e}")
                snapshot['capital'] = {}

            # 2. 当前持仓
            try:
                position_manager = getattr(self.engine, '_position_manager', None)
                if position_manager:
                    snapshot['positions'] = position_manager.get_all_positions()
                else:
                    snapshot['positions'] = []
            except Exception as e:
                logger.error(f"获取持仓信息失败: {e}")
                snapshot['positions'] = []

            # 3. 活动订单
            try:
                order_manager = getattr(self.engine, '_order_manager', None)
                if order_manager:
                    snapshot['orders'] = order_manager.get_all_orders()
                else:
                    snapshot['orders'] = []
            except Exception as e:
                logger.error(f"获取订单信息失败: {e}")
                snapshot['orders'] = []

            # 4. 最近 100 条日志
            try:
                snapshot['recent_logs'] = self._read_recent_logs(100, ['INFO', 'WARNING', 'ERROR', 'CRITICAL'])
            except Exception as e:
                logger.error(f"获取日志失败: {e}")
                snapshot['recent_logs'] = []

            # 5. 保存到文件
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"snapshot_{timestamp}.json"
            filepath = os.path.join(self.snapshot_path, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)

            logger.info(f"🛡️ 熔断快照已保存: {filepath}")

        except Exception as e:
            logger.critical(f"🛡️ 保存快照失败: {e}", exc_info=True)

    def is_meltdown_triggered(self) -> bool:
        """
        检查是否已触发熔断

        Returns:
            bool: 是否已触发熔断
        """
        return self._meltdown_triggered

    def get_meltdown_info(self) -> Optional[Dict[str, Any]]:
        """
        获取熔断信息

        Returns:
            Optional[Dict]: 熔断信息，None 表示未触发
        """
        if not self._meltdown_triggered:
            return None

        return {
            'triggered': True,
            'reason': self._meltdown_reason,
            'time': self._meltdown_time.isoformat() if self._meltdown_time else None,
        }
