# debug_launch.py
import sys
import os

print("🔹 [1] 正在设置 Python 路径...")
sys.path.append(os.getcwd())

print("🔹 [2] 尝试导入 dotenv...")
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ dotenv 加载成功")
except ImportError:
    print("❌ dotenv 导入失败，请运行 pip install python-dotenv")
except Exception as e:
    print(f"❌ dotenv 加载异常: {e}")

print("🔹 [3] 尝试导入 src.utils.logger...")
try:
    from src.utils.logger import setup_logging
    print("✅ logger 模块导入成功")
except Exception as e:
    print(f"❌ logger 导入失败 (可能是路径或语法错误): {e}")

print("🔹 [4] 尝试导入 src.core.engine...")
try:
    from src.core.engine import Engine
    print("✅ Engine 类导入成功")
except ImportError as e:
    print(f"❌ Engine 导入失败: {e}")
    print("   -> 提示: 检查 src/core/engine.py 是否引用了不存在的文件")
except Exception as e:
    print(f"❌ Engine 加载异常: {e}")

print("🔹 [5] 准备启动主程序逻辑...")

import asyncio

async def main():
    print("🔹 [6] 进入 async main 函数")
    try:
        # 手动配置一个简单的日志，不依赖配置文件
        import logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - FORCE_LOG - %(message)s')
        logging.info("强制日志输出测试")

        print("🔹 [7] 实例化 Engine...")
        # 这里模拟 main.py 的逻辑，但为了防止报错，我们先传个空配置或模拟配置
        config = {
            'total_capital': 10000.0,
            'strategies': []
        }
        engine = Engine(config)
        print("✅ Engine 实例化完成")

        print("🔹 [8] 尝试启动 Engine (仅运行 3 秒测试)...")
        # 这里我们不 await run，只是看看初始化是否通过
        await engine.initialize()
        print("✅ Engine 初始化完成")

    except Exception as e:
        print(f"❌ 运行时异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(main())
        print("🔹 [9] 程序正常结束")
    except KeyboardInterrupt:
        print("🔸 用户中断")
    except Exception as e:
        print(f"❌ 致命错误: {e}")
