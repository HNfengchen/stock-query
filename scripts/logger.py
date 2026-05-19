"""日志配置模块 - backend/logging/ 的薄封装

所有 logger 归入 stock_query.* 命名空间，由 backend/logging/config.py 的 setup_logging() 统一管理 handler 和格式。
脚本独立运行时自动 fallback 到基本 ConsoleHandler。
"""

import logging
import os

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_setup_done = False


def mark_setup_done():
    """标记 setup_logging() 已被调用"""
    global _setup_done
    _setup_done = True


def get_logger(name: str) -> logging.Logger:
    """获取日志记录器，归入 stock_query.* 命名空间

    Args:
        name: 模块名称，如 "Analyzer" 或 "analyzer"，自动映射为 stock_query.analyzer
    """
    logger_name = f"stock_query.{name.lower()}"
    logger = logging.getLogger(logger_name)

    # fallback: 如果 setup_logging() 未调用且 logger 没有 handler，添加基本 ConsoleHandler
    if not _setup_done and not logger.handlers and not logging.getLogger('stock_query').handlers:
        logger.setLevel(logging.DEBUG)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


# 延迟创建的预定义 logger（保持向后兼容）
_PREDEFINED_LOGGERS = {
    "stock_logger": "StockQuery",
    "db_logger": "Database",
    "fetcher_logger": "DataFetcher",
}


def __getattr__(name):
    """模块级延迟属性，支持 from scripts.logger import db_logger 等旧写法"""
    if name in _PREDEFINED_LOGGERS:
        return get_logger(_PREDEFINED_LOGGERS[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
