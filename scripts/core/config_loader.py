import os
import re
import logging
import yaml

logger = logging.getLogger("stock_query")

_ENV_PATTERN = re.compile(r'\$\{([^}:]+)(?::([^}]*))?\}')

def _resolve_env_vars(value):
    if isinstance(value, str):
        def _replace(match):
            env_var = match.group(1)
            default = match.group(2) if match.group(2) is not None else ""
            return os.environ.get(env_var, default)
        return _ENV_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value

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

    _config_cache = _resolve_env_vars(_config_cache)

    return _config_cache
