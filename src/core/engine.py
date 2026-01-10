"""
主引擎 (Main Engine)

Athena OS 的指挥官，负责组装和协调所有组件。

核心职责：
- 初始化所有模块（EventBus, OMS, Gateways, Strategies）
- 启动系统
- 优雅退出

设计原则：
- 依赖注入
- 事件驱动
- 统一的生命周期管理
"""

import asyncio
import signal
import logging
import os
from typing import List, Optional

from .event_bus import EventBus
from .event_types import Event, EventType

from ..oms.capital_commander import CapitalCommander
from ..oms.position_manager import PositionManager
from ..oms.order_manager import OrderManager
from ..risk.pre_trade import PreTradeCheck

from ..gateways.okx.rest_api import OkxRestGateway
from ..gateways.okx.ws_public_gateway import OkxPublicWsGateway
from ..gateways.okx.ws_private_gateway import OkxPrivateWsGateway

from ..strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class Engine:
    """
    主引擎

    Athena OS 的指挥官，负责组装和协调所有组件。

    Example:
        >>> async with Engine(config) as engine:
        ...     await engine.run()
        ...
        >>> # 按 Ctrl+C 优雅退出
    """

    def __init__(self, config: dict):
        """
        初始化引擎

        Args:
            config (dict): 配置字典
        """
        self.config = config

        # 组件容器
        self._event_bus: Optional[EventBus] = None
        self._capital_commander: Optional[CapitalCommander] = None
        self._position_manager: Optional[PositionManager] = None
        self._order_manager: Optional[OrderManager] = None

        # 网关容器
        self._rest_gateway: Optional[OkxRestGateway] = None
        self._public_ws: Optional[OkxPublicWsGateway] = None
        self._private_ws: Optional[OkxPrivateWsGateway] = None

        # 策略容器
        self._strategies: List[BaseStrategy] = []

        # 运行状态
        self._running = False
        self._shutdown_event = asyncio.Event()

        logger.info("Engine 初始化")

    async def initialize(self):
        """
        初始化所有组件

        步骤：
        1. 创建 EventBus
        2. 创建 OMS 组件
        3. 创建 Gateways
        4. 加载 Strategies
        5. 依赖注入
        6. 注册事件处理器
        """
        logger.info("开始初始化组件...")

        # 1. 创建 EventBus
        self._event_bus = EventBus()
        await self._event_bus.start()
        logger.info("✅ EventBus 已启动")

        # 2. 创建 OMS 组件
        total_capital = self.config.get('total_capital', 10000.0)

        self._capital_commander = CapitalCommander(
            total_capital=total_capital,
            event_bus=self._event_bus
        )
        logger.info(f"✅ CapitalCommander 已初始化: {total_capital:.2f} USDT")

        self._position_manager = PositionManager(
            event_bus=self._event_bus,
            sync_threshold_pct=self.config.get('sync_threshold_pct', 0.10),
            cooldown_seconds=self.config.get('sync_cooldown_seconds', 60)
        )
        logger.info("✅ PositionManager 已初始化")

        # 3. 创建 Gateways
        # REST Gateway
        rest_config = self.config.get('rest_gateway', {})
        self._rest_gateway = OkxRestGateway(
            api_key=rest_config.get('api_key', os.getenv('OKX_API_KEY')),
            secret_key=rest_config.get('secret_key', os.getenv('OKX_SECRET_KEY')),
            passphrase=rest_config.get('passphrase', os.getenv('OKX_PASSPHRASE')),
            base_url=rest_config.get('base_url', 'https://www.okx.com'),
            use_demo=rest_config.get('use_demo', True),
            timeout=rest_config.get('timeout', 10),
            event_bus=self._event_bus
        )
        logger.info(f"✅ REST Gateway 已创建: demo={rest_config.get('use_demo', True)}")

        # Public WebSocket
        public_ws_config = self.config.get('public_ws', {})
        self._public_ws = OkxPublicWsGateway(
            symbol=public_ws_config.get('symbol', 'BTC-USDT-SWAP'),
            use_demo=public_ws_config.get('use_demo', True),
            ws_url=public_ws_config.get('ws_url'),
            event_bus=self._event_bus
        )
        logger.info("✅ Public WebSocket 已创建")

        # Private WebSocket
        private_ws_config = self.config.get('private_ws', {})
        self._private_ws = OkxPrivateWsGateway(
            api_key=private_ws_config.get('api_key', os.getenv('OKX_API_KEY')),
            secret_key=private_ws_config.get('secret_key', os.getenv('OKX_SECRET_KEY')),
            passphrase=private_ws_config.get('passphrase', os.getenv('OKX_PASSPHRASE')),
            use_demo=private_ws_config.get('use_demo', True),
            ws_url=private_ws_config.get('ws_url'),
            event_bus=self._event_bus
        )
        logger.info("✅ Private WebSocket 已创建")

        # 4. 创建风控检查器
        risk_config = self.config.get('risk', {})
        self._pre_trade_check = PreTradeCheck(
            max_order_amount=risk_config.get('max_order_amount', 2000.0),
            max_frequency=risk_config.get('max_frequency', 5),
            frequency_window=risk_config.get('frequency_window', 1.0)
        )
        logger.info(
            f"✅ PreTradeCheck 已初始化: "
            f"max_amount={risk_config.get('max_order_amount', 2000.0)} USDT, "
            f"max_frequency={risk_config.get('max_frequency', 5)}/1s"
        )

        # 5. 创建 OrderManager（注入风控检查器）
        self._order_manager = OrderManager(
            rest_gateway=self._rest_gateway,
            event_bus=self._event_bus,
            pre_trade_check=self._pre_trade_check
        )
        logger.info("✅ OrderManager 已初始化（已集成风控）")

        # 6. 加载 Strategies
        strategies_config = self.config.get('strategies', [])
        for strategy_config in strategies_config:
            strategy = await self._load_strategy(strategy_config)
            if strategy:
                self._strategies.append(strategy)
        logger.info(f"✅ 已加载 {len(self._strategies)} 个策略")

        # 7. 注册事件处理器
        await self._register_event_handlers()
        logger.info("✅ 事件处理器已注册")

        # 8. 分配策略资金
        await self._allocate_strategy_capitals()
        logger.info("✅ 策略资金已分配")

        logger.info("✅ 所有组件初始化完成")

    async def _load_strategy(self, strategy_config: dict) -> Optional[BaseStrategy]:
        """
        加载策略

        Args:
            strategy_config (dict): 策略配置

        Returns:
            BaseStrategy: 策略实例
        """
        try:
            strategy_type = strategy_config.get('type')
            params = strategy_config.get('params', {})

            # 根据类型创建策略
            # 显式传入 strategy_id，确保 ID 一致性
            strategy_id = strategy_config.get('id', strategy_type)
            params['strategy_id'] = strategy_id  # 将 strategy_id 添加到参数中

            if strategy_type == 'vulture':
                from ..strategies.hft.vulture import VultureStrategy
                strategy = VultureStrategy(
                    event_bus=self._event_bus,
                    order_manager=self._order_manager,
                    capital_commander=self._capital_commander,
                    **params
                )
            elif strategy_type == 'sniper':
                from ..strategies.hft.sniper import SniperStrategy
                strategy = SniperStrategy(
                    event_bus=self._event_bus,
                    order_manager=self._order_manager,
                    capital_commander=self._capital_commander,
                    **params
                )
            else:
                logger.error(f"未知的策略类型: {strategy_type}")
                return None

            logger.info(
                f"策略已加载: {strategy.strategy_id} ({strategy_type})"
            )

            return strategy

        except Exception as e:
            logger.error(f"加载策略失败: {e}")
            return None

    async def _register_event_handlers(self):
        """注册事件处理器"""
        # 注册 OMS 事件处理器
        self._event_bus.register(
            EventType.ORDER_FILLED,
            self._capital_commander.on_order_filled
        )
        self._event_bus.register(
            EventType.POSITION_UPDATE,
            self._position_manager.update_from_event
        )
        self._event_bus.register(
            EventType.ORDER_FILLED,
            self._position_manager.update_from_event
        )
        self._event_bus.register(
            EventType.ORDER_UPDATE,
            self._order_manager.on_order_update
        )
        self._event_bus.register(
            EventType.ORDER_FILLED,
            self._order_manager.on_order_filled
        )
        self._event_bus.register(
            EventType.ORDER_CANCELLED,
            self._order_manager.on_order_cancelled
        )

    async def _allocate_strategy_capitals(self):
        """为策略分配资金"""
        for strategy in self._strategies:
            strategy_config_list = self.config.get('strategies', [])
            for config in strategy_config_list:
                # 使用 strategy_id 匹配，而不是 class name
                if config.get('id') == strategy.strategy_id:
                    capital = config.get('capital', 1000.0)
                    self._capital_commander.allocate_strategy(
                        strategy.strategy_id,
                        capital
                    )
                    logger.info(
                        f"✅ 策略 {strategy.strategy_id} 已分配资金: {capital:.2f} USDT"
                    )
                    break

    async def start(self):
        """
        启动系统

        步骤：
        1. 连接 Gateways
        2. 启动 Strategies
        3. 进入主循环
        """
        logger.info("启动系统...")

        # 1. 连接 Gateways
        logger.info("连接 Gateways...")

        # REST Gateway
        if not await self._rest_gateway.connect():
            logger.error("REST Gateway 连接失败")
            raise RuntimeError("REST Gateway 连接失败")
        logger.info("✅ REST Gateway 已连接")

        # Public WebSocket
        if not await self._public_ws.connect():
            logger.warning("Public WebSocket 连接失败，重试中...")
            # 继续运行，WebSocket 会自动重连
        else:
            logger.info("✅ Public WebSocket 已连接")

        # Private WebSocket
        if not await self._private_ws.connect():
            logger.warning("Private WebSocket 连接失败，重试中...")
            # 继续运行，WebSocket 会自动重连
        else:
            logger.info("✅ Private WebSocket 已连接")

        # 2. 设置杠杆（为所有策略的交易对设置 10x 杠杆）
        logger.info("设置杠杆...")
        # 获取所有策略使用的交易对
        symbols = set()
        for strategy in self._strategies:
            if hasattr(strategy, 'symbol'):
                symbols.add(strategy.symbol)

        # 设置杠杆
        for symbol in symbols:
            try:
                await self._rest_gateway.set_leverage(symbol, leverage=10)
            except Exception as e:
                logger.warning(f"设置杠杆失败 {symbol}: {e}（继续运行）")

        # 3. 启动 Strategies
        logger.info("启动 Strategies...")
        for strategy in self._strategies:
            await strategy.start()
        logger.info("✅ 所有策略已启动")

        # 4. 设置信号处理
        self._setup_signal_handlers()

        # 5. 进入主循环
        self._running = True
        logger.info("✅ 系统启动完成，进入主循环")

        while self._running:
            await asyncio.sleep(1)

    def _setup_signal_handlers(self):
        """设置信号处理器（优雅退出）"""
        def signal_handler(signum, frame):
            logger.info(f"收到信号 {signum}，准备退出...")
            asyncio.create_task(self.stop())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def stop(self):
        """
        停止系统

        步骤：
        1. 停止 Strategies
        2. 断开 Gateways
        3. 停止 EventBus
        """
        if not self._running:
            return

        logger.info("停止系统...")

        self._running = False
        self._shutdown_event.set()

        # 1. 停止 Strategies
        logger.info("停止 Strategies...")
        for strategy in self._strategies:
            await strategy.stop()
        logger.info("✅ 所有策略已停止")

        # 2. 断开 Gateways
        logger.info("断开 Gateways...")

        if self._public_ws:
            await self._public_ws.disconnect()
            logger.info("✅ Public WebSocket 已断开")

        if self._private_ws:
            await self._private_ws.disconnect()
            logger.info("✅ Private WebSocket 已断开")

        if self._rest_gateway:
            await self._rest_gateway.disconnect()
            logger.info("✅ REST Gateway 已断开")

        # 4. 停止 EventBus
        if self._event_bus:
            await self._event_bus.stop()
            logger.info("✅ EventBus 已停止")

        logger.info("✅ 系统已停止")

    async def run(self):
        """
        运行引擎（入口点）

        步骤：
        1. 初始化
        2. 启动
        3. 等待退出信号
        """
        try:
            # 1. 初始化
            await self.initialize()

            # 2. 启动
            await self.start()

        except Exception as e:
            logger.error(f"引擎运行异常: {e}", exc_info=True)
            await self.stop()
            raise

    def get_status(self) -> dict:
        """
        获取系统状态

        Returns:
            dict: 状态信息
        """
        return {
            'running': self._running,
            'gateways': {
                'rest': self._rest_gateway.is_connected() if self._rest_gateway else False,
                'public_ws': self._public_ws.is_connected() if self._public_ws else False,
                'private_ws': self._private_ws.is_connected() if self._private_ws else False
            },
            'capital': self._capital_commander.get_summary() if self._capital_commander else {},
            'positions': self._position_manager.get_summary() if self._position_manager else {},
            'orders': self._order_manager.get_summary() if self._order_manager else {},
            'strategies': len(self._strategies)
        }

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.stop()


# ======== 辅助函数 ========

def create_default_config() -> dict:
    """
    创建默认配置

    Returns:
        dict: 默认配置
    """
    return {
        'total_capital': 10000.0,
        'sync_threshold_pct': 0.10,
        'sync_cooldown_seconds': 60,
        'rest_gateway': {
            'use_demo': True,
            'timeout': 10
        },
        'public_ws': {
            'symbol': 'BTC-USDT-SWAP',
            'use_demo': True
        },
        'private_ws': {
            'use_demo': True
        },
        'risk': {
            'max_order_amount': 2000.0,
            'max_frequency': 5,
            'frequency_window': 1.0
        },
        'strategies': [
            {
                'id': 'sniper',
                'type': 'sniper',
                'capital': 2000.0,
                'params': {
                    'symbol': 'BTC-USDT-SWAP',
                    'position_size': 0.1,
                    'cooldown_seconds': 5.0,
                    'order_type': 'market',
                    'min_big_order_usdt': 5000.0
                }
            }
        ]
    }


async def main():
    """
    主函数（入口点）
    """
    import sys
    import os

    # 添加项目路径
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 创建引擎
    config = create_default_config()

    async with Engine(config) as engine:
        await engine.run()


if __name__ == '__main__':
    asyncio.run(main())
