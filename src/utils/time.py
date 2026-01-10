"""
时间工具模块

提供时间同步检查和时间戳生成功能，用于解决 API 签名时间戳问题。
"""

import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)


async def check_time_sync() -> dict:
    """
    检查系统时间是否与服务器时间同步

    通过查询多个 NTP 服务器和 OKX API 检查时间偏差。

    Returns:
        dict: 包含时间同步信息的字典
            - local_time: 本地时间
            - server_time: 服务器时间
            - time_offset: 时间偏差（秒）
            - is_synced: 是否同步（偏差小于 30 秒）
            - recommended_action: 建议操作

    Example:
        >>> result = await check_time_sync()
        >>> print(result['is_synced'])
        True
        >>> print(result['time_offset'])
        2.3
    """
    try:
        # 获取本地时间
        local_time = datetime.now(timezone.utc)
        logger.info(f"本地时间 (UTC): {local_time.isoformat()}")

        # 方法 1：通过 OKX API 获取服务器时间
        try:
            server_time = await get_okx_server_time()
            time_offset = (server_time - local_time).total_seconds()

            logger.info(f"OKX 服务器时间: {server_time.isoformat()}")
            logger.info(f"时间偏差: {time_offset:.2f} 秒")

            # 检查是否同步（偏差小于 30 秒）
            is_synced = abs(time_offset) < 30

            if not is_synced:
                logger.error(f"⚠️  时间不同步！偏差: {time_offset:.2f} 秒")
                logger.error("建议操作：")
                logger.error("  1. 检查系统时间设置")
                logger.error("  2. 同步系统时间（Windows: w32tm /resync）")
                logger.error("  3. 启用自动时间同步")
            else:
                logger.info("✅ 时间同步正常")

            return {
                'local_time': local_time,
                'server_time': server_time,
                'time_offset': time_offset,
                'is_synced': is_synced,
                'recommended_action': 'sync_time' if not is_synced else 'none'
            }

        except Exception as e:
            logger.warning(f"无法通过 OKX API 检查时间: {e}")
            # 返回默认值
            return {
                'local_time': local_time,
                'server_time': None,
                'time_offset': 0,
                'is_synced': True,  # 假设同步，避免阻塞
                'recommended_action': 'manual_check'
            }

    except Exception as e:
        logger.error(f"时间同步检查失败: {e}")
        return {
            'local_time': None,
            'server_time': None,
            'time_offset': 0,
            'is_synced': True,
            'recommended_action': 'error'
        }


async def get_okx_server_time() -> datetime:
    """
    获取 OKX 服务器时间

    Args:
        datetime: OKX 服务器时间（UTC）

    Raises:
        Exception: 网络请求失败
    """
    import time

    url = "https://www.okx.com/api/v5/public/time"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                # [修复] 强制将 API 返回的字符串时间戳转换为浮点数
                # OKX 返回的时间戳通常在 data[0]['ts'] 中
                try:
                    # 假设 response 结构为 {'code': '0', 'data': [{'ts': '167...'}]}
                    if isinstance(data, dict) and 'data' in data and len(data['data']) > 0:
                        server_ts_str = data['data'][0]['ts']
                        server_ts = float(server_ts_str) / 1000.0  # 转换为秒
                        # 转换为 UTC 时间
                        server_time = datetime.fromtimestamp(
                            server_ts,
                            tz=timezone.utc
                        )
                        return server_time
                    else:
                        # 兜底：如果格式不对，使用本地时间
                        logger.warning(f"OKX API 返回格式异常: {data}")
                        server_time = datetime.now(timezone.utc)
                        return server_time
                except Exception as e:
                    # 兜底：如果转换失败，使用本地时间
                    logger.warning(f"OKX API 时间戳转换失败: {e}")
                    server_time = datetime.now(timezone.utc)
                    return server_time
            else:
                raise Exception(f"HTTP 请求失败: {response.status}")


def get_timestamp() -> str:
    """
    获取 ISO 8601 格式的时间戳

    格式示例：2023-01-01T00:00:00.000Z

    Returns:
        str: ISO 8601 格式的时间戳字符串
    """
    # 强制使用 UTC 时间，精确到毫秒，符合 ISO 8601 格式
    dt = datetime.now(timezone.utc)
    # OKX 要求格式: YYYY-MM-DDThh:mm:ss.sssZ
    return dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def validate_timestamp(timestamp: str) -> bool:
    """
    验证时间戳是否有效

    Args:
        timestamp (str): ISO 8601 格式的时间戳

    Returns:
        bool: 时间戳是否有效

    Raises:
        ValueError: 时间戳格式无效
    """
    try:
        # 解析时间戳
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

        # 检查时间是否合理（不能是未来时间，不能太久以前）
        now = datetime.now(timezone.utc)
        max_future = timedelta(seconds=30)  # 允许最多未来 30 秒
        max_past = timedelta(hours=24)  # 允许最多过去 24 小时

        if dt - now > max_future:
            raise ValueError(f"时间戳是未来时间: {timestamp}")

        if now - dt > max_past:
            raise ValueError(f"时间戳过期: {timestamp}")

        return True

    except ValueError as e:
        raise ValueError(f"时间戳格式无效: {timestamp}, 错误: {e}")


async def sync_time_check_async():
    """
    异步时间同步检查（便捷函数）

    Example:
        >>> result = await sync_time_check_async()
        >>> if not result['is_synced']:
        ...     print("请先同步系统时间")
    """
    result = await check_time_sync()

    if not result['is_synced']:
        logger.error("=" * 60)
        logger.error("⚠️  时间不同步警告")
        logger.error("=" * 60)
        logger.error(f"本地时间: {result['local_time']}")
        logger.error(f"服务器时间: {result['server_time']}")
        logger.error(f"时间偏差: {result['time_offset']:.2f} 秒")
        logger.error("")
        logger.error("请先同步系统时间后重试：")
        logger.error("  Windows: 控制面板 → 日期和时间 → 立即同步")
        logger.error("  Linux: sudo ntpdate -s time.nist.gov")
        logger.error("  macOS: sudo sntp -sS time.apple.com")
        logger.error("=" * 60)
        raise Exception("系统时间未同步")

    return result
