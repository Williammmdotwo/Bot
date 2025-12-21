import logging
import importlib
from typing import Dict, Any, Callable
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from .config_loader import ConfigManager

logger = logging.getLogger(__name__)


class SchedulerManager:
    """任务调度管理器"""
    
    def __init__(self, config_manager: ConfigManager):
        """初始化调度管理器"""
        self.config_manager = config_manager
        
        # 初始化 APScheduler
        self.scheduler = BackgroundScheduler(timezone='UTC')
        
        # 任务配置映射
        self.job_configs: Dict[str, Dict[str, Any]] = {}
        
        # 模块函数缓存
        self._function_cache: Dict[str, Callable] = {}
        
        logger.info("任务调度管理器初始化完成")
    
    def setup_jobs(self):
        """根据配置设置所有任务"""
        try:
            # 获取时间设置配置
            config = self.config_manager.get_config()
            time_settings = config.get('time_settings', {})
            
            if not time_settings:
                logger.warning("未找到 time_settings 配置")
                return
            
            # 清除现有任务
            self.scheduler.remove_all_jobs()
            self.job_configs.clear()
            
            # 设置每个任务
            for job_id, job_config in time_settings.items():
                self._setup_single_job(job_id, job_config)
            
            logger.info(f"任务设置完成，共设置 {len(time_settings)} 个任务")
            
        except Exception as e:
            logger.error(f"设置任务失败: {e}")
            raise
    
    def _setup_single_job(self, job_id: str, job_config: Dict[str, Any]):
        """设置单个任务"""
        try:
            # 验证任务配置
            if not self._validate_job_config(job_config):
                logger.error(f"任务 {job_id} 配置无效，跳过")
                return
            
            # 获取任务函数
            job_function = self._get_job_function(job_config)
            if not job_function:
                logger.error(f"无法加载任务 {job_id} 的函数")
                return
            
            # 保存任务配置
            self.job_configs[job_id] = job_config
            
            # 根据触发器类型添加任务
            trigger = self._create_trigger(job_config)
            if trigger:
                self.scheduler.add_job(
                    func=job_function,
                    trigger=trigger,
                    id=job_id,
                    name=job_id,
                    replace_existing=True,
                    misfire_grace_time=30  # 错过时间宽限30秒
                )
                logger.info(f"任务 {job_id} 添加成功")
            else:
                logger.error(f"任务 {job_id} 触发器创建失败")
                
        except Exception as e:
            logger.error(f"设置任务 {job_id} 失败: {e}")
    
    def _validate_job_config(self, job_config: Dict[str, Any]) -> bool:
        """验证任务配置"""
        required_fields = ['module', 'function']
        
        for field in required_fields:
            if field not in job_config:
                logger.error(f"任务配置缺少必需字段: {field}")
                return False
        
        # 检查触发器配置
        trigger_types = ['interval', 'cron', 'date']
        has_trigger = any(trigger_type in job_config for trigger_type in trigger_types)
        
        if not has_trigger:
            logger.error("任务配置缺少触发器配置 (interval, cron, date)")
            return False
        
        return True
    
    def _get_job_function(self, job_config: Dict[str, Any]) -> Callable:
        """获取任务函数"""
        try:
            module_name = job_config['module']
            function_name = job_config['function']
            
            # 创建缓存键
            cache_key = f"{module_name}.{function_name}"
            
            # 检查缓存
            if cache_key in self._function_cache:
                logger.info(f"从缓存获取任务函数: {cache_key}")
                return self._function_cache[cache_key]
            
            # 动态导入模块
            module = importlib.import_module(module_name)
            
            # 获取函数
            if not hasattr(module, function_name):
                logger.error(f"模块 {module_name} 中未找到函数 {function_name}")
                return None
            
            job_function = getattr(module, function_name)
            
            # 缓存函数
            self._function_cache[cache_key] = job_function
            
            logger.info(f"成功加载任务函数: {cache_key}")
            return job_function
            
        except ImportError as e:
            logger.error(f"导入模块失败: {e}")
            return None
        except AttributeError as e:
            logger.error(f"获取函数失败: {e}")
            return None
        except Exception as e:
            logger.error(f"加载任务函数异常: {e}")
            return None
    
    def _create_trigger(self, job_config: Dict[str, Any]):
        """创建触发器"""
        try:
            # 间隔触发器
            if 'interval' in job_config:
                interval = job_config['interval']
                if isinstance(interval, (int, float)):
                    return IntervalTrigger(seconds=interval)
                else:
                    logger.error(f"无效的间隔配置: {interval}")
                    return None
            
            # Cron 触发器
            elif 'cron' in job_config:
                cron_config = job_config['cron']
                if isinstance(cron_config, str):
                    return CronTrigger.from_crontab(cron_config)
                elif isinstance(cron_config, dict):
                    return CronTrigger(**cron_config)
                else:
                    logger.error(f"无效的 cron 配置: {cron_config}")
                    return None
            
            # 日期触发器
            elif 'date' in job_config:
                from datetime import datetime
                date_config = job_config['date']
                if isinstance(date_config, str):
                    # 解析日期字符串
                    date_obj = datetime.fromisoformat(date_config)
                    return date_obj
                elif isinstance(date_config, datetime):
                    return date_config
                else:
                    logger.error(f"无效的日期配置: {date_config}")
                    return None
            
            else:
                logger.error("任务配置缺少有效的触发器")
                return None
                
        except Exception as e:
            logger.error(f"创建触发器失败: {e}")
            return None
    
    def reload_jobs(self):
        """重新加载所有任务"""
        try:
            logger.info("开始重新加载任务...")
            
            # 安全关闭调度器
            self.scheduler.shutdown(wait=False)
            
            # 重新创建调度器
            self.scheduler = BackgroundScheduler(timezone='UTC')
            
            # 清除函数缓存
            self._function_cache.clear()
            
            # 重新设置任务
            self.setup_jobs()
            
            logger.info("任务重新加载完成")
            
        except Exception as e:
            logger.error(f"重新加载任务失败: {e}")
            raise
    
    def start(self):
        """启动调度器"""
        try:
            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("任务调度器启动成功")
                
                # 打印当前任务状态
                jobs = self.scheduler.get_jobs()
                logger.info(f"当前运行的任务: {[job.id for job in jobs]}")
            else:
                logger.warning("任务调度器已在运行")
                
        except Exception as e:
            logger.error(f"启动任务调度器失败: {e}")
            print(f"启动任务调度器失败: {e}")
            exit(1)
    
    def stop(self):
        """停止调度器"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
                logger.info("任务调度器已停止")
            else:
                logger.info("任务调度器未在运行")
                
        except Exception as e:
            logger.error(f"停止任务调度器失败: {e}")
    
    def get_job_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有任务状态"""
        try:
            jobs = self.scheduler.get_jobs()
            status = {}
            
            for job in jobs:
                status[job.id] = {
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time,
                    'trigger': str(job.trigger),
                    'pending': job.pending,
                    'running': job.running
                }
            
            return status
            
        except Exception as e:
            logger.error(f"获取任务状态失败: {e}")
            return {}
    
    def pause_job(self, job_id: str) -> bool:
        """暂停指定任务"""
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"任务 {job_id} 已暂停")
            return True
            
        except Exception as e:
            logger.error(f"暂停任务 {job_id} 失败: {e}")
            return False
    
    def resume_job(self, job_id: str) -> bool:
        """恢复指定任务"""
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"任务 {job_id} 已恢复")
            return True
            
        except Exception as e:
            logger.error(f"恢复任务 {job_id} 失败: {e}")
            return False
    
    def remove_job(self, job_id: str) -> bool:
        """移除指定任务"""
        try:
            self.scheduler.remove_job(job_id)
            if job_id in self.job_configs:
                del self.job_configs[job_id]
            logger.info(f"任务 {job_id} 已移除")
            return True
            
        except Exception as e:
            logger.error(f"移除任务 {job_id} 失败: {e}")
            return False
    
    def add_config_reload_callback(self):
        """添加配置重载回调"""
        def reload_jobs_callback():
            logger.info("检测到配置重载，重新加载调度任务...")
            self.reload_jobs()
        
        self.config_manager.add_reload_callback(reload_jobs_callback)
        logger.info("已添加配置重载回调")


# 全局调度管理器实例
_scheduler_manager = None

def get_scheduler_manager(config_manager: ConfigManager = None) -> SchedulerManager:
    """获取全局调度管理器实例"""
    global _scheduler_manager
    if _scheduler_manager is None:
        if config_manager is None:
            from .config_loader import get_config_manager
            config_manager = get_config_manager()
        _scheduler_manager = SchedulerManager(config_manager)
    return _scheduler_manager
