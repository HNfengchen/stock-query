import sys
import os
import math
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.logger import get_logger

backtest_logger = get_logger("Backtest")

TREND_STRONG_UP = "strong_up"
TREND_UP = "up"
TREND_NEUTRAL = "neutral"
TREND_DOWN = "down"
TREND_STRONG_DOWN = "strong_down"

_STRONG_THRESHOLD = 0.03
_NORMAL_THRESHOLD = 0.01


def _get_trend_from_change(change_pct: float, is_ratio: bool = False) -> str:
    if isinstance(change_pct, str):
        try:
            change_pct = float(change_pct)
        except (TypeError, ValueError):
            return TREND_NEUTRAL
    if not math.isfinite(change_pct):
        return TREND_NEUTRAL
    if is_ratio:
        ratio = change_pct
    else:
        ratio = change_pct / 100.0
    if ratio > _STRONG_THRESHOLD:
        return TREND_STRONG_UP
    if ratio > _NORMAL_THRESHOLD:
        return TREND_UP
    if ratio < -_STRONG_THRESHOLD:
        return TREND_STRONG_DOWN
    if ratio < -_NORMAL_THRESHOLD:
        return TREND_DOWN
    return TREND_NEUTRAL


def _trend_direction(trend: str) -> int:
    if trend in (TREND_STRONG_UP, TREND_UP):
        return 1
    if trend in (TREND_STRONG_DOWN, TREND_DOWN):
        return -1
    return 0


def _is_trend_consistent(pred_trend: str, actual_trend: str) -> bool:
    if pred_trend == actual_trend:
        return True
    pred_dir = _trend_direction(pred_trend)
    actual_dir = _trend_direction(actual_trend)
    if pred_dir == 0 or actual_dir == 0:
        return pred_dir == actual_dir
    return pred_dir == actual_dir
