#!/usr/bin/env python3
"""
清理 tests 文件夹中的过时文件

功能：
- 删除过时的测试报告（.md 文件）
- 删除旧的测试脚本
- 保留必要的测试文件

使用方法：
    python scripts/cleanup_tests.py
"""

import os
import time
from datetime import datetime, timedelta
from typing import List, Dict

# ========== 配置 ==========

# 需要保留的文件（不会被删除）
KEEP_FILES = {
    '__init__.py',
    'conftest.py',           # pytest 配置文件
    'stress_test_scaling.py', # 压力测试脚本
}

# 需要删除的过时测试报告（文件名模式）
OLD_REPORTS_PATTERNS = [
    '测试覆盖率报告.md',
    '测试修复报告.md',
    'CRASH_RECOVERY_TEST_REPORT.md',
    'MICRO_LATENCY_ANALYSIS.md',
    'SCALPER_V1_TEST_REPORT.md',
]

# 需要删除的过时测试脚本（文件名模式）
OLD_TEST_PATTERNS = [
    'test_close_position_fix.py',
    'debug_entry.py',
    'test_environment_config.py',
    'test_recovery_flow.py',
    'test_scalper_v1.py',
    'test_scalper_v2_position_sizing.py',
    'test_scalper_v2_trade_replay.py',
    'test_public_gateway_depth.py',
]

# 需要保留的核心测试文件
CORE_TEST_FILES = {
    'test_order_manager.py',
    'test_position_manager.py',
    'test_position_sizer.py',
}

# 文件过期时间（天）
FILE_EXPIRE_DAYS = 30

# ========== 工具函数 ==========


def get_file_age_days(filepath: str) -> float:
    """
    获取文件年龄（天数）

    Args:
        filepath: 文件路径

    Returns:
        float: 文件年龄（天数）
    """
    file_mtime = os.path.getmtime(filepath)
    file_age = time.time() - file_mtime
    return file_age / (24 * 60 * 60)


def get_file_size_mb(filepath: str) -> float:
    """
    获取文件大小（MB）

    Args:
        filepath: 文件路径

    Returns:
        float: 文件大小（MB）
    """
    file_size = os.path.getsize(filepath)
    return file_size / (1024 * 1024)


def format_size(size_mb: float) -> str:
    """格式化文件大小"""
    if size_mb < 1:
        return f"{size_mb * 1024:.2f} KB"
    elif size_mb < 1024:
        return f"{size_mb:.2f} MB"
    else:
        return f"{size_mb / 1024:.2f} GB"


def scan_tests_directory(tests_dir: str) -> Dict[str, List[str]]:
    """
    扫描 tests 目录，分类文件

    Args:
        tests_dir: tests 目录路径

    Returns:
        Dict: 分类后的文件列表
    """
    categories = {
        'keep': [],           # 需要保留的文件
        'old_reports': [],    # 过时的测试报告
        'old_tests': [],      # 过时的测试脚本
        'expired': [],        # 过期的文件
        'unknown': []         # 未知文件
    }

    if not os.path.exists(tests_dir):
        print(f"⚠️  目录不存在: {tests_dir}")
        return categories

    for filename in os.listdir(tests_dir):
        filepath = os.path.join(tests_dir, filename)

        # 跳过目录
        if os.path.isdir(filepath):
            continue

        # 检查是否需要保留
        if filename in KEEP_FILES or filename in CORE_TEST_FILES:
            categories['keep'].append(filename)
            continue

        # 检查是否是过时的测试报告
        for pattern in OLD_REPORTS_PATTERNS:
            if pattern in filename:
                categories['old_reports'].append(filename)
                break
        else:
            # 检查是否是过时的测试脚本
            for pattern in OLD_TEST_PATTERNS:
                if pattern in filename:
                    categories['old_tests'].append(filename)
                    break
            else:
                # 检查是否过期
                age_days = get_file_age_days(filepath)
                if age_days > FILE_EXPIRE_DAYS:
                    categories['expired'].append(filename)
                else:
                    categories['unknown'].append(filename)

    return categories


def delete_files(filepaths: List[str], dry_run: bool = True) -> Dict[str, float]:
    """
    删除文件

    Args:
        filepaths: 文件路径列表
        dry_run: 是否只模拟（不实际删除）

    Returns:
        Dict: 删除统计 {count, total_size_mb}
    """
    stats = {
        'count': 0,
        'total_size_mb': 0.0
    }

    for filepath in filepaths:
        if not os.path.exists(filepath):
            continue

        file_size_mb = get_file_size_mb(filepath)
        stats['total_size_mb'] += file_size_mb
        stats['count'] += 1

        if dry_run:
            print(f"  📝 [模拟删除] {os.path.basename(filepath)} ({format_size(file_size_mb)})")
        else:
            try:
                os.remove(filepath)
                print(f"  ✅ [已删除] {os.path.basename(filepath)} ({format_size(file_size_mb)})")
            except Exception as e:
                print(f"  ❌ [删除失败] {os.path.basename(filepath)}: {e}")

    return stats


def main():
    """主函数"""
    import sys

    # 获取项目根目录
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    tests_dir = os.path.join(project_root, 'tests')

    print("=" * 80)
    print("🧹 Tests 文件夹清理工具")
    print("=" * 80)
    print()
    print(f"📁 扫描目录: {tests_dir}")
    print()

    # 扫描文件
    categories = scan_tests_directory(tests_dir)

    # 显示扫描结果
    print("📊 扫描结果:")
    print()

    total_size_mb = 0.0

    if categories['keep']:
        print("✅ 需要保留的文件:")
        for filename in categories['keep']:
            filepath = os.path.join(tests_dir, filename)
            size_mb = get_file_size_mb(filepath)
            total_size_mb += size_mb
            print(f"  📄 {filename} ({format_size(size_mb)})")
        print()

    if categories['old_reports']:
        print("🗑️  过时的测试报告（建议删除）:")
        for filename in categories['old_reports']:
            filepath = os.path.join(tests_dir, filename)
            size_mb = get_file_size_mb(filepath)
            total_size_mb += size_mb
            print(f"  📄 {filename} ({format_size(size_mb)})")
        print()

    if categories['old_tests']:
        print("🗑️  过时的测试脚本（建议删除）:")
        for filename in categories['old_tests']:
            filepath = os.path.join(tests_dir, filename)
            size_mb = get_file_size_mb(filepath)
            total_size_mb += size_mb
            print(f"  📄 {filename} ({format_size(size_mb)})")
        print()

    if categories['expired']:
        print("🗑️  过期的文件（超过 30 天未修改）:")
        for filename in categories['expired']:
            filepath = os.path.join(tests_dir, filename)
            size_mb = get_file_size_mb(filepath)
            age_days = get_file_age_days(filepath)
            total_size_mb += size_mb
            print(f"  📄 {filename} ({format_size(size_mb)}, {age_days:.1f} 天前)")
        print()

    if categories['unknown']:
        print("❓ 未知文件（建议手动检查）:")
        for filename in categories['unknown']:
            filepath = os.path.join(tests_dir, filename)
            size_mb = get_file_size_mb(filepath)
            total_size_mb += size_mb
            print(f"  📄 {filename} ({format_size(size_mb)})")
        print()

    # 汇总
    print("=" * 80)
    print("📊 文件统计:")
    print()
    print(f"  需要保留: {len(categories['keep'])} 个文件")
    print(f"  过时报告: {len(categories['old_reports'])} 个文件")
    print(f"  过时测试: {len(categories['old_tests'])} 个文件")
    print(f"  过期文件: {len(categories['expired'])} 个文件")
    print(f"  未知文件: {len(categories['unknown'])} 个文件")
    print(f"  总大小: {format_size(total_size_mb)}")
    print()

    # 计算可释放的空间
    files_to_delete = []
    files_to_delete.extend([os.path.join(tests_dir, f) for f in categories['old_reports']])
    files_to_delete.extend([os.path.join(tests_dir, f) for f in categories['old_tests']])
    files_to_delete.extend([os.path.join(tests_dir, f) for f in categories['expired']])

    if files_to_delete:
        delete_size_mb = sum(get_file_size_mb(f) for f in files_to_delete)
        print(f"💾 可释放空间: {format_size(delete_size_mb)}")
        print()

        # 询问是否删除
        dry_run = '--dry-run' in sys.argv or '-d' in sys.argv

        if dry_run:
            print("🔍 [模拟模式] 不会实际删除文件，只显示将要删除的内容")
        else:
            print("⚠️  [警告] 即将删除以上文件，确认继续？(y/N): ", end='')
            confirm = input().strip().lower()
            if confirm != 'y':
                print("❌ 取消删除")
                return

        print()

        # 删除过时报告
        print("🗑️  删除过时的测试报告:")
        old_reports_paths = [os.path.join(tests_dir, f) for f in categories['old_reports']]
        delete_files(old_reports_paths, dry_run=dry_run)
        print()

        # 删除过时测试
        print("🗑️  删除过时的测试脚本:")
        old_tests_paths = [os.path.join(tests_dir, f) for f in categories['old_tests']]
        delete_files(old_tests_paths, dry_run=dry_run)
        print()

        # 删除过期文件
        print("🗑️  删除过期的文件:")
        expired_paths = [os.path.join(tests_dir, f) for f in categories['expired']]
        delete_files(expired_paths, dry_run=dry_run)
        print()

        if not dry_run:
            print("=" * 80)
            print("✅ 清理完成！")
            print(f"💾 已释放空间: {format_size(delete_size_mb)}")
            print("=" * 80)
    else:
        print("✅ 没有需要清理的文件")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ 用户中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}", exc_info=True)
