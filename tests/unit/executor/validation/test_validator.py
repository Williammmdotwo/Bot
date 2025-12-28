"""
Executor验证器模块单元测试
覆盖executor/validator.py的核心功能
"""

import pytest
import json
import os
from unittest.mock import Mock, patch
import requests

# 导入测试目标
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../..'))

from src.executor.validator import validate_order_signal


class TestValidateOrderSignal:
    """validate_order_signal函数测试"""
    
    @pytest.fixture
    def mock_order_details(self):
        """模拟订单详情"""
        return {
            'symbol': 'BTC-USDT',
            'action': 'buy',
            'size': 0.001,
            'side': 'buy',
            'decision_id': 'test_decision_123'
        }
    
    @pytest.fixture
    def mock_snapshot(self):
        """模拟市场快照"""
        return {
            'symbol': 'BTC-USDT',
            'klines': [[1609459200000, 50000, 50100, 49900, 50050, 100]],
            'indicators': {'rsi': 50},
            'account': {'balance': {'BTC': 1.0}, 'positions': []},
            'data_status': 'OK'
        }
    
    def test_validate_order_signal_success(self, mock_order_details, mock_snapshot):
        """测试订单验证成功"""
        mock_response = Mock()
        mock_response.json.return_value = {"is_rational": True}
        mock_response.raise_for_status.return_value = None
        
        with patch('requests.post', return_value=mock_response) as mock_post:
            result = validate_order_signal(mock_order_details, mock_snapshot)
            
            assert result is True
            
            # 验证请求参数
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[1]['json'] == {"order_details": mock_order_details}
            assert call_args[1]['headers'] == {"Content-Type": "application/json"}
            assert call_args[1]['timeout'] == 10
    
    def test_validate_order_signal_rational_false(self, mock_order_details, mock_snapshot):
        """测试订单验证失败（is_rational为False）"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "is_rational": False,
            "error": "Order size too large"
        }
        mock_response.raise_for_status.return_value = None
        
        with patch('requests.post', return_value=mock_response):
            with pytest.raises(ValueError, match="Order validation failed: Order size too large"):
                validate_order_signal(mock_order_details, mock_snapshot)
    
    def test_validate_order_signal_rational_false_no_error(self, mock_order_details, mock_snapshot):
        """测试订单验证失败（无错误信息）"""
        mock_response = Mock()
        mock_response.json.return_value = {"is_rational": False}
        mock_response.raise_for_status.return_value = None
        
        with patch('requests.post', return_value=mock_response):
            with pytest.raises(ValueError, match="Order validation failed: Order is not rational"):
                validate_order_signal(mock_order_details, mock_snapshot)
    
    def test_validate_order_signal_network_error(self, mock_order_details, mock_snapshot):
        """测试网络错误"""
        with patch('requests.post', side_effect=requests.exceptions.ConnectionError("Network error")):
            with pytest.raises(ValueError, match="Network error calling risk-service: Network error"):
                validate_order_signal(mock_order_details, mock_snapshot)
    
    def test_validate_order_signal_timeout_error(self, mock_order_details, mock_snapshot):
        """测试超时错误"""
        with patch('requests.post', side_effect=requests.exceptions.Timeout("Request timeout")):
            with pytest.raises(ValueError, match="Network error calling risk-service: Request timeout"):
                validate_order_signal(mock_order_details, mock_snapshot)
    
    def test_validate_order_signal_http_error(self, mock_order_details, mock_snapshot):
        """测试HTTP错误"""
        with patch('requests.post', side_effect=requests.exceptions.HTTPError("500 Server Error")):
            with pytest.raises(ValueError, match="Network error calling risk-service: 500 Server Error"):
                validate_order_signal(mock_order_details, mock_snapshot)
    
    def test_validate_order_signal_json_decode_error(self, mock_order_details, mock_snapshot):
        """测试JSON解析错误"""
        mock_response = Mock()
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_response.raise_for_status.return_value = None
        
        with patch('requests.post', return_value=mock_response):
            with pytest.raises(ValueError, match="JSON parsing error from risk-service: Invalid JSON"):
                validate_order_signal(mock_order_details, mock_snapshot)
    
    def test_validate_order_signal_unexpected_error(self, mock_order_details, mock_snapshot):
        """测试意外错误"""
        with patch('requests.post', side_effect=Exception("Unexpected error")):
            with pytest.raises(ValueError, match="Unexpected error in validate_order_signal: Unexpected error"):
                validate_order_signal(mock_order_details, mock_snapshot)
    
    def test_validate_order_signal_with_config_manager(self, mock_order_details, mock_snapshot):
        """测试使用配置管理器获取风险服务URL"""
        mock_response = Mock()
        mock_response.json.return_value = {"is_rational": True}
        mock_response.raise_for_status.return_value = None
        
        with patch('requests.post', return_value=mock_response) as mock_post:
            with patch('src.executor.validator.get_config_manager') as mock_config_manager:
                mock_config = Mock()
                mock_config.get_config.return_value = {
                    'services': {
                        'risk_manager': {
                            'host': 'risk-service-custom',
                            'port': 8001
                        }
                    }
                }
                mock_config_manager.return_value = mock_config
                
                result = validate_order_signal(mock_order_details, mock_snapshot)
                
                assert result is True
                
                # 验证使用自定义URL
                mock_post.assert_called_once()
                call_args = mock_post.call_args
                assert 'risk-service-custom:8001' in call_args[0]
    
    def test_validate_order_signal_config_manager_fallback(self, mock_order_details, mock_snapshot):
        """测试配置管理器失败时回退到环境变量"""
        mock_response = Mock()
        mock_response.json.return_value = {"is_rational": True}
        mock_response.raise_for_status.return_value = None
        
        with patch('requests.post', return_value=mock_response) as mock_post:
            with patch('src.executor.validator.get_config_manager', side_effect=Exception("Config error")):
                with patch.dict(os.environ, {
                    'RISK_SERVICE_HOST': 'custom-risk-host',
                    'RISK_SERVICE_PORT': '9001'
                }):
                    result = validate_order_signal(mock_order_details, mock_snapshot)
                    
                    assert result is True
                    
                    # 验证使用环境变量
                    mock_post.assert_called_once()
                    call_args = mock_post.call_args
                    assert 'custom-risk-host:9001' in call_args[0]
    
    def test_validate_order_signal_default_fallback(self, mock_order_details, mock_snapshot):
        """测试使用默认值"""
        mock_response = Mock()
        mock_response.json.return_value = {"is_rational": True}
        mock_response.raise_for_status.return_value = None
        
        with patch('requests.post', return_value=mock_response) as mock_post:
            with patch('src.executor.validator.get_config_manager', side_effect=Exception("Config error")):
                # 清除环境变量
                with patch.dict(os.environ, {}, clear=False):
                    # 删除相关环境变量
                    env_keys = ['RISK_SERVICE_HOST', 'RISK_SERVICE_PORT']
                    for key in env_keys:
                        if key in os.environ:
                            del os.environ[key]
                    
                    result = validate_order_signal(mock_order_details, mock_snapshot)
                    
                    assert result is True
                    
                    # 验证使用默认值
                    mock_post.assert_called_once()
                    call_args = mock_post.call_args
                    assert 'risk-service:8001' in call_args[0]
    
    def test_validate_order_signal_request_details(self, mock_order_details, mock_snapshot):
        """测试请求详情"""
        mock_response = Mock()
        mock_response.json.return_value = {"is_rational": True}
        mock_response.raise_for_status.return_value = None
        
        with patch('requests.post', return_value=mock_response) as mock_post:
            validate_order_signal(mock_order_details, mock_snapshot)
            
            # 验证请求参数
            call_args = mock_post.call_args
            assert call_args[0] == 'http://risk-service:8001/api/check-order'
            assert call_args[1]['json'] == {"order_details": mock_order_details}
            assert call_args[1]['headers'] == {"Content-Type": "application/json"}
            assert call_args[1]['timeout'] == 10
    
    def test_validate_order_signal_complex_order_details(self, mock_snapshot):
        """测试复杂订单详情"""
        complex_order = {
            'symbol': 'ETH-USDT',
            'action': 'sell',
            'size': 0.1,
            'side': 'sell',
            'decision_id': 'complex_decision_456',
            'price': 2000.0,
            'type': 'limit',
            'time_in_force': 'GTC'
        }
        
        mock_response = Mock()
        mock_response.json.return_value = {"is_rational": True}
        mock_response.raise_for_status.return_value = None
        
        with patch('requests.post', return_value=mock_response) as mock_post:
            result = validate_order_signal(complex_order, mock_snapshot)
            
            assert result is True
            
            # 验证复杂订单详情被正确传递
            call_args = mock_post.call_args
            assert call_args[1]['json'] == {"order_details": complex_order}
    
    def test_validate_order_signal_empty_order_details(self, mock_snapshot):
        """测试空订单详情"""
        empty_order = {}
        
        mock_response = Mock()
        mock_response.json.return_value = {"is_rational": True}
        mock_response.raise_for_status.return_value = None
        
        with patch('requests.post', return_value=mock_response) as mock_post:
            result = validate_order_signal(empty_order, mock_snapshot)
            
            assert result is True
            
            # 验证空订单详情被正确传递
            call_args = mock_post.call_args
            assert call_args[1]['json'] == {"order_details": {}}
    
    def test_validate_order_signal_large_order_details(self, mock_snapshot):
        """测试大型订单详情"""
        large_order = {
            'symbol': 'BTC-USDT',
            'action': 'buy',
            'size': 0.001,
            'side': 'buy',
            'decision_id': 'x' * 1000,  # 长字符串
            'metadata': {
                'notes': 'y' * 500,  # 大量元数据
                'tags': ['tag'] * 100  # 大量标签
            }
        }
        
        mock_response = Mock()
        mock_response.json.return_value = {"is_rational": True}
        mock_response.raise_for_status.return_value = None
        
        with patch('requests.post', return_value=mock_response) as mock_post:
            result = validate_order_signal(large_order, mock_snapshot)
            
            assert result is True
            
            # 验证大型订单详情被正确传递
            call_args = mock_post.call_args
            assert call_args[1]['json'] == {"order_details": large_order}


class TestValidatorIntegration:
    """验证器集成测试"""
    
    def test_validate_order_signal_real_service_simulation(self):
        """模拟真实服务调用"""
        order_details = {
            'symbol': 'BTC-USDT',
            'action': 'buy',
            'size': 0.001,
            'side': 'buy'
        }
        snapshot = {'data_status': 'OK'}
        
        # 模拟不同的响应场景
        test_cases = [
            {"is_rational": True, "expected_result": True},
            {"is_rational": False, "error": "Insufficient balance", "expected_result": ValueError},
            {"is_rational": False, "expected_result": ValueError}
        ]
        
        for case in test_cases:
            mock_response = Mock()
            mock_response.json.return_value = {k: v for k, v in case.items() if k != "expected_result"}
            mock_response.raise_for_status.return_value = None
            
            with patch('requests.post', return_value=mock_response):
                if case["expected_result"] is True:
                    result = validate_order_signal(order_details, snapshot)
                    assert result is True
                else:
                    with pytest.raises(ValueError):
                        validate_order_signal(order_details, snapshot)
    
    def test_validate_order_signal_error_scenarios(self):
        """测试各种错误场景"""
        order_details = {'symbol': 'BTC-USDT', 'action': 'buy', 'size': 0.001}
        snapshot = {'data_status': 'OK'}
        
        error_scenarios = [
            requests.exceptions.ConnectionError("Connection refused"),
            requests.exceptions.Timeout("Request timeout"),
            requests.exceptions.HTTPError("500 Internal Server Error"),
            json.JSONDecodeError("Invalid JSON", "", 0),
            Exception("Unexpected error")
        ]
        
        for error in error_scenarios:
            if isinstance(error, json.JSONDecodeError):
                mock_response = Mock()
                mock_response.json.side_effect = error
                mock_response.raise_for_status.return_value = None
                with patch('requests.post', return_value=mock_response):
                    with pytest.raises(ValueError):
                        validate_order_signal(order_details, snapshot)
            else:
                with patch('requests.post', side_effect=error):
                    with pytest.raises(ValueError):
                        validate_order_signal(order_details, snapshot)
    
    def test_validate_order_signal_configuration_scenarios(self):
        """测试各种配置场景"""
        order_details = {'symbol': 'BTC-USDT', 'action': 'buy', 'size': 0.001}
        snapshot = {'data_status': 'OK'}
        
        mock_response = Mock()
        mock_response.json.return_value = {"is_rational": True}
        mock_response.raise_for_status.return_value = None
        
        config_scenarios = [
            # 配置管理器成功
            {
                'config_success': True,
                'config_data': {
                    'services': {
                        'risk_manager': {
                            'host': 'config-host',
                            'port': 9000
                        }
                    }
                },
                'expected_url': 'config-host:9000'
            },
            # 配置管理器失败，使用环境变量
            {
                'config_success': False,
                'env_vars': {
                    'RISK_SERVICE_HOST': 'env-host',
                    'RISK_SERVICE_PORT': '8000'
                },
                'expected_url': 'env-host:8000'
            },
            # 配置管理器失败，使用默认值
            {
                'config_success': False,
                'expected_url': 'risk-service:8001'
            }
        ]
        
        for scenario in config_scenarios:
            with patch('requests.post', return_value=mock_response) as mock_post:
                if scenario.get('config_success', False):
                    with patch('src.executor.validator.get_config_manager') as mock_config_manager:
                        mock_config = Mock()
                        mock_config.get_config.return_value = scenario['config_data']
                        mock_config_manager.return_value = mock_config
                        
                        result = validate_order_signal(order_details, snapshot)
                        assert result is True
                else:
                    with patch('src.executor.validator.get_config_manager', side_effect=Exception("Config error")):
                        env_vars = scenario.get('env_vars', {})
                        with patch.dict(os.environ, env_vars, clear=False):
                            result = validate_order_signal(order_details, snapshot)
                            assert result is True
                
                # 验证URL
                call_args = mock_post.call_args
                assert scenario['expected_url'] in call_args[0]
