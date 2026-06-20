"""
特征正交化处理模块
通过PCA降低技术指标间的多重共线性，避免评分重复计算
"""

import numpy as np
from typing import List


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


def _float_or_zero(value) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _volume_ma_ratio(ma_data) -> float:
    """计算成交量 MA5/MA20 比值"""
    if not isinstance(ma_data, dict):
        return 0.0
    ma5 = ma_data.get("MA5", {}).get("latest")
    ma20 = ma_data.get("MA20", {}).get("latest")
    if ma5 is not None and ma20 is not None and float(ma20) > 0:
        return float(ma5) / float(ma20)
    return 0.0


def _get_distribution_feature(dist_data, feature: str) -> float:
    """从 Distribution 指标中提取指定窗口（优先 W20，其次 W60）的分布特征"""
    if not isinstance(dist_data, dict):
        return 0.0
    for window in ["W20", "W60"]:
        window_data = dist_data.get(window, {})
        feature_data = window_data.get(feature, {}) if isinstance(window_data, dict) else {}
        latest = feature_data.get("latest") if isinstance(feature_data, dict) else None
        if latest is not None:
            return _float_or_zero(latest)
    return 0.0


def _get_historical_volatility(vol_data) -> float:
    """从历史波动率指标中提取 HV20（优先）或 HV60"""
    if not isinstance(vol_data, dict):
        return 0.0
    historical = vol_data.get("Historical", {})
    latest = historical.get("latest", {}) if isinstance(historical, dict) else {}
    if isinstance(latest, dict):
        for window in ["HV20", "HV60"]:
            value = latest.get(window)
            if value is not None:
                return _float_or_zero(value)
    return 0.0


def _get_parkinson_volatility(vol_data) -> float:
    """从 Parkinson 波动率指标中提取最新值"""
    if not isinstance(vol_data, dict):
        return 0.0
    parkinson = vol_data.get("Parkinson", {})
    latest = parkinson.get("latest") if isinstance(parkinson, dict) else None
    return _float_or_zero(latest)


def _get_market_structure_feature(ms_data, feature: str) -> float:
    """从 MarketStructure 指标中提取 RelativeStrength 或 Beta 的最新值"""
    if not isinstance(ms_data, dict):
        return 0.0
    feature_data = ms_data.get(feature, {})
    latest = feature_data.get("latest") if isinstance(feature_data, dict) else None
    return _float_or_zero(latest)


# 固定特征模板：确保每次提取的特征数量和顺序一致，缺失值填0
# 格式: (特征名, 指标键, 子键路径, 转换函数或None)
_FEATURE_TEMPLATE = None  # 延迟初始化

def _get_feature_template():
    """返回固定特征模板，确保特征向量长度一致"""
    global _FEATURE_TEMPLATE
    if _FEATURE_TEMPLATE is not None:
        return _FEATURE_TEMPLATE

    template = []

    # MACD: signal, DIF, DEA, hist
    template.append(("MACD_signal", "MACD", "signal", lambda v: _map_signal(v) if isinstance(v, str) else 0.0))
    template.append(("MACD_DIF", "MACD", "latest.DIF", float))
    template.append(("MACD_DEA", "MACD", "latest.DEA", float))
    template.append(("MACD_hist", "MACD", "latest.MACD", float))

    # RSI(6), RSI(12), RSI(24): signal, value, cross
    for period in ["RSI(6)", "RSI(12)", "RSI(24)"]:
        template.append((f"{period}_signal", f"RSI.{period}", "signal", lambda v: _map_signal(v) if isinstance(v, str) else 0.0))
        template.append((f"{period}_value", f"RSI.{period}", "latest", lambda v: float(v) / 100.0 if v is not None else 0.0))
        template.append((f"{period}_cross", f"RSI.{period}", "cross", lambda v: _map_signal(v) if isinstance(v, str) and v else 0.0))

    # KDJ: signal, K, D, J
    template.append(("KDJ_signal", "KDJ", "signal", lambda v: _map_signal(v) if isinstance(v, str) else 0.0))
    template.append(("KDJ_K", "KDJ", "latest.K", lambda v: float(v) / 100.0 if v is not None else 0.0))
    template.append(("KDJ_D", "KDJ", "latest.D", lambda v: float(v) / 100.0 if v is not None else 0.0))
    template.append(("KDJ_J", "KDJ", "latest.J", lambda v: float(v) / 100.0 if v is not None else 0.0))

    # BOLL: signal, bandwidth, pct_b
    template.append(("BOLL_signal", "BOLL", "signal", lambda v: _map_signal(v) if isinstance(v, str) else 0.0))
    template.append(("BOLL_bandwidth", "BOLL", "latest.bandwidth", lambda v: float(v) / 100.0 if v is not None else 0.0))
    template.append(("BOLL_pct_b", "BOLL", "latest.pct_b", lambda v: float(v) / 100.0 if v is not None else 0.0))

    # MA5, MA10, MA20, MA60: value (归一化)
    for ma_key in ["MA5", "MA10", "MA20", "MA60"]:
        template.append((f"{ma_key}_value", f"MA.{ma_key}", "latest", "MA_NORMALIZE"))

    # ATR: signal, value (归一化)
    template.append(("ATR_signal", "ATR", "signal", lambda v: _map_signal(v) if isinstance(v, str) else 0.0))
    template.append(("ATR_value", "ATR", "latest", "ATR_NORMALIZE"))

    # 量价与风险特征（复用 technical_indicators.py 中已有计算）
    template.append(("obv", "OBV", "latest", _float_or_zero))
    template.append(("volume_ratio", "Volume_Ratio", "latest", _float_or_zero))
    template.append(("volume_ma5_ma20", "Volume_MA", "", _volume_ma_ratio))
    template.append(("relative_strength", "MarketStructure", "", lambda v: _get_market_structure_feature(v, "RelativeStrength")))
    template.append(("beta", "MarketStructure", "", lambda v: _get_market_structure_feature(v, "Beta")))
    template.append(("historical_volatility", "Volatility", "", _get_historical_volatility))
    template.append(("parkinson_volatility", "Volatility", "", _get_parkinson_volatility))
    template.append(("skewness", "Distribution", "", lambda v: _get_distribution_feature(v, "skewness")))
    template.append(("kurtosis", "Distribution", "", lambda v: _get_distribution_feature(v, "kurtosis")))
    template.append(("var_95", "Distribution", "", lambda v: _get_distribution_feature(v, "var_95")))

    _FEATURE_TEMPLATE = template
    return _FEATURE_TEMPLATE


def _resolve_path(data: dict, path: str):
    """按点分隔路径从嵌套dict中取值，如 'latest.DIF' → data['latest']['DIF']"""
    if path == "":
        return data
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def extract_feature_vector(indicators: dict, current_price: float = None) -> tuple:
    # 如果未提供 current_price，尝试从 MA5 的 latest 值推断
    if current_price is None:
        ma_data = indicators.get("MA", {})
        if isinstance(ma_data, dict):
            ma5 = ma_data.get("MA5", {})
            if isinstance(ma5, dict):
                ma5_latest = ma5.get("latest")
                if ma5_latest is not None:
                    try:
                        current_price = float(ma5_latest)
                    except (TypeError, ValueError):
                        pass

    template = _get_feature_template()
    feature_names = []
    feature_values = []

    for name, indicator_key, sub_path, transform in template:
        feature_names.append(name)
        # 解析 indicator_key (如 "RSI.RSI(6)" → indicators["RSI"]["RSI(6)"])
        ind_parts = indicator_key.split(".", 1)
        if len(ind_parts) == 2:
            ind_data = indicators.get(ind_parts[0], {})
            if isinstance(ind_data, dict):
                ind_data = ind_data.get(ind_parts[1], {})
            else:
                ind_data = {}
        else:
            ind_data = indicators.get(indicator_key, {})

        if not isinstance(ind_data, dict):
            ind_data = {}

        raw_val = _resolve_path(ind_data, sub_path)

        # 转换值
        try:
            if transform == "MA_NORMALIZE":
                if raw_val is not None and current_price and current_price > 0:
                    feature_values.append(float(raw_val) / current_price)
                elif raw_val is not None:
                    feature_values.append(float(raw_val))
                else:
                    feature_values.append(0.0)
            elif transform == "ATR_NORMALIZE":
                if raw_val is not None and current_price and current_price > 0:
                    feature_values.append(float(raw_val) / current_price)
                elif raw_val is not None:
                    feature_values.append(float(raw_val))
                else:
                    feature_values.append(0.0)
            elif callable(transform):
                if raw_val is not None:
                    feature_values.append(transform(raw_val))
                else:
                    feature_values.append(0.0)
            else:
                feature_values.append(0.0)
        except (TypeError, ValueError):
            feature_values.append(0.0)

    if not feature_values:
        return ([], np.array([]))

    return (feature_names, np.array(feature_values, dtype=np.float64))


def compute_feature_correlation(
    feature_matrix: np.ndarray,
    feature_names: List[str],
    threshold: float = 0.7,
) -> dict:
    """基于多期特征历史计算特征相关性矩阵。

    Args:
        feature_matrix: 形状为 (n_samples, n_features) 的二维特征矩阵。
        feature_names: 与矩阵列对应的特征名称列表。
        threshold: 高相关性判定阈值。

    Returns:
        dict: 包含 correlation_matrix、feature_names、high_correlation_pairs 的结果字典。
    """
    if (
        feature_matrix.ndim != 2
        or feature_matrix.shape[0] < 2
        or feature_matrix.shape[1] != len(feature_names)
        or len(feature_names) < 2
    ):
        return {
            "correlation_matrix": np.array([]),
            "feature_names": feature_names,
            "high_correlation_pairs": [],
        }

    with np.errstate(divide="ignore", invalid="ignore"):
        corr_matrix = np.corrcoef(feature_matrix, rowvar=False)
    n = len(feature_names)
    if corr_matrix.ndim != 2 or corr_matrix.shape != (n, n):
        return {
            "correlation_matrix": np.array([]),
            "feature_names": feature_names,
            "high_correlation_pairs": [],
        }

    high_corr_pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            corr_val = corr_matrix[i, j]
            if np.isfinite(corr_val) and abs(corr_val) > threshold:
                high_corr_pairs.append(
                    (feature_names[i], feature_names[j], float(corr_val))
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
