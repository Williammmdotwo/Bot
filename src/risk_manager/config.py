from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
import logging
import os
import json
import sys

logger = logging.getLogger(__name__)


class RiskLimits(BaseModel):
    """风控限制配置"""
    
    max_single_order_size_percent: float = Field(
        default=0.20, 
        description="单笔仓位上限百分比",
        ge=0.0, 
        le=1.0
    )
    
    max_total_position_percent: float = Field(
        default=0.6, 
        description="总持仓上限百分比",
        ge=0.0, 
        le=1.0
    )
    
    mandatory_stop_loss_percent: float = Field(
        default=-0.04, 
        description="强制止损百分比",
        lt=0.0
    )
    
    mandatory_take_profit_percent: float = Field(
        default=0.08, 
        description="强制止盈百分比",
        gt=0.0
    )
    
    max_drawdown_percent: float = Field(
        default=0.2, 
        description="最大回撤百分比",
        ge=0.0, 
        le=1.0
    )
    
    # 新增动态风险参数
    min_confidence_threshold: float = Field(
        default=0.7, 
        description="最低置信度阈值",
        ge=0.0, 
        le=1.0
    )
    
    dynamic_risk_adjustment: bool = Field(
        default=True, 
        description="启用动态风险调整"
    )
    
    volatility_multiplier: float = Field(
        default=1.5, 
        description="波动性调整倍数",
        ge=1.0, 
        le=3.0
    )
    
    @field_validator('mandatory_take_profit_percent')
    def take_profit_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('止盈百分比必须为正数')
        return v
    
    @field_validator('mandatory_stop_loss_percent')
    def stop_loss_must_be_negative(cls, v):
        if v >= 0:
            raise ValueError('止损百分比必须为负数')
        return v
    
    @field_validator('max_single_order_size_percent', 'max_total_position_percent', 'max_drawdown_percent')
    def percentage_must_be_valid(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError('百分比必须在0到1之间')
        return v


class Config:
    """风控配置类 - 使用统一配置管理器"""
    
    def __init__(self, config_data: Optional[Dict[str, Any]] = None):
        """初始化风控配置"""
        # 如果没有提供配置数据，从统一配置管理器获取
        if config_data is None:
            try:
                # 使用绝对导入避免相对导入问题
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                if project_root not in sys.path:
                    sys.path.insert(0, project_root)
                
                from src.utils.config_loader import get_config_manager
                config_manager = get_config_manager()
                config_data = config_manager.get_config()
                logger.info("已从统一配置管理器加载风控配置")
            except Exception as e:
                logger.error(f"从统一配置管理器加载配置失败: {e}")
                config_data = {}
        
        # 提取风控限制配置
        risk_limits_data = config_data.get('risk_limits', {})
        self.risk_limits = RiskLimits(**risk_limits_data)
        
        # 其他配置项
        self.enable_risk_notifications = config_data.get('enable_risk_notifications', True)
        self.risk_notification_webhook = config_data.get('risk_notification_webhook')
        
        # 存储完整配置数据
        self._config_data = config_data
        
        logger.info("风控配置初始化完成")
    
    @classmethod
    def load_from_file(cls, config_path: str) -> 'Config':
        """从指定文件加载配置"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        return cls(**config_data)
    
    def get_risk_limits(self) -> RiskLimits:
        """获取风控限制配置"""
        return self.risk_limits
    
    def validate_position_size(self, position_percent: float) -> bool:
        """验证仓位大小是否符合限制"""
        return position_percent <= self.risk_limits.max_single_order_size_percent
    
    def validate_total_position(self, total_position_percent: float) -> bool:
        """验证总持仓是否符合限制"""
        return total_position_percent <= self.risk_limits.max_total_position_percent
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "risk_limits": self.risk_limits.model_dump(),
            "enable_risk_notifications": self.enable_risk_notifications,
            "risk_notification_webhook": self.risk_notification_webhook
        }
    
    def save_to_file(self, config_path: str) -> None:
        """保存配置到文件"""
        config_data = self.to_dict()
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)


# 全局配置实例
_config = None

def get_config() -> Config:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = Config()
    return _config

def reload_config() -> Config:
    """重新加载配置"""
    global _config
    _config = Config()
    return _config
