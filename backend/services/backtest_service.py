import sys
import os
import json
import tempfile
import subprocess
import math
import numpy as np
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import yaml
import pandas as pd
from scripts.core.data_fetcher import DataFetcher
from scripts.core.backtest import Backtester
from scripts.technical_indicators import calculate_all_indicators


def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_history_data(stock_code: str, days: int = 120) -> pd.DataFrame:
    config = load_config()
    fetcher = DataFetcher(config)
    return fetcher.fetch_history_data(stock_code, days)


def _clean_float(v):
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
    if hasattr(v, 'item'):
        try:
            f = float(v.item())
            if math.isnan(f) or math.isinf(f):
                return None
            return round(f, 6)
        except Exception:
            return str(v)
    return v


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def run_builtin_backtest(stock_code: str, params: Optional[Dict] = None) -> Dict:
    df = get_history_data(stock_code, days=120)
    if df is None or df.empty or len(df) < 70:
        raise ValueError(f"无法获取 {stock_code} 的足够历史数据")

    atr_multiplier = (params or {}).get("atr_multiplier", 1.5)

    backtester = Backtester(atr_multiplier=atr_multiplier, stock_code=stock_code)

    df_sorted = df.copy()
    if "日期" in df_sorted.columns:
        import pandas as pd
        df_sorted["日期"] = pd.to_datetime(df_sorted["日期"])
        df_sorted = df_sorted.sort_values("日期")
        df_sorted = df_sorted.set_index("日期")

    all_predictions = backtester.calculate_predictions(df_sorted)
    if not all_predictions:
        raise ValueError("数据量不足，无法回测")

    stats = backtester.evaluate_predictions(all_predictions)

    equity_curve = []
    equity = 1.0
    for p in all_predictions:
        current = p.get("current_price", 0)
        actual = p.get("actual_day1")
        if actual is not None and current > 0:
            ret = (actual - current) / current
            equity *= (1 + ret * 0.3)
        equity_curve.append({
            "date": str(p.get("date", ""))[:10],
            "value": round(equity, 4),
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
            "predicted_low": round(float(day1.get("low", 0)), 2),
            "predicted_high": round(float(day1.get("high", 0)), 2),
            "actual_price": round(float(actual), 2) if actual is not None else None,
            "hit": hit,
        })

    returns = [(equity_curve[i]["value"] - equity_curve[i - 1]["value"]) / equity_curve[i - 1]["value"]
               for i in range(1, len(equity_curve)) if equity_curve[i - 1]["value"] > 0]
    sharpe = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if returns and np.std(returns) > 0 else 0

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
            "day1_accuracy": round(float(stats.get("day1_hit_rate", 0)) / 100, 4),
            "day2_accuracy": round(float(stats.get("day2_hit_rate", 0)) / 100, 4),
            "day1_trend_accuracy": round(float(stats.get("day1_trend_accuracy", 0)) / 100, 4),
            "day2_trend_accuracy": round(float(stats.get("day2_trend_accuracy", 0)) / 100, 4),
            "sharpe_ratio": round(float(sharpe), 4),
            "max_drawdown": round(float(-max_dd), 4),
            "total_predictions": stats.get("total_predictions", 0),
        },
        "predictions": prediction_rows,
        "equity_curve": equity_curve,
    }

    return _sanitize(result)


def run_custom_backtest(stock_code: str, algorithm_code: str, algorithm_name: str = "custom") -> Dict:
    df = get_history_data(stock_code, days=120)
    if df is None or df.empty or len(df) < 30:
        raise ValueError(f"无法获取 {stock_code} 的足够历史数据")

    indicators = calculate_all_indicators(df)

    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w', encoding='utf-8') as f:
        json.dump({
            "dates": [str(d)[:10] for d in df.index],
            "opens": df["开盘"].tolist() if "开盘" in df.columns else [],
            "closes": df["收盘"].tolist() if "收盘" in df.columns else [],
            "highs": df["最高"].tolist() if "最高" in df.columns else [],
            "lows": df["最低"].tolist() if "最低" in df.columns else [],
            "volumes": df["成交量"].tolist() if "成交量" in df.columns else [],
        }, f)
        data_path = f.name

    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w', encoding='utf-8') as f:
        json.dump(_serialize_indicators(indicators), f)
        indicators_path = f.name

    runner_code = f'''
import json, sys
sys.path.insert(0, r"{os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))}")
with open(r"{data_path}", encoding="utf-8") as f:
    data = json.load(f)
with open(r"{indicators_path}", encoding="utf-8") as f:
    indicators = json.load(f)

import pandas as pd
df = pd.DataFrame(data)

{algorithm_code}

results = []
for i in range(30, len(df)):
    sub_df = df.iloc[:i+1]
    sub_ind = {{}}
    for k, v in indicators.items():
        if isinstance(v, dict) and "series" in v:
            sub_ind[k] = {{"latest": v.get("latest"), "signal": v.get("signal")}}
        else:
            sub_ind[k] = v
    try:
        sig = signal(sub_df, sub_ind)
    except Exception as e:
        sig = "hold"
    results.append(sig)

print(json.dumps(results))
'''

    result = subprocess.run(
        [sys.executable, "-c", runner_code],
        capture_output=True, text=True, timeout=30,
    )

    os.unlink(data_path)
    os.unlink(indicators_path)

    if result.returncode != 0:
        return {"error": result.stderr, "stock_code": stock_code}

    signals = json.loads(result.stdout)
    return _sanitize(_evaluate_signals(df, signals))


def _serialize_indicators(indicators):
    result = {}
    for key, val in indicators.items():
        if isinstance(val, dict):
            cleaned = {}
            for k, v in val.items():
                if hasattr(v, 'tolist'):
                    cleaned[k] = v.tolist()
                elif hasattr(v, 'item'):
                    cleaned[k] = v.item()
                elif isinstance(v, dict):
                    cleaned[k] = {kk: vv.item() if hasattr(vv, 'item') else vv for kk, vv in v.items()}
                else:
                    cleaned[k] = v
            result[key] = cleaned
        else:
            result[key] = val
    return result


def _evaluate_signals(df: pd.DataFrame, signals: List[str]) -> Dict:
    closes = df["收盘"].values
    predictions = []
    equity = [1.0]

    for i, sig in enumerate(signals):
        idx = i + 30
        if idx + 1 >= len(closes):
            break
        current_price = closes[idx]
        next_price = closes[idx + 1]

        predicted_range = (current_price * 0.98, current_price * 1.02)
        hit = bool(predicted_range[0] <= next_price <= predicted_range[1])
        trend = "上涨" if sig == "buy" else ("下跌" if sig == "sell" else "震荡")

        predictions.append({
            "date": str(df.index[idx])[:10] if hasattr(df.index[idx], 'strftime') else str(df.index[idx])[:10],
            "trend": trend,
            "predicted_low": round(float(predicted_range[0]), 2),
            "predicted_high": round(float(predicted_range[1]), 2),
            "actual_price": round(float(next_price), 2),
            "hit": hit,
        })

        ret = 0
        if sig == "buy":
            ret = (next_price - current_price) / current_price if current_price > 0 else 0
        elif sig == "sell":
            ret = -(next_price - current_price) / current_price if current_price > 0 else 0
        equity.append(equity[-1] * (1 + ret))

    if not predictions:
        raise ValueError("预测数据不足")

    hits = [p["hit"] for p in predictions]
    day1_acc = sum(hits) / len(hits) if hits else 0

    returns = [(equity[i] - equity[i - 1]) / equity[i - 1] for i in range(1, len(equity)) if equity[i - 1] > 0]
    sharpe = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if returns and np.std(returns) > 0 else 0

    max_dd = 0
    peak = equity[0]
    for val in equity:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    return {
        "stock_code": "",
        "statistics": {
            "day1_accuracy": round(float(day1_acc), 4),
            "day2_accuracy": round(float(day1_acc), 4),
            "day1_trend_accuracy": round(float(day1_acc), 4),
            "day2_trend_accuracy": round(float(day1_acc), 4),
            "sharpe_ratio": round(float(sharpe), 4),
            "max_drawdown": round(float(-max_dd), 4),
            "total_predictions": len(predictions),
        },
        "predictions": predictions,
        "equity_curve": [{"date": p["date"], "value": round(float(equity[i + 1]), 4)} for i, p in enumerate(predictions)],
    }
