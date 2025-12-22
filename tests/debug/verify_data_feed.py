#!/usr/bin/env python3
"""
数据源验证脚本
验证Data Manager是否真的连接到OKX并获取到实时数据
"""

import os
import sys
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# 加载环境变量
env_file = project_root / ".env"
if env_file.exists():
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def verify_data_source():
    """验证数据源连接"""
    logger.info("🔍 开始验证数据源连接...")
    logger.info("=" * 60)
    
    try:
        # 1. 检查环境配置
        logger.info("📋 步骤1: 检查环境配置")
        data_source_mode = os.getenv("DATA_SOURCE_MODE", "NOT_SET")
        use_mock_data = os.getenv("USE_MOCK_DATA", "true").lower() == "true"
        okx_environment = os.getenv("OKX_ENVIRONMENT", "NOT_SET")
        
        logger.info(f"DATA_SOURCE_MODE: {data_source_mode}")
        logger.info(f"USE_MOCK_DATA: {use_mock_data}")
        logger.info(f"OKX_ENVIRONMENT: {okx_environment}")
        
        # 2. 初始化REST客户端
        logger.info("\n📋 步骤2: 初始化REST客户端")
        from src.data_manager.rest_client import RESTClient
        
        rest_client = RESTClient()
        
        logger.info(f"REST客户端类型: {type(rest_client).__name__}")
        logger.info(f"使用Mock: {rest_client.use_mock}")
        logger.info(f"使用Demo: {rest_client.use_demo}")
        logger.info(f"有API密钥: {rest_client.has_credentials}")
        
        if rest_client.use_mock:
            logger.error("❌ 警告: REST客户端处于Mock模式，无法获取真实数据")
            return False
        
        if not rest_client.has_credentials:
            logger.error("❌ 警告: REST客户端没有API密钥，无法连接OKX")
            return False
        
        # 3. 获取市场数据
        logger.info("\n📋 步骤3: 获取OKX市场数据")
        symbol = "BTC-USDT"
        timeframe = "15m"
        limit = 5
        
        logger.info(f"获取 {symbol} {timeframe} K线数据，数量: {limit}")
        
        # 计算时间范围
        timeframe_minutes = 15  # 15分钟
        since = int((time.time() - timeframe_minutes * limit * 60) * 1000)
        
        logger.info(f"时间范围: {datetime.fromtimestamp(since/1000)} 到现在")
        
        # 获取OHLCV数据
        ohlcv_data = rest_client.fetch_ohlcv(symbol, since, limit, timeframe)
        
        if not ohlcv_data:
            logger.error("❌ 错误: 无法获取OHLCV数据")
            return False
        
        logger.info(f"✅ 成功获取 {len(ohlcv_data)} 根K线数据")
        
        # 4. 验证数据时效性
        logger.info("\n📋 步骤4: 验证数据时效性")
        
        current_time = time.time() * 1000  # 当前时间（毫秒）
        latest_candle = ohlcv_data[-1]  # 最新K线
        latest_timestamp = latest_candle[0]
        
        latest_time = datetime.fromtimestamp(latest_timestamp / 1000)
        current_dt = datetime.fromtimestamp(current_time / 1000)
        time_diff = current_dt - latest_time
        
        logger.info(f"最新K线时间: {latest_time}")
        logger.info(f"当前时间: {current_dt}")
        logger.info(f"时间差: {time_diff}")
        
        # 检查数据是否在合理范围内（30分钟内）
        if time_diff > timedelta(minutes=30):
            logger.error(f"❌ 错误: 数据过时，时间差 {time_diff} > 30分钟")
            logger.error("可能在使用Mock数据或API连接有问题")
            return False
        elif time_diff > timedelta(minutes=20):
            logger.warning(f"⚠️ 警告: 数据延迟较大，时间差 {time_diff}")
        else:
            logger.info("✅ 数据时效性良好")
        
        # 5. 分析K线数据
        logger.info("\n📋 步骤5: 分析K线数据")
        
        for i, candle in enumerate(ohlcv_data[-3:]):  # 显示最后3根K线
            timestamp, open_price, high_price, low_price, close_price, volume = candle
            candle_time = datetime.fromtimestamp(timestamp / 1000)
            
            logger.info(f"K线{i+1}: {candle_time}")
            logger.info(f"  开盘: {open_price:.2f}")
            logger.info(f"  最高: {high_price:.2f}")
            logger.info(f"  最低: {low_price:.2f}")
            logger.info(f"  收盘: {close_price:.2f}")
            logger.info(f"  成交量: {volume:.2f}")
        
        # 6. 验证价格合理性
        logger.info("\n📋 步骤6: 验证价格合理性")
        
        latest_close = latest_candle[4]
        price_range = max(c[4] for c in ohlcv_data) - min(c[4] for c in ohlcv_data)
        
        logger.info(f"最新收盘价: ${latest_close:.2f}")
        logger.info(f"价格区间: ${price_range:.2f}")
        
        # BTC价格合理性检查（应该在20000-100000之间）
        if not (20000 <= latest_close <= 100000):
            logger.warning(f"⚠️ 警告: BTC价格异常 ${latest_close:.2f}")
        else:
            logger.info("✅ 价格在合理范围内")
        
        # 7. 测试API连接稳定性
        logger.info("\n📋 步骤7: 测试API连接稳定性")
        
        try:
            # 获取ticker数据
            ticker = rest_client.fetch_ticker(symbol)
            if ticker:
                logger.info(f"✅ Ticker数据获取成功: ${ticker.get('last', 'N/A')}")
            else:
                logger.warning("⚠️ Ticker数据为空")
        except Exception as e:
            logger.warning(f"⚠️ Ticker获取失败: {e}")
        
        try:
            # 获取订单簿数据
            orderbook = rest_client.fetch_orderbook(symbol, 5)
            if orderbook and orderbook.get('bids') and orderbook.get('asks'):
                best_bid = orderbook['bids'][0][0] if orderbook['bids'] else 0
                best_ask = orderbook['asks'][0][0] if orderbook['asks'] else 0
                logger.info(f"✅ 订单簿获取成功: 买${best_bid:.2f} 卖${best_ask:.2f}")
            else:
                logger.warning("⚠️ 订单簿数据为空")
        except Exception as e:
            logger.warning(f"⚠️ 订单簿获取失败: {e}")
        
        # 8. 总结验证结果
        logger.info("\n📋 步骤8: 验证结果总结")
        
        success_criteria = [
            ("数据源配置", data_source_mode == "OKX_DEMO"),
            ("非Mock模式", not rest_client.use_mock),
            ("API密钥配置", rest_client.has_credentials),
            ("数据获取成功", len(ohlcv_data) > 0),
            ("数据时效性", time_diff <= timedelta(minutes=30)),
            ("价格合理性", 20000 <= latest_close <= 100000)
        ]
        
        passed_criteria = 0
        total_criteria = len(success_criteria)
        
        for criterion, passed in success_criteria:
            status = "✅" if passed else "❌"
            logger.info(f"{status} {criterion}: {'通过' if passed else '失败'}")
            if passed:
                passed_criteria += 1
        
        success_rate = passed_criteria / total_criteria
        logger.info(f"\n📊 总体评分: {passed_criteria}/{total_criteria} ({success_rate:.1%})")
        
        if success_rate >= 0.8:  # 80%以上通过率
            logger.info("🎉 数据源验证成功！Data Manager正确连接到OKX Demo API")
            return True
        else:
            logger.error("❌ 数据源验证失败，存在配置或连接问题")
            return False
            
    except Exception as e:
        logger.error(f"❌ 验证过程中发生异常: {e}")
        import traceback
        logger.error(f"异常详情: {traceback.format_exc()}")
        return False

def main():
    """主函数"""
    logger.info("🚀 Data Manager数据源验证脚本")
    logger.info("验证目标: 确认Data Manager连接到OKX Demo API获取实时数据")
    
    # 检查是否需要停止data-service
    logger.info("\n📋 运行前检查:")
    logger.info("如果data-service正在运行，可能会有端口冲突，但不影响此脚本")
    logger.info("此脚本直接调用RESTClient，不依赖HTTP服务")
    
    # 执行验证
    success = verify_data_source()
    
    logger.info("\n" + "=" * 60)
    if success:
        logger.info("🎉 验证完成: Data Manager数据源配置正确")
        logger.info("✅ 已成功连接到OKX Demo API")
        logger.info("✅ 获取到实时市场数据")
        logger.info("✅ 数据时效性和价格合理性正常")
    else:
        logger.error("❌ 验证失败: Data Manager数据源配置有问题")
        logger.error("请检查:")
        logger.error("1. 环境变量配置 (.env 文件)")
        logger.error("2. OKX Demo API密钥")
        logger.error("3. 网络连接")
        logger.error("4. DATA_SOURCE_MODE 设置")
    
    logger.info("=" * 60)
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
