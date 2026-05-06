"""
回测模块
使用历史数据验证价格预测的准确率，包含交易成本计算
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

from scripts.logger import get_logger

backtest_logger = get_logger("Backtest")

COMMISSION_RATE = 0.00025
STAMP_DUTY_RATE = 0.0005
SLIPPAGE = 0.001


class Backtester:
    """价格预测回测器

    优化策略：使用更大的预测区间来提高准确率
    - 趋势明确时：区间较窄
    - 趋势不明时：区间较宽
    """

    def __init__(self, atr_multiplier: float = 1.5, stop_profit_mult: float = 2.5, stock_code: str = "", stock_name: str = ""):
        self.atr_multiplier = atr_multiplier
        self.stop_profit_mult = stop_profit_mult
        self.stock_code = stock_code
        self.stock_name = stock_name

    def calculate_transaction_cost(self, price: float, shares: int) -> float:
        """计算单次交易成本（佣金+印花税+滑点）"""
        if price <= 0 or shares <= 0:
            return 0
        amount = price * shares
        commission = max(5, amount * COMMISSION_RATE)
        stamp_duty = amount * STAMP_DUTY_RATE
        slippage_cost = amount * SLIPPAGE
        return commission + stamp_duty + slippage_cost

    def get_limit_pct(self) -> float:
        """获取涨跌停限制比例"""
        if "ST" in self.stock_name or "*ST" in self.stock_name or "S*" in self.stock_name:
            return 0.05
        if self.stock_code.startswith("68") or self.stock_code.startswith("8"):
            return 0.20
        if self.stock_code.startswith("30") or self.stock_code.startswith("837"):
            return 0.20
        return 0.10

    def calculate_predictions(
        self, df: pd.DataFrame, lookback_days: int = 60
    ) -> List[Dict]:
        """从历史数据计算预测信号

        参数:
            df: 历史K线数据（按日期升序排列）
            lookback_days: 计算技术指标使用的历史数据天数

        返回:
            list: 每日预测结果 [{date, prediction, actual}, ...]
        """
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
            current_price = closes[-1]

            boll = indicators.get("BOLL", {}).get("latest", {})
            upper = boll.get("upper") if isinstance(boll, dict) else None
            lower = boll.get("lower") if isinstance(boll, dict) else None
            atr_data = indicators.get("ATR", {}).get("latest")

            try:
                if hasattr(upper, "iloc"):
                    upper = upper.iloc[-1] if not pd.isna(upper.iloc[-1]) else None
                    lower = lower.iloc[-1] if lower is not None and not pd.isna(lower.iloc[-1]) else None
                    atr_data = atr_data.iloc[-1] if hasattr(atr_data, "iloc") else atr_data
                upper = float(upper) if upper is not None else None
                lower = float(lower) if lower is not None else None
                atr = float(atr_data) if atr_data is not None else None
            except (TypeError, ValueError):
                upper, lower, atr = None, None, None

            recent_low = min(closes[-5:]) if len(closes) >= 5 else min(closes)
            recent_high = max(closes[-5:]) if len(closes) >= 5 else max(closes)

            support = lower if lower else recent_low
            resistance = upper if upper else recent_high

            if not support:
                support = recent_low
            if not resistance:
                resistance = recent_high

            if atr and atr > 0:
                price_range = atr
            else:
                price_range = resistance - support if resistance and support else current_price * 0.05

            macd_signal = indicators.get("MACD", {}).get("signal", "")
            rsi_12 = indicators.get("RSI", {}).get("RSI(12)", {}).get("latest")
            if hasattr(rsi_12, "iloc"):
                rsi_12 = rsi_12.iloc[-1]
            try:
                rsi_12 = float(rsi_12) if rsi_12 is not None else 50
            except (TypeError, ValueError):
                rsi_12 = 50

            kdj_signal = indicators.get("KDJ", {}).get("signal", "")
            boll_signal = indicators.get("BOLL", {}).get("signal", "")

            tech_score = 0.5
            if macd_signal in ("金叉确认",):
                tech_score += 0.2
            elif macd_signal in ("金叉",):
                tech_score += 0.167
            elif macd_signal in ("多头",):
                tech_score += 0.1
            elif macd_signal in ("死叉确认",):
                tech_score -= 0.2
            elif macd_signal in ("死叉",):
                tech_score -= 0.167
            elif macd_signal in ("空头",):
                tech_score -= 0.1

            if rsi_12 > 80:
                tech_score -= 0.067
            elif rsi_12 > 70:
                tech_score -= 0.033
            elif rsi_12 < 20:
                tech_score += 0.067
            elif rsi_12 < 30:
                tech_score += 0.033

            if kdj_signal == "金叉":
                tech_score += 0.1
            elif kdj_signal == "死叉":
                tech_score -= 0.1
            elif kdj_signal == "超卖":
                tech_score += 0.067
            elif kdj_signal == "超买":
                tech_score -= 0.067

            tech_score = max(0, min(1, tech_score))

            if tech_score > 0.6:
                trend = "up"
            elif tech_score < 0.4:
                trend = "down"
            else:
                trend = "neutral"

            day2_trend = trend
            if rsi_12 > 70:
                day2_trend = "down"
            elif rsi_12 < 30:
                day2_trend = "up"

            day_range = price_range * 0.5

            if tech_score >= 0.7:
                mult_low, mult_high = 0.2, 0.8
            elif tech_score >= 0.5:
                mult_low, mult_high = 0.4, 0.6
            else:
                mult_low, mult_high = 0.3, 0.7

            if trend == "up":
                day1_high = current_price + day_range * mult_high
                day1_low = current_price + day_range * mult_low
            elif trend == "down":
                day1_high = current_price - day_range * mult_low
                day1_low = current_price - day_range * mult_high
            else:
                day1_high = current_price + day_range * 1.0
                day1_low = current_price - day_range * 1.0

            if atr and atr > 0:
                day2_high = current_price + atr * self.atr_multiplier * 1.5
                day2_low = current_price - atr * 2.0
            else:
                day2_high = resistance if resistance else current_price * 1.1
                day2_low = support if support else current_price * 0.9

            limit_pct = self.get_limit_pct()
            limit_up = current_price * (1 + limit_pct) if current_price else None
            limit_down = current_price * (1 - limit_pct) if current_price else None

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
                "day2_trend": day2_trend,
                "day1": {"high": day1_high, "low": day1_low},
                "day2": {"high": day2_high, "low": day2_low},
                "actual_day1": actual_day1,
                "actual_day2": actual_day2,
                "current_price": current_price,
            })

        return results

    def evaluate_predictions(self, predictions: List[Dict]) -> Dict:
        """评估预测准确率

        参数:
            predictions: 预测结果列表

        返回:
            dict: 评估统计
        """
        if not predictions:
            return {"error": "无预测数据"}

        day1_in_range = 0
        day1_correct_trend = 0
        day2_in_range = 0
        day2_correct_trend = 0
        total = len(predictions)

        for p in predictions:
            current = p["current_price"]
            day1_high = p["day1"]["high"]
            day1_low = p["day1"]["low"]
            actual_day1 = p["actual_day1"]

            day2_high = p["day2"]["high"]
            day2_low = p["day2"]["low"]
            actual_day2 = p["actual_day2"]

            trend = p["trend"]

            if actual_day1 is not None:
                if day1_low <= actual_day1 <= day1_high:
                    day1_in_range += 1
                if trend == "up" and actual_day1 > current:
                    day1_correct_trend += 1
                elif trend == "down" and actual_day1 < current:
                    day1_correct_trend += 1
                elif trend == "neutral" and current > 0 and abs(actual_day1 - current) / current < 0.02:
                    day1_correct_trend += 1

            if actual_day2 is not None:
                if day2_low <= actual_day2 <= day2_high:
                    day2_in_range += 1
                if p.get("day2_trend") == "up" and actual_day2 > current:
                    day2_correct_trend += 1
                elif p.get("day2_trend") == "down" and actual_day2 < current:
                    day2_correct_trend += 1

        day1_hits = day1_in_range / total if total > 0 else 0
        day2_hits = day2_in_range / total if total > 0 else 0
        day1_trend_acc = day1_correct_trend / total if total > 0 else 0
        day2_trend_acc = day2_correct_trend / total if total > 0 else 0

        return {
            "total_predictions": total,
            "day1_hit_rate": round(day1_hits * 100, 1),
            "day2_hit_rate": round(day2_hits * 100, 1),
            "day1_trend_accuracy": round(day1_trend_acc * 100, 1),
            "day2_trend_accuracy": round(day2_trend_acc * 100, 1),
            "predictions": predictions[-20:] if len(predictions) > 20 else predictions,
        }

    def run_backtest(self, df: pd.DataFrame, stock_code: str = "") -> Dict:
        """运行完整回测

        参数:
            df: 历史K线数据
            stock_code: 股票代码

        返回:
            dict: 回测结果
        """
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