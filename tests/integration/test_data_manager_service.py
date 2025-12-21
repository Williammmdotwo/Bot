#!/usr/bin/env python3
"""
数据管理服务综合测试脚本
Comprehensive Test Script for Data Manager Service
"""

import requests
import json
import time
import sys
import os
import redis
import logging
from typing import Dict, Any, List
import subprocess
import psutil

# 添加项目路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from data_manager.technical_indicators import TechnicalIndicators
    from data_manager.rest_client import RESTClient
except ImportError as e:
    print(f"模块导入错误: {e}")
    print(f"当前Python路径: {sys.path}")
    sys.exit(1)

class DataManagerServiceTester:
    def __init__(self):
        self.logger = self._setup_logger()
        self.service_url = "http://localhost:8004"
        self.test_symbol = "BTC-USDT"
        self.test_results = {}
        
    def _setup_logger(self):
        """设置日志记录器"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)
    
    def test_service_health(self) -> Dict[str, Any]:
        """测试服务健康状态"""
        self.logger.info("=== 测试服务健康状态 ===")
        result = {
            "test_name": "service_health",
            "status": "unknown",
            "details": {},
            "error": None
        }
        
        try:
            # 测试根端点
            response = requests.get(f"{self.service_url}/", timeout=10)
            if response.status_code == 200:
                result["details"]["root_endpoint"] = "OK"
                self.logger.info("✓ 根端点响应正常")
            else:
                result["details"]["root_endpoint"] = f"FAILED: {response.status_code}"
                self.logger.error(f"✗ 根端点响应异常: {response.status_code}")
            
            # 测试健康检查端点
            response = requests.get(f"{self.service_url}/health", timeout=10)
            if response.status_code == 200:
                health_data = response.json()
                result["details"]["health_endpoint"] = "OK"
                result["details"]["health_data"] = health_data
                self.logger.info(f"✓ 健康检查正常: {health_data}")
            else:
                result["details"]["health_endpoint"] = f"FAILED: {response.status_code}"
                self.logger.error(f"✗ 健康检查异常: {response.status_code}")
            
            result["status"] = "passed" if "OK" in result["details"].values() else "failed"
            
        except requests.exceptions.ConnectionError:
            result["status"] = "failed"
            result["error"] = "服务未运行或无法连接"
            self.logger.error("✗ 无法连接到数据管理服务")
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            self.logger.error(f"✗ 健康检查测试失败: {e}")
        
        return result
    
    def test_market_data_api(self) -> Dict[str, Any]:
        """测试市场数据API端点"""
        self.logger.info("=== 测试市场数据API端点 ===")
        result = {
            "test_name": "market_data_api",
            "status": "unknown",
            "details": {},
            "error": None
        }
        
        try:
            # 测试演示数据API
            self.logger.info("测试演示数据API...")
            response = requests.get(
                f"{self.service_url}/api/market-data/{self.test_symbol}?use_demo=true",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                result["details"]["demo_api"] = "OK"
                result["details"]["demo_data_structure"] = self._validate_market_data_structure(data)
                self.logger.info("✓ 演示数据API响应正常")
                self.logger.info(f"  数据状态: {data.get('data_status', 'unknown')}")
                self.logger.info(f"  当前价格: {data.get('current_price', 0)}")
                self.logger.info(f"  处理时间: {data.get('processing_time', 0):.2f}s")
            else:
                result["details"]["demo_api"] = f"FAILED: {response.status_code}"
                result["error"] = f"API响应错误: {response.status_code}"
                self.logger.error(f"✗ 演示数据API失败: {response.status_code}")
                if response.text:
                    self.logger.error(f"  错误详情: {response.text}")
            
            # 测试生产数据API（如果可用）
            self.logger.info("测试生产数据API...")
            try:
                response = requests.get(
                    f"{self.service_url}/api/market-data/{self.test_symbol}?use_demo=false",
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    result["details"]["production_api"] = "OK"
                    result["details"]["production_data_structure"] = self._validate_market_data_structure(data)
                    self.logger.info("✓ 生产数据API响应正常")
                else:
                    result["details"]["production_api"] = f"FAILED: {response.status_code}"
                    self.logger.warning(f"⚠ 生产数据API失败: {response.status_code}")
                    
            except Exception as e:
                result["details"]["production_api"] = f"ERROR: {str(e)}"
                self.logger.warning(f"⚠ 生产数据API测试异常: {e}")
            
            result["status"] = "passed" if result["details"].get("demo_api") == "OK" else "failed"
            
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            self.logger.error(f"✗ 市场数据API测试失败: {e}")
        
        return result
    
    def _validate_market_data_structure(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """验证市场数据结构"""
        validation = {
            "is_valid": True,
            "missing_fields": [],
            "invalid_fields": [],
            "data_quality": "unknown"
        }
        
        required_fields = [
            "symbol", "current_price", "ticker", "orderbook", 
            "recent_trades", "technical_analysis", "data_status"
        ]
        
        for field in required_fields:
            if field not in data:
                validation["missing_fields"].append(field)
                validation["is_valid"] = False
        
        # 检查技术分析数据
        if "technical_analysis" in data:
            ta = data["technical_analysis"]
            if isinstance(ta, dict) and ta:
                validation["data_quality"] = "good"
                if "error" in ta:
                    validation["invalid_fields"].append("technical_analysis_contains_error")
                    validation["data_quality"] = "degraded"
            else:
                validation["data_quality"] = "poor"
        
        # 检查价格数据
        if "current_price" in data:
            price = data["current_price"]
            if not isinstance(price, (int, float)) or price <= 0:
                validation["invalid_fields"].append("invalid_current_price")
                validation["data_quality"] = "poor"
        
        return validation
    
    def test_redis_connection(self) -> Dict[str, Any]:
        """测试Redis连接状态"""
        self.logger.info("=== 测试Redis连接状态 ===")
        result = {
            "test_name": "redis_connection",
            "status": "unknown",
            "details": {},
            "error": None
        }
        
        try:
            # 尝试连接Redis
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                redis_client = redis.from_url(redis_url, decode_responses=True)
            else:
                redis_host = os.getenv("REDIS_HOST", "localhost")
                redis_port = os.getenv("REDIS_PORT", "6379")
                redis_password = os.getenv("REDIS_PASSWORD")
                
                if redis_password:
                    redis_client = redis.Redis(
                        host=redis_host, port=redis_port, password=redis_password, decode_responses=True
                    )
                else:
                    redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
            
            # 测试连接
            redis_client.ping()
            result["details"]["connection"] = "OK"
            self.logger.info("✓ Redis连接成功")
            
            # 检查数据
            info = redis_client.info()
            result["details"]["redis_info"] = {
                "used_memory": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0)
            }
            self.logger.info(f"  内存使用: {result['details']['redis_info']['used_memory']}")
            self.logger.info(f"  连接客户端: {result['details']['redis_info']['connected_clients']}")
            
            # 检查缓存的数据
            keys = redis_client.keys(f"*{self.test_symbol}*")
            result["details"]["cached_keys"] = len(keys)
            self.logger.info(f"  缓存的{self.test_symbol}相关键: {len(keys)}")
            
            if keys:
                sample_keys = keys[:5]  # 显示前5个键
                for key in sample_keys:
                    key_type = redis_client.type(key)
                    ttl = redis_client.ttl(key)
                    self.logger.info(f"    {key} ({key_type}, TTL: {ttl}s)")
            
            result["status"] = "passed"
            
        except redis.ConnectionError:
            result["status"] = "failed"
            result["error"] = "Redis连接失败"
            self.logger.error("✗ Redis连接失败")
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            self.logger.error(f"✗ Redis测试失败: {e}")
        
        return result
    
    def test_technical_indicators(self) -> Dict[str, Any]:
        """测试技术指标计算"""
        self.logger.info("=== 测试技术指标计算 ===")
        result = {
            "test_name": "technical_indicators",
            "status": "unknown",
            "details": {},
            "error": None
        }
        
        try:
            # 生成测试数据
            test_ohlcv = self._generate_test_ohlcv_data(100)
            self.logger.info(f"生成测试数据: {len(test_ohlcv)} 个K线")
            
            # 测试技术指标计算
            start_time = time.time()
            indicators = TechnicalIndicators.calculate_all_indicators(test_ohlcv)
            calculation_time = time.time() - start_time
            
            result["details"]["calculation_time"] = calculation_time
            result["details"]["indicators_count"] = len(indicators) if isinstance(indicators, dict) else 0
            
            if isinstance(indicators, dict) and "error" not in indicators:
                result["details"]["indicators_sample"] = {
                    "rsi": indicators.get("rsi"),
                    "macd": indicators.get("macd"),
                    "bollinger": indicators.get("bollinger"),
                    "trend": indicators.get("trend"),
                    "momentum": indicators.get("momentum")
                }
                result["status"] = "passed"
                self.logger.info("✓ 技术指标计算成功")
                self.logger.info(f"  计算时间: {calculation_time:.3f}s")
                self.logger.info(f"  RSI: {indicators.get('rsi', 'N/A')}")
                self.logger.info(f"  趋势: {indicators.get('trend', 'N/A')}")
                self.logger.info(f"  动量: {indicators.get('momentum', 'N/A')}")
            else:
                result["status"] = "failed"
                result["error"] = indicators.get("error", "Unknown error")
                self.logger.error(f"✗ 技术指标计算失败: {result['error']}")
            
            # 测试边界情况
            self.logger.info("测试边界情况...")
            
            # 测试空数据
            empty_result = TechnicalIndicators.calculate_all_indicators([])
            if "error" in empty_result:
                result["details"]["empty_data_handling"] = "OK"
            else:
                result["details"]["empty_data_handling"] = "FAILED"
            
            # 测试数据不足
            insufficient_result = TechnicalIndicators.calculate_all_indicators(test_ohlcv[:5])
            if "error" in insufficient_result:
                result["details"]["insufficient_data_handling"] = "OK"
            else:
                result["details"]["insufficient_data_handling"] = "FAILED"
            
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            self.logger.error(f"✗ 技术指标测试失败: {e}")
        
        return result
    
    def _generate_test_ohlcv_data(self, count: int) -> List[List]:
        """生成测试用的OHLCV数据"""
        import random
        import math
        
        data = []
        base_price = 50000  # BTC基础价格
        current_time = int(time.time() * 1000) - count * 5 * 60 * 1000  # 5分钟间隔
        
        for i in range(count):
            # 模拟价格波动
            price_change = random.uniform(-0.02, 0.02)  # ±2%波动
            base_price *= (1 + price_change)
            
            open_price = base_price
            high_price = open_price * random.uniform(1.0, 1.01)
            low_price = open_price * random.uniform(0.99, 1.0)
            close_price = random.uniform(low_price, high_price)
            volume = random.uniform(100, 1000)
            
            data.append([
                current_time + i * 5 * 60 * 1000,  # timestamp
                open_price,  # open
                high_price,  # high
                low_price,   # low
                close_price, # close
                volume       # volume
            ])
        
        return data
    
    def test_rest_client(self) -> Dict[str, Any]:
        """测试REST客户端"""
        self.logger.info("=== 测试REST客户端 ===")
        result = {
            "test_name": "rest_client",
            "status": "unknown",
            "details": {},
            "error": None
        }
        
        try:
            # 测试演示环境REST客户端
            self.logger.info("测试演示环境REST客户端...")
            demo_client = RESTClient(use_demo=True)
            result["details"]["demo_client_init"] = "OK"
            
            # 测试获取ticker
            try:
                ticker = demo_client.fetch_ticker(self.test_symbol)
                if ticker:
                    result["details"]["demo_ticker"] = "OK"
                    result["details"]["demo_ticker_price"] = ticker.get("last", 0)
                    self.logger.info(f"✓ 演示环境ticker获取成功: {ticker.get('last', 0)}")
                else:
                    result["details"]["demo_ticker"] = "FAILED"
            except Exception as e:
                result["details"]["demo_ticker"] = f"ERROR: {str(e)}"
                self.logger.warning(f"⚠ 演示环境ticker获取失败: {e}")
            
            # 测试获取OHLCV数据
            try:
                since = int((time.time() - 300 * 10) * 1000)  # 最近10个5分钟K线
                ohlcv = demo_client.fetch_ohlcv(self.test_symbol, since, 10, "5m")
                if ohlcv:
                    result["details"]["demo_ohlcv"] = "OK"
                    result["details"]["demo_ohlcv_count"] = len(ohlcv)
                    self.logger.info(f"✓ 演示环境OHLCV获取成功: {len(ohlcv)}个K线")
                else:
                    result["details"]["demo_ohlcv"] = "FAILED"
            except Exception as e:
                result["details"]["demo_ohlcv"] = f"ERROR: {str(e)}"
                self.logger.warning(f"⚠ 演示环境OHLCV获取失败: {e}")
            
            result["status"] = "passed" if result["details"].get("demo_client_init") == "OK" else "failed"
            
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            self.logger.error(f"✗ REST客户端测试失败: {e}")
        
        return result
    
    def check_service_logs(self) -> Dict[str, Any]:
        """检查服务日志"""
        self.logger.info("=== 检查服务日志 ===")
        result = {
            "test_name": "service_logs",
            "status": "unknown",
            "details": {},
            "error": None
        }
        
        try:
            # 检查日志目录
            log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
            if os.path.exists(log_dir):
                log_files = [f for f in os.listdir(log_dir) if f.endswith('.log')]
                result["details"]["log_files"] = log_files
                
                # 检查最新的日志文件
                if log_files:
                    latest_log = max(log_files, key=lambda f: os.path.getmtime(os.path.join(log_dir, f)))
                    log_path = os.path.join(log_dir, latest_log)
                    
                    # 读取最后几行日志
                    with open(log_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        recent_lines = lines[-10:] if len(lines) > 10 else lines
                    
                    result["details"]["recent_log_entries"] = [line.strip() for line in recent_lines]
                    result["details"]["latest_log_file"] = latest_log
                    self.logger.info(f"✓ 找到日志文件: {latest_log}")
                    self.logger.info(f"  最近日志条目: {len(recent_lines)}")
                else:
                    result["details"]["log_files"] = []
                    self.logger.warning("⚠ 未找到日志文件")
            else:
                result["details"]["log_directory"] = "NOT_FOUND"
                self.logger.warning("⚠ 日志目录不存在")
            
            result["status"] = "passed"
            
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            self.logger.error(f"✗ 日志检查失败: {e}")
        
        return result
    
    def run_all_tests(self) -> Dict[str, Any]:
        """运行所有测试"""
        self.logger.info("开始运行数据管理服务综合测试...")
        
        tests = [
            self.test_service_health,
            self.test_market_data_api,
            self.test_redis_connection,
            self.test_technical_indicators,
            self.test_rest_client,
            self.check_service_logs
        ]
        
        results = {
            "test_suite": "data_manager_service",
            "timestamp": time.time(),
            "total_tests": len(tests),
            "passed": 0,
            "failed": 0,
            "test_results": {}
        }
        
        for test_func in tests:
            try:
                test_result = test_func()
                results["test_results"][test_result["test_name"]] = test_result
                
                if test_result["status"] == "passed":
                    results["passed"] += 1
                else:
                    results["failed"] += 1
                    
            except Exception as e:
                self.logger.error(f"测试执行异常: {test_func.__name__} - {e}")
                results["test_results"][test_func.__name__] = {
                    "test_name": test_func.__name__,
                    "status": "error",
                    "error": str(e)
                }
                results["failed"] += 1
        
        # 生成测试总结
        results["success_rate"] = (results["passed"] / results["total_tests"]) * 100
        results["overall_status"] = "PASSED" if results["failed"] == 0 else "FAILED"
        
        return results
    
    def print_test_summary(self, results: Dict[str, Any]):
        """打印测试总结"""
        try:
            print("\n" + "="*60)
            print("数据管理服务测试总结")
            print("="*60)
            print(f"总测试数: {results['total_tests']}")
            print(f"通过: {results['passed']}")
            print(f"失败: {results['failed']}")
            print(f"成功率: {results['success_rate']:.1f}%")
            print(f"总体状态: {results['overall_status']}")
            print("\n详细结果:")
            
            for test_name, result in results["test_results"].items():
                status_icon = "PASS" if result["status"] == "passed" else "FAIL"
                print(f"  {status_icon} {test_name}: {result['status'].upper()}")
                if result.get("error"):
                    print(f"    错误: {result['error']}")
            
            print("="*60)
        except UnicodeEncodeError:
            # 处理字符编码问题
            import sys
            print("\n" + "="*60)
            print("Data Manager Service Test Summary")
            print("="*60)
            print(f"Total tests: {results['total_tests']}")
            print(f"Passed: {results['passed']}")
            print(f"Failed: {results['failed']}")
            print(f"Success rate: {results['success_rate']:.1f}%")
            print(f"Overall status: {results['overall_status']}")
            print("\nDetailed results:")
            
            for test_name, result in results["test_results"].items():
                status_icon = "PASS" if result["status"] == "passed" else "FAIL"
                print(f"  {status_icon} {test_name}: {result['status'].upper()}")
                if result.get("error"):
                    print(f"    Error: {result['error']}")
            
            print("="*60)


def main():
    """主函数"""
    tester = DataManagerServiceTester()
    
    try:
        results = tester.run_all_tests()
        tester.print_test_summary(results)
        
        # 保存测试结果到文件
        results_file = "data_manager_test_results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n测试结果已保存到: {results_file}")
        
        # 返回适当的退出码
        sys.exit(0 if results["overall_status"] == "PASSED" else 1)
        
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n测试执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
