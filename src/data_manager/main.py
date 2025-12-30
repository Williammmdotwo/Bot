from src.data_manager.data_handler import DataHandler
from src.strategy_engine.dual_ema_strategy import DualEMAStrategy
from src.executor.interface import initialize_dependencies, health_check
from src.risk_manager.interface import health_check as risk_health_check
from src.monitoring.dashboard import get_dashboard
from src.utils.logging_config import setup_logging
from src.utils.config_loader import get_config_manager
