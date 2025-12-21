#!/usr/bin/env python3
"""
UTF-8 BOM 修复脚本
用于检测和移除 Python 文件中的 UTF-8 BOM 字符
"""

import os
import sys
import shutil
import logging
from pathlib import Path
from typing import List, Tuple

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BOMFixer:
    """BOM 修复器"""
    
    def __init__(self, project_root: str = None, create_backup: bool = True):
        """
        初始化 BOM 修复器
        
        Args:
            project_root: 项目根目录，默认为当前脚本所在目录的上级目录
            create_backup: 是否创建备份文件
        """
        if project_root is None:
            # 获取脚本所在目录的上级目录（项目根目录）
            script_dir = Path(__file__).parent
            self.project_root = script_dir.parent
        else:
            self.project_root = Path(project_root)
        
        self.create_backup = create_backup
        self.backup_dir = self.project_root / '.bom_backups'
        
        # 统计信息
        self.stats = {
            'total_files': 0,
            'bom_files': 0,
            'fixed_files': 0,
            'failed_files': 0,
            'backed_up_files': 0
        }
    
    def check_bom(self, file_path: Path) -> bool:
        """
        检查文件是否包含 UTF-8 BOM
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: True 如果包含 BOM
        """
        try:
            with open(file_path, 'rb') as f:
                content = f.read(4)
                return content.startswith(b'\xef\xbb\xbf')
        except Exception as e:
            logger.error(f"检查文件 BOM 时出错 {file_path}: {e}")
            return False
    
    def create_backup_file(self, file_path: Path) -> bool:
        """
        创建备份文件
        
        Args:
            file_path: 原文件路径
            
        Returns:
            bool: True 如果备份成功
        """
        if not self.create_backup:
            return True
        
        try:
            # 创建备份目录
            self.backup_dir.mkdir(exist_ok=True)
            
            # 计算相对路径
            relative_path = file_path.relative_to(self.project_root)
            backup_path = self.backup_dir / relative_path
            
            # 创建备份文件的父目录
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 复制文件
            shutil.copy2(file_path, backup_path)
            logger.info(f"已创建备份: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"创建备份失败 {file_path}: {e}")
            return False
    
    def remove_bom(self, file_path: Path) -> bool:
        """
        移除文件中的 UTF-8 BOM
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: True 如果移除成功
        """
        try:
            # 创建备份
            if self.create_backup:
                if not self.create_backup_file(file_path):
                    return False
                self.stats['backed_up_files'] += 1
            
            # 读取文件内容（跳过 BOM）
            with open(file_path, 'rb') as f:
                content = f.read()
            
            # 移除 BOM
            if content.startswith(b'\xef\xbb\xbf'):
                content = content[3:]
            
            # 写回文件
            with open(file_path, 'wb') as f:
                f.write(content)
            
            logger.info(f"已移除 BOM: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"移除 BOM 失败 {file_path}: {e}")
            return False
    
    def validate_python_syntax(self, file_path: Path) -> bool:
        """
        验证 Python 文件语法
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: True 如果语法正确
        """
        try:
            import ast
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 尝试解析 AST
            ast.parse(content)
            return True
            
        except SyntaxError as e:
            logger.error(f"Python 语法错误 {file_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"验证语法时出错 {file_path}: {e}")
            return False
    
    def find_python_files(self) -> List[Path]:
        """
        查找所有 Python 文件
        
        Returns:
            List[Path]: Python 文件路径列表
        """
        python_files = []
        
        for root, dirs, files in os.walk(self.project_root):
            # 跳过某些目录
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            
            for file in files:
                if file.endswith('.py'):
                    file_path = Path(root) / file
                    python_files.append(file_path)
        
        return python_files
    
    def scan_and_fix(self, dry_run: bool = False) -> Tuple[List[Path], List[Path]]:
        """
        扫描并修复 BOM 问题
        
        Args:
            dry_run: 是否只扫描不修复
            
        Returns:
            Tuple[List[Path], List[Path]]: (包含 BOM 的文件列表, 修复成功的文件列表)
        """
        python_files = self.find_python_files()
        self.stats['total_files'] = len(python_files)
        
        bom_files = []
        fixed_files = []
        
        logger.info(f"开始扫描 {len(python_files)} 个 Python 文件...")
        
        for file_path in python_files:
            if self.check_bom(file_path):
                bom_files.append(file_path)
                self.stats['bom_files'] += 1
                
                if not dry_run:
                    logger.info(f"发现 BOM 文件: {file_path}")
                    
                    # 移除 BOM
                    if self.remove_bom(file_path):
                        fixed_files.append(file_path)
                        self.stats['fixed_files'] += 1
                        
                        # 验证语法
                        if not self.validate_python_syntax(file_path):
                            logger.error(f"修复后语法验证失败: {file_path}")
                            self.stats['failed_files'] += 1
                            
                            # 尝试从备份恢复
                            if self.create_backup:
                                relative_path = file_path.relative_to(self.project_root)
                                backup_path = self.backup_dir / relative_path
                                if backup_path.exists():
                                    shutil.copy2(backup_path, file_path)
                                    logger.info(f"已从备份恢复: {file_path}")
                    else:
                        self.stats['failed_files'] += 1
        
        return bom_files, fixed_files
    
    def print_summary(self):
        """打印修复摘要"""
        print("\n" + "="*60)
        print("BOM 修复摘要")
        print("="*60)
        print(f"总文件数: {self.stats['total_files']}")
        print(f"包含 BOM 的文件数: {self.stats['bom_files']}")
        print(f"成功修复的文件数: {self.stats['fixed_files']}")
        print(f"修复失败的文件数: {self.stats['failed_files']}")
        if self.create_backup:
            print(f"备份文件数: {self.stats['backed_up_files']}")
        print("="*60)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='检测和修复 Python 文件中的 UTF-8 BOM')
    parser.add_argument('--dry-run', action='store_true', help='只扫描不修复')
    parser.add_argument('--no-backup', action='store_true', help='不创建备份文件')
    parser.add_argument('--project-root', help='项目根目录路径')
    
    args = parser.parse_args()
    
    # 创建 BOM 修复器
    fixer = BOMFixer(
        project_root=args.project_root,
        create_backup=not args.no_backup
    )
    
    logger.info(f"项目根目录: {fixer.project_root}")
    logger.info(f"创建备份: {fixer.create_backup}")
    
    if args.dry_run:
        logger.info("运行模式: 仅扫描（不修复）")
    else:
        logger.info("运行模式: 扫描并修复")
    
    # 执行扫描和修复
    bom_files, fixed_files = fixer.scan_and_fix(dry_run=args.dry_run)
    
    # 打印结果
    if bom_files:
        print(f"\n发现 {len(bom_files)} 个包含 BOM 的文件:")
        for file_path in bom_files:
            print(f"  {file_path}")
        
        if not args.dry_run:
            print(f"\n成功修复 {len(fixed_files)} 个文件:")
            for file_path in fixed_files:
                print(f"  {file_path}")
    else:
        print("\n未发现包含 BOM 的 Python 文件")
    
    # 打印摘要
    fixer.print_summary()
    
    # 返回适当的退出码
    if fixer.stats['failed_files'] > 0:
        sys.exit(1)
    elif fixer.stats['bom_files'] > 0 and args.dry_run:
        sys.exit(2)  # 发现 BOM 但未修复
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
