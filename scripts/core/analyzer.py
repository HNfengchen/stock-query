"""
分析逻辑层
负责综合分析：技术指标、资金流向、市场情绪，生成买卖建议
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from scripts.logger import get_logger

analyzer_logger = get_logger("Analyzer")


class AnalysisError(Exception):
    """分析错误"""

    pass


class StockAnalyzer:
    """股票分析器"""

    def __init__(self, config: dict):
        self.config = config
        self.weights = config.get("analyzer", {}).get("weights", {})
        self.thresholds = config.get("analyzer", {}).get("thresholds", {})
        self.prediction_config = config.get("analyzer", {}).get("price_prediction", {})

    def analyze_technical(self, indicators: Dict) -> Dict:
        """分析技术指标"""
        analyzer_logger.info("=" * 50)
        analyzer_logger.info("开始技术指标分析...")

        result = {"score": 0, "details": {}, "signals": []}

        if "error" in indicators:
            analyzer_logger.warning(f"技术指标计算出错: {indicators.get('error')}")
            result["error"] = indicators["error"]
            return result

        macd = indicators.get("MACD", {})
        rsi = indicators.get("RSI", {})
        kdj = indicators.get("KDJ", {})
        boll = indicators.get("BOLL", {})

        analyzer_logger.debug(f"MACD信号: {macd.get('signal', 'N/A')}")
        analyzer_logger.debug(f"RSI数据: {rsi}")
        analyzer_logger.debug(f"KDJ信号: {kdj.get('signal', 'N/A')}")

        score = 0
        signals = []

        # MACD 分析
        macd_signal = macd.get("signal", "")
        if macd_signal == "金叉":
            score += 25
            signals.append("MACD 金叉")
        elif macd_signal == "死叉":
            score -= 25
            signals.append("MACD 死叉")
        elif macd_signal == "多头":
            score += 15
            signals.append("MACD 多头")
        elif macd_signal == "空头":
            score -= 15
            signals.append("MACD 空头")

        # RSI 分析
        for key, val in rsi.items():
            if val.get("status") == "超卖":
                score += 10
                signals.append(f"{key}超卖")
            elif val.get("status") == "超买":
                score -= 10
                signals.append(f"{key}超买")

        # KDJ 分析
        kdj_signal = kdj.get("signal", "")
        if kdj_signal == "金叉":
            score += 15
            signals.append("KDJ 金叉")
        elif kdj_signal == "死叉":
            score -= 15
            signals.append("KDJ 死叉")
        elif kdj_signal == "超卖":
            score += 10
            signals.append("KDJ 超卖")
        elif kdj_signal == "超买":
            score -= 10
            signals.append("KDJ 超买")

        # 归一化到 0-1 范围
        normalized_score = max(0, min(1, (score + 50) / 100))

        result["score"] = normalized_score
        result["details"] = {"MACD": macd, "RSI": rsi, "KDJ": kdj, "BOLL": boll}
        result["signals"] = signals

        return result

    def analyze_fund_flow(self, fund_flow: Dict) -> Dict:
        """分析资金流向"""
        result = {"score": 0, "details": {}, "trend": "neutral"}

        if "error" in fund_flow:
            result["error"] = fund_flow["error"]
            return result

        main_inflow = fund_flow.get("主力净流入", 0)
        ratio = fund_flow.get("主力净流入占比", 0)

        score = 0
        trend = "neutral"

        if main_inflow > 0:
            if main_inflow > 10000:
                score = 1.0
                trend = "inflow"
            elif main_inflow > 5000:
                score = 0.7
                trend = "inflow"
            elif main_inflow > 0:
                score = 0.4
                trend = "inflow"
        else:
            if main_inflow < -10000:
                score = 0
                trend = "outflow"
            elif main_inflow < -5000:
                score = 0.3
                trend = "outflow"
            else:
                score = 0.5
                trend = "neutral"

        history = fund_flow.get("历史数据", [])
        if len(history) >= 3:
            recent_inflows = [h.get("主力净流入", 0) for h in history[-3:]]
            if all(x > 0 for x in recent_inflows):
                score = min(1.0, score + 0.2)
                trend = "inflow"
            elif all(x < 0 for x in recent_inflows):
                score = max(0, score - 0.2)
                trend = "outflow"

        result["score"] = score
        result["details"] = {
            "main_inflow": main_inflow,
            "ratio": ratio,
            "history": history,
        }
        result["trend"] = trend

        return result

    def analyze_market_sentiment(self, data: Dict) -> Dict:
        """分析市场情绪"""
        result = {"score": 0.5, "details": {}}

        info = data.get("stock_info", {})

        turnover = info.get("换手率", 0)
        volume_ratio = info.get("量比", 0)

        score = 0.5

        try:
            turnover = (
                float(turnover.replace("%", ""))
                if isinstance(turnover, str)
                else float(turnover)
            )
            if turnover > 15:
                score += 0.2
            elif turnover > 8:
                score += 0.1
            elif turnover < 2:
                score -= 0.1
        except:
            pass

        try:
            volume_ratio = float(volume_ratio) if volume_ratio else 1.0
            if volume_ratio > 2:
                score += 0.2
            elif volume_ratio > 1.5:
                score += 0.1
            elif volume_ratio < 0.5:
                score -= 0.1
        except:
            pass

        result["score"] = max(0, min(1, score))
        result["details"] = {"turnover": turnover, "volume_ratio": volume_ratio}

        return result

    def generate_trading_signal(self, analysis: Dict) -> Dict:
        """生成交易信号"""
        analyzer_logger.info("=" * 50)
        analyzer_logger.info("开始生成交易信号...")

        technical_score = analysis.get("technical", {}).get("score", 0.5)
        fund_flow_score = analysis.get("fund_flow", {}).get("score", 0.5)
        sentiment_score = analysis.get("sentiment", {}).get("score", 0.5)

        analyzer_logger.info(f"技术评分: {technical_score:.3f}")
        analyzer_logger.info(f"资金评分: {fund_flow_score:.3f}")
        analyzer_logger.info(f"情绪评分: {sentiment_score:.3f}")

        weights = self.weights
        total_score = (
            technical_score * weights.get("technical", 0.5)
            + fund_flow_score * weights.get("fund_flow", 0.3)
            + sentiment_score * weights.get("sentiment", 0.2)
        )

        analyzer_logger.info(f"权重配置: {weights}")
        analyzer_logger.info(f"综合评分: {total_score:.3f}")

        thresholds = self.thresholds
        signal = "hold"
        if total_score >= thresholds.get("strong_buy", 0.7):
            signal = "strong_buy"
            analyzer_logger.info(
                f"信号判定: 强烈买入 (阈值: {thresholds.get('strong_buy', 0.7)})"
            )
        elif total_score >= thresholds.get("buy", 0.5):
            signal = "buy"
            analyzer_logger.info(f"信号判定: 买入 (阈值: {thresholds.get('buy', 0.5)})")
        elif total_score >= thresholds.get("hold", 0.3):
            signal = "hold"
            analyzer_logger.info(
                f"信号判定: 持有 (阈值: {thresholds.get('hold', 0.3)})"
            )
        elif total_score > 0:
            signal = "watch"
        else:
            signal = "sell"

        return {
            "score": round(total_score, 3),
            "signal": signal,
            "signal_text": {
                "strong_buy": "强烈买入",
                "buy": "买入",
                "hold": "持有",
                "watch": "观望",
                "sell": "卖出",
            }.get(signal, "持有"),
        }

    def predict_price_range(self, data: Dict, indicators: Dict) -> Dict:
        """预测价格区间（含未来两天预测）"""
        analyzer_logger.info("=" * 50)
        analyzer_logger.info("开始价格预测...")

        info = data.get("stock_info", {})
        history_df = data.get("history_data")

        current_price = info.get("最新价", 0)
        try:
            current_price = float(current_price)
        except:
            current_price = 0

        analyzer_logger.info(f"当前价格: {current_price}")

        if current_price == 0 or history_df is None or history_df.empty:
            analyzer_logger.warning("数据不足，无法进行价格预测")
            return {
                "current": current_price,
                "support": None,
                "resistance": None,
                "day1": {"target_low": None, "target_high": None, "trend": "neutral"},
                "day2": {"target_low": None, "target_high": None, "trend": "neutral"},
            }

        boll = indicators.get("BOLL", {})
        lower = boll.get("lower")
        upper = boll.get("upper")

        analyzer_logger.debug(f"布林带: lower={lower}, upper={upper}")

        if isinstance(lower, pd.Series) and not lower.empty:
            lower = lower.iloc[-1]
        if isinstance(upper, pd.Series) and not upper.empty:
            upper = upper.iloc[-1]

        try:
            lower = float(lower) if lower is not None else None
            upper = float(upper) if upper is not None else None
        except (TypeError, ValueError):
            lower, upper = None, None

        if "收盘" in history_df.columns:
            closes = history_df["收盘"].values
        else:
            closes = history_df["close"].values

        recent_low = min(closes[-5:]) if len(closes) >= 5 else min(closes)
        recent_high = max(closes[-5:]) if len(closes) >= 5 else max(closes)

        support = lower if lower else recent_low
        resistance = upper if upper else recent_high

        if not support:
            support = recent_low
        if not resistance:
            resistance = recent_high

        trend = "neutral"
        technical_analysis = data.get("technical_analysis", {})
        if technical_analysis.get("score", 0.5) > 0.6:
            trend = "up"
        elif technical_analysis.get("score", 0.5) < 0.4:
            trend = "down"

        atr_mult = self.prediction_config.get("atr_multiplier", 1.5)
        price_range = resistance - support
        day_range = price_range * 0.5

        if trend == "up":
            base_target_high = current_price + price_range * atr_mult
            base_target_low = current_price + price_range * 0.3
        elif trend == "down":
            base_target_high = current_price + price_range * 0.3
            base_target_low = current_price - price_range * atr_mult
        else:
            base_target_low = support
            base_target_high = resistance

        day1_trend = trend
        day2_trend = trend

        macd = indicators.get("MACD", {}).get("signal", "")
        rsi = indicators.get("RSI", {}).get("RSI(6)", {}).get("status", "")

        if rsi == "超买":
            day2_trend = "down"
        elif rsi == "超卖":
            day2_trend = "up"

        if trend == "up":
            day1 = {
                "target_low": round(current_price + day_range * 0.3, 2),
                "target_high": round(current_price + day_range * 0.7, 2),
                "trend": day1_trend,
                "signal": "看涨延续",
            }
            day2 = {
                "target_low": round(base_target_low + day_range * 0.5, 2),
                "target_high": round(base_target_high, 2),
                "trend": day2_trend,
                "signal": "持续上涨" if day2_trend == "up" else "注意回调",
            }
        elif trend == "down":
            day1 = {
                "target_low": round(current_price - day_range * 0.7, 2),
                "target_high": round(current_price - day_range * 0.3, 2),
                "trend": day1_trend,
                "signal": "看跌延续",
            }
            day2 = {
                "target_low": round(base_target_low, 2),
                "target_high": round(base_target_high - day_range * 0.5, 2),
                "trend": day2_trend,
                "signal": "持续下跌" if day2_trend == "down" else "注意反弹",
            }
        else:
            day1 = {
                "target_low": round(support, 2),
                "target_high": round(current_price + day_range * 0.5, 2),
                "trend": "neutral",
                "signal": "震荡整理",
            }
            day2 = {
                "target_low": round(support, 2),
                "target_high": round(resistance, 2),
                "trend": "neutral",
                "signal": "等待突破",
            }

        result = {
            "current": current_price,
            "support": round(support, 2) if support else None,
            "resistance": round(resistance, 2) if resistance else None,
            "target_low": round(base_target_low, 2) if base_target_low else None,
            "target_high": round(base_target_high, 2) if base_target_high else None,
            "trend": trend,
            "day1": day1,
            "day2": day2,
        }

        analyzer_logger.info("价格预测结果:")
        analyzer_logger.info(f"  支撑位: {result.get('support')}")
        analyzer_logger.info(f"  压力位: {result.get('resistance')}")
        analyzer_logger.info(f"  目标低价: {result.get('target_low')}")
        analyzer_logger.info(f"  目标高价: {result.get('target_high')}")
        analyzer_logger.info(f"  趋势判断: {trend}")
        analyzer_logger.info(
            f"  Day1预测: {day1.get('target_low')}-{day1.get('target_high')} ({day1.get('trend')})"
        )
        analyzer_logger.info(
            f"  Day2预测: {day2.get('target_low')}-{day2.get('target_high')} ({day2.get('trend')})"
        )

        return result

    def generate_recommendation(self, all_data: Dict) -> Dict:
        """生成完整的买卖建议"""
        from scripts.technical_indicators import calculate_all_indicators

        history_df = all_data.get("history_data")
        if history_df is not None and not history_df.empty:
            indicators = calculate_all_indicators(history_df)
        else:
            indicators = {"error": "无法计算技术指标"}

        all_data["indicators"] = indicators

        technical_analysis = self.analyze_technical(indicators)
        fund_flow_analysis = self.analyze_fund_flow(all_data.get("fund_flow", {}))
        sentiment_analysis = self.analyze_market_sentiment(all_data)

        all_data["technical_analysis"] = technical_analysis

        analysis = {
            "technical": technical_analysis,
            "fund_flow": fund_flow_analysis,
            "sentiment": sentiment_analysis,
        }

        trading_signal = self.generate_trading_signal(analysis)
        price_prediction = self.predict_price_range(all_data, indicators)

        return {
            "analysis": analysis,
            "trading_signal": trading_signal,
            "price_prediction": price_prediction,
            "indicators": indicators,
        }
