#!/usr/bin/env python3
"""
测试服务启动脚本
用于启动运行测试所需的服务
"""

import os
import sys
import time
import subprocess
import signal
import json
import requests
from typing import Dict, List, Optional
import logging

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestServiceManager:
    """测试服务管理器"""
    
    def __init__(self):
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.processes: Dict[str, subprocess.Popen] = {}
        self.config = self._load_config()
        
    def _load_config(self) -> Dict:
        """加载测试配置"""
        try:
            config_path = os.path.join(self.project_root, "config", "test.json")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.warning(f"配置文件不存在: {config_path}")
                return self._get_default_config()
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """获取默认配置"""
        return {
            "services": {
                "data_manager": {"port": 8000, "enabled": True},
                "strategy_engine": {"port": 8003, "enabled": True},
                "risk_manager": {"port": 8002, "enabled": True},
                "executor": {"port": 8001, "enabled": True}
            }
        }
    
    def check_service_health(self, service_name: str, port: int, max_retries: int = 30) -> bool:
        """检查服务健康状态"""
        url = f"http://localhost:{port}/health"
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    logger.info(f"✅ {service_name} (端口 {port}) - 健康")
                    return True
                else:
                    logger.warning(f"⚠️ {service_name} (端口 {port}) - 状态异常: {response.status_code}")
            except requests.exceptions.ConnectionError:
                if attempt < max_retries - 1:
                    logger.info(f"⏳ 等待 {service_name} (端口 {port}) 启动... ({attempt + 1}/{max_retries})")
                    time.sleep(2)
                else:
                    logger.error(f"❌ {service_name} (端口 {port}) - 连接失败")
            except Exception as e:
                logger.error(f"❌ {service_name} (端口 {port}) - 检查异常: {e}")
                break
        
        return False
    
    def start_service(self, service_name: str, service_config: Dict) -> bool:
        """启动单个服务"""
        if not service_config.get('enabled', True):
            logger.info(f"⏭️ 跳过已禁用的服务: {service_name}")
            return True
        
        port = service_config.get('port', 8000)
        
        # 检查端口是否已被占用
        if self._is_port_occupied(port):
            logger.info(f"🔄 端口 {port} 已被占用，检查是否为 {service_name} 服务...")
            if self.check_service_health(service_name, port, 5):
                logger.info(f"✅ {service_name} 已在运行")
                return True
            else:
                logger.error(f"❌ 端口 {port} 被占用但服务不健康")
                return False
        
        # 启动服务
        try:
            logger.info(f"🚀 启动服务: {service_name} (端口 {port})")
            
            # 构建启动命令
            if service_name == "data_manager":
                cmd = [sys.executable, "-m", "src.data_manager.main"]
            elif service_name == "strategy_engine":
                cmd = [sys.executable, "-m", "src.strategy_engine.main"]
            elif service_name == "risk_manager":
                cmd = [sys.executable, "-m", "src.risk_manager.main"]
            elif service_name == "executor":
                cmd = [sys.executable, "-m", "src.executor.main"]
            else:
                logger.error(f"❌ 未知服务: {service_name}")
                return False
            
            # 设置环境变量
            env = os.environ.copy()
            env.update({
                'PYTHONPATH': self.project_root,
                'SERVICE_HOST': '0.0.0.0',
                'SERVICE_PORT': str(port),
                'LOG_LEVEL': 'INFO',
                'USE_DATABASE': 'false',  # 测试环境不使用数据库
                'DISABLE_REDIS': 'true',   # 测试环境不使用Redis
                'INTERNAL_SERVICE_TOKEN': 'athena-test-token'
            })
            
            # 启动进程
            process = subprocess.Popen(
                cmd,
                cwd=self.project_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并输出以便调试
                text=True,
                bufsize=1,  # 行缓冲
                universal_newlines=True
            )
            
            self.processes[service_name] = process
            
            # 等待服务启动，同时监控输出
            import threading
            
            def monitor_output():
                if process.stdout:
                    for line in iter(process.stdout.readline, ''):
                        if line.strip():
                            logger.info(f"[{service_name}] {line.strip()}")
            
            # 启动输出监控线程
            monitor_thread = threading.Thread(target=monitor_output, daemon=True)
            monitor_thread.start()
            
            # 等待服务启动
            if self.check_service_health(service_name, port):
                logger.info(f"✅ {service_name} 启动成功")
                return True
            else:
                logger.error(f"❌ {service_name} 启动失败")
                # 输出剩余的错误信息
                if process.stdout:
                    remaining_output = process.stdout.read()
                    if remaining_output:
                        logger.error(f"[{service_name}] 剩余输出: {remaining_output}")
                process.terminate()
                del self.processes[service_name]
                return False
                
        except Exception as e:
            logger.error(f"❌ 启动 {service_name} 失败: {e}")
            return False
    
    def _is_port_occupied(self, port: int) -> bool:
        """检查端口是否被占用"""
        try:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(('localhost', port)) == 0
        except:
            return False
    
    def start_all_services(self) -> bool:
        """启动所有服务"""
        logger.info("🚀 开始启动测试服务...")
        
        services = self.config.get('services', {})
        success_count = 0
        total_count = 0
        
        # 按依赖顺序启动服务
        startup_order = ["data_manager", "risk_manager", "executor", "strategy_engine"]
        
        for service_name in startup_order:
            if service_name in services:
                total_count += 1
                if self.start_service(service_name, services[service_name]):
                    success_count += 1
                    time.sleep(2)  # 给服务一些启动时间
        
        logger.info(f"📊 服务启动完成: {success_count}/{total_count}")
        return success_count == total_count
    
    def stop_all_services(self):
        """停止所有服务"""
        logger.info("🛑 停止所有服务...")
        
        for service_name, process in self.processes.items():
            try:
                logger.info(f"🛑 停止服务: {service_name}")
                process.terminate()
                process.wait(timeout=10)
                logger.info(f"✅ {service_name} 已停止")
            except subprocess.TimeoutExpired:
                logger.warning(f"⚠️ 强制终止 {service_name}")
                process.kill()
            except Exception as e:
                logger.error(f"❌ 停止 {service_name} 失败: {e}")
        
        self.processes.clear()
    
    def check_all_services(self) -> bool:
        """检查所有服务状态"""
        logger.info("🔍 检查所有服务状态...")
        
        services = self.config.get('services', {})
        all_healthy = True
        
        for service_name, service_config in services.items():
            if service_config.get('enabled', True):
                port = service_config.get('port', 8000)
                if not self.check_service_health(service_name, port, 5):
                    all_healthy = False
        
        return all_healthy
    
    def signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"收到信号 {signum}，正在停止服务...")
        self.stop_all_services()
        sys.exit(0)

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="测试服务管理器")
    parser.add_argument("action", choices=["start", "stop", "check", "restart"], 
                       help="操作类型")
    parser.add_argument("--wait", action="store_true", 
                       help="启动后等待，直到手动停止")
    
    args = parser.parse_args()
    
    manager = TestServiceManager()
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, manager.signal_handler)
    signal.signal(signal.SIGTERM, manager.signal_handler)
    
    try:
        if args.action == "start":
            if manager.start_all_services():
                logger.info("🎉 所有服务启动成功")
                if args.wait:
                    logger.info("⏳ 服务运行中，按 Ctrl+C 停止...")
                    try:
                        while True:
                            time.sleep(10)
                            # 定期检查服务状态
                            if not manager.check_all_services():
                                logger.warning("⚠️ 部分服务不健康")
                    except KeyboardInterrupt:
                        pass
            else:
                logger.error("❌ 部分服务启动失败")
                sys.exit(1)
        
        elif args.action == "stop":
            manager.stop_all_services()
            logger.info("🎉 所有服务已停止")
        
        elif args.action == "check":
            if manager.check_all_services():
                logger.info("🎉 所有服务运行正常")
            else:
                logger.error("❌ 部分服务不健康")
                sys.exit(1)
        
        elif args.action == "restart":
            manager.stop_all_services()
            time.sleep(2)
            if manager.start_all_services():
                logger.info("🎉 所有服务重启成功")
            else:
                logger.error("❌ 部分服务重启失败")
                sys.exit(1)
    
    finally:
        if args.action in ["start", "restart"] and not args.wait:
            # 如果不是等待模式，清理进程
            manager.stop_all_services()

if __name__ == "__main__":
    main()
