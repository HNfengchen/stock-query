import numpy as np
import pandas as pd
import pytest
from scripts.technical_indicators import (
    calculate_historical_volatility,
    calculate_parkinson_volatility,
    calculate_garman_klass_volatility,
    calculate_realized_volatility,
    calculate_all_indicators,
)


def _make_df(n=120, seed=42):
    rng = np.random.RandomState(seed)
    base = 100.0
    closes = [base]
    for _ in range(n - 1):
        ret = rng.normal(0, 0.02)
        closes.append(closes[-1] * (1 + ret))
    closes = np.array(closes)
    highs = closes * (1 + rng.uniform(0, 0.03, n))
    lows = closes * (1 - rng.uniform(0, 0.03, n))
    opens = closes * (1 + rng.uniform(-0.01, 0.01, n))
    volumes = rng.randint(100000, 500000, n)
    return pd.DataFrame({
        "收盘": closes,
        "最高": highs,
        "最低": lows,
        "开盘": opens,
        "成交量": volumes,
    })


def _make_df_english(n=120, seed=42):
    rng = np.random.RandomState(seed)
    base = 100.0
    closes = [base]
    for _ in range(n - 1):
        ret = rng.normal(0, 0.02)
        closes.append(closes[-1] * (1 + ret))
    closes = np.array(closes)
    highs = closes * (1 + rng.uniform(0, 0.03, n))
    lows = closes * (1 - rng.uniform(0, 0.03, n))
    opens = closes * (1 + rng.uniform(-0.01, 0.01, n))
    volumes = rng.randint(100000, 500000, n)
    return pd.DataFrame({
        "close": closes,
        "high": highs,
        "low": lows,
        "open": opens,
        "volume": volumes,
    })


class TestHistoricalVolatility:
    def test_basic_calculation(self):
        df = _make_df(120)
        result = calculate_historical_volatility(df)
        assert "HV20" in result
        assert "HV60" in result
        assert result["HV20"]["latest"] is not None
        assert result["HV60"]["latest"] is not None
        assert result["HV20"]["latest"] > 0
        assert result["HV60"]["latest"] > 0

    def test_annualization_factor(self):
        df = _make_df(120)
        result = calculate_historical_volatility(df, windows=[20])
        closes = df["收盘"].values.astype(float)
        log_returns = np.log(closes[1:] / closes[:-1])
        manual_std = np.std(log_returns[-20:], ddof=1)
        manual_hv = manual_std * np.sqrt(252)
        assert abs(result["HV20"]["latest"] - round(manual_hv, 6)) < 1e-4

    def test_signal_values(self):
        df = _make_df(120)
        result = calculate_historical_volatility(df)
        assert result["HV20"]["signal"] in ("低波动", "正常", "高波动")
        assert result["HV60"]["signal"] in ("低波动", "正常", "高波动")

    def test_series_length(self):
        df = _make_df(120)
        result = calculate_historical_volatility(df)
        assert len(result["HV20"]["series"]) > 0
        assert len(result["HV60"]["series"]) > 0

    def test_insufficient_data(self):
        df = _make_df(10)
        result = calculate_historical_volatility(df)
        assert result["HV20"]["latest"] is None
        assert result["HV20"]["signal"] == "数据不足"

    def test_state_key(self):
        df = _make_df(120)
        result = calculate_historical_volatility(df)
        assert "state" in result
        assert "prev_hv_20" in result["state"]
        assert "prev_hv_60" in result["state"]

    def test_custom_windows(self):
        df = _make_df(120)
        result = calculate_historical_volatility(df, windows=[10, 30])
        assert "HV10" in result
        assert "HV30" in result

    def test_english_columns(self):
        df = _make_df_english(120)
        result = calculate_historical_volatility(df)
        assert result["HV20"]["latest"] is not None

    def test_missing_close_column(self):
        df = pd.DataFrame({"high": [100, 101], "low": [99, 100]})
        result = calculate_historical_volatility(df)
        assert result["HV20"]["latest"] is None


class TestParkinsonVolatility:
    def test_basic_calculation(self):
        df = _make_df(120)
        result = calculate_parkinson_volatility(df)
        assert "Parkinson" in result
        assert result["Parkinson"]["latest"] is not None
        assert result["Parkinson"]["latest"] > 0

    def test_parkinson_less_than_hv(self):
        df = _make_df(200, seed=123)
        hv = calculate_historical_volatility(df)
        pv = calculate_parkinson_volatility(df)
        assert pv["Parkinson"]["latest"] < hv["HV20"]["latest"]

    def test_annualization(self):
        df = _make_df(120)
        result = calculate_parkinson_volatility(df)
        assert result["Parkinson"]["latest"] > 0
        assert result["Parkinson"]["latest"] < 5.0

    def test_signal_values(self):
        df = _make_df(120)
        result = calculate_parkinson_volatility(df)
        assert result["Parkinson"]["signal"] in ("低波动", "正常", "高波动")

    def test_state_key(self):
        df = _make_df(120)
        result = calculate_parkinson_volatility(df)
        assert "state" in result["Parkinson"]
        assert "prev_parkinson" in result["Parkinson"]["state"]

    def test_insufficient_data(self):
        df = _make_df(10)
        result = calculate_parkinson_volatility(df)
        assert result["Parkinson"]["latest"] is None
        assert result["Parkinson"]["signal"] == "数据不足"

    def test_known_values(self):
        n = 30
        highs = np.full(n, 105.0)
        lows = np.full(n, 100.0)
        closes = np.full(n, 102.5)
        df = pd.DataFrame({"最高": highs, "最低": lows, "收盘": closes})
        result = calculate_parkinson_volatility(df, window=20)
        assert result["Parkinson"]["latest"] is not None
        hl_log = np.log(105.0 / 100.0)
        factor = 1.0 / (4.0 * np.log(2))
        expected = np.sqrt(factor * hl_log ** 2) * np.sqrt(252)
        assert abs(result["Parkinson"]["latest"] - round(expected, 6)) < 1e-4


class TestGarmanKlassVolatility:
    def test_basic_calculation(self):
        df = _make_df(120)
        result = calculate_garman_klass_volatility(df)
        assert "GarmanKlass" in result
        assert result["GarmanKlass"]["latest"] is not None
        assert result["GarmanKlass"]["latest"] > 0

    def test_gk_less_than_hv(self):
        df = _make_df(200, seed=456)
        hv = calculate_historical_volatility(df)
        gk = calculate_garman_klass_volatility(df)
        assert gk["GarmanKlass"]["latest"] is not None
        assert hv["HV20"]["latest"] is not None

    def test_signal_values(self):
        df = _make_df(120)
        result = calculate_garman_klass_volatility(df)
        assert result["GarmanKlass"]["signal"] in ("低波动", "正常", "高波动")

    def test_state_key(self):
        df = _make_df(120)
        result = calculate_garman_klass_volatility(df)
        assert "state" in result["GarmanKlass"]
        assert "prev_garman_klass" in result["GarmanKlass"]["state"]

    def test_insufficient_data(self):
        df = _make_df(10)
        result = calculate_garman_klass_volatility(df)
        assert result["GarmanKlass"]["latest"] is None
        assert result["GarmanKlass"]["signal"] == "数据不足"

    def test_missing_open_column(self):
        df = _make_df(120).drop(columns=["开盘"])
        result = calculate_garman_klass_volatility(df)
        assert result["GarmanKlass"]["latest"] is None

    def test_english_columns(self):
        df = _make_df_english(120)
        result = calculate_garman_klass_volatility(df)
        assert result["GarmanKlass"]["latest"] is not None


class TestRealizedVolatility:
    def test_fallback_to_parkinson(self):
        df = _make_df(120)
        result = calculate_realized_volatility(df, minute_df=None)
        assert "RealizedVol" in result
        assert result["RealizedVol"]["latest"] is not None

    def test_with_minute_data(self):
        df = _make_df(120)
        rng = np.random.RandomState(99)
        n_days = 25
        n_minutes = 240 * n_days
        m_closes = [100.0]
        for _ in range(n_minutes - 1):
            ret = rng.normal(0, 0.001)
            m_closes.append(m_closes[-1] * (1 + ret))
        dates = []
        for d in range(n_days):
            dates.extend([f"2025-01-{d+1:02d}"] * 240)
        minute_df = pd.DataFrame({
            "收盘": m_closes,
            "日期": dates,
        })
        result = calculate_realized_volatility(df, minute_df=minute_df, window=5)
        assert "RealizedVol" in result
        assert result["RealizedVol"]["latest"] is not None
        assert result["RealizedVol"]["latest"] > 0

    def test_signal_values(self):
        df = _make_df(120)
        result = calculate_realized_volatility(df)
        assert result["RealizedVol"]["signal"] in ("低波动", "正常", "高波动")

    def test_state_key(self):
        df = _make_df(120)
        result = calculate_realized_volatility(df)
        assert "state" in result["RealizedVol"]

    def test_empty_minute_df_fallback(self):
        df = _make_df(120)
        result = calculate_realized_volatility(df, minute_df=pd.DataFrame())
        assert "RealizedVol" in result
        assert result["RealizedVol"]["latest"] is not None


class TestVolatilitySignalClassification:
    def test_low_volatility_signal(self):
        n = 120
        closes = np.linspace(100, 100.5, n)
        highs = closes + 0.01
        lows = closes - 0.01
        df = pd.DataFrame({"收盘": closes, "最高": highs, "最低": lows, "开盘": closes})
        result = calculate_historical_volatility(df)
        assert result["HV20"]["signal"] in ("低波动", "正常", "高波动")

    def test_high_volatility_signal(self):
        n = 120
        rng = np.random.RandomState(77)
        closes = [100.0]
        for _ in range(n - 1):
            ret = rng.normal(0, 0.08)
            closes.append(closes[-1] * (1 + ret))
        closes = np.array(closes)
        highs = closes * 1.05
        lows = closes * 0.95
        df = pd.DataFrame({"收盘": closes, "最高": highs, "最低": lows, "开盘": closes})
        result = calculate_historical_volatility(df)
        assert result["HV20"]["signal"] in ("低波动", "正常", "高波动")


class TestIntegrationWithCalculateAllIndicators:
    def test_volatility_in_result(self):
        df = _make_df(120)
        result = calculate_all_indicators(df)
        assert "Volatility" in result
        vol = result["Volatility"]
        assert "HV20" in vol
        assert "HV60" in vol
        assert "Parkinson" in vol
        assert "GarmanKlass" in vol
        assert "RealizedVol" in vol

    def test_volatility_values_not_none(self):
        df = _make_df(120)
        result = calculate_all_indicators(df)
        vol = result["Volatility"]
        assert vol["HV20"]["latest"] is not None
        assert vol["HV60"]["latest"] is not None
        assert vol["Parkinson"]["latest"] is not None
        assert vol["GarmanKlass"]["latest"] is not None
        assert vol["RealizedVol"]["latest"] is not None

    def test_minute_df_passed_through(self):
        df = _make_df(120)
        rng = np.random.RandomState(88)
        n_days = 25
        n_minutes = 240 * n_days
        m_closes = [100.0]
        for _ in range(n_minutes - 1):
            ret = rng.normal(0, 0.001)
            m_closes.append(m_closes[-1] * (1 + ret))
        dates = []
        for d in range(n_days):
            dates.extend([f"2025-01-{d+1:02d}"] * 240)
        minute_df = pd.DataFrame({"收盘": m_closes, "日期": dates})
        result = calculate_all_indicators(df, minute_df=minute_df)
        assert "Volatility" in result
        assert result["Volatility"]["RealizedVol"]["latest"] is not None

    def test_other_indicators_still_work(self):
        df = _make_df(120)
        result = calculate_all_indicators(df)
        assert "MACD" in result
        assert "RSI" in result
        assert "KDJ" in result
        assert "MA" in result
        assert "BOLL" in result
        assert "ATR" in result


class TestAnnualizationFactor:
    def test_hv_annualization(self):
        df = _make_df(120)
        result = calculate_historical_volatility(df, windows=[20])
        closes = df["收盘"].values.astype(float)
        log_returns = np.log(closes[1:] / closes[:-1])
        daily_std = np.std(log_returns[-20:], ddof=1)
        annualized = daily_std * np.sqrt(252)
        assert abs(result["HV20"]["latest"] - round(annualized, 6)) < 1e-4

    def test_parkinson_annualization(self):
        n = 30
        highs = np.full(n, 110.0)
        lows = np.full(n, 100.0)
        closes = np.full(n, 105.0)
        df = pd.DataFrame({"最高": highs, "最低": lows, "收盘": closes})
        result = calculate_parkinson_volatility(df, window=20)
        hl_log = np.log(110.0 / 100.0)
        factor = 1.0 / (4.0 * np.log(2))
        expected = np.sqrt(factor * hl_log ** 2) * np.sqrt(252)
        assert abs(result["Parkinson"]["latest"] - round(expected, 6)) < 1e-4
