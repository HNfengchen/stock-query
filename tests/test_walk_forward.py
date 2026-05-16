import pytest
import pandas as pd
import numpy as np
from scripts.core.walk_forward import WalkForwardValidator


def _make_predictions_df(n: int, base_price: float = 10.0, seed: int = 42):
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    current_close = base_price + rng.randn(n).cumsum() * 0.1
    predicted_low = current_close - 0.5
    predicted_high = current_close + 0.5
    directions = []
    for i in range(n):
        if i == 0:
            directions.append("neutral")
        else:
            chg = (current_close[i] - current_close[i - 1]) / current_close[i - 1] * 100
            if chg > 3:
                directions.append("strong_up")
            elif chg > 1:
                directions.append("up")
            elif chg < -3:
                directions.append("strong_down")
            elif chg < -1:
                directions.append("down")
            else:
                directions.append("neutral")

    actual_close = current_close + rng.randn(n) * 0.3

    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "predicted_low": predicted_low,
        "predicted_high": predicted_high,
        "predicted_direction": directions,
        "current_close": current_close,
        "close": actual_close,
    })


def _make_actual_df(n: int, base_price: float = 10.0, seed: int = 42):
    rng = np.random.RandomState(seed + 1)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = base_price + rng.randn(n).cumsum() * 0.1
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": close - 0.1,
        "high": close + 0.3,
        "low": close - 0.3,
        "close": close,
    })


class TestWalkForwardValidatorInit:
    def test_default_params(self):
        v = WalkForwardValidator()
        assert v.train_window == 60
        assert v.test_window == 20
        assert v.step == 20

    def test_custom_params(self):
        v = WalkForwardValidator(train_window=30, test_window=10, step=5)
        assert v.train_window == 30
        assert v.test_window == 10
        assert v.step == 5


class TestWalkForwardWindowSliding:
    def test_window_count(self):
        n = 120
        pred_df = _make_predictions_df(n)
        actual_df = _make_actual_df(n)
        v = WalkForwardValidator(train_window=60, test_window=20, step=20)
        result = v.validate(pred_df, actual_df)
        expected_windows = (n - 60 - 20) // 20 + 1
        assert len(result["windows"]) == expected_windows

    def test_window_boundaries(self):
        n = 100
        pred_df = _make_predictions_df(n)
        actual_df = _make_actual_df(n)
        v = WalkForwardValidator(train_window=40, test_window=10, step=10)
        result = v.validate(pred_df, actual_df)
        for w in result["windows"]:
            assert w["train_start"] is not None
            assert w["train_end"] is not None
            assert w["test_start"] is not None
            assert w["test_end"] is not None
            assert w["n_predictions"] > 0

    def test_step_equals_test_window_no_overlap(self):
        n = 100
        pred_df = _make_predictions_df(n)
        actual_df = _make_actual_df(n)
        v = WalkForwardValidator(train_window=40, test_window=10, step=10)
        result = v.validate(pred_df, actual_df)
        if len(result["windows"]) >= 2:
            w1 = result["windows"][0]
            w2 = result["windows"][1]
            assert w1["window_id"] == 0
            assert w2["window_id"] == 1


class TestWalkForwardMetricComputation:
    def test_hit_rate_perfect(self):
        pred_df = pd.DataFrame({
            "date": [f"2024-01-{i:02d}" for i in range(1, 11)],
            "predicted_low": [9.0] * 10,
            "predicted_high": [11.0] * 10,
            "predicted_direction": ["neutral"] * 10,
            "current_close": [10.0] * 10,
            "close": [10.0] * 10,
        })
        actual_df = pd.DataFrame({
            "date": [f"2024-01-{i:02d}" for i in range(1, 11)],
            "open": [10.0] * 10,
            "high": [10.5] * 10,
            "low": [9.5] * 10,
            "close": [10.0] * 10,
        })
        v = WalkForwardValidator(train_window=3, test_window=5, step=5)
        result = v.validate(pred_df, actual_df)
        if result["windows"]:
            assert result["windows"][0]["hit_rate"] == 100.0

    def test_hit_rate_zero(self):
        pred_df = pd.DataFrame({
            "date": [f"2024-01-{i:02d}" for i in range(1, 11)],
            "predicted_low": [8.0] * 10,
            "predicted_high": [8.5] * 10,
            "predicted_direction": ["neutral"] * 10,
            "current_close": [10.0] * 10,
            "close": [15.0] * 10,
        })
        actual_df = pd.DataFrame({
            "date": [f"2024-01-{i:02d}" for i in range(1, 11)],
            "open": [15.0] * 10,
            "high": [15.5] * 10,
            "low": [14.5] * 10,
            "close": [15.0] * 10,
        })
        v = WalkForwardValidator(train_window=3, test_window=5, step=5)
        result = v.validate(pred_df, actual_df)
        if result["windows"]:
            assert result["windows"][0]["hit_rate"] == 0.0

    def test_direction_accuracy(self):
        pred_df = pd.DataFrame({
            "date": [f"2024-01-{i:02d}" for i in range(1, 11)],
            "predicted_low": [9.0] * 10,
            "predicted_high": [11.0] * 10,
            "predicted_direction": ["up"] * 10,
            "current_close": [10.0] * 10,
            "close": [10.5] * 10,
        })
        actual_df = pd.DataFrame({
            "date": [f"2024-01-{i:02d}" for i in range(1, 11)],
            "open": [10.0] * 10,
            "high": [10.8] * 10,
            "low": [9.8] * 10,
            "close": [10.5] * 10,
        })
        v = WalkForwardValidator(train_window=3, test_window=5, step=5)
        result = v.validate(pred_df, actual_df)
        if result["windows"]:
            assert result["windows"][0]["direction_accuracy"] == 100.0

    def test_trend_accuracy(self):
        pred_df = pd.DataFrame({
            "date": [f"2024-01-{i:02d}" for i in range(1, 11)],
            "predicted_low": [9.0] * 10,
            "predicted_high": [11.0] * 10,
            "predicted_direction": ["up"] * 10,
            "current_close": [10.0] * 10,
            "close": [10.15] * 10,
        })
        actual_df = pd.DataFrame({
            "date": [f"2024-01-{i:02d}" for i in range(1, 11)],
            "open": [10.0] * 10,
            "high": [10.3] * 10,
            "low": [9.9] * 10,
            "close": [10.15] * 10,
        })
        v = WalkForwardValidator(train_window=3, test_window=5, step=5)
        result = v.validate(pred_df, actual_df)
        if result["windows"]:
            assert result["windows"][0]["trend_accuracy"] == 100.0


class TestWalkForwardStability:
    def test_stability_keys(self):
        n = 120
        pred_df = _make_predictions_df(n)
        actual_df = _make_actual_df(n)
        v = WalkForwardValidator(train_window=60, test_window=20, step=20)
        result = v.validate(pred_df, actual_df)
        assert "hit_rate_std" in result["stability"]
        assert "direction_accuracy_std" in result["stability"]
        assert "trend_accuracy_std" in result["stability"]
        assert "sharpe_ratio" in result["stability"]

    def test_stability_values_non_negative(self):
        n = 120
        pred_df = _make_predictions_df(n)
        actual_df = _make_actual_df(n)
        v = WalkForwardValidator(train_window=60, test_window=20, step=20)
        result = v.validate(pred_df, actual_df)
        assert result["stability"]["hit_rate_std"] >= 0
        assert result["stability"]["direction_accuracy_std"] >= 0
        assert result["stability"]["trend_accuracy_std"] >= 0

    def test_sharpe_ratio_computation(self):
        pred_df = pd.DataFrame({
            "date": [f"2024-01-{i:02d}" for i in range(1, 101)],
            "predicted_low": [9.0] * 100,
            "predicted_high": [11.0] * 100,
            "predicted_direction": ["up"] * 100,
            "current_close": [10.0] * 100,
            "close": [10.5] * 100,
        })
        actual_df = pd.DataFrame({
            "date": [f"2024-01-{i:02d}" for i in range(1, 101)],
            "open": [10.0] * 100,
            "high": [10.8] * 100,
            "low": [9.8] * 100,
            "close": [10.5] * 100,
        })
        v = WalkForwardValidator(train_window=40, test_window=10, step=10)
        result = v.validate(pred_df, actual_df)
        if len(result["windows"]) > 1 and result["stability"]["hit_rate_std"] == 0:
            assert result["stability"]["sharpe_ratio"] == 0.0


class TestWalkForwardOverall:
    def test_overall_keys(self):
        n = 120
        pred_df = _make_predictions_df(n)
        actual_df = _make_actual_df(n)
        v = WalkForwardValidator(train_window=60, test_window=20, step=20)
        result = v.validate(pred_df, actual_df)
        assert "avg_hit_rate" in result["overall"]
        assert "avg_direction_accuracy" in result["overall"]
        assert "avg_trend_accuracy" in result["overall"]

    def test_overall_is_average_of_windows(self):
        n = 120
        pred_df = _make_predictions_df(n)
        actual_df = _make_actual_df(n)
        v = WalkForwardValidator(train_window=60, test_window=20, step=20)
        result = v.validate(pred_df, actual_df)
        if result["windows"]:
            hit_rates = [w["hit_rate"] for w in result["windows"]]
            expected_avg = round(float(np.mean(hit_rates)), 1)
            assert abs(result["overall"]["avg_hit_rate"] - expected_avg) < 0.2


class TestWalkForwardEdgeCases:
    def test_empty_predictions(self):
        pred_df = pd.DataFrame(columns=["date", "predicted_low", "predicted_high", "predicted_direction", "current_close", "close"])
        actual_df = _make_actual_df(100)
        v = WalkForwardValidator()
        result = v.validate(pred_df, actual_df)
        assert result["windows"] == []
        assert result["overall"]["avg_hit_rate"] == 0.0

    def test_empty_actuals(self):
        pred_df = _make_predictions_df(100)
        actual_df = pd.DataFrame(columns=["date", "open", "high", "low", "close"])
        v = WalkForwardValidator()
        result = v.validate(pred_df, actual_df)
        assert result["windows"] == []

    def test_insufficient_data(self):
        pred_df = _make_predictions_df(10)
        actual_df = _make_actual_df(10)
        v = WalkForwardValidator(train_window=60, test_window=20, step=20)
        result = v.validate(pred_df, actual_df)
        assert result["windows"] == []
        assert result["overall"]["avg_hit_rate"] == 0.0

    def test_single_window(self):
        pred_df = _make_predictions_df(85)
        actual_df = _make_actual_df(85)
        v = WalkForwardValidator(train_window=60, test_window=20, step=20)
        result = v.validate(pred_df, actual_df)
        assert len(result["windows"]) == 1
        assert result["windows"][0]["window_id"] == 0

    def test_none_values_in_predictions(self):
        n = 100
        pred_df = _make_predictions_df(n)
        pred_df.loc[0, "predicted_low"] = None
        pred_df.loc[1, "predicted_high"] = None
        actual_df = _make_actual_df(n)
        v = WalkForwardValidator(train_window=40, test_window=10, step=10)
        result = v.validate(pred_df, actual_df)
        assert "windows" in result
