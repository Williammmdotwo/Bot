"""
Pytest Root Configuration

确保 src 目录在 Python 路径中，解决 ModuleNotFoundError 问题。
"""

import sys
from pathlib import Path

# 获取项目根目录
ROOT_DIR = Path(__file__).parent.absolute()

# 将 src 目录添加到 Python 路径，解决 ModuleNotFoundError
sys.path.insert(0, str(ROOT_DIR / "src"))

print(f"✅ [Test Config] Added {ROOT_DIR}/src to sys.path")
