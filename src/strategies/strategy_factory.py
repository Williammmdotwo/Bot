"""
StrategyFactory - 策略工厂模式

职责：
- 使用注册模式管理所有策略
- 提供统一的策略创建接口
- 支持动态加载和实例化策略

设计原则：
- 开闭原则：新增策略无需修改工厂代码
- 依赖注入：策略通过装饰器自动注册
- 类型安全：使用类型注解确保策略类型正确
"""

from typing import Dict, Type, Optional, Any
import logging

from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class StrategyFactory:
    """
    策略工厂（注册模式）

    使用装饰器模式，所有策略类通过 @StrategyFactory.register() 装饰器注册。

    特性：
    - 自动注册：策略类通过装饰器自动注册到工厂
    - 动态创建：运行时根据名称创建策略实例
    - 类型检查：确保注册的是 BaseStrategy 的子类
    - 列表查询：可以查询所有已注册的策略

    使用示例：
        >>> # 策略类定义
        >>> @StrategyFactory.register("scalper_v2")
        >>> class ScalperV2(BaseStrategy):
        >>>     pass
        >>>
        >>> # 创建策略实例
        >>> strategy = StrategyFactory.create(
        ...     strategy_type="scalper_v2",
        ...     event_bus=event_bus,
        ...     symbol="DOGE-USDT-SWAP",
        ...     capital=10000.0
        ... )
        >>>
        >>> # 查询所有策略
        >>> strategies = StrategyFactory.list_strategies()
        >>> print(strategies)  # ['scalper_v2', ...]
    """

    # 策略注册表：{策略名称: 策略类}
    _registry: Dict[str, Type[BaseStrategy]] = {}

    @classmethod
    def register(cls, name: str):
        """
        策略注册装饰器

        Args:
            name: 策略名称（唯一标识符）

        Returns:
            装饰器函数

        使用示例：
            >>> @StrategyFactory.register("scalper_v2")
            >>> class ScalperV2(BaseStrategy):
            >>>     pass
        """
        def decorator(strategy_class: Type[BaseStrategy]):
            """
            内部装饰器函数

            Args:
                strategy_class: 策略类

            Returns:
                策略类（未修改）
            """
            # 类型检查：确保是 BaseStrategy 的子类
            if not issubclass(strategy_class, BaseStrategy):
                raise TypeError(
                    f"策略 {name} 必须继承自 BaseStrategy"
                )

            # 检查是否已注册
            if name in cls._registry:
                logger.warning(
                    f"策略 {name} 已被 {cls._registry[name].__name__} 注册，"
                    f"将被 {strategy_class.__name__} 覆盖"
                )

            # 注册策略
            cls._registry[name] = strategy_class
            logger.info(
                f"✅ 策略已注册: {name} -> {strategy_class.__name__}"
            )

            return strategy_class

        return decorator

    @classmethod
    def create(
        cls,
        strategy_type: str,
        **kwargs
    ) -> BaseStrategy:
        """
        创建策略实例

        Args:
            strategy_type: 策略名称（必须已注册）
            **kwargs: 传递给策略 __init__ 的参数
                常用参数：
                - event_bus: EventBus 实例
                - order_manager: OrderManager 实例
                - capital_commander: CapitalCommander 实例
                - position_manager: PositionManager 实例
                - symbol: 交易对符号
                - mode: 运行模式（PRODUCTION/PAPER/BACKTEST）
                - strategy_id: 策略 ID
                - cooldown_seconds: 冷却时间

        Returns:
            BaseStrategy: 策略实例

        Raises:
            ValueError: 策略未注册
            Exception: 策略实例化失败

        使用示例：
            >>> strategy = StrategyFactory.create(
            ...     strategy_type="scalper_v2",
            ...     event_bus=event_bus,
            ...     order_manager=order_manager,
            ...     capital_commander=capital_commander,
            ...     position_manager=position_manager,
            ...     symbol="DOGE-USDT-SWAP",
            ...     mode="PRODUCTION"
            ... )
        """
        # 检查策略是否已注册
        if strategy_type not in cls._registry:
            available = ", ".join(cls._registry.keys())
            raise ValueError(
                f"未注册的策略类型: {strategy_type}\n"
                f"可用类型: [{available}]"
            )

        # 获取策略类
        strategy_class = cls._registry[strategy_type]

        try:
            # 创建策略实例
            strategy = strategy_class(**kwargs)
            logger.info(
                f"✅ 策略实例创建成功: {strategy_type} "
                f"(class={strategy_class.__name__})"
            )
            return strategy

        except Exception as e:
            logger.error(
                f"❌ 策略实例创建失败: {strategy_type}, "
                f"class={strategy_class.__name__}, error={e}",
                exc_info=True
            )
            raise

    @classmethod
    def list_strategies(cls) -> list:
        """
        列出所有已注册的策略

        Returns:
            list: 策略名称列表

        使用示例：
            >>> strategies = StrategyFactory.list_strategies()
            >>> for name in strategies:
            ...     print(f"- {name}")
        """
        return list(cls._registry.keys())

    @classmethod
    def is_registered(cls, strategy_type: str) -> bool:
        """
        检查策略是否已注册

        Args:
            strategy_type: 策略名称

        Returns:
            bool: 是否已注册

        使用示例：
            >>> if StrategyFactory.is_registered("scalper_v2"):
            ...     print("ScalperV2 策略已注册")
        """
        return strategy_type in cls._registry

    @classmethod
    def get_strategy_class(cls, strategy_type: str) -> Optional[Type[BaseStrategy]]:
        """
        获取策略类（不实例化）

        Args:
            strategy_type: 策略名称

        Returns:
            Type[BaseStrategy]: 策略类，如果未注册返回 None

        使用示例：
            >>> strategy_class = StrategyFactory.get_strategy_class("scalper_v2")
            >>> if strategy_class:
            ...     print(f"策略类: {strategy_class.__name__}")
        """
        return cls._registry.get(strategy_type)

    @classmethod
    def create_from_config(cls, config: Dict[str, Any], **dependencies) -> BaseStrategy:
        """
        从配置字典创建策略实例

        Args:
            config: 配置字典，必须包含 'strategy_type' 字段
                {
                    'strategy_type': 'scalper_v2',
                    'symbol': 'DOGE-USDT-SWAP',
                    'mode': 'PRODUCTION',
                    ...
                }
            **dependencies: 依赖注入对象
                - event_bus
                - order_manager
                - capital_commander
                - position_manager

        Returns:
            BaseStrategy: 策略实例

        使用示例：
            >>> config = {
            ...     'strategy_type': 'scalper_v2',
            ...     'symbol': 'DOGE-USDT-SWAP',
            ...     'mode': 'PRODUCTION'
            ... }
            >>> strategy = StrategyFactory.create_from_config(
            ...     config,
            ...     event_bus=event_bus,
            ...     order_manager=order_manager
            ... )
        """
        strategy_type = config.get('strategy_type')
        if not strategy_type:
            raise ValueError("配置字典必须包含 'strategy_type' 字段")

        # 合并配置和依赖
        kwargs = {**config, **dependencies}

        return cls.create(strategy_type=strategy_type, **kwargs)

    @classmethod
    def clear_registry(cls):
        """
        清空策略注册表（主要用于测试）

        警告：此方法会清空所有已注册的策略，谨慎使用！

        使用示例：
            >>> StrategyFactory.clear_registry()
        """
        cls._registry.clear()
        logger.warning("⚠️ 策略注册表已清空")


# ========== 便捷函数 ==========

def register_strategy(name: str):
    """
    便捷函数：策略注册装饰器

    与 StrategyFactory.register 功能相同，提供更简洁的别名。

    Args:
        name: 策略名称

    Returns:
        装饰器函数

    使用示例：
        >>> @register_strategy("scalper_v2")
        >>> class ScalperV2(BaseStrategy):
        >>>     pass
    """
    return StrategyFactory.register(name)


def create_strategy(strategy_type: str, **kwargs) -> BaseStrategy:
    """
    便捷函数：创建策略实例

    与 StrategyFactory.create 功能相同，提供更简洁的别名。

    Args:
        strategy_type: 策略名称
        **kwargs: 策略初始化参数

    Returns:
        BaseStrategy: 策略实例

    使用示例：
        >>> strategy = create_strategy(
        ...     "scalper_v2",
        ...     event_bus=event_bus,
        ...     symbol="DOGE-USDT-SWAP"
        ... )
    """
    return StrategyFactory.create(strategy_type, **kwargs)


# ========== 测试代码 ==========

if __name__ == '__main__':
    # 测试注册和创建

    # 定义测试策略
    @StrategyFactory.register("test_strategy")
    class TestStrategy(BaseStrategy):
        async def on_tick(self, event):
            pass

        async def on_signal(self, signal):
            pass

    # 列出所有策略
    print("已注册的策略:", StrategyFactory.list_strategies())

    # 检查是否注册
    print("test_strategy 已注册:", StrategyFactory.is_registered("test_strategy"))

    # 获取策略类
    strategy_class = StrategyFactory.get_strategy_class("test_strategy")
    print(f"策略类: {strategy_class}")

    # 清空注册表
    StrategyFactory.clear_registry()
    print("清空后:", StrategyFactory.list_strategies())
