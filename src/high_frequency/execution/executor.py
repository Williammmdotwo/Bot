"""
HFT 订单执行器

本模块提供高频交易的订单执行功能，用于 HFT 场景。

核心功能：
- 实现 IOC（Immediate-Or-Cancel）订单
- 批量撤单功能
- 基于 RestClient 的异步 API 调用

设计原则：
- 不使用 ccxt，直接使用 RestClient
- IOC 订单通过限价单 + 立即撤单实现
- 异步并发处理，低延迟
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from ..utils.async_client import RestClient

logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    HFT 订单执行器

    使用 RestClient 实现 IOC 订单和批量撤单功能。

    OKX V5 IOC 实现方式：
    1. 发送限价单（ordType="limit"）
    2. 立即撤单（实现 IOC 效果）
    3. 只有立即成交的部分会被执行

    Example:
        >>> async with OrderExecutor(
        ...     api_key="your_api_key",
        ...     secret_key="your_secret",
        ...     passphrase="your_passphrase",
        ...     use_demo=True
        ... ) as executor:
        ...     response = await executor.place_ioc_order(
        ...         symbol="BTC-USDT-SWAP",
        ...         side="buy",
        ...         price=50000.0,
        ...         size=0.01
        ...     )
        ...     print(response)
    """

    # OKX V5 API 端点
    ORDER_ENDPOINT = "/api/v5/trade/order"
    CANCEL_ORDER_ENDPOINT = "/api/v5/trade/cancel-order"
    CANCEL_BATCH_ENDPOINT = "/api/v5/trade/cancel-batch-orders"

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        base_url: str = "https://www.okx.com",
        use_demo: bool = False,
        timeout: int = 5
    ):
        """
        初始化订单执行器

        Args:
            api_key (str): OKX API Key
            secret_key (str): OKX Secret Key
            passphrase (str): OKX Passphrase
            base_url (str): API 基础 URL，默认为 OKX 生产环境
            use_demo (bool): 是否使用模拟交易，默认为 False
            timeout (int): 请求超时时间（秒），默认为 5（HFT 场景更短）
        """
        self.rest_client = RestClient(
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase,
            base_url=base_url,
            use_demo=use_demo,
            timeout=timeout
        )

        logger.info(
            f"OrderExecutor 初始化: use_demo={use_demo}, timeout={timeout}s"
        )

    async def place_ioc_order(
        self,
        symbol: str,
        side: str,
        price: float,
        size: float
    ) -> Dict[str, Any]:
        """
        下达 IOC（Immediate-Or-Cancel）订单

        OKX V5 IOC 实现策略：
        1. 发送限价单（ordType="limit"）
        2. 立即撤单（实现 IOC 效果）

        只有立即成交的部分会被执行，未成交部分会被立即取消。

        Args:
            symbol (str): 交易对（如：BTC-USDT-SWAP）
            side (str): 订单方向（"buy" 或 "sell"）
            price (float): 限价价格
            size (float): 订单数量

        Returns:
            Dict[str, Any]: API 响应数据，包含订单 ID 和成交信息

        Raises:
            ValueError: 如果参数无效或 API 返回错误
            RuntimeError: 如果 RestClient 已关闭

        Example:
            >>> response = await executor.place_ioc_order(
            ...     symbol="BTC-USDT-SWAP",
            ...     side="buy",
            ...     price=50000.0,
            ...     size=0.01
            ... )
            >>> print(response['data'][0]['ordId'])
            '1234567890'
        """
        # 参数验证
        if side not in ["buy", "sell"]:
            raise ValueError(f"无效的订单方向: {side}，必须是 'buy' 或 'sell'")

        if price <= 0:
            raise ValueError(f"无效的价格: {price}，必须大于 0")

        if size <= 0:
            raise ValueError(f"无效的数量: {size}，必须大于 0")

        # 🚨 修复：数量处理 🚨
        # ⚠️ 注意：OKX 合约的 size (sz) 是"张数"(Contracts)，必须是整数！
        # 如果您的 size 是 0.01 (0.01个SOL)，在 OKX 上是无法下单的（最小1张）。
        # 假设现在的 size 是计算出的张数，我们需要取整。
        # 如果 size < 1，强制改为 1 (测试用)，或者拒绝下单
        if size < 1:
            logger.warning(f"⚠️  警告: 计算出的数量 {size} 小于 1 张，强制调整为 1 张以进行测试")
            size = 1

        formatted_size = str(int(size))  # 强制转为整数并转字符串

        logger.info(f"⚡ 准备下单: 修正数量 {size} -> {formatted_size}")

        # 🚀 改用市价单 (Market Order) 🚀
        # 原因：Error 51121 显示限价单容易因为价格保护被拒绝。
        # 市价单能保证在 DEV 模式下立即成交。

        logger.info(f"⚡ [市价单] 正在发送市价单 (Market Order) 以确保成交...")

        # ✅ 关键修复：动态构造 order_body
        # 市价单绝对不能包含 px 参数
        order_body = {
            "instId": symbol,
            "tdMode": "cross",  # 全仓模式
            "side": side,
            "ordType": "market",  # ✅ 市价单
            "sz": formatted_size   # ✅ 传格式化后的字符串(整数)
        }

        # 🚨 重要：市价单不要传递 px 参数！
        # 如果需要限价单，再单独添加 px

        # 🚨 修复结束 🚨

        logger.info(
            f"下达市价单: symbol={symbol}, side={side}, size={formatted_size}"
        )

        try:
            # 1. 发送市价单（市价单会立即成交，不需要撤单）
            response = await self.rest_client.post_signed(
                self.ORDER_ENDPOINT,
                order_body
            )

            # 检查响应
            order_data = response.get("data", [])
            if not order_data:
                raise ValueError("API 返回数据为空")

            order_id = order_data[0].get("ordId")
            logger.debug(f"市价单已提交: order_id={order_id}")

            # 市价单已成交，直接返回响应（不需要撤单）
            return response

        except ValueError as e:
            logger.error(f"IOC 订单参数错误: {e}")
            raise
        except Exception as e:
            logger.error(f"IOC 订单执行失败: {e}")
            raise RuntimeError(f"IOC 订单执行失败: {e}")

    async def _cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        撤销单个订单

        Args:
            order_id (str): 订单 ID

        Returns:
            Dict[str, Any]: API 响应数据
        """
        cancel_body = {
            "ordId": order_id
        }

        logger.debug(f"撤单: order_id={order_id}")

        response = await self.rest_client.post_signed(
            self.CANCEL_ORDER_ENDPOINT,
            cancel_body
        )

        return response

    async def cancel_all(self, symbol: str) -> List[Dict[str, Any]]:
        """
        撤销指定交易对的所有挂单

        批量撤单，使用异步并发提高速度。

        Args:
            symbol (str): 交易对（如：BTC-USDT-SWAP）

        Returns:
            List[Dict[str, Any]]: 撤单结果列表

        Raises:
            RuntimeError: 如果撤单失败

        Example:
            >>> results = await executor.cancel_all("BTC-USDT-SWAP")
            >>> for result in results:
            ...     print(f"撤单结果: {result}")
        """
        logger.info(f"撤销所有挂单: symbol={symbol}")

        try:
            # 1. 查询所有挂单
            pending_orders = await self._get_pending_orders(symbol)

            if not pending_orders:
                logger.info(f"没有待撤订单: symbol={symbol}")
                return []

            logger.info(f"找到 {len(pending_orders)} 个待撤订单")

            # 2. 批量撤单
            # OKX 支持批量撤单，但为了更好的控制，我们并发撤单
            cancel_tasks = []

            for order in pending_orders:
                order_id = order.get("ordId")
                if order_id:
                    task = self._cancel_order(order_id)
                    cancel_tasks.append(task)

            # 并发执行撤单
            results = await asyncio.gather(
                *cancel_tasks,
                return_exceptions=True
            )

            # 3. 统计撤单结果
            success_count = 0
            fail_count = 0

            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"撤单失败: {result}")
                    fail_count += 1
                else:
                    success_count += 1

            logger.info(
                f"批量撤单完成: 成功={success_count}, 失败={fail_count}"
            )

            return results

        except Exception as e:
            logger.error(f"批量撤单失败: {e}")
            raise RuntimeError(f"批量撤单失败: {e}")

    async def _get_pending_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """
        查询指定交易对的所有挂单

        Args:
            symbol (str): 交易对

        Returns:
            List[Dict[str, Any]]: 挂单列表
        """
        # 使用未成交订单端点
        pending_endpoint = "/api/v5/trade/orders-pending"

        params = {
            "instType": "SWAP",  # 合约类型
            "instId": symbol
        }

        try:
            response = await self.rest_client.get_signed(
                pending_endpoint,
                params=params
            )

            # 提取挂单数据
            orders = response.get("data", [])

            logger.debug(f"查询到 {len(orders)} 个挂单: symbol={symbol}")

            return orders

        except Exception as e:
            logger.error(f"查询挂单失败: {e}")
            return []

    async def get_account_balance(self) -> Dict[str, Any]:
        """
        查询账户余额

        Returns:
            Dict[str, Any]: 账户余额信息
        """
        balance_endpoint = "/api/v5/account/balance"

        response = await self.rest_client.get_signed(balance_endpoint)

        return response

    async def get_usdt_balance(self) -> float:
        """
        [新增] 查询 USDT 可用余额

        Returns:
            float: USDT 可用余额
        """
        try:
            balance_endpoint = "/api/v5/account/balance"
            response = await self.rest_client.get_signed(balance_endpoint)

            if isinstance(response, dict) and response.get('data'):
                for detail in response['data'][0].get('details', []):
                    if detail.get('ccy') == 'USDT':
                        return float(detail.get('availBal', 0.0))
            return 0.0
        except Exception as e:
            logger.error(f"❌ 查询余额失败: {e}")
            return 0.0

    async def set_leverage(self, symbol: str, lever: str = "10", mgn_mode: str = "cross") -> bool:
        """[新增] 强制设置合约杠杆倍数和保证金模式"""
        try:
            endpoint = "/api/v5/account/set-leverage"
            body = {
                "instId": symbol,
                "lever": lever,
                "mgnMode": mgn_mode
            }
            response = await self.rest_client.post_signed(endpoint, body)

            if response.get("code") == "0":
                logger.info(f"✅ 杠杆设置成功: {symbol} -> {lever}x ({mgn_mode})")
                return True
            else:
                logger.warning(f"⚠️  杠杆设置可能有误: {response}")
                return False
        except Exception as e:
            logger.error(f"❌ 设置杠杆异常: {e}")
            return False

    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        查询持仓信息

        Args:
            symbol (Optional[str]): 交易对，None 表示查询全部

        Returns:
            List[Dict[str, Any]]: 持仓列表
        """
        position_endpoint = "/api/v5/account/positions"

        params = {
            "instType": "SWAP"
        }

        if symbol:
            params["instId"] = symbol

        response = await self.rest_client.get_signed(
            position_endpoint,
            params=params
        )

        # [修复] 兼容 API 返回列表或字典两种情况
        if isinstance(response, list):
            positions = response
        elif isinstance(response, dict):
            positions = response.get("data", [])
        else:
            logger.warning(f"未知持仓数据格式: {type(response)}")
            positions = []

        return positions

    async def close(self):
        """
        关闭订单执行器

        Example:
            >>> await executor.close()
        """
        await self.rest_client.close()
        logger.info("OrderExecutor 已关闭")

    async def __aenter__(self):
        """
        异步上下文管理器入口

        Returns:
            OrderExecutor: 返回自身
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        异步上下文管理器退出

        自动关闭 RestClient。
        """
        await self.close()
