import pandas as pd
import pytest

from backend.services import backtest_service


def _history_frame(length=120):
    dates = pd.date_range("2024-01-01", periods=length, freq="D")
    return pd.DataFrame(
        {
            "日期": dates,
            "开盘": [10.0] * length,
            "收盘": [10.0] * length,
            "最高": [10.5] * length,
            "最低": [9.5] * length,
            "成交量": [1000] * length,
        }
    )


def test_run_builtin_backtest_passes_lookback_days(monkeypatch):
    captured = {}

    class FakeBacktester:
        def __init__(self, atr_multiplier, stock_code):
            captured["atr_multiplier"] = atr_multiplier
            captured["stock_code"] = stock_code

        def calculate_predictions(self, df, lookback_days=60):
            captured["lookback_days"] = lookback_days
            return [
                {
                    "date": "2024-01-31",
                    "current_price": 100.0,
                    "actual_day1": 101.0,
                    "trend": "up",
                    "day1": {"low": 100.5, "high": 102.0},
                    "day2": {"low": 99.0, "high": 103.0},
                }
            ]

        def evaluate_predictions(self, predictions):
            return {
                "day1_hit_rate": 100.0,
                "day2_hit_rate": 0.0,
                "day1_trend_accuracy": 100.0,
                "day2_trend_accuracy": 0.0,
                "total_predictions": len(predictions),
                "mean_width_pct": 0.015,
                "median_width_pct": 0.015,
                "midpoint_mae_pct": 0.0025,
                "coverage_width_score": 0.985,
            }

    def fake_get_history_data(stock_code, days=120):
        captured["history_days"] = days
        return _history_frame()

    monkeypatch.setattr(backtest_service, "get_history_data", fake_get_history_data)
    monkeypatch.setattr(backtest_service, "Backtester", FakeBacktester)

    result = backtest_service.run_builtin_backtest(
        "000001", {"atr_multiplier": 2.0, "lookback_days": 45}
    )

    assert captured["lookback_days"] == 45
    assert captured["history_days"] == 120
    assert result["effective_params"] == {"atr_multiplier": 2.0, "lookback_days": 45}


@pytest.mark.parametrize("lookback_days", [29, 253])
def test_run_builtin_backtest_rejects_invalid_lookback_days(monkeypatch, lookback_days):
    monkeypatch.setattr(backtest_service, "get_history_data", lambda stock_code, days=120: _history_frame())

    with pytest.raises(ValueError, match="回看天数必须在 30 到 252 之间"):
        backtest_service.run_builtin_backtest("000001", {"lookback_days": lookback_days})


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"atr_multiplier": "abc"}, "ATR乘数必须是有效数字"),
        ({"lookback_days": "abc"}, "回看天数必须是整数"),
        ({"lookback_days": 45.9}, "回看天数必须是整数"),
        ({"lookback_days": True}, "回看天数必须是整数"),
    ],
)
def test_run_builtin_backtest_rejects_invalid_numeric_params(monkeypatch, params, message):
    monkeypatch.setattr(backtest_service, "get_history_data", lambda stock_code, days=120: _history_frame())

    with pytest.raises(ValueError, match=message):
        backtest_service.run_builtin_backtest("000001", params)


def test_run_builtin_backtest_fetches_enough_history_for_large_lookback(monkeypatch):
    captured = {}

    class FakeBacktester:
        def __init__(self, atr_multiplier, stock_code):
            pass

        def calculate_predictions(self, df, lookback_days=60):
            captured["lookback_days"] = lookback_days
            return [
                {
                    "date": "2024-01-31",
                    "current_price": 100.0,
                    "actual_day1": 101.0,
                    "trend": "up",
                    "day1": {"low": 100.0, "high": 102.0},
                    "day2": {"low": 99.0, "high": 103.0},
                }
            ]

        def evaluate_predictions(self, predictions):
            return {
                "day1_hit_rate": 100.0,
                "day2_hit_rate": 0.0,
                "day1_trend_accuracy": 100.0,
                "day2_trend_accuracy": 0.0,
                "total_predictions": len(predictions),
            }

    def fake_get_history_data(stock_code, days=120):
        captured["history_days"] = days
        return _history_frame(length=days)

    monkeypatch.setattr(backtest_service, "get_history_data", fake_get_history_data)
    monkeypatch.setattr(backtest_service, "Backtester", FakeBacktester)

    backtest_service.run_builtin_backtest("000001", {"lookback_days": 252})

    assert captured["history_days"] == 262
    assert captured["lookback_days"] == 252


def test_run_builtin_backtest_uses_dynamic_minimum_rows(monkeypatch):
    monkeypatch.setattr(
        backtest_service,
        "get_history_data",
        lambda stock_code, days=120: _history_frame(length=45),
    )

    class FakeBacktester:
        def __init__(self, atr_multiplier, stock_code):
            pass

        def calculate_predictions(self, df, lookback_days=60):
            return [
                {
                    "date": "2024-01-31",
                    "current_price": 100.0,
                    "actual_day1": 101.0,
                    "trend": "up",
                    "day1": {"low": 100.0, "high": 102.0},
                    "day2": {"low": 99.0, "high": 103.0},
                }
            ]

        def evaluate_predictions(self, predictions):
            return {"total_predictions": len(predictions)}

    monkeypatch.setattr(backtest_service, "Backtester", FakeBacktester)

    result = backtest_service.run_builtin_backtest("000001", {"lookback_days": 30})

    assert result["statistics"]["total_predictions"] == 1


def test_run_builtin_backtest_uses_long_only_positions_and_exposure_cost(monkeypatch):
    class FakeBacktester:
        def __init__(self, atr_multiplier, stock_code):
            pass

        def calculate_predictions(self, df, lookback_days=60):
            return [
                {
                    "date": "2024-01-31",
                    "current_price": 100.0,
                    "actual_day1": 110.0,
                    "trend": "neutral",
                    "day1": {"low": 99.0, "high": 101.0},
                    "day2": {"low": 99.0, "high": 101.0},
                },
                {
                    "date": "2024-02-01",
                    "current_price": 100.0,
                    "actual_day1": 110.0,
                    "trend": "down",
                    "day1": {"low": 99.0, "high": 101.0},
                    "day2": {"low": 99.0, "high": 101.0},
                },
                {
                    "date": "2024-02-02",
                    "current_price": 100.0,
                    "actual_day1": 110.0,
                    "trend": "up",
                    "day1": {"low": 105.0, "high": 112.0},
                    "day2": {"low": 99.0, "high": 113.0},
                },
                {
                    "date": "2024-02-03",
                    "current_price": 100.0,
                    "actual_day1": 90.0,
                    "trend": "neutral",
                    "day1": {"low": 98.0, "high": 102.0},
                    "day2": {"low": 99.0, "high": 101.0},
                },
            ]

        def evaluate_predictions(self, predictions):
            return {
                "day1_hit_rate": 50.0,
                "day2_hit_rate": 0.0,
                "day1_trend_accuracy": 50.0,
                "day2_trend_accuracy": 0.0,
                "total_predictions": len(predictions),
                "mean_width_pct": 0.04,
                "median_width_pct": 0.04,
                "midpoint_mae_pct": 0.03,
                "coverage_width_score": 0.46,
            }

    monkeypatch.setattr(backtest_service, "get_history_data", lambda stock_code, days=120: _history_frame())
    monkeypatch.setattr(backtest_service, "Backtester", FakeBacktester)

    result = backtest_service.run_builtin_backtest("000001", {"lookback_days": 60})

    curve = result["equity_curve"]
    assert curve[0]["position"] == 0.0
    assert curve[0]["daily_return"] == 0.0
    assert curve[1]["position"] == 0.0
    assert curve[1]["daily_return"] == 0.0
    assert curve[2]["position"] == 0.3
    assert curve[2]["turnover"] == 0.3
    assert curve[2]["cost"] == 0.0005
    assert curve[2]["daily_return"] == 0.0295
    assert curve[3]["position"] == 0.0
    assert curve[3]["turnover"] == 0.3
    assert curve[3]["cost"] == 0.0005
    assert curve[3]["daily_return"] == -0.0005
    assert result["statistics"]["trades"] == 2
    assert result["statistics"]["turnover"] == 0.6
    assert result["statistics"]["total_cost"] == 0.001
    assert result["statistics"]["win_rate"] == 0.25


def test_run_builtin_backtest_handles_none_prices_and_stats(monkeypatch):
    class FakeBacktester:
        def __init__(self, atr_multiplier, stock_code):
            pass

        def calculate_predictions(self, df, lookback_days=60):
            return [
                {
                    "date": "2024-01-31",
                    "current_price": None,
                    "actual_day1": 101.0,
                    "trend": "up",
                    "day1": {"low": 100.0, "high": 102.0},
                    "day2": {"low": 99.0, "high": 103.0},
                }
            ]

        def evaluate_predictions(self, predictions):
            return {
                "day1_hit_rate": None,
                "day2_hit_rate": None,
                "day1_trend_accuracy": None,
                "day2_trend_accuracy": None,
                "total_predictions": None,
                "mean_width_pct": None,
                "median_width_pct": None,
                "midpoint_mae_pct": None,
                "coverage_width_score": None,
            }

    monkeypatch.setattr(backtest_service, "get_history_data", lambda stock_code, days=120: _history_frame())
    monkeypatch.setattr(backtest_service, "Backtester", FakeBacktester)

    result = backtest_service.run_builtin_backtest("000001", {"lookback_days": 60})

    assert result["equity_curve"][0]["daily_return"] == -0.0005
    assert result["statistics"]["day1_accuracy"] == 0.0
    assert result["statistics"]["total_predictions"] == 0
    assert result["statistics"]["mean_width_pct"] == 0.0


def test_run_builtin_backtest_handles_missing_stats_and_prediction_prices(monkeypatch):
    class FakeBacktester:
        def __init__(self, atr_multiplier, stock_code):
            pass

        def calculate_predictions(self, df, lookback_days=60):
            return [
                {
                    "date": "2024-01-31",
                    "current_price": None,
                    "actual_day1": None,
                    "trend": "neutral",
                    "day1": {"low": None, "high": None},
                    "day2": {"low": None, "high": None},
                }
            ]

        def evaluate_predictions(self, predictions):
            return None

    monkeypatch.setattr(backtest_service, "get_history_data", lambda stock_code, days=120: _history_frame())
    monkeypatch.setattr(backtest_service, "Backtester", FakeBacktester)

    result = backtest_service.run_builtin_backtest("000001", {"lookback_days": 60})

    assert result["statistics"]["day1_accuracy"] == 0.0
    assert result["statistics"]["mean_width_pct"] == 0.0
    assert result["predictions"][0]["predicted_low"] == 0.0
    assert result["predictions"][0]["predicted_high"] == 0.0
