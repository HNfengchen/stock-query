import numpy as np
import pandas as pd

from scripts.technical_indicators import (
    calculate_distribution_features,
    calculate_all_indicators,
)
from scripts.core.analyzer import StockAnalyzer


def _make_df(closes, highs=None, lows=None, volumes=None):
    length = len(closes)
    return pd.DataFrame(
        {
            "收盘": closes,
            "最高": highs if highs is not None else [c + 0.2 for c in closes],
            "最低": lows if lows is not None else [c - 0.2 for c in closes],
            "成交量": volumes if volumes is not None else [1000] * length,
        }
    )


def _analyzer():
    return StockAnalyzer(
        {
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
            }
        }
    )


def test_skewness_left_skewed():
    np.random.seed(42)
    data = np.random.exponential(scale=1.0, size=200)
    prices = 100 + np.cumsum(data * 0.1)
    closes = prices.tolist()
    df = _make_df(closes)

    result = calculate_distribution_features(df, windows=[20])
    w20 = result["Distribution"]["W20"]
    skewness = w20["skewness"]["latest"]
    signal = w20["skewness"]["signal"]

    assert skewness is not None
    assert signal in ("右偏", "对称", "左偏")


def test_skewness_right_skewed():
    np.random.seed(42)
    data = -np.random.exponential(scale=1.0, size=200)
    prices = 100 + np.cumsum(data * 0.1)
    closes = prices.tolist()
    df = _make_df(closes)

    result = calculate_distribution_features(df, windows=[20])
    w20 = result["Distribution"]["W20"]
    skewness = w20["skewness"]["latest"]
    signal = w20["skewness"]["signal"]

    assert skewness is not None
    assert signal in ("左偏", "右偏", "对称")


def test_skewness_symmetric():
    np.random.seed(123)
    data = np.random.normal(loc=0, scale=1.0, size=5000)
    prices = 100 + np.cumsum(data * 0.001)
    closes = prices.tolist()
    df = _make_df(closes)

    result = calculate_distribution_features(df, windows=[60])
    w60 = result["Distribution"]["W60"]
    skewness = w60["skewness"]["latest"]
    signal = w60["skewness"]["signal"]

    assert skewness is not None
    assert abs(skewness) < 0.5
    assert signal == "对称"


def test_kurtosis_normal_distribution():
    np.random.seed(42)
    data = np.random.normal(loc=0, scale=1.0, size=10000)
    prices = 100 + np.cumsum(data * 0.001)
    closes = prices.tolist()
    df = _make_df(closes)

    result = calculate_distribution_features(df, windows=[60])
    w60 = result["Distribution"]["W60"]
    kurtosis = w60["kurtosis"]["latest"]
    signal = w60["kurtosis"]["signal"]

    assert kurtosis is not None
    assert abs(kurtosis) < 1.0
    assert signal == "正常"


def test_var_cvar_with_known_data():
    returns = np.array([-0.05, -0.04, -0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04] * 10)
    prices = 100 * np.exp(np.cumsum(returns))
    closes = prices.tolist()
    df = _make_df(closes)

    result = calculate_distribution_features(df, windows=[50])
    w50 = result["Distribution"]["W50"]

    var_95 = w50["var_95"]["latest"]
    var_99 = w50["var_99"]["latest"]
    cvar_95 = w50["cvar_95"]["latest"]
    cvar_99 = w50["cvar_99"]["latest"]

    assert var_95 is not None
    assert var_99 is not None
    assert cvar_95 is not None
    assert cvar_99 is not None

    assert var_99 <= var_95
    assert cvar_95 <= var_95
    assert cvar_99 <= var_99


def test_signal_classification():
    np.random.seed(42)
    heavy_tail_data = np.concatenate([
        np.random.normal(0, 1, 80),
        np.random.normal(0, 10, 20),
    ])
    prices = 100 + np.cumsum(heavy_tail_data * 0.1)
    closes = prices.tolist()
    df = _make_df(closes)

    result = calculate_distribution_features(df, windows=[20])
    w20 = result["Distribution"]["W20"]

    assert w20["skewness"]["signal"] in ("左偏", "右偏", "对称")
    assert w20["kurtosis"]["signal"] in ("厚尾", "轻尾", "正常")


def test_insufficient_data():
    closes = [10.0, 11.0]
    df = _make_df(closes)

    result = calculate_distribution_features(df, windows=[20])

    assert "W20" in result["Distribution"]
    w20 = result["Distribution"]["W20"]
    assert w20["skewness"]["latest"] is None
    assert w20["skewness"]["signal"] == "数据不足"


def test_integration_with_calculate_all_indicators():
    np.random.seed(42)
    closes = [10.0 + i * 0.01 for i in range(80)]
    df = _make_df(closes)

    result = calculate_all_indicators(df)

    assert "Distribution" in result
    dist = result["Distribution"]
    assert "W20" in dist
    assert "W60" in dist


def test_analyzer_skewness_reduces_buy_weight():
    analyzer = _analyzer()

    analysis = {
        "technical": {"score": 0.72},
        "fund_flow": {"score": 0.75, "trend": "inflow"},
        "sentiment": {"score": 0.6},
    }
    price_prediction = {
        "day1": {"trend": "up"},
        "day2": {"trend": "up"},
    }
    indicators_no_dist = {
        "MACD": {"signal": "多头"},
        "RSI": {"RSI(12)": {"latest": 55, "signal": "正常"}},
        "KDJ": {"signal": "金叉"},
        "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
    }
    indicators_with_dist = dict(indicators_no_dist)
    indicators_with_dist["Distribution"] = {
        "W20": {
            "skewness": {"latest": -0.8, "signal": "左偏"},
            "kurtosis": {"latest": 1.0, "signal": "正常"},
            "var_95": {"latest": -0.02},
            "var_99": {"latest": -0.03},
            "cvar_95": {"latest": -0.025},
            "cvar_99": {"latest": -0.035},
        },
        "W60": {
            "skewness": {"latest": -0.7, "signal": "左偏"},
            "kurtosis": {"latest": 0.5, "signal": "正常"},
            "var_95": {"latest": -0.018},
            "var_99": {"latest": -0.028},
            "cvar_95": {"latest": -0.023},
            "cvar_99": {"latest": -0.033},
        },
    }

    validation_normal = analyzer.cross_validate_analysis(
        analysis,
        price_prediction,
        indicators_no_dist,
        trading_signal={"signal": "strong_buy", "score": 0.76},
        position_status="未持有",
        current_price=10.0,
    )

    validation_skewed = analyzer.cross_validate_analysis(
        analysis,
        price_prediction,
        indicators_with_dist,
        trading_signal={"signal": "strong_buy", "score": 0.76},
        position_status="未持有",
        current_price=10.0,
    )

    assert validation_skewed["confidence"] < validation_normal["confidence"]
    assert "收益率左偏分布" in validation_skewed["opposing_factors"]


def test_analyzer_kurtosis_elevates_risk_level():
    analyzer = _analyzer()

    analysis = {
        "technical": {"score": 0.72},
        "fund_flow": {"score": 0.75, "trend": "inflow"},
        "sentiment": {"score": 0.6},
    }
    price_prediction = {
        "day1": {"trend": "up"},
        "day2": {"trend": "up"},
    }
    indicators_with_heavy_tail = {
        "MACD": {"signal": "多头"},
        "RSI": {"RSI(12)": {"latest": 55, "signal": "正常"}},
        "KDJ": {"signal": "金叉"},
        "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
        "Distribution": {
            "W20": {
                "skewness": {"latest": 0.1, "signal": "对称"},
                "kurtosis": {"latest": 6.0, "signal": "厚尾"},
                "var_95": {"latest": -0.02},
                "var_99": {"latest": -0.03},
                "cvar_95": {"latest": -0.025},
                "cvar_99": {"latest": -0.035},
            },
            "W60": {
                "skewness": {"latest": 0.1, "signal": "对称"},
                "kurtosis": {"latest": 5.5, "signal": "厚尾"},
                "var_95": {"latest": -0.018},
                "var_99": {"latest": -0.028},
                "cvar_95": {"latest": -0.023},
                "cvar_99": {"latest": -0.033},
            },
        },
    }

    validation = analyzer.cross_validate_analysis(
        analysis,
        price_prediction,
        indicators_with_heavy_tail,
        trading_signal={"signal": "strong_buy", "score": 0.76},
        position_status="未持有",
        current_price=10.0,
    )

    assert "尾部风险显著" in validation["conflicts"]
    risk_order = {"low": 0, "medium": 1, "high": 2}
    assert risk_order.get(validation["risk_level"], 0) >= 1


def test_buy_strategy_halves_position_on_left_skew():
    analyzer = _analyzer()

    indicators_normal = {
        "MACD": {"signal": "金叉"},
        "RSI": {"RSI(12)": {"latest": 50}},
        "KDJ": {"signal": "正常"},
        "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
        "ATR": {"latest": 0.2},
    }

    indicators_skewed = dict(indicators_normal)
    indicators_skewed["Distribution"] = {
        "W20": {
            "skewness": {"latest": -0.8, "signal": "左偏"},
            "kurtosis": {"latest": 1.0, "signal": "正常"},
            "var_95": {"latest": -0.02},
            "var_99": {"latest": -0.03},
            "cvar_95": {"latest": -0.025},
            "cvar_99": {"latest": -0.035},
        },
        "W60": {
            "skewness": {"latest": -0.7, "signal": "左偏"},
            "kurtosis": {"latest": 0.5, "signal": "正常"},
            "var_95": {"latest": -0.018},
            "var_99": {"latest": -0.028},
            "cvar_95": {"latest": -0.023},
            "cvar_99": {"latest": -0.033},
        },
    }

    strategy_normal = analyzer.generate_buy_strategy(
        {"technical_analysis": {"score": 0.5}},
        indicators_normal,
        current_price=10.0,
        trading_signal={"signal": "buy", "score": 0.55},
    )

    strategy_skewed = analyzer.generate_buy_strategy(
        {"technical_analysis": {"score": 0.5}},
        indicators_skewed,
        current_price=10.0,
        trading_signal={"signal": "buy", "score": 0.55},
    )

    assert strategy_skewed["position_size_pct"] < strategy_normal["position_size_pct"]


def test_distribution_features_returns_state():
    np.random.seed(42)
    closes = [10.0 + i * 0.01 for i in range(80)]
    df = _make_df(closes)

    result = calculate_distribution_features(df, windows=[20, 60])

    assert "state" in result
    state = result["state"]
    assert "windows" in state
    assert state["windows"] == [20, 60]
    assert "window_states" in state
    assert "W20" in state["window_states"]
    assert "W60" in state["window_states"]


def test_distribution_features_custom_windows():
    np.random.seed(42)
    closes = [10.0 + i * 0.01 for i in range(80)]
    df = _make_df(closes)

    result = calculate_distribution_features(df, windows=[10, 30])

    assert "W10" in result["Distribution"]
    assert "W30" in result["Distribution"]
    assert "W20" not in result["Distribution"]


def test_distribution_features_no_close_column():
    df = pd.DataFrame({"open": [10, 11, 12]})

    result = calculate_distribution_features(df)

    assert result["Distribution"] == {}
