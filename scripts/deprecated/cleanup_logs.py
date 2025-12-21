#!/usr/bin/env python3
"""
日志文件清理脚本
清理7天前的历史日志文件，保留最新的测试报告和关键日志
"""

import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


def extract_date_from_filename(filename):
    """
    从文件名中提取日期
    文件名格式: {testname}_{YYYYMMDD}_{HHMMSS}.{ext}
    """
    # 匹配日期格式 YYYYMMDD
    match = re.search(r'_(\d{8})_', filename)
    if match:
        date_str = match.group(1)
        try:
            return datetime.strptime(date_str, '%Y%m%d')
        except ValueError:
            return None
    return None


def should_keep_file(filename, file_date, cutoff_date):
    """
    判断是否应该保留文件
    """
    # 保留7天内的文件
    if file_date >= cutoff_date:
        return True
    
    # 保留最新的测试报告（.txt文件通常包含交易报告）
    if filename.endswith('.txt'):
        # 对于交易报告，保留最近3天的
        report_cutoff = datetime.now() - timedelta(days=3)
        return file_date >= report_cutoff
    
    return False


def cleanup_logs(logs_dir, dry_run=True):
    """
    清理日志文件
    """
    logs_path = Path(logs_dir)
    if not logs_path.exists():
        print(f"错误: 日志目录 {logs_dir} 不存在")
        return False
    
    # 计算7天前的日期
    cutoff_date = datetime.now() - timedelta(days=7)
    print(f"清理日期: {cutoff_date.strftime('%Y-%m-%d')} 之前的文件将被删除")
    print(f"保留7天内的文件和最近3天的交易报告")
    print("-" * 60)
    
    total_files = 0
    deleted_files = 0
    total_size = 0
    deleted_size = 0
    
    # 遍历所有日志文件
    for file_path in logs_path.glob('*'):
        if file_path.is_file():
            total_files += 1
            file_size = file_path.stat().st_size
            total_size += file_size
            
            # 提取文件日期
            file_date = extract_date_from_filename(file_path.name)
            
            if file_date is None:
                print(f"警告: 无法解析文件日期: {file_path.name}")
                continue
            
            # 判断是否应该删除
            if not should_keep_file(file_path.name, file_date, cutoff_date):
                print(f"将删除: {file_path.name} ({file_date.strftime('%Y-%m-%d')}, {file_size:,} bytes)")
                deleted_files += 1
                deleted_size += file_size
                
                if not dry_run:
                    try:
                        file_path.unlink()
                        print(f"已删除: {file_path.name}")
                    except Exception as e:
                        print(f"删除失败 {file_path.name}: {e}")
            else:
                print(f"保留: {file_path.name} ({file_date.strftime('%Y-%m-%d')}, {file_size:,} bytes)")
    
    print("-" * 60)
    print(f"总文件数: {total_files}")
    print(f"删除文件数: {deleted_files}")
    print(f"保留文件数: {total_files - deleted_files}")
    print(f"总大小: {total_size:,} bytes ({total_size/1024:.1f} KB)")
    print(f"删除大小: {deleted_size:,} bytes ({deleted_size/1024:.1f} KB)")
    print(f"释放空间: {deleted_size/1024:.1f} KB")
    
    if dry_run:
        print("\n这是试运行模式。使用 --execute 参数来实际删除文件。")
    
    return True


def main():
    """
    主函数
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='清理历史日志文件')
    parser.add_argument('--logs-dir', default='logs', 
                       help='日志目录路径 (默认: logs)')
    parser.add_argument('--execute', action='store_true',
                       help='实际执行删除操作 (默认为试运行)')
    
    args = parser.parse_args()
    
    # 获取脚本所在目录的上级目录作为项目根目录
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    logs_dir = project_root / args.logs_dir
    
    print(f"项目根目录: {project_root}")
    print(f"日志目录: {logs_dir}")
    print(f"执行模式: {'实际删除' if args.execute else '试运行'}")
    print()
    
    success = cleanup_logs(logs_dir, dry_run=not args.execute)
    
    if success:
        print("\n日志清理完成!")
        return 0
    else:
        print("\n日志清理失败!")
        return 1


if __name__ == '__main__':
    sys.exit(main())
