"""交叉验证阈值校准模块"""

from copy import deepcopy
from typing import Optional

import pandas as pd


def evaluate_validation_config(
    config: dict,
    stock_codes: list[str],
    lookback_days: int = 120,
    fetcher=None,
) -> dict:
    """
    对给定的 validation 配置运行滑动窗口历史评估。

    对每只股票，取 last 2*lookback_days 历史数据，
    从 lookback_days 开始逐日滑动：
    - 用截至当天的数据计算指标
    - 调 StockAnalyzer 做预测 + 交叉验证
    - 对比预测方向与次日的实际方向

    返回聚合指标。
    """
    from scripts.core.analyzer import StockAnalyzer
    from scripts.technical_indicators import calculate_all_indicators

    analyzer = StockAnalyzer(config)
    all_predictions = []

    for code in (stock_codes or []):
        if fetcher is None:
            continue
        try:
            df = fetcher.fetch_history_data(code, lookback_days * 2 + 20)
        except Exception:
            continue
        if df is None or len(df) < lookback_days + 5:
            continue

        df = df.reset_index(drop=True)
        min_idx = lookback_days + 1

        for test_idx in range(min_idx, len(df) - 1):
            history_up_to = df.iloc[:test_idx + 1].copy()
            current_close = float(history_up_to["收盘"].iloc[-1])
            actual_next_close = float(df["收盘"].iloc[test_idx + 1])
            actual_trend = "up" if actual_next_close >= current_close else "down"

            indicators = calculate_all_indicators(history_up_to)

            technical = analyzer.analyze_technical(indicators, current_close)
            analysis = {
                "technical": technical,
                "fund_flow": {"score": 0.5, "trend": "neutral"},
                "sentiment": {"score": 0.5},
            }
            trading_signal = analyzer.generate_trading_signal(analysis, "未持有")

            all_data = {
                "history_data": history_up_to,
                "stock_info": {"最新价": current_close},
                "stock_code": code,
                "indicators": indicators,
                "technical_analysis": technical,
            }
            price_pred = analyzer.predict_price_range(
                all_data, indicators, code, trading_signal
            )
            validation = analyzer.cross_validate_analysis(
                analysis, price_pred, indicators, trading_signal, "未持有", current_close
            )

            day1_trend = price_pred.get("day1", {}).get("trend", "")
            consensus = validation.get("direction_consensus", "")

            all_predictions.append({
                "stock_code": code,
                "date": str(test_idx),
                "consensus": consensus,
                "predicted_trend": day1_trend,
                "actual_trend": actual_trend,
                "confidence": validation.get("confidence", 0),
            })

    total = len(all_predictions) or 1
    correct_consensus = sum(
        1 for p in all_predictions
        if (p["consensus"] == "bullish" and p["actual_trend"] == "up")
        or (p["consensus"] == "bearish" and p["actual_trend"] == "down")
    )
    correct_trend = sum(
        1 for p in all_predictions
        if p["predicted_trend"] == p["actual_trend"]
    )
    has_consensus = sum(
        1 for p in all_predictions if p["consensus"] in ("bullish", "bearish")
    )
    correct_when_has_consensus = sum(
        1 for p in all_predictions
        if p["consensus"] in ("bullish", "bearish")
        and ((p["consensus"] == "bullish" and p["actual_trend"] == "up")
             or (p["consensus"] == "bearish" and p["actual_trend"] == "down"))
    )

    return {
        "accuracy": correct_trend / total,
        "trend_accuracy": correct_trend / total,
        "consistency": correct_when_has_consensus / (has_consensus or 1),
        "total_predictions": total,
        "predictions_with_consensus": has_consensus,
        "_raw": all_predictions,
    }
