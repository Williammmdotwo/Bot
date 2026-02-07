"""
State Machine - 状态机模块

提供通用的状态机实现，用于管理策略状态转换。

设计原则：
- 清晰的状态定义：使用枚举定义状态
- 灵活的转换规则：支持条件函数
- 状态处理器：每个状态可注册处理函数
- 易于调试：提供状态转换日志
"""

from enum import Enum
from typing import Dict, Callable, Optional, Any, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class StrategyState(Enum):
    """
    策略状态枚举

    定义策略的所有可能状态。

    状态说明：
    - IDLE: 空闲状态（无持仓，等待信号）
    - WAITING_ENTRY: 等待入场（已发现机会，等待订单成交）
    - IN_POSITION: 持仓中（已有持仓，监控市场）
    - WAITING_EXIT: 等待出场（已触发平仓信号，等待成交）
    - COOLDOWN: 冷却期（交易后冷却，避免过度交易）
    """

    IDLE = "idle"
    WAITING_ENTRY = "waiting_entry"
    IN_POSITION = "in_position"
    WAITING_EXIT = "waiting_exit"
    COOLDOWN = "cooldown"

    def __str__(self) -> str:
        """返回状态的字符串表示"""
        return self.value

    def __repr__(self) -> str:
        """返回状态的详细表示"""
        return f"StrategyState.{self.name}('{self.value}')"


@dataclass
class StateTransition:
    """
    状态转换定义

    定义从一个状态到另一个状态的转换规则。

    属性：
    - from_state: 起始状态
    - to_state: 目标状态
    - condition: 转换条件函数（返回 bool）
    - action: 转换动作（可选，在转换前执行）
    - name: 转换名称（用于日志和调试）

    使用示例：
        >>> transition = StateTransition(
        ...     from_state=StrategyState.IDLE,
        ...     to_state=StrategyState.WAITING_ENTRY,
        ...     condition=lambda: has_signal(),
        ...     action=lambda: submit_order(),
        ...     name="IDLE -> WAITING_ENTRY (发现信号)"
        ... )
    """

    from_state: StrategyState
    to_state: StrategyState
    condition: Callable[[], bool]
    action: Optional[Callable] = None
    name: str = ""

    def __post_init__(self):
        """初始化后处理"""
        if not self.name:
            self.name = f"{self.from_state.value} -> {self.to_state.value}"

    def __str__(self) -> str:
        """返回转换的字符串表示"""
        return self.name

    def __repr__(self) -> str:
        """返回转换的详细表示"""
        return f"StateTransition(from={self.from_state}, to={self.to_state}, action={self.action is not None})"


class StateMachine:
    """
    状态机基类

    提供通用的状态机实现，支持：
    - 状态转换规则定义
    - 状态处理器注册
    - 状态转换条件检查
    - 状态转换日志

    使用示例：
        >>> fsm = StateMachine(initial_state=StrategyState.IDLE)
        >>>
        >>> # 注册状态处理器
        >>> fsm.register_handler(StrategyState.IDLE, handle_idle)
        >>>
        >>> # 添加转换规则
        >>> fsm.add_transition(StateTransition(
        ...     from_state=StrategyState.IDLE,
        ...     to_state=StrategyState.WAITING_ENTRY,
        ...     condition=lambda: has_signal(),
        ...     action=lambda: submit_order()
        ... ))
        >>>
        >>> # 更新状态机
        >>> await fsm.update()
    """

    def __init__(self, initial_state: StrategyState):
        """
        初始化状态机

        Args:
            initial_state: 初始状态
        """
        self.current_state = initial_state
        self._previous_state: Optional[StrategyState] = None
        self._transitions: Dict[StrategyState, List[StateTransition]] = {}
        self._state_handlers: Dict[StrategyState, Callable] = {}
        self._transition_count = 0

        logger.info(f"状态机初始化: 初始状态={initial_state.value}")

    def add_transition(self, transition: StateTransition) -> None:
        """
        添加状态转换规则

        Args:
            transition: 状态转换定义

        Example:
            >>> fsm.add_transition(StateTransition(
            ...     from_state=StrategyState.IDLE,
            ...     to_state=StrategyState.WAITING_ENTRY,
            ...     condition=lambda: has_signal()
            ... ))
        """
        if transition.from_state not in self._transitions:
            self._transitions[transition.from_state] = []

        self._transitions[transition.from_state].append(transition)
        logger.debug(f"添加状态转换: {transition}")

    def register_handler(self, state: StrategyState, handler: Callable) -> None:
        """
        注册状态处理器

        Args:
            state: 状态
            handler: 处理函数（async function）

        Example:
            >>> async def handle_idle():
            ...     print("空闲状态")
            >>>
            >>> fsm.register_handler(StrategyState.IDLE, handle_idle)
        """
        self._state_handlers[state] = handler
        logger.debug(f"注册状态处理器: {state.value} -> {handler.__name__}")

    async def update(self) -> bool:
        """
        更新状态机（检查转换条件）

        检查当前状态的所有转换规则，如果满足条件则执行转换。
        按添加顺序检查，第一个满足条件的转换会被执行。

        Returns:
            bool: 是否发生了状态转换

        Example:
            >>> changed = await fsm.update()
            >>> if changed:
            ...     print(f"状态已改变: {fsm.current_state}")
        """
        transitions = self._transitions.get(self.current_state, [])

        for transition in transitions:
            try:
                # 检查转换条件
                if transition.condition():
                    # 执行转换动作
                    if transition.action:
                        await transition.action()

                    # 状态切换
                    old_state = self.current_state
                    self._previous_state = old_state
                    self.current_state = transition.to_state
                    self._transition_count += 1

                    logger.info(
                        f"状态转换: {old_state.value} -> {self.current_state.value} "
                        f"(转换 #{self._transition_count})"
                    )

                    return True
            except Exception as e:
                logger.error(
                    f"状态转换失败: {transition.from_state.value} -> {transition.to_state.value}, "
                    f"错误: {e}",
                    exc_info=True
                )

        return False

    async def handle_current_state(self, *args, **kwargs) -> Any:
        """
        处理当前状态

        调用当前状态注册的处理函数。

        Args:
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            Any: 处理函数的返回值

        Example:
            >>> await fsm.handle_current_state(event_data)
        """
        handler = self._state_handlers.get(self.current_state)
        if handler:
            try:
                result = await handler(*args, **kwargs)
                return result
            except Exception as e:
                logger.error(
                    f"状态处理器执行失败: {self.current_state.value}, "
                    f"错误: {e}",
                    exc_info=True
                )
        else:
            logger.warning(f"未注册状态处理器: {self.current_state.value}")

        return None

    def force_transition(self, new_state: StrategyState) -> None:
        """
        强制转换到指定状态（跳过条件检查）

        Args:
            new_state: 新状态

        警告：
            此方法会跳过所有转换条件检查，仅用于特殊情况（如异常恢复）。

        Example:
            >>> fsm.force_transition(StrategyState.IDLE)
        """
        old_state = self.current_state
        self._previous_state = old_state
        self.current_state = new_state
        self._transition_count += 1

        logger.warning(
            f"强制状态转换: {old_state.value} -> {new_state.value} "
            f"(转换 #{self._transition_count})"
        )

    def reset(self, initial_state: Optional[StrategyState] = None) -> None:
        """
        重置状态机

        Args:
            initial_state: 新的初始状态（可选，默认使用当前状态）

        Example:
            >>> fsm.reset(StrategyState.IDLE)
        """
        if initial_state is None:
            initial_state = self.current_state

        self._previous_state = None
        self.current_state = initial_state
        self._transition_count = 0

        logger.info(f"状态机已重置: 初始状态={initial_state.value}")

    def get_state_info(self) -> Dict[str, Any]:
        """
        获取状态机信息

        Returns:
            dict: 状态机信息

        Example:
            >>> info = fsm.get_state_info()
            >>> print(info)
            {'current_state': 'idle', 'previous_state': None, 'transition_count': 0}
        """
        return {
            'current_state': self.current_state.value,
            'previous_state': self._previous_state.value if self._previous_state else None,
            'transition_count': self._transition_count,
            'registered_transitions': len(self._transitions.get(self.current_state, [])),
            'registered_handlers': len(self._state_handlers)
        }

    def has_transition(self, from_state: StrategyState, to_state: StrategyState) -> bool:
        """
        检查是否存在指定转换

        Args:
            from_state: 起始状态
            to_state: 目标状态

        Returns:
            bool: 是否存在该转换

        Example:
            >>> if fsm.has_transition(StrategyState.IDLE, StrategyState.WAITING_ENTRY):
            ...     print("存在转换")
        """
        transitions = self._transitions.get(from_state, [])
        return any(t.to_state == to_state for t in transitions)

    def get_possible_transitions(self) -> List[StateTransition]:
        """
        获取当前状态的所有可能转换

        Returns:
            list: 转换列表

        Example:
            >>> transitions = fsm.get_possible_transitions()
            >>> for t in transitions:
            ...     print(t)
        """
        return self._transitions.get(self.current_state, []).copy()

    def __str__(self) -> str:
        """返回状态机的字符串表示"""
        return f"StateMachine(current={self.current_state.value}, transitions={self._transition_count})"

    def __repr__(self) -> str:
        """返回状态机的详细表示"""
        return (
            f"StateMachine("
            f"current={self.current_state.value}, "
            f"previous={self._previous_state.value if self._previous_state else None}, "
            f"transitions={self._transition_count})"
        )


# ========== 便捷函数 ==========

def create_simple_fsm(
    states: List[StrategyState],
    initial_state: StrategyState,
    transitions: List[tuple]
) -> StateMachine:
    """
    创建简单状态机（便捷函数）

    Args:
        states: 状态列表
        initial_state: 初始状态
        transitions: 转换列表 [(from_state, to_state, condition, action), ...]

    Returns:
        StateMachine: 状态机实例

    Example:
        >>> fsm = create_simple_fsm(
        ...     states=[StrategyState.IDLE, StrategyState.IN_POSITION],
        ...     initial_state=StrategyState.IDLE,
        ...     transitions=[
        ...         (StrategyState.IDLE, StrategyState.IN_POSITION, lambda: True, None)
        ...     ]
        ... )
    """
    fsm = StateMachine(initial_state=initial_state)

    for t in transitions:
        from_state, to_state, condition, action = t[:4]
        name = t[4] if len(t) > 4 else ""

        transition = StateTransition(
            from_state=from_state,
            to_state=to_state,
            condition=condition,
            action=action,
            name=name
        )

        fsm.add_transition(transition)

    return fsm


# ========== 测试代码 ==========

async def _test_fsm():
    """测试状态机"""

    # 创建状态机
    fsm = StateMachine(initial_state=StrategyState.IDLE)

    # 定义状态变量
    has_signal = False
    position_size = 0

    # 注册状态处理器
    async def handle_idle():
        print("处理空闲状态")

    async def handle_waiting_entry():
        print("处理等待入场状态")

    async def handle_in_position():
        print("处理持仓状态")

    fsm.register_handler(StrategyState.IDLE, handle_idle)
    fsm.register_handler(StrategyState.WAITING_ENTRY, handle_waiting_entry)
    fsm.register_handler(StrategyState.IN_POSITION, handle_in_position)

    # 添加转换规则
    # IDLE -> WAITING_ENTRY（发现信号）
    fsm.add_transition(StateTransition(
        from_state=StrategyState.IDLE,
        to_state=StrategyState.WAITING_ENTRY,
        condition=lambda: has_signal,
        action=lambda: print("提交入场订单"),
        name="IDLE -> WAITING_ENTRY (发现信号)"
    ))

    # WAITING_ENTRY -> IN_POSITION（订单成交）
    fsm.add_transition(StateTransition(
        from_state=StrategyState.WAITING_ENTRY,
        to_state=StrategyState.IN_POSITION,
        condition=lambda: position_size != 0,
        action=None,
        name="WAITING_ENTRY -> IN_POSITION (成交)"
    ))

    # IN_POSITION -> IDLE（平仓完成）
    fsm.add_transition(StateTransition(
        from_state=StrategyState.IN_POSITION,
        to_state=StrategyState.IDLE,
        condition=lambda: position_size == 0,
        action=lambda: print("平仓完成"),
        name="IN_POSITION -> IDLE (平仓)"
    ))

    # 测试状态转换
    print("\n=== 初始状态 ===")
    print(fsm.get_state_info())

    print("\n=== 触发信号 ===")
    has_signal = True
    changed = await fsm.update()
    print(f"状态是否改变: {changed}")
    print(fsm.get_state_info())

    print("\n=== 模拟成交 ===")
    position_size = 100
    changed = await fsm.update()
    print(f"状态是否改变: {changed}")
    print(fsm.get_state_info())

    print("\n=== 模拟平仓 ===")
    position_size = 0
    changed = await fsm.update()
    print(f"状态是否改变: {changed}")
    print(fsm.get_state_info())

    print("\n=== 测试完成 ===")


if __name__ == '__main__':
    import asyncio
    asyncio.run(_test_fsm())
