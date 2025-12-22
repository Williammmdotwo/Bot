#!/usr/bin/env python3
"""
Athena Trader 全能交易启动脚本
一键启动所有服务并开始交易
"""

import os
import sys
import json
import time
import logging
import subprocess
import threading
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# 加载环境变量
env_file = project_root / ".env"
if env_file.exists():
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"{project_root}/logs/trading_start.log", encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class TradingLauncher:
    """交易启动器"""

    def __init__(self):
        self.project_root = project_root
        self.logs_dir = self.project_root / "logs"
        self.services = {}
        self.service_processes = {}

        # 确保日志目录存在
        self.logs_dir.mkdir(exist_ok=True)

        # 服务配置
        self.services = {
            "data_manager": {
                "port": 8000,
                "enabled": True,
                "command": "python -m src.data_manager.main",
                "health_url": "http://localhost:8000/health"
            },
            "risk_manager": {
                "port": 8001,
                "enabled": True,
                "command": "python -m src.risk_manager.main",
                "health_url": "http://localhost:8001/health"
            },
            "executor": {
                "port": 8002,
                "enabled": True,
                "command": "python -m src.executor.main",
                "health_url": "http://localhost:8002/health"
            },
            "strategy_engine": {
                "port": 8003,
                "enabled": True,
                "command": "python -m src.strategy_engine.main",
                "health_url": "http://localhost:8003/health"
            }
        }

        logger.info("交易启动器初始化完成")

    def check_prerequisites(self) -> bool:
        """检查启动前置条件"""
        logger.info("🔍 检查启动前置条件...")

        # 1. 检查环境配置
        env_file = self.project_root / ".env"
        if not env_file.exists():
            logger.error("❌ .env 文件不存在")
            return False

        # 2. 检查关键环境变量
        required_vars = [
            'DATA_SOURCE_MODE', 'USE_MOCK_DATA', 'OKX_ENVIRONMENT',
            'OKX_DEMO_API_KEY', 'OKX_DEMO_SECRET', 'OKX_DEMO_PASSPHRASE'
        ]

        missing_vars = []
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)

        if missing_vars:
            logger.error(f"❌ 缺少环境变量: {missing_vars}")
            return False

        # 3. 检查数据源连接
        logger.info("🔍 检查数据源连接...")
        try:
            result = subprocess.run([
                sys.executable,
                str(self.project_root / "scripts" / "verify_data_feed.py")
            ], capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                logger.error(f"❌ 数据源连接失败: {result.stderr}")
                return False

            logger.info("✅ 数据源连接正常")
        except Exception as e:
            logger.error(f"❌ 数据源检查失败: {e}")
            return False

        # 4. 检查端口占用
        logger.info("🔍 检查端口占用...")
        for service_name, service_config in self.services.items():
            port = service_config['port']
            if self._is_port_occupied(port):
                logger.warning(f"⚠️ 端口 {port} 已被占用，可能影响 {service_name}")

        logger.info("✅ 前置条件检查完成")
        return True

    def start_services(self) -> bool:
        """启动所有交易服务"""
        logger.info("🚀 启动交易服务...")

        # 设置环境变量
        env = os.environ.copy()
        env.update({
            'PYTHONPATH': str(self.project_root / "src"),
            'CONFIG_PATH': str(self.project_root / "config"),
            'ATHENA_ENV': 'development',
            'INTERNAL_SERVICE_TOKEN': 'athena-trading-token'
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

            # 启动服务进程
            cmd = service_config['command'].split()
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
            time.sleep(3)

            # 检查服务是否健康
            if self._check_service_health(service_config['health_url']):
                logger.info(f"✅ {service_name} 启动成功 (端口: {service_config['port']})")
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
                if line:
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

    def _check_service_health(self, health_url: str, max_retries: int = 10) -> bool:
        """检查服务健康状态"""
        for i in range(max_retries):
            try:
                response = requests.get(health_url, timeout=5)
                if response.status_code == 200:
                    return True
            except:
                pass
            if i < max_retries - 1:
                time.sleep(1)
        return False

    def verify_trading_system(self) -> bool:
        """验证交易系统"""
        logger.info("🔍 验证交易系统...")

        try:
            # 1. 检查所有服务健康状态
            logger.info("📋 检查服务健康状态...")
            all_healthy = True

            for service_name, service_config in self.services.items():
                if service_config.get('enabled', True):
                    health_url = service_config['health_url']
                    if self._check_service_health(health_url, 3):
                        logger.info(f"✅ {service_name} 健康")
                    else:
                        logger.error(f"❌ {service_name} 不健康")
                        all_healthy = False

            if not all_healthy:
                logger.error("❌ 部分服务不健康")
                return False

            # 2. 测试策略引擎
            logger.info("📋 测试策略引擎...")
            try:
                response = requests.get(
                    "http://localhost:8003/api/strategy/status",
                    timeout=10
                )
                if response.status_code == 200:
                    logger.info("✅ 策略引擎响应正常")
                else:
                    logger.error(f"❌ 策略引擎响应异常: {response.status_code}")
                    return False
            except Exception as e:
                logger.error(f"❌ 策略引擎测试失败: {e}")
                return False

            # 3. 测试执行器
            logger.info("📋 测试执行器...")
            try:
                test_signal = {
                    "signal": {
                        "signal": "HOLD",
                        "symbol": "BTC-USDT",
                        "confidence": 0.5,
                        "decision_id": "test_signal_001"
                    },
                    "use_demo": True,
                    "stop_loss_pct": 0.03,
                    "take_profit_pct": 0.06
                }

                response = requests.post(
                    "http://localhost:8002/api/execute-trade",
                    json=test_signal,
                    headers={"X-Service-Token": "athena-trading-token"},
                    timeout=10
                )

                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"✅ 执行器响应正常: {result.get('status')}")
                else:
                    logger.error(f"❌ 执行器响应异常: {response.status_code}")
                    return False
            except Exception as e:
                logger.error(f"❌ 执行器测试失败: {e}")
                return False

            logger.info("✅ 交易系统验证完成")
            return True

        except Exception as e:
            logger.error(f"❌ 交易系统验证失败: {e}")
            return False

    def start_trading_loop(self):
        """启动交易循环"""
        logger.info("🔄 启动交易循环...")

        try:
            # 触发策略引擎开始交易
            response = requests.post(
                "http://localhost:8003/api/strategy/start",
                json={"symbols": ["BTC-USDT"], "timeframe": "15m"},
                headers={"X-Service-Token": "athena-trading-token"},
                timeout=10
            )

            if response.status_code == 200:
                logger.info("✅ 交易循环启动成功")
                return True
            else:
                logger.error(f"❌ 交易循环启动失败: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ 启动交易循环失败: {e}")
            return False

    def stop_services(self):
        """停止所有服务"""
        logger.info("🛑 停止所有服务...")

        # 停止交易循环
        try:
            requests.post(
                "http://localhost:8003/api/strategy/stop",
                headers={"X-Service-Token": "athena-trading-token"},
                timeout=5
            )
        except:
            pass

        # 停止服务进程
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

    def show_status(self):
        """显示交易状态"""
        print("\n" + "="*60)
        print("🚀 Athena Trader 交易系统状态")
        print("="*60)

        # 显示服务状态
        for service_name, service_config in self.services.items():
            if service_config.get('enabled', True):
                health_url = service_config['health_url']
                try:
                    response = requests.get(health_url, timeout=3)
                    status = "🟢 健康" if response.status_code == 200 else "🔴 异常"
                except:
                    status = "🔴 离线"

                print(f"  {service_name}: {status} (端口: {service_config['port']})")

        print()
        print("🌐 访问地址:")
        print("  数据管理器: http://localhost:8000")
        print("  风险管理器: http://localhost:8001")
        print("  执行器: http://localhost:8002")
        print("  策略引擎: http://localhost:8003")
        print()
        print("📊 交易状态:")
        print("  双均线策略: 运行中")
        print("  数据源: OKX Demo API")
        print("="*60)


def signal_handler(signum, frame):
    """信号处理器"""
    logger.info("收到停止信号，正在停止交易...")
    if 'launcher' in globals():
        launcher.stop_services()
    sys.exit(0)


def main():
    """主函数"""
    import signal

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 创建启动器实例
    global launcher
    launcher = TradingLauncher()

    try:
        print("🚀 Athena Trader 全能交易启动器")
        print("="*60)

        # 1. 检查前置条件
        if not launcher.check_prerequisites():
            print("❌ 前置条件检查失败，无法启动交易")
            sys.exit(1)

        # 2. 启动服务
        if not launcher.start_services():
            print("❌ 服务启动失败，无法开始交易")
            sys.exit(1)

        # 3. 验证交易系统
        if not launcher.verify_trading_system():
            print("❌ 交易系统验证失败")
            launcher.stop_services()
            sys.exit(1)

        # 4. 启动交易循环
        if not launcher.start_trading_loop():
            print("❌ 交易循环启动失败")
            launcher.stop_services()
            sys.exit(1)

        # 5. 显示状态
        launcher.show_status()

        print("\n🎉 交易系统启动成功！")
        print("📈 双均线策略已开始运行")
        print("🔄 实时监控 BTC-USDT 15分钟K线")
        print("⚡ 自动生成交易信号")
        print("\n按 Ctrl+C 停止交易...")

        # 保持运行
        try:
            while True:
                time.sleep(10)
                # 定期检查服务状态
                for service_name, process in launcher.service_processes.items():
                    if process.poll() is not None:
                        logger.error(f"❌ 服务 {service_name} 意外退出")
                        launcher.stop_services()
                        sys.exit(1)
        except KeyboardInterrupt:
            pass

    except Exception as e:
        logger.error(f"❌ 启动过程中发生错误: {e}")
        launcher.stop_services()
        sys.exit(1)

    finally:
        launcher.stop_services()
        print("\n✅ 交易系统已安全停止")


if __name__ == "__main__":
    main()
