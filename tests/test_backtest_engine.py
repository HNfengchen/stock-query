from scripts.core.backtest import Backtester


def test_evaluate_predictions_reports_interval_quality_metrics():
    predictions = [
        {
            "current_price": 100.0,
            "day1": {"low": 98.0, "high": 102.0},
            "day2": {"low": 97.0, "high": 103.0},
            "actual_day1": 101.0,
            "actual_day2": 104.0,
            "trend": "up",
            "day2_trend": "up",
        },
        {
            "current_price": 200.0,
            "day1": {"low": 190.0, "high": 210.0},
            "day2": {"low": 188.0, "high": 212.0},
            "actual_day1": 215.0,
            "actual_day2": 198.0,
            "trend": "down",
            "day2_trend": "down",
        },
    ]

    stats = Backtester().evaluate_predictions(predictions)

    assert stats["mean_width_pct"] == 0.07
    assert stats["median_width_pct"] == 0.07
    assert stats["midpoint_mae_pct"] == 0.0425
    assert stats["coverage_width_score"] == 0.43


def test_evaluate_predictions_ignores_invalid_interval_metrics_without_crashing():
    predictions = [
        {
            "current_price": 100.0,
            "day1": {"low": 105.0, "high": 95.0},
            "day2": {"low": None, "high": None},
            "actual_day1": 100.0,
            "actual_day2": 101.0,
            "trend": "neutral",
            "day2_trend": "up",
        },
        {
            "current_price": None,
            "day1": {"low": None, "high": None},
            "day2": {"low": None, "high": None},
            "actual_day1": 100.0,
            "actual_day2": 100.0,
            "trend": "up",
            "day2_trend": "down",
        },
    ]

    stats = Backtester().evaluate_predictions(predictions)

    assert stats["mean_width_pct"] == 0.0
    assert stats["median_width_pct"] == 0.0
    assert stats["midpoint_mae_pct"] == 0.0
