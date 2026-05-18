import os
import logging
import yaml

logger = logging.getLogger("stock_query")

_PROJECT_ROOT = None

def get_project_root():
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return _PROJECT_ROOT

def get_config_path():
    return os.path.join(get_project_root(), "config", "config.yaml")

_config_cache = None

def load_config(force_reload=False):
    global _config_cache
    if _config_cache is not None and not force_reload:
        return _config_cache
    config_path = get_config_path()
    if os.path.exists(config_path):
        with open(config_path) as f:
            _config_cache = yaml.safe_load(f) or {}
    else:
        _config_cache = {}

    db_password = os.environ.get("DB_PASSWORD")
    if db_password:
        if "database" not in _config_cache:
            _config_cache["database"] = {}
        _config_cache["database"]["password"] = db_password
    else:
        if _config_cache.get("database", {}).get("password"):
            logger.warning("数据库密码使用配置文件默认值，建议设置 DB_PASSWORD 环境变量")

    return _config_cache
