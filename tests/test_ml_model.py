import os
import shutil
import tempfile

import numpy as np
import pytest

from scripts.core.ml_model import (
    LightGBMPredictor,
    hybrid_predict,
    _LGB_AVAILABLE,
)


def _make_synthetic_data(n_samples=200, n_features=10):
    np.random.seed(42)
    X = np.random.randn(n_samples, n_features)
    weights = np.random.randn(n_features)
    next_day_return = X @ weights * 0.01 + np.random.randn(n_samples) * 0.005
    direction = (next_day_return > 0).astype(int)
    volatility = np.abs(np.random.randn(n_samples)) * 0.02
    y = {
        "next_day_return": next_day_return,
        "direction": direction,
        "volatility": volatility,
    }
    return X, y


@pytest.mark.skipif(not _LGB_AVAILABLE, reason="lightgbm not installed")
def test_train_and_predict():
    X, y = _make_synthetic_data()
    predictor = LightGBMPredictor()
    predictor._feature_names = [f"f{i}" for i in range(X.shape[1])]

    metrics = predictor.train(X, y)

    assert "error" not in metrics
    assert "return_train_loss" in metrics
    assert "return_val_loss" in metrics
    assert "direction_train_acc" in metrics
    assert "direction_val_acc" in metrics
    assert "volatility_train_loss" in metrics
    assert "volatility_val_loss" in metrics
    assert metrics["n_samples"] == 200
    assert metrics["n_features"] == 10

    assert predictor.is_ready()

    result = predictor.predict(X[-1:].reshape(1, -1))
    assert "next_day_return" in result
    assert "direction" in result
    assert "volatility" in result
    assert "confidence" in result
    assert result["direction"] in (0, 1)
    assert 0 <= result["confidence"] <= 1


@pytest.mark.skipif(not _LGB_AVAILABLE, reason="lightgbm not installed")
def test_train_insufficient_data():
    X = np.random.randn(30, 5)
    y = {
        "next_day_return": np.random.randn(30),
        "direction": np.random.randint(0, 2, 30),
        "volatility": np.abs(np.random.randn(30)) * 0.02,
    }
    predictor = LightGBMPredictor()
    metrics = predictor.train(X, y)
    assert "error" in metrics
    assert not predictor.is_ready()


@pytest.mark.skipif(not _LGB_AVAILABLE, reason="lightgbm not installed")
def test_model_save_load_roundtrip():
    X, y = _make_synthetic_data()
    predictor = LightGBMPredictor()
    predictor._feature_names = [f"f{i}" for i in range(X.shape[1])]
    predictor.train(X, y)

    pred_before = predictor.predict(X[-1:].reshape(1, -1))

    tmpdir = tempfile.mkdtemp()
    try:
        model_dir = predictor.save(tmpdir)

        assert os.path.exists(os.path.join(tmpdir, "return_model.txt"))
        assert os.path.exists(os.path.join(tmpdir, "direction_model.txt"))
        assert os.path.exists(os.path.join(tmpdir, "volatility_model.txt"))
        assert os.path.exists(os.path.join(tmpdir, "meta.joblib"))
        assert os.path.exists(os.path.join(tmpdir, "return_model.joblib"))
        assert os.path.exists(os.path.join(tmpdir, "direction_model.joblib"))
        assert os.path.exists(os.path.join(tmpdir, "volatility_model.joblib"))

        predictor2 = LightGBMPredictor()
        loaded = predictor2.load(tmpdir)
        assert loaded
        assert predictor2.is_ready()

        pred_after = predictor2.predict(X[-1:].reshape(1, -1))
        assert abs(pred_before["next_day_return"] - pred_after["next_day_return"]) < 1e-4
        assert pred_before["direction"] == pred_after["direction"]
    finally:
        shutil.rmtree(tmpdir)


@pytest.mark.skipif(not _LGB_AVAILABLE, reason="lightgbm not installed")
def test_get_feature_importance():
    X, y = _make_synthetic_data()
    predictor = LightGBMPredictor()
    predictor._feature_names = [f"f{i}" for i in range(X.shape[1])]
    predictor.train(X, y)

    importance = predictor.get_feature_importance()
    assert "return" in importance
    assert "direction" in importance
    assert "volatility" in importance
    assert len(importance["return"]) == X.shape[1]


def test_predictor_not_ready_without_lgb():
    predictor = LightGBMPredictor()
    if not _LGB_AVAILABLE:
        assert not predictor.is_ready()
        result = predictor.predict(np.array([[1.0, 2.0]]))
        assert result == {}


def test_hybrid_predict_both_directions_agree():
    rule_prediction = {
        "current": 10.0,
        "target_low": 9.5,
        "target_high": 10.5,
        "trend": "up",
        "validation_confidence": 0.7,
        "limit_pct": 0.10,
        "day1": {"target_low": 9.8, "target_high": 10.3},
        "day2": {"target_low": 9.5, "target_high": 10.5},
    }
    ml_prediction = {
        "next_day_return": 0.02,
        "direction": 1,
        "volatility": 0.015,
        "confidence": 0.8,
    }

    result = hybrid_predict(rule_prediction, ml_prediction, alpha=0.5)

    assert "target_low" in result
    assert "target_high" in result
    assert result["direction"] == 1
    assert result["hybrid_alpha"] == 0.5
    assert result["ml_prediction"] == ml_prediction

    assert result["target_low"] >= 10.0 * (1 - 0.10)
    assert result["target_high"] <= 10.0 * (1 + 0.10)


def test_hybrid_predict_directions_disagree():
    rule_prediction = {
        "current": 10.0,
        "target_low": 9.5,
        "target_high": 10.5,
        "trend": "up",
        "validation_confidence": 0.7,
        "limit_pct": 0.10,
    }
    ml_prediction = {
        "next_day_return": -0.02,
        "direction": 0,
        "volatility": 0.015,
        "confidence": 0.6,
    }

    result = hybrid_predict(rule_prediction, ml_prediction, alpha=0.5)

    assert result["confidence"] < max(0.7, 0.6)


def test_hybrid_predict_no_ml_prediction():
    rule_prediction = {
        "current": 10.0,
        "target_low": 9.5,
        "target_high": 10.5,
        "trend": "up",
    }
    result = hybrid_predict(rule_prediction, {}, alpha=0.5)
    assert result["target_low"] == 9.5
    assert result["target_high"] == 10.5


def test_hybrid_predict_no_rule_prediction():
    ml_prediction = {
        "next_day_return": 0.02,
        "direction": 1,
        "volatility": 0.015,
        "confidence": 0.8,
    }
    result = hybrid_predict({}, ml_prediction, alpha=0.5)
    assert result == ml_prediction


def test_hybrid_predict_feasibility_constraints():
    rule_prediction = {
        "current": 10.0,
        "target_low": 9.5,
        "target_high": 10.5,
        "trend": "up",
        "validation_confidence": 0.7,
        "limit_pct": 0.10,
    }
    ml_prediction = {
        "next_day_return": 0.15,
        "direction": 1,
        "volatility": 0.05,
        "confidence": 0.9,
    }

    result = hybrid_predict(rule_prediction, ml_prediction, alpha=0.3)

    limit_up = 10.0 * (1 + 0.10)
    limit_down = 10.0 * (1 - 0.10)
    assert result["target_high"] <= limit_up
    assert result["target_low"] >= limit_down


def test_hybrid_predict_alpha_control():
    rule_prediction = {
        "current": 10.0,
        "target_low": 9.0,
        "target_high": 11.0,
        "trend": "up",
        "validation_confidence": 0.7,
        "limit_pct": 0.20,
    }
    ml_prediction = {
        "next_day_return": 0.05,
        "direction": 1,
        "volatility": 0.02,
        "confidence": 0.8,
    }

    result_alpha1 = hybrid_predict(rule_prediction, ml_prediction, alpha=1.0)
    result_alpha0 = hybrid_predict(rule_prediction, ml_prediction, alpha=0.0)

    assert abs(result_alpha1["target_low"] - 9.0) < 0.01
    assert abs(result_alpha1["target_high"] - 11.0) < 0.01

    assert result_alpha0["target_low"] != 9.0
    assert result_alpha0["target_high"] != 11.0


def test_graceful_degradation_no_model():
    config = {"ml_model": {"enabled": False}}
    predictor = LightGBMPredictor(config)
    assert not predictor.is_ready()

    result = predictor.predict(np.array([[1.0, 2.0, 3.0]]))
    assert result == {}


def test_build_feature_matrix_with_mock_data():
    import pandas as pd
    from unittest.mock import MagicMock

    from scripts.core.ml_model import build_feature_matrix

    np.random.seed(42)
    n = 80
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    closes = [10.0 + i * 0.05 + np.random.normal(0, 0.1) for i in range(n)]
    highs = [c + 0.3 for c in closes]
    lows = [c - 0.3 for c in closes]
    volumes = [100000] * n

    df = pd.DataFrame({
        "日期": dates,
        "收盘": closes,
        "最高": highs,
        "最低": lows,
        "成交量": volumes,
    })

    mock_db = MagicMock()
    mock_db.get_historical_data.return_value = df

    X, y, feature_names, dates_result = build_feature_matrix(mock_db, "000001")

    if X.size > 0:
        assert X.shape[0] == n
        assert len(feature_names) > 0
        assert "next_day_return" in y
        assert "direction" in y
        assert "volatility" in y
        assert len(y["next_day_return"]) == n
        assert len(y["direction"]) == n
        assert len(y["volatility"]) == n
    else:
        assert feature_names == []


def test_build_feature_matrix_insufficient_data():
    import pandas as pd
    from unittest.mock import MagicMock

    from scripts.core.ml_model import build_feature_matrix

    df = pd.DataFrame({
        "日期": pd.date_range("2024-01-01", periods=30, freq="D"),
        "收盘": [10.0] * 30,
        "最高": [10.5] * 30,
        "最低": [9.5] * 30,
        "成交量": [1000] * 30,
    })

    mock_db = MagicMock()
    mock_db.get_historical_data.return_value = df

    X, y, feature_names, dates = build_feature_matrix(mock_db, "000001")
    assert X.size == 0


def test_build_feature_matrix_empty_data():
    from unittest.mock import MagicMock

    from scripts.core.ml_model import build_feature_matrix

    mock_db = MagicMock()
    mock_db.get_historical_data.return_value = None

    X, y, feature_names, dates = build_feature_matrix(mock_db, "000001")
    assert X.size == 0
