# 5. 初始化Monitoring（监控）
        if modules_config.get('monitoring', {}).get('enabled', True):
            try:
                from src.monitoring.dashboard import PerformanceDashboard, get_dashboard
                modules["monitoring"] = get_dashboard()
                modules["monitoring"].start_monitoring(interval=5)
                self.logger.info("✓ Monitoring initialized")
            except Exception as e:
                self.logger.error(f"✗ Monitoring initialization failed: {e}")
                modules["monitoring"] = None  # 不使用监控功能
