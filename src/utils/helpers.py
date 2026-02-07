"""
Helpers - 工具函数模块

提供统一的工具类，消除重复代码，统一计算逻辑。

设计原则：
- 静态方法：无需实例化
- 类型安全：完整的类型提示
- 独立可测：每个方法独立可测试
- 易于使用：简洁的 API
"""

from typing import Optional
import time


class PriceUtils:
    """
    价格工具类

    提供价格相关的常用计算和格式化方法。

    使用示例：
        >>> PriceUtils.round_to_tick(0.085123, 0.0001)
        0.0851

        >>> PriceUtils.format_price(1234.5678, 2)
        '1,234.57'
    """

    @staticmethod
    def round_to_tick(price: float, tick_size: float) -> float:
        """
        按 tick_size 四舍五入价格

        Args:
            price: 原始价格
            tick_size: 最小价格变动单位

        Returns:
            float: 四舍五入后的价格

        Example:
            >>> PriceUtils.round_to_tick(0.085123, 0.0001)
            0.0851
        """
        if tick_size <= 0:
            return price
        return round(price / tick_size) * tick_size

    @staticmethod
    def format_price(price: float, precision: int = 2) -> str:
        """
        格式化价格显示（带千分位）

        Args:
            price: 价格
            precision: 小数位数（默认 2）

        Returns:
            str: 格式化后的价格字符串

        Example:
            >>> PriceUtils.format_price(1234.5678, 2)
            '1,234.57'
        """
        return f"{price:,.{precision}f}"

    @staticmethod
    def calculate_slippage_pct(entry_price: float, exit_price: float, side: str) -> float:
        """
        计算滑点百分比

        Args:
            entry_price: 入场价格
            exit_price: 出场价格
            side: 交易方向（'buy' 或 'sell'）

        Returns:
            float: 滑点百分比

        Example:
            >>> PriceUtils.calculate_slippage_pct(0.085, 0.0851, 'buy')
            0.117647...
        """
        if entry_price <= 0:
            return 0.0

        if side == 'buy':
            return (exit_price - entry_price) / entry_price * 100
        else:
            return (entry_price - exit_price) / entry_price * 100

    @staticmethod
    def calculate_mid_price(bid: float, ask: float) -> float:
        """
        计算中间价

        Args:
            bid: 买价
            ask: 卖价

        Returns:
            float: 中间价

        Example:
            >>> PriceUtils.calculate_mid_price(0.0849, 0.0851)
            0.085
        """
        if bid <= 0 or ask <= 0:
            return 0.0
        return (bid + ask) / 2.0

    @staticmethod
    def calculate_spread_pct(bid: float, ask: float) -> float:
        """
        计算点差百分比

        Args:
            bid: 买价
            ask: 卖价

        Returns:
            float: 点差百分比

        Example:
            >>> PriceUtils.calculate_spread_pct(0.0849, 0.0851)
            0.235...
        """
        mid_price = PriceUtils.calculate_mid_price(bid, ask)
        if mid_price <= 0:
            return 0.0
        return (ask - bid) / mid_price * 100


class TimeUtils:
    """
    时间工具类

    提供时间相关的常用计算和格式化方法。

    使用示例：
        >>> TimeUtils.now_ms()
        1701234567890

        >>> TimeUtils.format_duration(123.456)
        '2.1min'
    """

    @staticmethod
    def now_ms() -> int:
        """
        当前时间戳（毫秒）

        Returns:
            int: 毫秒级时间戳

        Example:
            >>> TimeUtils.now_ms()
            1701234567890
        """
        return int(time.time() * 1000)

    @staticmethod
    def now_s() -> int:
        """
        当前时间戳（秒）

        Returns:
            int: 秒级时间戳

        Example:
            >>> TimeUtils.now_s()
            1701234567
        """
        return int(time.time())

    @staticmethod
    def ms_to_s(ms: int) -> float:
        """
        毫秒转换为秒

        Args:
            ms: 毫秒

        Returns:
            float: 秒

        Example:
            >>> TimeUtils.ms_to_s(1500)
            1.5
        """
        return ms / 1000.0

    @staticmethod
    def s_to_ms(s: float) -> int:
        """
        秒转换为毫秒

        Args:
            s: 秒

        Returns:
            int: 毫秒

        Example:
            >>> TimeUtils.s_to_ms(1.5)
            1500
        """
        return int(s * 1000)

    @staticmethod
    def format_duration(seconds: float) -> str:
        """
        格式化时长

        Args:
            seconds: 秒数

        Returns:
            str: 格式化后的时长字符串

        Example:
            >>> TimeUtils.format_duration(0.5)
            '500ms'

            >>> TimeUtils.format_duration(30)
            '30.0s'

            >>> TimeUtils.format_duration(90)
            '1.5min'
        """
        if seconds < 1:
            return f"{seconds * 1000:.0f}ms"
        elif seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}min"
        else:
            return f"{seconds / 3600:.1f}h"

    @staticmethod
    def format_timestamp_ms(ms: int) -> str:
        """
        格式化时间戳为可读字符串

        Args:
            ms: 毫秒级时间戳

        Returns:
            str: 格式化后的时间字符串

        Example:
            >>> TimeUtils.format_timestamp_ms(1701234567890)
            '2023-11-29 12:09:27'
        """
        from datetime import datetime
        dt = datetime.fromtimestamp(ms / 1000.0)
        return dt.strftime('%Y-%m-%d %H:%M:%S')

    @staticmethod
    def elapsed_ms(start_ms: int) -> float:
        """
        计算经过的毫秒数

        Args:
            start_ms: 开始时间戳（毫秒）

        Returns:
            float: 经过的时间（毫秒）

        Example:
            >>> start = TimeUtils.now_ms()
            >>> # ... 执行某些操作 ...
            >>> elapsed = TimeUtils.elapsed_ms(start)
        """
        return TimeUtils.now_ms() - start_ms

    @staticmethod
    def elapsed_s(start_ms: int) -> float:
        """
        计算经过的秒数

        Args:
            start_ms: 开始时间戳（毫秒）

        Returns:
            float: 经过的时间（秒）
        """
        return TimeUtils.elapsed_ms(start_ms) / 1000.0


class PositionUtils:
    """
    持仓工具类

    提供持仓相关的计算方法。

    使用示例：
        >>> PositionUtils.usdt_to_contracts(100, 0.085, 10)
        117

        >>> PositionUtils.calculate_pnl_pct(0.085, 0.086, 'buy')
        1.176...
    """

    @staticmethod
    def usdt_to_contracts(usdt_amount: float, price: float, ct_val: float) -> int:
        """
        USDT 转换为合约张数

        Args:
            usdt_amount: USDT 金额
            price: 价格
            ct_val: 合约面值（每张合约的币数量）

        Returns:
            int: 合约张数（向下取整）

        Example:
            >>> PositionUtils.usdt_to_contracts(100, 0.085, 10)
            117
        """
        if price <= 0 or ct_val <= 0:
            return 0
        return int(usdt_amount / (price * ct_val))

    @staticmethod
    def contracts_to_usdt(contracts: int, price: float, ct_val: float) -> float:
        """
        合约张数转换为 USDT

        Args:
            contracts: 合约张数
            price: 价格
            ct_val: 合约面值

        Returns:
            float: USDT 金额

        Example:
            >>> PositionUtils.contracts_to_usdt(117, 0.085, 10)
            99.45
        """
        return contracts * price * ct_val

    @staticmethod
    def calculate_pnl_pct(entry_price: float, current_price: float, side: str) -> float:
        """
        计算盈亏百分比

        Args:
            entry_price: 入场价格
            current_price: 当前价格
            side: 交易方向（'buy' 或 'sell'）

        Returns:
            float: 盈亏百分比

        Example:
            >>> PositionUtils.calculate_pnl_pct(0.085, 0.086, 'buy')
            1.176...
        """
        if entry_price <= 0:
            return 0.0

        if side == 'buy':
            return (current_price - entry_price) / entry_price * 100
        else:
            return (entry_price - current_price) / entry_price * 100

    @staticmethod
    def calculate_pnl_usdt(contracts: int, entry_price: float, current_price: float,
                          ct_val: float, side: str) -> float:
        """
        计算 USDT 盈亏

        Args:
            contracts: 合约张数
            entry_price: 入场价格
            current_price: 当前价格
            ct_val: 合约面值
            side: 交易方向（'buy' 或 'sell'）

        Returns:
            float: USDT 盈亏

        Example:
            >>> PositionUtils.calculate_pnl_usdt(100, 0.085, 0.086, 10, 'buy')
            10.0
        """
        pnl_pct = PositionUtils.calculate_pnl_pct(entry_price, current_price, side)
        usdt_value = PositionUtils.contracts_to_usdt(contracts, entry_price, ct_val)
        return usdt_value * pnl_pct / 100.0

    @staticmethod
    def calculate_liquidation_price(entry_price: float, leverage: float,
                                   side: str, maintenance_margin: float = 0.005) -> float:
        """
        计算强平价格

        Args:
            entry_price: 入场价格
            leverage: 杠杆倍数
            side: 交易方向（'buy' 或 'sell'）
            maintenance_margin: 维持保证金率（默认 0.5%）

        Returns:
            float: 强平价格

        Example:
            >>> PositionUtils.calculate_liquidation_price(0.085, 10, 'buy')
            0.0765
        """
        if entry_price <= 0 or leverage <= 0:
            return 0.0

        margin_ratio = 1.0 / leverage

        if side == 'buy':
            # 多头：当价格下跌时触发强平
            return entry_price * (1 - margin_ratio + maintenance_margin)
        else:
            # 空头：当价格上涨时触发强平
            return entry_price * (1 + margin_ratio - maintenance_margin)


class ValidationUtils:
    """
    验证工具类

    提供常用的数据验证方法。

    使用示例：
        >>> ValidationUtils.is_valid_symbol('DOGE-USDT-SWAP')
        True

        >>> ValidationUtils.is_valid_side('buy')
        True
    """

    @staticmethod
    def is_valid_symbol(symbol: str) -> bool:
        """
        验证交易对格式

        Args:
            symbol: 交易对符号（如 'DOGE-USDT-SWAP'）

        Returns:
            bool: 是否有效

        Example:
            >>> ValidationUtils.is_valid_symbol('DOGE-USDT-SWAP')
            True
        """
        if not symbol or not isinstance(symbol, str):
            return False
        return '-' in symbol and len(symbol.split('-')) >= 2

    @staticmethod
    def is_valid_side(side: str) -> bool:
        """
        验证交易方向

        Args:
            side: 交易方向

        Returns:
            bool: 是否有效

        Example:
            >>> ValidationUtils.is_valid_side('buy')
            True
        """
        return side in ['buy', 'sell']

    @staticmethod
    def is_valid_order_type(order_type: str) -> bool:
        """
        验证订单类型

        Args:
            order_type: 订单类型

        Returns:
            bool: 是否有效

        Example:
            >>> ValidationUtils.is_valid_order_type('market')
            True
        """
        return order_type in ['market', 'limit', 'post_only', 'fok', 'ioc']

    @staticmethod
    def is_valid_price(price: float) -> bool:
        """
        验证价格

        Args:
            price: 价格

        Returns:
            bool: 是否有效

        Example:
            >>> ValidationUtils.is_valid_price(0.085)
            True
        """
        return isinstance(price, (int, float)) and price > 0

    @staticmethod
    def is_valid_size(size: float) -> bool:
        """
        验证数量

        Args:
            size: 数量

        Returns:
            bool: 是否有效

        Example:
            >>> ValidationUtils.is_valid_size(100)
            True
        """
        return isinstance(size, (int, float)) and size > 0

    @staticmethod
    def is_valid_timestamp(timestamp: int) -> bool:
        """
        验证时间戳

        Args:
            timestamp: 时间戳

        Returns:
            bool: 是否有效

        Example:
            >>> ValidationUtils.is_valid_timestamp(1701234567890)
            True
        """
        if not isinstance(timestamp, int):
            return False
        # 检查是否在合理范围内（2020-2030年）
        return 1577836800000 <= timestamp <= 1893456000000


class MathUtils:
    """
    数学工具类

    提供常用的数学计算方法。

    使用示例：
        >>> MathUtils.clamp(150, 0, 100)
        100

        >>> MathUtils.lerp(0, 100, 0.5)
        50.0
    """

    @staticmethod
    def clamp(value: float, min_val: float, max_val: float) -> float:
        """
        将值限制在指定范围内

        Args:
            value: 原始值
            min_val: 最小值
            max_val: 最大值

        Returns:
            float: 限制后的值

        Example:
            >>> MathUtils.clamp(150, 0, 100)
            100
        """
        return max(min_val, min(value, max_val))

    @staticmethod
    def lerp(a: float, b: float, t: float) -> float:
        """
        线性插值

        Args:
            a: 起始值
            b: 结束值
            t: 插值参数（0-1）

        Returns:
            float: 插值结果

        Example:
            >>> MathUtils.lerp(0, 100, 0.5)
            50.0
        """
        return a + (b - a) * t

    @staticmethod
    def map_range(value: float, in_min: float, in_max: float,
                 out_min: float, out_max: float) -> float:
        """
        将值从一个范围映射到另一个范围

        Args:
            value: 输入值
            in_min: 输入范围最小值
            in_max: 输入范围最大值
            out_min: 输出范围最小值
            out_max: 输出范围最大值

        Returns:
            float: 映射后的值

        Example:
            >>> MathUtils.map_range(50, 0, 100, 0, 1)
            0.5
        """
        if in_max == in_min:
            return out_min
        return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    @staticmethod
    def is_close(a: float, b: float, rel_tol: float = 1e-9, abs_tol: float = 0.0) -> bool:
        """
        判断两个浮点数是否接近

        Args:
            a: 第一个数
            b: 第二个数
            rel_tol: 相对容差
            abs_tol: 绝对容差

        Returns:
            bool: 是否接近

        Example:
            >>> MathUtils.is_close(0.1 + 0.2, 0.3)
            True
        """
        return abs(a - b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)


# ========== 便捷函数 ==========

def format_usdt(amount: float, precision: int = 2) -> str:
    """
    格式化 USDT 金额

    Args:
        amount: 金额
        precision: 小数位数

    Returns:
        str: 格式化后的金额字符串

    Example:
        >>> format_usdt(1234.5678)
        '1,234.57 USDT'
    """
    return f"{PriceUtils.format_price(amount, precision)} USDT"


def format_price_with_side(price: float, side: str, precision: int = 2) -> str:
    """
    格式化价格并显示交易方向

    Args:
        price: 价格
        side: 交易方向
        precision: 小数位数

    Returns:
        str: 格式化后的字符串

    Example:
        >>> format_price_with_side(0.085, 'buy')
        '🟢 Buy @ 0.09'
    """
    emoji = '🟢' if side == 'buy' else '🔴'
    direction = 'Buy' if side == 'buy' else 'Sell'
    return f"{emoji} {direction} @ {PriceUtils.format_price(price, precision)}"


def calculate_position_size(usdt_amount: float, price: float, ct_val: float,
                           leverage: float = 1.0) -> int:
    """
    计算仓位大小（考虑杠杆）

    Args:
        usdt_amount: USDT 金额
        price: 价格
        ct_val: 合约面值
        leverage: 杠杆倍数

    Returns:
        int: 合约张数

    Example:
        >>> calculate_position_size(100, 0.085, 10, 10)
        1176
    """
    effective_usdt = usdt_amount * leverage
    return PositionUtils.usdt_to_contracts(effective_usdt, price, ct_val)


# ========== 测试代码 ==========

if __name__ == '__main__':
    # 测试 PriceUtils
    print("=== PriceUtils ===")
    print(f"Round to tick: {PriceUtils.round_to_tick(0.085123, 0.0001)}")
    print(f"Format price: {PriceUtils.format_price(1234.5678, 2)}")
    print(f"Slippage: {PriceUtils.calculate_slippage_pct(0.085, 0.0851, 'buy'):.4f}%")
    print(f"Mid price: {PriceUtils.calculate_mid_price(0.0849, 0.0851)}")
    print(f"Spread: {PriceUtils.calculate_spread_pct(0.0849, 0.0851):.4f}%")

    # 测试 TimeUtils
    print("\n=== TimeUtils ===")
    print(f"Now ms: {TimeUtils.now_ms()}")
    print(f"Now s: {TimeUtils.now_s()}")
    print(f"Format duration (0.5s): {TimeUtils.format_duration(0.5)}")
    print(f"Format duration (30s): {TimeUtils.format_duration(30)}")
    print(f"Format duration (90s): {TimeUtils.format_duration(90)}")
    print(f"Format timestamp: {TimeUtils.format_timestamp_ms(TimeUtils.now_ms())}")

    # 测试 PositionUtils
    print("\n=== PositionUtils ===")
    print(f"USDT to contracts: {PositionUtils.usdt_to_contracts(100, 0.085, 10)}")
    print(f"Contracts to USDT: {PositionUtils.contracts_to_usdt(117, 0.085, 10):.2f}")
    print(f"PNL %: {PositionUtils.calculate_pnl_pct(0.085, 0.086, 'buy'):.4f}%")
    print(f"PNL USDT: {PositionUtils.calculate_pnl_usdt(100, 0.085, 0.086, 10, 'buy'):.2f}")
    print(f"Liquidation price: {PositionUtils.calculate_liquidation_price(0.085, 10, 'buy'):.4f}")

    # 测试 ValidationUtils
    print("\n=== ValidationUtils ===")
    print(f"Valid symbol: {ValidationUtils.is_valid_symbol('DOGE-USDT-SWAP')}")
    print(f"Valid side: {ValidationUtils.is_valid_side('buy')}")
    print(f"Valid order type: {ValidationUtils.is_valid_order_type('market')}")
    print(f"Valid price: {ValidationUtils.is_valid_price(0.085)}")
    print(f"Valid size: {ValidationUtils.is_valid_size(100)}")
    print(f"Valid timestamp: {ValidationUtils.is_valid_timestamp(TimeUtils.now_ms())}")

    # 测试 MathUtils
    print("\n=== MathUtils ===")
    print(f"Clamp: {MathUtils.clamp(150, 0, 100)}")
    print(f"Lerp: {MathUtils.lerp(0, 100, 0.5)}")
    print(f"Map range: {MathUtils.map_range(50, 0, 100, 0, 1)}")
    print(f"Is close: {MathUtils.is_close(0.1 + 0.2, 0.3)}")

    # 测试便捷函数
    print("\n=== 便捷函数 ===")
    print(f"Format USDT: {format_usdt(1234.5678)}")
    print(f"Format price with side: {format_price_with_side(0.085, 'buy')}")
    print(f"Calculate position size: {calculate_position_size(100, 0.085, 10, 10)}")
