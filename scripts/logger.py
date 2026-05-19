"""
日志配置模块
"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "stock_query.log")


def get_logger(name: str) -> logging.Logger:
    """获取日志记录器"""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    file_handler = TimedRotatingFileHandler(
        LOG_FILE, when='midnight', interval=1, backupCount=30, encoding="utf-8"
    )
    file_handler.suffix = "%Y%m%d"
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


stock_logger = get_logger("StockQuery")
db_logger = get_logger("Database")
fetcher_logger = get_logger("DataFetcher")
