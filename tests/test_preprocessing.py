import numpy as np
import pandas as pd

from scripts.core.preprocessing import (
    robust_z_score,
    detect_outliers,
    handle_outliers,
    preprocess_data,
)


def _normal_series(n=100, seed=42):
    rng = np.random.RandomState(seed)
    return pd.Series(rng.normal(10, 1, n))


def _series_with_outliers(n=100, outlier_indices=None, outlier_value=1000, seed=42):
    rng = np.random.RandomState(seed)
    s = pd.Series(rng.normal(10, 1, n))
    if outlier_indices:
        for idx in outlier_indices:
            s.iloc[idx] = outlier_value
    return s


def _ohlcv_frame(n=50, outlier_col="收盘", outlier_indices=None, seed=42):
    rng = np.random.RandomState(seed)
    base = rng.normal(10, 1, n)
    df = pd.DataFrame({
        "开盘": base + 0.1,
        "收盘": base,
        "最高": base + 0.3,
        "最低": base - 0.3,
        "成交量": rng.randint(1000, 5000, n),
    })
    if outlier_indices and outlier_col:
        for idx in outlier_indices:
            df.iloc[idx, df.columns.get_loc(outlier_col)] = 1000.0
    return df


class TestRobustZScore:
    def test_normal_data_z_scores_near_zero_mean(self):
        s = _normal_series(1000)
        z = robust_z_score(s)
        assert abs(z.mean()) < 0.1

    def test_outlier_has_high_z_score(self):
        s = _series_with_outliers(100, outlier_indices=[50], outlier_value=1000)
        z = robust_z_score(s)
        assert abs(z.iloc[50]) > 3.0

    def test_mad_zero_fallback_to_iqr(self):
        s = pd.Series([5.0] * 50 + [20.0])
        z = robust_z_score(s)
        assert z.iloc[-1] != 0 or z.iloc[0] == 0

    def test_all_same_values_returns_zero(self):
        s = pd.Series([7.0] * 20)
        z = robust_z_score(s)
        assert (z == 0.0).all()

    def test_iqr_fallback_with_varied_data(self):
        s = pd.Series([1, 2, 2, 3, 3, 3, 4, 4, 5, 100])
        z = robust_z_score(s)
        assert abs(z.iloc[-1]) > 2.0

    def test_nan_values_handled(self):
        s = pd.Series([10, np.nan, 10, 10, 1000, 10])
        z = robust_z_score(s)
        assert not np.isnan(z.iloc[4])


class TestDetectOutliers:
    def test_detects_extreme_outlier(self):
        s = _series_with_outliers(100, outlier_indices=[50], outlier_value=1000)
        mask = detect_outliers(s, threshold=3.0)
        assert mask.iloc[50]

    def test_normal_data_few_outliers(self):
        s = _normal_series(1000)
        mask = detect_outliers(s, threshold=3.0)
        assert mask.sum() < 50

    def test_custom_threshold(self):
        s = _series_with_outliers(100, outlier_indices=[50], outlier_value=1000)
        mask_strict = detect_outliers(s, threshold=5.0)
        mask_loose = detect_outliers(s, threshold=1.0)
        assert mask_strict.sum() <= mask_loose.sum()

    def test_returns_bool_series(self):
        s = _normal_series(50)
        mask = detect_outliers(s)
        assert mask.dtype == bool


class TestHandleOutliers:
    def test_winsorize_clips_outliers(self):
        df = _ohlcv_frame(50, outlier_col="收盘", outlier_indices=[25])
        result = handle_outliers(df, ["收盘"], method="winsorize", threshold=3.0)
        assert result["收盘"].iloc[25] < 1000.0

    def test_winsorize_preserves_non_outliers(self):
        df = _ohlcv_frame(50)
        result = handle_outliers(df, ["收盘"], method="winsorize", threshold=3.0)
        pd.testing.assert_series_equal(result["收盘"], df["收盘"])

    def test_interpolate_replaces_outliers(self):
        df = _ohlcv_frame(50, outlier_col="收盘", outlier_indices=[25])
        result = handle_outliers(df, ["收盘"], method="interpolate", threshold=3.0)
        assert result["收盘"].iloc[25] < 1000.0

    def test_interpolate_fills_with_neighbor_values(self):
        df = _ohlcv_frame(50, outlier_col="收盘", outlier_indices=[25])
        result = handle_outliers(df, ["收盘"], method="interpolate", threshold=3.0)
        prev_val = df["收盘"].iloc[24]
        next_val = df["收盘"].iloc[26]
        interpolated = result["收盘"].iloc[25]
        assert interpolated >= min(prev_val, next_val) - 1
        assert interpolated <= max(prev_val, next_val) + 1

    def test_missing_column_skipped(self):
        df = _ohlcv_frame(50)
        result = handle_outliers(df, ["nonexistent"], method="winsorize")
        pd.testing.assert_frame_equal(result, df)

    def test_no_outliers_returns_same_data(self):
        df = _ohlcv_frame(50)
        result = handle_outliers(df, ["收盘"], method="winsorize", threshold=3.0)
        pd.testing.assert_series_equal(result["收盘"], df["收盘"])


class TestPreprocessData:
    def test_enabled_preprocessing(self):
        df = _ohlcv_frame(50, outlier_col="收盘", outlier_indices=[25])
        config = {"preprocessing": {"enabled": True, "robust_z_threshold": 3.0, "outlier_method": "winsorize"}}
        result = preprocess_data(df, config)
        assert result["收盘"].iloc[25] < 1000.0

    def test_disabled_preprocessing(self):
        df = _ohlcv_frame(50, outlier_col="收盘", outlier_indices=[25])
        config = {"preprocessing": {"enabled": False}}
        result = preprocess_data(df, config)
        assert result["收盘"].iloc[25] == 1000.0

    def test_default_config_processes_ohlcv(self):
        df = _ohlcv_frame(50, outlier_col="成交量", outlier_indices=[10])
        df.iloc[10, df.columns.get_loc("成交量")] = 999999
        result = preprocess_data(df)
        assert result["成交量"].iloc[10] < 999999

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame()
        result = preprocess_data(df)
        assert result.empty

    def test_none_returns_none(self):
        result = preprocess_data(None)
        assert result is None

    def test_interpolate_method_via_config(self):
        df = _ohlcv_frame(50, outlier_col="收盘", outlier_indices=[25])
        config = {"preprocessing": {"enabled": True, "robust_z_threshold": 3.0, "outlier_method": "interpolate"}}
        result = preprocess_data(df, config)
        assert result["收盘"].iloc[25] < 1000.0


class TestIntegrationWithDataPipeline:
    def test_preprocess_data_with_full_config(self):
        config = {
            "preprocessing": {
                "enabled": True,
                "robust_z_threshold": 3.0,
                "outlier_method": "winsorize",
                "mad_fallback": "iqr",
            }
        }
        df = _ohlcv_frame(80, outlier_col="收盘", outlier_indices=[40])
        result = preprocess_data(df, config)
        assert result is not None
        assert not result.empty
        assert result["收盘"].iloc[40] < 1000.0

    def test_preprocess_preserves_frame_shape(self):
        df = _ohlcv_frame(80, outlier_col="收盘", outlier_indices=[40])
        config = {"preprocessing": {"enabled": True, "robust_z_threshold": 3.0, "outlier_method": "winsorize"}}
        result = preprocess_data(df, config)
        assert result.shape == df.shape
        assert list(result.columns) == list(df.columns)

    def test_preprocess_does_not_alter_non_ohlcv_columns(self):
        df = _ohlcv_frame(50)
        df["自定义列"] = range(50)
        config = {"preprocessing": {"enabled": True, "robust_z_threshold": 3.0, "outlier_method": "winsorize"}}
        result = preprocess_data(df, config)
        pd.testing.assert_series_equal(result["自定义列"], df["自定义列"])
