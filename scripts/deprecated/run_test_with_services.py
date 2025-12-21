#!/usr/bin/env python3
"""
带服务启动的测试运行脚本
自动启动必要的服务，运行测试，然后清理
"""

import os
import sys
import time
import subprocess
import signal
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestRunner:
    """测试运行器"""
    
    def __init__(self):
        self.project_root = project_root
        self.service_manager = None
        self.test_process = None
        
    def setup_service_manager(self):
        """设置服务管理器"""
        try:
            from scripts.start_test_services import TestServiceManager
            self.service_manager = TestServiceManager()
            return True
        except ImportError as e:
            logger.error(f"无法导入服务管理器: {e}")
            return False
    
    def start_services(self) -> bool:
        """启动测试服务"""
        if not self.service_manager:
            if not self.setup_service_manager():
                return False
        
        logger.info("🚀 启动测试服务...")
        return self.service_manager.start_all_services()
    
    def stop_services(self):
        """停止测试服务"""
        if self.service_manager:
            logger.info("🛑 停止测试服务...")
            self.service_manager.stop_all_services()
    
    def run_test(self, test_name: str = "simple_trading_test") -> bool:
        """运行测试"""
        try:
            logger.info(f"🧪 运行测试: {test_name}")
            
            # 构建测试命令
            test_module = f"tests.system.{test_name}"
            cmd = [sys.executable, "-m", test_module]
            
            # 设置环境变量
            env = os.environ.copy()
            env.update({
                'PYTHONPATH': str(self.project_root),
                'ATHENA_ENV': 'test'
            })
            
            # 运行测试
            self.test_process = subprocess.Popen(
                cmd,
                cwd=self.project_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # 实时输出测试日志
            for line in iter(self.test_process.stdout.readline, ''):
                if line:
                    print(line.rstrip())
            
            # 等待测试完成
            return_code = self.test_process.wait()
            
            if return_code == 0:
                logger.info("✅ 测试完成")
                return True
            else:
                logger.error(f"❌ 测试失败，返回码: {return_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 运行测试失败: {e}")
            return False
    
    def signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"收到信号 {signum}，正在清理...")
        
        # 停止测试进程
        if self.test_process:
            try:
                self.test_process.terminate()
                self.test_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.test_process.kill()
        
        # 停止服务
        self.stop_services()
        
        sys.exit(1)
    
    def run(self, test_name: str = "simple_trading_test") -> bool:
        """运行完整的测试流程"""
        # 注册信号处理器
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        try:
            print("╔════════════════════════════════════════════════════════════╗")
            print("║              Athena Trader 自动化测试                        ║")
            print("╚════════════════════════════════════════════════════════════╝")
            print()
            
            # 1. 启动服务
            if not self.start_services():
                logger.error("❌ 服务启动失败，测试终止")
                return False
            
            # 2. 等待服务稳定
            logger.info("⏳ 等待服务稳定...")
            time.sleep(5)
            
            # 3. 验证服务健康状态
            if not self.service_manager.check_all_services():
                logger.error("❌ 部分服务不健康，测试终止")
                return False
            
            # 4. 运行测试
            success = self.run_test(test_name)
            
            return success
            
        except Exception as e:
            logger.error(f"❌ 测试流程异常: {e}")
            return False
        
        finally:
            # 5. 清理服务
            self.stop_services()

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="自动化测试运行器")
    parser.add_argument("--test", default="simple_trading_test", 
                       help="测试名称 (默认: simple_trading_test)")
    parser.add_argument("--services-only", action="store_true",
                       help="仅启动服务，不运行测试")
    
    args = parser.parse_args()
    
    runner = TestRunner()
    
    try:
        if args.services_only:
            # 仅启动服务
            if runner.setup_service_manager():
                if runner.start_services():
                    logger.info("🎉 服务启动完成，按 Ctrl+C 停止...")
                    try:
                        while True:
                            time.sleep(10)
                            if not runner.service_manager.check_all_services():
                                logger.warning("⚠️ 部分服务不健康")
                    except KeyboardInterrupt:
                        pass
                else:
                    logger.error("❌ 服务启动失败")
                    sys.exit(1)
            else:
                logger.error("❌ 无法设置服务管理器")
                sys.exit(1)
        else:
            # 运行完整测试流程
            success = runner.run(args.test)
            if success:
                logger.info("🎉 测试流程完成")
                sys.exit(0)
            else:
                logger.error("❌ 测试流程失败")
                sys.exit(1)
    
    finally:
        runner.stop_services()

if __name__ == "__main__":
    main()
