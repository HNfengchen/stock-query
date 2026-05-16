import numpy as np
import pandas as pd
import pytest

from scripts.core.stress_test import MonteCarloStressTest
from scripts.core.analyzer import StockAnalyzer
from scripts.technical_indicators import calculate_all_indicators


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


def _make_analyzer(stress_enabled=False, n_simulations=100):
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
        "stress_test": {
            "enabled": stress_enabled,
            "n_simulations": n_simulations,
            "noise_scale": 0.5,
        },
    }
    return StockAnalyzer(config)


def _make_history_df(n=80, seed=42):
    np.random.seed(seed)
    closes = [10.0 + i * 0.05 + np.random.normal(0, 0.1) for i in range(n)]
    return _make_df(closes)


def test_perturb_returns_shape():
    mc = MonteCarloStressTest(n_simulations=10)
    returns = np.array([0.01, -0.02, 0.03, -0.01, 0.02])
    perturbed = mc._perturb_returns(returns, noise_scale=0.5)
    assert perturbed.shape == returns.shape


def test_perturb_returns_adds_noise():
    np.random.seed(42)
    mc = MonteCarloStressTest(n_simulations=10)
    returns = np.array([0.01, -0.02, 0.03, -0.01, 0.02])
    perturbed = mc._perturb_returns(returns, noise_scale=0.5)
    assert not np.allclose(perturbed, returns)


def test_perturb_returns_zero_std():
    mc = MonteCarloStressTest(n_simulations=10)
    returns = np.array([0.01, 0.01, 0.01, 0.01])
    perturbed = mc._perturb_returns(returns, noise_scale=0.5)
    np.testing.assert_array_equal(perturbed, returns)


def test_reconstruct_prices():
    mc = MonteCarloStressTest(n_simulations=10)
    original_close = np.array([100.0, 101.0, 99.5, 102.0])
    returns = np.array([0.01, -0.014851, 0.025126])
    prices = mc._reconstruct_prices(original_close, returns)
    assert len(prices) == len(original_close)
    assert prices[0] == original_close[0]
    assert prices[1] == pytest.approx(100.0 * (1 + 0.01))


def test_reconstruct_prices_consistency():
    mc = MonteCarloStressTest(n_simulations=10)
    original_close = np.array([100.0, 110.0, 105.0, 115.0])
    returns = np.diff(original_close) / original_close[:-1]
    reconstructed = mc._reconstruct_prices(original_close, returns)
    np.testing.assert_allclose(reconstructed, original_close, rtol=1e-10)


def test_compute_max_drawdown_basic():
    mc = MonteCarloStressTest(n_simulations=10)
    prices = np.array([100.0, 110.0, 95.0, 105.0, 90.0, 100.0])
    dd = mc._compute_max_drawdown(prices)
    expected = (110.0 - 90.0) / 110.0
    assert dd == pytest.approx(expected, abs=1e-6)


def test_compute_max_drawdown_no_drawdown():
    mc = MonteCarloStressTest(n_simulations=10)
    prices = np.array([100.0, 110.0, 120.0, 130.0])
    dd = mc._compute_max_drawdown(prices)
    assert dd == 0.0


def test_compute_max_drawdown_single_price():
    mc = MonteCarloStressTest(n_simulations=10)
    prices = np.array([100.0])
    dd = mc._compute_max_drawdown(prices)
    assert dd == 0.0


def test_compute_sharpe():
    mc = MonteCarloStressTest(n_simulations=10)
    returns = np.array([0.01, 0.02, -0.01, 0.03, -0.005])
    sharpe = mc._compute_sharpe(returns)
    expected = np.mean(returns) / np.std(returns)
    assert sharpe == pytest.approx(expected, abs=1e-6)


def test_compute_sharpe_zero_std():
    mc = MonteCarloStressTest(n_simulations=10)
    returns = np.array([0.01, 0.01, 0.01])
    sharpe = mc._compute_sharpe(returns)
    assert sharpe == 0.0


def test_compute_sharpe_empty():
    mc = MonteCarloStressTest(n_simulations=10)
    sharpe = mc._compute_sharpe(np.array([]))
    assert sharpe == 0.0


def test_compute_sortino():
    mc = MonteCarloStressTest(n_simulations=10)
    returns = np.array([0.01, 0.02, -0.01, 0.03, -0.005])
    sortino = mc._compute_sortino(returns)
    negative_returns = returns[returns < 0]
    downside_std = np.std(negative_returns)
    expected = np.mean(returns) / downside_std
    assert sortino == pytest.approx(expected, abs=1e-6)


def test_compute_sortino_no_negative():
    mc = MonteCarloStressTest(n_simulations=10)
    returns = np.array([0.01, 0.02, 0.03, 0.01])
    sortino = mc._compute_sortino(returns)
    assert sortino == float("inf")


def test_compute_sortino_empty():
    mc = MonteCarloStressTest(n_simulations=10)
    sortino = mc._compute_sortino(np.array([]))
    assert sortino == 0.0


def test_compute_calmar():
    mc = MonteCarloStressTest(n_simulations=10)
    returns = np.array([0.001] * 252)
    max_dd = 0.1
    calmar = mc._compute_calmar(returns, max_dd)
    annualized = np.mean(returns) * 252
    expected = annualized / max_dd
    assert calmar == pytest.approx(expected, abs=1e-6)


def test_compute_calmar_zero_drawdown():
    mc = MonteCarloStressTest(n_simulations=10)
    returns = np.array([0.01, 0.02, -0.01])
    calmar = mc._compute_calmar(returns, 0.0)
    assert calmar == 0.0


def test_signal_flipped_buy_to_sell():
    mc = MonteCarloStressTest(n_simulations=10)
    assert mc._signal_flipped("buy", "sell") is True
    assert mc._signal_flipped("strong_buy", "sell") is True
    assert mc._signal_flipped("buy", "watch") is True


def test_signal_flipped_sell_to_buy():
    mc = MonteCarloStressTest(n_simulations=10)
    assert mc._signal_flipped("sell", "buy") is True
    assert mc._signal_flipped("watch", "strong_buy") is True


def test_signal_flipped_hold():
    mc = MonteCarloStressTest(n_simulations=10)
    assert mc._signal_flipped("hold", "buy") is True
    assert mc._signal_flipped("hold", "sell") is True
    assert mc._signal_flipped("buy", "hold") is True
    assert mc._signal_flipped("sell", "hold") is True


def test_signal_not_flipped_same_category():
    mc = MonteCarloStressTest(n_simulations=10)
    assert mc._signal_flipped("buy", "strong_buy") is False
    assert mc._signal_flipped("sell", "watch") is False
    assert mc._signal_flipped("hold", "hold") is False


def test_run_with_synthetic_data():
    np.random.seed(42)
    mc = MonteCarloStressTest(n_simulations=20, config={"noise_scale": 0.5})
    analyzer = _make_analyzer()
    history_df = _make_history_df(n=80)
    indicators = calculate_all_indicators(history_df)

    result = mc.run(analyzer, history_df, indicators)

    assert "signal_flip_rate" in result
    assert "is_robust" in result
    assert "risk_metrics" in result
    assert "original_signal" in result
    assert "simulation_count" in result
    assert result["simulation_count"] == 20
    assert 0 <= result["signal_flip_rate"] <= 1.0
    assert isinstance(result["is_robust"], bool)
    assert "max_drawdown" in result["risk_metrics"]
    assert "sharpe" in result["risk_metrics"]
    assert "sortino" in result["risk_metrics"]
    assert "calmar" in result["risk_metrics"]


def test_robustness_flag():
    np.random.seed(42)
    mc = MonteCarloStressTest(n_simulations=10, config={"noise_scale": 0.01})
    analyzer = _make_analyzer()
    history_df = _make_history_df(n=80)
    indicators = calculate_all_indicators(history_df)

    result = mc.run(analyzer, history_df, indicators)

    assert isinstance(result["is_robust"], bool)
    assert result["is_robust"] == (result["signal_flip_rate"] < 0.3)


def test_empty_result_on_insufficient_data():
    mc = MonteCarloStressTest(n_simulations=10)
    result = mc.run(_make_analyzer(), None, {})
    assert result["signal_flip_rate"] == 0.0
    assert result["is_robust"] is True
    assert result["simulation_count"] == 0

    result = mc.run(_make_analyzer(), pd.DataFrame(), {})
    assert result["simulation_count"] == 0


def test_empty_result_on_short_data():
    mc = MonteCarloStressTest(n_simulations=10)
    df = _make_df([10.0])
    result = mc.run(_make_analyzer(), df, {})
    assert result["simulation_count"] == 0


def test_integration_with_analyzer_stress_disabled():
    analyzer = _make_analyzer(stress_enabled=False)
    history_df = _make_history_df(n=80)
    indicators = calculate_all_indicators(history_df)

    analysis = {
        "technical": analyzer.analyze_technical(indicators, 10.0),
        "fund_flow": analyzer.analyze_fund_flow({}),
        "sentiment": analyzer.analyze_market_sentiment({"stock_info": {}}),
    }
    trading_signal = analyzer.generate_trading_signal(analysis)

    validation = analyzer.cross_validate_analysis(
        analysis,
        {"day1": {"trend": "neutral"}, "day2": {"trend": "neutral"}},
        indicators,
        trading_signal,
        "未持有",
        10.0,
        history_df=history_df,
    )

    assert "stress_test" not in validation


def test_integration_with_analyzer_stress_enabled():
    analyzer = _make_analyzer(stress_enabled=True, n_simulations=10)
    history_df = _make_history_df(n=80)
    indicators = calculate_all_indicators(history_df)

    analysis = {
        "technical": analyzer.analyze_technical(indicators, 10.0),
        "fund_flow": analyzer.analyze_fund_flow({}),
        "sentiment": analyzer.analyze_market_sentiment({"stock_info": {}}),
    }
    trading_signal = analyzer.generate_trading_signal(analysis)

    validation = analyzer.cross_validate_analysis(
        analysis,
        {"day1": {"trend": "neutral"}, "day2": {"trend": "neutral"}},
        indicators,
        trading_signal,
        "未持有",
        10.0,
        history_df=history_df,
    )

    assert "stress_test" in validation
    stress = validation["stress_test"]
    assert "signal_flip_rate" in stress
    assert "is_robust" in stress
    assert "risk_metrics" in stress
    assert "original_signal" in stress
    assert "simulation_count" in stress


def test_high_flip_rate_reduces_confidence():
    np.random.seed(42)
    analyzer = _make_analyzer(stress_enabled=True, n_simulations=10)
    history_df = _make_history_df(n=80)
    indicators = calculate_all_indicators(history_df)

    analysis = {
        "technical": analyzer.analyze_technical(indicators, 10.0),
        "fund_flow": analyzer.analyze_fund_flow({}),
        "sentiment": analyzer.analyze_market_sentiment({"stock_info": {}}),
    }
    trading_signal = analyzer.generate_trading_signal(analysis)

    validation_no_stress = analyzer.cross_validate_analysis(
        analysis,
        {"day1": {"trend": "neutral"}, "day2": {"trend": "neutral"}},
        indicators,
        trading_signal,
        "未持有",
        10.0,
        history_df=None,
    )

    validation_with_stress = analyzer.cross_validate_analysis(
        analysis,
        {"day1": {"trend": "neutral"}, "day2": {"trend": "neutral"}},
        indicators,
        trading_signal,
        "未持有",
        10.0,
        history_df=history_df,
    )

    stress = validation_with_stress.get("stress_test", {})
    if stress.get("signal_flip_rate", 0) > 0.3:
        assert validation_with_stress["confidence"] <= validation_no_stress["confidence"]
        assert "模型鲁棒性不足" in validation_with_stress["conflicts"]
