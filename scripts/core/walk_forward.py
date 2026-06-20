import math
import numpy as np
import pandas as pd
from typing import Any, Callable, List

from scripts.core.backtest import (
    _get_trend_from_change,
    _is_trend_consistent,
    _simulate_trade_return,
    TransactionCostModel,
)

TREND_STRONG_UP = "strong_up"
TREND_UP = "up"
TREND_NEUTRAL = "neutral"
TREND_DOWN = "down"
TREND_STRONG_DOWN = "strong_down"

# 从配置读取 Walk-Forward 默认窗口，保留硬编码默认值以防配置缺失
try:
    from scripts.core.config_loader import load_config

    _BACKTEST_CFG = load_config().get("backtest", {})
    _WALK_FORWARD_CFG = _BACKTEST_CFG.get("walk_forward", {})
    _DEFAULT_TRAIN_WINDOW = _WALK_FORWARD_CFG.get("train_window", 60)
    _DEFAULT_TEST_WINDOW = _WALK_FORWARD_CFG.get("test_window", 20)
    _DEFAULT_STEP = _WALK_FORWARD_CFG.get("step", 20)
except Exception:
    _DEFAULT_TRAIN_WINDOW = 60
    _DEFAULT_TEST_WINDOW = 20
    _DEFAULT_STEP = 20


class WalkForwardValidator:
    def __init__(
        self,
        train_window: int = _DEFAULT_TRAIN_WINDOW,
        test_window: int = _DEFAULT_TEST_WINDOW,
        step: int = _DEFAULT_STEP,
        cost_model: TransactionCostModel = None,
    ):
        self.train_window = train_window
        self.test_window = test_window
        self.step = step
        self.cost_model = cost_model or TransactionCostModel()

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

    def walk_forward_train_validate(
        self,
        data_df: pd.DataFrame,
        train_callback: Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame] = None,
        trainer_callback: Callable[[pd.DataFrame], Any] = None,
    ) -> dict:
        """真正的滚动训练 Walk-Forward 验证。

        参数：
            data_df: 包含完整历史数据的 DataFrame，列需包含 date 及价格列
                （open/high/low/close 或 开盘/最高/最低/收盘）。
            train_callback: 接收 (train_df, test_df) 并返回 predictions_df 的回调，
                predictions_df 的格式与 validate 方法的 predictions_df 一致。
                若未提供，则跳过预测生成，仅保留窗口结构。
            trainer_callback: 可选的训练回调，签名 trainer_callback(train_df) -> Any。
                在每个训练窗口上调用，用于触发模型重新训练。

        返回：
            与 validate 相同结构的结果 dict：{"windows": [...], "overall": {...}, "stability": {...}}
        """
        if data_df is None or data_df.empty:
            return self._empty_result()

        data = self._normalize_price_columns(data_df.copy())
        if "date" not in data.columns:
            return self._empty_result()

        data = data.sort_values("date").reset_index(drop=True)
        total_len = len(data)
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

            train_df = data.iloc[start:test_start].copy()
            test_df = data.iloc[test_start:test_end].copy()

            # 若提供训练回调，在每个训练窗口上调用，实现真正的滚动训练
            if trainer_callback is not None:
                trainer_callback(train_df)

            if train_callback is not None:
                predictions_df = train_callback(train_df, test_df)
                metrics = self._evaluate_train_window(predictions_df, test_df)
            else:
                metrics = self._compute_window_metrics(pd.DataFrame())
                metrics["n_predictions"] = 0

            metrics["window_id"] = window_id
            metrics["train_start"] = str(data.iloc[start]["date"])[:10]
            metrics["train_end"] = str(data.iloc[test_start - 1]["date"])[:10]
            metrics["test_start"] = str(data.iloc[test_start]["date"])[:10]
            metrics["test_end"] = str(data.iloc[test_end - 1]["date"])[:10]

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

    def _normalize_price_columns(self, data: pd.DataFrame) -> pd.DataFrame:
        """将中文列名统一映射为英文列名，便于后续处理。"""
        cn_to_en = {"开盘": "open", "最高": "high", "最低": "low", "收盘": "close"}
        rename_map = {
            cn: en for cn, en in cn_to_en.items()
            if cn in data.columns and en not in data.columns
        }
        if rename_map:
            data = data.rename(columns=rename_map)
        return data

    def _evaluate_train_window(
        self,
        predictions_df: pd.DataFrame,
        test_df: pd.DataFrame,
    ) -> dict:
        """将单个窗口的预测结果与测试集实际数据合并并计算指标。"""
        if predictions_df is None or predictions_df.empty or test_df.empty:
            metrics = self._compute_window_metrics(pd.DataFrame())
            metrics["n_predictions"] = 0
            return metrics

        pred_cols = {"date", "predicted_low", "predicted_high", "predicted_direction", "current_close", "close"}
        actual_cols = {"date", "open", "high", "low", "close"}

        overlap = pred_cols & actual_cols - {"date"}
        if overlap:
            rename_map = {c: f"{c}_pred" for c in overlap if c in predictions_df.columns}
            predictions_df = predictions_df.rename(columns=rename_map)

        available_actual_cols = list(actual_cols & set(test_df.columns))
        if not available_actual_cols:
            metrics = self._compute_window_metrics(pd.DataFrame())
            metrics["n_predictions"] = 0
            return metrics

        actual_df = test_df[available_actual_cols].copy()
        merged = pd.merge(predictions_df, actual_df, on="date", how="inner")
        if merged.empty:
            metrics = self._compute_window_metrics(pd.DataFrame())
            metrics["n_predictions"] = 0
            return metrics

        if "close_pred" in merged.columns and "close" not in merged.columns:
            merged = merged.rename(columns={"close_pred": "close"})
        elif "close_pred" in merged.columns:
            merged = merged.drop(columns=["close"])
            merged = merged.rename(columns={"close_pred": "close"})

        merged = merged.sort_values("date").reset_index(drop=True)
        metrics = self._compute_window_metrics(merged)
        metrics["n_predictions"] = len(merged)
        return metrics

    def _compute_window_metrics(self, data: pd.DataFrame) -> dict:
        n = len(data)
        if n == 0:
            return {
                "hit_rate": 0.0,
                "direction_accuracy": 0.0,
                "trend_accuracy": 0.0,
                "avg_return_without_cost": 0.0,
                "avg_return_with_cost": 0.0,
            }

        hit_count = 0
        hit_valid = 0
        direction_correct = 0
        direction_valid = 0
        trend_correct = 0
        trend_valid = 0
        returns_no_cost = []
        returns_with_cost = []

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

                        if pred_direction in (TREND_STRONG_UP, TREND_UP):
                            trade = _simulate_trade_return(cc, ac, self.cost_model)
                            returns_no_cost.append(trade["return_without_cost"])
                            returns_with_cost.append(trade["return_with_cost"])
                except (TypeError, ValueError):
                    pass

        hit_rate = round(hit_count / hit_valid * 100, 1) if hit_valid > 0 else 0.0
        direction_accuracy = round(direction_correct / direction_valid * 100, 1) if direction_valid > 0 else 0.0
        trend_accuracy = round(trend_correct / trend_valid * 100, 1) if trend_valid > 0 else 0.0
        avg_return_without_cost = round(float(np.mean(returns_no_cost)), 6) if returns_no_cost else 0.0
        avg_return_with_cost = round(float(np.mean(returns_with_cost)), 6) if returns_with_cost else 0.0

        return {
            "hit_rate": hit_rate,
            "direction_accuracy": direction_accuracy,
            "trend_accuracy": trend_accuracy,
            "avg_return_without_cost": avg_return_without_cost,
            "avg_return_with_cost": avg_return_with_cost,
        }

    def _compute_overall(self, window_metrics: List[dict]) -> dict:
        hit_rates = [m["hit_rate"] for m in window_metrics]
        dir_accs = [m["direction_accuracy"] for m in window_metrics]
        trend_accs = [m["trend_accuracy"] for m in window_metrics]
        ret_no_cost = [m["avg_return_without_cost"] for m in window_metrics]
        ret_with_cost = [m["avg_return_with_cost"] for m in window_metrics]

        return {
            "avg_hit_rate": round(float(np.mean(hit_rates)), 1),
            "avg_direction_accuracy": round(float(np.mean(dir_accs)), 1),
            "avg_trend_accuracy": round(float(np.mean(trend_accs)), 1),
            "avg_return_without_cost": round(float(np.mean(ret_no_cost)), 6),
            "avg_return_with_cost": round(float(np.mean(ret_with_cost)), 6),
        }

    def _compute_stability(self, window_metrics: List[dict]) -> dict:
        hit_rates = [m["hit_rate"] for m in window_metrics]
        dir_accs = [m["direction_accuracy"] for m in window_metrics]
        trend_accs = [m["trend_accuracy"] for m in window_metrics]

        hit_std = float(np.std(hit_rates, ddof=1)) if len(hit_rates) > 1 else 0.0
        dir_std = float(np.std(dir_accs, ddof=1)) if len(dir_accs) > 1 else 0.0
        trend_std = float(np.std(trend_accs, ddof=1)) if len(trend_accs) > 1 else 0.0

        hit_mean = float(np.mean(hit_rates))
        consistency_ratio = round(hit_mean / hit_std, 3) if hit_std > 0 else 0.0

        return {
            "hit_rate_std": round(hit_std, 2),
            "direction_accuracy_std": round(dir_std, 2),
            "trend_accuracy_std": round(trend_std, 2),
            "consistency_ratio": consistency_ratio,
        }

    def _empty_result(self) -> dict:
        return {
            "windows": [],
            "overall": {
                "avg_hit_rate": 0.0,
                "avg_direction_accuracy": 0.0,
                "avg_trend_accuracy": 0.0,
                "avg_return_without_cost": 0.0,
                "avg_return_with_cost": 0.0,
            },
            "stability": {
                "hit_rate_std": 0.0,
                "direction_accuracy_std": 0.0,
                "trend_accuracy_std": 0.0,
                "consistency_ratio": 0.0,
            },
        }
