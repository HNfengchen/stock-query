import math
import numpy as np
import pandas as pd
from typing import Dict, List

from scripts.core.backtest import _get_trend_from_change, _is_trend_consistent, _trend_direction

TREND_STRONG_UP = "strong_up"
TREND_UP = "up"
TREND_NEUTRAL = "neutral"
TREND_DOWN = "down"
TREND_STRONG_DOWN = "strong_down"


class WalkForwardValidator:
    def __init__(self, train_window: int = 60, test_window: int = 20, step: int = 20):
        self.train_window = train_window
        self.test_window = test_window
        self.step = step

    def validate(self, predictions_df: pd.DataFrame, actual_df: pd.DataFrame) -> dict:
        if predictions_df.empty or actual_df.empty:
            return self._empty_result()

        pred_cols = {"date", "predicted_low", "predicted_high", "predicted_direction", "current_close", "close"}
        actual_cols = {"date", "open", "high", "low", "close"}

        overlap = pred_cols & actual_cols - {"date"}
        if overlap:
            rename_map = {c: f"{c}_pred" for c in overlap if c in predictions_df.columns}
            predictions_df = predictions_df.rename(columns=rename_map)

        merged = pd.merge(predictions_df, actual_df, on="date", how="inner")
        if merged.empty:
            return self._empty_result()

        if "close_pred" in merged.columns and "close" not in merged.columns:
            merged = merged.rename(columns={"close_pred": "close"})
        elif "close_pred" in merged.columns:
            merged = merged.drop(columns=["close"])
            merged = merged.rename(columns={"close_pred": "close"})

        merged = merged.sort_values("date").reset_index(drop=True)
        total_len = len(merged)

        min_required = self.train_window + self.test_window
        if total_len < min_required:
            return self._empty_result()

        window_metrics: List[dict] = []
        start = 0
        window_id = 0

        while start + min_required <= total_len:
            test_start = start + self.train_window
            test_end = min(test_start + self.test_window, total_len)

            if test_end <= test_start:
                break

            window_data = merged.iloc[test_start:test_end]
            metrics = self._compute_window_metrics(window_data)
            metrics["window_id"] = window_id
            metrics["train_start"] = str(merged.iloc[start]["date"])[:10]
            metrics["train_end"] = str(merged.iloc[test_start - 1]["date"])[:10]
            metrics["test_start"] = str(merged.iloc[test_start]["date"])[:10]
            metrics["test_end"] = str(merged.iloc[test_end - 1]["date"])[:10]
            metrics["n_predictions"] = len(window_data)

            window_metrics.append(metrics)
            window_id += 1
            start += self.step

        if not window_metrics:
            return self._empty_result()

        overall = self._compute_overall(window_metrics)
        stability = self._compute_stability(window_metrics)

        return {
            "windows": window_metrics,
            "overall": overall,
            "stability": stability,
        }

    def _compute_window_metrics(self, data: pd.DataFrame) -> dict:
        n = len(data)
        if n == 0:
            return {
                "hit_rate": 0.0,
                "direction_accuracy": 0.0,
                "trend_accuracy": 0.0,
            }

        hit_count = 0
        hit_valid = 0
        direction_correct = 0
        direction_valid = 0
        trend_correct = 0
        trend_valid = 0

        for _, row in data.iterrows():
            pred_low = row.get("predicted_low")
            pred_high = row.get("predicted_high")
            pred_direction = row.get("predicted_direction")
            actual_close = row.get("close")
            current_close = row.get("current_close")

            if pred_low is not None and pred_high is not None and actual_close is not None:
                try:
                    pl = float(pred_low)
                    ph = float(pred_high)
                    ac = float(actual_close)
                    if math.isfinite(pl) and math.isfinite(ph) and math.isfinite(ac):
                        hit_valid += 1
                        if pl <= ac <= ph:
                            hit_count += 1
                except (TypeError, ValueError):
                    pass

            if pred_direction is not None and current_close is not None and actual_close is not None:
                try:
                    cc = float(current_close)
                    ac = float(actual_close)
                    if cc > 0 and math.isfinite(cc) and math.isfinite(ac):
                        actual_change_pct = (ac - cc) / cc * 100
                        actual_trend = _get_trend_from_change(actual_change_pct)

                        trend_valid += 1
                        if pred_direction == actual_trend:
                            trend_correct += 1

                        direction_valid += 1
                        if _is_trend_consistent(pred_direction, actual_trend):
                            direction_correct += 1
                except (TypeError, ValueError):
                    pass

        hit_rate = round(hit_count / hit_valid * 100, 1) if hit_valid > 0 else 0.0
        direction_accuracy = round(direction_correct / direction_valid * 100, 1) if direction_valid > 0 else 0.0
        trend_accuracy = round(trend_correct / trend_valid * 100, 1) if trend_valid > 0 else 0.0

        return {
            "hit_rate": hit_rate,
            "direction_accuracy": direction_accuracy,
            "trend_accuracy": trend_accuracy,
        }

    def _compute_overall(self, window_metrics: List[dict]) -> dict:
        hit_rates = [m["hit_rate"] for m in window_metrics]
        dir_accs = [m["direction_accuracy"] for m in window_metrics]
        trend_accs = [m["trend_accuracy"] for m in window_metrics]

        return {
            "avg_hit_rate": round(float(np.mean(hit_rates)), 1),
            "avg_direction_accuracy": round(float(np.mean(dir_accs)), 1),
            "avg_trend_accuracy": round(float(np.mean(trend_accs)), 1),
        }

    def _compute_stability(self, window_metrics: List[dict]) -> dict:
        hit_rates = [m["hit_rate"] for m in window_metrics]
        dir_accs = [m["direction_accuracy"] for m in window_metrics]
        trend_accs = [m["trend_accuracy"] for m in window_metrics]

        hit_std = float(np.std(hit_rates, ddof=1)) if len(hit_rates) > 1 else 0.0
        dir_std = float(np.std(dir_accs, ddof=1)) if len(dir_accs) > 1 else 0.0
        trend_std = float(np.std(trend_accs, ddof=1)) if len(trend_accs) > 1 else 0.0

        hit_mean = float(np.mean(hit_rates))
        sharpe_ratio = round(hit_mean / hit_std, 3) if hit_std > 0 else 0.0

        return {
            "hit_rate_std": round(hit_std, 2),
            "direction_accuracy_std": round(dir_std, 2),
            "trend_accuracy_std": round(trend_std, 2),
            "sharpe_ratio": sharpe_ratio,
        }

    def _empty_result(self) -> dict:
        return {
            "windows": [],
            "overall": {
                "avg_hit_rate": 0.0,
                "avg_direction_accuracy": 0.0,
                "avg_trend_accuracy": 0.0,
            },
            "stability": {
                "hit_rate_std": 0.0,
                "direction_accuracy_std": 0.0,
                "trend_accuracy_std": 0.0,
                "sharpe_ratio": 0.0,
            },
        }
