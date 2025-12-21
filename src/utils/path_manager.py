"""
路径管理模块
统一处理项目中的导入路径问题
"""

import os
import sys
from pathlib import Path

def setup_project_paths():
    """设置项目路径，确保模块可以正确导入"""
    
    # 获取项目根目录
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent.parent
    
    # 添加 src 目录到 Python 路径
    src_path = project_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    
    # 添加项目根目录到 Python 路径
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    return {
        'project_root': project_root,
        'src_path': src_path,
        'config_path': project_root / "config",
        'tests_path': project_root / "tests"
    }

def get_project_paths():
    """获取项目相关路径"""
    return setup_project_paths()

# 自动设置路径
paths = setup_project_paths()

# 导出路径常量
PROJECT_ROOT = paths['project_root']
SRC_PATH = paths['src_path']
CONFIG_PATH = paths['config_path']
TESTS_PATH = paths['tests_path']
