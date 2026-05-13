import sys
import os
import json
import math
import numpy as np
from typing import Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
from scripts.core.backtest import Backtester
from scripts.technical_indicators import calculate_all_indicators
from backend.utils import sanitize_for_json
from backend.services.analysis_service import get_fetcher


def _get_config():
    import yaml
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_history_data(stock_code: str, days: int = 120) -> pd.DataFrame:
    fetcher = get_fetcher()
    return fetcher.fetch_history_data(stock_code, days)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        numeric = float(value)
        if not math.isfinite(numeric):
            return default
        return numeric
    except (TypeError, ValueError):
        return default


def _parse_lookback_days(value) -> int:
    if value is None:
        return 60
    if isinstance(value, bool):
        raise ValueError("回看天数必须是整数")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise ValueError("回看天数必须是整数")
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
        raise ValueError("回看天数必须是整数")
    raise ValueError("回看天数必须是整数")


def run_builtin_backtest(stock_code: str, params: Optional[Dict] = None) -> Dict:
    params = params or {}

    stock_name = ""
    try:
        fetcher = get_fetcher()
        _, stock_name, _ = fetcher.resolve_stock_code(stock_code)
    except Exception:
        pass

    try:
        atr_multiplier = float(params.get("atr_multiplier", 1.5))
    except (TypeError, ValueError):
        raise ValueError("ATR乘数必须是有效数字")

    lookback_days = _parse_lookback_days(params.get("lookback_days", 60))

    if not 30 <= lookback_days <= 252:
        raise ValueError("回看天数必须在 30 到 252 之间")

    history_days = max(120, lookback_days + 10)
    df = get_history_data(stock_code, days=history_days)
    minimum_rows = lookback_days + 10
    if df is None or df.empty or len(df) < minimum_rows:
        raise ValueError(f"无法获取 {stock_code} 的足够历史数据")

    backtester = Backtester(atr_multiplier=atr_multiplier, stock_code=stock_code, stock_name=stock_name, config=_get_config())

    df_sorted = df.copy()
    if "日期" in df_sorted.columns:
        df_sorted["日期"] = pd.to_datetime(df_sorted["日期"])
        df_sorted = df_sorted.sort_values("日期")
        df_sorted = df_sorted.set_index("日期")
    elif df_sorted.index.name == "日期" or hasattr(df_sorted.index, "dtype"):
        df_sorted = df_sorted.sort_index()

    all_predictions = backtester.calculate_predictions(
        df_sorted, lookback_days=lookback_days
    )
    if not all_predictions:
        raise ValueError("数据量不足，无法回测")

    stats = backtester.evaluate_predictions(all_predictions)
    if not isinstance(stats, dict):
        stats = {}

    equity_curve = []
    equity = 1.0
    position_size = 0.3
    commission_rate = 0.00025
    stamp_duty_rate = 0.0005
    slippage = 0.001
    # 当前使用简化总成本率，后续可按买卖方向拆分手续费和印花税。
    total_cost_rate = commission_rate + stamp_duty_rate + slippage
    previous_position = 0.0
    daily_returns = []
    total_turnover = 0.0
    total_cost = 0.0
    trades = 0
    profitable_day_count = 0

    for p in all_predictions:
        current = _safe_float(p.get("current_price"))
        actual_value = p.get("actual_day1")
        actual = _safe_float(actual_value) if actual_value is not None else None
        trend = p.get("trend", "neutral")
        if trend in ("strong_up",):
            target_position = position_size * 1.0
        elif trend in ("up",):
            target_position = position_size * 0.7
        elif trend in ("strong_down", "down"):
            target_position = 0.0
        else:
            target_position = position_size * 0.3
        turnover = abs(target_position - previous_position)
        cost = turnover * total_cost_rate
        price_return = 0.0

        if actual is not None and current > 0:
            price_return = (actual - current) / current

        daily_return = target_position * price_return - cost
        equity *= (1 + daily_return)
        previous_position = target_position
        daily_returns.append(daily_return)
        total_turnover += turnover
        total_cost += cost
        if turnover > 0:
            trades += 1
        if daily_return > 0:
            profitable_day_count += 1

        equity_curve.append({
            "date": str(p.get("date", ""))[:10],
            "value": round(equity, 4),
            "position": round(float(target_position), 4),
            "daily_return": round(float(daily_return), 4),
            "turnover": round(float(turnover), 4),
            "cost": round(float(cost), 4),
        })

    prediction_rows = []
    for p in all_predictions:
        day1 = p.get("day1", {})
        actual = p.get("actual_day1")
        current = p.get("current_price", 0)
        trend = p.get("trend", "neutral")
        hit = False
        if actual is not None and day1.get("low") is not None and day1.get("high") is not None:
            hit = day1["low"] <= actual <= day1["high"]
        prediction_rows.append({
            "date": str(p.get("date", ""))[:10],
            "trend": trend,
            "predicted_low": round(_safe_float(day1.get("low")), 2),
            "predicted_high": round(_safe_float(day1.get("high")), 2),
            "actual_price": round(_safe_float(actual), 2) if actual is not None else None,
            "current_price": round(_safe_float(current), 2) if current is not None else None,
            "hit": hit,
        })

    sharpe = (np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)) if daily_returns and np.std(daily_returns) > 0 else 0

    max_dd = 0
    peak = 1.0
    for ec in equity_curve:
        val = ec["value"]
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    result = {
        "stock_code": stock_code,
        "statistics": {
            "day1_accuracy": round(_safe_float(stats.get("day1_hit_rate")) / 100, 4),
            "day2_accuracy": round(_safe_float(stats.get("day2_hit_rate")) / 100, 4),
            "day1_trend_accuracy": round(_safe_float(stats.get("day1_trend_accuracy")) / 100, 4),
            "day2_trend_accuracy": round(_safe_float(stats.get("day2_trend_accuracy")) / 100, 4),
            "sharpe_ratio": round(float(sharpe), 4),
            "max_drawdown": round(float(-max_dd), 4),
            "total_predictions": int(_safe_float(stats.get("total_predictions"))),
            "mean_width_pct": round(_safe_float(stats.get("mean_width_pct")), 4),
            "median_width_pct": round(_safe_float(stats.get("median_width_pct")), 4),
            "midpoint_mae_pct": round(_safe_float(stats.get("midpoint_mae_pct")), 4),
            "coverage_width_score": round(_safe_float(stats.get("coverage_width_score")), 4),
            "total_return": round(float(equity - 1), 4),
            "total_cost": round(float(total_cost), 4),
            "turnover": round(float(total_turnover), 4),
            "trades": trades,
            # win_rate 表示正收益预测日占比，不是闭合交易胜率。
            "win_rate": round(float(profitable_day_count / len(daily_returns)), 4) if daily_returns else 0,
        },
        "predictions": prediction_rows,
        "equity_curve": equity_curve,
        "effective_params": {
            "atr_multiplier": atr_multiplier,
            "lookback_days": lookback_days,
        },
    }

    return sanitize_for_json(result)


DANGEROUS_PATTERNS = [
    '__import__', 'import os', 'import sys', 'import subprocess',
    'import shutil', 'import socket', 'import http', 'import urllib',
    'import requests', 'import pathlib', 'import ctypes', 'import pickle',
    'exec(', 'eval(', 'compile(', 'open(', '__builtins__',
    'os.system', 'os.popen', 'os.exec', 'os.spawn', 'os.remove',
    'os.unlink', 'os.rmdir', 'os.makedirs', 'os.rename',
    'subprocess.', 'shutil.', 'socket.', 'http.',
]


def _validate_algorithm_code(code: str):
    for pattern in DANGEROUS_PATTERNS:
        if pattern in code:
            raise ValueError(f"算法代码包含不允许的操作: {pattern}")


def run_custom_backtest(stock_code: str, algorithm_code: str, algorithm_name: str = "custom") -> Dict:
    _validate_algorithm_code(algorithm_code)

    df = get_history_data(stock_code, days=120)
    if df is None or df.empty or len(df) < 30:
        raise ValueError(f"无法获取 {stock_code} 的足够历史数据")

    indicators = calculate_all_indicators(df)

    data_dict = {
        "dates": [str(d)[:10] for d in df.index],
        "opens": _safe_list(df, "开盘"),
        "closes": _safe_list(df, "收盘"),
        "highs": _safe_list(df, "最高"),
        "lows": _safe_list(df, "最低"),
        "volumes": _safe_list(df, "成交量"),
    }
    indicators_dict = _serialize_indicators(indicators)

    safe_builtins = {}
    for name in ['print', 'len', 'range', 'int', 'float', 'str', 'bool',
                 'list', 'dict', 'tuple', 'set', 'abs', 'max', 'min', 'sum',
                 'round', 'sorted', 'enumerate', 'zip', 'map', 'filter',
                 'True', 'False', 'None', 'isinstance', 'type', 'hasattr']:
        safe_builtins[name] = __builtins__[name] if isinstance(__builtins__, dict) else getattr(__builtins__, name)

    local_ns = {
        '__builtins__': safe_builtins,
        'pd': pd,
        'np': np,
        'json': json,
        'math': math,
        'data': data_dict,
        'indicators': indicators_dict,
    }

    try:
        exec(algorithm_code, local_ns)
    except Exception as e:
        raise ValueError(f"算法代码执行错误: {e}")

    if 'signal' not in local_ns or not callable(local_ns['signal']):
        raise ValueError("算法代码必须定义 signal(df, indicators) 函数")

    signal_func = local_ns['signal']
    test_df = pd.DataFrame(data_dict)
    try:
        test_result = signal_func(test_df, indicators_dict)
        if test_result not in ('buy', 'sell', 'hold'):
            raise ValueError("signal函数必须返回 'buy', 'sell' 或 'hold'")
    except ValueError:
        raise
    except Exception:
        pass

    signals = []
    for i in range(30, len(test_df)):
        sub_df = test_df.iloc[:i+1]
        sub_ind = {}
        for k, v in indicators_dict.items():
            if isinstance(v, dict) and "series" in v:
                sub_ind[k] = {"latest": v.get("latest"), "signal": v.get("signal")}
            else:
                sub_ind[k] = v
        try:
            sig = signal_func(sub_df, sub_ind)
            if sig not in ('buy', 'sell', 'hold'):
                sig = 'hold'
        except Exception:
            sig = 'hold'
        signals.append(sig)

    return sanitize_for_json(_evaluate_signals(df, signals))


def _safe_list(df, col):
    if col in df.columns:
        vals = df[col].tolist()
        return [float(v) if hasattr(v, 'item') else v for v in vals]
    return []


def _serialize_indicators(indicators):
    result = {}
    for key, val in indicators.items():
        if isinstance(val, dict):
            cleaned = {}
            for k, v in val.items():
                if hasattr(v, 'tolist'):
                    cleaned[k] = v.tolist()
                elif hasattr(v, 'item'):
                    try:
                        cleaned[k] = v.item()
                    except Exception:
                        cleaned[k] = str(v)
                elif isinstance(v, dict):
                    cleaned[k] = {kk: _safe_item(vv) for kk, vv in v.items()}
                elif isinstance(v, list):
                    cleaned[k] = [_safe_item(x) for x in v]
                else:
                    cleaned[k] = v
            result[key] = cleaned
        else:
            result[key] = val
    return result


def _safe_item(v):
    if hasattr(v, 'item'):
        try:
            return v.item()
        except Exception:
            pass
    if hasattr(v, 'tolist'):
        return v.tolist()
    return v


def _evaluate_signals(df, signals):
    if "收盘" not in df.columns or len(signals) == 0:
        return {"error": "无法评估信号", "stock_code": ""}

    closes = df["收盘"].values
    equity = 1.0
    position = 0
    entry_price = 0
    equity_curve = []
    commission_rate = 0.00025
    stamp_duty_rate = 0.0005
    slippage = 0.001
    total_cost_rate = commission_rate + stamp_duty_rate + slippage

    for i, signal in enumerate(signals):
        idx = i + 30
        if idx >= len(closes):
            break

        price = float(closes[idx])

        if signal == "buy" and position == 0:
            position = 1
            entry_price = price * (1 + slippage)
        elif signal == "sell" and position == 1:
            sell_price = price * (1 - slippage)
            profit = (sell_price - entry_price) / entry_price
            cost = profit * total_cost_rate
            equity *= (1 + profit - cost)
            position = 0
            entry_price = 0

        equity_curve.append({"date": str(df.index[idx])[:10], "value": round(equity, 4)})

    if position == 1 and len(closes) > 30:
        last_price = float(closes[-1])
        profit = (last_price - entry_price) / entry_price
        equity *= (1 + profit)

    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i - 1]["value"] > 0:
            r = (equity_curve[i]["value"] - equity_curve[i - 1]["value"]) / equity_curve[i - 1]["value"]
            returns.append(r)

    sharpe = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if returns and np.std(returns) > 0 else 0

    max_dd = 0
    peak = 1.0
    for ec in equity_curve:
        if ec["value"] > peak:
            peak = ec["value"]
        dd = (peak - ec["value"]) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    return {
        "stock_code": "",
        "statistics": {
            "day1_accuracy": 0,
            "day2_accuracy": 0,
            "sharpe_ratio": round(float(sharpe), 4),
            "max_drawdown": round(float(-max_dd), 4),
            "total_predictions": len(signals),
        },
        "predictions": [],
        "equity_curve": equity_curve,
    }
