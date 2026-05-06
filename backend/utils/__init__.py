import math
import numpy as np


def clean_float(v):
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, 6)
    if isinstance(v, (np.integer, np.floating)):
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 6)
    if isinstance(v, (np.bool_,)):
        return bool(v)
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
    return obj


def deep_clean_nan(obj):
    if isinstance(obj, dict):
        return {k: deep_clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_clean_nan(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def clean_nested(obj):
    if isinstance(obj, dict):
        return {k: clean_nested(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nested(v) for v in obj]
    return clean_float(obj)
