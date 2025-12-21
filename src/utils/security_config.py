"""
安全配置管理模块
负责安全相关的配置管理和验证
"""

import os
import logging
from typing import Dict, Any, List, Optional
from .security_manager import SecurityManager


class SecurityConfig:
    """安全配置管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.security_manager = SecurityManager()
        self._load_security_config()
        self.logger.info("SecurityConfig 初始化完成")
    
    def _load_security_config(self):
        """加载安全配置"""
        try:
            # 基础安全配置
            self.security_config = {
                "encryption": {
                    "enabled": True,
                    "algorithm": "AES-256-GCM",
                    "key_rotation_days": 90
                },
                "api_keys": {
                    "min_length": 32,
                    "max_length": 128,
                    "rotation_days": 30,
                    "require_rotation": True
                },
                "sessions": {
                    "timeout_minutes": 60,
                    "max_concurrent": 5,
                    "require_https": True
                },
                "rate_limiting": {
                    "enabled": True,
                    "window_size": 60,
                    "max_requests": 100,
                    "burst_limit": 150
                },
                "password_policy": {
                    "min_length": 12,
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "require_special": True,
                    "max_age_days": 90
                },
                "file_upload": {
                    "enabled": True,
                    "max_size_mb": 10,
                    "allowed_extensions": [".csv", ".json", ".txt", ".log"],
                    "scan_viruses": False
                },
                "audit": {
                    "enabled": True,
                    "log_level": "INFO",
                    "retention_days": 365,
                    "include_sensitive": False
                }
            }
            
            # 从环境变量覆盖配置
            self._override_from_env()
            
            # 验证配置
            self._validate_security_config()
            
        except Exception as e:
            self.logger.error(f"加载安全配置失败: {e}")
            raise
    
    def _override_from_env(self):
        """从环境变量覆盖配置"""
        env_mappings = {
            "ATHENA_ENCRYPTION_ENABLED": ("encryption", "enabled", self._to_bool),
            "ATHENA_API_KEY_ROTATION_DAYS": ("api_keys", "rotation_days", int),
            "ATHENA_SESSION_TIMEOUT": ("sessions", "timeout_minutes", int),
            "ATHENA_RATE_LIMIT_ENABLED": ("rate_limiting", "enabled", self._to_bool),
            "ATHENA_MAX_REQUESTS": ("rate_limiting", "max_requests", int),
            "ATHENA_PASSWORD_MIN_LENGTH": ("password_policy", "min_length", int),
            "ATHENA_FILE_UPLOAD_MAX_SIZE": ("file_upload", "max_size_mb", int),
            "ATHENA_AUDIT_ENABLED": ("audit", "enabled", self._to_bool)
        }
        
        for env_var, (section, key, converter) in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                try:
                    converted_value = converter(value)
                    self.security_config[section][key] = converted_value
                    self.logger.info(f"从环境变量覆盖配置: {section}.{key} = {converted_value}")
                except (ValueError, TypeError) as e:
                    self.logger.warning(f"无效的环境变量值 {env_var}={value}: {e}")
    
    def _to_bool(self, value: str) -> bool:
        """转换字符串为布尔值"""
        return value.lower() in ('true', '1', 'yes', 'on', 'enabled')
    
    def _validate_security_config(self):
        """验证安全配置"""
        try:
            # 验证加密配置
            if self.security_config["encryption"]["enabled"]:
                if self.security_config["encryption"]["key_rotation_days"] < 7:
                    raise ValueError("密钥轮换间隔不能少于7天")
            
            # 验证 API 密钥配置
            api_config = self.security_config["api_keys"]
            if api_config["min_length"] < 16:
                raise ValueError("API 密钥最小长度不能少于16位")
            if api_config["rotation_days"] < 7:
                raise ValueError("API 密钥轮换间隔不能少于7天")
            
            # 验证会话配置
            session_config = self.security_config["sessions"]
            if session_config["timeout_minutes"] < 5:
                raise ValueError("会话超时时间不能少于5分钟")
            if session_config["max_concurrent"] < 1:
                raise ValueError("最大并发会话数不能少于1")
            
            # 验证速率限制配置
            rate_config = self.security_config["rate_limiting"]
            if rate_config["enabled"]:
                if rate_config["max_requests"] < 1:
                    raise ValueError("最大请求数不能少于1")
                if rate_config["burst_limit"] < rate_config["max_requests"]:
                    raise ValueError("突发限制不能小于最大请求数")
            
            # 验证密码策略
            password_config = self.security_config["password_policy"]
            if password_config["min_length"] < 8:
                raise ValueError("密码最小长度不能少于8位")
            if password_config["max_age_days"] < 30:
                raise ValueError("密码最大使用天数不能少于30天")
            
            # 验证文件上传配置
            upload_config = self.security_config["file_upload"]
            if upload_config["enabled"]:
                if upload_config["max_size_mb"] < 1:
                    raise ValueError("文件上传最大大小不能少于1MB")
                if not upload_config["allowed_extensions"]:
                    raise ValueError("必须指定允许的文件扩展名")
            
            self.logger.info("安全配置验证通过")
            
        except Exception as e:
            self.logger.error(f"安全配置验证失败: {e}")
            raise
    
    def get_security_config(self, section: Optional[str] = None) -> Any:
        """获取安全配置"""
        if section:
            return self.security_config.get(section, {})
        return self.security_config.copy()
    
    def is_encryption_enabled(self) -> bool:
        """检查是否启用加密"""
        return self.security_config["encryption"]["enabled"]
    
    def get_api_key_policy(self) -> Dict[str, Any]:
        """获取 API 密钥策略"""
        return self.security_config["api_keys"].copy()
    
    def get_session_config(self) -> Dict[str, Any]:
        """获取会话配置"""
        return self.security_config["sessions"].copy()
    
    def get_rate_limit_config(self) -> Dict[str, Any]:
        """获取速率限制配置"""
        return self.security_config["rate_limiting"].copy()
    
    def get_password_policy(self) -> Dict[str, Any]:
        """获取密码策略"""
        return self.security_config["password_policy"].copy()
    
    def get_file_upload_config(self) -> Dict[str, Any]:
        """获取文件上传配置"""
        return self.security_config["file_upload"].copy()
    
    def get_audit_config(self) -> Dict[str, Any]:
        """获取审计配置"""
        return self.security_config["audit"].copy()
    
    def validate_password_strength(self, password: str) -> tuple[bool, List[str]]:
        """验证密码强度"""
        errors = []
        policy = self.security_config["password_policy"]
        
        # 检查长度
        if len(password) < policy["min_length"]:
            errors.append(f"密码长度不能少于{policy['min_length']}位")
        
        # 检查大写字母
        if policy["require_uppercase"] and not any(c.isupper() for c in password):
            errors.append("密码必须包含大写字母")
        
        # 检查小写字母
        if policy["require_lowercase"] and not any(c.islower() for c in password):
            errors.append("密码必须包含小写字母")
        
        # 检查数字
        if policy["require_numbers"] and not any(c.isdigit() for c in password):
            errors.append("密码必须包含数字")
        
        # 检查特殊字符
        if policy["require_special"]:
            special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
            if not any(c in special_chars for c in password):
                errors.append("密码必须包含特殊字符")
        
        # 检查常见弱密码
        weak_passwords = [
            "password", "123456", "qwerty", "admin", "letmein",
            "welcome", "monkey", "dragon", "master", "hello"
        ]
        if password.lower() in weak_passwords:
            errors.append("不能使用常见弱密码")
        
        return len(errors) == 0, errors
    
    def should_rotate_api_key(self, created_at: int) -> bool:
        """检查是否应该轮换 API 密钥"""
        rotation_days = self.security_config["api_keys"]["rotation_days"]
        current_time = int(os.time())
        rotation_seconds = rotation_days * 24 * 60 * 60
        
        return (current_time - created_at) >= rotation_seconds
    
    def should_rotate_encryption_key(self, last_rotation: int) -> bool:
        """检查是否应该轮换加密密钥"""
        rotation_days = self.security_config["encryption"]["key_rotation_days"]
        current_time = int(os.time())
        rotation_seconds = rotation_days * 24 * 60 * 60
        
        return (current_time - last_rotation) >= rotation_seconds
    
    def is_session_expired(self, created_at: int) -> bool:
        """检查会话是否过期"""
        timeout_minutes = self.security_config["sessions"]["timeout_minutes"]
        current_time = int(os.time())
        timeout_seconds = timeout_minutes * 60
        
        return (current_time - created_at) >= timeout_seconds
    
    def get_allowed_file_extensions(self) -> List[str]:
        """获取允许的文件扩展名"""
        return self.security_config["file_upload"]["allowed_extensions"].copy()
    
    def get_max_file_size(self) -> int:
        """获取最大文件大小（字节）"""
        max_size_mb = self.security_config["file_upload"]["max_size_mb"]
        return max_size_mb * 1024 * 1024
    
    def is_rate_limiting_enabled(self) -> bool:
        """检查是否启用速率限制"""
        return self.security_config["rate_limiting"]["enabled"]
    
    def get_rate_limits(self) -> tuple[int, int, int]:
        """获取速率限制参数"""
        config = self.security_config["rate_limiting"]
        return (
            config["window_size"],
            config["max_requests"],
            config["burst_limit"]
        )
    
    def should_audit_log(self, level: str = "INFO") -> bool:
        """检查是否应该记录审计日志"""
        if not self.security_config["audit"]["enabled"]:
            return False
        
        audit_level = self.security_config["audit"]["log_level"]
        level_hierarchy = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        
        return level_hierarchy.get(level, 1) >= level_hierarchy.get(audit_level, 1)
    
    def get_audit_retention_days(self) -> int:
        """获取审计日志保留天数"""
        return self.security_config["audit"]["retention_days"]
    
    def include_sensitive_data_in_audit(self) -> bool:
        """检查审计日志是否包含敏感数据"""
        return self.security_config["audit"]["include_sensitive"]
    
    def generate_security_report(self) -> Dict[str, Any]:
        """生成安全配置报告"""
        try:
            report = {
                "timestamp": int(os.time()),
                "security_status": "configured",
                "encryption": {
                    "enabled": self.is_encryption_enabled(),
                    "key_rotation_days": self.security_config["encryption"]["key_rotation_days"]
                },
                "api_security": {
                    "min_key_length": self.security_config["api_keys"]["min_length"],
                    "rotation_required": self.security_config["api_keys"]["require_rotation"],
                    "rotation_days": self.security_config["api_keys"]["rotation_days"]
                },
                "session_security": {
                    "timeout_minutes": self.security_config["sessions"]["timeout_minutes"],
                    "max_concurrent": self.security_config["sessions"]["max_concurrent"],
                    "https_required": self.security_config["sessions"]["require_https"]
                },
                "rate_limiting": {
                    "enabled": self.is_rate_limiting_enabled(),
                    "max_requests_per_minute": self.security_config["rate_limiting"]["max_requests"],
                    "burst_limit": self.security_config["rate_limiting"]["burst_limit"]
                },
                "password_policy": {
                    "min_length": self.security_config["password_policy"]["min_length"],
                    "require_complexity": any([
                        self.security_config["password_policy"]["require_uppercase"],
                        self.security_config["password_policy"]["require_lowercase"],
                        self.security_config["password_policy"]["require_numbers"],
                        self.security_config["password_policy"]["require_special"]
                    ])
                },
                "file_upload": {
                    "enabled": self.security_config["file_upload"]["enabled"],
                    "max_size_mb": self.security_config["file_upload"]["max_size_mb"],
                    "allowed_extensions_count": len(self.security_config["file_upload"]["allowed_extensions"])
                },
                "audit": {
                    "enabled": self.security_config["audit"]["enabled"],
                    "log_level": self.security_config["audit"]["log_level"],
                    "retention_days": self.security_config["audit"]["retention_days"]
                }
            }
            
            return report
            
        except Exception as e:
            self.logger.error(f"生成安全报告失败: {e}")
            return {
                "timestamp": int(os.time()),
                "security_status": "error",
                "error": str(e)
            }
    
    def update_security_config(self, section: str, key: str, value: Any):
        """更新安全配置"""
        try:
            if section not in self.security_config:
                raise ValueError(f"未知的安全配置节: {section}")
            
            # 临时更新配置
            old_value = self.security_config[section][key]
            self.security_config[section][key] = value
            
            # 验证更新后的配置
            self._validate_security_config()
            
            self.logger.info(f"更新安全配置: {section}.{key} 从 {old_value} 更改为 {value}")
            
        except Exception as e:
            # 恢复原值
            if section in self.security_config and key in self.security_config[section]:
                self.security_config[section][key] = old_value
            
            self.logger.error(f"更新安全配置失败: {e}")
            raise
