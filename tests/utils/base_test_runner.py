#!/usr/bin/env python3
"""
测试运行器基类
提供测试脚本的公共功能
"""

import json
import logging
import requests
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import os


class BaseTestRunner:
    """测试运行器基类"""
    
    def __init__(self, config_file: str = "test_config.json"):
        self.test_start_time = datetime.now()
        self.stop_event = False
        
        # 设置日志（必须在加载配置之前）
        self._setup_logging()
        self.logger = logging.getLogger(__name__)
        
        # 加载配置
        self.config = self._load_config(config_file)
        
        # 初始化统计
        self.stats = {
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'errors': [],
            'warnings': [],
            'start_time': self.test_start_time
        }
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            # 首先尝试从项目根目录加载测试配置
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = os.path.join(project_root, "config", "test.json")
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    test_config = json.load(f)
                
                # 转换服务配置为URL格式
                services = {}
                for service_name, service_config in test_config.get('services', {}).items():
                    if service_config.get('enabled', True):
                        port = service_config.get('port', 8000)
                        services[service_name.split('_')[0]] = f"http://localhost:{port}"
                
                # 合并默认配置和测试配置
                merged_config = self._get_default_config()
                merged_config['services'] = services
                # 深度合并其他配置，避免覆盖services
                for key, value in test_config.items():
                    if key != 'services':
                        merged_config[key] = value
                
                self.logger.info(f"成功加载测试配置: {config_path}")
                return merged_config
            else:
                self.logger.warning(f"测试配置文件不存在: {config_path}，使用默认配置")
                return self._get_default_config()
                
        except Exception as e:
            self.logger.warning(f"无法加载配置文件 {config_file}: {e}，使用默认配置")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "services": {
                "data": "http://localhost:8000",
                "strategy": "http://localhost:8003",
                "risk": "http://localhost:8001",
                "executor": "http://localhost:8002"
            },
            "auth": {
                "internal_token": "athena-internal-token-change-in-production"
            },
            "test_symbols": ["BTC-USDT", "ETH-USDT"],
            "timeframes": ["5m", "15m", "1h", "4h"],
            "trading": {
                "test_duration_minutes": 30,
                "signal_interval_seconds": 60,
                "progress_interval_seconds": 30,
                "use_demo": True,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06,
                "max_risk_pct": 0.02
            },
            "logging": {
                "level": "INFO",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },
            "performance": {
                "max_response_time_seconds": 30,
                "max_fetch_time_seconds": 5,
                "max_indicator_calc_time_seconds": 0.1
            }
        }
    
    def _setup_logging(self):
        """设置日志配置"""
        # 使用默认日志配置，因为此时self.config还未加载
        log_level = logging.INFO
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        # 确保日志目录存在
        os.makedirs('logs', exist_ok=True)
        
        # 创建日志文件名
        timestamp = self.test_start_time.strftime("%Y%m%d_%H%M%S")
        class_name = self.__class__.__name__
        log_file = f'logs/{class_name.lower()}_{timestamp}.log'
        
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
    
    def make_service_request(self, service_name: str, endpoint: str, 
                          data: Dict[str, Any] = None, method: str = 'GET', 
                          timeout: int = 30) -> Optional[Dict[str, Any]]:
        """向服务发送请求"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'x-service-token': self.config['auth']['internal_token']
            }
            
            service_url = self.config['services'][service_name]
            url = f"{service_url}{endpoint}"
            
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            else:
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
            
            if response.status_code == 200:
                self.stats['successful_requests'] += 1
                return response.json()
            else:
                self.stats['failed_requests'] += 1
                self.logger.error(f"Service request failed: {url} - {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.stats['failed_requests'] += 1
            self.logger.error(f"Service request error: {e}")
            return None
    
    def check_service_health(self) -> bool:
        """检查所有服务健康状态"""
        self.logger.info("检查服务健康状态...")
        
        all_healthy = True
        for service_name, service_url in self.config['services'].items():
            service_healthy = False
            for attempt in range(3):  # 重试3次
                try:
                    response = requests.get(f"{service_url}/health", timeout=15)
                    if response.status_code == 200:
                        self.logger.info(f"✅ {service_name} - 健康")
                        service_healthy = True
                        break
                    else:
                        self.logger.warning(f"⚠️ {service_name} - 状态异常: {response.status_code} (尝试 {attempt + 1}/3)")
                except Exception as e:
                    if attempt < 2:  # 不是最后一次尝试
                        self.logger.warning(f"⚠️ {service_name} - 连接失败: {e} (尝试 {attempt + 1}/3)")
                        time.sleep(2)  # 等待2秒后重试
                    else:
                        self.logger.error(f"❌ {service_name} - 连接失败: {e}")
            
            if not service_healthy:
                all_healthy = False
        
        return all_healthy
    
    def update_stats(self, test_passed: bool, error_msg: str = None, warning_msg: str = None):
        """更新测试统计"""
        self.stats['total_tests'] += 1
        
        if test_passed:
            self.stats['passed_tests'] += 1
        else:
            self.stats['failed_tests'] += 1
            if error_msg:
                self.stats['errors'].append(error_msg)
                self.logger.error(error_msg)
        
        if warning_msg:
            self.stats['warnings'].append(warning_msg)
            self.logger.warning(warning_msg)
    
    def print_progress(self, custom_info: Dict[str, Any] = None):
        """打印测试进度"""
        elapsed = datetime.now() - self.test_start_time
        
        print(f"\n📊 === 测试进度 ===")
        print(f"⏱️ 已运行: {elapsed}")
        print(f"🎯 总测试: {self.stats['total_tests']} (通过: {self.stats['passed_tests']}, 失败: {self.stats['failed_tests']})")
        print(f"✅ 成功请求: {self.stats['successful_requests']}")
        print(f"❌ 失败请求: {self.stats['failed_requests']}")
        
        # 计算成功率
        total_requests = self.stats['successful_requests'] + self.stats['failed_requests']
        if total_requests > 0:
            success_rate = (self.stats['successful_requests'] / total_requests) * 100
            print(f"📈 请求成功率: {success_rate:.1f}%")
        
        # 显示自定义信息
        if custom_info:
            for key, value in custom_info.items():
                print(f"   {key}: {value}")
        
        print("=" * 50)
    
    def generate_basic_report(self, report_title: str = "测试报告") -> str:
        """生成基础测试报告"""
        elapsed = datetime.now() - self.test_start_time
        total_requests = self.stats['successful_requests'] + self.stats['failed_requests']
        success_rate = (self.stats['successful_requests'] / total_requests * 100) if total_requests > 0 else 0
        test_success_rate = (self.stats['passed_tests'] / self.stats['total_tests'] * 100) if self.stats['total_tests'] > 0 else 0
        
        report = f"""
╔════════════════════════════════════════════════════════════╗
║                    {report_title}                              ║
╚══════════════════════════════════════════════════════════════╝

📅 测试时间: {self.test_start_time.strftime('%Y-%m-%d %H:%M:%S')} - {datetime.now().strftime('%H:%M:%S')}
⏱️ 测试时长: {elapsed}

📊 测试统计:
   🎯 总测试数: {self.stats['total_tests']}
   ✅ 通过测试: {self.stats['passed_tests']}
   ❌ 失败测试: {self.stats['failed_tests']}
   📈 测试成功率: {test_success_rate:.2f}%

🌐 请求统计:
   ✅ 成功请求: {self.stats['successful_requests']}
   ❌ 失败请求: {self.stats['failed_requests']}
   📈 请求成功率: {success_rate:.2f}%

⚠️ 警告数量: {len(self.stats['warnings'])}
❌ 错误数量: {len(self.stats['errors'])}
"""
        
        # 添加错误详情
        if self.stats['errors']:
            report += "❌ 错误详情:\n"
            for i, error in enumerate(self.stats['errors'][:5], 1):
                report += f"   {i}. {error}\n"
            if len(self.stats['errors']) > 5:
                report += f"   ... 还有 {len(self.stats['errors']) - 5} 个错误\n"
            report += "\n"
        
        # 添加警告详情
        if self.stats['warnings']:
            report += "⚠️ 警告详情:\n"
            for i, warning in enumerate(self.stats['warnings'][:5], 1):
                report += f"   {i}. {warning}\n"
            if len(self.stats['warnings']) > 5:
                report += f"   ... 还有 {len(self.stats['warnings']) - 5} 个警告\n"
            report += "\n"
        
        report += f"""
📁 日志文件: logs/{self.__class__.__name__.lower()}_{self.test_start_time.strftime('%Y%m%d_%H%M%S')}.log

🎯 测试完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        return report
    
    def save_report(self, report: str, filename_suffix: str = ""):
        """保存报告到文件"""
        try:
            timestamp = self.test_start_time.strftime("%Y%m%d_%H%M%S")
            class_name = self.__class__.__name__.lower()
            
            if filename_suffix:
                filename = f"logs/{class_name}_{filename_suffix}_{timestamp}.txt"
            else:
                filename = f"logs/{class_name}_report_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report)
                
            self.logger.info(f"报告已保存到: {filename}")
            
        except Exception as e:
            self.logger.error(f"保存报告失败: {e}")
    
    def signal_handler(self, signum, frame):
        """信号处理器"""
        self.logger.info(f"收到信号 {signum}，正在停止测试...")
        self.stop_event = True
    
    def get_test_duration(self) -> timedelta:
        """获取测试运行时长"""
        return datetime.now() - self.test_start_time
    
    def should_continue(self, max_duration: timedelta = None) -> bool:
        """检查是否应该继续测试"""
        if self.stop_event:
            return False
        
        if max_duration and self.get_test_duration() >= max_duration:
            return False
        
        return True
