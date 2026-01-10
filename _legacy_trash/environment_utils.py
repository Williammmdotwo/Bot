"""
统一环境判断工具
确保所有服务使用相同的环境判断逻辑和安全默认值
支持三层标签系统：模拟数据、OKX模拟交易、OKX真实交易
"""

import os
import logging
from typing import Tuple, Dict, Any

logger = logging.getLogger(__name__)

# 三层数据源定义
DATA_SOURCE_TYPES = {
    "MOCK_DATA": "模拟数据",
    "OKX_DEMO": "OKX模拟交易", 
    "OKX_PRODUCTION": "OKX真实交易"
}

# 数据源配置映射
DATA_SOURCE_CONFIG = {
    "MOCK_DATA": {
        "use_mock": True,
        "use_demo": False,
        "description": "本地生成的模拟数据，用于离线测试"
    },
    "OKX_DEMO": {
        "use_mock": False,
        "use_demo": True,
        "description": "使用OKX Demo API进行模拟交易"
    },
    "OKX_PRODUCTION": {
        "use_mock": False,
        "use_demo": False,
        "description": "使用OKX Production API进行真实交易"
    }
}

def get_environment_config() -> Dict[str, Any]:
    """
    获取统一的环境配置
    
    Returns:
        Dict: 包含环境配置信息的字典
    """
    # 使用安全的默认值 "demo" 而不是 "production"
    okx_environment = os.getenv("OKX_ENVIRONMENT", "demo").lower()
    
    # 标准化环境值判断
    is_demo = okx_environment in ["demo", "demo环境", "demo-trading"]
    is_production = okx_environment in ["production", "prod", "生产环境"]
    
    # 如果环境值无效，默认为demo（安全优先）
    if not is_demo and not is_production:
        logger.warning(f"无效的环境值: {okx_environment}，默认使用demo环境")
        okx_environment = "demo"
        is_demo = True
        is_production = False
    
    config = {
        "okx_environment": okx_environment,
        "is_demo": is_demo,
        "is_production": is_production,
        "environment_type": "demo" if is_demo else "production"
    }
    
    logger.info(f"环境配置: {config}")
    return config

def get_api_credentials() -> Tuple[Dict[str, str], bool]:
    """
    根据环境获取对应的API密钥
    
    Returns:
        Tuple[Dict, bool]: (API密钥字典, 是否有完整密钥)
    """
    config = get_environment_config()
    is_demo = config["is_demo"]
    
    if is_demo:
        # Demo环境密钥
        credentials = {
            "api_key": os.getenv("OKX_DEMO_API_KEY", ""),
            "secret": os.getenv("OKX_DEMO_SECRET", ""),
            "passphrase": os.getenv("OKX_DEMO_PASSPHRASE", ""),
            "environment": "demo"
        }
    else:
        # 生产环境密钥
        credentials = {
            "api_key": os.getenv("OKX_API_KEY", ""),
            "secret": os.getenv("OKX_SECRET", ""),
            "passphrase": os.getenv("OKX_PASSPHRASE", ""),
            "environment": "production"
        }
    
    # 检查密钥完整性
    has_credentials = all([
        credentials["api_key"].strip(),
        credentials["secret"].strip(),
        credentials["passphrase"].strip()
    ])
    
    if not has_credentials:
        logger.warning(f"API密钥不完整 ({credentials['environment']}环境)")
    else:
        logger.info(f"API密钥配置完整 ({credentials['environment']}环境)")
    
    return credentials, has_credentials

def validate_safety() -> bool:
    """
    验证环境配置安全性
    
    Returns:
        bool: 是否安全
    """
    config = get_environment_config()
    credentials, has_credentials = get_api_credentials()
    
    # 安全检查
    safety_issues = []
    
    # 1. 检查是否为生产环境
    if config["is_production"]:
        safety_issues.append("当前为生产交易环境，存在真实交易风险")
    
    # 2. 检查API密钥配置
    if not has_credentials:
        safety_issues.append("API密钥配置不完整")
    
    # 3. 检查环境变量一致性
    raw_env = os.getenv("OKX_ENVIRONMENT", "demo")
    normalized_env = raw_env.lower() if raw_env else "demo"
    if config["okx_environment"] != normalized_env:
        safety_issues.append("环境变量读取不一致")
        logger.debug(f"环境变量不一致详情: config='{config['okx_environment']}', raw_env='{raw_env}', normalized_env='{normalized_env}'")
    
    # 4. 检查Demo环境下的生产密钥泄露
    if config["is_demo"]:
        prod_key = os.getenv("OKX_API_KEY", "")
        if prod_key and prod_key != "your_okx_api_key_here":
            safety_issues.append("Demo环境下配置了生产API密钥")
    
    if safety_issues:
        logger.error("安全检查失败:")
        for issue in safety_issues:
            logger.error(f"  - {issue}")
        return False
    else:
        logger.info("安全检查通过")
        return True

def enforce_demo_environment() -> bool:
    """
    强制使用Demo环境（用于测试和安全）
    
    Returns:
        bool: 是否成功设置为Demo环境
    """
    # 设置环境变量
    os.environ["OKX_ENVIRONMENT"] = "demo"
    
    # 验证设置
    config = get_environment_config()
    
    if config["is_demo"]:
        logger.info("✅ 已强制设置为Demo环境")
        return True
    else:
        logger.error("❌ 强制设置Demo环境失败")
        return False

def get_ccxt_config() -> Dict[str, Any]:
    """
    获取CCXT配置
    
    Returns:
        Dict: CCXT配置字典
    """
    config = get_environment_config()
    credentials, has_credentials = get_api_credentials()
    
    ccxt_config = {
        "sandbox": config["is_demo"],
        "enableRateLimit": True
    }
    
    # 如果有完整密钥，添加到配置中
    if has_credentials:
        ccxt_config.update({
            "apiKey": credentials["api_key"],
            "secret": credentials["secret"],
            "password": credentials["passphrase"]
        })
        logger.info(f"CCXT配置包含API密钥 ({config['environment_type']}环境)")
    else:
        logger.warning(f"CCXT配置不包含API密钥 ({config['environment_type']}环境) - 仅公开数据")
    
    return ccxt_config

def get_data_source_type() -> str:
    """
    获取当前数据源类型
    
    Returns:
        str: 数据源类型 (MOCK_DATA, OKX_DEMO, OKX_PRODUCTION)
    """
    # 优先级：DATA_SOURCE_MODE > USE_MOCK_DATA > OKX_ENVIRONMENT
    
    # 1. 检查强制指定的数据源
    data_source_mode = os.getenv("DATA_SOURCE_MODE", "").upper()
    if data_source_mode in DATA_SOURCE_TYPES:
        logger.info(f"使用强制指定的数据源: {data_source_mode}")
        return data_source_mode
    
    # 2. 检查是否使用Mock数据
    use_mock_data = os.getenv("USE_MOCK_DATA", "false").lower() == "true"
    if use_mock_data:
        logger.info("使用本地Mock数据")
        return "MOCK_DATA"
    
    # 3. 根据OKX环境判断
    config = get_environment_config()
    if config["is_demo"]:
        return "OKX_DEMO"
    else:
        return "OKX_PRODUCTION"

def get_data_source_config() -> Dict[str, Any]:
    """
    获取数据源配置
    
    Returns:
        Dict: 数据源配置信息
    """
    data_source_type = get_data_source_type()
    
    if data_source_type not in DATA_SOURCE_TYPES:
        logger.error(f"未知的数据源类型: {data_source_type}")
        data_source_type = "MOCK_DATA"  # 安全默认值
    
    config = DATA_SOURCE_CONFIG[data_source_type].copy()
    config.update({
        "data_source_type": data_source_type,
        "data_source_label": DATA_SOURCE_TYPES[data_source_type],
        "okx_environment": get_environment_config()["okx_environment"]
    })
    
    logger.info(f"数据源配置: {config['data_source_label']} ({data_source_type})")
    return config

def get_data_source_label() -> str:
    """
    获取数据源标签
    
    Returns:
        str: 数据源标签
    """
    data_source_type = get_data_source_type()
    return DATA_SOURCE_TYPES.get(data_source_type, "未知数据源")

def is_using_mock_data() -> bool:
    """
    检查是否使用Mock数据
    
    Returns:
        bool: 是否使用Mock数据
    """
    data_source_type = get_data_source_type()
    return data_source_type == "MOCK_DATA"

def is_using_okx_demo() -> bool:
    """
    检查是否使用OKX Demo API
    
    Returns:
        bool: 是否使用OKX Demo API
    """
    data_source_type = get_data_source_type()
    return data_source_type == "OKX_DEMO"

def is_using_okx_production() -> bool:
    """
    检查是否使用OKX Production API
    
    Returns:
        bool: 是否使用OKX Production API
    """
    data_source_type = get_data_source_type()
    return data_source_type == "OKX_PRODUCTION"

def log_environment_info(service_name: str):
    """
    记录服务环境信息
    
    Args:
        service_name: 服务名称
    """
    config = get_environment_config()
    data_source_config = get_data_source_config()
    credentials, has_credentials = get_api_credentials()
    
    logger.info("=" * 60)
    logger.info(f"🔧 {service_name} 环境配置")
    logger.info("=" * 60)
    logger.info(f"数据源类型: {data_source_config['data_source_label']}")
    logger.info(f"数据源代码: {data_source_config['data_source_type']}")
    logger.info(f"OKX环境: {config['okx_environment']}")
    logger.info(f"使用Mock: {data_source_config['use_mock']}")
    logger.info(f"使用Demo: {data_source_config['use_demo']}")
    logger.info(f"API密钥: {'完整' if has_credentials else '缺失'}")
    logger.info(f"安全状态: {'安全' if validate_safety() else '风险'}")
    logger.info(f"数据源描述: {data_source_config['description']}")
    logger.info("=" * 60)
