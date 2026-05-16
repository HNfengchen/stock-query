import numpy as np
import pandas as pd
import pytest

from scripts.core.preprocessing import (
    kalman_filter_denoise,
    ema_adaptive_denoise,
    denoise_data,
)


def _noisy_series(n=200, base=100.0, noise_std=2.0, seed=42):
    rng = np.random.RandomState(seed)
    trend = np.linspace(0, 5, n)
    noise = rng.normal(0, noise_std, n)
    values = base + trend + noise
    return pd.Series(values, name="close")


def _noisy_ohlcv(n=200, base=100.0, noise_std=2.0, seed=42):
    rng = np.random.RandomState(seed)
    trend = np.linspace(0, 5, n)
    base_prices = base + trend
    df = pd.DataFrame({
        "开盘": base_prices + rng.normal(0, noise_std, n) + 0.1,
        "收盘": base_prices + rng.normal(0, noise_std, n),
        "最高": base_prices + rng.normal(0, noise_std, n) + 0.3,
        "最低": base_prices + rng.normal(0, noise_std, n) - 0.3,
        "成交量": rng.randint(1000, 5000, n),
    })
    return df


def _noisy_ohlcv_en(n=200, base=100.0, noise_std=2.0, seed=42):
    rng = np.random.RandomState(seed)
    trend = np.linspace(0, 5, n)
    base_prices = base + trend
    df = pd.DataFrame({
        "open": base_prices + rng.normal(0, noise_std, n) + 0.1,
        "close": base_prices + rng.normal(0, noise_std, n),
        "high": base_prices + rng.normal(0, noise_std, n) + 0.3,
        "low": base_prices + rng.normal(0, noise_std, n) - 0.3,
        "volume": rng.randint(1000, 5000, n),
    })
    return df


class TestKalmanFilterDenoise:
    def test_smooth_output_lower_variance(self):
        s = _noisy_series(n=200, noise_std=2.0)
        smoothed = kalman_filter_denoise(s)
        assert smoothed.var() < s.var()

    def test_preserves_index(self):
        s = _noisy_series(n=50)
        idx = pd.date_range("2024-01-01", periods=50, freq="D")
        s.index = idx
        smoothed = kalman_filter_denoise(s)
        pd.testing.assert_index_equal(smoothed.index, s.index)

    def test_preserves_name(self):
        s = _noisy_series(n=50)
        smoothed = kalman_filter_denoise(s)
        assert smoothed.name == s.name

    def test_first_value_equals_first_observation(self):
        s = _noisy_series(n=50)
        smoothed = kalman_filter_denoise(s)
        assert smoothed.iloc[0] == s.iloc[0]

    def test_nan_handling_skip_observation(self):
        s = _noisy_series(n=50)
        s.iloc[10] = np.nan
        s.iloc[25] = np.nan
        smoothed = kalman_filter_denoise(s)
        assert not smoothed.isna().any()

    def test_leading_nan(self):
        s = pd.Series([np.nan, np.nan, 10.0, 11.0, 12.0, 13.0, 14.0])
        smoothed = kalman_filter_denoise(s)
        assert np.isnan(smoothed.iloc[0])
        assert np.isnan(smoothed.iloc[1])
        assert smoothed.iloc[2] == 10.0

    def test_all_nan_series(self):
        s = pd.Series([np.nan] * 10)
        smoothed = kalman_filter_denoise(s)
        assert smoothed.isna().all()

    def test_single_value(self):
        s = pd.Series([42.0])
        smoothed = kalman_filter_denoise(s)
        assert smoothed.iloc[0] == 42.0

    def test_higher_R_more_smoothing(self):
        s = _noisy_series(n=200, noise_std=3.0)
        smooth_low_R = kalman_filter_denoise(s, R=1e-2)
        smooth_high_R = kalman_filter_denoise(s, R=1.0)
        assert smooth_high_R.var() < smooth_low_R.var()


class TestEmaAdaptiveDenoise:
    def test_smooth_output_lower_variance(self):
        s = _noisy_series(n=200, noise_std=2.0)
        smoothed = ema_adaptive_denoise(s)
        assert smoothed.var() < s.var()

    def test_preserves_index(self):
        s = _noisy_series(n=50)
        idx = pd.date_range("2024-01-01", periods=50, freq="D")
        s.index = idx
        smoothed = ema_adaptive_denoise(s)
        pd.testing.assert_index_equal(smoothed.index, s.index)

    def test_preserves_name(self):
        s = _noisy_series(n=50)
        smoothed = ema_adaptive_denoise(s)
        assert smoothed.name == s.name

    def test_first_value_equals_first_observation(self):
        s = _noisy_series(n=50)
        smoothed = ema_adaptive_denoise(s)
        assert smoothed.iloc[0] == s.iloc[0]

    def test_alpha_varies_with_volatility(self):
        rng = np.random.RandomState(42)
        n = 200
        low_vol = np.random.normal(0, 0.5, n // 2)
        high_vol = np.random.normal(0, 5.0, n // 2)
        returns = np.concatenate([low_vol, high_vol])
        prices = 100 + np.cumsum(returns)
        s = pd.Series(prices)

        smoothed = ema_adaptive_denoise(s, alpha_range=(0.01, 0.5))

        low_vol_diff = (smoothed.iloc[: n // 2] - s.iloc[: n // 2]).abs().mean()
        high_vol_diff = (smoothed.iloc[n // 2 :] - s.iloc[n // 2 :]).abs().mean()
        assert high_vol_diff > low_vol_diff

    def test_nan_handling(self):
        s = _noisy_series(n=50)
        s.iloc[10] = np.nan
        s.iloc[25] = np.nan
        smoothed = ema_adaptive_denoise(s)
        assert not smoothed.isna().any()

    def test_custom_alpha_range(self):
        s = _noisy_series(n=100)
        narrow = ema_adaptive_denoise(s, alpha_range=(0.01, 0.05))
        wide = ema_adaptive_denoise(s, alpha_range=(0.01, 0.5))
        assert narrow.var() < wide.var()

    def test_all_nan_series(self):
        s = pd.Series([np.nan] * 10)
        smoothed = ema_adaptive_denoise(s)
        assert smoothed.isna().all()


class TestDenoiseData:
    def test_kalman_method(self):
        df = _noisy_ohlcv(n=100, noise_std=2.0)
        config = {"preprocessing": {"denoise": {"method": "kalman", "kalman_Q": 1e-5, "kalman_R": 1e-2}}}
        result = denoise_data(df, config)
        assert result["收盘"].var() < df["收盘"].var()

    def test_ema_adaptive_method(self):
        df = _noisy_ohlcv(n=100, noise_std=2.0)
        config = {"preprocessing": {"denoise": {"method": "ema_adaptive", "ema_alpha_range": [0.05, 0.3]}}}
        result = denoise_data(df, config)
        assert result["收盘"].var() < df["收盘"].var()

    def test_none_method_returns_original(self):
        df = _noisy_ohlcv(n=50)
        config = {"preprocessing": {"denoise": {"method": "none"}}}
        result = denoise_data(df, config)
        pd.testing.assert_frame_equal(result, df)

    def test_default_config_returns_original(self):
        df = _noisy_ohlcv(n=50)
        result = denoise_data(df)
        pd.testing.assert_frame_equal(result, df)

    def test_volume_not_modified(self):
        df = _noisy_ohlcv(n=100, noise_std=2.0)
        config = {"preprocessing": {"denoise": {"method": "kalman"}}}
        result = denoise_data(df, config)
        pd.testing.assert_series_equal(result["成交量"], df["成交量"])

    def test_english_column_names(self):
        df = _noisy_ohlcv_en(n=100, noise_std=2.0)
        config = {"preprocessing": {"denoise": {"method": "kalman", "kalman_Q": 1e-5, "kalman_R": 1e-2}}}
        result = denoise_data(df, config)
        assert result["close"].var() < df["close"].var()
        pd.testing.assert_series_equal(result["volume"], df["volume"])

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame()
        result = denoise_data(df)
        assert result.empty

    def test_none_returns_none(self):
        result = denoise_data(None)
        assert result is None

    def test_preserves_shape(self):
        df = _noisy_ohlcv(n=80)
        config = {"preprocessing": {"denoise": {"method": "kalman"}}}
        result = denoise_data(df, config)
        assert result.shape == df.shape
        assert list(result.columns) == list(df.columns)

    def test_all_ohl_columns_denoised(self):
        df = _noisy_ohlcv(n=100, noise_std=2.0)
        config = {"preprocessing": {"denoise": {"method": "kalman"}}}
        result = denoise_data(df, config)
        for col in ["开盘", "收盘", "最高", "最低"]:
            assert result[col].var() < df[col].var(), f"{col} should have lower variance after denoising"


class TestDenoiseConfigIntegration:
    def test_full_config_kalman(self):
        config = {
            "preprocessing": {
                "enabled": True,
                "robust_z_threshold": 3.0,
                "outlier_method": "winsorize",
                "denoise": {
                    "method": "kalman",
                    "kalman_Q": 1e-5,
                    "kalman_R": 1e-2,
                },
            }
        }
        df = _noisy_ohlcv(n=100, noise_std=2.0)
        result = denoise_data(df, config)
        assert result["收盘"].var() < df["收盘"].var()

    def test_full_config_ema_adaptive(self):
        config = {
            "preprocessing": {
                "enabled": True,
                "robust_z_threshold": 3.0,
                "outlier_method": "winsorize",
                "denoise": {
                    "method": "ema_adaptive",
                    "ema_alpha_range": [0.05, 0.3],
                },
            }
        }
        df = _noisy_ohlcv(n=100, noise_std=2.0)
        result = denoise_data(df, config)
        assert result["收盘"].var() < df["收盘"].var()

    def test_pipeline_order_outlier_then_denoise(self):
        from scripts.core.preprocessing import preprocess_data

        config = {
            "preprocessing": {
                "enabled": True,
                "robust_z_threshold": 3.0,
                "outlier_method": "winsorize",
                "denoise": {
                    "method": "kalman",
                    "kalman_Q": 1e-5,
                    "kalman_R": 1e-2,
                },
            }
        }
        df = _noisy_ohlcv(n=100, noise_std=2.0)
        df.iloc[50, df.columns.get_loc("收盘")] = 9999.0

        after_outlier = preprocess_data(df, config)
        assert after_outlier["收盘"].iloc[50] < 9999.0

        after_denoise = denoise_data(after_outlier, config)
        assert after_denoise["收盘"].var() < after_outlier["收盘"].var()

    def test_kalman_custom_params(self):
        df = _noisy_ohlcv(n=100, noise_std=3.0)
        config_low_R = {"preprocessing": {"denoise": {"method": "kalman", "kalman_Q": 1e-5, "kalman_R": 1e-2}}}
        config_high_R = {"preprocessing": {"denoise": {"method": "kalman", "kalman_Q": 1e-5, "kalman_R": 1.0}}}
        result_low_R = denoise_data(df, config_low_R)
        result_high_R = denoise_data(df, config_high_R)
        assert result_high_R["收盘"].var() < result_low_R["收盘"].var()
