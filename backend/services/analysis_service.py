import sys
import os
import json
import math
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional
from functools import lru_cache

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import yaml
from scripts.core.data_fetcher import DataFetcher
from scripts.core.analyzer import StockAnalyzer
from scripts.technical_indicators import calculate_all_indicators
from backend.utils import clean_float, to_list, sanitize_for_json, deep_clean_nan, clean_nested

_config_cache = None
_fetcher_cache = None
_analyzer_cache = None
_result_cache = {}


def load_config():
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f)
    return _config_cache


def get_fetcher():
    global _fetcher_cache
    if _fetcher_cache is None:
        _fetcher_cache = DataFetcher(load_config())
    return _fetcher_cache


def get_analyzer():
    global _analyzer_cache
    if _analyzer_cache is None:
        _analyzer_cache = StockAnalyzer(load_config())
    return _analyzer_cache


def build_chart_data(history_df, indicators: Dict, fund_flow: Dict = None) -> Dict:
    if history_df is None or history_df.empty:
        return {
            "kline": {"dates": [], "opens": [], "closes": [], "highs": [], "lows": [], "volumes": [],
                      "ma5": [], "ma10": [], "ma20": [], "ma60": [], "boll_upper": [], "boll_middle": [], "boll_lower": []},
            "technical": {"dates": [], "macd": [], "dif": [], "dea": [], "rsi6": [], "rsi12": [], "k": [], "d": [], "j": []},
            "fund_flow": {"dates": [], "main_flow": [], "main_flow_ratio": [], "small_flow": [], "change_pct": []},
        }

    import pandas as pd
    df = history_df.copy()

    if "日期" in df.columns:
        dates = [str(d)[:10] for d in df["日期"]]
    else:
        dates = [str(d)[:10] for d in df.index]

    opens = to_list(df.get("开盘", []))
    closes = to_list(df.get("收盘", []))
    highs = to_list(df.get("最高", []))
    lows = to_list(df.get("最低", []))
    volumes = to_list(df.get("成交量", []))

    ma_data = indicators.get("MA", {})
    ma5 = to_list(ma_data.get("MA5", {}).get("series", [])) if isinstance(ma_data.get("MA5"), dict) else []
    ma10 = to_list(ma_data.get("MA10", {}).get("series", [])) if isinstance(ma_data.get("MA10"), dict) else []
    ma20 = to_list(ma_data.get("MA20", {}).get("series", [])) if isinstance(ma_data.get("MA20"), dict) else []
    ma60 = to_list(ma_data.get("MA60", {}).get("series", [])) if isinstance(ma_data.get("MA60"), dict) else []

    if not ma5 and "收盘" in df.columns:
        ma5 = to_list(df["收盘"].rolling(window=5).mean().fillna(0))
    if not ma10 and "收盘" in df.columns:
        ma10 = to_list(df["收盘"].rolling(window=10).mean().fillna(0))
    if not ma20 and "收盘" in df.columns:
        ma20 = to_list(df["收盘"].rolling(window=20).mean().fillna(0))
    if not ma60 and "收盘" in df.columns:
        ma60 = to_list(df["收盘"].rolling(window=60).mean().fillna(0))

    boll_data = indicators.get("BOLL", {}).get("series", {})
    boll_upper = to_list(boll_data.get("upper", [])) if isinstance(boll_data, dict) else []
    boll_middle = to_list(boll_data.get("middle", [])) if isinstance(boll_data, dict) else []
    boll_lower = to_list(boll_data.get("lower", [])) if isinstance(boll_data, dict) else []

    if not boll_upper and "收盘" in df.columns and len(df) >= 20:
        middle = df["收盘"].rolling(window=20).mean()
        std = df["收盘"].rolling(window=20).std(ddof=1)
        boll_upper = to_list((middle + 2 * std).fillna(0))
        boll_middle = to_list(middle.fillna(0))
        boll_lower = to_list((middle - 2 * std).fillna(0))

    macd_series = indicators.get("MACD", {}).get("series", {})
    rsi_series = indicators.get("RSI", {})
    kdj_series = indicators.get("KDJ", {}).get("series", {})

    macd_vals = to_list(macd_series.get("MACD", []))
    dif_vals = to_list(macd_series.get("DIF", []))
    dea_vals = to_list(macd_series.get("DEA", []))
    rsi6_vals = to_list(rsi_series.get("RSI(6)", {}).get("series", []))
    rsi12_vals = to_list(rsi_series.get("RSI(12)", {}).get("series", []))
    k_vals = to_list(kdj_series.get("K", []))
    d_vals = to_list(kdj_series.get("D", []))
    j_vals = to_list(kdj_series.get("J", []))

    ff_dates = []
    ff_main_flow = []
    ff_main_flow_ratio = []
    ff_small_flow = []
    ff_change_pct = []
    if fund_flow and isinstance(fund_flow, dict):
        hist = fund_flow.get("历史数据", [])
        if isinstance(hist, list):
            for item in hist:
                ff_dates.append(str(item.get("日期", ""))[:10])
                ff_main_flow.append(clean_float(item.get("主力净流入")))
                ff_main_flow_ratio.append(clean_float(item.get("主力净流入占比")))
                ff_small_flow.append(clean_float(item.get("小单净流入", 0)))
                ff_change_pct.append(clean_float(item.get("涨跌幅", 0)))

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
        "fund_flow": {"dates": ff_dates, "main_flow": ff_main_flow, "main_flow_ratio": ff_main_flow_ratio, "small_flow": ff_small_flow, "change_pct": ff_change_pct},
    }


def run_analysis(stock_input: str, position_status: str, cost_price: Optional[float] = None) -> Dict:
    cache_key = (stock_input, position_status, cost_price)
    now = datetime.now()
    if cache_key in _result_cache:
        cached_result, cached_time = _result_cache[cache_key]
        if (now - cached_time).total_seconds() < 300:
            return cached_result

    fetcher = get_fetcher()
    analyzer = get_analyzer()

    stock_code, stock_name, market = fetcher.resolve_stock_code(stock_input)
    info = fetcher.fetch_stock_info(stock_code)
    fund_flow = fetcher.fetch_fund_flow(stock_code)
    history_df = fetcher.fetch_history_data(stock_code, days=120)

    if history_df is None or history_df.empty:
        raise ValueError(f"无法获取 {stock_code} 的历史数据")

    indicators = calculate_all_indicators(history_df)

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
    validation = analysis.get("validation", {})

    result = {
        "stock_code": stock_code,
        "stock_name": stock_name or info.get("名称", stock_code),
        "analysis": {
            "technical_score": clean_float(analysis_data.get("technical", {}).get("score", 0)),
            "fund_flow_score": clean_float(analysis_data.get("fund_flow", {}).get("score", 0)),
            "sentiment_score": clean_float(analysis_data.get("sentiment", {}).get("score", 0)),
            "overall_score": clean_float(trading_signal.get("score", 0)),
            "recommendation": trading_signal.get("signal_text", "未知"),
            "details": clean_nested(analysis_data),
        },
        "trading_signal": {
            "score": clean_float(trading_signal.get("score", 0)),
            "signal": trading_signal.get("signal", "hold"),
            "signal_text": trading_signal.get("signal_text", "持有"),
            "reason": trading_signal.get("reason", ""),
        },
        "price_prediction": {
            "current": clean_float(price_prediction.get("current")),
            "support": clean_float(price_prediction.get("support")),
            "resistance": clean_float(price_prediction.get("resistance")),
            "validation_confidence": clean_float(price_prediction.get("validation_confidence")),
            "validation_note": price_prediction.get("validation_note", ""),
            "day1": {
                "target_low": clean_float(price_prediction.get("day1", {}).get("target_low")),
                "target_high": clean_float(price_prediction.get("day1", {}).get("target_high")),
                "trend": price_prediction.get("day1", {}).get("trend", "neutral"),
                "signal": price_prediction.get("day1", {}).get("signal", ""),
            },
            "day2": {
                "target_low": clean_float(price_prediction.get("day2", {}).get("target_low")),
                "target_high": clean_float(price_prediction.get("day2", {}).get("target_high")),
                "trend": price_prediction.get("day2", {}).get("trend", "neutral"),
                "signal": price_prediction.get("day2", {}).get("signal", ""),
            },
        },
        "indicators": _clean_indicators(indicators),
        "position_strategy": clean_nested(position_strategy),
        "validation": clean_nested(validation),
        "stock_info": {k: clean_float(v) for k, v in info.items()},
        "charts": charts,
    }

    result = deep_clean_nan(result)
    _result_cache[cache_key] = (result, now)
    _cleanup_cache()

    try:
        from backend.services.history_service import update_signal_cache
        update_signal_cache(stock_code, position_status, result.get("trading_signal", {}))
    except Exception:
        pass

    return result


def _cleanup_cache():
    now = datetime.now()
    expired = [k for k, (_, t) in _result_cache.items() if (now - t).total_seconds() > 300]
    for k in expired:
        del _result_cache[k]


def _clean_indicators(indicators: Dict) -> Dict:
    result = {}
    for key, val in indicators.items():
        if isinstance(val, dict):
            cleaned = {}
            for k, v in val.items():
                if hasattr(v, 'tolist'):
                    cleaned[k] = to_list(v)
                elif hasattr(v, 'item'):
                    try:
                        cleaned[k] = clean_float(v.item())
                    except Exception:
                        cleaned[k] = _safe_item(v)
                elif isinstance(v, dict):
                    cleaned[k] = {kk: _safe_item(vv) for kk, vv in v.items()}
                elif isinstance(v, list):
                    cleaned[k] = [_safe_item(x) for x in v]
                else:
                    cleaned[k] = clean_float(v)
            result[key] = cleaned
        else:
            result[key] = clean_float(val)
    return result


def _safe_item(v):
    if hasattr(v, 'item'):
        try:
            return clean_float(v.item())
        except Exception:
            pass
    if hasattr(v, 'tolist'):
        return to_list(v)
    return clean_float(v)
