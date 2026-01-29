"""
策略状态定义（有限状态机 - FSM）

用于 ScalperV2 策略的状态管理
"""

from enum import IntEnum


class StrategyState(IntEnum):
    """
    策略状态枚举

    状态流转：
    IDLE → PENDING_OPEN → POSITION_HELD → PENDING_CLOSE → IDLE

    IDLE: 空仓，无挂单 → 需要运行信号生成
    PENDING_OPEN: 有挂单（开仓中） → 只需要运行挂单维护（插队/撤单），不需要生成新信号
    POSITION_HELD: 持仓 → 只需要运行止损/止盈逻辑
    PENDING_CLOSE: 有挂单（平仓中） → 只需要运行挂单维护
    """
    IDLE = 0          # 空仓，无挂单 -> 需要运行信号生成
    PENDING_OPEN = 1  # 有挂单（开仓中） -> 只需要运行挂单维护（插队/撤单），不需要生成新信号
    POSITION_HELD = 2  # 持仓 -> 只需要运行止损/止盈逻辑
    PENDING_CLOSE = 3   # 有挂单（平仓中） -> 只需要运行挂单维护

    def __str__(self):
        """状态描述"""
        return self.name
