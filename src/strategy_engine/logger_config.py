import logging
import os
from datetime import datetime

def setup_logger(name: str = "strategy_engine") -> logging.Logger:
    """
    Setup a logger for strategy_engine module with proper formatting and handlers.
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger
    
    # Create logs directory if it does not exist
    log_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # Create formatters
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler with date in filename
    log_filename = f"strategy_engine_{datetime.now().strftime("%Y%m%d")}.log"
    file_handler = logging.FileHandler(
        os.path.join(log_dir, log_filename),
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger
    
# Create default logger instance
strategy_logger = setup_logger()
