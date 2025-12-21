import logging
import threading
import time
import json
import asyncio
from typing import Dict, Any, Optional
import redis
import os
# Fix relative imports for direct execution
try:
    from .config import get_config
    from .actions import emergency_close_position
    from .api_server import app
except ImportError:
    from src.risk_manager.config import get_config
    from src.risk_manager.actions import emergency_close_position
    from src.risk_manager.api_server import app

logger = logging.getLogger(__name__)


class RiskManager:
    """风控管理器"""
    
    def __init__(self):
        """初始化风控管理器"""
        try:
            # 加载配置
            self.config = get_config()
            logger.info("风控配置加载完成")
            
            # 连接 Redis
            self.redis_client = self._connect_redis()
            logger.info("Redis 连接建立")
            
            # 初始化持仓监控集合
            self.monitored_positions: Dict[str, Dict[str, Any]] = {}
            
            # 线程控制
            self._stop_event = threading.Event()
            self._listener_thread = None
            
            # PostgreSQL 连接池（将在外部注入）
            self.postgres_pool = None
            
            # 防止重复警告的标志
            self._db_warning_shown = False
            
            logger.info("风控管理器初始化完成")
            
        except Exception as e:
            logger.error(f"风控管理器初始化失败: {e}")
            raise
    
    def _connect_redis(self) -> Optional[redis.Redis]:
        """连接 Redis"""
        try:
            # Check if Redis is disabled for testing
            if os.getenv('DISABLE_REDIS', 'false').lower() == 'true':
                logger.warning("Redis disabled by DISABLE_REDIS=true")
                return None
                
            # 优先从 REDIS_URL 环境变量解析
            redis_url = os.getenv('REDIS_URL')
            if redis_url:
                logger.info(f"使用 REDIS_URL 连接 Redis: {redis_url}")
                client = redis.from_url(redis_url, decode_responses=True)
            else:
                # 从环境变量获取连接信息
                redis_config = {
                    'host': os.getenv('REDIS_HOST', 'redis'),  # Docker服务名
                    'port': int(os.getenv('REDIS_PORT', 6379)),
                    'password': os.getenv('REDIS_PASSWORD'),
                    'decode_responses': True,
                    'socket_connect_timeout': 5,
                    'socket_timeout': 5,
                    'retry_on_timeout': True,
                    'health_check_interval': 30
                }
                logger.info(f"使用配置连接 Redis: {redis_config['host']}:{redis_config['port']}")
                client = redis.Redis(**redis_config)
            
            client.ping()  # 测试连接
            logger.info("Redis 连接成功")
            return client
            
        except Exception as e:
            logger.warning(f"Redis 连接失败，继续运行: {e}")
            return None
    
    def set_postgres_pool(self, pool):
        """设置 PostgreSQL 连接池"""
        self.postgres_pool = pool
    
    def start_listener(self):
        """启动 Redis 监听线程"""
        if not self.redis_client:
            logger.warning("Redis not available, skipping listener startup")
            return
            
        if self._listener_thread and self._listener_thread.is_alive():
            logger.warning("监听线程已在运行")
            return
        
        self._stop_event.clear()
        self._listener_thread = threading.Thread(
            target=self._redis_listener_loop,
            daemon=True,
            name="risk-listener"
        )
        self._listener_thread.start()
        logger.info("Redis 监听线程启动")
    
    def _redis_listener_loop(self):
        """Redis 监听循环"""
        while not self._stop_event.is_set():
            try:
                # 创建 pubsub 连接
                pubsub = self.redis_client.pubsub()
                pubsub.subscribe('new_position_opened')
                logger.info("订阅 new_position_opened 频道")
                
                # 监听消息
                for message in pubsub.listen():
                    if self._stop_event.is_set():
                        break
                    
                    if message['type'] == 'message':
                        self._handle_new_position(message)
                        
            except redis.ConnectionError as e:
                logger.error(f"Redis 连接错误: {e}")
                time.sleep(5)  # 等待后重连
            except Exception as e:
                logger.error(f"监听循环异常: {e}")
                time.sleep(5)
    
    def _handle_new_position(self, message):
        """处理新持仓消息"""
        try:
            # 解析消息
            data = json.loads(message['data'])
            symbol = data.get('symbol')
            
            if not symbol:
                logger.warning(f"收到无效持仓消息: {data}")
                return
            
            # 更新持仓监控
            self.monitored_positions[symbol] = {
                'symbol': data.get('symbol'),
                'side': data.get('side'),
                'size': data.get('size'),
                'entry_price': data.get('entry_price'),
                'timestamp': data.get('timestamp'),
                'last_check': time.time()
            }
            
            logger.info(f"新增监控持仓: {symbol}, 详情: {self.monitored_positions[symbol]}")
            
        except json.JSONDecodeError as e:
            logger.error(f"持仓消息解析失败: {e}, 原始消息: {message}")
        except Exception as e:
            logger.error(f"处理新持仓异常: {e}")
    
    def run_position_checks(self):
        """运行持仓级风控检查 (Level 2)"""
        use_database = os.getenv('USE_DATABASE', 'false').lower() == 'true'
        if not self.postgres_pool and use_database:
            logger.error("PostgreSQL 连接池未设置")
            return
        if not use_database:
            if not self._db_warning_shown:
                logger.info("数据库功能已禁用，跳过持仓检查")
                self._db_warning_shown = True
            return
        
        positions_to_remove = []
        
        for symbol, position in self.monitored_positions.items():
            try:
                # 检查强制止损和止盈
                should_close, reason = self._check_position_limits(position)
                
                if should_close:
                    logger.critical(f"触发持仓风控: {symbol}, 原因: {reason}")
                    
                    # 执行紧急平仓
                    success = asyncio.run(emergency_close_position(
                        symbol=symbol,
                        side=position['side'],
                        postgres_pool=self.postgres_pool,
                        config=self.config
                    ))
                    
                    if success:
                        positions_to_remove.append(symbol)
                        logger.info(f"持仓 {symbol} 紧急平仓成功")
                    else:
                        logger.error(f"持仓 {symbol} 紧急平仓失败")
                
                # 更新检查时间
                position['last_check'] = time.time()
                
            except Exception as e:
                logger.error(f"检查持仓 {symbol} 异常: {e}")
        
        # 清理已平仓的持仓
        for symbol in positions_to_remove:
            del self.monitored_positions[symbol]
        
        # 清理过期持仓（超过1小时未更新）
        current_time = time.time()
        expired_positions = [
            symbol for symbol, position in self.monitored_positions.items()
            if current_time - position.get('last_check', 0) > 3600
        ]
        
        for symbol in expired_positions:
            del self.monitored_positions[symbol]
            logger.info(f"清理过期持仓: {symbol}")
    
    def _check_position_limits(self, position: Dict[str, Any]) -> tuple[bool, str]:
        """检查持仓限制"""
        try:
            # 这里应该获取当前价格来检查止损止盈
            # 简化实现，实际需要从交易所API获取当前价格
            current_price = position.get('entry_price', 0)  # 临时使用开仓价
            
            entry_price = position.get('entry_price', 0)
            side = position.get('side', '')
            
            if side == 'buy':
                # 买单：当前价格低于止损价或高于止盈价
                stop_loss_price = entry_price * (1 + self.config.risk_limits.mandatory_stop_loss_percent)
                take_profit_price = entry_price * (1 + self.config.risk_limits.mandatory_take_profit_percent)
                
                if current_price <= stop_loss_price:
                    return True, f"触发强制止损: {current_price} <= {stop_loss_price}"
                elif current_price >= take_profit_price:
                    return True, f"触发强制止盈: {current_price} >= {take_profit_price}"
                    
            else:  # sell
                # 卖单：当前价格高于止损价或低于止盈价
                stop_loss_price = entry_price * (1 - self.config.risk_limits.mandatory_stop_loss_percent)
                take_profit_price = entry_price * (1 - self.config.risk_limits.mandatory_take_profit_percent)
                
                if current_price >= stop_loss_price:
                    return True, f"触发强制止损: {current_price} >= {stop_loss_price}"
                elif current_price <= take_profit_price:
                    return True, f"触发强制止盈: {current_price} <= {take_profit_price}"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"检查持仓限制异常: {e}")
            return False, f"检查异常: {e}"
    
    def run_account_checks(self):
        """运行账户级风控检查 (Level 3)"""
        use_database = os.getenv('USE_DATABASE', 'false').lower() == 'true'
        if not self.postgres_pool and use_database:
            logger.error("PostgreSQL 连接池未设置")
            return
        if not use_database:
            if not self._db_warning_shown:
                logger.info("数据库功能已禁用，跳过账户检查")
                self._db_warning_shown = True
            return
        
        try:
            # 获取当前账户权益（需要从交易所API获取）
            current_equity = self._get_current_equity()
            if current_equity <= 0:
                logger.error("无法获取当前账户权益")
                return
            
            # 检查最大回撤
            max_drawdown_check = self._check_max_drawdown(current_equity)
            if max_drawdown_check[0]:
                self._trigger_circuit_breaker(f"最大回撤超限: {max_drawdown_check[1]}")
                return
            
            # 检查日内亏损
            daily_loss_check = self._check_daily_loss(current_equity)
            if daily_loss_check[0]:
                self._trigger_circuit_breaker(f"日内亏损超限: {daily_loss_check[1]}")
                return
            
            logger.info(f"账户级风控检查通过: 当前权益 {current_equity}")
            
        except Exception as e:
            logger.error(f"账户级风控检查异常: {e}")
    
    def _get_current_equity(self) -> float:
        """获取当前账户权益"""
        # 这里应该从交易所API获取，简化实现
        # 实际需要集成交易所客户端
        return 10000.0  # 临时返回固定值
    
    def _check_max_drawdown(self, current_equity: float) -> tuple[bool, str]:
        """检查最大回撤"""
        try:
            # 从数据库获取历史最高权益
            # 简化实现，实际需要查询数据库
            historical_max_equity = 12000.0  # 临时值
            
            if historical_max_equity <= 0:
                return False, "无历史数据"
            
            drawdown_percent = (historical_max_equity - current_equity) / historical_max_equity
            
            if drawdown_percent > self.config.risk_limits.max_drawdown_percent:
                return True, f"回撤 {drawdown_percent:.4f} > {self.config.risk_limits.max_drawdown_percent}"
            
            return False, f"回撤 {drawdown_percent:.4f} <= {self.config.risk_limits.max_drawdown_percent}"
            
        except Exception as e:
            logger.error(f"检查最大回撤异常: {e}")
            return False, f"检查异常: {e}"
    
    def _check_daily_loss(self, current_equity: float) -> tuple[bool, str]:
        """检查日内亏损"""
        try:
            # 从数据库获取昨日收盘权益
            # 简化实现，实际需要查询数据库
            yesterday_close_equity = 10500.0  # 临时值
            
            if yesterday_close_equity <= 0:
                return False, "无昨日数据"
            
            daily_loss_percent = (yesterday_close_equity - current_equity) / yesterday_close_equity
            
            # 假设日内亏损限制为 5%
            daily_loss_limit = 0.05
            if daily_loss_percent > daily_loss_limit:
                return True, f"日内亏损 {daily_loss_percent:.4f} > {daily_loss_limit}"
            
            return False, f"日内亏损 {daily_loss_percent:.4f} <= {daily_loss_limit}"
            
        except Exception as e:
            logger.error(f"检查日内亏损异常: {e}")
            return False, f"检查异常: {e}"
    
    def _trigger_circuit_breaker(self, reason: str):
        """触发熔断"""
        try:
            # 在 Redis 中设置熔断标志，有效期 1 小时
            if self.redis_client:
                self.redis_client.setex(
                    'risk:circuit_breaker',
                    3600,  # 1 小时过期
                    json.dumps({
                        'triggered': True,
                        'reason': reason,
                        'timestamp': time.time()
                    })
                )
            
            logger.critical(f"触发熔断: {reason}")
            
        except Exception as e:
            logger.error(f"设置熔断标志失败: {e}")
    
    def stop(self):
        """停止风控管理器"""
        logger.info("正在停止风控管理器...")
        
        # 设置停止事件
        self._stop_event.set()
        
        # 等待监听线程结束
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=10)
            if self._listener_thread.is_alive():
                logger.warning("监听线程未能在超时时间内停止")
            else:
                logger.info("监听线程已停止")
        
        # 关闭 Redis 连接
        try:
            if self.redis_client:
                self.redis_client.close()
                logger.info("Redis 连接已关闭")
        except Exception as e:
            logger.error(f"关闭 Redis 连接失败: {e}")
        
        logger.info("风控管理器已停止")


# 全局风控管理器实例
_risk_manager = None

def get_risk_manager() -> RiskManager:
    """获取全局风控管理器实例"""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager


if __name__ == "__main__":
    import logging
    import os
    import time
    import signal
    import sys
    import threading
    import uvicorn
    try:
        from .api_server import app
    except ImportError:
        from src.risk_manager.api_server import app
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Starting Risk Manager Service...")
    
    # Create risk manager instance
    risk_manager = get_risk_manager()
    
    def signal_handler(signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        risk_manager.stop()
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    def run_risk_manager():
        """运行风控管理器的后台线程"""
        try:
            # Start the risk manager
            risk_manager.start_listener()
            
            # Main monitoring loop
            logger.info("Risk Manager started successfully")
            while not risk_manager._stop_event.is_set():
                try:
                    # Run position checks every 10 seconds
                    risk_manager.run_position_checks()
                    
                    # Run account checks every 30 seconds
                    if int(time.time()) % 30 == 0:
                        risk_manager.run_account_checks()
                    
                    time.sleep(10)
                    
                except Exception as e:
                    logger.error(f"Error in monitoring loop: {e}")
                    time.sleep(5)  # Wait before retrying
                    
        except Exception as e:
            logger.error(f"Risk Manager failed: {e}")
    
    try:
        # Start risk manager in background thread
        risk_thread = threading.Thread(target=run_risk_manager, daemon=True)
        risk_thread.start()
        
        # Start FastAPI server
        logger.info("Starting Risk Manager API server on port 8001...")
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8001,
            log_level="info"
        )
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Risk Manager Service failed: {e}")
        raise
    finally:
        risk_manager.stop()
        logger.info("Risk Manager Service stopped")
