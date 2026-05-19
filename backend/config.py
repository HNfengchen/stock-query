import os
import logging
import yaml
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stock_query.config")

_config_cache = None

def load_config(config_path: str = None) -> dict:
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config", "config.yaml"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    db_password = os.environ.get("DB_PASSWORD")
    if db_password:
        if "database" not in config:
            config["database"] = {}
        config["database"]["password"] = db_password
    else:
        if config.get("database", {}).get("password"):
            logger.warning("数据库密码使用配置文件默认值，建议设置 DB_PASSWORD 环境变量")

    _config_cache = config
    return config


def clear_config_cache():
    global _config_cache
    _config_cache = None
