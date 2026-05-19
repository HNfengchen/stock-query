"""
特征正交化处理模块
通过PCA降低技术指标间的多重共线性，避免评分重复计算
"""

import numpy as np
from typing import Dict, List, Tuple


SIGNAL_MAP = {
    "金叉确认": 1.0,
    "金叉": 0.8,
    "多头": 0.5,
    "偏强": 0.3,
    "超卖": 0.6,
    "死叉确认": -1.0,
    "死叉": -0.8,
    "空头": -0.5,
    "偏弱": -0.3,
    "超买": -0.6,
    "正常": 0.0,
    "收窄": 0.2,
    "扩张": -0.2,
    "数据不足": 0.0,
}


def _map_signal(signal: str) -> float:
    if signal in SIGNAL_MAP:
        return SIGNAL_MAP[signal]
    for key in SIGNAL_MAP:
        if key in signal:
            return SIGNAL_MAP[key]
    return 0.0


def extract_feature_vector(indicators: dict) -> tuple:
    feature_names: list = []
    feature_values: list = []

    if "MACD" in indicators and isinstance(indicators["MACD"], dict):
        macd = indicators["MACD"]
        macd_signal = macd.get("signal", "")
        feature_names.append("MACD_signal")
        feature_values.append(_map_signal(macd_signal))

        latest = macd.get("latest", {})
        if isinstance(latest, dict):
            dif = latest.get("DIF")
            dea = latest.get("DEA")
            hist = latest.get("MACD")
            if dif is not None:
                try:
                    feature_names.append("MACD_DIF")
                    feature_values.append(float(dif))
                except (TypeError, ValueError):
                    pass
            if dea is not None:
                try:
                    feature_names.append("MACD_DEA")
                    feature_values.append(float(dea))
                except (TypeError, ValueError):
                    pass
            if hist is not None:
                try:
                    feature_names.append("MACD_hist")
                    feature_values.append(float(hist))
                except (TypeError, ValueError):
                    pass

    if "RSI" in indicators and isinstance(indicators["RSI"], dict):
        rsi = indicators["RSI"]
        for period_key in ["RSI(6)", "RSI(12)", "RSI(24)"]:
            rsi_data = rsi.get(period_key, {})
            if isinstance(rsi_data, dict):
                signal = rsi_data.get("signal", "")
                latest_val = rsi_data.get("latest")

                feature_names.append(f"{period_key}_signal")
                feature_values.append(_map_signal(signal))

                if latest_val is not None:
                    try:
                        feature_names.append(f"{period_key}_value")
                        feature_values.append(float(latest_val) / 100.0)
                    except (TypeError, ValueError):
                        pass

                cross = rsi_data.get("cross", "")
                if cross:
                    feature_names.append(f"{period_key}_cross")
                    feature_values.append(_map_signal(cross))

    if "KDJ" in indicators and isinstance(indicators["KDJ"], dict):
        kdj = indicators["KDJ"]
        kdj_signal = kdj.get("signal", "")
        feature_names.append("KDJ_signal")
        feature_values.append(_map_signal(kdj_signal))

        latest = kdj.get("latest", {})
        if isinstance(latest, dict):
            for key in ["K", "D", "J"]:
                val = latest.get(key)
                if val is not None:
                    try:
                        feature_names.append(f"KDJ_{key}")
                        feature_values.append(float(val) / 100.0)
                    except (TypeError, ValueError):
                        pass

    if "BOLL" in indicators and isinstance(indicators["BOLL"], dict):
        boll = indicators["BOLL"]
        boll_signal = boll.get("signal", "")
        feature_names.append("BOLL_signal")
        feature_values.append(_map_signal(boll_signal))

        latest = boll.get("latest", {})
        if isinstance(latest, dict):
            bandwidth = latest.get("bandwidth")
            pct_b = latest.get("pct_b")
            if bandwidth is not None:
                try:
                    feature_names.append("BOLL_bandwidth")
                    feature_values.append(float(bandwidth) / 100.0)
                except (TypeError, ValueError):
                    pass
            if pct_b is not None:
                try:
                    feature_names.append("BOLL_pct_b")
                    feature_values.append(float(pct_b) / 100.0)
                except (TypeError, ValueError):
                    pass

    if "MA" in indicators and isinstance(indicators["MA"], dict):
        ma = indicators["MA"]
        for ma_key in ["MA5", "MA10", "MA20", "MA60"]:
            ma_data = ma.get(ma_key, {})
            if isinstance(ma_data, dict):
                latest_val = ma_data.get("latest")
                if latest_val is not None:
                    try:
                        feature_names.append(f"{ma_key}_value")
                        feature_values.append(float(latest_val))
                    except (TypeError, ValueError):
                        pass

    if "ATR" in indicators and isinstance(indicators["ATR"], dict):
        atr = indicators["ATR"]
        atr_signal = atr.get("signal", "")
        feature_names.append("ATR_signal")
        feature_values.append(_map_signal(atr_signal))

        latest_val = atr.get("latest")
        if latest_val is not None:
            try:
                feature_names.append("ATR_value")
                feature_values.append(float(latest_val))
            except (TypeError, ValueError):
                pass

    if not feature_values:
        return ([], np.array([]))

    return (feature_names, np.array(feature_values, dtype=np.float64))


def compute_feature_correlation(feature_dict: dict) -> dict:
    feature_names = list(feature_dict.keys())
    if len(feature_names) < 2:
        return {
            "correlation_matrix": np.array([]),
            "feature_names": [],
            "high_correlation_pairs": [],
        }

    values = np.array([feature_dict[name] for name in feature_names], dtype=np.float64)

    n = len(feature_names)
    corr_matrix = np.corrcoef(values)

    if corr_matrix.ndim != 2 or corr_matrix.shape[0] != n:
        return {
            "correlation_matrix": np.array([]),
            "feature_names": feature_names,
            "high_correlation_pairs": [],
        }

    high_corr_pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            if abs(corr_matrix[i, j]) > 0.7:
                high_corr_pairs.append(
                    (feature_names[i], feature_names[j], float(corr_matrix[i, j]))
                )

    return {
        "correlation_matrix": corr_matrix,
        "feature_names": feature_names,
        "high_correlation_pairs": high_corr_pairs,
    }


def orthogonalize_features(
    feature_matrix: np.ndarray,
    feature_names: list,
    variance_threshold: float = 0.95,
) -> dict:
    if feature_matrix.size == 0 or feature_matrix.shape[0] < 2 or feature_matrix.shape[1] < 1:
        return {
            "orthogonal_features": np.array([]),
            "components": np.array([]),
            "explained_variance_ratio": np.array([]),
            "n_components": 0,
            "original_feature_names": feature_names,
            "orthogonal_feature_names": [],
        }

    n_samples, n_features = feature_matrix.shape

    centered = feature_matrix - feature_matrix.mean(axis=0)

    if n_samples < n_features:
        u, s, vt = np.linalg.svd(centered, full_matrices=False)
        eigenvalues = s ** 2 / (n_samples - 1)
        total_variance = eigenvalues.sum()
        if total_variance == 0:
            return {
                "orthogonal_features": np.zeros_like(centered),
                "components": np.zeros((0, n_features)),
                "explained_variance_ratio": np.array([]),
                "n_components": 0,
                "original_feature_names": feature_names,
                "orthogonal_feature_names": [],
            }
        explained_variance_ratio = eigenvalues / total_variance
        components = vt
    else:
        cov_matrix = np.dot(centered.T, centered) / (n_samples - 1)
        cov_matrix = (cov_matrix + cov_matrix.T) / 2
        eigenvalues, eigenvectors = np.linalg.eigh(cov_matrix)

        sorted_idx = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[sorted_idx]
        eigenvectors = eigenvectors[:, sorted_idx]

        total_variance = eigenvalues.sum()
        if total_variance == 0:
            return {
                "orthogonal_features": np.zeros_like(centered),
                "components": np.zeros((0, n_features)),
                "explained_variance_ratio": np.array([]),
                "n_components": 0,
                "original_feature_names": feature_names,
                "orthogonal_feature_names": [],
            }
        explained_variance_ratio = eigenvalues / total_variance
        components = eigenvectors.T

    cumulative_variance = np.cumsum(explained_variance_ratio)
    n_components = int(np.searchsorted(cumulative_variance, variance_threshold) + 1)
    n_components = min(n_components, n_features)

    selected_components = components[:n_components, :]
    orthogonal_features = np.dot(centered, selected_components.T)

    orthogonal_names = [f"PC{i+1}" for i in range(n_components)]

    return {
        "orthogonal_features": orthogonal_features,
        "components": selected_components,
        "explained_variance_ratio": explained_variance_ratio[:n_components],
        "n_components": n_components,
        "original_feature_names": feature_names,
        "orthogonal_feature_names": orthogonal_names,
    }


def build_feature_series_matrix(indicators_series: list) -> tuple:
    if not indicators_series:
        return (np.array([]), [])

    all_feature_names = None
    all_feature_values = []

    for indicators in indicators_series:
        names, values = extract_feature_vector(indicators)
        if len(values) == 0:
            continue
        if all_feature_names is None:
            all_feature_names = names
            all_feature_values.append(values)
        else:
            if len(names) == len(all_feature_names):
                if list(names) == list(all_feature_names):
                    all_feature_values.append(values)
                else:
                    padded = np.zeros(len(all_feature_names), dtype=np.float64)
                    name_to_idx = {n: i for i, n in enumerate(all_feature_names)}
                    for i, n in enumerate(names):
                        if n in name_to_idx:
                            padded[name_to_idx[n]] = values[i]
                    all_feature_values.append(padded)
            else:
                padded = np.zeros(len(all_feature_names), dtype=np.float64)
                name_to_idx = {n: i for i, n in enumerate(all_feature_names)}
                for i, n in enumerate(names):
                    if n in name_to_idx:
                        padded[name_to_idx[n]] = values[i]
                all_feature_values.append(padded)

    if not all_feature_values or all_feature_names is None:
        return (np.array([]), [])

    feature_matrix = np.array(all_feature_values, dtype=np.float64)

    return (feature_matrix, all_feature_names)
