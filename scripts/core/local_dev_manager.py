#!/usr/bin/env python3
"""
Athena Trader 本地开发管理器
统一管理本地开发环境的服务启动、停止、清理和测试功能
"""

import os
import sys
import json
import time
import signal
import logging
import argparse
import subprocess
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# 获取日志文件的绝对路径
log_dir = f"{project_root}/logs"
log_file = f"{log_dir}/local_dev_manager.log"

# 如果目录不存在，则创建它
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class LocalDevManager:
    """本地开发管理器"""

    def __init__(self):
        self.project_root = project_root
        self.config_dir = self.project_root / "config"
        self.logs_dir = self.project_root / "logs"
        self.services = {}
        self.service_processes = {}
        self.stop_event = threading.Event()

        # 确保日志目录存在
        self.logs_dir.mkdir(exist_ok=True)

        # 加载配置
        self._load_config()

        logger.info("本地开发管理器初始化完成")

    def _load_config(self):
        """加载本地开发配置"""
        try:
            config_file = self.config_dir / "local.json"
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                self.services = config.get('services', {})
                logger.info(f"已加载本地配置: {config_file}")
            else:
                # 使用默认配置
                self.services = self._get_default_services()
                logger.info("使用默认服务配置")
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            self.services = self._get_default_services()

    def _get_default_services(self) -> Dict[str, Any]:
        """获取默认服务配置"""
        return {
            "data_manager": {
                "port": 8000,
                "enabled": True,
                "command": "python -m src.data_manager.main"
            },
            "risk_manager": {
                "port": 8001,
                "enabled": True,
                "command": "python -m src.risk_manager.main"
            },
            "executor": {
                "port": 8002,
                "enabled": True,
                "command": "python -m src.executor.main"
            },
            "strategy_engine": {
                "port": 8003,
                "enabled": True,
                "command": "python -m src.strategy_engine.main"
            }
        }

    def start_services(self) -> bool:
        """启动所有服务"""
        logger.info("🚀 启动本地开发服务...")

        # 设置环境变量
        env = os.environ.copy()
        env.update({
            'PYTHONPATH': str(self.project_root / "src"),
            'CONFIG_PATH': str(self.config_dir),
            'ATHENA_ENV': 'local',
            'DISABLE_REDIS': 'true',  # 本地开发禁用Redis
            'USE_DATABASE': 'false',  # 本地开发使用模拟数据
            'INTERNAL_SERVICE_TOKEN': 'athena-local-dev-token'
        })

        success_count = 0
        total_count = 0

        # 按依赖顺序启动服务
        startup_order = ["data_manager", "risk_manager", "executor", "strategy_engine"]

        for service_name in startup_order:
            if service_name in self.services and self.services[service_name].get('enabled', True):
                total_count += 1
                if self._start_service(service_name, self.services[service_name], env):
                    success_count += 1

        logger.info(f"✅ 服务启动完成: {success_count}/{total_count}")
        return success_count == total_count

    def _start_service(self, service_name: str, service_config: Dict, env: Dict) -> bool:
        """启动单个服务"""
        try:
            logger.info(f"启动服务: {service_name}")

            # 检查端口是否被占用
            port = service_config.get('port', 8000)
            if self._is_port_occupied(port):
                logger.warning(f"端口 {port} 已被占用，跳过 {service_name}")
                return False

            # 启动服务进程
            cmd = service_config['command'].split()

            # 将命令中的 'python' 替换为当前解释器的绝对路径
            if cmd and cmd[0] == 'python':
                cmd[0] = sys.executable

            process = subprocess.Popen(
                cmd,
                cwd=self.project_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            self.service_processes[service_name] = process

            # 启动输出监控线程
            monitor_thread = threading.Thread(
                target=self._monitor_service_output,
                args=(service_name, process),
                daemon=True
            )
            monitor_thread.start()

            # 等待服务启动
            time.sleep(2)

            # 检查服务是否健康
            if self._check_service_health(port):
                logger.info(f"✅ {service_name} 启动成功 (端口: {port})")
                return True
            else:
                logger.error(f"❌ {service_name} 启动失败")
                process.terminate()
                del self.service_processes[service_name]
                return False

        except Exception as e:
            logger.error(f"启动 {service_name} 时发生错误: {e}")
            return False

    def _monitor_service_output(self, service_name: str, process: subprocess.Popen):
        """监控服务输出"""
        try:
            for line in iter(process.stdout.readline, ''):
                if line and not self.stop_event.is_set():
                    logger.info(f"[{service_name}] {line.strip()}")
        except Exception as e:
            logger.error(f"监控 {service_name} 输出时发生错误: {e}")

    def _is_port_occupied(self, port: int) -> bool:
        """检查端口是否被占用"""
        try:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(('localhost', port)) == 0
        except:
            return False

    def _check_service_health(self, port: int, max_retries: int = 5) -> bool:
        """检查服务健康状态"""
        import requests

        for _ in range(max_retries):
            try:
                response = requests.get(f"http://localhost:{port}/health", timeout=5)
                if response.status_code == 200:
                    return True
            except:
                pass
            time.sleep(1)
        return False

    def stop_services(self):
        """停止所有服务"""
        logger.info("🛑 停止所有服务...")

        for service_name, process in self.service_processes.items():
            try:
                logger.info(f"停止服务: {service_name}")
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                logger.info(f"✅ {service_name} 已停止")
            except Exception as e:
                logger.error(f"停止 {service_name} 时发生错误: {e}")

        self.service_processes.clear()
        logger.info("✅ 所有服务已停止")

    def check_status(self) -> Dict[str, Any]:
        """检查服务状态"""
        status = {
            'services': {},
            'overall': 'unknown'
        }

        healthy_count = 0
        total_count = 0

        for service_name, service_config in self.services.items():
            if service_config.get('enabled', True):
                total_count += 1
                port = service_config.get('port', 8000)

                if service_name in self.service_processes:
                    process = self.service_processes[service_name]
                    if process.poll() is None:  # 进程还在运行
                        if self._check_service_health(port, 1):
                            status['services'][service_name] = 'healthy'
                            healthy_count += 1
                        else:
                            status['services'][service_name] = 'unhealthy'
                    else:
                        status['services'][service_name] = 'stopped'
                else:
                    if self._is_port_occupied(port):
                        status['services'][service_name] = 'running_external'
                    else:
                        status['services'][service_name] = 'stopped'

        status['overall'] = 'healthy' if healthy_count == total_count else 'partial' if healthy_count > 0 else 'stopped'
        return status

    def run_test(self, test_name: str = "simple_trading_test") -> bool:
        """运行测试"""
        logger.info(f"🧪 运行测试: {test_name}")

        try:
            # 构建测试命令
            test_module = f"tests.system.{test_name}"
            cmd = [sys.executable, "-m", test_module]

            # 设置测试环境
            env = os.environ.copy()
            env.update({
                'PYTHONPATH': str(self.project_root / "src"),
                'ATHENA_ENV': 'test'
            })

            # 运行测试
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                env=env,
                capture_output=True,
                text=True
            )

            # 输出测试结果
            if result.stdout:
                logger.info(f"测试输出:\n{result.stdout}")
            if result.stderr:
                logger.error(f"测试错误:\n{result.stderr}")

            success = result.returncode == 0
            if success:
                logger.info("✅ 测试通过")
            else:
                logger.error("❌ 测试失败")

            return success

        except Exception as e:
            logger.error(f"运行测试时发生错误: {e}")
            return False

    def cleanup(self, cleanup_type: str = "all") -> bool:
        """清理系统"""
        logger.info(f"🧹 开始清理: {cleanup_type}")

        try:
            if cleanup_type in ["all", "logs"]:
                self._cleanup_logs()

            if cleanup_type in ["all", "temp"]:
                self._cleanup_temp_files()

            if cleanup_type in ["all", "cache"]:
                self._cleanup_cache()

            logger.info("✅ 清理完成")
            return True

        except Exception as e:
            logger.error(f"清理时发生错误: {e}")
            return False

    def _cleanup_logs(self):
        """清理日志文件"""
        logger.info("清理日志文件...")

        # 保留最新的5个日志文件
        log_files = list(self.logs_dir.glob("*.log"))
        log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        for log_file in log_files[5:]:
            try:
                log_file.unlink()
                logger.info(f"删除日志文件: {log_file}")
            except Exception as e:
                logger.error(f"删除日志文件失败 {log_file}: {e}")

    def _cleanup_temp_files(self):
        """清理临时文件"""
        logger.info("清理临时文件...")

        temp_patterns = [
            "**/__pycache__",
            "**/*.pyc",
            "**/*.pyo",
            "**/.pytest_cache",
            "**/*.tmp"
        ]

        for pattern in temp_patterns:
            for temp_file in self.project_root.glob(pattern):
                try:
                    if temp_file.is_file():
                        temp_file.unlink()
                    elif temp_file.is_dir():
                        import shutil
                        shutil.rmtree(temp_file)
                    logger.info(f"删除临时文件/目录: {temp_file}")
                except Exception as e:
                    logger.error(f"删除临时文件失败 {temp_file}: {e}")

    def _cleanup_cache(self):
        """清理缓存文件"""
        logger.info("清理缓存文件...")

        cache_dirs = [
            self.project_root / "src" / "data_manager" / "cache",
            self.project_root / "src" / "risk_manager" / "cache",
            self.project_root / "src" / "executor" / "cache",
            self.project_root / "src" / "strategy_engine" / "cache"
        ]

        for cache_dir in cache_dirs:
            if cache_dir.exists():
                try:
                    import shutil
                    shutil.rmtree(cache_dir)
                    cache_dir.mkdir(exist_ok=True)
                    logger.info(f"清理缓存目录: {cache_dir}")
                except Exception as e:
                    logger.error(f"清理缓存目录失败 {cache_dir}: {e}")

    def show_status(self):
        """显示服务状态"""
        status = self.check_status()

        print("\n" + "="*50)
        print("📊 Athena Trader 本地开发状态")
        print("="*50)

        # 显示整体状态
        status_emoji = {
            'healthy': '🟢',
            'partial': '🟡',
            'stopped': '🔴',
            'unknown': '⚪'
        }

        print(f"整体状态: {status_emoji.get(status['overall'], '⚪')} {status['overall']}")
        print()

        # 显示各服务状态
        for service_name, service_status in status['services'].items():
            emoji = {
                'healthy': '✅',
                'unhealthy': '❌',
                'stopped': '⏹️',
                'running_external': '🔄'
            }
            print(f"  {service_name}: {emoji.get(service_status, '❓')} {service_status}")

        print()
        print("🔧 管理命令:")
        print("  启动服务: python scripts/local_dev_manager.py start")
        print("  停止服务: python scripts/local_dev_manager.py stop")
        print("  运行测试: python scripts/local_dev_manager.py test")
        print("  清理系统: python scripts/local_dev_manager.py cleanup")
        print("  查看状态: python scripts/local_dev_manager.py status")
        print("="*50)


def signal_handler(signum, frame):
    """信号处理器"""
    logger.info("收到停止信号，正在清理...")
    if 'manager' in globals():
        manager.stop_services()
    sys.exit(0)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Athena Trader 本地开发管理器")
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "test", "cleanup"],
                       help="操作类型")
    parser.add_argument("--test", default="simple_trading_test",
                       help="测试名称 (默认: simple_trading_test)")
    parser.add_argument("--cleanup-type", choices=["all", "logs", "temp", "cache"], default="all",
                       help="清理类型 (默认: all)")

    args = parser.parse_args()

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 创建管理器实例
    global manager
    manager = LocalDevManager()

    try:
        if args.action == "start":
            success = manager.start_services()
            if success:
                print("✅ 所有服务启动成功！")
                print("🌐 访问地址: http://localhost:3000")
                print("按 Ctrl+C 停止服务...")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    pass
            else:
                print("❌ 部分服务启动失败")
                sys.exit(1)

        elif args.action == "stop":
            manager.stop_services()
            print("✅ 所有服务已停止")

        elif args.action == "restart":
            manager.stop_services()
            time.sleep(2)
            success = manager.start_services()
            if success:
                print("✅ 所有服务重启成功")
            else:
                print("❌ 部分服务重启失败")
                sys.exit(1)

        elif args.action == "status":
            manager.show_status()

        elif args.action == "test":
            success = manager.run_test(args.test)
            sys.exit(0 if success else 1)

        elif args.action == "cleanup":
            success = manager.cleanup(args.cleanup_type)
            sys.exit(0 if success else 1)

    finally:
        if args.action in ["start", "restart"]:
            manager.stop_services()


if __name__ == "__main__":
    main()
