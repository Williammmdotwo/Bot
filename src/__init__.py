"""
Athena Trader 微服务系统初始化模块
自动加载环境变量和配置
"""

import os
from dotenv import load_dotenv

# 自动加载 .env 文件中的环境变量
load_dotenv()

# 设置默认环境变量
os.environ.setdefault('USE_DATABASE', 'false')
os.environ.setdefault('REDIS_PASSWORD', '')
os.environ.setdefault('REDIS_HOST', 'localhost')
os.environ.setdefault('REDIS_PORT', '6379')

__version__ = "1.0.0"
__author__ = "Athena Trader Team"
