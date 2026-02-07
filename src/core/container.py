"""
Container - 依赖注入容器

提供简化的依赖注入实现，解耦组件创建逻辑。

设计原则：
- 简单易用：不引入复杂的 DI 框架
- 灵活性：支持单例和工厂函数
- 延迟加载：工厂函数按需创建实例
- 易于测试：可以轻松 Mock 依赖
"""

from __future__ import annotations
from typing import Dict, Type, Any, Callable, Optional, TypeVar
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class Container:
    """
    依赖注入容器（简化版）

    提供轻量级的依赖注入实现，支持：
    - 单例注册：直接注册实例
    - 工厂注册：注册工厂函数，延迟创建
    - 自动缓存：工厂函数创建的实例会被缓存
    - 类型提示：支持泛型

    使用示例：
        >>> container = Container()
        >>>
        >>> # 注册单例
        >>> container.register('event_bus', EventBus())
        >>>
        >>> # 注册工厂
        >>> container.register_factory('strategy', lambda c: Strategy(c.get('event_bus')))
        >>>
        >>> # 获取服务
        >>> event_bus = container.get('event_bus')
        >>> strategy = container.get('strategy')
    """

    def __init__(self):
        """初始化容器"""
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[[Container], Any]] = {}

        logger.debug("依赖注入容器已初始化")

    def register(self, name: str, instance: Any) -> None:
        """
        注册单例服务

        Args:
            name: 服务名称
            instance: 服务实例

        Example:
            >>> container.register('event_bus', EventBus())
        """
        if name in self._services:
            logger.warning(f"服务已注册，将被覆盖: {name}")

        self._services[name] = instance
        logger.debug(f"注册单例服务: {name}")

    def register_factory(self, name: str, factory: Callable[[Container], Any]) -> None:
        """
        注册工厂函数

        Args:
            name: 服务名称
            factory: 工厂函数（接收容器作为参数）

        Example:
            >>> container.register_factory('strategy', lambda c: Strategy(c.get('event_bus')))
        """
        if name in self._factories:
            logger.warning(f"工厂已注册，将被覆盖: {name}")

        self._factories[name] = factory
        logger.debug(f"注册工厂函数: {name}")

    def get(self, name: str) -> Any:
        """
        获取服务实例

        优先返回已注册的单例，如果没有则调用工厂函数创建。
        工厂函数创建的实例会被缓存为单例。

        Args:
            name: 服务名称

        Returns:
            Any: 服务实例

        Raises:
            KeyError: 服务未注册

        Example:
            >>> event_bus = container.get('event_bus')
            >>> strategy = container.get('strategy')
        """
        # 先查找已注册的实例
        if name in self._services:
            return self._services[name]

        # 再查找工厂函数
        if name in self._factories:
            try:
                instance = self._factories[name](self)
                self._services[name] = instance  # 缓存
                logger.debug(f"通过工厂创建并缓存服务: {name}")
                return instance
            except Exception as e:
                logger.error(f"工厂函数执行失败: {name}, 错误: {e}", exc_info=True)
                raise

        raise KeyError(f"服务未注册: {name}")

    def has(self, name: str) -> bool:
        """
        检查服务是否存在

        Args:
            name: 服务名称

        Returns:
            bool: 是否存在

        Example:
            >>> if container.has('event_bus'):
            ...     event_bus = container.get('event_bus')
        """
        return name in self._services or name in self._factories

    def unregister(self, name: str) -> None:
        """
        注销服务

        Args:
            name: 服务名称

        Example:
            >>> container.unregister('event_bus')
        """
        if name in self._services:
            del self._services[name]
            logger.debug(f"注销单例服务: {name}")

        if name in self._factories:
            del self._factories[name]
            logger.debug(f"注销工厂函数: {name}")

    def clear(self) -> None:
        """
        清空所有服务

        警告：
            此方法会清空所有已注册的服务和工厂。

        Example:
            >>> container.clear()
        """
        self._services.clear()
        self._factories.clear()
        logger.debug("依赖注入容器已清空")

    def get_all_services(self) -> Dict[str, Any]:
        """
        获取所有已注册的单例服务

        Returns:
            dict: 服务字典

        Example:
            >>> services = container.get_all_services()
            >>> print(services.keys())
        """
        return self._services.copy()

    def get_all_factories(self) -> Dict[str, Callable]:
        """
        获取所有已注册的工厂函数

        Returns:
            dict: 工厂字典

        Example:
            >>> factories = container.get_all_factories()
            >>> print(factories.keys())
        """
        return self._factories.copy()

    def info(self) -> Dict[str, Any]:
        """
        获取容器信息

        Returns:
            dict: 容器信息

        Example:
            >>> info = container.info()
            >>> print(info)
            {'services': 5, 'factories': 3, 'total': 8}
        """
        return {
            'services': len(self._services),
            'factories': len(self._factories),
            'total': len(self._services) + len(self._factories),
            'service_names': list(self._services.keys()),
            'factory_names': list(self._factories.keys())
        }

    def __str__(self) -> str:
        """返回容器的字符串表示"""
        return f"Container(services={len(self._services)}, factories={len(self._factories)})"

    def __repr__(self) -> str:
        """返回容器的详细表示"""
        return (
            f"Container("
            f"services={list(self._services.keys())}, "
            f"factories={list(self._factories.keys())})"
        )


# ========== 便捷函数 ==========

def create_container() -> Container:
    """
    创建容器（便捷函数）

    Returns:
        Container: 容器实例

    Example:
        >>> container = create_container()
    """
    return Container()


# ========== 装饰器 ==========

def injectable(name: str, factory: bool = False):
    """
    可注入装饰器

    用于标记类可以被容器注入。

    Args:
        name: 服务名称
        factory: 是否为工厂函数（默认 False）

    Example:
        >>> @injectable('my_service')
        ... class MyService:
        ...     pass
    """
    def decorator(cls):
        # 添加元数据
        if not hasattr(cls, '_injectable_metadata'):
            cls._injectable_metadata = {}

        cls._injectable_metadata['name'] = name
        cls._injectable_metadata['factory'] = factory

        return cls

    return decorator


# ========== 测试代码 ==========

def _test_container():
    """测试依赖注入容器"""

    # 创建容器
    container = Container()

    # 定义测试服务
    class EventBus:
        """事件总线"""
        def __init__(self):
            self.events = []

        def publish(self, event):
            self.events.append(event)

    class Strategy:
        """策略"""
        def __init__(self, event_bus):
            self.event_bus = event_bus

    # 注册单例
    container.register('event_bus', EventBus())
    print(f"注册单例: event_bus")

    # 注册工厂
    container.register_factory('strategy', lambda c: Strategy(c.get('event_bus')))
    print(f"注册工厂: strategy")

    # 获取服务
    event_bus = container.get('event_bus')
    print(f"获取服务: event_bus = {event_bus}")

    # 获取工厂创建的服务
    strategy = container.get('strategy')
    print(f"获取服务: strategy = {strategy}")
    print(f"策略的 event_bus: {strategy.event_bus}")

    # 检查服务是否存在
    print(f"检查服务: has('event_bus') = {container.has('event_bus')}")
    print(f"检查服务: has('unknown') = {container.has('unknown')}")

    # 获取容器信息
    info = container.info()
    print(f"\n容器信息:")
    print(f"  服务数量: {info['services']}")
    print(f"  工厂数量: {info['factories']}")
    print(f"  总计: {info['total']}")
    print(f"  服务名称: {info['service_names']}")
    print(f"  工厂名称: {info['factory_names']}")

    # 测试缓存
    strategy2 = container.get('strategy')
    print(f"\n测试缓存: strategy is strategy2 = {strategy is strategy2}")

    print("\n测试完成！")


if __name__ == '__main__':
    _test_container()
