#!/usr/bin/env python3
"""
临时文件和缓存清理脚本
清理开发过程中产生的临时文件和缓存
"""

import os
import shutil
import glob
import logging
from datetime import datetime
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TempFileCleaner:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
        self.cleaned_items = []
        
    def clean_python_cache(self):
        """清理Python缓存文件"""
        logger.info("开始清理Python缓存文件...")
        
        # 清理__pycache__目录
        pycache_dirs = list(self.project_root.rglob("__pycache__"))
        for pycache_dir in pycache_dirs:
            try:
                shutil.rmtree(pycache_dir)
                self.cleaned_items.append(f"删除目录: {pycache_dir}")
                logger.info(f"已删除: {pycache_dir}")
            except Exception as e:
                logger.error(f"删除失败 {pycache_dir}: {e}")
        
        # 清理.pyc文件
        pyc_files = list(self.project_root.rglob("*.pyc"))
        for pyc_file in pyc_files:
            try:
                pyc_file.unlink()
                self.cleaned_items.append(f"删除文件: {pyc_file}")
                logger.info(f"已删除: {pyc_file}")
            except Exception as e:
                logger.error(f"删除失败 {pyc_file}: {e}")
        
        # 清理.pyo文件
        pyo_files = list(self.project_root.rglob("*.pyo"))
        for pyo_file in pyo_files:
            try:
                pyo_file.unlink()
                self.cleaned_items.append(f"删除文件: {pyo_file}")
                logger.info(f"已删除: {pyo_file}")
            except Exception as e:
                logger.error(f"删除失败 {pyo_file}: {e}")
    
    def clean_frontend_cache(self):
        """清理前端构建缓存"""
        logger.info("开始清理前端构建缓存...")
        
        frontend_dir = self.project_root / "frontend"
        
        # 清理.next目录
        next_dir = frontend_dir / ".next"
        if next_dir.exists():
            try:
                shutil.rmtree(next_dir)
                self.cleaned_items.append(f"删除目录: {next_dir}")
                logger.info(f"已删除: {next_dir}")
            except Exception as e:
                logger.error(f"删除失败 {next_dir}: {e}")
        
        # 清理其他前端缓存
        cache_dirs = [
            frontend_dir / ".cache",
            frontend_dir / "node_modules" / ".cache",
        ]
        
        for cache_dir in cache_dirs:
            if cache_dir.exists():
                try:
                    shutil.rmtree(cache_dir)
                    self.cleaned_items.append(f"删除目录: {cache_dir}")
                    logger.info(f"已删除: {cache_dir}")
                except Exception as e:
                    logger.error(f"删除失败 {cache_dir}: {e}")
    
    def clean_test_logs(self, keep_latest=5):
        """清理测试日志文件，保留最新的几个"""
        logger.info(f"开始清理测试日志文件，保留最新{keep_latest}个...")
        
        logs_dir = self.project_root / "logs"
        if not logs_dir.exists():
            return
        
        log_files = list(logs_dir.glob("*.log"))
        log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        # 保留最新的几个文件
        files_to_delete = log_files[keep_latest:]
        
        for log_file in files_to_delete:
            try:
                log_file.unlink()
                self.cleaned_items.append(f"删除日志: {log_file}")
                logger.info(f"已删除: {log_file}")
            except Exception as e:
                logger.error(f"删除失败 {log_file}: {e}")
    
    def clean_temp_files(self):
        """清理临时文件"""
        logger.info("开始清理临时文件...")
        
        # 清理常见的临时文件扩展名
        temp_extensions = ["*.tmp", "*.temp", "*.bak", "*.swp", "*.swo"]
        
        for ext in temp_extensions:
            temp_files = list(self.project_root.rglob(ext))
            for temp_file in temp_files:
                try:
                    temp_file.unlink()
                    self.cleaned_items.append(f"删除临时文件: {temp_file}")
                    logger.info(f"已删除: {temp_file}")
                except Exception as e:
                    logger.error(f"删除失败 {temp_file}: {e}")
    
    def generate_report(self):
        """生成清理报告"""
        report_dir = self.project_root / "docs" / "reports"
        report_dir.mkdir(exist_ok=True)
        
        report_file = report_dir / f"temp_cleanup_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        report_content = f"""# 临时文件清理报告

**清理时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 清理统计

- 总计清理项目: {len(self.cleaned_items)}

## 清理详情

"""
        
        for item in self.cleaned_items:
            report_content += f"- {item}\n"
        
        report_content += f"""

## 清理范围

1. **Python缓存文件**
   - `__pycache__` 目录
   - `*.pyc` 文件
   - `*.pyo` 文件

2. **前端构建缓存**
   - `.next` 目录
   - `.cache` 目录

3. **测试日志文件**
   - 保留最新5个日志文件
   - 删除旧的测试日志

4. **临时文件**
   - `*.tmp` 文件
   - `*.temp` 文件
   - `*.bak` 文件
   - `*.swp` 文件
   - `*.swo` 文件

## 建议

1. 定期运行此清理脚本以保持项目整洁
2. 在提交代码前运行清理，避免提交临时文件
3. 可以将此脚本集成到CI/CD流程中

---
*此报告由临时文件清理脚本自动生成*
"""
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        logger.info(f"清理报告已生成: {report_file}")
        return report_file
    
    def run_cleanup(self):
        """执行完整的清理流程"""
        logger.info("开始执行临时文件清理...")
        
        self.clean_python_cache()
        self.clean_frontend_cache()
        self.clean_test_logs()
        self.clean_temp_files()
        
        report_file = self.generate_report()
        
        logger.info(f"清理完成! 共清理 {len(self.cleaned_items)} 个项目")
        logger.info(f"详细报告: {report_file}")
        
        return self.cleaned_items

def main():
    """主函数"""
    import sys
    
    # 获取项目根目录
    if len(sys.argv) > 1:
        project_root = sys.argv[1]
    else:
        project_root = Path(__file__).parent.parent
    
    cleaner = TempFileCleaner(project_root)
    cleaner.run_cleanup()

if __name__ == "__main__":
    main()
