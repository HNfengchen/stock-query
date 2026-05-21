"""
技术指标计算模块
提供 MACD、RSI、KDJ 等常用技术指标的计算功能
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Union, Optional


def calculate_macd(
    close_prices: Union[List, pd.Series],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Dict:
    """
    计算MACD指标

    参数:
        close_prices: 收盘价序列
        fast: 快线周期，默认12
        slow: 慢线周期，默认26
        signal: 信号线周期，默认9

    返回:
        dict: 包含latest、series和signal的字典
    """
    if len(close_prices) < slow + signal:
        length = len(close_prices) if hasattr(close_prices, '__len__') else 0
        return {
            "latest": {"DIF": None, "DEA": None, "MACD": None},
            "series": {
                "DIF": pd.Series([None] * length),
                "DEA": pd.Series([None] * length),
                "MACD": pd.Series([None] * length),
            },
            "signal": "数据不足",
        }

    closes = pd.Series(close_prices)
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd = (dif - dea) * 2

    dif_series = dif.round(4)
    dea_series = dea.round(4)
    macd_series = macd.round(4)

    signal_text = "数据不足"
    if len(dif) >= 5:
        dif_diff = dif.iloc[-1] - dea.iloc[-1]
        avg_diff = (dif - dea).abs().tail(10).mean()
        threshold = avg_diff * 0.3 if avg_diff else 0

        dif_rising = dif.iloc[-1] > dif.iloc[-2] > dif.iloc[-3]
        dif_falling = dif.iloc[-1] < dif.iloc[-2] < dif.iloc[-3]

        if dif.iloc[-1] > dea.iloc[-1] and dif.iloc[-2] <= dea.iloc[-2]:
            if dif_rising and abs(dif_diff) > threshold:
                signal_text = "金叉确认"
            else:
                signal_text = "金叉"
        elif dif.iloc[-1] < dea.iloc[-1] and dif.iloc[-2] >= dea.iloc[-2]:
            if dif_falling and abs(dif_diff) > threshold:
                signal_text = "死叉确认"
            else:
                signal_text = "死叉"
        elif dif.iloc[-1] > dea.iloc[-1]:
            signal_text = "多头"
        else:
            signal_text = "空头"
    elif len(dif) >= 2:
        if dif.iloc[-1] > dea.iloc[-1] and dif.iloc[-2] <= dea.iloc[-2]:
            signal_text = "金叉"
        elif dif.iloc[-1] < dea.iloc[-1] and dif.iloc[-2] >= dea.iloc[-2]:
            signal_text = "死叉"
        elif dif.iloc[-1] > dea.iloc[-1]:
            signal_text = "多头"
        else:
            signal_text = "空头"

    return {
        "latest": {
            "DIF": round(dif.iloc[-1], 4) if not pd.isna(dif.iloc[-1]) else None,
            "DEA": round(dea.iloc[-1], 4) if not pd.isna(dea.iloc[-1]) else None,
            "MACD": round(macd.iloc[-1], 4) if not pd.isna(macd.iloc[-1]) else None,
        },
        "series": {
            "DIF": dif_series,
            "DEA": dea_series,
            "MACD": macd_series,
        },
        "signal": signal_text,
    }


def calculate_rsi(
    close_prices: Union[List, pd.Series], periods: List[int] = [6, 12, 24]
) -> Dict:
    """
    计算RSI指标

    参数:
        close_prices: 收盘价序列
        periods: RSI周期列表，默认[6, 12, 24]

    返回:
        dict: 包含各周期RSI值和状态
    """
    closes = pd.Series(close_prices)
    deltas = closes.diff()

    result = {}
    rsi_series = {}

    for period in periods:
        if len(closes) < period + 1:
            result[f"RSI({period})"] = {
                "latest": None,
                "series": pd.Series([None] * len(closes)),
                "signal": "数据不足",
            }
            continue

        gain = deltas.where(deltas > 0, 0)
        loss = -deltas.where(deltas < 0, 0)

        avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
        avg_loss = loss.ewm(com=period - 1, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.inf)
        rsi = 100 - (100 / (1 + rs))

        rsi_series[period] = rsi.round(2)

        latest = round(rsi.iloc[-1], 2) if not pd.isna(rsi.iloc[-1]) else None

        if latest is not None:
            if len(rsi) >= 60:
                rsi_p80 = rsi.rolling(window=60).quantile(0.8).iloc[-1]
                rsi_p20 = rsi.rolling(window=60).quantile(0.2).iloc[-1]
                if not pd.isna(rsi_p80) and not pd.isna(rsi_p20):
                    ob = rsi_p80
                    os_val = rsi_p20
                else:
                    ob, os_val = 80, 20
            else:
                ob, os_val = 80, 20

            if latest > ob:
                signal = "超买"
            elif latest < os_val:
                signal = "超卖"
            elif latest > (ob + 50) / 2:
                signal = "偏强"
            elif latest < (os_val + 50) / 2:
                signal = "偏弱"
            else:
                signal = "正常"
        else:
            signal = "数据不足"

        result[f"RSI({period})"] = {"latest": latest, "series": rsi_series[period], "signal": signal}

    if len(periods) >= 2:
        rsi_6 = result.get("RSI(6)", {}).get("latest")
        rsi_12 = result.get("RSI(12)", {}).get("latest")
        if rsi_6 is not None and rsi_12 is not None and len(rsi_series.get(6, pd.Series())) >= 2:
            rsi_6_s = rsi_series.get(6, pd.Series())
            rsi_12_s = rsi_series.get(12, pd.Series())
            if rsi_6_s.iloc[-1] > rsi_12_s.iloc[-1] and rsi_6_s.iloc[-2] <= rsi_12_s.iloc[-2]:
                if "RSI(6)" in result:
                    result["RSI(6)"]["cross"] = "金叉"
            elif rsi_6_s.iloc[-1] < rsi_12_s.iloc[-1] and rsi_6_s.iloc[-2] >= rsi_12_s.iloc[-2]:
                if "RSI(6)" in result:
                    result["RSI(6)"]["cross"] = "死叉"

    return result


def calculate_kdj(
    high_prices: Union[List, pd.Series],
    low_prices: Union[List, pd.Series],
    close_prices: Union[List, pd.Series],
    n: int = 9,
    m1: int = 3,
    m2: int = 3,
) -> Dict:
    """
    计算KDJ指标

    参数:
        high_prices: 最高价序列
        low_prices: 最低价序列
        close_prices: 收盘价序列
        n: RSV周期，默认9
        m1: K值平滑周期，默认3
        m2: D值平滑周期，默认3

    返回:
        dict: 包含K、D、J值的序列和信号
    """
    if len(close_prices) < n:
        length = len(close_prices) if hasattr(close_prices, "__len__") else 10
        return {
            "K": pd.Series([None] * length),
            "D": pd.Series([None] * length),
            "J": pd.Series([None] * length),
            "signal": "数据不足",
        }

    high = pd.Series(high_prices)
    low = pd.Series(low_prices)
    close = pd.Series(close_prices)

    lowest_low = low.rolling(window=n, min_periods=n).min()
    highest_high = high.rolling(window=n, min_periods=n).max()

    rsv = (close - lowest_low) / (highest_high - lowest_low) * 100
    rsv = rsv.replace([np.inf, -np.inf], 50).fillna(50)

    k = pd.Series([np.nan] * len(close), index=close.index)
    d = pd.Series([np.nan] * len(close), index=close.index)

    first_valid = rsv.first_valid_index()
    if first_valid is not None:
        k.iloc[first_valid] = rsv.iloc[first_valid]
        d.iloc[first_valid] = rsv.iloc[first_valid]
        start_idx = first_valid + 1
    else:
        k.iloc[0] = 50.0
        d.iloc[0] = 50.0
        start_idx = 1

    for i in range(start_idx, len(rsv)):
        if pd.isna(rsv.iloc[i]):
            continue
        k.iloc[i] = (k.iloc[i - 1] * (m1 - 1) + rsv.iloc[i]) / m1
        d.iloc[i] = (d.iloc[i - 1] * (m2 - 1) + k.iloc[i]) / m2

    j = 3 * k - 2 * d

    k_series = k.round(2)
    d_series = d.round(2)
    j_series = j.round(2)

    k_val = round(k.iloc[-1], 2) if not pd.isna(k.iloc[-1]) else None
    d_val = round(d.iloc[-1], 2) if not pd.isna(d.iloc[-1]) else None
    j_val = round(j.iloc[-1], 2) if not pd.isna(j.iloc[-1]) else None

    if k_val is not None and d_val is not None and len(k) >= 2:
        if k_val > d_val and k.iloc[-2] <= d.iloc[-2]:
            signal_text = "金叉"
        elif k_val < d_val and k.iloc[-2] >= d.iloc[-2]:
            signal_text = "死叉"
        elif k_val > 80 and d_val > 80:
            signal_text = "超买"
        elif k_val < 20 and d_val < 20:
            signal_text = "超卖"
        else:
            signal_text = "正常"
    else:
        signal_text = "数据不足"

    return {
        "latest": {"K": k_val, "D": d_val, "J": j_val},
        "series": {"K": k_series, "D": d_series, "J": j_series},
        "signal": signal_text,
    }


def calculate_ma(
    close_prices: Union[List, pd.Series], periods: List[int] = [5, 10, 20, 60]
) -> Dict:
    """
    计算移动平均线

    参数:
        close_prices: 收盘价序列
        periods: 均线周期列表，默认[5, 10, 20, 60]

    返回:
        dict: 包含各周期均线值的序列和最新值
    """
    closes = pd.Series(close_prices)
    result = {}

    for period in periods:
        if len(closes) >= period:
            ma = closes.rolling(window=period).mean().round(2)
            latest = ma.iloc[-1] if not pd.isna(ma.iloc[-1]) else None
        else:
            ma = pd.Series([None] * len(closes))
            latest = None

        result[f"MA{period}"] = {"latest": latest, "series": ma}

    return result


def calculate_boll(
    close_prices: Union[List, pd.Series], n: int = 20, k: int = 2
) -> Dict:
    """
    计算布林带指标

    参数:
        close_prices: 收盘价序列
        n: 周期，默认20
        k: 标准差倍数，默认2

    返回:
        dict: 包含latest、series的字典
    """
    closes = pd.Series(close_prices)
    length = len(closes)

    if length < n:
        return {
            "latest": {"upper": None, "middle": None, "lower": None},
            "series": {
                "upper": pd.Series([None] * length),
                "middle": pd.Series([None] * length),
                "lower": pd.Series([None] * length),
            },
        }

    middle = closes.rolling(window=n).mean()
    std = closes.rolling(window=n).std(ddof=1)

    upper = middle + k * std
    lower = middle - k * std

    bandwidth = ((upper - middle) / middle * 100).replace([np.inf, -np.inf], np.nan).round(2)
    pct_b = ((closes - lower) / (upper - lower) * 100).replace([np.inf, -np.inf], np.nan).round(2)

    latest_bandwidth = bandwidth.iloc[-1] if not pd.isna(bandwidth.iloc[-1]) else None
    latest_pct_b = pct_b.iloc[-1] if not pd.isna(pct_b.iloc[-1]) else None

    signal = "正常"
    if latest_bandwidth is not None:
        if latest_bandwidth < 10:
            signal = "收窄"
        elif latest_bandwidth > 25:
            signal = "扩张"

    return {
        "latest": {
            "upper": round(upper.iloc[-1], 2) if not pd.isna(upper.iloc[-1]) else None,
            "middle": round(middle.iloc[-1], 2) if not pd.isna(middle.iloc[-1]) else None,
            "lower": round(lower.iloc[-1], 2) if not pd.isna(lower.iloc[-1]) else None,
            "bandwidth": latest_bandwidth,
            "pct_b": latest_pct_b,
        },
        "signal": signal,
        "series": {
            "upper": upper.round(2),
            "middle": middle.round(2),
            "lower": lower.round(2),
            "bandwidth": bandwidth,
            "pct_b": pct_b,
        },
    }


def calculate_atr(
    high_prices: Union[List, pd.Series],
    low_prices: Union[List, pd.Series],
    close_prices: Union[List, pd.Series],
    period: int = 14,
) -> Dict:
    """
    计算ATR（Average True Range）指标

    参数:
        high_prices: 最高价序列
        low_prices: 最低价序列
        close_prices: 收盘价序列
        period: ATR周期，默认14

    返回:
        dict: 包含ATR序列、最新值和信号
    """
    high = pd.Series(high_prices)
    low = pd.Series(low_prices)
    close = pd.Series(close_prices)

    if len(high) < period + 1:
        length = len(high)
        return {
            "atr": pd.Series([None] * length),
            "latest": None,
            "signal": "数据不足",
        }

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # M-06: 改用Wilder平滑（等同于EWM with com=period-1）
    atr = true_range.ewm(com=period - 1, adjust=False).mean().round(2)

    latest = round(atr.iloc[-1], 2) if not pd.isna(atr.iloc[-1]) else None

    current_price = close.iloc[-1]
    if latest and current_price and latest > current_price * 0.03:
        status = "波动剧烈"
    else:
        status = "正常"

    return {"atr": atr, "latest": latest, "signal": status}


def calculate_obv(
    close_prices: Union[List, pd.Series],
    volumes: Union[List, pd.Series],
) -> Dict:
    """
    计算OBV（能量潮）指标

    参数:
        close_prices: 收盘价序列
        volumes: 成交量序列

    返回:
        dict: 包含OBV序列、最新值和信号
    """
    close = pd.Series(close_prices)
    volume = pd.Series(volumes)

    if len(close) < 2:
        length = len(close)
        return {"obv": pd.Series([None] * length), "latest": None, "signal": "数据不足"}

    close_diff = close.diff()
    direction = close_diff.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    obv = (volume * direction).cumsum()

    latest = round(obv.iloc[-1], 0) if not pd.isna(obv.iloc[-1]) else None

    if len(obv) >= 5:
        signal = "上涨" if obv.iloc[-1] > obv.iloc[-5] else "下跌"
    else:
        signal = "震荡"

    return {"obv": obv, "latest": latest, "signal": signal}


def calculate_volume_ma(
    volumes: Union[List, pd.Series], periods: List[int] = [5, 10, 20]
) -> Dict:
    """
    计算成交量MA指标

    参数:
        volumes: 成交量序列
        periods: MA周期列表，默认[5, 10, 20]

    返回:
        dict: 包含各周期成交量MA的序列和最新值
    """
    volumes = pd.Series(volumes)
    result = {}

    for period in periods:
        if len(volumes) >= period:
            ma = volumes.rolling(window=period).mean().round(0)
            latest = ma.iloc[-1] if not pd.isna(ma.iloc[-1]) else None
        else:
            ma = pd.Series([None] * len(volumes))
            latest = None

        result[f"MA{period}"] = {"latest": latest, "series": ma}

    return result


def calculate_volume_ratio(volume: Union[List, pd.Series], n: int = 5) -> Dict:
    """
    计算量比指标

    参数:
        volume: 成交量序列
        n: 平均周期，默认5

    返回:
        dict: 包含量比值
    """
    volumes = pd.Series(volume)

    if len(volumes) < n + 1:
        return {"volume_ratio": None, "status": "数据不足"}

    today_volume = volumes.iloc[-1]
    avg_volume = volumes.iloc[-n - 1 : -1].mean()

    if avg_volume > 0:
        vr = today_volume / avg_volume
        vr = round(vr, 2)

        if vr > 2.5:
            signal = "巨量"
        elif vr > 1.5:
            signal = "放量"
        elif vr > 0.8:
            signal = "正常"
        else:
            signal = "缩量"
    else:
        vr = None
        signal = "数据异常"

    return {"latest": vr, "signal": signal}


def calculate_distribution_features(
    df: pd.DataFrame,
    windows: List[int] = None,
    prev_state: Optional[Dict] = None,
) -> Dict:
    if windows is None:
        windows = [20, 60]

    if "收盘" in df.columns:
        closes = df["收盘"]
    elif "close" in df.columns:
        closes = df["close"]
    else:
        return {"Distribution": {}, "state": {}}

    closes = pd.Series(closes).astype(float)
    log_returns = np.log(closes / closes.shift(1)).replace([np.inf, -np.inf], np.nan).dropna()

    result = {}
    window_states = {}

    for w in windows:
        w_key = f"W{w}"
        if len(log_returns) < w:
            result[w_key] = {
                "skewness": {"latest": None, "signal": "数据不足"},
                "kurtosis": {"latest": None, "signal": "数据不足"},
                "var_95": {"latest": None},
                "var_99": {"latest": None},
                "cvar_95": {"latest": None},
                "cvar_99": {"latest": None},
            }
            continue

        returns_window = log_returns.iloc[-w:].values

        mean = np.mean(returns_window)
        std = np.std(returns_window, ddof=1)

        if std == 0:
            skewness = 0.0
            kurtosis = 0.0
        else:
            n = len(returns_window)
            skewness = float(np.sum(((returns_window - mean) / std) ** 3) / n)
            kurtosis = float(np.sum(((returns_window - mean) / std) ** 4) / n - 3)

        if skewness < -0.5:
            skew_signal = "左偏"
        elif skewness > 0.5:
            skew_signal = "右偏"
        else:
            skew_signal = "对称"

        if kurtosis > 0:
            kurt_signal = "厚尾"
        elif kurtosis < -1:
            kurt_signal = "轻尾"
        else:
            kurt_signal = "正常"

        var_95 = float(np.percentile(returns_window, 5))
        var_99 = float(np.percentile(returns_window, 1))

        below_var_95 = returns_window[returns_window <= var_95]
        below_var_99 = returns_window[returns_window <= var_99]

        cvar_95 = float(np.mean(below_var_95)) if len(below_var_95) > 0 else var_95
        cvar_99 = float(np.mean(below_var_99)) if len(below_var_99) > 0 else var_99

        result[w_key] = {
            "skewness": {"latest": round(skewness, 4), "signal": skew_signal},
            "kurtosis": {"latest": round(kurtosis, 4), "signal": kurt_signal},
            "var_95": {"latest": round(var_95, 6)},
            "var_99": {"latest": round(var_99, 6)},
            "cvar_95": {"latest": round(cvar_95, 6)},
            "cvar_99": {"latest": round(cvar_99, 6)},
        }

        window_states[w_key] = {
            "skewness": skewness,
            "kurtosis": kurtosis,
            "var_95": var_95,
            "var_99": var_99,
            "cvar_95": cvar_95,
            "cvar_99": cvar_99,
        }

    state = {
        "windows": list(windows),
        "window_states": window_states,
    }

    return {"Distribution": result, "state": state}


def calculate_relative_strength(
    stock_returns: pd.Series, index_returns: pd.Series, window: int = 20
) -> Dict:
    if index_returns is None or (hasattr(index_returns, "empty") and index_returns.empty) or len(index_returns) == 0:
        return {"RelativeStrength": {"latest": 1.0, "series": [], "signal": "数据不可用"}}

    stock_ret = pd.Series(stock_returns).iloc[-window:] if len(stock_returns) >= window else pd.Series(stock_returns)
    index_ret = pd.Series(index_returns).iloc[-window:] if len(index_returns) >= window else pd.Series(index_returns)

    min_len = min(len(stock_ret), len(index_ret))
    stock_ret = stock_ret.iloc[-min_len:]
    index_ret = index_ret.iloc[-min_len:]

    stock_cum = (1 + stock_ret).prod()
    index_cum = (1 + index_ret).prod()

    if index_cum == 0:
        rs = 1.0
    else:
        rs = stock_cum / index_cum

    rs = round(float(rs), 4)

    if rs > 1.2:
        signal = "强势"
    elif rs > 1.0:
        signal = "偏强"
    elif rs > 0.8:
        signal = "偏弱"
    else:
        signal = "弱势"

    series = []
    step = max(1, min_len // 20)
    for i in range(step, min_len + 1, step):
        s_cum = (1 + stock_ret.iloc[:i]).prod()
        i_cum = (1 + index_ret.iloc[:i]).prod()
        series.append(round(float(s_cum / i_cum), 4) if i_cum != 0 else 1.0)

    return {"RelativeStrength": {"latest": rs, "series": series, "signal": signal}}


def calculate_beta(
    stock_returns: pd.Series, index_returns: pd.Series, window: int = 60
) -> Dict:
    if index_returns is None or (hasattr(index_returns, "empty") and index_returns.empty) or len(index_returns) < 2:
        return {"Beta": {"latest": 1.0, "series": [], "signal": "数据不可用"}}

    stock_ret = pd.Series(stock_returns)
    index_ret = pd.Series(index_returns)

    min_len = min(len(stock_ret), len(index_ret))
    stock_ret = stock_ret.iloc[-min_len:].values
    index_ret = index_ret.iloc[-min_len:].values

    series = []
    step = max(1, min(window, min_len) // 10)
    for i in range(window, min_len + 1, step):
        s = stock_ret[i - window:i]
        idx = index_ret[i - window:i]
        cov_mat = np.cov(s, idx)
        var_idx = np.var(idx)
        if var_idx != 0:
            b = cov_mat[0, 1] / var_idx
        else:
            b = 1.0
        series.append(round(float(b), 4))

    s_w = stock_ret[-window:]
    idx_w = index_ret[-window:]
    cov_mat = np.cov(s_w, idx_w)
    var_idx = np.var(idx_w)
    if var_idx != 0:
        beta = cov_mat[0, 1] / var_idx
    else:
        beta = 1.0

    beta = round(float(beta), 4)

    if beta > 1.5:
        signal = "高Beta"
    elif beta > 1.0:
        signal = "中高Beta"
    elif beta > 0.5:
        signal = "中低Beta"
    else:
        signal = "低Beta"

    return {"Beta": {"latest": beta, "series": series, "signal": signal}}


def calculate_industry_strength(
    industry_returns: pd.Series, index_returns: pd.Series, window: int = 20
) -> Dict:
    if industry_returns is None or (hasattr(industry_returns, "empty") and industry_returns.empty) or len(industry_returns) == 0:
        return {"IndustryStrength": {"latest": 0.0, "series": [], "signal": "数据不可用"}}

    ind_ret = pd.Series(industry_returns).iloc[-window:] if len(industry_returns) >= window else pd.Series(industry_returns)

    if index_returns is not None and len(index_returns) > 0:
        idx_ret = pd.Series(index_returns).iloc[-window:] if len(index_returns) >= window else pd.Series(index_returns)
        min_len = min(len(ind_ret), len(idx_ret))
        ind_ret = ind_ret.iloc[-min_len:]
        idx_ret = idx_ret.iloc[-min_len:]
        index_cum = (1 + idx_ret).prod()
    else:
        index_cum = 1.0

    industry_cum = (1 + ind_ret).prod()
    strength = industry_cum - index_cum
    strength = round(float(strength), 4)

    if strength > 0.05:
        signal = "强势"
    elif strength > 0:
        signal = "偏强"
    elif strength > -0.05:
        signal = "偏弱"
    else:
        signal = "弱势"

    series = []
    step = max(1, len(ind_ret) // 20)
    for i in range(step, len(ind_ret) + 1, step):
        i_cum = (1 + ind_ret.iloc[:i]).prod()
        if index_returns is not None and len(index_returns) > 0:
            x_cum = (1 + idx_ret.iloc[:i]).prod()
        else:
            x_cum = 1.0
        series.append(round(float(i_cum - x_cum), 4))

    return {"IndustryStrength": {"latest": strength, "series": series, "signal": signal}}


def calculate_sector_fund_flow(sector_fund_data: dict = None) -> Dict:
    if sector_fund_data is None:
        return {"SectorFundFlow": {"latest": 0.0, "signal": "数据不可用"}}

    net_inflow = sector_fund_data.get("net_inflow", sector_fund_data.get("主力净流入", 0))
    try:
        net_inflow = float(net_inflow) if net_inflow else 0.0
    except (TypeError, ValueError):
        net_inflow = 0.0

    if net_inflow > 1e9:
        signal = "大幅流入"
    elif net_inflow > 0:
        signal = "流入"
    elif net_inflow > -1e9:
        signal = "流出"
    else:
        signal = "大幅流出"

    return {"SectorFundFlow": {"latest": net_inflow, "signal": signal}}


def calculate_market_structure(
    stock_df: pd.DataFrame,
    index_df: pd.DataFrame = None,
    industry_df: pd.DataFrame = None,
    sector_fund_data: dict = None,
    config: dict = None,
) -> Dict:
    if config is None:
        config = {}

    rs_window = config.get("rs_window", 20)
    beta_window = config.get("beta_window", 60)
    is_window = config.get("is_window", 20)

    if "收盘" in stock_df.columns:
        stock_closes = stock_df["收盘"].astype(float)
    elif "close" in stock_df.columns:
        stock_closes = stock_df["close"].astype(float)
    else:
        return {"MarketStructure": {}}

    stock_returns = stock_closes.pct_change().dropna()

    index_returns = None
    if index_df is not None and not index_df.empty:
        if "收盘" in index_df.columns:
            index_closes = index_df["收盘"].astype(float)
        elif "close" in index_df.columns:
            index_closes = index_df["close"].astype(float)
        else:
            index_closes = None
        if index_closes is not None:
            index_returns = index_closes.pct_change().dropna()

    industry_returns = None
    if industry_df is not None and not industry_df.empty:
        if "收盘" in industry_df.columns:
            industry_closes = industry_df["收盘"].astype(float)
        elif "close" in industry_df.columns:
            industry_closes = industry_df["close"].astype(float)
        else:
            industry_closes = None
        if industry_closes is not None:
            industry_returns = industry_closes.pct_change().dropna()

    rs_result = calculate_relative_strength(stock_returns, index_returns, rs_window)
    beta_result = calculate_beta(stock_returns, index_returns, beta_window)
    is_result = calculate_industry_strength(industry_returns, index_returns, is_window)
    fund_result = calculate_sector_fund_flow(sector_fund_data)

    return {
        "MarketStructure": {
            "RelativeStrength": rs_result["RelativeStrength"],
            "Beta": beta_result["Beta"],
            "IndustryStrength": is_result["IndustryStrength"],
            "SectorFundFlow": fund_result["SectorFundFlow"],
        }
    }


def _get_column(df, cn_name, en_name):
    if cn_name in df.columns:
        return df[cn_name].astype(float)
    elif en_name in df.columns:
        return df[en_name].astype(float)
    return None


def _vol_signal(series, low_pct, high_pct):
    if len(series) < 20:
        return "数据不足"
    valid = series.dropna()
    if len(valid) < 20:
        return "数据不足"
    latest = valid.iloc[-1]
    low_threshold = valid.rolling(window=len(valid), min_periods=20).quantile(low_pct / 100.0).iloc[-1]
    high_threshold = valid.rolling(window=len(valid), min_periods=20).quantile(high_pct / 100.0).iloc[-1]
    if pd.isna(low_threshold) or pd.isna(high_threshold):
        return "正常"
    if latest <= low_threshold:
        return "低波动"
    elif latest >= high_threshold:
        return "高波动"
    else:
        return "正常"


def calculate_historical_volatility(
    df: pd.DataFrame,
    windows: Union[int, List[int]] = 20,
    prev_state: Optional[Dict] = None,
) -> Dict:
    closes = _get_column(df, "收盘", "close")
    if closes is None:
        return {"latest": None, "series": {}, "signal": "数据不足", "state": {}}

    log_returns = np.log(closes / closes.shift(1)).replace([np.inf, -np.inf], np.nan).dropna()
    if isinstance(windows, int):
        windows = [windows]

    result_series = {}
    result_latest = {}
    states = {}
    low_pct = 25
    high_pct = 75

    for w in windows:
        if len(log_returns) < w:
            result_series[f"HV{w}"] = pd.Series([None] * len(closes), index=closes.index)
            result_latest[f"HV{w}"] = None
            continue
        hv = log_returns.rolling(window=w).std() * np.sqrt(252)
        result_series[f"HV{w}"] = hv.round(4)
        result_latest[f"HV{w}"] = round(hv.iloc[-1], 4) if not pd.isna(hv.iloc[-1]) else None
        states[f"HV{w}"] = {"window": w, "last_value": result_latest[f"HV{w}"]}

    combined = pd.DataFrame(result_series)
    first_key = list(result_series.keys())[0] if result_series else None
    if first_key and result_series[first_key] is not None:
        signal = _vol_signal(result_series[first_key], low_pct, high_pct)
    else:
        signal = "数据不足"

    return {
        "latest": result_latest,
        "series": result_series,
        "signal": signal,
        "state": states,
    }


def calculate_parkinson_volatility(
    df: pd.DataFrame,
    window: int = 20,
    prev_state: Optional[Dict] = None,
) -> Dict:
    high = _get_column(df, "最高", "high")
    low = _get_column(df, "最低", "low")
    if high is None or low is None:
        return {"latest": None, "series": pd.Series(), "signal": "数据不足", "state": {}}

    if len(high) < window:
        return {"latest": None, "series": pd.Series([None] * len(high)), "signal": "数据不足", "state": {}}

    log_hl_sq = (np.log(high / low)) ** 2
    log_hl_sq = log_hl_sq.replace([np.inf, -np.inf], np.nan)
    factor = 1.0 / (4.0 * np.log(2.0))
    pv = np.sqrt(log_hl_sq.rolling(window=window).mean() * factor) * np.sqrt(252)

    latest = round(pv.iloc[-1], 4) if not pd.isna(pv.iloc[-1]) else None
    signal = _vol_signal(pv, 25, 75)

    return {
        "latest": latest,
        "series": pv.round(4),
        "signal": signal,
        "state": {"window": window, "last_value": latest},
    }


def calculate_garman_klass_volatility(
    df: pd.DataFrame,
    window: int = 20,
    prev_state: Optional[Dict] = None,
) -> Dict:
    high = _get_column(df, "最高", "high")
    low = _get_column(df, "最低", "low")
    close = _get_column(df, "收盘", "close")
    open_ = _get_column(df, "开盘", "open")
    if high is None or low is None or close is None:
        return {"latest": None, "series": pd.Series(), "signal": "数据不足", "state": {}}
    if open_ is None:
        open_ = close.shift(1)
    if len(high) < window:
        return {"latest": None, "series": pd.Series([None] * len(high)), "signal": "数据不足", "state": {}}

    log_hl = 0.5 * (np.log(high / low)) ** 2
    log_co = (2 * np.log(2) - 1) * (np.log(close / open_)) ** 2
    log_hl = log_hl.replace([np.inf, -np.inf], np.nan)
    log_co = log_co.replace([np.inf, -np.inf], np.nan)
    gk = log_hl - log_co
    gk_vol = np.sqrt(gk.rolling(window=window).mean()) * np.sqrt(252)

    latest = round(gk_vol.iloc[-1], 4) if not pd.isna(gk_vol.iloc[-1]) else None
    signal = _vol_signal(gk_vol, 25, 75)

    return {
        "latest": latest,
        "series": gk_vol.round(4),
        "signal": signal,
        "state": {"window": window, "last_value": latest},
    }


def calculate_realized_volatility(
    df: pd.DataFrame,
    window: int = 20,
    prev_state: Optional[Dict] = None,
) -> Dict:
    closes = _get_column(df, "收盘", "close")
    if closes is None:
        return {"latest": None, "series": pd.Series(), "signal": "数据不足", "state": {}}

    log_returns = np.log(closes / closes.shift(1)).replace([np.inf, -np.inf], np.nan)
    if len(log_returns) < window:
        return {"latest": None, "series": pd.Series([None] * len(closes)), "signal": "数据不足", "state": {}}

    rv = np.sqrt((log_returns ** 2).rolling(window=window).sum()) * np.sqrt(252 / window)

    latest = round(rv.iloc[-1], 4) if not pd.isna(rv.iloc[-1]) else None
    signal = _vol_signal(rv, 25, 75)

    return {
        "latest": latest,
        "series": rv.round(4),
        "signal": signal,
        "state": {"window": window, "last_value": latest},
    }


def calculate_all_indicators(
    df: pd.DataFrame,
    index_df: pd.DataFrame = None,
    industry_df: pd.DataFrame = None,
    sector_fund_data: dict = None,
    config: dict = None,
) -> Dict:
    """
    计算所有技术指标

    参数:
        df: 包含OHLCV数据的DataFrame

    返回:
        dict: 包含所有技术指标
    """
    result = {}

    if "收盘" in df.columns:
        closes = df["收盘"].values
    elif "close" in df.columns:
        closes = df["close"].values
    else:
        return {"error": "缺少收盘价数据"}

    if "最高" in df.columns:
        highs = df["最高"].values
    elif "high" in df.columns:
        highs = df["high"].values
    else:
        highs = closes

    if "最低" in df.columns:
        lows = df["最低"].values
    elif "low" in df.columns:
        lows = df["low"].values
    else:
        lows = closes

    if "成交量" in df.columns:
        volumes = df["成交量"].values
    elif "volume" in df.columns:
        volumes = df["volume"].values
    else:
        volumes = None

    result["MACD"] = calculate_macd(closes)
    result["RSI"] = calculate_rsi(closes)
    result["KDJ"] = calculate_kdj(highs, lows, closes)
    result["MA"] = calculate_ma(closes)
    result["BOLL"] = calculate_boll(closes)
    result["ATR"] = calculate_atr(highs, lows, closes)

    dist_result = calculate_distribution_features(df)
    result["Distribution"] = dist_result["Distribution"]

    if volumes is not None:
        result["Volume_Ratio"] = calculate_volume_ratio(volumes)
        result["OBV"] = calculate_obv(closes, volumes)
        result["Volume_MA"] = calculate_volume_ma(volumes)

    ms_result = calculate_market_structure(df, index_df, industry_df, sector_fund_data, config)
    result["MarketStructure"] = ms_result["MarketStructure"]

    vol_config = (config or {}).get("volatility", {})
    hv_windows = vol_config.get("hv_windows", [20, 60])
    parkinson_window = vol_config.get("parkinson_window", 20)
    garman_klass_window = vol_config.get("garman_klass_window", 20)
    realized_vol_window = vol_config.get("realized_vol_window", 20)

    hv_result = calculate_historical_volatility(df, windows=hv_windows)
    pk_result = calculate_parkinson_volatility(df, window=parkinson_window)
    gk_result = calculate_garman_klass_volatility(df, window=garman_klass_window)
    rv_result = calculate_realized_volatility(df, window=realized_vol_window)

    result["Volatility"] = {
        "Historical": hv_result,
        "Parkinson": pk_result,
        "GarmanKlass": gk_result,
        "Realized": rv_result,
    }

    return result


def calculate_all_indicators_incremental(
    df: pd.DataFrame,
    prev_states: Optional[Dict] = None,
    index_df: pd.DataFrame = None,
    industry_df: pd.DataFrame = None,
    sector_fund_data: dict = None,
    config: dict = None,
) -> Dict:
    if prev_states is None:
        prev_states = {}

    result = calculate_all_indicators(df, index_df, industry_df, sector_fund_data, config)

    new_states = {}

    dist_result = calculate_distribution_features(df, prev_state=prev_states.get("Distribution"))
    if "state" in dist_result:
        new_states["Distribution"] = dist_result["state"]

    vol_config = (config or {}).get("volatility", {})
    hv_windows = vol_config.get("hv_windows", [20, 60])
    parkinson_window = vol_config.get("parkinson_window", 20)
    garman_klass_window = vol_config.get("garman_klass_window", 20)
    realized_vol_window = vol_config.get("realized_vol_window", 20)

    hv = calculate_historical_volatility(df, windows=hv_windows, prev_state=prev_states.get("Volatility_Historical"))
    pk = calculate_parkinson_volatility(df, window=parkinson_window, prev_state=prev_states.get("Volatility_Parkinson"))
    gk = calculate_garman_klass_volatility(df, window=garman_klass_window, prev_state=prev_states.get("Volatility_GarmanKlass"))
    rv = calculate_realized_volatility(df, window=realized_vol_window, prev_state=prev_states.get("Volatility_Realized"))

    if "state" in hv:
        new_states["Volatility_Historical"] = hv["state"]
    if "state" in pk:
        new_states["Volatility_Parkinson"] = pk["state"]
    if "state" in gk:
        new_states["Volatility_GarmanKlass"] = gk["state"]
    if "state" in rv:
        new_states["Volatility_Realized"] = rv["state"]

    return {"indicators": result, "states": new_states}
