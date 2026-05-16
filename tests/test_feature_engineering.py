import numpy as np
import pandas as pd

from scripts.core.feature_engineering import (
    extract_feature_vector,
    compute_feature_correlation,
    orthogonalize_features,
    build_feature_series_matrix,
)
from scripts.technical_indicators import calculate_all_indicators
from scripts.core.analyzer import StockAnalyzer


def _make_df(closes, highs=None, lows=None, volumes=None):
    length = len(closes)
    return pd.DataFrame(
        {
            "收盘": closes,
            "最高": highs if highs is not None else [c + 0.5 for c in closes],
            "最低": lows if lows is not None else [c - 0.5 for c in closes],
            "成交量": volumes if volumes is not None else [1000] * length,
        }
    )


def _make_indicators():
    np.random.seed(42)
    closes = [10.0 + i * 0.05 + np.random.normal(0, 0.1) for i in range(80)]
    df = _make_df(closes)
    return calculate_all_indicators(df)


def _analyzer(fe_enabled=False):
    config = {
        "analyzer": {
            "weights": {"technical": 0.5, "fund_flow": 0.3, "sentiment": 0.2},
            "thresholds": {"strong_buy": 0.7, "buy": 0.5, "hold": 0.3},
            "price_prediction": {"atr_multiplier": 1.5},
            "validation": {
                "score_thresholds": {
                    "technical_bullish": 0.65,
                    "technical_bearish": 0.35,
                    "fund_bullish": 0.6,
                    "fund_bearish": 0.4,
                    "sentiment_bullish": 0.6,
                    "sentiment_bearish": 0.4,
                },
                "vote_thresholds": {
                    "bullish_consensus_margin": 3,
                    "bearish_consensus_margin": 2,
                },
                "confidence_weights": {"signal": 0.4, "agreement": 0.6},
                "conflict_penalty": {"per_conflict": 0.1, "max": 0.3},
            },
        },
        "feature_engineering": {
            "enabled": fe_enabled,
            "variance_threshold": 0.95,
            "correlation_threshold": 0.7,
            "method": "pca",
        },
    }
    return StockAnalyzer(config)


def test_correlation_with_known_correlated_data():
    np.random.seed(42)
    n = 100
    x = np.random.randn(n)
    y = x * 0.9 + np.random.randn(n) * 0.1
    z = np.random.randn(n)

    feature_dict = {"x": x, "y": y, "z": z}
    result = compute_feature_correlation(feature_dict)

    assert result["correlation_matrix"].shape == (3, 3)
    assert len(result["feature_names"]) == 3
    assert len(result["high_correlation_pairs"]) >= 1

    pair_names = [(p[0], p[1]) for p in result["high_correlation_pairs"]]
    assert ("x", "y") in pair_names


def test_correlation_with_uncorrelated_data():
    np.random.seed(42)
    n = 1000
    x = np.random.randn(n)
    y = np.random.randn(n)

    feature_dict = {"x": x, "y": y}
    result = compute_feature_correlation(feature_dict)

    assert len(result["high_correlation_pairs"]) == 0


def test_correlation_insufficient_features():
    feature_dict = {"x": np.array([1, 2, 3])}
    result = compute_feature_correlation(feature_dict)

    assert result["correlation_matrix"].size == 0
    assert result["high_correlation_pairs"] == []


def test_pca_reduces_correlation():
    np.random.seed(42)
    n = 100
    x = np.random.randn(n)
    y = x * 0.95 + np.random.randn(n) * 0.05
    z = np.random.randn(n)

    feature_matrix = np.column_stack([x, y, z])
    feature_names = ["x", "y", "z"]

    result = orthogonalize_features(feature_matrix, feature_names, variance_threshold=0.95)

    assert result["n_components"] >= 1
    assert result["orthogonal_features"].shape[1] == result["n_components"]
    assert len(result["orthogonal_feature_names"]) == result["n_components"]
    assert result["orthogonal_feature_names"][0] == "PC1"

    if result["n_components"] >= 2:
        orth = result["orthogonal_features"]
        corr = np.corrcoef(orth.T)
        off_diag = []
        for i in range(corr.shape[0]):
            for j in range(i + 1, corr.shape[1]):
                off_diag.append(abs(corr[i, j]))
        max_corr = max(off_diag) if off_diag else 0
        assert max_corr < 0.1


def test_variance_threshold_selection():
    np.random.seed(42)
    n = 200
    x = np.random.randn(n)
    y = x * 0.9 + np.random.randn(n) * 0.1
    z = np.random.randn(n)
    w = np.random.randn(n)

    feature_matrix = np.column_stack([x, y, z, w])
    feature_names = ["x", "y", "z", "w"]

    result_95 = orthogonalize_features(feature_matrix, feature_names, variance_threshold=0.95)
    result_50 = orthogonalize_features(feature_matrix, feature_names, variance_threshold=0.50)

    assert result_50["n_components"] <= result_95["n_components"]


def test_pca_svd_for_wide_matrix():
    np.random.seed(42)
    n_samples = 5
    n_features = 10

    feature_matrix = np.random.randn(n_samples, n_features)
    feature_names = [f"f{i}" for i in range(n_features)]

    result = orthogonalize_features(feature_matrix, feature_names, variance_threshold=0.95)

    assert result["n_components"] >= 1
    assert result["orthogonal_features"].shape[0] == n_samples
    assert result["orthogonal_features"].shape[1] == result["n_components"]


def test_feature_extraction_from_indicators():
    indicators = _make_indicators()
    names, values = extract_feature_vector(indicators)

    assert len(names) > 0
    assert len(names) == len(values)
    assert all(isinstance(n, str) for n in names)
    assert values.dtype == np.float64


def test_feature_extraction_signal_mapping():
    indicators = {
        "MACD": {"signal": "金叉", "latest": {"DIF": 0.5, "DEA": 0.3, "MACD": 0.4}},
        "RSI": {
            "RSI(12)": {"signal": "超卖", "latest": 25, "cross": "金叉"},
        },
        "KDJ": {"signal": "金叉", "latest": {"K": 60, "D": 40, "J": 100}},
        "BOLL": {"signal": "收窄", "latest": {"bandwidth": 8, "pct_b": 30}},
        "ATR": {"signal": "正常", "latest": 0.5},
    }

    names, values = extract_feature_vector(indicators)

    macd_idx = names.index("MACD_signal")
    assert values[macd_idx] == 0.8

    rsi_signal_idx = names.index("RSI(12)_signal")
    assert values[rsi_signal_idx] == 0.6

    kdj_signal_idx = names.index("KDJ_signal")
    assert values[kdj_signal_idx] == 0.8

    boll_signal_idx = names.index("BOLL_signal")
    assert values[boll_signal_idx] == 0.2


def test_feature_extraction_empty_indicators():
    names, values = extract_feature_vector({})

    assert names == []
    assert len(values) == 0


def test_orthogonalized_features_near_zero_correlation():
    np.random.seed(42)
    n = 200
    base = np.random.randn(n)
    feature_matrix = np.column_stack([
        base,
        base * 0.8 + np.random.randn(n) * 0.2,
        base * 0.6 + np.random.randn(n) * 0.4,
    ])
    feature_names = ["f1", "f2", "f3"]

    result = orthogonalize_features(feature_matrix, feature_names, variance_threshold=0.95)

    orth = result["orthogonal_features"]
    if result["n_components"] >= 2:
        corr = np.corrcoef(orth.T)
        for i in range(corr.shape[0]):
            for j in range(i + 1, corr.shape[1]):
                assert abs(corr[i, j]) < 0.15


def test_insufficient_data_graceful_degradation():
    result = orthogonalize_features(
        np.array([]).reshape(0, 0), [], variance_threshold=0.95
    )
    assert result["n_components"] == 0
    assert result["orthogonal_features"].size == 0

    result = orthogonalize_features(
        np.array([[1.0, 2.0]]), ["a", "b"], variance_threshold=0.95
    )
    assert result["n_components"] >= 0


def test_build_feature_series_matrix():
    indicators1 = _make_indicators()

    np.random.seed(43)
    closes = [10.0 + i * 0.03 + np.random.normal(0, 0.1) for i in range(80)]
    df = _make_df(closes)
    indicators2 = calculate_all_indicators(df)

    matrix, names = build_feature_series_matrix([indicators1, indicators2])

    assert matrix.shape[0] == 2
    assert len(names) > 0
    assert matrix.shape[1] == len(names)


def test_build_feature_series_matrix_empty():
    matrix, names = build_feature_series_matrix([])

    assert matrix.size == 0
    assert names == []


def test_analyzer_with_feature_engineering_enabled():
    indicators = _make_indicators()
    analyzer = _analyzer(fe_enabled=True)

    result = analyzer.analyze_technical(indicators, current_price=10.0)

    assert "score" in result
    assert 0 <= result["score"] <= 1
    assert "feature_correlation" in result
    fc = result["feature_correlation"]
    assert "high_correlation_pairs" in fc
    assert "feature_names" in fc


def test_analyzer_with_feature_engineering_disabled():
    indicators = _make_indicators()
    analyzer = _analyzer(fe_enabled=False)

    result = analyzer.analyze_technical(indicators, current_price=10.0)

    assert "score" in result
    assert "feature_correlation" not in result


def test_analyzer_feature_engineering_no_change_to_return_format():
    indicators = _make_indicators()
    analyzer = _analyzer(fe_enabled=True)

    result = analyzer.analyze_technical(indicators, current_price=10.0)

    assert "score" in result
    assert "details" in result
    assert "signals" in result
    assert "confidence" in result
