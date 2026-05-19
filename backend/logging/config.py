import os
import logging
from typing import Dict, Optional

from backend.logging.formatter import JsonFormatter, ConsoleFormatter
from backend.logging.handler import SizeAndTimeRotatingFileHandler


LOG_LEVELS = {
    'TRACE': logging.DEBUG - 5,
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARN': logging.WARNING,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'FATAL': logging.CRITICAL,
    'CRITICAL': logging.CRITICAL,
}

logging.addLevelName(LOG_LEVELS['TRACE'], 'TRACE')
logging.addLevelName(LOG_LEVELS['FATAL'], 'FATAL')

_DEFAULT_MODULE_LEVELS: Dict[str, str] = {
    'stock_query': 'INFO',
    'stock_query.request': 'INFO',
    'stock_query.business': 'INFO',
    'stock_query.system': 'INFO',
}

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'logs')


def setup_logging(
    service_name: str = 'stock-query',
    environment: str = None,
    log_dir: str = None,
    console_level: str = 'INFO',
    file_level: str = 'DEBUG',
    module_levels: Dict[str, str] = None,
    max_bytes: int = 100 * 1024 * 1024,
    backup_count: int = 30,
) -> None:
    if environment is None:
        environment = os.environ.get('APP_ENV', 'development')

    if log_dir is None:
        log_dir = _LOG_DIR

    os.makedirs(log_dir, exist_ok=True)

    json_formatter = JsonFormatter(service_name=service_name, environment=environment)
    console_formatter = ConsoleFormatter(service_name=service_name)

    root_logger = logging.getLogger('stock_query')
    root_logger.handlers.clear()
    root_logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(LOG_LEVELS.get(console_level.upper(), logging.INFO))
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    log_files = {
        'stock_query': os.path.join(log_dir, 'app.log'),
        'stock_query.request': os.path.join(log_dir, 'request.log'),
        'stock_query.business': os.path.join(log_dir, 'business.log'),
        'stock_query.system': os.path.join(log_dir, 'system.log'),
    }

    for logger_name, file_path in log_files.items():
        file_handler = SizeAndTimeRotatingFileHandler(
            filename=file_path,
            max_bytes=max_bytes,
            backup_count=backup_count,
        )
        file_handler.setLevel(LOG_LEVELS.get(file_level.upper(), logging.DEBUG))
        file_handler.setFormatter(json_formatter)

        module_logger = logging.getLogger(logger_name)
        module_logger.handlers.clear()
        module_logger.propagate = False
        module_logger.addHandler(file_handler)

        module_console = logging.StreamHandler()
        module_console.setLevel(LOG_LEVELS.get(console_level.upper(), logging.INFO))
        module_console.setFormatter(console_formatter)
        module_logger.addHandler(module_console)

    merged_levels = {**_DEFAULT_MODULE_LEVELS, **(module_levels or {})}
    for module_name, level_str in merged_levels.items():
        level = LOG_LEVELS.get(level_str.upper(), logging.INFO)
        mod_logger = logging.getLogger(module_name)
        mod_logger.setLevel(level)

    logging.getLogger('uvicorn').setLevel(logging.WARNING)
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)


def get_module_levels_from_env() -> Dict[str, str]:
    env_str = os.environ.get('LOG_MODULE_LEVELS', '')
    if not env_str:
        return {}
    levels = {}
    for pair in env_str.split(','):
        if '=' in pair:
            name, level = pair.split('=', 1)
            levels[name.strip()] = level.strip()
    return levels
