#!/usr/bin/env python3
"""
配置迁移脚本 - 从旧配置系统迁移到新的统一配置系统
"""

import os
import json
import shutil
import logging
from datetime import datetime

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConfigMigrator:
    """配置迁移器"""
    
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.config_dir = os.path.join(project_root, 'config')
        self.backup_dir = os.path.join(project_root, 'config_backup')
        
    def backup_existing_configs(self):
        """备份现有配置文件"""
        logger.info("开始备份现有配置文件...")
        
        # 创建备份目录
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # 备份文件列表
        backup_files = [
            'config.json',
            'risk_config_example.json',
            '../tests/test_config.json',
            '../.env'
        ]
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_subdir = os.path.join(self.backup_dir, f'backup_{timestamp}')
        os.makedirs(backup_subdir, exist_ok=True)
        
        for file_path in backup_files:
            source_path = os.path.join(self.config_dir, file_path)
            if os.path.exists(source_path):
                dest_path = os.path.join(backup_subdir, os.path.basename(file_path))
                shutil.copy2(source_path, dest_path)
                logger.info(f"已备份: {source_path} -> {dest_path}")
        
        logger.info(f"配置文件备份完成，备份位置: {backup_subdir}")
        return backup_subdir
    
    def migrate_old_config_json(self):
        """迁移旧的 config.json"""
        old_config_path = os.path.join(self.config_dir, 'config.json')
        
        if not os.path.exists(old_config_path):
            logger.warning("未找到旧的 config.json 文件")
            return
        
        try:
            with open(old_config_path, 'r', encoding='utf-8') as f:
                old_config = json.load(f)
            
            # 创建新的基础配置
            base_config = {
                "services": old_config.get("services", {}),
                "database": old_config.get("database", {}),
                "redis": old_config.get("redis", {}),
                "logging": old_config.get("logging", {}),
                "risk_limits": old_config.get("risk_limits", {}),
                "trading": old_config.get("trading", {}),
                "performance": old_config.get("performance", {})
            }
            
            # 保存新的基础配置
            base_config_path = os.path.join(self.config_dir, 'base.json')
            with open(base_config_path, 'w', encoding='utf-8') as f:
                json.dump(base_config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"已迁移 config.json 到 base.json")
            
        except Exception as e:
            logger.error(f"迁移 config.json 失败: {e}")
    
    def migrate_risk_config(self):
        """迁移风控配置"""
        risk_config_path = os.path.join(self.config_dir, 'risk_config_example.json')
        
        if not os.path.exists(risk_config_path):
            logger.warning("未找到 risk_config_example.json 文件")
            return
        
        try:
            with open(risk_config_path, 'r', encoding='utf-8') as f:
                risk_config = json.load(f)
            
            # 更新基础配置中的风控部分
            base_config_path = os.path.join(self.config_dir, 'base.json')
            if os.path.exists(base_config_path):
                with open(base_config_path, 'r', encoding='utf-8') as f:
                    base_config = json.load(f)
                
                # 合并风控配置
                base_config.update(risk_config)
                
                # 保存更新后的基础配置
                with open(base_config_path, 'w', encoding='utf-8') as f:
                    json.dump(base_config, f, indent=2, ensure_ascii=False)
                
                logger.info("已合并风控配置到 base.json")
            
        except Exception as e:
            logger.error(f"迁移风控配置失败: {e}")
    
    def create_env_template(self):
        """创建 .env.template 文件"""
        env_template_path = os.path.join(self.project_root, '.env.template')
        
        if os.path.exists(env_template_path):
            logger.info(".env.template 已存在，跳过创建")
            return
        
        template_content = """# Database Configuration
POSTGRES_USER=athena
POSTGRES_PASSWORD=your_postgres_password_here
POSTGRES_DB=athena_trader
REDIS_PASSWORD=your_redis_password_here

# Service Configuration
LOG_LEVEL=INFO
CONFIG_PATH=/app/config
INTERNAL_SERVICE_TOKEN=athena-internal-token-change-in-production

# OKX API Configuration (Real Market Data)
OKX_API_KEY=your_okx_api_key_here
OKX_SECRET=your_okx_secret_here
OKX_PASSPHRASE=your_okx_passphrase_here
OKX_ENVIRONMENT=production

# OKX Demo API Configuration (Simulated Trading)
OKX_DEMO_API_KEY=your_okx_demo_api_key_here
OKX_DEMO_SECRET=your_okx_demo_secret_here
OKX_DEMO_PASSPHRASE=your_okx_demo_passphrase_here

# Internal Service API Keys
DATA_API_KEY=your_data_api_key_here
DATA_SECRET=your_data_secret_here
RISK_API_KEY=your_risk_api_key_here
RISK_SECRET=your_risk_secret_here
EXECUTOR_API_KEY=your_executor_api_key_here
EXECUTOR_SECRET=your_executor_secret_here
EXECUTOR_PASSPHRASE=your_executor_passphrase_here
STRATEGY_API_KEY=your_strategy_api_key_here
STRATEGY_SECRET=your_strategy_secret_here

# AI Model Configuration
AI_API_BASE_URL=https://api.siliconflow.cn/v1/chat/completions
AI_API_KEY=your_siliconflow_token_here
AI_MODEL_NAME=Pro/deepseek-ai/DeepSeek-V3

# External Services
ALERT_WEBHOOK_URL=https://your-webhook-url.com/alerts
WALLET_CONNECT_PROJECT_ID=your_walletconnect_project_id_here

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password_here
REDIS_URL=redis://:your_redis_password_here@localhost:6379

# Database Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
USE_DATABASE=false

# Environment Configuration
ATHENA_ENV=development

# Development Override (uncomment for development)
# COMPOSE_PROFILES=development
"""
        
        with open(env_template_path, 'w', encoding='utf-8') as f:
            f.write(template_content)
        
        logger.info("已创建 .env.template 文件")
    
    def migrate(self):
        """执行完整的配置迁移"""
        logger.info("开始配置迁移...")
        
        # 1. 备份现有配置
        backup_dir = self.backup_existing_configs()
        
        # 2. 迁移配置文件
        self.migrate_old_config_json()
        self.migrate_risk_config()
        
        # 3. 创建环境变量模板
        self.create_env_template()
        
        logger.info("配置迁移完成！")
        logger.info(f"备份文件位置: {backup_dir}")
        logger.info("请检查新的配置文件并根据需要调整")
        
        return backup_dir


def main():
    """主函数"""
    # 获取项目根目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    logger.info(f"项目根目录: {project_root}")
    
    # 创建迁移器并执行迁移
    migrator = ConfigMigrator(project_root)
    
    try:
        backup_dir = migrator.migrate()
        print(f"\n✅ 配置迁移成功完成！")
        print(f"📁 备份位置: {backup_dir}")
        print(f"🔧 请检查新的配置文件并根据需要调整")
        print(f"📝 新的配置结构:")
        print(f"   - config/base.json (基础配置)")
        print(f"   - config/development.json (开发环境)")
        print(f"   - config/test.json (测试环境)")
        print(f"   - config/production.json (生产环境)")
        print(f"   - .env.template (环境变量模板)")
        
    except Exception as e:
        logger.error(f"配置迁移失败: {e}")
        print(f"\n❌ 配置迁移失败: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
