import os
import asyncio
import threading
import logging
from typing import Optional
import asyncpg
import redis
from redis.connection import ConnectionPool
from .config_loader import ConfigManager

logger = logging.getLogger(__name__)

# 模块级变量（单例实现）
_config_manager: Optional[ConfigManager] = None
_postgres_pool: Optional[asyncpg.Pool] = None
_redis_client: Optional[redis.Redis] = None
_redis_pool: Optional[ConnectionPool] = None

# 线程安全锁
_init_lock = threading.Lock()


def get_config_manager() -> ConfigManager:
    """获取全局单例的 ConfigManager 实例"""
    global _config_manager
    
    if _config_manager is None:
        with _init_lock:
            if _config_manager is None:
                _config_manager = ConfigManager()
                logger.info("ConfigManager 实例已创建")
    
    return _config_manager


def get_postgres_pool() -> asyncpg.Pool:
    """获取全局单例的 asyncpg 连接池实例"""
    global _postgres_pool
    
    if _postgres_pool is None:
        with _init_lock:
            if _postgres_pool is None:
                _postgres_pool = _create_postgres_pool()
                logger.info("PostgreSQL 连接池已创建")
    
    return _postgres_pool


def get_redis_client() -> redis.Redis:
    """获取全局单例的 redis 客户端实例"""
    global _redis_client, _redis_pool
    
    if _redis_client is None:
        with _init_lock:
            if _redis_client is None:
                _redis_pool = _create_redis_pool()
                _redis_client = redis.Redis(connection_pool=_redis_pool)
                logger.info("Redis 客户端已创建")
    
    return _redis_client


def _create_postgres_pool() -> asyncpg.Pool:
    """创建 PostgreSQL 连接池"""
    try:
        # 获取配置
        config = get_config_manager().get_config()
        db_config = config.get('database', {})
        
        # 构建连接参数
        connection_params = {
            'host': os.getenv('DB_HOST', db_config.get('host', 'localhost')),
            'port': int(os.getenv('DB_PORT', str(db_config.get('port', 5432)))),
            'user': os.getenv('DB_USER', db_config.get('user', 'postgres')),
            'password': os.getenv('DB_PASSWORD', db_config.get('password', '')),
            'database': os.getenv('DB_NAME', db_config.get('database', 'athena_trader')),
            'min_size': db_config.get('min_connections', 5),
            'max_size': db_config.get('max_connections', 20),
            'max_queries': db_config.get('max_queries_per_connection', 50000),
            'max_inactive_connection_lifetime': db_config.get('max_inactive_connection_lifetime', 300),
            'command_timeout': db_config.get('command_timeout', 60),
            'server_settings': {
                'application_name': 'athena_trader',
                'timezone': 'UTC'
            }
        }
        
        # 验证必需参数
        if not connection_params['password']:
            logger.critical("数据库密码未配置")
            exit(1)
        
        logger.info(f"创建 PostgreSQL 连接池: {connection_params['host']}:{connection_params['port']}/{connection_params['database']}")
        
        # 创建连接池
        pool = asyncio.run(_create_pool_async(connection_params))
        return pool
        
    except Exception as e:
        logger.critical(f"创建 PostgreSQL 连接池失败: {e}")
        exit(1)


async def _create_pool_async(connection_params: dict) -> asyncpg.Pool:
    """异步创建连接池"""
    return await asyncpg.create_pool(**connection_params)


def _create_redis_pool() -> ConnectionPool:
    """创建 Redis 连接池"""
    try:
        # 获取配置
        config = get_config_manager().get_config()
        redis_config = config.get('redis', {})
        
        # 构建连接参数
        connection_params = {
            'host': os.getenv('REDIS_HOST', redis_config.get('host', 'localhost')),
            'port': int(os.getenv('REDIS_PORT', str(redis_config.get('port', 6379)))),
            'password': os.getenv('REDIS_PASSWORD', redis_config.get('password', None)),
            'db': int(os.getenv('REDIS_DB', str(redis_config.get('db', 0)))),
            'max_connections': redis_config.get('max_connections', 20),
            'retry_on_timeout': redis_config.get('retry_on_timeout', True),
            'socket_connect_timeout': redis_config.get('socket_connect_timeout', 5),
            'socket_timeout': redis_config.get('socket_timeout', 5),
            'health_check_interval': redis_config.get('health_check_interval', 30),
            'decode_responses': True
        }
        
        logger.info(f"创建 Redis 连接池: {connection_params['host']}:{connection_params['port']}/{connection_params['db']}")
        
        # 创建连接池
        pool = ConnectionPool(**connection_params)
        return pool
        
    except Exception as e:
        logger.critical(f"创建 Redis 连接池失败: {e}")
        exit(1)


async def test_connections():
    """测试所有连接"""
    try:
        # 测试 PostgreSQL
        logger.info("测试 PostgreSQL 连接...")
        pool = get_postgres_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval('SELECT 1')
            if result == 1:
                logger.info("PostgreSQL 连接测试成功")
            else:
                logger.error("PostgreSQL 连接测试失败")
        
        # 测试 Redis
        logger.info("测试 Redis 连接...")
        redis_client = get_redis_client()
        redis_result = redis_client.ping()
        if redis_result:
            logger.info("Redis 连接测试成功")
        else:
            logger.error("Redis 连接测试失败")
            
    except Exception as e:
        logger.error(f"连接测试失败: {e}")


async def close_connections():
    """关闭所有连接"""
    try:
        global _postgres_pool, _redis_client, _redis_pool
        
        # 关闭 PostgreSQL 连接池
        if _postgres_pool:
            await _postgres_pool.close()
            _postgres_pool = None
            logger.info("PostgreSQL 连接池已关闭")
        
        # 关闭 Redis 连接
        if _redis_client:
            _redis_client.close()
            _redis_client = None
            logger.info("Redis 客户端已关闭")
        
        # 关闭 Redis 连接池
        if _redis_pool:
            _redis_pool.disconnect()
            _redis_pool = None
            logger.info("Redis 连接池已关闭")
            
    except Exception as e:
        logger.error(f"关闭连接失败: {e}")


def reset_dependencies():
    """重置所有依赖（主要用于测试）"""
    global _config_manager, _postgres_pool, _redis_client, _redis_pool
    
    with _init_lock:
        _config_manager = None
        _postgres_pool = None
        _redis_client = None
        _redis_pool = None
        
        logger.info("所有依赖已重置")


def get_dependency_status() -> dict:
    """获取依赖状态"""
    return {
        'config_manager': _config_manager is not None,
        'postgres_pool': _postgres_pool is not None,
        'redis_client': _redis_client is not None,
        'redis_pool': _redis_pool is not None
    }


if __name__ == '__main__':
    # 测试依赖注入
    from .logging_config import setup_logging
    
    setup_logging()
    
    async def main():
        try:
            # 测试连接
            await test_connections()
            
            # 显示状态
            status = get_dependency_status()
            logger.info(f"依赖状态: {status}")
            
        finally:
            # 清理连接
            await close_connections()
    
    asyncio.run(main())
