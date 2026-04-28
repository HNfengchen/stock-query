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
        avg_diff = (dif - dea).abs().tail(20).mean()
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
            if latest > 80:
                signal = "超买"
            elif latest < 20:
                signal = "超卖"
            elif latest > 70:
                signal = "偏强"
            elif latest < 30:
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
    rsv = rsv.fillna(50)

    k = pd.Series([np.nan] * len(close), index=close.index)
    d = pd.Series([np.nan] * len(close), index=close.index)
    k.iloc[0] = 50.0
    d.iloc[0] = 50.0

    for i in range(1, len(rsv)):
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
    std = closes.rolling(window=n).std(ddof=0)

    upper = middle + k * std
    lower = middle - k * std

    bandwidth = ((upper - middle) / middle * 100).round(2)
    pct_b = ((closes - lower) / (upper - lower) * 100).round(2)

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
    result["ATR"] = calculate_atr(highs, lows, closes)

    if volumes is not None:
        result["Volume_Ratio"] = calculate_volume_ratio(volumes)
        result["OBV"] = calculate_obv(closes, volumes)
        result["Volume_MA"] = calculate_volume_ma(volumes)

    return result
