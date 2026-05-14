import pytest
from unittest.mock import patch, MagicMock
from backend.services import backtest_service


def _mock_db_rows():
    return [
        ("2024-01-10", 10.0, 10.5, 9.5, 11.0, 9.0, 0.02),
        ("2024-01-11", 10.2, 10.7, 9.7, 11.2, 9.2, 0.01),
        ("2024-01-12", 10.5, 11.0, 10.0, 11.5, 9.5, -0.01),
    ]


def _mock_all_prices():
    return [
        ("2024-01-09", 9.8),
        ("2024-01-10", 10.0),
        ("2024-01-11", 10.2),
        ("2024-01-12", 10.5),
        ("2024-01-13", 10.3),
        ("2024-01-14", 10.8),
    ]


@patch("backend.services.backtest_service.get_connection")
def test_run_prediction_validation_basic(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur1 = MagicMock()
    mock_cur1.fetchall.return_value = _mock_db_rows()
    mock_cur2 = MagicMock()
    mock_cur2.fetchall.return_value = _mock_all_prices()

    mock_conn.cursor.side_effect = [mock_cur1, mock_cur2]
    mock_get_conn.return_value = mock_conn

    result = backtest_service.run_prediction_validation("000001")

    assert result["stock_code"] == "000001"
    assert result["total_predictions"] == 3
    assert "statistics" in result
    assert "predictions" in result
    assert len(result["predictions"]) == 3

    for p in result["predictions"]:
        assert "date" in p
        assert "trend" in p
        assert "day1_pred_high" in p
        assert "day1_pred_low" in p
        assert "day2_pred_high" in p
        assert "day2_pred_low" in p
        assert "actual_day1" in p
        assert "actual_day2" in p
        assert "day1_hit" in p
        assert "day2_hit" in p
        assert "day1_trend_correct" in p
        assert "day2_trend_correct" in p


@patch("backend.services.backtest_service.get_connection")
def test_run_prediction_validation_no_data(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = []
    mock_conn.cursor.return_value = mock_cur
    mock_get_conn.return_value = mock_conn

    with pytest.raises(ValueError, match="暂无预测数据"):
        backtest_service.run_prediction_validation("999999")


@patch("backend.services.backtest_service.get_connection")
def test_run_prediction_validation_hit_calculation(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur1 = MagicMock()
    mock_cur1.fetchall.return_value = [
        ("2024-01-10", 10.0, 10.5, 9.5, 11.0, 9.0, 0.02),
    ]
    mock_cur2 = MagicMock()
    mock_cur2.fetchall.return_value = [
        ("2024-01-09", 9.8),
        ("2024-01-10", 10.0),
        ("2024-01-11", 10.3),
        ("2024-01-12", 10.8),
    ]

    mock_conn.cursor.side_effect = [mock_cur1, mock_cur2]
    mock_get_conn.return_value = mock_conn

    result = backtest_service.run_prediction_validation("000001")

    pred = result["predictions"][0]
    assert pred["day1_hit"] is True
    assert pred["day2_hit"] is True
    assert result["statistics"]["day1_hit_rate"] == 100.0
    assert result["statistics"]["day2_hit_rate"] == 100.0


@patch("backend.services.backtest_service.get_connection")
def test_run_prediction_validation_miss_calculation(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur1 = MagicMock()
    mock_cur1.fetchall.return_value = [
        ("2024-01-10", 10.0, 10.1, 9.9, 10.2, 9.8, 0.0),
    ]
    mock_cur2 = MagicMock()
    mock_cur2.fetchall.return_value = [
        ("2024-01-09", 9.8),
        ("2024-01-10", 10.0),
        ("2024-01-11", 11.0),
        ("2024-01-12", 8.0),
    ]

    mock_conn.cursor.side_effect = [mock_cur1, mock_cur2]
    mock_get_conn.return_value = mock_conn

    result = backtest_service.run_prediction_validation("000001")

    pred = result["predictions"][0]
    assert pred["day1_hit"] is False
    assert pred["day2_hit"] is False
    assert result["statistics"]["day1_hit_rate"] == 0.0
    assert result["statistics"]["day2_hit_rate"] == 0.0


@patch("backend.services.backtest_service.get_connection")
def test_run_prediction_validation_trend_from_change_pct(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur1 = MagicMock()
    mock_cur1.fetchall.return_value = [
        ("2024-01-10", 10.0, 10.5, 9.5, 11.0, 9.0, 2.5),
    ]
    mock_cur2 = MagicMock()
    mock_cur2.fetchall.return_value = [
        ("2024-01-09", 9.8),
        ("2024-01-10", 10.0),
        ("2024-01-11", 10.3),
        ("2024-01-12", 10.8),
    ]

    mock_conn.cursor.side_effect = [mock_cur1, mock_cur2]
    mock_get_conn.return_value = mock_conn

    result = backtest_service.run_prediction_validation("000001")

    pred = result["predictions"][0]
    assert pred["trend"] == "up"
