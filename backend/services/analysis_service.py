import sys
import os
import json
import math
import numpy as np
from datetime import datetime
from typing import Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import yaml
from scripts.core.data_fetcher import DataFetcher
from scripts.core.analyzer import StockAnalyzer
from scripts.technical_indicators import calculate_all_indicators


def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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


def _to_list(val):
    if val is None:
        return []
    if hasattr(val, 'tolist'):
        arr = val.tolist()
        if isinstance(arr, (list, tuple)):
            return [_clean_float(x) for x in arr]
        return [_clean_float(arr)]
    if isinstance(val, (list, tuple)):
        return [_clean_float(x) for x in val]
    return [_clean_float(val)]


def build_chart_data(history_df, indicators: Dict, fund_flow: Dict = None) -> Dict:
    if history_df is None or history_df.empty:
        return {
            "kline": {"dates": [], "opens": [], "closes": [], "highs": [], "lows": [], "volumes": [],
                      "ma5": [], "ma10": [], "ma20": [], "ma60": [], "boll_upper": [], "boll_middle": [], "boll_lower": []},
            "technical": {"dates": [], "macd": [], "dif": [], "dea": [], "rsi6": [], "rsi12": [], "k": [], "d": [], "j": []},
            "fund_flow": {"dates": [], "main_flow": [], "main_flow_ratio": [], "retail_flow": []},
        }

    import pandas as pd
    df = history_df.copy()

    if "日期" in df.columns:
        dates = [str(d)[:10] for d in df["日期"]]
    else:
        dates = [str(d)[:10] for d in df.index]

    opens = _to_list(df.get("开盘", []))
    closes = _to_list(df.get("收盘", []))
    highs = _to_list(df.get("最高", []))
    lows = _to_list(df.get("最低", []))
    volumes = _to_list(df.get("成交量", []))

    ma5 = _to_list(df["收盘"].rolling(window=5).mean().fillna(0)) if "收盘" in df.columns else []
    ma10 = _to_list(df["收盘"].rolling(window=10).mean().fillna(0)) if "收盘" in df.columns else []
    ma20 = _to_list(df["收盘"].rolling(window=20).mean().fillna(0)) if "收盘" in df.columns else []
    ma60 = _to_list(df["收盘"].rolling(window=60).mean().fillna(0)) if "收盘" in df.columns else []

    boll_upper = []
    boll_middle = []
    boll_lower = []
    if "收盘" in df.columns and len(df) >= 20:
        middle = df["收盘"].rolling(window=20).mean()
        std = df["收盘"].rolling(window=20).std(ddof=0)
        boll_upper = _to_list((middle + 2 * std).fillna(0))
        boll_middle = _to_list(middle.fillna(0))
        boll_lower = _to_list((middle - 2 * std).fillna(0))

    macd_series = indicators.get("MACD", {}).get("series", {})
    rsi_series = indicators.get("RSI", {})
    kdj_series = indicators.get("KDJ", {}).get("series", {})

    macd_vals = _to_list(macd_series.get("MACD", []))
    dif_vals = _to_list(macd_series.get("DIF", []))
    dea_vals = _to_list(macd_series.get("DEA", []))
    rsi6_vals = _to_list(rsi_series.get("RSI(6)", {}).get("series", []))
    rsi12_vals = _to_list(rsi_series.get("RSI(12)", {}).get("series", []))
    k_vals = _to_list(kdj_series.get("K", []))
    d_vals = _to_list(kdj_series.get("D", []))
    j_vals = _to_list(kdj_series.get("J", []))

    ff_dates = []
    ff_main_flow = []
    ff_main_flow_ratio = []
    ff_retail_flow = []
    if fund_flow and isinstance(fund_flow, dict):
        hist = fund_flow.get("历史数据", [])
        if isinstance(hist, list):
            for item in hist:
                ff_dates.append(str(item.get("日期", ""))[:10])
                ff_main_flow.append(_clean_float(item.get("主力净流入")))
                ff_main_flow_ratio.append(_clean_float(item.get("主力净流入占比")))
                ff_retail_flow.append(_clean_float(item.get("小单净流入")))

    return {
        "kline": {
            "dates": dates, "opens": opens, "closes": closes, "highs": highs, "lows": lows, "volumes": volumes,
            "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
            "boll_upper": boll_upper, "boll_middle": boll_middle, "boll_lower": boll_lower,
        },
        "technical": {
            "dates": dates, "macd": macd_vals, "dif": dif_vals, "dea": dea_vals,
            "rsi6": rsi6_vals, "rsi12": rsi12_vals, "k": k_vals, "d": d_vals, "j": j_vals,
        },
        "fund_flow": {"dates": ff_dates, "main_flow": ff_main_flow, "main_flow_ratio": ff_main_flow_ratio, "retail_flow": ff_retail_flow},
    }


def run_analysis(stock_input: str, position_status: str, cost_price: Optional[float] = None) -> Dict:
    config = load_config()
    fetcher = DataFetcher(config)

    stock_code, stock_name, market = fetcher.resolve_stock_code(stock_input)
    info = fetcher.fetch_stock_info(stock_code)
    fund_flow = fetcher.fetch_fund_flow(stock_code)
    history_df = fetcher.fetch_history_data(stock_code, days=120)

    if history_df is None or history_df.empty:
        raise ValueError(f"无法获取 {stock_code} 的历史数据")

    indicators = calculate_all_indicators(history_df)

    analyzer = StockAnalyzer(config)
    analysis = analyzer.generate_recommendation({
        "stock_code": stock_code,
        "stock_name": stock_name,
        "market": market,
        "stock_info": info,
        "fund_flow": fund_flow,
        "history_data": history_df,
        "indicators": indicators,
    }, position_status, cost_price)

    charts = build_chart_data(history_df, indicators, fund_flow)

    trading_signal = analysis.get("trading_signal", {})
    price_prediction = analysis.get("price_prediction", {})
    position_strategy = analysis.get("position_strategy", {})
    analysis_data = analysis.get("analysis", {})

    result = {
        "stock_code": stock_code,
        "stock_name": stock_name or info.get("名称", stock_code),
        "analysis": {
            "technical_score": _clean_float(analysis_data.get("technical", {}).get("score", 0)),
            "fund_flow_score": _clean_float(analysis_data.get("fund_flow", {}).get("score", 0)),
            "sentiment_score": _clean_float(analysis_data.get("sentiment", {}).get("score", 0)),
            "overall_score": _clean_float(trading_signal.get("score", 0)),
            "recommendation": trading_signal.get("signal_text", "未知"),
            "details": _clean_nested(analysis_data),
        },
        "trading_signal": {
            "score": _clean_float(trading_signal.get("score", 0)),
            "signal": trading_signal.get("signal", "hold"),
            "signal_text": trading_signal.get("signal_text", "持有"),
        },
        "price_prediction": {
            "current": _clean_float(price_prediction.get("current")),
            "support": _clean_float(price_prediction.get("support")),
            "resistance": _clean_float(price_prediction.get("resistance")),
            "day1": {
                "target_low": _clean_float(price_prediction.get("day1", {}).get("target_low")),
                "target_high": _clean_float(price_prediction.get("day1", {}).get("target_high")),
                "trend": price_prediction.get("day1", {}).get("trend", "neutral"),
                "signal": price_prediction.get("day1", {}).get("signal", ""),
            },
            "day2": {
                "target_low": _clean_float(price_prediction.get("day2", {}).get("target_low")),
                "target_high": _clean_float(price_prediction.get("day2", {}).get("target_high")),
                "trend": price_prediction.get("day2", {}).get("trend", "neutral"),
                "signal": price_prediction.get("day2", {}).get("signal", ""),
            },
        },
        "indicators": _clean_indicators(indicators),
        "position_strategy": _clean_nested(position_strategy),
        "stock_info": {k: _clean_float(v) for k, v in info.items()},
        "charts": charts,
    }

    result = _deep_clean_nan(result)
    return result


def _deep_clean_nan(obj):
    if isinstance(obj, dict):
        return {k: _deep_clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_clean_nan(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def _clean_nested(obj):
    if isinstance(obj, dict):
        return {k: _clean_nested(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nested(v) for v in obj]
    return _clean_float(obj)


def _clean_indicators(indicators: Dict) -> Dict:
    result = {}
    for key, val in indicators.items():
        if isinstance(val, dict):
            cleaned = {}
            for k, v in val.items():
                if hasattr(v, 'tolist'):
                    cleaned[k] = _to_list(v)
                elif hasattr(v, 'item'):
                    try:
                        cleaned[k] = _clean_float(v.item())
                    except Exception:
                        cleaned[k] = _safe_item(v)
                elif isinstance(v, dict):
                    cleaned[k] = {kk: _safe_item(vv) for kk, vv in v.items()}
                elif isinstance(v, list):
                    cleaned[k] = [_safe_item(x) for x in v]
                else:
                    cleaned[k] = _clean_float(v)
            result[key] = cleaned
        else:
            result[key] = _clean_float(val)
    return result


def _safe_item(v):
    if hasattr(v, 'item'):
        try:
            return _clean_float(v.item())
        except Exception:
            pass
    if hasattr(v, 'tolist'):
        return _to_list(v)
    return _clean_float(v)
