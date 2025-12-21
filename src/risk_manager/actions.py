import os
import logging
import ccxt
from .config import get_config

logger = logging.getLogger(__name__)


async def emergency_close_position(symbol: str, side: str, postgres_pool, config=None) -> bool:
    """
    紧急平仓操作
    
    Args:
        symbol: 交易对符号
        side: 持仓方向 (buy/sell)
        postgres_pool: PostgreSQL 连接池
        config: 风控配置对象，如果为None则使用全局配置
        
    Returns:
        bool: True表示平仓成功，False表示失败
    """
    try:
        # 使用全局配置如果没有传入config
        if config is None:
            config = get_config()
        
        # 确定平仓方向（与持仓方向相反）
        close_side = 'sell' if side == 'buy' else 'buy'
        
        logger.critical(
            f"开始紧急平仓: symbol={symbol}, 持仓方向={side}, "
            f"平仓方向={close_side}"
        )
        
        # 从环境变量获取OKX风控API密钥
        okx_api_key = os.getenv('OKX_RISK_API_KEY')
        okx_secret = os.getenv('OKX_RISK_SECRET')
        okx_passphrase = os.getenv('OKX_RISK_PASSPHRASE')
        
        if not all([okx_api_key, okx_secret, okx_passphrase]):
            logger.critical("OKX风控API密钥未完整配置")
            return False
        
        # 实例化OKX客户端（仅使用风控密钥）
        try:
            # 使用统一的环境判断逻辑
            okx_environment = os.getenv("OKX_ENVIRONMENT", "production").lower()
            use_demo = okx_environment in ["demo", "demo环境", "demo-trading"]
            
            exchange = ccxt.okx({
                'apiKey': okx_api_key,
                'secret': okx_secret,
                'password': okx_passphrase,
                'sandbox': use_demo,
                'enableRateLimit': True,
            })
            
            logger.critical(f"OKX风控客户端初始化成功: {symbol}, 环境: {okx_environment}, 模拟模式: {use_demo}")
            
            logger.info(f"OKX风控客户端初始化成功: {symbol}")
            
        except Exception as e:
            logger.critical(f"OKX客户端初始化失败: {e}")
            return False
        
        # 查询当前持仓数量
        try:
            positions = exchange.fetch_positions([symbol])
            current_position = None
            
            for pos in positions:
                if (pos['symbol'] == symbol and 
                    pos['side'].lower() == side.lower() and 
                    float(pos['contracts']) > 0):
                    current_position = pos
                    break
            
            if not current_position:
                logger.critical(f"未找到持仓: symbol={symbol}, side={side}")
                return False
            
            position_size = abs(float(current_position['contracts']))
            logger.info(f"当前持仓数量: {position_size}")
            
        except Exception as e:
            logger.critical(f"查询持仓失败: {e}")
            return False
        
        # 执行市价平仓
        try:
            # 创建市价平仓订单
            close_order = exchange.create_market_order(
                symbol=symbol,
                side=close_side,
                amount=position_size
            )
            
            logger.critical(
                f"紧急平仓订单创建成功: order_id={close_order.get('id')}, "
                f"symbol={symbol}, side={close_side}, amount={position_size}"
            )
            
        except Exception as e:
            logger.critical(f"创建平仓订单失败: {e}")
            # 记录失败到数据库
            await _log_failed_close_to_db(
                symbol, side, close_side, position_size, 
                str(e), postgres_pool
            )
            return False
        
        # 记录成功的平仓操作到数据库
        try:
            await _log_successful_close_to_db(
                symbol, side, close_side, position_size, 
                close_order, postgres_pool
            )
            
            logger.critical(
                f"紧急平仓完成: symbol={symbol}, order_id={close_order.get('id')}, "
                f"filled_amount={close_order.get('filled', 0)}"
            )
            
            return True
            
        except Exception as e:
            logger.critical(f"记录平仓到数据库失败: {e}")
            return False
            
    except Exception as e:
        logger.critical(f"紧急平仓操作异常: {e}")
        return False


async def _log_successful_close_to_db(symbol: str, original_side: str, close_side: str, 
                                position_size: float, order: dict, postgres_pool) -> None:
    """
    记录成功的平仓操作到数据库
    
    Args:
        symbol: 交易对符号
        original_side: 原始持仓方向
        close_side: 平仓方向
        position_size: 平仓数量
        order: 平仓订单信息
        postgres_pool: 数据库连接池
    """
    insert_sql = """
    INSERT INTO trades (
        decision_id, order_id, symbol, side, order_type, amount, price, 
        status, reason, filled_amount, filled_price, fee, created_at
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW()
    )
    """
    
    await postgres_pool.execute(
        insert_sql,
        None,  # decision_id
        order.get('id'),
        symbol,
        close_side,
        'market',
        position_size,
        None,  # price (市价单)
        order.get('status', 'closed'),
        'RISK_FORCED_CLOSE',
        order.get('filled', 0),
        order.get('price', 0),
        order.get('fee', {}).get('cost', 0) if order.get('fee') else 0
    )


async def _log_failed_close_to_db(symbol: str, original_side: str, close_side: str, 
                             position_size: float, error_msg: str, postgres_pool) -> None:
    """
    记录失败的平仓操作到数据库
    
    Args:
        symbol: 交易对符号
        original_side: 原始持仓方向
        close_side: 平仓方向
        position_size: 平仓数量
        error_msg: 错误信息
        postgres_pool: 数据库连接池
    """
    insert_sql = """
    INSERT INTO trades (
        decision_id, order_id, symbol, side, order_type, amount, price, 
        status, reason, created_at
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, NOW()
    )
    """
    
    await postgres_pool.execute(
        insert_sql,
        None,  # decision_id
        f"FAILED_{symbol}_{original_side}",  # 生成一个失败订单ID
        symbol,
        close_side,
        'market',
        position_size,
        None,  # price
        'failed',
        f'RISK_FORCED_CLOSE_FAILED: {error_msg}'
    )


def get_current_position_size(symbol: str, side: str, exchange) -> float:
    """
    获取指定交易对的持仓数量
    
    Args:
        symbol: 交易对符号
        side: 持仓方向
        exchange: CCXT交易所实例
        
    Returns:
        float: 持仓数量，0表示无持仓
    """
    try:
        positions = exchange.fetch_positions([symbol])
        
        for pos in positions:
            if (pos['symbol'] == symbol and 
                pos['side'].lower() == side.lower() and 
                float(pos['contracts']) > 0):
                return abs(float(pos['contracts']))
        
        return 0.0
        
    except Exception as e:
        logger.error(f"获取持仓数量失败: {e}")
        return 0.0


def validate_emergency_close_params(symbol: str, side: str) -> bool:
    """
    验证紧急平仓参数
    
    Args:
        symbol: 交易对符号
        side: 持仓方向
        
    Returns:
        bool: True表示参数有效，False表示无效
    """
    if not symbol or not side:
        logger.error("紧急平仓参数无效: symbol和side不能为空")
        return False
    
    if side.lower() not in ['buy', 'sell']:
        logger.error(f"无效的持仓方向: {side}")
        return False
    
    return True
