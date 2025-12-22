#!/usr/bin/env python3
"""
WebSocket修复验证脚本
测试OKX WebSocket连接和数据接收
"""

import sys
import os
import time
import logging
import asyncio
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.data_manager.websocket_client import OKXWebSocketClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def test_websocket_connection():
    """测试WebSocket连接和数据接收"""
    logger.info("🚀 开始测试WebSocket连接...")

    try:
        # 创建WebSocket客户端
        ws_client = OKXWebSocketClient(redis_client=None)

        # 显示连接配置
        status = ws_client.get_status()
        logger.info(f"📋 连接配置:")
        logger.info(f"   - 环境: {status['environment']}")
        logger.info(f"   - URL: {status['ws_url']}")
        logger.info(f"   - 交易对: {status['symbol']}")
        logger.info(f"   - 时间框架: {status['timeframe']}")

        # 连接到WebSocket
        logger.info("🔌 正在连接到OKX WebSocket...")
        connected = await ws_client.connect()

        if connected:
            logger.info("✅ WebSocket连接成功!")

            # 等待数据接收
            logger.info("⏳ 等待数据接收（30秒）...")
            start_time = time.time()

            while time.time() - start_time < 30:  # 等待30秒
                if ws_client.last_data_time:
                    time_since_data = time.time() - ws_client.last_data_time
                    logger.info(f"📊 收到数据! 距离最后数据: {time_since_data:.1f}秒")
                    break

                await asyncio.sleep(2)

            # 检查结果
            if ws_client.last_data_time:
                logger.info("🎉 测试成功! WebSocket正常接收数据")
                return True
            else:
                logger.warning("⚠️  测试失败! 30秒内未收到任何数据")
                return False
        else:
            logger.error("❌ WebSocket连接失败!")
            return False

    except Exception as e:
        logger.error(f"❌ 测试过程中发生错误: {e}")
        return False
    finally:
        # 清理连接
        try:
            await ws_client.disconnect()
            logger.info("🧹 WebSocket连接已断开")
        except Exception as e:
            logger.error(f"断开连接时出错: {e}")

def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("🔧 OKX WebSocket修复验证测试")
    logger.info("=" * 60)

    # 显示修复内容
    logger.info("🔨 已应用的修复:")
    logger.info("   1. ✅ 修复频道名称: tickers5m → candle5m")
    logger.info("   2. ✅ 增强错误处理: 检测OKX错误消息")
    logger.info("   3. ✅ 修复数据处理: 新增_process_candle_data方法")
    logger.info("   4. ✅ 改进消息处理: 支持K线数组格式")
    logger.info("")

    # 运行测试
    try:
        # 运行异步测试
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        result = loop.run_until_complete(test_websocket_connection())

        logger.info("")
        logger.info("=" * 60)
        if result:
            logger.info("🎯 测试结果: 成功! WebSocket修复有效")
            logger.info("💡 现在应该能正常接收K线数据了")
        else:
            logger.info("🎯 测试结果: 失败! 需要进一步调试")
            logger.info("💡 请检查:")
            logger.info("   - 网络连接")
            logger.info("   - API凭据配置")
            logger.info("   - OKX服务状态")
        logger.info("=" * 60)

    except KeyboardInterrupt:
        logger.info("⏹️ 用户中断测试")
    except Exception as e:
        logger.error(f"❌ 测试执行失败: {e}")
    finally:
        try:
            loop.close()
        except:
            pass

if __name__ == "__main__":
    main()
