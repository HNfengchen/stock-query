import math
import numpy as np
import pandas as pd


def clean_float(v):
    if v is None:
        return None
    # np.floating 必须在 float 之前检查，因为 np.float64 继承自 float
    # round(np.float64, 6) 返回 np.float64，而 round(float, 6) 返回 float
    if isinstance(v, (np.integer, np.floating)):
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 6)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, 6)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Series):
        return to_list(v)
    if isinstance(v, pd.DataFrame):
        return sanitize_for_json(v.to_dict(orient="list"))
    if hasattr(v, 'item'):
        try:
            f = float(v.item())
            if math.isnan(f) or math.isinf(f):
                return None
            return round(f, 6)
        except Exception:
            return str(v)
    return v


def to_list(val):
    if val is None:
        return []
    if hasattr(val, 'tolist'):
        arr = val.tolist()
        if isinstance(arr, (list, tuple)):
            return [clean_float(x) for x in arr]
        return [clean_float(arr)]
    if isinstance(val, (list, tuple)):
        return [clean_float(x) for x in val]
    return [clean_float(val)]


def sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, pd.Series):
        return sanitize_for_json(obj.tolist())
    if isinstance(obj, pd.DataFrame):
        return sanitize_for_json(obj.to_dict(orient="list"))
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    if isinstance(obj, np.ndarray):
        return sanitize_for_json(obj.tolist())
    return obj


def deep_clean_nan(obj):
    if isinstance(obj, dict):
        return {k: deep_clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_clean_nan(v) for v in obj]
    if isinstance(obj, pd.Series):
        return deep_clean_nan(obj.tolist())
    if isinstance(obj, pd.DataFrame):
        return deep_clean_nan(obj.to_dict(orient="list"))
    if isinstance(obj, (float, np.floating)) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def clean_nested(obj):
    if isinstance(obj, dict):
        return {k: clean_nested(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nested(v) for v in obj]
    if isinstance(obj, pd.Series):
        return to_list(obj)
    if isinstance(obj, pd.DataFrame):
        return sanitize_for_json(obj.to_dict(orient="list"))
    return clean_float(obj)
