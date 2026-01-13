"""
简单的导入测试
"""
import sys
from pathlib import Path

# 手动添加 src 到路径
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

print(f"Project root: {project_root}")
print(f"Src path: {src_path}")
print(f"Sys path: {sys.path[:3]}")

try:
    from src.strategies.hft.scalper_v1 import ScalperV1
    print("✅ 导入成功: ScalperV1")
except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
