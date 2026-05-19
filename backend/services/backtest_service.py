import sys
import os
import math
import re
import logging
import time
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, wait as _futures_wait

import pandas as pd
from psycopg2 import sql

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.database import get_connection
from scripts.core.backtest import _get_trend_from_change, _is_trend_consistent, _trend_direction
from scripts.core.walk_forward import WalkForwardValidator
from backend.utils import sanitize_for_json

logger = logging.getLogger("stock_query.backtest_service")

VALIDATION_TIMEOUT = 30
WALK_FORWARD_TIMEOUT = 60

_STOCK_CODE_PATTERN = re.compile(r'^\d{6}$')


class BacktestTimeoutError(Exception):
    pass


def _run_with_timeout(func, timeout_seconds, *args, **kwargs):
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(func, *args, **kwargs)
        done, not_done = _futures_wait([future], timeout=timeout_seconds)
        if not_done:
            not_done.pop().cancel()
            raise BacktestTimeoutError(f"回测操作超时（{timeout_seconds}秒）")
        return future.result()
    finally:
        executor.shutdown(wait=False)


def _validate_stock_code(stock_code: str):
    if not isinstance(stock_code, str) or not _STOCK_CODE_PATTERN.match(stock_code):
        raise ValueError(f"无效的股票代码格式: {stock_code}，必须为6位数字")


def _validate_window_params(train_window: int, test_window: int, step: int):
    if not isinstance(train_window, int) or train_window <= 0 or train_window > 500:
        raise ValueError(f"无效的训练窗口: {train_window}，必须为1-500之间的整数")
    if not isinstance(test_window, int) or test_window <= 0 or test_window > 500:
        raise ValueError(f"无效的测试窗口: {test_window}，必须为1-500之间的整数")
    if not isinstance(step, int) or step <= 0 or step > 500:
        raise ValueError(f"无效的步长: {step}，必须为1-500之间的整数")


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


def _fetch_prediction_data(stock_code: str):
    table_ident = sql.Identifier(f"stock_{stock_code}")
    conn = get_connection()
    cur = conn.cursor()
    try:
        query = sql.SQL("""
            SELECT trade_date, close, day1_pred_high, day1_pred_low,
                   day2_pred_high, day2_pred_low, change_pct
            FROM {}
            WHERE day1_pred_high IS NOT NULL OR day1_pred_low IS NOT NULL
                  OR day2_pred_high IS NOT NULL OR day2_pred_low IS NOT NULL
            ORDER BY trade_date ASC
        """).format(table_ident)
        cur.execute(query)
        rows = cur.fetchall()
        if not rows:
            raise ValueError(f"股票 {stock_code} 暂无预测数据，请先运行分析")

        query = sql.SQL("""
            SELECT trade_date, close FROM {}
            ORDER BY trade_date ASC
        """).format(table_ident)
        cur.execute(query)
        all_price_rows = cur.fetchall()
        return rows, all_price_rows
    finally:
        cur.close()
        conn.close()


def _fetch_walk_forward_data(stock_code: str):
    table_ident = sql.Identifier(f"stock_{stock_code}")
    conn = get_connection()
    cur = conn.cursor()
    try:
        query = sql.SQL("""
            SELECT trade_date, close, day1_pred_high, day1_pred_low, change_pct
            FROM {}
            WHERE day1_pred_high IS NOT NULL AND day1_pred_low IS NOT NULL
            ORDER BY trade_date ASC
        """).format(table_ident)
        cur.execute(query)
        pred_rows = cur.fetchall()
        if not pred_rows:
            raise ValueError(f"股票 {stock_code} 暂无预测数据，请先运行分析")

        query = sql.SQL("""
            SELECT trade_date, open, high, low, close
            FROM {}
            ORDER BY trade_date ASC
        """).format(table_ident)
        cur.execute(query)
        price_rows = cur.fetchall()
        return pred_rows, price_rows
    finally:
        cur.close()
        conn.close()


def run_prediction_validation(stock_code: str) -> Dict:
    _validate_stock_code(stock_code)
    logger.info(f"回测验证开始: stock_code={stock_code}")
    start_time = time.time()

    rows, all_price_rows = _run_with_timeout(_fetch_prediction_data, VALIDATION_TIMEOUT, stock_code)

    all_dates = [r[0] for r in rows]
    all_closes = {r[0]: float(r[1]) if r[1] is not None else None for r in rows}

    price_map = {}
    for r in all_price_rows:
        if r[1] is not None:
            price_map[str(r[0])] = float(r[1])

    sorted_dates = sorted(price_map.keys())
    date_index_map = {d: i for i, d in enumerate(sorted_dates)}

    predictions: List[Dict] = []
    day1_hit = 0
    day1_total = 0
    day2_hit = 0
    day2_total = 0
    day1_trend_correct = 0
    day1_trend_total = 0
    day2_trend_correct = 0
    day2_trend_total = 0
    day1_dir_correct = 0
    day1_dir_total = 0
    day2_dir_correct = 0
    day2_dir_total = 0
    day1_width_pcts = []
    day2_width_pcts = []
    day1_midpoint_mae_pcts = []
    day2_midpoint_mae_pcts = []

    for row in rows:
        trade_date = str(row[0])
        current_close = all_closes.get(row[0])
        day1_pred_high = float(row[2]) if row[2] is not None else None
        day1_pred_low = float(row[3]) if row[3] is not None else None
        day2_pred_high = float(row[4]) if row[4] is not None else None
        day2_pred_low = float(row[5]) if row[5] is not None else None
        change_pct = float(row[6]) if row[6] is not None else None

        pred_trend = _get_trend_from_change(change_pct if change_pct is not None else 0.0)

        idx = date_index_map.get(trade_date)
        if idx is None:
            continue

        actual_day1_close = None
        actual_day2_close = None
        if idx + 1 < len(sorted_dates):
            actual_day1_close = price_map.get(sorted_dates[idx + 1])
        if idx + 2 < len(sorted_dates):
            actual_day2_close = price_map.get(sorted_dates[idx + 2])

        day1_hit_flag = None
        day2_hit_flag = None
        day1_trend_flag = None
        day2_trend_flag = None
        day1_dir_flag = None
        day2_dir_flag = None

        if day1_pred_high is not None and day1_pred_low is not None and actual_day1_close is not None:
            day1_total += 1
            day1_hit_flag = day1_pred_low <= actual_day1_close <= day1_pred_high
            if day1_hit_flag:
                day1_hit += 1
            if current_close and current_close > 0:
                width_pct = (day1_pred_high - day1_pred_low) / current_close
                day1_width_pcts.append(width_pct)
                midpoint = (day1_pred_high + day1_pred_low) / 2
                day1_midpoint_mae_pcts.append(abs(actual_day1_close - midpoint) / current_close)

        if current_close and current_close > 0 and actual_day1_close is not None:
            actual_change = (actual_day1_close - current_close) / current_close * 100
            actual_trend = _get_trend_from_change(actual_change)

            day1_trend_total += 1
            day1_trend_flag = (pred_trend == actual_trend)
            if day1_trend_flag:
                day1_trend_correct += 1

            day1_dir_total += 1
            day1_dir_flag = _is_trend_consistent(pred_trend, actual_trend)
            if day1_dir_flag:
                day1_dir_correct += 1

        if day2_pred_high is not None and day2_pred_low is not None and actual_day2_close is not None:
            day2_total += 1
            day2_hit_flag = day2_pred_low <= actual_day2_close <= day2_pred_high
            if day2_hit_flag:
                day2_hit += 1
            if current_close and current_close > 0:
                width_pct = (day2_pred_high - day2_pred_low) / current_close
                day2_width_pcts.append(width_pct)
                midpoint = (day2_pred_high + day2_pred_low) / 2
                day2_midpoint_mae_pcts.append(abs(actual_day2_close - midpoint) / current_close)

        if current_close and current_close > 0 and actual_day2_close is not None:
            actual_change = (actual_day2_close - current_close) / current_close * 100
            actual_trend = _get_trend_from_change(actual_change)

            day2_trend_total += 1
            day2_trend_flag = (pred_trend == actual_trend)
            if day2_trend_flag:
                day2_trend_correct += 1

            day2_dir_total += 1
            day2_dir_flag = _is_trend_consistent(pred_trend, actual_trend)
            if day2_dir_flag:
                day2_dir_correct += 1

        predictions.append({
            "date": trade_date[:10],
            "current_price": round(_safe_float(current_close), 2) if current_close else None,
            "trend": pred_trend,
            "day1_pred_high": round(_safe_float(day1_pred_high), 2) if day1_pred_high is not None else None,
            "day1_pred_low": round(_safe_float(day1_pred_low), 2) if day1_pred_low is not None else None,
            "day2_pred_high": round(_safe_float(day2_pred_high), 2) if day2_pred_high is not None else None,
            "day2_pred_low": round(_safe_float(day2_pred_low), 2) if day2_pred_low is not None else None,
            "actual_day1": round(_safe_float(actual_day1_close), 2) if actual_day1_close else None,
            "actual_day2": round(_safe_float(actual_day2_close), 2) if actual_day2_close else None,
            "day1_hit": day1_hit_flag,
            "day2_hit": day2_hit_flag,
            "day1_trend_correct": day1_trend_flag,
            "day2_trend_correct": day2_trend_flag,
            "day1_direction_correct": day1_dir_flag,
            "day2_direction_correct": day2_dir_flag,
        })

    total = len(predictions)
    day1_hit_rate = round(day1_hit / day1_total * 100, 1) if day1_total > 0 else 0.0
    day2_hit_rate = round(day2_hit / day2_total * 100, 1) if day2_total > 0 else 0.0
    day1_trend_acc = round(day1_trend_correct / day1_trend_total * 100, 1) if day1_trend_total > 0 else 0.0
    day2_trend_acc = round(day2_trend_correct / day2_trend_total * 100, 1) if day2_trend_total > 0 else 0.0
    day1_dir_acc = round(day1_dir_correct / day1_dir_total * 100, 1) if day1_dir_total > 0 else 0.0
    day2_dir_acc = round(day2_dir_correct / day2_dir_total * 100, 1) if day2_dir_total > 0 else 0.0

    import numpy as np
    day1_mean_width = round(float(np.mean(day1_width_pcts)), 4) if day1_width_pcts else 0.0
    day1_median_width = round(float(np.median(day1_width_pcts)), 4) if day1_width_pcts else 0.0
    day1_midpoint_mae = round(float(np.mean(day1_midpoint_mae_pcts)), 4) if day1_midpoint_mae_pcts else 0.0
    day2_mean_width = round(float(np.mean(day2_width_pcts)), 4) if day2_width_pcts else 0.0
    day2_median_width = round(float(np.median(day2_width_pcts)), 4) if day2_width_pcts else 0.0
    day2_midpoint_mae = round(float(np.mean(day2_midpoint_mae_pcts)), 4) if day2_midpoint_mae_pcts else 0.0

    day1_coverage_width = round(day1_hit_rate / 100 - day1_mean_width, 4) if day1_total > 0 else 0.0
    day2_coverage_width = round(day2_hit_rate / 100 - day2_mean_width, 4) if day2_total > 0 else 0.0

    data_range = ""
    if predictions:
        data_range = f"{predictions[0]['date']} ~ {predictions[-1]['date']}"

    result = {
        "stock_code": stock_code,
        "data_range": data_range,
        "total_predictions": total,
        "day1_valid_count": day1_total,
        "day2_valid_count": day2_total,
        "statistics": {
            "day1_hit_rate": day1_hit_rate,
            "day2_hit_rate": day2_hit_rate,
            "day1_trend_accuracy": day1_trend_acc,
            "day2_trend_accuracy": day2_trend_acc,
            "day1_direction_accuracy": day1_dir_acc,
            "day2_direction_accuracy": day2_dir_acc,
            "day1_mean_width_pct": day1_mean_width,
            "day1_median_width_pct": day1_median_width,
            "day1_midpoint_mae_pct": day1_midpoint_mae,
            "day1_coverage_width_score": day1_coverage_width,
            "day2_mean_width_pct": day2_mean_width,
            "day2_median_width_pct": day2_median_width,
            "day2_midpoint_mae_pct": day2_midpoint_mae,
            "day2_coverage_width_score": day2_coverage_width,
        },
        "predictions": predictions,
    }

    elapsed = time.time() - start_time
    logger.info(f"回测验证完成: stock_code={stock_code}, 耗时={elapsed:.1f}s")
    return sanitize_for_json(result)


def run_walk_forward_validation(stock_code: str, train_window: int = 60, test_window: int = 20, step: int = 20) -> Dict:
    _validate_stock_code(stock_code)
    _validate_window_params(train_window, test_window, step)
    logger.info(f"Walk-Forward验证开始: stock_code={stock_code}, train_window={train_window}, test_window={test_window}, step={step}")
    start_time = time.time()

    pred_rows, price_rows = _run_with_timeout(_fetch_walk_forward_data, WALK_FORWARD_TIMEOUT, stock_code)

    price_map = {}
    for r in price_rows:
        if r[4] is not None:
            price_map[str(r[0])] = {
                "open": float(r[1]) if r[1] is not None else None,
                "high": float(r[2]) if r[2] is not None else None,
                "low": float(r[3]) if r[3] is not None else None,
                "close": float(r[4]),
            }

    sorted_dates = sorted(price_map.keys())
    date_index_map = {d: i for i, d in enumerate(sorted_dates)}

    pred_records = []
    for row in pred_rows:
        trade_date = str(row[0])
        current_close = float(row[1]) if row[1] is not None else None
        day1_pred_high = float(row[2]) if row[2] is not None else None
        day1_pred_low = float(row[3]) if row[3] is not None else None
        change_pct = float(row[4]) if row[4] is not None else 0.0

        pred_direction = _get_trend_from_change(change_pct)

        idx = date_index_map.get(trade_date)
        if idx is None:
            continue

        actual_day1_close = None
        if idx + 1 < len(sorted_dates):
            day1_info = price_map.get(sorted_dates[idx + 1])
            if day1_info:
                actual_day1_close = day1_info["close"]

        if day1_pred_high is None or day1_pred_low is None or actual_day1_close is None:
            continue

        pred_records.append({
            "date": trade_date[:10],
            "predicted_low": day1_pred_low,
            "predicted_high": day1_pred_high,
            "predicted_direction": pred_direction,
            "current_close": current_close,
            "close": actual_day1_close,
        })

    if not pred_records:
        raise ValueError(f"股票 {stock_code} 有效预测数据不足，无法进行Walk-Forward验证")

    predictions_df = pd.DataFrame(pred_records)

    actual_records = []
    for d, info in price_map.items():
        if info["close"] is not None:
            actual_records.append({
                "date": d[:10],
                "open": info["open"],
                "high": info["high"],
                "low": info["low"],
                "close": info["close"],
            })

    actual_df = pd.DataFrame(actual_records)

    validator = WalkForwardValidator(
        train_window=train_window,
        test_window=test_window,
        step=step,
    )
    result = validator.validate(predictions_df, actual_df)
    result["stock_code"] = stock_code
    result["train_window"] = train_window
    result["test_window"] = test_window
    result["step"] = step
    result["total_predictions"] = len(pred_records)

    elapsed = time.time() - start_time
    logger.info(f"Walk-Forward验证完成: stock_code={stock_code}, 耗时={elapsed:.1f}s")
    return sanitize_for_json(result)
