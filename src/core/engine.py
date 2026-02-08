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
from ..market.market_data_manager import MarketDataManager
from ..persistence.persistence_adapter import JsonPersistenceAdapter

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

        # 市场数据管理器
        self._market_data_manager: Optional[MarketDataManager] = None

        # 🔥 [新增] 持久化适配器
        self._persistence: Optional[JsonPersistenceAdapter] = None

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

        # 🔧 支持自定义风控配置
        from ..config.risk_config import RiskConfig, DEFAULT_RISK_CONFIG
        risk_config_dict = self.config.get('risk', {})

        if risk_config_dict:
            # 如果配置中有自定义参数，创建自定义 RiskConfig
            custom_risk_config = RiskConfig(
                RISK_PER_TRADE_PCT=risk_config_dict.get('RISK_PER_TRADE_PCT', DEFAULT_RISK_CONFIG.RISK_PER_TRADE_PCT)
            )
            self._capital_commander = CapitalCommander(
                total_capital=total_capital,
                event_bus=self._event_bus,
                risk_config=custom_risk_config
            )
            logger.info(f"✅ CapitalCommander 已初始化: {total_capital:.2f} USDT (自定义风控)")
        else:
            # 使用默认风控配置
            self._capital_commander = CapitalCommander(
                total_capital=total_capital,
                event_bus=self._event_bus
            )
            logger.info(f"✅ CapitalCommander 已初始化: {total_capital:.2f} USDT (默认风控)")

        # 注意：OrderManager 还未创建，需要在后面设置
        self._position_manager = PositionManager(
            event_bus=self._event_bus,
            order_manager=None,  # 暂时设为 None，后面设置
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

        # 5. 创建 OrderManager（注入风控检查器和资金指挥官）
        self._order_manager = OrderManager(
            rest_gateway=self._rest_gateway,
            event_bus=self._event_bus,
            pre_trade_check=self._pre_trade_check,
            capital_commander=self._capital_commander  # 🔧 修复：传入资金指挥官
        )
        logger.info("✅ OrderManager 已初始化（已集成风控和资金检查）")

        # 将 OrderManager 设置到 PositionManager（用于幽灵单防护）
        self._position_manager._order_manager = self._order_manager
        logger.debug("✅ PositionManager 已关联 OrderManager（幽灵单防护已启用）")

        # 🔥 [关键修复] 6. 创建市场数据管理器（必须在策略加载之前）
        self._market_data_manager = MarketDataManager(event_bus=self._event_bus)
        logger.info("✅ MarketDataManager 已初始化")

        # 7. 加载 Strategies（现在可以安全注入 MarketDataManager）
        strategies_config = self.config.get('strategies', [])
        for strategy_config in strategies_config:
            strategy = await self._load_strategy(strategy_config)
            if strategy:
                self._strategies.append(strategy)
        logger.info(f"✅ 已加载 {len(self._strategies)} 个策略")

        # 8. 注册事件处理器
        await self._register_event_handlers()
        logger.info("✅ 事件处理器已注册")

        # 9. 🔥 [新增] 创建持久化适配器
        persistence_config = self.config.get('persistence', {})
        persistence_type = persistence_config.get('type', 'json')

        if persistence_type == 'json':
            storage_path = persistence_config.get('storage_path', 'data/state.json')
            self._persistence = JsonPersistenceAdapter(storage_path)
            logger.info(f"✅ PersistenceAdapter 已初始化: {storage_path}")
        else:
            logger.warning(f"⚠️ 未知的持久化类型: {persistence_type}，使用内存模式")

        # 10. 动态加载交易对信息（补丁三）
        await self._load_instruments()
        logger.info("✅ 交易对信息已加载")

        # 11. 分配策略资金
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

            if strategy_type == 'scalper_v2':
                from ..strategies.hft.scalper_v2 import ScalperV2
                strategy = ScalperV2(
                    event_bus=self._event_bus,
                    order_manager=self._order_manager,
                    capital_commander=self._capital_commander,
                    **params
                )
            else:
                logger.error(f"未知的策略类型: {strategy_type}")
                return None

            # [修复] 注入 PositionManager（支持自动全平）
            strategy.set_position_manager(self._position_manager)

            # ✨ 新增：注入市场数据管理器（统一数据源）
            if hasattr(strategy, 'set_market_data_manager'):
                strategy.set_market_data_manager(self._market_data_manager)
                logger.debug(f"MarketDataManager 已注入到策略: {strategy.strategy_id}")

            # 🔥 [新增] 注入持久化适配器到 StateManager
            if self._persistence and hasattr(strategy, 'state_manager'):
                # 重新创建 StateManager 并注入持久化适配器
                from ..strategies.hft.components.state_manager import StateManager
                symbol = strategy.symbol if hasattr(strategy, 'symbol') else 'UNKNOWN'
                old_state_manager = strategy.state_manager
                strategy.state_manager = StateManager(symbol=symbol, persistence=self._persistence)
                logger.debug(f"✅ PersistenceAdapter 已注入到策略 {strategy.strategy_id} 的 StateManager")

            logger.info(
                f"策略已加载: {strategy.strategy_id} ({strategy_type})"
            )

            return strategy

        except Exception as e:
            logger.error(f"加载策略失败: {e}", exc_info=True)
            return None

    async def _register_event_handlers(self):
        """注册事件处理器"""
        # 1. 注册 OMS 事件处理器
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

        # 2. ✨ 关键修复：注册策略的事件处理器
        if not self._strategies:
            logger.warning("没有加载任何策略，跳过策略事件注册")
            return

        for strategy in self._strategies:
            # 注册行情事件 (驱动策略核心逻辑)
            self._event_bus.register(EventType.TICK, strategy.on_tick)

            # 注册成交事件 (驱动持仓更新和挂单管理)
            # 注意：BaseStrategy 通常已经实现了 on_order_filled
            if hasattr(strategy, 'on_order_filled'):
                self._event_bus.register(EventType.ORDER_FILLED, strategy.on_order_filled)

            # 注册取消事件 (解锁开仓锁)
            # 注意：BaseStrategy 已经实现了 on_order_cancelled
            if hasattr(strategy, 'on_order_cancelled'):
                self._event_bus.register(EventType.ORDER_CANCELLED, strategy.on_order_cancelled)

            # 🔥 [修复] 注册订单提交事件（可选回调）
            if hasattr(strategy, 'on_order_submitted'):
                self._event_bus.register(EventType.ORDER_SUBMITTED, strategy.on_order_submitted)
                logger.debug(f"✅ 策略 {strategy.strategy_id} 已注册 on_order_submitted 事件处理器")

            # 🔥 [修复] 注册通用事件处理器（用于监听BOOK_EVENT）
            if hasattr(strategy, 'on_event'):
                self._event_bus.register(EventType.BOOK_EVENT, strategy.on_event)
                logger.debug(f"✅ 策略 {strategy.strategy_id} 已注册 on_event 事件处理器 (BOOK_EVENT)")

            logger.info(
                f"✅ 策略 {strategy.strategy_id} 已注册监听 "
                f"TICK, ORDER_FILLED, ORDER_CANCELLED, ORDER_SUBMITTED 和 BOOK_EVENT"
            )

        # 3. 🔥 [修复58] 注册 OrderBook 事件监听器（修复 PositionSizer 获取空订单簿问题）
        if self._public_ws and hasattr(self._public_ws, 'on_book_update'):
            self._event_bus.register(EventType.BOOK_EVENT, self._public_ws.on_book_update)
            logger.info("✅ Public WebSocket 已注册监听 BOOK_EVENT（更新 OrderBook 缓存）")

    async def _load_instruments(self):
        """
        动态加载交易对信息（补丁三）

        从交易所拉取所有交易对配置，自动注册到 CapitalCommander。
        避免手动维护交易对配置，支持交易所动态调整。
        """
        try:
            logger.info("动态加载交易对信息...")

            # 从 Gateway 拉取所有 SWAP（永续合约）交易对
            instruments = await self._rest_gateway.get_instruments(inst_type="SWAP")

            if not instruments:
                logger.warning("未获取到交易对信息，跳过注册")
                return

            # 获取策略使用的交易对列表
            strategy_symbols = set()
            for strategy in self._strategies:
                if hasattr(strategy, 'symbol'):
                    strategy_symbols.add(strategy.symbol)

            # 只注册策略使用的交易对（避免注册几千个无用的）
            registered_count = 0
            for inst in instruments:
                symbol = inst.get('instId', '')

                # 只注册策略使用的交易对
                if symbol in strategy_symbols:
                    lot_size = inst.get('lotSz', 0)
                    min_order_size = inst.get('minSz', 0)
                    # min_notional 通常是 10 USDT（OKX 默认）
                    min_notional = 10.0
                    # 🔥 [修复] 获取合约面值（ctVal）
                    ct_val = inst.get('ctVal', 1.0)
                    # 🔥 [Fix 41] 获取 tick_size
                    tick_size = inst.get('tickSz', 0.01)

                    self._capital_commander.register_instrument(
                        symbol=symbol,
                        lot_size=lot_size,
                        min_order_size=min_order_size,
                        min_notional=min_notional,
                        ct_val=ct_val,  # 🔥 [修复] 传递合约面值
                        tick_size=tick_size  # 🔥 [Fix 41] 传递 tick_size
                    )
                    registered_count += 1

                    logger.info(
                        f"✅ 交易对已注册: {symbol} "
                        f"lot_size={lot_size}, min_order_size={min_order_size}, "
                        f"min_notional={min_notional:.2f} USDT, "
                        f"ctVal={ct_val}, "  # 🔥 [修复] 显示合约面值
                        f"tickSize={tick_size}"  # � [Fix 41] 显示 tick_size
                    )

            logger.info(
                f"✅ 交易对信息加载完成: 共注册 {registered_count} 个交易对"
            )

        except Exception as e:
            logger.error(f"加载交易对信息失败: {e}", exc_info=True)
            # 不阻塞系统启动，继续运行
            logger.warning("交易对信息加载失败，继续运行...")

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
        1. 连接 REST Gateway
        2. 设置杠杆
        3. 清理遗留订单（在连接 WebSocket 之前）
        4. 连接 WebSocket（此时才开始接收市场数据）
        5. 启动 Strategies
        6. 进入主循环
        """
        logger.info("启动系统...")

        # 1. 连接 REST Gateway
        logger.info("连接 Gateways...")
        if not await self._rest_gateway.connect():
            logger.error("REST Gateway 连接失败")
            raise RuntimeError("REST Gateway 连接失败")
        logger.info("✅ REST Gateway 已连接")

        # 2. 设置杠杆（优先从策略配置中读取）
        logger.info("设置杠杆...")

        # 获取所有策略使用的交易对
        symbols = set()
        for strategy in self._strategies:
            if hasattr(strategy, 'symbol'):
                symbols.add(strategy.symbol)

        # 确定目标杠杆（默认 10x）
        target_leverage = 10

        # 尝试从配置中获取第一个策略的杠杆设置
        strategies_config = self.config.get('strategies', [])
        if strategies_config:
            first_strategy = strategies_config[0]
            # 尝试获取 params.leverage
            target_leverage = first_strategy.get('params', {}).get('leverage', 10)
            logger.info(f"📊 从策略配置读取杠杆: {target_leverage}x")
        else:
            logger.info(f"📊 使用默认杠杆: {target_leverage}x")

        # 设置杠杆
        for symbol in symbols:
            try:
                await self._rest_gateway.set_leverage(symbol, leverage=int(target_leverage))
                logger.info(f"✅ 杠杆设置成功: {symbol} = {target_leverage}x")
            except Exception as e:
                logger.warning(f"设置杠杆失败 {symbol}: {e}（继续运行）")

        # 3. 🧹 清理遗留订单（在连接 WebSocket 之前）
        # 🔥 关键：在 WebSocket 连接之前清理，避免误杀策略的新订单
        logger.info("🧹 清理遗留订单...")
        try:
            cancelled_count = await self._order_manager.cancel_all_orders()
            logger.info(f"✅ 启动清理完成: 已取消 {cancelled_count} 个遗留订单")
        except Exception as e:
            logger.error(f"❌ 启动清理失败: {e}", exc_info=True)
            logger.warning("继续启动，但请注意可能有遗留订单")

        # 4. 连接 WebSocket（此时才开始接收市场数据）
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

        # 5. 启动 Strategies
        logger.info("启动 Strategies...")
        for strategy in self._strategies:
            await strategy.start()

            # 🔥 [修复] 初始化持久化状态（在策略启动后，事件循环已运行）
            if hasattr(strategy, 'state_manager') and hasattr(strategy.state_manager, 'initialize_persistence'):
                await strategy.state_manager.initialize_persistence()

        logger.info("✅ 所有策略已启动")

        # ✅ [关键] 启动 OMS 定时持仓同步（修复幽灵持仓问题）
        sync_interval = self.config.get('position_sync_interval', 30)
        self._position_manager.start_scheduled_sync(interval=sync_interval)
        logger.info(f"✅ 定时持仓同步已启动，间隔: {sync_interval}秒")

        # 🔥 [新增] 原子对账：启动时验证本地订单状态
        await self._reconcile_with_exchange()

        # 5. 设置信号处理
        self._setup_signal_handlers()

        # 5. 进入主循环
        self._running = True
        logger.info("✅ 系统启动完成，进入主循环")

        while self._running:
            await asyncio.sleep(1)

    def _setup_signal_handlers(self):
        """设置信号处理器（优雅退出）"""
        def signal_handler(signum, frame):
            import signal as signal_module
            signal_name = signal_module.Signals(signum).name
            logger.info(f"📡 收到信号 {signum} ({signal_name})，准备退出...")
            # 只有在明确按下 Ctrl+C 时才退出
            if signum == signal_module.SIGINT:
                asyncio.create_task(self.stop())
            else:
                logger.warning(f"⚠️ 收到非预期信号 {signum} ({signal_name})，忽略...")

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def stop(self):
        """
        停止系统

        步骤：
        1. 停止 Strategies
        2. 停止 PositionManager 同步任务
        3. 断开 REST Gateway（关键修复）
        4. 断开 WebSocket 连接
        5. 停止 EventBus
        6. 等待所有异步任务完成（关键）
        """
        if not self._running:
            return

        logger.info("🛑 正在停止系统...")

        self._running = False
        self._shutdown_event.set()

        # 1. 停止 Strategies
        logger.info("停止 Strategies...")
        for strategy in self._strategies:
            await strategy.stop()
        logger.info("✅ 所有策略已停止")

        # 2. 停止 PositionManager 同步任务（PositionManager 会自动处理任务取消）
        logger.info("停止 PositionManager 同步任务...")
        logger.info("✅ PositionManager 同步任务将在停止时自动取消")

        # 3. 🔥 关闭 REST Gateway（关键修复）
        logger.info("关闭 REST Gateway...")
        if hasattr(self, '_rest_gateway') and self._rest_gateway:
            await self._rest_gateway.disconnect()
            logger.info("✅ REST Gateway 已断开")

        # 4. 关闭 WebSocket 连接
        logger.info("断开 WebSocket 连接...")
        if hasattr(self, '_public_ws') and self._public_ws:
            await self._public_ws.disconnect()
            logger.info("✅ Public WebSocket 已断开")

        if hasattr(self, '_private_ws') and self._private_ws:
            await self._private_ws.disconnect()
            logger.info("✅ Private WebSocket 已断开")

        # 5. 停止 EventBus
        logger.info("停止 EventBus...")
        if hasattr(self, '_event_bus') and self._event_bus:
            await self._event_bus.stop()
            logger.info("✅ EventBus 已停止")

        # 6. 🔥 等待所有异步任务完成（关键）
        logger.info("等待所有异步任务完成...")
        await asyncio.sleep(0.5)

        logger.info("✅ 系统已停止")

    async def disable_all_strategies(self):
        """
        🔥 [Guardian] 禁用所有策略（熔断时调用）

        立即停止所有策略，不再发送新订单。
        此方法用于 Guardian 熔断机制，与 stop() 的区别是：
        - stop() 会关闭整个系统
        - disable_all_strategies() 只停止策略，保持系统运行以便后续处理

        执行步骤：
        1. 遍历所有策略，调用 strategy.stop()
        2. 标记策略为已禁用状态
        3. 记录日志
        """
        logger.critical("🛡️ [熔断] 开始禁用所有策略...")

        disabled_count = 0
        for strategy in self._strategies:
            try:
                # 停止策略
                await strategy.stop()
                disabled_count += 1

                logger.warning(f"🛡️ [熔断] 策略 {strategy.strategy_id} 已禁用")

                # 可选：标记策略为永久禁用（重启前不恢复）
                if hasattr(strategy, '_disabled'):
                    strategy._disabled = True

            except Exception as e:
                logger.error(
                    f"🛡️ [熔断] 禁用策略 {strategy.strategy_id} 失败: {e}",
                    exc_info=True
                )

        logger.critical(f"🛡️ [熔断] 已禁用 {disabled_count}/{len(self._strategies)} 个策略")

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

    async def _reconcile_with_exchange(self):
        """
        🔥 [新增] 原子对账：启动时立即查询活动订单

        确保本地保存的 maker_order_id 在交易所仍然有效
        """
        logger.info("🔄 [Engine] 开始原子对账...")

        try:
            # 查询所有活动订单
            active_orders = await self._rest_gateway.fetch_active_orders()

            # 对每个策略进行对账
            for strategy in self._strategies:
                if not hasattr(strategy, 'state_manager'):
                    continue

                state_manager = strategy.state_manager
                local_order_id = state_manager.get_maker_order_id()

                if local_order_id and local_order_id != "pending":
                    # 检查本地订单是否在交易所活动中
                    is_active = any(
                        order.get('ordId') == local_order_id
                        for order in active_orders
                        if order.get('state') == 'live'
                    )

                    if not is_active:
                        logger.warning(
                            f"⚠️ [Engine] 策略 {strategy.symbol} 的本地订单 {local_order_id} "
                            f"不在交易所活动中，自动清理"
                        )
                        state_manager.clear_maker_order()
                    else:
                        logger.info(
                            f"✅ [Engine] 策略 {strategy.symbol} 的订单 {local_order_id} "
                            f"确认有效"
                        )

            logger.info("✅ [Engine] 原子对账完成")

        except Exception as e:
            logger.error(f"❌ [Engine] 原子对账失败: {e}")
            # 不阻塞启动，继续运行

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
        'strategies': []  # 空列表，由 main.py 根据环境变量动态加载
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
