"""
技术指标计算模块
提供 MACD、RSI、KDJ 等常用技术指标的计算功能
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Union


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
        dict: 包含DIF、DEA、MACD柱的序列和信号
    """
    if len(close_prices) < slow + signal:
        return {
            "DIF": pd.Series([None] * len(close_prices)),
            "DEA": pd.Series([None] * len(close_prices)),
            "MACD": pd.Series([None] * len(close_prices)),
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

    if len(dif) >= 2:
        if dif.iloc[-1] > dea.iloc[-1] and dif.iloc[-2] <= dea.iloc[-2]:
            signal_text = "金叉"
        elif dif.iloc[-1] < dea.iloc[-1] and dif.iloc[-2] >= dea.iloc[-2]:
            signal_text = "死叉"
        elif dif.iloc[-1] > dea.iloc[-1]:
            signal_text = "多头"
        else:
            signal_text = "空头"
    else:
        signal_text = "数据不足"

    return {
        "DIF": dif_series,
        "DEA": dea_series,
        "MACD": macd_series,
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
                "value": pd.Series([None] * len(closes)),
                "status": "数据不足",
            }
            continue

        gain = deltas.where(deltas > 0, 0)
        loss = -deltas.where(deltas < 0, 0)

        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()

        rs = avg_gain / avg_loss.replace(0, np.inf)
        rsi = 100 - (100 / (1 + rs))

        rsi_series[period] = rsi.round(2)

        value = round(rsi.iloc[-1], 2) if not pd.isna(rsi.iloc[-1]) else None

        if value is not None:
            if value > 80:
                status = "超买"
            elif value < 20:
                status = "超卖"
            elif value > 70:
                status = "偏强"
            elif value < 30:
                status = "偏弱"
            else:
                status = "正常"
        else:
            status = "数据不足"

        result[f"RSI({period})"] = {"value": rsi_series[period], "status": status}

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
    rsv = rsv.fillna(50)

    k = rsv.ewm(com=m1 - 1, adjust=False).mean()
    d = k.ewm(com=m2 - 1, adjust=False).mean()
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

    return {"K": k_series, "D": d_series, "J": j_series, "signal": signal_text}


def calculate_ma(
    close_prices: Union[List, pd.Series], periods: List[int] = [5, 10, 20, 60]
) -> Dict:
    """
    计算移动平均线

    参数:
        close_prices: 收盘价序列
        periods: 均线周期列表，默认[5, 10, 20, 60]

    返回:
        dict: 包含各周期均线值的序列
    """
    closes = pd.Series(close_prices)
    result = {}

    for period in periods:
        if len(closes) >= period:
            ma = closes.rolling(window=period).mean()
            result[f"MA{period}"] = ma.round(2)
        else:
            result[f"MA{period}"] = pd.Series([None] * len(closes))

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
        dict: 包含上轨、中轨、下轨的序列
    """
    closes = pd.Series(close_prices)
    length = len(closes)

    if length < n:
        return {
            "upper": pd.Series([None] * length),
            "middle": pd.Series([None] * length),
            "lower": pd.Series([None] * length),
        }

    middle = closes.rolling(window=n).mean()
    std = closes.rolling(window=n).std()

    upper = middle + k * std
    lower = middle - k * std

    return {
        "upper": upper.round(2),
        "middle": middle.round(2),
        "lower": lower.round(2),
    }


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
            status = "巨量"
        elif vr > 1.5:
            status = "放量"
        elif vr > 0.8:
            status = "正常"
        else:
            status = "缩量"
    else:
        vr = None
        status = "数据异常"

    return {"volume_ratio": vr, "status": status}


def calculate_all_indicators(df: pd.DataFrame) -> Dict:
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

    if volumes is not None:
        result["Volume_Ratio"] = calculate_volume_ratio(volumes)

    return result
