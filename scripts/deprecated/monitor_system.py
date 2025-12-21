#!/usr/bin/env python3
"""
系统监控脚本
提供实时性能监控、健康检查和回归测试
"""

import time
import logging
import json
import sys
import signal
import asyncio
import threading
import requests
import psutil
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import traceback
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/system_monitor_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class SystemMonitor:
    """系统监控类"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.monitor_start_time = datetime.now()
        self.stop_event = False
        
        # 监控配置
        self.monitor_interval = 60  # 60秒检查一次
        self.health_check_interval = 30  # 30秒健康检查
        self.performance_history = []
        self.alert_thresholds = {
            'cpu_usage': 80.0,  # CPU使用率阈值
            'memory_usage': 85.0,  # 内存使用率阈值
            'response_time': 10.0,  # API响应时间阈值(秒)
            'error_rate': 10.0,  # 错误率阈值(%)
            'disk_usage': 90.0   # 磁盘使用率阈值
        }
        
        # 监控统计
        self.stats = {
            'total_checks': 0,
            'successful_checks': 0,
            'failed_checks': 0,
            'alerts_triggered': 0,
            'performance_samples': [],
            'health_status': {},
            'system_metrics': [],
            'alerts': []
        }
        
        # 服务端点
        self.services = {
            'data': 'http://localhost:8004',
            'strategy': 'http://localhost:8003',
            'risk': 'http://localhost:8001',
            'executor': 'http://localhost:8002'
        }
    
    def monitor_system_resources(self):
        """监控系统资源使用情况"""
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # 内存使用情况
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # 磁盘使用情况
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            
            # 网络统计
            network = psutil.net_io_counters()
            
            system_metrics = {
                'timestamp': datetime.now(),
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
                'memory_used_gb': memory.used / (1024**3),
                'memory_total_gb': memory.total / (1024**3),
                'disk_percent': disk_percent,
                'disk_used_gb': disk.used / (1024**3),
                'disk_total_gb': disk.total / (1024**3),
                'network_bytes_sent': network.bytes_sent,
                'network_bytes_recv': network.bytes_recv
            }
            
            self.stats['system_metrics'].append(system_metrics)
            
            # 检查阈值并触发警报
            self._check_resource_thresholds(system_metrics)
            
            self.logger.debug(f"系统资源: CPU={cpu_percent:.1f}%, 内存={memory_percent:.1f}%, 磁盘={disk_percent:.1f}%")
            
            return system_metrics
            
        except Exception as e:
            self.logger.error(f"系统资源监控失败: {e}")
            return None
    
    def _check_resource_thresholds(self, metrics: Dict[str, Any]):
        """检查资源使用阈值"""
        alerts = []
        
        # CPU检查
        if metrics['cpu_percent'] > self.alert_thresholds['cpu_usage']:
            alert = {
                'type': 'cpu_high',
                'message': f"CPU使用率过高: {metrics['cpu_percent']:.1f}%",
                'severity': 'warning' if metrics['cpu_percent'] < 90 else 'critical',
                'timestamp': datetime.now()
            }
            alerts.append(alert)
        
        # 内存检查
        if metrics['memory_percent'] > self.alert_thresholds['memory_usage']:
            alert = {
                'type': 'memory_high',
                'message': f"内存使用率过高: {metrics['memory_percent']:.1f}%",
                'severity': 'warning' if metrics['memory_percent'] < 95 else 'critical',
                'timestamp': datetime.now()
            }
            alerts.append(alert)
        
        # 磁盘检查
        if metrics['disk_percent'] > self.alert_thresholds['disk_usage']:
            alert = {
                'type': 'disk_high',
                'message': f"磁盘使用率过高: {metrics['disk_percent']:.1f}%",
                'severity': 'warning' if metrics['disk_percent'] < 95 else 'critical',
                'timestamp': datetime.now()
            }
            alerts.append(alert)
        
        # 处理警报
        for alert in alerts:
            self._handle_alert(alert)
    
    def check_service_health(self):
        """检查服务健康状态"""
        health_status = {}
        
        for service_name, service_url in self.services.items():
            try:
                # 健康检查
                start_time = time.time()
                response = requests.get(f"{service_url}/health", timeout=10)
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    health_status[service_name] = {
                        'status': 'healthy',
                        'response_time': response_time,
                        'timestamp': datetime.now(),
                        'last_check': 'success'
                    }
                    self.logger.debug(f"✅ {service_name} 健康 ({response_time:.3f}s)")
                else:
                    health_status[service_name] = {
                        'status': 'unhealthy',
                        'response_time': response_time,
                        'timestamp': datetime.now(),
                        'last_check': 'failed',
                        'error': f"HTTP {response.status_code}"
                    }
                    self.logger.warning(f"❌ {service_name} 不健康: HTTP {response.status_code}")
                
                # 检查响应时间阈值
                if response_time > self.alert_thresholds['response_time']:
                    alert = {
                        'type': 'response_time_high',
                        'service': service_name,
                        'message': f"{service_name} 响应时间过长: {response_time:.2f}s",
                        'severity': 'warning',
                        'timestamp': datetime.now()
                    }
                    self._handle_alert(alert)
                
            except Exception as e:
                health_status[service_name] = {
                    'status': 'error',
                    'response_time': None,
                    'timestamp': datetime.now(),
                    'last_check': 'error',
                    'error': str(e)
                }
                self.logger.error(f"❌ {service_name} 健康检查失败: {e}")
                
                alert = {
                    'type': 'service_down',
                    'service': service_name,
                    'message': f"{service_name} 服务不可用: {str(e)}",
                    'severity': 'critical',
                    'timestamp': datetime.now()
                }
                self._handle_alert(alert)
        
        self.stats['health_status'] = health_status
        return health_status
    
    def check_api_performance(self):
        """检查API性能"""
        try:
            # 测试数据管理器API性能
            symbol = "BTC-USDT"
            start_time = time.time()
            
            response = requests.get(
                f"{self.services['data']}/api/market-data/{symbol}?use_demo=true",
                timeout=30
            )
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                performance_sample = {
                    'timestamp': datetime.now(),
                    'response_time': response_time,
                    'status_code': response.status_code,
                    'service': 'data_api',
                    'symbol': symbol
                }
                
                self.stats['performance_samples'].append(performance_sample)
                
                # 检查性能阈值
                if response_time > self.alert_thresholds['response_time']:
                    alert = {
                        'type': 'api_performance_slow',
                        'message': f"API响应时间过长: {response_time:.2f}s",
                        'severity': 'warning',
                        'timestamp': datetime.now()
                    }
                    self._handle_alert(alert)
                
                self.logger.debug(f"API性能测试: {response_time:.3f}s")
            else:
                self.logger.warning(f"API性能测试失败: HTTP {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"API性能检查失败: {e}")
    
    def run_regression_test(self):
        """运行回归测试"""
        self.logger.info("🔄 运行回归测试...")
        
        try:
            # 导入综合测试
            import subprocess
            import os
            
            # 运行综合测试脚本
            test_script = os.path.join(os.path.dirname(__file__), 'test_system_comprehensive.py')
            
            # 记录测试开始时间
            start_time = time.time()
            
            result = subprocess.run(
                [sys.executable, test_script],
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            if result.returncode == 0:
                self.logger.info("✅ 回归测试通过")
                regression_status = {
                    'status': 'passed',
                    'timestamp': datetime.now(),
                    'duration': time.time() - start_time
                }
            else:
                self.logger.error(f"❌ 回归测试失败: {result.stderr}")
                regression_status = {
                    'status': 'failed',
                    'timestamp': datetime.now(),
                    'duration': time.time() - start_time,
                    'error': result.stderr
                }
                
                alert = {
                    'type': 'regression_test_failed',
                    'message': "回归测试失败",
                    'severity': 'critical',
                    'timestamp': datetime.now()
                }
                self._handle_alert(alert)
            
            return regression_status
            
        except Exception as e:
            self.logger.error(f"回归测试执行失败: {e}")
            return {
                'status': 'error',
                'timestamp': datetime.now(),
                'error': str(e)
            }
    
    def _handle_alert(self, alert: Dict[str, Any]):
        """处理警报"""
        self.stats['alerts_triggered'] += 1
        self.stats['alerts'].append(alert)
        
        # 记录警报
        severity_emoji = {
            'warning': '⚠️',
            'critical': '🚨'
        }
        
        emoji = severity_emoji.get(alert['severity'], 'ℹ️')
        self.logger.warning(f"{emoji} 警报: {alert['message']}")
        
        # 可以在这里添加其他警报处理逻辑，如发送邮件、Slack通知等
    
    def generate_monitoring_report(self):
        """生成监控报告"""
        try:
            elapsed = datetime.now() - self.monitor_start_time
            
            # 计算统计信息
            total_checks = self.stats['total_checks']
            successful_checks = self.stats['successful_checks']
            failed_checks = self.stats['failed_checks']
            
            success_rate = (successful_checks / total_checks * 100) if total_checks > 0 else 0
            
            # 系统资源统计
            if self.stats['system_metrics']:
                recent_metrics = self.stats['system_metrics'][-10:]  # 最近10个样本
                avg_cpu = sum(m['cpu_percent'] for m in recent_metrics) / len(recent_metrics)
                avg_memory = sum(m['memory_percent'] for m in recent_metrics) / len(recent_metrics)
                avg_disk = sum(m['disk_percent'] for m in recent_metrics) / len(recent_metrics)
            else:
                avg_cpu = avg_memory = avg_disk = 0
            
            # API性能统计
            if self.stats['performance_samples']:
                recent_samples = self.stats['performance_samples'][-10:]  # 最近10个样本
                avg_response_time = sum(s['response_time'] for s in recent_samples) / len(recent_samples)
                max_response_time = max(s['response_time'] for s in recent_samples)
            else:
                avg_response_time = max_response_time = 0
            
            report = f"""
╔════════════════════════════════════════════════════════════╗
║                    系统监控报告                                ║
╚════════════════════════════════════════════════════════════╝

📅 监控时间: {self.monitor_start_time.strftime('%Y-%m-%d %H:%M:%S')} - {datetime.now().strftime('%H:%M:%S')}
⏱️ 监控时长: {elapsed}

📊 监控统计:
   🔍 总检查次数: {total_checks}
   ✅ 成功检查: {successful_checks}
   ❌ 失败检查: {failed_checks}
   📈 成功率: {success_rate:.2f}%
   🚨 触发警报: {self.stats['alerts_triggered']}

💻 系统资源 (最近10次平均):
   🖥️ CPU使用率: {avg_cpu:.1f}%
   🧠 内存使用率: {avg_memory:.1f}%
   💾 磁盘使用率: {avg_disk:.1f}%

🌐 API性能 (最近10次平均):
   ⚡ 平均响应时间: {avg_response_time:.3f}s
   📊 最大响应时间: {max_response_time:.3f}s

🏥 服务健康状态:
"""
            
            # 服务健康状态
            for service_name, status in self.stats['health_status'].items():
                status_emoji = "✅" if status['status'] == 'healthy' else "❌"
                response_time = status.get('response_time', 0)
                report += f"   {status_emoji} {service_name}: {status['status']} ({response_time:.3f}s)\n"
            
            # 最近警报
            if self.stats['alerts']:
                recent_alerts = self.stats['alerts'][-5:]  # 最近5个警报
                report += "\n🚨 最近警报:\n"
                for alert in recent_alerts:
                    severity_emoji = {
                        'warning': '⚠️',
                        'critical': '🚨'
                    }.get(alert['severity'], 'ℹ️')
                    report += f"   {severity_emoji} {alert['timestamp'].strftime('%H:%M:%S')} - {alert['message']}\n"
            
            report += f"""
📁 监控日志: logs/system_monitor_{self.monitor_start_time.strftime('%Y%m%d_%H%M%S')}.log

🎯 监控建议:
"""
            
            # 建议生成
            if avg_cpu > 70:
                report += "   1. CPU使用率较高，考虑优化或扩容\n"
            if avg_memory > 80:
                report += "   2. 内存使用率较高，检查内存泄漏\n"
            if avg_response_time > 5:
                report += "   3. API响应时间较长，优化性能\n"
            if self.stats['alerts_triggered'] > 10:
                report += "   4. 警报频繁，需要系统维护\n"
            
            report += f"""
🎯 监控完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            print(report)
            self.logger.info("监控报告已生成")
            
            # 保存报告到文件
            filename = f"logs/monitoring_report_{self.monitor_start_time.strftime('%Y%m%d_%H%M%S')}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report)
                
            self.logger.info(f"监控报告已保存到: {filename}")
            
        except Exception as e:
            self.logger.error(f"生成监控报告失败: {e}")
    
    def save_monitoring_data(self):
        """保存监控数据到JSON文件"""
        try:
            # 准备保存的数据
            monitoring_data = {
                'session_info': {
                    'start_time': self.monitor_start_time.isoformat(),
                    'duration_minutes': (datetime.now() - self.monitor_start_time).total_seconds() / 60,
                    'total_checks': self.stats['total_checks'],
                    'alerts_triggered': self.stats['alerts_triggered']
                },
                'system_metrics': [
                    {
                        'timestamp': m['timestamp'].isoformat(),
                        'cpu_percent': m['cpu_percent'],
                        'memory_percent': m['memory_percent'],
                        'disk_percent': m['disk_percent']
                    } for m in self.stats['system_metrics'][-100:]  # 保存最近100个样本
                ],
                'performance_samples': [
                    {
                        'timestamp': s['timestamp'].isoformat(),
                        'response_time': s['response_time'],
                        'service': s['service']
                    } for s in self.stats['performance_samples'][-50:]  # 保存最近50个样本
                ],
                'alerts': [
                    {
                        'timestamp': a['timestamp'].isoformat(),
                        'type': a['type'],
                        'message': a['message'],
                        'severity': a['severity']
                    } for a in self.stats['alerts'][-20:]  # 保存最近20个警报
                ]
            }
            
            # 保存到JSON文件
            filename = f"logs/monitoring_data_{self.monitor_start_time.strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(monitoring_data, f, indent=2, ensure_ascii=False)
                
            self.logger.debug(f"监控数据已保存到: {filename}")
            
        except Exception as e:
            self.logger.error(f"保存监控数据失败: {e}")
    
    def signal_handler(self, signum, frame):
        """信号处理器"""
        self.logger.info(f"收到信号 {signum}，正在停止监控...")
        self.stop_event = True
    
    def run_monitoring(self):
        """运行系统监控"""
        self.logger.info("🚀 开始系统监控")
        self.logger.info(f"监控开始时间: {self.monitor_start_time}")
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # 创建日志目录
        Path('logs').mkdir(exist_ok=True)
        
        try:
            last_health_check = time.time()
            last_performance_check = time.time()
            last_regression_test = time.time()
            last_data_save = time.time()
            
            while not self.stop_event:
                current_time = time.time()
                
                # 系统资源监控 (每分钟)
                if current_time - last_health_check >= self.monitor_interval:
                    self.monitor_system_resources()
                    self.check_service_health()
                    self.stats['total_checks'] += 1
                    self.stats['successful_checks'] += 1
                    last_health_check = current_time
                
                # API性能检查 (每2分钟)
                if current_time - last_performance_check >= 120:
                    self.check_api_performance()
                    last_performance_check = current_time
                
                # 回归测试 (每30分钟)
                if current_time - last_regression_test >= 1800:
                    self.run_regression_test()
                    last_regression_test = current_time
                
                # 保存监控数据 (每5分钟)
                if current_time - last_data_save >= 300:
                    self.save_monitoring_data()
                    last_data_save = current_time
                
                # 短暂休眠
                time.sleep(10)
            
            # 生成最终报告
            self.generate_monitoring_report()
            self.save_monitoring_data()
            
            self.logger.info("🎉 系统监控完成")
            
        except Exception as e:
            self.logger.error(f"监控过程中发生错误: {e}")
            self.logger.debug(traceback.format_exc())

def main():
    """主函数"""
    print("╔════════════════════════════════════════════════════════════╗")
    print("║              Athena Trader 系统监控                          ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    
    monitor = SystemMonitor()
    
    try:
        monitor.run_monitoring()
    except KeyboardInterrupt:
        monitor.stop_event = True
        monitor.generate_monitoring_report()
        monitor.save_monitoring_data()
        print("\n监控被用户中断")
    except Exception as e:
        logging.error(f"监控启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
