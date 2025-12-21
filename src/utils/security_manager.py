"""
安全管理器模块
负责密钥管理、访问控制和安全审计
"""

import os
import hashlib
import hmac
import logging
import time
import json
import secrets
from typing import Dict, Any, Optional, List
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64


class SecurityManager:
    """安全管理器 - 提供加密、密钥管理和访问控制功能"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._encryption_key = None
        self._cipher_suite = None
        self._init_encryption()
        self.logger.info("SecurityManager 初始化完成")
    
    def _init_encryption(self):
        """初始化加密功能"""
        try:
            # 从环境变量获取主密钥
            master_key = os.getenv('ATHENA_MASTER_KEY')
            if not master_key:
                # 如果没有主密钥，生成一个并警告
                master_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
                self.logger.warning("未设置 ATHENA_MASTER_KEY，已生成临时密钥。请设置环境变量以持久化加密。")
            
            # 使用 PBKDF2 派生加密密钥
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'athena_salt',  # 在生产环境中应该使用随机盐
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
            self._cipher_suite = Fernet(key)
            
        except Exception as e:
            self.logger.error(f"初始化加密功能失败: {e}")
            raise
    
    def encrypt_sensitive_data(self, data: str) -> str:
        """加密敏感数据"""
        try:
            if not self._cipher_suite:
                raise ValueError("加密套件未初始化")
            
            encrypted_data = self._cipher_suite.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted_data).decode()
        except Exception as e:
            self.logger.error(f"加密数据失败: {e}")
            raise
    
    def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        """解密敏感数据"""
        try:
            if not self._cipher_suite:
                raise ValueError("加密套件未初始化")
            
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = self._cipher_suite.decrypt(encrypted_bytes)
            return decrypted_data.decode()
        except Exception as e:
            self.logger.error(f"解密数据失败: {e}")
            raise
    
    def hash_password(self, password: str, salt: Optional[str] = None) -> tuple[str, str]:
        """哈希密码"""
        try:
            if salt is None:
                salt = secrets.token_hex(16)
            
            # 使用 PBKDF2 哈希密码
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt.encode(),
                iterations=100000,
            )
            hashed = base64.urlsafe_b64encode(kdf.derive(password.encode())).decode()
            return hashed, salt
        except Exception as e:
            self.logger.error(f"哈希密码失败: {e}")
            raise
    
    def verify_password(self, password: str, hashed: str, salt: str) -> bool:
        """验证密码"""
        try:
            new_hash, _ = self.hash_password(password, salt)
            return hmac.compare_digest(new_hash, hashed)
        except Exception as e:
            self.logger.error(f"验证密码失败: {e}")
            return False
    
    def generate_api_key(self, service_name: str) -> Dict[str, str]:
        """生成 API 密钥"""
        try:
            # 生成 API 密钥和密钥
            api_key = f"ak_{secrets.token_urlsafe(32)}"
            api_secret = secrets.token_urlsafe(64)
            
            # 哈希密钥用于存储
            hashed_secret, salt = self.hash_password(api_secret)
            
            # 创建密钥信息
            key_info = {
                "api_key": api_key,
                "hashed_secret": hashed_secret,
                "salt": salt,
                "service_name": service_name,
                "created_at": int(time.time()),
                "status": "active"
            }
            
            self.logger.info(f"为服务 {service_name} 生成 API 密钥")
            return {
                "api_key": api_key,
                "api_secret": api_secret,  # 只在生成时返回一次
                "key_info": key_info
            }
            
        except Exception as e:
            self.logger.error(f"生成 API 密钥失败: {e}")
            raise
    
    def validate_api_key(self, api_key: str, api_secret: str, stored_key_info: Dict[str, Any]) -> bool:
        """验证 API 密钥"""
        try:
            # 检查基本字段
            if not all([api_key, api_secret, stored_key_info]):
                return False
            
            # 检查密钥是否匹配
            if api_key != stored_key_info.get("api_key"):
                return False
            
            # 验证密钥
            hashed_secret = stored_key_info.get("hashed_secret")
            salt = stored_key_info.get("salt")
            
            if not all([hashed_secret, salt]):
                return False
            
            return self.verify_password(api_secret, hashed_secret, salt)
            
        except Exception as e:
            self.logger.error(f"验证 API 密钥失败: {e}")
            return False
    
    def rotate_api_key(self, service_name: str, old_key_info: Dict[str, Any]) -> Dict[str, str]:
        """轮换 API 密钥"""
        try:
            # 生成新密钥
            new_key_data = self.generate_api_key(service_name)
            
            # 标记旧密钥为已撤销
            old_key_info["status"] = "revoked"
            old_key_info["revoked_at"] = int(time.time())
            
            self.logger.info(f"为服务 {service_name} 轮换 API 密钥")
            
            return {
                "new_key_data": new_key_data,
                "old_key_info": old_key_info
            }
            
        except Exception as e:
            self.logger.error(f"轮换 API 密钥失败: {e}")
            raise
    
    def mask_sensitive_value(self, value: str, mask_char: str = "*", visible_chars: int = 4) -> str:
        """遮蔽敏感值"""
        try:
            if not value or len(value) <= visible_chars:
                return mask_char * len(value) if value else ""
            
            return value[:visible_chars] + mask_char * (len(value) - visible_chars)
        except Exception as e:
            self.logger.error(f"遮蔽敏感值失败: {e}")
            return mask_char * 8
    
    def validate_service_token(self, token: str, expected_token: str) -> bool:
        """验证服务间令牌"""
        try:
            if not token or not expected_token:
                return False
            
            # 使用恒定时间比较防止时序攻击
            return hmac.compare_digest(token.encode(), expected_token.encode())
            
        except Exception as e:
            self.logger.error(f"验证服务令牌失败: {e}")
            return False
    
    def generate_session_token(self, user_id: str, expires_in: int = 3600) -> Dict[str, Any]:
        """生成会话令牌"""
        try:
            # 生成会话 ID
            session_id = secrets.token_urlsafe(32)
            
            # 计算过期时间
            expires_at = int(time.time()) + expires_in
            
            # 创建会话信息
            session_info = {
                "session_id": session_id,
                "user_id": user_id,
                "created_at": int(time.time()),
                "expires_at": expires_at,
                "status": "active"
            }
            
            # 生成签名
            session_data = json.dumps(session_info, sort_keys=True)
            signature = hmac.new(
                self._cipher_suite.key if self._cipher_suite else b'default',
                session_data.encode(),
                hashlib.sha256
            ).hexdigest()
            
            self.logger.info(f"为用户 {user_id} 生成会话令牌")
            
            return {
                "session_token": session_id,
                "signature": signature,
                "expires_at": expires_at,
                "session_info": session_info
            }
            
        except Exception as e:
            self.logger.error(f"生成会话令牌失败: {e}")
            raise
    
    def validate_session_token(self, session_token: str, signature: str, stored_session_info: Dict[str, Any]) -> bool:
        """验证会话令牌"""
        try:
            # 检查会话是否存在
            if not session_token or not stored_session_info:
                return False
            
            # 检查会话状态
            if stored_session_info.get("status") != "active":
                return False
            
            # 检查是否过期
            if int(time.time()) > stored_session_info.get("expires_at", 0):
                return False
            
            # 验证签名
            session_data = json.dumps(stored_session_info, sort_keys=True)
            expected_signature = hmac.new(
                self._cipher_suite.key if self._cipher_suite else b'default',
                session_data.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature.encode(), expected_signature.encode())
            
        except Exception as e:
            self.logger.error(f"验证会话令牌失败: {e}")
            return False
    
    def audit_log(self, action: str, user_id: str, resource: str, details: Dict[str, Any] = None):
        """记录安全审计日志"""
        try:
            audit_entry = {
                "timestamp": int(time.time()),
                "action": action,
                "user_id": user_id,
                "resource": resource,
                "ip_address": details.get("ip_address") if details else None,
                "user_agent": details.get("user_agent") if details else None,
                "success": details.get("success", True) if details else True,
                "details": details or {}
            }
            
            # 在实际实现中，这里应该写入安全的审计日志存储
            self.logger.info(f"安全审计: {json.dumps(audit_entry, separators=(',', ':'))}")
            
        except Exception as e:
            self.logger.error(f"记录审计日志失败: {e}")
    
    def check_rate_limit(self, identifier: str, window_size: int = 60, max_requests: int = 100) -> bool:
        """检查速率限制"""
        try:
            # 在实际实现中，这里应该使用 Redis 或其他存储来跟踪请求
            # 这里提供一个简化的实现示例
            
            current_time = int(time.time())
            window_start = current_time - window_size
            
            # 模拟从存储中获取请求计数
            # 在实际实现中，应该使用有序集合或滑动窗口算法
            request_count = self._get_request_count(identifier, window_start, current_time)
            
            if request_count >= max_requests:
                self.logger.warning(f"速率限制触发: {identifier} 在 {window_size}s 内请求 {request_count} 次")
                return False
            
            # 记录当前请求
            self._record_request(identifier, current_time)
            return True
            
        except Exception as e:
            self.logger.error(f"检查速率限制失败: {e}")
            # 出错时允许请求，避免阻断服务
            return True
    
    def _get_request_count(self, identifier: str, window_start: int, current_time: int) -> int:
        """获取窗口内的请求计数（模拟实现）"""
        # 在实际实现中，这里应该查询 Redis 或其他存储
        # 这里返回模拟值
        return 0
    
    def _record_request(self, identifier: str, timestamp: int):
        """记录请求（模拟实现）"""
        # 在实际实现中，这里应该写入 Redis 或其他存储
        pass
    
    def sanitize_input(self, input_data: str) -> str:
        """清理输入数据"""
        try:
            if not input_data:
                return ""
            
            # 移除潜在的恶意字符
            dangerous_chars = ['<', '>', '"', "'", '&', '\x00', '\n', '\r', '\t']
            sanitized = input_data
            
            for char in dangerous_chars:
                sanitized = sanitized.replace(char, '')
            
            # 限制长度
            max_length = 1000
            if len(sanitized) > max_length:
                sanitized = sanitized[:max_length]
            
            return sanitized.strip()
            
        except Exception as e:
            self.logger.error(f"清理输入数据失败: {e}")
            return ""
    
    def validate_file_upload(self, filename: str, file_size: int, allowed_extensions: List[str]) -> bool:
        """验证文件上传"""
        try:
            # 检查文件名
            if not filename or '..' in filename or '/' in filename:
                return False
            
            # 检查文件扩展名
            file_extension = filename.lower().split('.')[-1] if '.' in filename else ''
            if file_extension not in [ext.lower() for ext in allowed_extensions]:
                return False
            
            # 检查文件大小（默认 10MB 限制）
            max_size = 10 * 1024 * 1024
            if file_size > max_size:
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"验证文件上传失败: {e}")
            return False
    
    def get_security_headers(self) -> Dict[str, str]:
        """获取安全 HTTP 头"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'",
            "Referrer-Policy": "strict-origin-when-cross-origin"
        }
