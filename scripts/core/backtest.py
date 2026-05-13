"""回测模块
使用历史数据验证价格预测的准确率，包含交易成本计算
策略与分析窗口(analyzer.py predict_price_range)保持一致
"""

import pandas as pd
import numpy as np
from typing import Dict, List
from datetime import datetime

from scripts.core.analyzer import (
    StockAnalyzer,
    TREND_STRONG_UP, TREND_UP, TREND_NEUTRAL, TREND_DOWN, TREND_STRONG_DOWN,
    STRONG_THRESHOLD, NORMAL_THRESHOLD,
)

from scripts.logger import get_logger

backtest_logger = get_logger("Backtest")

COMMISSION_RATE = 0.00025
STAMP_DUTY_RATE = 0.0005
SLIPPAGE = 0.001


class Backtester:
    """价格预测回测器

    策略与分析窗口(analyzer.py predict_price_range)保持一致
    通过直接调用 analyzer.predict_price_range() 确保预测逻辑完全相同
    """

    def __init__(self, atr_multiplier: float = 1.5, stop_profit_mult: float = 2.5, stock_code: str = "", stock_name: str = "", config: dict = None):
        self.atr_multiplier = atr_multiplier
        self.stop_profit_mult = stop_profit_mult
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.config = config
        self._analyzer = None

    @property
    def analyzer(self) -> StockAnalyzer:
        if self._analyzer is None:
            if self.config is None:
                import yaml
                with open("config/config.yaml") as f:
                    self.config = yaml.safe_load(f)
            self._analyzer = StockAnalyzer(self.config)
        return self._analyzer

    def calculate_transaction_cost(self, price: float, shares: int) -> float:
        if price <= 0 or shares <= 0:
            return 0
        amount = price * shares
        commission = max(5, amount * COMMISSION_RATE)
        stamp_duty = amount * STAMP_DUTY_RATE
        slippage_cost = amount * SLIPPAGE
        return commission + stamp_duty + slippage_cost

    def get_limit_pct(self) -> float:
        name_upper = str(self.stock_name).upper()
        if "ST" in name_upper or "*ST" in name_upper or "S*" in name_upper:
            return 0.05
        if self.stock_code.startswith("30") or self.stock_code.startswith("68"):
            return 0.20
        return 0.10

    def calculate_predictions(
        self, df: pd.DataFrame, lookback_days: int = 60
    ) -> List[Dict]:
        """从历史数据计算预测信号 - 直接调用 analyzer.predict_price_range() 确保一致"""
        if df is None or len(df) < lookback_days + 10:
            return []

        from scripts.technical_indicators import calculate_all_indicators

        results = []
        n = len(df)

        for i in range(lookback_days, n - 2):
            window_df = df.iloc[i - lookback_days + 1 : i + 1].copy()

            indicators = calculate_all_indicators(window_df)
            if "error" in indicators:
                continue

            closes = window_df["收盘"].values
            current_price = float(closes[-1])

            technical_analysis = self.analyzer.analyze_technical(indicators, current_price)

            all_data = {
                "history_data": window_df,
                "stock_info": {"最新价": current_price, "名称": self.stock_name},
                "stock_code": self.stock_code,
                "indicators": indicators,
                "technical_analysis": technical_analysis,
            }

            trading_signal = self.analyzer.generate_trading_signal(
                {"technical": technical_analysis, "fund_flow": {}, "sentiment": {}},
                "未持有",
            )

            try:
                prediction = self.analyzer.predict_price_range(
                    all_data, indicators, self.stock_code, trading_signal
                )
            except Exception as e:
                backtest_logger.warning(f"预测失败(i={i}): {e}")
                continue

            trend = prediction.get("trend", TREND_NEUTRAL)
            day1 = prediction.get("day1", {})
            day2 = prediction.get("day2", {})

            day1_low = day1.get("target_low")
            day1_high = day1.get("target_high")
            day2_low = day2.get("target_low")
            day2_high = day2.get("target_high")

            limit_pct = self.get_limit_pct()
            limit_up = current_price * (1 + limit_pct) if current_price else None
            limit_down = current_price * (1 - limit_pct) if current_price else None

            if limit_up and day1_high:
                day1_high = min(day1_high, limit_up)
            if limit_down and day1_low:
                day1_low = max(day1_low, limit_down)
            if limit_up and day2_high:
                day2_high = min(day2_high, limit_up)
            if limit_down and day2_low:
                day2_low = max(day2_low, limit_down)

            prediction_date = df.index[i] if hasattr(df.index, "__getitem__") else df.iloc[i]["日期"]
            actual_day1 = df.iloc[i + 1]["收盘"] if i + 1 < n else None
            actual_day2 = df.iloc[i + 2]["收盘"] if i + 2 < n else None

            results.append({
                "date": str(prediction_date),
                "trend": trend,
                "day2_trend": day2.get("trend", trend),
                "day1": {"high": round(day1_high, 2) if day1_high else None, "low": round(day1_low, 2) if day1_low else None},
                "day2": {"high": round(day2_high, 2) if day2_high else None, "low": round(day2_low, 2) if day2_low else None},
                "actual_day1": actual_day1,
                "actual_day2": actual_day2,
                "current_price": current_price,
            })

        return results

    def evaluate_predictions(self, predictions: List[Dict]) -> Dict:
        if not predictions:
            return {"error": "无预测数据"}

        day1_in_range = 0
        day1_correct_trend = 0
        day2_in_range = 0
        day2_correct_trend = 0
        total = len(predictions)
        width_pct_values = []
        midpoint_mae_pct_values = []

        for p in predictions:
            current = p["current_price"]
            day1_high = p["day1"]["high"]
            day1_low = p["day1"]["low"]
            actual_day1 = p["actual_day1"]

            if current and current > 0 and day1_high is not None and day1_low is not None:
                width_pct = (day1_high - day1_low) / current
                if width_pct >= 0:
                    width_pct_values.append(width_pct)
                    if actual_day1 is not None:
                        midpoint = (day1_high + day1_low) / 2
                        midpoint_mae_pct_values.append(abs(actual_day1 - midpoint) / current)

            day2_high = p["day2"]["high"]
            day2_low = p["day2"]["low"]
            actual_day2 = p["actual_day2"]

            trend = p["trend"]

            if actual_day1 is not None and day1_low is not None and day1_high is not None:
                if day1_low <= actual_day1 <= day1_high:
                    day1_in_range += 1
            if actual_day1 is not None and current is not None and current > 0:
                actual_change = (actual_day1 - current) / current
                if trend == TREND_STRONG_UP and actual_change > STRONG_THRESHOLD:
                    day1_correct_trend += 1
                elif trend == TREND_UP and actual_change > NORMAL_THRESHOLD:
                    day1_correct_trend += 1
                elif trend == TREND_NEUTRAL and abs(actual_change) <= NORMAL_THRESHOLD:
                    day1_correct_trend += 1
                elif trend == TREND_DOWN and actual_change < -NORMAL_THRESHOLD:
                    day1_correct_trend += 1
                elif trend == TREND_STRONG_DOWN and actual_change < -STRONG_THRESHOLD:
                    day1_correct_trend += 1

            if actual_day2 is not None and day2_low is not None and day2_high is not None:
                if day2_low <= actual_day2 <= day2_high:
                    day2_in_range += 1
            if actual_day2 is not None and current is not None and current > 0:
                if p.get("day2_trend") in (TREND_STRONG_UP, TREND_UP) and actual_day2 > current:
                    day2_correct_trend += 1
                elif p.get("day2_trend") in (TREND_STRONG_DOWN, TREND_DOWN) and actual_day2 < current:
                    day2_correct_trend += 1

        day1_hits = day1_in_range / total if total > 0 else 0
        day2_hits = day2_in_range / total if total > 0 else 0
        day1_trend_acc = day1_correct_trend / total if total > 0 else 0
        day2_trend_acc = day2_correct_trend / total if total > 0 else 0
        mean_width_pct = float(np.mean(width_pct_values)) if width_pct_values else 0.0
        median_width_pct = float(np.median(width_pct_values)) if width_pct_values else 0.0
        midpoint_mae_pct = float(np.mean(midpoint_mae_pct_values)) if midpoint_mae_pct_values else 0.0
        coverage_width_score = day1_hits - mean_width_pct

        return {
            "total_predictions": total,
            "day1_hit_rate": round(day1_hits * 100, 1),
            "day2_hit_rate": round(day2_hits * 100, 1),
            "day1_trend_accuracy": round(day1_trend_acc * 100, 1),
            "day2_trend_accuracy": round(day2_trend_acc * 100, 1),
            "mean_width_pct": round(mean_width_pct, 4),
            "median_width_pct": round(median_width_pct, 4),
            "midpoint_mae_pct": round(midpoint_mae_pct, 4),
            "coverage_width_score": round(coverage_width_score, 4),
            "predictions": predictions[-20:] if len(predictions) > 20 else predictions,
        }

    def run_backtest(self, df: pd.DataFrame, stock_code: str = "") -> Dict:
        backtest_logger.info(f"开始回测 {stock_code}，数据量: {len(df) if df is not None else 0}")

        if df is None or df.empty:
            return {"error": "无历史数据"}

        df = df.copy()
        if "日期" in df.columns:
            df["日期"] = pd.to_datetime(df["日期"])
            df = df.sort_values("日期")

        predictions = self.calculate_predictions(df)
        if not predictions:
            return {"error": "数据量不足，无法回测"}

        stats = self.evaluate_predictions(predictions)

        backtest_logger.info(f"回测完成: Day1准确率={stats['day1_hit_rate']}%, Day2准确率={stats['day2_hit_rate']}%")

        return {
            "stock_code": stock_code,
            "backtest_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "data_range": f"{df.index[0] if hasattr(df.index, '__getitem__') else df.iloc[0]['日期']} ~ {df.index[-1] if hasattr(df.index, '__getitem__') else df.iloc[-1]['日期']}",
            "statistics": stats,
        }
