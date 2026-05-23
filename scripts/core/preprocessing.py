"""
数据预处理模块
基于 Robust Z-Score 的异常值检测与处理
支持卡尔曼滤波和自适应EMA去噪
"""

import pandas as pd
import numpy as np
from typing import List, Optional, Tuple


OHLCV_COLUMNS = ["开盘", "收盘", "最高", "最低", "成交量"]
OHLCV_ALT_COLUMNS = ["open", "close", "high", "low", "volume"]
OHLC_COLUMNS = ["开盘", "收盘", "最高", "最低"]
OHLC_ALT_COLUMNS = ["open", "close", "high", "low"]


def robust_z_score(series: pd.Series) -> pd.Series:
    median = series.median()
    mad = (series - median).abs().median() * 1.4826

    if mad == 0 or (isinstance(mad, float) and np.isnan(mad)):
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0 or (isinstance(iqr, float) and np.isnan(iqr)):
            return pd.Series(0.0, index=series.index)
        return (series - median) / (iqr / 1.35)

    return (series - median) / mad


def detect_outliers(series: pd.Series, threshold: float = 3.0) -> pd.Series:
    z_scores = robust_z_score(series)
    return z_scores.abs() > threshold


def handle_outliers(
    df: pd.DataFrame,
    columns: list,
    method: str = "winsorize",
    threshold: float = 3.0,
) -> pd.DataFrame:
    result = df.copy()

    for col in columns:
        if col not in result.columns:
            continue

        series = result[col].copy()
        valid_mask = series.notna()
        if valid_mask.sum() < 3:
            continue

        outlier_mask = detect_outliers(series[valid_mask], threshold=threshold)
        outlier_indices = series[valid_mask].index[outlier_mask]

        if len(outlier_indices) == 0:
            continue

        if method == "winsorize":
            z_scores = robust_z_score(series[valid_mask])
            median = series[valid_mask].median()
            mad = (series[valid_mask] - median).abs().median() * 1.4826

            if mad == 0 or (isinstance(mad, float) and np.isnan(mad)):
                q1 = series[valid_mask].quantile(0.25)
                q3 = series[valid_mask].quantile(0.75)
                iqr = q3 - q1
                if iqr == 0 or (isinstance(iqr, float) and np.isnan(iqr)):
                    continue
                scale = iqr / 1.35
            else:
                scale = mad

            upper_bound = median + threshold * scale
            lower_bound = median - threshold * scale
            result[col] = series.clip(lower=lower_bound, upper=upper_bound)

        elif method == "interpolate":
            series.loc[outlier_indices] = np.nan
            series = series.interpolate(method="linear")
            if series.iloc[0] != series.iloc[0]:
                first_valid = series.first_valid_index()
                if first_valid is not None:
                    series.iloc[0] = series.loc[first_valid]
            if series.iloc[-1] != series.iloc[-1]:
                last_valid = series.last_valid_index()
                if last_valid is not None:
                    series.iloc[-1] = series.loc[last_valid]
            result[col] = series

    return result


def preprocess_data(df: pd.DataFrame, config: dict = None) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    config = config or {}
    preprocessing_config = config.get("preprocessing", {})

    if not preprocessing_config.get("enabled", True):
        return df

    threshold = preprocessing_config.get("robust_z_threshold", 3.0)
    method = preprocessing_config.get("outlier_method", "winsorize")

    target_columns = []
    for col in OHLCV_COLUMNS + OHLCV_ALT_COLUMNS:
        if col in df.columns:
            target_columns.append(col)

    if not target_columns:
        return df

    return handle_outliers(df, target_columns, method=method, threshold=threshold)


def kalman_filter_denoise(series: pd.Series, Q: float = 1e-5, R: float = 1e-2) -> pd.Series:
    # 基于近期波动率自适应调整Q，波动大时增大Q允许更快跟踪
    Q_adaptive = Q
    if len(series) >= 20:
        vol = series.pct_change().rolling(20).std().iloc[-1]
        if not np.isnan(vol):
            Q_adaptive = Q * (1 + vol * 100)

    x = None
    P = 1.0
    result = np.full(len(series), np.nan)

    for i in range(len(series)):
        z = series.iloc[i]

        if x is None:
            if not np.isnan(z):
                x = z
                result[i] = x
            continue

        x_pred = x
        P_pred = P + Q_adaptive

        if np.isnan(z):
            x = x_pred
            P = P_pred
            result[i] = x
            continue

        K = P_pred / (P_pred + R)
        x = x_pred + K * (z - x_pred)
        P = (1 - K) * P_pred
        result[i] = x

    return pd.Series(result, index=series.index, name=series.name)


def ema_adaptive_denoise(series: pd.Series, alpha_range: Tuple[float, float] = (0.05, 0.3)) -> pd.Series:
    alpha_low, alpha_high = alpha_range
    result = np.full(len(series), np.nan)

    returns = series.pct_change()
    rolling_vol = returns.rolling(window=20, min_periods=1).std()

    vol_values = rolling_vol.dropna()
    if vol_values.empty:
        return series.copy()

    vol_ranks = rolling_vol.rank(pct=True).fillna(0.5)

    first_valid_idx = series.first_valid_index()
    if first_valid_idx is None:
        return series.copy()

    first_pos = series.index.get_loc(first_valid_idx)
    result[first_pos] = series.iloc[first_pos]

    for i in range(first_pos + 1, len(series)):
        if np.isnan(series.iloc[i]):
            result[i] = result[i - 1]
            continue

        vol_percentile = vol_ranks.iloc[i] if not np.isnan(vol_ranks.iloc[i]) else 0.5
        alpha = alpha_low + (alpha_high - alpha_low) * vol_percentile
        result[i] = alpha * series.iloc[i] + (1 - alpha) * result[i - 1]

    return pd.Series(result, index=series.index, name=series.name)


def denoise_data(df: pd.DataFrame, config: dict = None) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    config = config or {}
    preprocessing_config = config.get("preprocessing", {})
    denoise_config = preprocessing_config.get("denoise", {})

    method = denoise_config.get("method", "none")
    if method == "none":
        return df

    result = df.copy()

    price_columns = []
    for col in OHLC_COLUMNS + OHLC_ALT_COLUMNS:
        if col in result.columns:
            price_columns.append(col)

    if not price_columns:
        return result

    for col in price_columns:
        series = result[col].copy()
        valid_count = series.notna().sum()
        if valid_count < 3:
            continue

        if method == "kalman":
            Q = denoise_config.get("kalman_Q", 1e-5)
            R = denoise_config.get("kalman_R", 1e-2)
            result[col] = kalman_filter_denoise(series, Q=Q, R=R)
        elif method == "ema_adaptive":
            alpha_range = tuple(denoise_config.get("ema_alpha_range", [0.05, 0.3]))
            result[col] = ema_adaptive_denoise(series, alpha_range=alpha_range)

    return result
