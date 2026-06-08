"""
分析逻辑层
负责综合分析：技术指标、资金流向、市场情绪，生成买卖建议
"""

import os
import pandas as pd
import numpy as np
from collections import deque
from typing import Dict, Optional
from scripts.logger import get_logger
from scripts.core.feature_engineering import (
    extract_feature_vector,
    compute_feature_correlation,
    orthogonalize_features,
)
from scripts.core.regime_detector import DynamicWeightManager, HMMRegimeDetector
from scripts.core.ml_model import LightGBMPredictor, hybrid_predict

analyzer_logger = get_logger("analyzer")

TREND_STRONG_UP = "strong_up"
TREND_UP = "up"
TREND_NEUTRAL = "neutral"
TREND_DOWN = "down"
TREND_STRONG_DOWN = "strong_down"

TREND_ALL = [TREND_STRONG_UP, TREND_UP, TREND_NEUTRAL, TREND_DOWN, TREND_STRONG_DOWN]

STRONG_THRESHOLD = 0.03
NORMAL_THRESHOLD = 0.01


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
        self.validation_config = config.get("analyzer", {}).get("validation", {})
        self._dynamic_weight_manager = DynamicWeightManager(config)
        self._market_regime = None

        self._ml_config = config.get("ml_model", {})
        self._ml_enabled = self._ml_config.get("enabled", False)
        self._ml_alpha = self._ml_config.get("alpha", 0.5)
        self._ml_predictor = LightGBMPredictor(config)
        self._ml_loaded_stock = None  # 当前加载模型的股票代码

        hmm_config = config.get("hmm", {})
        self._hmm_detector = None
        self._regime_detector = None
        if hmm_config.get("enabled", False):
            self._hmm_detector = HMMRegimeDetector(
                n_components=hmm_config.get("n_components", 4),
                config=hmm_config,
            )
            model_path = hmm_config.get("model_path", "")
            if model_path:
                self._hmm_detector.load(model_path)
            if self._hmm_detector.is_ready():
                self._dynamic_weight_manager.set_hmm_detector(self._hmm_detector)
            else:
                from scripts.core.regime_detector import RegimeDetector
                self._regime_detector = RegimeDetector(config=hmm_config)

        self._stress_test_config = config.get("stress_test", {})
        self._pending_stress_test = None
        self._feature_history = deque(maxlen=20)

    def analyze_technical(self, indicators: Dict, current_price: float = 0) -> Dict:
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
        ma = indicators.get("MA", {})
        atr = indicators.get("ATR", {})

        analyzer_logger.debug(f"MACD信号: {macd.get('signal', 'N/A')}")
        analyzer_logger.debug(f"RSI数据: {rsi}")
        analyzer_logger.debug(f"KDJ信号: {kdj.get('signal', 'N/A')}")

        score = 0
        signals = []

        # --- MACD 分析 ---
        macd_signal = macd.get("signal", "")
        if macd_signal == "金叉确认":
            score += 25
            signals.append("MACD 金叉确认")
        elif macd_signal == "金叉":
            score += 20
            signals.append("MACD 金叉")
        elif macd_signal == "死叉确认":
            score -= 25
            signals.append("MACD 死叉确认")
        elif macd_signal == "死叉":
            score -= 20
            signals.append("MACD 死叉")
        elif macd_signal == "多头":
            score += 10
            signals.append("MACD 多头")
        elif macd_signal == "空头":
            score -= 10
            signals.append("MACD 空头")

        # --- RSI 分析 ---
        rsi_12 = rsi.get("RSI(12)", {})
        rsi_signal = rsi_12.get("signal", "") if isinstance(rsi_12, dict) else ""
        rsi_12_val = None
        if isinstance(rsi_12, dict):
            try:
                v = rsi_12.get("latest")
                rsi_12_val = float(v) if not hasattr(v, 'iloc') else float(v.iloc[-1])
            except (TypeError, ValueError):
                pass

        if rsi_signal == "超卖":
            score += 20
            signals.append("RSI(12)超卖")
        elif rsi_signal == "超买":
            score -= 20
            signals.append("RSI(12)超买")
        elif rsi_signal == "偏强":
            score += 5
            signals.append("RSI(12)偏强")
        elif rsi_signal == "偏弱":
            score -= 5
            signals.append("RSI(12)偏弱")

        # RSI极端区域额外惩罚
        if rsi_12_val is not None:
            if rsi_12_val >= 80:
                score -= 5
                signals.append("RSI(12)极端超买")
            elif rsi_12_val <= 20:
                score += 5
                signals.append("RSI(12)极端超卖")

        # RSI交叉：超买区金叉为多头陷阱，超卖区死叉为空头陷阱
        rsi_cross = rsi_12.get("cross", "") if isinstance(rsi_12, dict) else ""
        if "金叉" in rsi_cross:
            if rsi_12_val is not None and rsi_12_val >= 70:
                score -= 5
                signals.append("RSI超买区金叉(多头陷阱)")
            else:
                score += 5
                signals.append("RSI金叉")
        elif "死叉" in rsi_cross:
            if rsi_12_val is not None and rsi_12_val <= 30:
                score += 5
                signals.append("RSI超卖区死叉(空头陷阱)")
            else:
                score -= 5
                signals.append("RSI死叉")

        rsi_6 = rsi.get("RSI(6)", {})
        rsi_6_signal = rsi_6.get("signal", "") if isinstance(rsi_6, dict) else ""
        if rsi_6_signal == "超卖":
            score += 10
            signals.append("RSI(6)超卖")
        elif rsi_6_signal == "超买":
            score -= 10
            signals.append("RSI(6)超买")

        rsi_6_val = rsi_6.get("latest") if isinstance(rsi_6, dict) else None
        rsi_24 = rsi.get("RSI(24)", {})
        rsi_24_val = rsi_24.get("latest") if isinstance(rsi_24, dict) else None
        if rsi_6_val is not None and rsi_24_val is not None:
            try:
                r6 = float(rsi_6_val) if not hasattr(rsi_6_val, 'iloc') else float(rsi_6_val.iloc[-1])
                r24 = float(rsi_24_val) if not hasattr(rsi_24_val, 'iloc') else float(rsi_24_val.iloc[-1])
                if r6 > 70 and r24 < 40:
                    score -= 15
                    signals.append("RSI周期矛盾（偏空）")
                elif r6 < 30 and r24 > 60:
                    score += 15
                    signals.append("RSI周期矛盾（偏多）")
            except (TypeError, ValueError):
                pass

        # --- KDJ 分析 ---
        kdj_signal = kdj.get("signal", "") if isinstance(kdj, dict) else ""
        if kdj_signal == "金叉":
            score += 15
            signals.append("KDJ 金叉")
        elif kdj_signal == "死叉":
            score -= 15
            signals.append("KDJ 死叉")
        elif kdj_signal == "超卖":
            score += 15
            signals.append("KDJ 超卖")
        elif kdj_signal == "超买":
            score -= 15
            signals.append("KDJ 超买")

        # --- BOLL 分析 ---
        if current_price > 0 and isinstance(boll, dict):
            boll_latest = boll.get("latest", {})
            if isinstance(boll_latest, dict):
                boll_upper = boll_latest.get("upper")
                boll_middle = boll_latest.get("middle")
                boll_lower = boll_latest.get("lower")
            else:
                boll_upper = None
                boll_middle = None
                boll_lower = None

            if hasattr(boll_upper, "iloc"):
                boll_upper = boll_upper.iloc[-1]
                boll_middle = boll_middle.iloc[-1] if boll_middle is not None else None
                boll_lower = boll_lower.iloc[-1] if boll_lower is not None else None

            try:
                boll_upper = float(boll_upper) if boll_upper is not None else None
                boll_middle = float(boll_middle) if boll_middle is not None else None
                boll_lower = float(boll_lower) if boll_lower is not None else None

                if boll_upper is not None and current_price > boll_upper:
                    score -= 15
                    signals.append("BOLL超买")
                elif boll_lower is not None and current_price < boll_lower:
                    score += 15
                    signals.append("BOLL超卖")
                elif boll_middle is not None and current_price > boll_middle:
                    score += 5
                    signals.append("BOLL中轨上方")
                elif boll_middle is not None and current_price < boll_middle:
                    score -= 5
                    signals.append("BOLL中轨下方")

                boll_latest = boll.get("latest", {})
                boll_bandwidth = boll_latest.get("bandwidth") if isinstance(boll_latest, dict) else None
                if boll_bandwidth is not None:
                    if boll_bandwidth < 10:
                        signals.append("BOLL收窄(方向待定)")
                    elif boll_bandwidth > 25:
                        signals.append("BOLL扩张(方向待定)")
            except (TypeError, ValueError):
                pass

        # --- 均线排列判断 ---
        if isinstance(ma, dict):
            ma5_val = ma.get("MA5", {}).get("latest") if isinstance(ma.get("MA5"), dict) else None
            ma10_val = ma.get("MA10", {}).get("latest") if isinstance(ma.get("MA10"), dict) else None
            ma20_val = ma.get("MA20", {}).get("latest") if isinstance(ma.get("MA20"), dict) else None

            try:
                ma5_val = float(ma5_val) if ma5_val is not None else None
                ma10_val = float(ma10_val) if ma10_val is not None else None
                ma20_val = float(ma20_val) if ma20_val is not None else None

                if ma5_val is not None and ma10_val is not None and ma20_val is not None:
                    if ma5_val > ma10_val > ma20_val:
                        score += 15
                        signals.append("多头排列")
                    elif ma5_val < ma10_val < ma20_val:
                        score -= 15
                        signals.append("空头排列")
            except (TypeError, ValueError):
                pass

        # --- 归一化与冲突检测 ---
        MIN_SCORE = -55
        MAX_SCORE = 55

        # 超买视为看空方向，超卖视为看多方向
        upward_signals = sum(1 for s in signals if any(x in s for x in ["金叉", "多头", "偏强", "超卖"]))
        downward_signals = sum(1 for s in signals if any(x in s for x in ["死叉", "空头", "偏弱", "空头排列", "超买"]))

        conflict_penalty = 0
        if upward_signals > 0 and downward_signals > 0:
            conflict_penalty = min(0.15, abs(upward_signals - downward_signals) * 0.03)

        atr_signal = atr.get("signal", "") if isinstance(atr, dict) else ""
        boll_signal = boll.get("signal", "") if isinstance(boll, dict) else ""
        if atr_signal == "波动剧烈" and boll_signal in ("收窄", "扩张"):
            conflict_penalty = min(0.20, conflict_penalty + 0.05)

        normalized_score = (score - MIN_SCORE) / (MAX_SCORE - MIN_SCORE)
        normalized_score = max(0, min(1, normalized_score))

        if upward_signals > 0 and downward_signals > 0:
            normalized_score = normalized_score * (1 - conflict_penalty)

        result["score"] = normalized_score
        result["confidence"] = 1 - conflict_penalty
        result["details"] = {
            "MACD": macd,
            "RSI": rsi,
            "KDJ": kdj,
            "BOLL": boll,
            "MA": ma,
        }
        result["signals"] = signals

        fe_config = self.config.get("feature_engineering", {})
        if fe_config.get("enabled", False):
            try:
                feature_names, feature_values = extract_feature_vector(indicators)
                if len(feature_values) >= 2:
                    feature_dict = dict(zip(feature_names, feature_values))
                    self._feature_history.append(feature_values.copy())

                    if len(self._feature_history) >= 5:
                        # 确保所有历史特征向量长度一致（固定模板后应一致，做防御性检查）
                        expected_len = len(feature_values)
                        valid_history = [h for h in self._feature_history if len(h) == expected_len]
                        if len(valid_history) >= 5:
                            feature_matrix = np.array(valid_history)
                        else:
                            feature_matrix = np.array(list(self._feature_history)[-min(len(self._feature_history), expected_len):])
                            # 如果仍然不规则，跳过正交化
                            if feature_matrix.ndim != 2:
                                analyzer_logger.info(f"特征历史长度不一致，跳过正交化")
                                feature_matrix = None

                        if feature_matrix is not None:
                            corr_result = compute_feature_correlation(feature_dict)
                            result["feature_correlation"] = {
                                "high_correlation_pairs": corr_result["high_correlation_pairs"],
                                "feature_names": corr_result["feature_names"],
                            }

                            corr_threshold = fe_config.get("correlation_threshold", 0.7)
                            if corr_result["high_correlation_pairs"]:
                                variance_threshold = fe_config.get("variance_threshold", 0.95)
                                orth_result = orthogonalize_features(
                                    feature_matrix, feature_names, variance_threshold
                                )
                                if orth_result["n_components"] > 0:
                                    orth_features = orth_result["orthogonal_features"][-1]
                                    orth_score = np.sum(orth_features)
                                    max_possible = np.sum(np.abs(orth_features)) if np.sum(np.abs(orth_features)) > 0 else 1.0
                                    if max_possible > 0:
                                        orth_normalized = (orth_score / max_possible + 1) / 2
                                    else:
                                        orth_normalized = 0.5
                                    orth_normalized = max(0, min(1, orth_normalized))

                                    blend = 0.3
                                    result["score"] = normalized_score * (1 - blend) + orth_normalized * blend
                                    result["feature_correlation"]["orthogonalized"] = True
                                    result["feature_correlation"]["n_components"] = orth_result["n_components"]
                                    result["feature_correlation"]["explained_variance_ratio"] = orth_result["explained_variance_ratio"].tolist()
                                    analyzer_logger.info(
                                        f"特征正交化: {orth_result['n_components']}个主成分, "
                                        f"原始评分={normalized_score:.3f}, 正交评分={orth_normalized:.3f}, "
                                        f"混合评分={result['score']:.3f}"
                                    )
                                else:
                                    result["feature_correlation"]["orthogonalized"] = False
                            else:
                                result["feature_correlation"]["orthogonalized"] = False
                                analyzer_logger.info("特征相关性低，无需正交化")
                    else:
                        analyzer_logger.info(f"特征历史不足5期(当前{len(self._feature_history)}期)，跳过正交化")
            except Exception as e:
                analyzer_logger.warning(f"特征正交化处理异常: {e}")
                result["feature_correlation"] = {"error": str(e)}

        return result

    def analyze_multi_timeframe(self, daily_tech: Dict, weekly_tech: Dict = None, monthly_tech: Dict = None) -> Dict:
        """多时间框架趋势一致性检测

        基于日线/周线/月线技术评分判断趋势一致性，
        当小级别与大级别趋势矛盾时返回较低的confidence_factor。

        Args:
            daily_tech: 日线技术分析结果（含score字段）
            weekly_tech: 周线技术分析结果（可选）
            monthly_tech: 月线技术分析结果（可选）

        Returns:
            {
                "consistency": str,  # 一致性判定结果
                "confidence_factor": float,  # confidence调整因子
                "daily_score": float,
                "weekly_score": float or None,
                "monthly_score": float or None,
                "description": str  # 人类可读描述
            }
        """
        daily_score = daily_tech.get("score", 0.5) if daily_tech else 0.5
        weekly_score = weekly_tech.get("score", 0.5) if weekly_tech else None
        monthly_score = monthly_tech.get("score", 0.5) if monthly_tech else None

        # 周线/月线数据不可用时，不干预
        if weekly_score is None and monthly_score is None:
            return {
                "consistency": "no_data",
                "confidence_factor": 1.0,
                "daily_score": daily_score,
                "weekly_score": None,
                "monthly_score": None,
                "description": "周线/月线数据不可用，不进行多时间框架判定"
            }

        # 定义看多/看空阈值
        bull_threshold = 0.6
        bear_threshold = 0.4

        daily_bull = daily_score > bull_threshold
        daily_bear = daily_score < bear_threshold
        weekly_bull = weekly_score is not None and weekly_score > bull_threshold
        weekly_bear = weekly_score is not None and weekly_score < bear_threshold
        monthly_bull = monthly_score is not None and monthly_score > bull_threshold
        monthly_bear = monthly_score is not None and monthly_score < bear_threshold

        # 三周期一致看多
        if daily_bull and weekly_bull and monthly_bull:
            return {
                "consistency": "aligned_bull",
                "confidence_factor": 1.2,
                "daily_score": daily_score,
                "weekly_score": weekly_score,
                "monthly_score": monthly_score,
                "description": "日线/周线/月线趋势一致看多"
            }

        # 三周期一致看空
        if daily_bear and weekly_bear and monthly_bear:
            return {
                "consistency": "aligned_bear",
                "confidence_factor": 1.2,
                "daily_score": daily_score,
                "weekly_score": weekly_score,
                "monthly_score": monthly_score,
                "description": "日线/周线/月线趋势一致看空"
            }

        # 日线看多但周线看空（最强矛盾信号）
        if daily_bull and weekly_bear:
            return {
                "consistency": "counter_trend",
                "confidence_factor": 0.6,
                "daily_score": daily_score,
                "weekly_score": weekly_score,
                "monthly_score": monthly_score,
                "description": "日线看多但周线看空，逆势信号"
            }

        # 日线看空但周线看多（可能只是回调）
        if daily_bear and weekly_bull:
            # 月线也看多 → 回调买入机会
            if monthly_bull:
                return {
                    "consistency": "pullback_opportunity",
                    "confidence_factor": 0.9,
                    "daily_score": daily_score,
                    "weekly_score": weekly_score,
                    "monthly_score": monthly_score,
                    "description": "大周期上涨中的回调"
                }
            else:
                return {
                    "consistency": "counter_trend",
                    "confidence_factor": 0.7,
                    "daily_score": daily_score,
                    "weekly_score": weekly_score,
                    "monthly_score": monthly_score,
                    "description": "日线看空周线看多但月线不确认"
                }

        # 日线看多但月线看空（周线不矛盾时）
        if daily_bull and monthly_bear and not weekly_bear:
            return {
                "consistency": "monthly_conflict",
                "confidence_factor": 0.8,
                "daily_score": daily_score,
                "weekly_score": weekly_score,
                "monthly_score": monthly_score,
                "description": "日线看多但月线看空，中长期趋势矛盾"
            }

        # 日线看空但月线看空（周线不矛盾时）
        if daily_bear and monthly_bear and not weekly_bull:
            return {
                "consistency": "aligned_bear",
                "confidence_factor": 1.1,
                "daily_score": daily_score,
                "weekly_score": weekly_score,
                "monthly_score": monthly_score,
                "description": "日线/月线趋势一致看空"
            }

        # 仅周线可用的情况
        if weekly_score is not None and monthly_score is None:
            if daily_bull and weekly_bull:
                return {
                    "consistency": "aligned_bull",
                    "confidence_factor": 1.1,
                    "daily_score": daily_score,
                    "weekly_score": weekly_score,
                    "monthly_score": None,
                    "description": "日线/周线趋势一致看多"
                }
            if daily_bear and weekly_bear:
                return {
                    "consistency": "aligned_bear",
                    "confidence_factor": 1.1,
                    "daily_score": daily_score,
                    "weekly_score": weekly_score,
                    "monthly_score": None,
                    "description": "日线/周线趋势一致看空"
                }

        # 其他混合情况
        return {
            "consistency": "mixed",
            "confidence_factor": 1.0,
            "daily_score": daily_score,
            "weekly_score": weekly_score,
            "monthly_score": monthly_score,
            "description": "多时间框架信号混合，不干预"
        }

    def analyze_fund_flow(self, fund_flow: Dict, stock_info: Dict = None, history_df=None) -> Dict:
        """分析资金流向（使用相对指标）"""
        result = {"score": 0, "details": {}, "trend": "neutral"}

        if "error" in fund_flow:
            result["error"] = fund_flow["error"]
            return result

        main_inflow = fund_flow.get("主力净流入", 0)
        ratio = fund_flow.get("主力净流入占比", 0)

        try:
            main_inflow = float(main_inflow) if main_inflow else 0
        except (TypeError, ValueError):
            main_inflow = 0

        try:
            ratio = float(ratio) if ratio else 0
        except (TypeError, ValueError):
            ratio = 0

        score = 0
        trend = "neutral"

        amount = fund_flow.get("成交额", 0)
        if not amount and stock_info:
            amount = stock_info.get("成交额") or stock_info.get("今日成交额") or stock_info.get("成交额(万)")

        try:
            amount = float(amount) if amount else 1
            if amount <= 0:
                amount = 1
        except (TypeError, ValueError):
            amount = 1

        if ratio != 0:
            inflow_ratio = ratio / 100
        else:
            inflow_ratio = main_inflow / amount if amount else 0

        market_cap = 0
        if stock_info:
            try:
                mc = stock_info.get("总市值") or stock_info.get("流通市值") or 0
                market_cap = float(mc) if mc else 0
            except (TypeError, ValueError):
                market_cap = 0

        if market_cap > 500e8:
            threshold_high, threshold_low = 0.01, 0.005
        elif market_cap > 50e8:
            threshold_high, threshold_low = 0.03, 0.015
        else:
            threshold_high, threshold_low = 0.05, 0.025

        if inflow_ratio > threshold_high:
            score = 1.0
            trend = "inflow"
        elif inflow_ratio > threshold_low:
            score = 0.7
            trend = "inflow"
        elif inflow_ratio > 0:
            score = 0.5
            trend = "inflow"
        elif inflow_ratio > -threshold_low:
            score = 0.4
            trend = "outflow"
        elif inflow_ratio > -threshold_high:
            score = 0.3
            trend = "outflow"
        else:
            score = 0.1
            trend = "outflow"

        history = fund_flow.get("历史数据", [])
        if len(history) >= 3:
            recent_inflows = [h.get("主力净流入", 0) for h in history[-3:]]
            if all(x > 0 for x in recent_inflows):
                score = min(1.0, score + 0.2)
                trend = "inflow"
            elif all(x < 0 for x in recent_inflows):
                score = max(0.1, score - 0.15)
                trend = "outflow"

        result["score"] = score
        result["details"] = {
            "main_inflow": main_inflow,
            "ratio": ratio,
            "inflow_ratio": inflow_ratio,
            "history": history,
        }
        result["trend"] = trend
        analyzer_logger.info(f"资金评分(原始): {score:.3f}, trend={trend}, inflow_ratio={inflow_ratio:.4f}")

        # ETF/基金类：资金流数据含义与个股不同（申赎行为而非主力控盘），降权
        if stock_info and isinstance(stock_info, dict):
            stock_code = stock_info.get("代码", "")
        else:
            stock_code = ""
        if not stock_code and fund_flow:
            stock_code = fund_flow.get("代码", "")

        etf_prefixes = ("51", "15", "16", "18", "50", "52", "56", "58")
        etf_keywords = ("ETF", "LOF", "基金", "联接")

        is_etf = False
        if stock_code and str(stock_code).startswith(etf_prefixes):
            is_etf = True
        else:
            stock_name = ""
            if stock_info and isinstance(stock_info, dict):
                stock_name = stock_info.get("股票名称", "") or stock_info.get("名称", "")
            if stock_name and any(kw in str(stock_name) for kw in etf_keywords):
                is_etf = True

        if is_etf:
            score_before_shrink = score
            score = 0.5 + (score - 0.5) * 0.5  # 向0.5收缩
            result["score"] = score
            result["is_etf"] = True
            analyzer_logger.info(f"ETF降权: score {score_before_shrink:.3f}→{score:.3f}")

        # 量价背离校验
        result["price_volume_divergence"] = False
        if history_df is not None and not history_df.empty and "收盘" in history_df.columns:
            try:
                close_prices = history_df["收盘"].tail(3).astype(float).values
                if len(close_prices) >= 3:
                    # 线性回归斜率
                    x = np.arange(len(close_prices))
                    slope = np.polyfit(x, close_prices, 1)[0]
                    mean_price = np.mean(close_prices)
                    normalized_slope = slope / mean_price if mean_price > 0 else 0

                    slope_threshold = 0.005  # 判定为趋势的最小斜率
                    if normalized_slope < -slope_threshold and score >= 0.7:
                        # 价格下跌但资金评分偏高 → 背离
                        divergence_strength = min(1.0, abs(normalized_slope) / 0.02)
                        shrink_factor = 0.3 + 0.4 * (1 - divergence_strength)
                        score = 0.5 + (score - 0.5) * shrink_factor
                        result["score"] = score
                        result["price_volume_divergence"] = True
                        analyzer_logger.info(f"量价背离: 价格下跌但资金评分偏高, 收缩后={score:.3f}, 斜率={normalized_slope:.4f}")
                    elif normalized_slope > slope_threshold and score <= 0.3:
                        # 价格上涨但资金评分偏低 → 背离
                        divergence_strength = min(1.0, abs(normalized_slope) / 0.02)
                        shrink_factor = 0.3 + 0.4 * (1 - divergence_strength)
                        score = 0.5 + (score - 0.5) * shrink_factor
                        result["score"] = score
                        result["price_volume_divergence"] = True
                        analyzer_logger.info(f"量价背离: 价格上涨但资金评分偏低, 收缩后={score:.3f}, 斜率={normalized_slope:.4f}")
            except Exception as e:
                analyzer_logger.debug(f"量价背离检测异常: {e}")

        analyzer_logger.info(f"资金评分(最终): {result.get('score', 0):.3f}, divergence={result.get('price_volume_divergence', False)}")
        return result

    def analyze_market_sentiment(self, data: Dict, market_data: Dict = None) -> Dict:
        """分析市场情绪（包含大盘参考）

        参数:
            data: 股票数据
            market_data: 大盘数据（可选，外部获取后传入避免重复API调用）
        """
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
                score += 0.15
            elif turnover > 8:
                score += 0.1
            elif turnover < 2:
                score -= 0.05
        except (ValueError, TypeError):
            pass

        try:
            volume_ratio = float(volume_ratio) if volume_ratio else 1.0
            if volume_ratio > 2:
                score += 0.15
            elif volume_ratio > 1.5:
                score += 0.1
            elif volume_ratio < 0.5:
                score -= 0.05
        except (ValueError, TypeError):
            pass

        market_change = 0
        market_status = "未知"

        if market_data and isinstance(market_data, dict) and market_data.get("涨跌幅") is not None:
            market_change = market_data.get("涨跌幅", 0)
            try:
                market_change = float(market_change)
            except (ValueError, TypeError):
                market_change = 0
            if market_change > 1:
                market_status = "大涨"
                score += 0.1
            elif market_change > 0.5:
                market_status = "上涨"
                score += 0.05
            elif market_change < -1:
                market_status = "大跌"
                score -= 0.1
            elif market_change < -0.5:
                market_status = "下跌"
                score -= 0.05
            else:
                market_status = "平稳"
        elif market_data is None or not market_data:
            # 兜底：用 baostock 获取上证指数涨跌幅（加锁防并发冲突）
            try:
                from scripts.core.data_fetcher import _baostock_lock
                import baostock as bs
                from datetime import datetime, timedelta

                def _fetch_index():
                    with _baostock_lock:
                        lg = bs.login()
                        try:
                            today = datetime.now().strftime('%Y-%m-%d')
                            start = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
                            rs = bs.query_history_k_data_plus(
                                'sh.000001', 'date,pctChg',
                                start_date=start, end_date=today, frequency='d'
                            )
                            rows = []
                            while rs.error_code == '0' and rs.next():
                                rows.append(rs.get_row_data())
                            if rows:
                                return float(rows[-1][1]) if len(rows[-1]) > 1 else 0
                        finally:
                            bs.logout()
                    return None

                import concurrent.futures
                _executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                try:
                    future = _executor.submit(_fetch_index)
                    done, not_done = concurrent.futures.wait([future], timeout=20)
                    if not_done:
                        not_done.pop().cancel()
                    else:
                        market_change = future.result() or 0
                except Exception:
                    market_change = 0
                finally:
                    _executor.shutdown(wait=False)

                try:
                    market_change = float(market_change)
                except (ValueError, TypeError):
                    market_change = 0
                if market_change > 1:
                    market_status = "大涨"
                    score += 0.1
                elif market_change > 0.5:
                    market_status = "上涨"
                    score += 0.05
                elif market_change < -1:
                    market_status = "大跌"
                    score -= 0.1
                elif market_change < -0.5:
                    market_status = "下跌"
                    score -= 0.05
                else:
                    market_status = "平稳"
            except Exception as e:
                analyzer_logger.debug(f"获取大盘数据失败: {e}")

        result["score"] = max(0, min(1, score))
        result["details"] = {
            "turnover": turnover,
            "volume_ratio": volume_ratio,
            "market_change": market_change,
            "market_status": market_status,
        }

        return result

    def generate_trading_signal(self, analysis: Dict, position_status: str = "未持有", market_data: dict = None) -> Dict:
        """生成交易信号"""
        analyzer_logger.info("=" * 50)
        analyzer_logger.info("开始生成交易信号...")

        technical_score = analysis.get("technical", {}).get("score", 0.5)
        fund_flow_score = analysis.get("fund_flow", {}).get("score", 0.5)
        sentiment_score = analysis.get("sentiment", {}).get("score", 0.5)

        analyzer_logger.info(f"技术评分: {technical_score:.3f}")
        analyzer_logger.info(f"资金评分: {fund_flow_score:.3f}")
        analyzer_logger.info(f"情绪评分: {sentiment_score:.3f}")

        dwm = self._dynamic_weight_manager
        if dwm.enabled and market_data is not None:
            dynamic_weights = dwm.detect_and_update(market_data)
            self._market_regime = dwm.get_regime()
            w_technical = dynamic_weights.get("technical", 0.5)
            w_fund_flow = dynamic_weights.get("fund_flow", 0.3)
            w_sentiment = dynamic_weights.get("sentiment", 0.2)
            weight_total = w_technical + w_fund_flow + w_sentiment
            if weight_total > 0:
                w_technical /= weight_total
                w_fund_flow /= weight_total
                w_sentiment /= weight_total
            weights = {"technical": w_technical, "fund_flow": w_fund_flow, "sentiment": w_sentiment}
            analyzer_logger.info(f"动态权重: {weights}, 市场状态: {self._market_regime}")
        else:
            weights = self.weights
            w_technical = weights.get("technical", 0.5)
            w_fund_flow = weights.get("fund_flow", 0.3)
            w_sentiment = weights.get("sentiment", 0.2)

        total_score = (
            technical_score * w_technical
            + fund_flow_score * w_fund_flow
            + sentiment_score * w_sentiment
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

        if position_status == "已持有":
            signal_text_map = {
                "strong_buy": "强烈加仓",
                "buy": "加仓",
                "hold": "持有",
                "watch": "观望",
                "sell": "减仓",
            }
        else:
            signal_text_map = {
                "strong_buy": "强烈买入",
                "buy": "买入",
                "hold": "观望",
                "watch": "回避",
                "sell": "回避",
            }

        result = {
            "score": round(total_score, 3),
            "signal": signal,
            "signal_text": signal_text_map.get(signal, "观望"),
        }
        if self._market_regime is not None:
            result["market_regime"] = self._market_regime
        return result

    def _safe_score(self, value, default: float = 0.5) -> float:
        """安全读取 0-1 区间评分"""
        try:
            score = float(value)
        except (TypeError, ValueError):
            return default
        if pd.isna(score):
            return default
        return max(0.0, min(1.0, score))

    def _latest_indicator_value(self, value, default=None):
        """安全读取指标最新值"""
        if value is None:
            return default
        try:
            if hasattr(value, "iloc"):
                value = value.iloc[-1]
            if pd.isna(value):
                return default
            return value
        except (IndexError, TypeError, ValueError):
            return default

    def _detect_signal_persistence(self, indicators: Dict) -> Dict:
        """检测技术指标的信号持续性

        返回:
            dict: 各指标信号的持续天数和方向
        """
        persistence = {}

        macd_data = indicators.get("MACD", {})
        macd_hist = macd_data.get("histogram")
        if macd_hist is not None and hasattr(macd_hist, "__len__") and len(macd_hist) >= 2:
            try:
                vals = list(macd_hist.iloc[-10:]) if hasattr(macd_hist, "iloc") else list(macd_hist[-10:])
                vals = [float(v) for v in vals if not pd.isna(v)]
                if vals:
                    sign = 1 if vals[-1] > 0 else -1
                    days = 0
                    for v in reversed(vals):
                        if (v > 0 and sign > 0) or (v < 0 and sign < 0):
                            days += 1
                        else:
                            break
                    persistence["macd"] = {"direction": "bullish" if sign > 0 else "bearish", "days": days}
            except (TypeError, ValueError, IndexError):
                pass

        rsi_data = indicators.get("RSI", {})
        rsi_12 = rsi_data.get("RSI(12)", {})
        if isinstance(rsi_12, dict):
            rsi_series = rsi_12.get("values")
            if rsi_series is not None and hasattr(rsi_series, "__len__") and len(rsi_series) >= 2:
                try:
                    vals = list(rsi_series.iloc[-10:]) if hasattr(rsi_series, "iloc") else list(rsi_series[-10:])
                    vals = [float(v) for v in vals if not pd.isna(v)]
                    if vals:
                        latest = vals[-1]
                        if latest >= 70:
                            over_days = sum(1 for v in reversed(vals) if v >= 70)
                            persistence["rsi"] = {"direction": "overbought", "days": over_days}
                        elif latest <= 30:
                            over_days = sum(1 for v in reversed(vals) if v <= 30)
                            persistence["rsi"] = {"direction": "oversold", "days": over_days}
                except (TypeError, ValueError, IndexError):
                    pass

        return persistence

    @staticmethod
    def calc_chip_distribution(history_df, current_price, decay=0.97, price_bins=200):
        """
        筹码分布算法：基于历史成交量分布估算各价位持仓成本。

        参数:
            history_df: DataFrame，需包含 最高/最低/收盘/成交量 列
            current_price: 当前价格
            decay: 每日衰减系数，越久远的交易筹码越可能已换手
            price_bins: 价格分桶数

        返回:
            dict: profit_ratio(获利盘), trapped_ratio(套牢盘),
                  concentration(集中度), resistance_price(压力位),
                  support_price(支撑位), peak_price(峰值价位)
        """
        if history_df is None or history_df.empty or current_price <= 0:
            return None
        try:
            highs = history_df["最高"].astype(float).values
            lows = history_df["最低"].astype(float).values
            volumes = history_df["成交量"].astype(float).values
        except (KeyError, ValueError):
            return None

        n = len(highs)
        if n < 10:
            return None

        # 确定价格范围
        price_min = lows.min() * 0.98
        price_max = highs.max() * 1.02
        if price_max <= price_min:
            return None

        # 创建价格桶
        bin_edges = np.linspace(price_min, price_max, price_bins + 1)
        chip_dist = np.zeros(price_bins)

        # 从最新到最旧，逐日分配筹码
        for i in range(n - 1, -1, -1):
            days_ago = n - 1 - i
            h, l, vol = highs[i], lows[i], volumes[i]
            if vol <= 0 or h <= l:
                continue

            weight = vol * (decay ** days_ago)

            low_bin = max(0, np.searchsorted(bin_edges, l, side="left") - 1)
            high_bin = min(price_bins - 1, np.searchsorted(bin_edges, h, side="right") - 1)

            if high_bin >= low_bin:
                per_bin = weight / (high_bin - low_bin + 1)
                chip_dist[low_bin:high_bin + 1] += per_bin

        # 归一化
        total = chip_dist.sum()
        if total == 0:
            return None
        chip_dist = chip_dist / total

        # 获利盘比例：当前价以下的筹码占比
        current_bin = min(np.searchsorted(bin_edges, current_price, side="right") - 1, price_bins - 1)
        profit_ratio = chip_dist[:current_bin + 1].sum()

        # 筹码集中度：90%筹码分布的价格宽度 / 当前价
        cumsum = np.cumsum(chip_dist)
        low_5_idx = max(0, np.searchsorted(cumsum, 0.05))
        high_95_idx = min(price_bins - 1, np.searchsorted(cumsum, 0.95))
        concentration = (bin_edges[high_95_idx] - bin_edges[low_5_idx]) / current_price

        # 套牢盘压力位：当前价以上筹码最密集的价位
        above_current = chip_dist[current_bin + 1:]
        resistance_price = None
        if above_current.sum() > 0.01:
            resistance_idx = np.argmax(above_current) + current_bin + 1
            resistance_price = round((bin_edges[resistance_idx] + bin_edges[resistance_idx + 1]) / 2, 2)

        # 支撑位：当前价以下筹码最密集的价位
        below_current = chip_dist[:current_bin + 1]
        support_price = None
        if below_current.sum() > 0.01:
            support_idx = np.argmax(below_current)
            support_price = round((bin_edges[support_idx] + bin_edges[support_idx + 1]) / 2, 2)

        # 套牢盘占比
        trapped_ratio = chip_dist[current_bin + 1:].sum()

        # 筹码峰值价位
        peak_idx = np.argmax(chip_dist)
        peak_price = round((bin_edges[peak_idx] + bin_edges[peak_idx + 1]) / 2, 2)

        return {
            "profit_ratio": round(float(profit_ratio), 4),
            "trapped_ratio": round(float(trapped_ratio), 4),
            "concentration": round(float(concentration), 4),
            "resistance_price": resistance_price,
            "support_price": support_price,
            "peak_price": peak_price,
        }

    def cross_validate_analysis(
        self,
        analysis: Dict,
        price_prediction: Dict,
        indicators: Dict,
        trading_signal: Optional[Dict] = None,
        position_status: str = "未持有",
        current_price: float = 0,
        history_df: "pd.DataFrame" = None,
        multi_timeframe: Dict = None,
        hmm_state_override: str = None,
    ) -> Dict:
        """
        对分析结论进行交叉验证，返回可解释的一致性、风控与行动门控结果。

        优化点:
        1. 加权投票 - 使用模型权重(技术0.5/资金0.3/情绪0.2)替代简单计数
        2. 缺失数据标记 - 检测各维度数据缺失，排除并降低共识阈值
        3. 信号持续性 - MACD金叉持续天数、RSI超买/超卖持续天数
        4. 扩展冲突检测 - 新增"技术偏弱但资金流入"、"RSI背离"等模式
        5. 柔性门控 - 分级action_gate替代二元门控

        参数:
            analysis: 技术、资金、情绪分析结果
            price_prediction: 价格预测结果
            indicators: 技术指标结果
            trading_signal: 交易信号结果
            position_status: 持仓状态
            current_price: 当前价格

        返回:
            dict: 交叉验证结果
        """
        trading_signal = trading_signal or {}
        vcfg = self.validation_config
        st = vcfg.get("score_thresholds", {})
        vt = vcfg.get("vote_thresholds", {})
        cw = vcfg.get("confidence_weights", {})
        cp = vcfg.get("conflict_penalty", {})

        tech_bullish = st.get("technical_bullish", 0.65)
        tech_bearish = st.get("technical_bearish", 0.35)
        fund_bullish = st.get("fund_bullish", 0.6)
        fund_bearish = st.get("fund_bearish", 0.4)
        sentiment_bullish = st.get("sentiment_bullish", 0.6)
        sentiment_bearish = st.get("sentiment_bearish", 0.4)
        bullish_margin = vt.get("bullish_consensus_margin", 3)
        bearish_margin = vt.get("bearish_consensus_margin", 2)
        signal_weight = cw.get("signal", 0.4)
        agreement_weight = cw.get("agreement", 0.6)
        per_conflict_penalty = cp.get("per_conflict", 0.1)
        max_conflict_penalty = cp.get("max", 0.3)

        model_weights = self._dynamic_weight_manager.get_current_weights() if self._dynamic_weight_manager.enabled else self.weights
        w_tech = model_weights.get("technical", 0.5)
        w_fund = model_weights.get("fund_flow", 0.3)
        w_sent = model_weights.get("sentiment", 0.2)

        supporting_factors = []
        opposing_factors = []
        conflicts = []
        missing_dimensions = []

        technical_score = self._safe_score(
            analysis.get("technical", {}).get("score"), default=None
        )
        fund_flow = analysis.get("fund_flow", {})
        fund_score_raw = self._safe_score(fund_flow.get("score"), default=None)
        sentiment_score_raw = self._safe_score(
            analysis.get("sentiment", {}).get("score"), default=None
        )
        signal_score = self._safe_score(trading_signal.get("score"), default=0.5)

        tech_missing = technical_score is None
        fund_missing = fund_score_raw is None
        sent_missing = sentiment_score_raw is None

        technical_score = technical_score if technical_score is not None else 0.5
        fund_score = fund_score_raw if fund_score_raw is not None else 0.5
        sentiment_score = sentiment_score_raw if sentiment_score_raw is not None else 0.5

        if tech_missing:
            missing_dimensions.append("技术")
        if fund_missing:
            missing_dimensions.append("资金")
        if sent_missing:
            missing_dimensions.append("情绪")

        weighted_bullish = 0.0
        weighted_bearish = 0.0
        active_weight_total = 0.0

        # 改动1+2：评分幅度参与共识计算，中性维度不占座
        if not tech_missing:
            if technical_score > 0.5:
                strength = (technical_score - 0.5) / 0.5  # 0~1
                weighted_bullish += w_tech * strength
                active_weight_total += w_tech * strength
                if technical_score >= tech_bullish:
                    supporting_factors.append("技术评分偏强")
            elif technical_score < 0.5:
                strength = (0.5 - technical_score) / 0.5  # 0~1
                weighted_bearish += w_tech * strength
                active_weight_total += w_tech * strength
                if technical_score <= tech_bearish:
                    opposing_factors.append("技术评分偏弱")

        if not fund_missing:
            if fund_score > 0.5:
                strength = (fund_score - 0.5) / 0.5
                weighted_bullish += w_fund * strength
                active_weight_total += w_fund * strength
                if fund_score >= fund_bullish:
                    supporting_factors.append("资金流入支持")
            elif fund_score < 0.5:
                strength = (0.5 - fund_score) / 0.5
                weighted_bearish += w_fund * strength
                active_weight_total += w_fund * strength
                if fund_score <= fund_bearish:
                    opposing_factors.append("资金流出压制")
            # 资金趋势辅助判断
            fund_trend = fund_flow.get("trend", "neutral")
            if fund_trend == "inflow" and fund_score <= fund_bullish:
                # 评分未达偏强但趋势为流入，小幅加成
                weighted_bullish += w_fund * 0.2
                active_weight_total += w_fund * 0.2
                supporting_factors.append("资金流入支持(趋势)")
            elif fund_trend == "outflow" and fund_score >= fund_bearish:
                weighted_bearish += w_fund * 0.2
                active_weight_total += w_fund * 0.2
                opposing_factors.append("资金流出压制(趋势)")

        if not sent_missing:
            if sentiment_score > 0.5:
                strength = (sentiment_score - 0.5) / 0.5
                weighted_bullish += w_sent * strength
                active_weight_total += w_sent * strength
                if sentiment_score >= sentiment_bullish:
                    supporting_factors.append("市场情绪偏暖")
            elif sentiment_score < 0.5:
                strength = (0.5 - sentiment_score) / 0.5
                weighted_bearish += w_sent * strength
                active_weight_total += w_sent * strength
                if sentiment_score <= sentiment_bearish:
                    opposing_factors.append("市场情绪偏弱")

        prediction_trends = [
            price_prediction.get("day1", {}).get("trend"),
            price_prediction.get("day2", {}).get("trend"),
        ]
        up_weight_pred = sum(
            1.0 if t == TREND_STRONG_UP else 0.6
            for t in prediction_trends if t in (TREND_STRONG_UP, TREND_UP)
        )
        down_weight_pred = sum(
            1.0 if t == TREND_STRONG_DOWN else 0.6
            for t in prediction_trends if t in (TREND_STRONG_DOWN, TREND_DOWN)
        )
        pred_weight = 0.15
        if up_weight_pred > down_weight_pred:
            weighted_bullish += pred_weight
            active_weight_total += pred_weight
            supporting_factors.append("短线价格预测向上")
        elif down_weight_pred > up_weight_pred:
            weighted_bearish += pred_weight
            active_weight_total += pred_weight
            opposing_factors.append("短线价格预测承压")

        # MACD/RSI/KDJ/BOLL信号已通过technical_score计入，不再独立计权
        macd_signal = indicators.get("MACD", {}).get("signal", "")
        macd_bearish = macd_signal in ("死叉", "死叉确认", "空头")
        if macd_signal in ("金叉", "金叉确认", "多头"):
            supporting_factors.append(f"MACD{macd_signal}")
        elif macd_bearish:
            opposing_factors.append(f"MACD{macd_signal}")

        kdj_signal = indicators.get("KDJ", {}).get("signal", "")
        if kdj_signal == "金叉":
            supporting_factors.append(f"KDJ{kdj_signal}")
        elif kdj_signal == "超卖":
            # MACD空头+KDJ超卖 = 下跌中继，不应作为支持因素
            if macd_bearish:
                conflicts.append("MACD空头+KDJ超卖，下跌中继反弹空间有限")
                opposing_factors.append("KDJ超卖(下跌趋势中)")
                analyzer_logger.info("MACD空头+KDJ超卖: 标记为下跌中继，不作为支持因素")
            else:
                supporting_factors.append(f"KDJ{kdj_signal}")
        elif kdj_signal in ("死叉", "超买"):
            opposing_factors.append(f"KDJ{kdj_signal}")

        rsi_12 = indicators.get("RSI", {}).get("RSI(12)", {})
        if isinstance(rsi_12, dict):
            rsi_latest = self._latest_indicator_value(rsi_12.get("latest"))
            rsi_signal = rsi_12.get("signal", "")
        else:
            rsi_latest = self._latest_indicator_value(rsi_12)
            rsi_signal = ""
        rsi_value = None
        try:
            rsi_value = float(rsi_latest) if rsi_latest is not None else None
            if rsi_value is not None and rsi_value >= 70:
                opposing_factors.append("RSI接近超买")
            elif rsi_value is not None and rsi_value <= 30:
                # MACD空头+RSI超卖 = 下跌趋势中的超卖，反弹空间有限
                if macd_bearish:
                    conflicts.append(f"MACD空头+RSI超卖({rsi_value:.0f})，下跌趋势中反弹空间有限")
                    opposing_factors.append(f"RSI超卖({rsi_value:.0f},下跌趋势中)")
                    analyzer_logger.info(f"MACD空头+RSI超卖({rsi_value:.0f}): 标记为下跌趋势中超卖，不作为支持因素")
                else:
                    supporting_factors.append("RSI接近超卖反弹区")
            elif rsi_signal == "偏强":
                supporting_factors.append("RSI偏强")
            elif rsi_signal == "偏弱":
                opposing_factors.append("RSI偏弱")
        except (TypeError, ValueError):
            pass

        boll_latest = indicators.get("BOLL", {}).get("latest", {})
        if isinstance(boll_latest, dict) and current_price:
            upper = self._latest_indicator_value(boll_latest.get("upper"))
            lower = self._latest_indicator_value(boll_latest.get("lower"))
            try:
                upper = float(upper) if upper is not None else None
                lower = float(lower) if lower is not None else None
                if upper is not None and current_price >= upper:
                    opposing_factors.append("价格接近布林上轨")
                elif lower is not None and current_price <= lower:
                    supporting_factors.append("价格接近布林下轨")
            except (TypeError, ValueError):
                pass

        persistence = self._detect_signal_persistence(indicators)
        persistence_info = {}
        for key, info in persistence.items():
            direction = info.get("direction", "")
            days = info.get("days", 0)
            if key == "macd":
                persistence_info["macd_persistence"] = info
                if direction == "bullish" and days >= 3:
                    supporting_factors.append(f"MACD多头持续{days}日")
                elif direction == "bearish" and days >= 3:
                    opposing_factors.append(f"MACD空头持续{days}日")
            elif key == "rsi":
                persistence_info["rsi_persistence"] = info
                if direction == "overbought" and days >= 3:
                    opposing_factors.append(f"RSI超买持续{days}日")
                elif direction == "oversold" and days >= 3:
                    supporting_factors.append(f"RSI超卖持续{days}日")

        if technical_score >= tech_bullish and (fund_score <= fund_bearish or fund_flow.get("trend") == "outflow"):
            conflicts.append("技术偏强但资金未确认")
        if technical_score <= tech_bearish and fund_score >= fund_bullish:
            conflicts.append("技术偏弱但资金流入")
        if signal_score >= 0.7 and down_weight_pred > 0:
            conflicts.append("交易信号偏强但价格预测转弱")
        if signal_score < 0.5 and weighted_bullish >= 0.3:
            conflicts.append("多项指标偏多但综合信号未确认")
        if rsi_value is not None and rsi_value >= 70 and weighted_bullish > weighted_bearish:
            conflicts.append("RSI超买与看多方向背离")
        if rsi_value is not None and rsi_value <= 30 and weighted_bearish > weighted_bullish:
            conflicts.append("RSI超卖与看空方向背离")

        # P3: 量价背离冲突检测
        fund_flow_result = analysis.get("fund_flow", {})
        if fund_flow_result.get("price_volume_divergence"):
            conflicts.append("量价背离：资金流向与价格趋势不一致")
            conflict_penalty_extra = 0.1
        else:
            conflict_penalty_extra = 0.0

        # 资金-ML方向背离检测
        fund_ml_diverged = False
        fund_ml_divergence_penalty = 0.0
        ml_prediction = price_prediction.get("ml_prediction")
        ml_direction = ml_prediction.get("direction") if ml_prediction else None
        if ml_direction is not None:
            if fund_score >= 0.7 and ml_direction == 0:
                fund_ml_diverged = True
                conflicts.append("资金强流入但ML预测看跌")
                opposing_factors.append("资金-ML方向背离")
                fund_ml_divergence_penalty = 0.1 + 0.1 * (fund_score - 0.7) / 0.3
                analyzer_logger.info(
                    f"资金-ML背离: 资金评分={fund_score:.3f}(强流入), ML direction=0(看跌), "
                    f"惩罚={fund_ml_divergence_penalty:.3f}"
                )
            elif fund_score <= 0.3 and ml_direction == 1:
                fund_ml_diverged = True
                conflicts.append("资金强流出但ML预测看涨")
                supporting_factors.append("资金-ML方向背离(反向)")
                fund_ml_divergence_penalty = 0.1 + 0.1 * (0.3 - fund_score) / 0.3
                analyzer_logger.info(
                    f"资金-ML背离: 资金评分={fund_score:.3f}(强流出), ML direction=1(看涨), "
                    f"惩罚={fund_ml_divergence_penalty:.3f}"
                )

        # 筹码分布修正资金-ML背离
        chip_result = None
        chip_relieve = 0.0  # 筹码修正量（减少惩罚）
        if fund_ml_diverged and history_df is not None and not history_df.empty and current_price > 0:
            chip_result = self.calc_chip_distribution(history_df, current_price)
            if chip_result is not None:
                profit_ratio = chip_result["profit_ratio"]
                trapped_ratio = chip_result["trapped_ratio"]
                resistance = chip_result["resistance_price"]

                # 场景1：资金流入+ML看跌 + 获利盘>85%且无压力位 → 趋势延续，削弱ML否决权
                if fund_score >= 0.7 and ml_direction == 0:
                    if profit_ratio > 0.85 and (resistance is None or resistance > current_price * 1.05):
                        chip_relieve = fund_ml_divergence_penalty * 0.6  # 减免60%惩罚
                        supporting_factors.append(f"筹码获利盘{profit_ratio:.0%}+无压力位，趋势延续")
                        analyzer_logger.info(
                            f"筹码修正: 获利盘={profit_ratio:.1%}, 无压力位, "
                            f"趋势延续信号→惩罚减免{chip_relieve:.3f}({chip_relieve/fund_ml_divergence_penalty:.0%})"
                        )
                    elif profit_ratio > 0.85 and resistance is not None and resistance <= current_price * 1.05:
                        # 获利盘重但压力位近 → 获利回吐风险，维持惩罚
                        conflicts.append(f"获利盘{profit_ratio:.0%}+压力位{resistance}近，回吐风险")
                        analyzer_logger.info(
                            f"筹码确认: 获利盘={profit_ratio:.1%}, 压力位={resistance}(近), 回吐风险高"
                        )

                # 场景2：资金流出+ML看涨 + 套牢盘>70% → 反弹遇抛压，加强ML看跌判断
                elif fund_score <= 0.3 and ml_direction == 1:
                    if trapped_ratio > 0.70:
                        chip_relieve = -fund_ml_divergence_penalty * 0.3  # 额外增加30%惩罚
                        opposing_factors.append(f"筹码套牢盘{trapped_ratio:.0%}，反弹遇抛压")
                        analyzer_logger.info(
                            f"筹码修正: 套牢盘={trapped_ratio:.1%}, 反弹遇抛压→惩罚增加{abs(chip_relieve):.3f}"
                        )

                # 计算最终惩罚
                fund_ml_divergence_penalty = max(0.0, fund_ml_divergence_penalty - chip_relieve)
                if chip_relieve > 0:
                    # 惩罚减免后力度较弱，不再构成背离降级条件
                    if fund_ml_divergence_penalty < 0.10:
                        fund_ml_diverged = False
                        analyzer_logger.info("筹码修正后惩罚<0.10，取消资金-ML背离降级")

                analyzer_logger.info(
                    f"筹码分布: 获利盘={profit_ratio:.1%}, 套牢盘={trapped_ratio:.1%}, "
                    f"集中度={chip_result['concentration']:.1%}, "
                    f"压力位={resistance}, 支撑位={chip_result['support_price']}, "
                    f"峰值={chip_result['peak_price']}"
                )

        # 布林带极窄检测
        boll_narrow = False
        boll = indicators.get("BOLL", {})
        if isinstance(boll, dict) and current_price > 0:
            boll_latest = boll.get("latest", {})
            if isinstance(boll_latest, dict):
                boll_upper = boll_latest.get("upper")
                boll_lower = boll_latest.get("lower")
                try:
                    if hasattr(boll_upper, "iloc"):
                        boll_upper = float(boll_upper.iloc[-1])
                        boll_lower = float(boll_lower.iloc[-1])
                    elif boll_upper is not None and boll_lower is not None:
                        boll_upper = float(boll_upper)
                        boll_lower = float(boll_lower)
                    if boll_upper is not None and boll_lower is not None and boll_lower > 0:
                        boll_width_ratio = (boll_upper - boll_lower) / current_price
                        if boll_width_ratio < 0.005:
                            boll_narrow = True
                            conflicts.append(f"布林带极度收敛(宽度{boll_width_ratio*100:.2f}%)，方向不确定")
                            analyzer_logger.info(
                                f"布林带极窄: upper={boll_upper:.2f}, lower={boll_lower:.2f}, "
                                f"宽度比={boll_width_ratio*100:.2f}%"
                            )
                except (TypeError, ValueError, IndexError):
                    pass

        # 多时间框架冲突检测
        mtf_consistency = None
        mtf_factor = 1.0
        if multi_timeframe and multi_timeframe.get("consistency", "no_data") != "no_data":
            mtf_consistency = multi_timeframe["consistency"]
            mtf_factor = multi_timeframe.get("confidence_factor", 1.0)

            if mtf_consistency == "counter_trend":
                conflicts.append("日线与周线趋势矛盾")
            elif mtf_consistency == "monthly_conflict":
                conflicts.append("日线与月线趋势矛盾")
            elif mtf_consistency in ("aligned_bull", "aligned_bear"):
                supporting_factors.append("多周期趋势一致")
            elif mtf_consistency == "pullback_opportunity":
                supporting_factors.append("大周期上涨中的回调")

        # 独立检测：近3日价格变化率与资金评分背离
        surge_risk = False
        if history_df is not None and not history_df.empty and "收盘" in history_df.columns:
            try:
                recent_closes = history_df["收盘"].tail(4).astype(float).values
                if len(recent_closes) >= 2:
                    price_change_3d = (recent_closes[-1] - recent_closes[0]) / recent_closes[0] * 100
                    if price_change_3d < -3 and fund_score >= 0.7:
                        conflicts.append("近期下跌但资金评分偏高")
                    elif price_change_3d > 3 and fund_score <= 0.3:
                        conflicts.append("近期上涨但资金评分偏低")

                # 大涨后回调风险检测
                if len(recent_closes) >= 2:
                    last_change = (recent_closes[-1] - recent_closes[-2]) / recent_closes[-2] * 100
                    if last_change >= 5 and direction_consensus == "bullish":
                        surge_risk = True
                        conflicts.append(f"单日大涨{last_change:.1f}%后追高风险")
                        opposing_factors.append(f"追高风险(单日+{last_change:.1f}%)")
            except Exception:
                pass

        if active_weight_total > 0:
            bull_ratio = weighted_bullish / active_weight_total
            bear_ratio = weighted_bearish / active_weight_total
        else:
            bull_ratio = 0.5
            bear_ratio = 0.5

        missing_penalty = len(missing_dimensions) * 0.05

        # 数据质量低时加重惩罚
        data_quality = analysis.get("data_quality", "normal")
        if data_quality == "low":
            missing_penalty += 0.1
            analyzer_logger.info("数据质量低(DB回退)，加重missing_penalty")

        if bull_ratio >= 0.6:
            direction_consensus = "bullish"
        elif bear_ratio >= 0.6:
            direction_consensus = "bearish"
        else:
            direction_consensus = "mixed"

        conflict_penalty = min(max_conflict_penalty, len(conflicts) * per_conflict_penalty) + conflict_penalty_extra
        agreement_ratio = max(bull_ratio, bear_ratio)
        confidence = (signal_score * signal_weight) + (agreement_ratio * agreement_weight) - conflict_penalty - missing_penalty - fund_ml_divergence_penalty
        confidence = round(max(0.0, min(1.0, confidence)), 3)

        # 多时间框架confidence调整
        if mtf_factor != 1.0:
            confidence_before_mtf = confidence
            confidence = round(max(0.0, min(1.0, confidence * mtf_factor)), 3)

        # P2: HMM状态信号约束
        # 优先使用直接传入的HMM状态，其次从HMM检测器实时获取（避免并发共享状态问题）
        hmm_state = hmm_state_override
        hmm_decay = 1.0
        if not hmm_state and self._hmm_detector is not None and self._hmm_detector.is_ready():
            # 直接从HMM检测器获取当前股票的市场状态，而非依赖共享的DynamicWeightManager
            try:
                if history_df is not None and not history_df.empty and "收盘" in history_df.columns:
                    closes = history_df["收盘"].values.astype(np.float64)
                    if len(closes) > 20:
                        returns = np.diff(closes) / closes[:-1]
                        vols = np.zeros_like(returns)
                        window = 20
                        for i in range(len(returns)):
                            start = max(0, i - window + 1)
                            vols[i] = np.std(returns[start:i + 1]) if i > 0 else 0.0
                        volumes = history_df["成交量"].values.astype(np.float64) if "成交量" in history_df.columns else np.ones(len(closes))
                        volume_changes = np.diff(volumes) / (volumes[:-1] + 1e-10)
                        hmm_result = self._hmm_detector.predict(returns, vols, volume_changes)
                        hmm_state = hmm_result.get("current_state", "")
            except Exception:
                pass
        if not hmm_state and self._dynamic_weight_manager and self._dynamic_weight_manager.enabled:
            hmm_state = self._dynamic_weight_manager.get_regime()

        decay_map = vcfg.get("hmm_confidence_decay", {
            "高波动": 0.75, "趋势下跌": 0.85, "低波动震荡": 0.9, "趋势上涨": 1.0
        })
        if hmm_state and hmm_state in decay_map:
            hmm_decay = decay_map[hmm_state]
            confidence_before_decay = confidence
            confidence = round(max(0.0, min(1.0, confidence * hmm_decay)), 3)
            analyzer_logger.info(
                f"HMM衰减: state={hmm_state}, decay={hmm_decay}, "
                f"confidence {confidence_before_decay:.3f}→{confidence:.3f}"
            )

        # P2: 高波动状态下action_gate门槛提升
        gate_boost = vcfg.get("hmm_gate_threshold_boost", {})
        allow_buy_threshold = 0.7
        cautious_buy_threshold = 0.5
        if hmm_state == "高波动" and "高波动" in gate_boost:
            allow_buy_threshold = gate_boost["高波动"].get("allow_buy", 0.8)
            cautious_buy_threshold = gate_boost["高波动"].get("cautious_buy", 0.6)

        if conflicts or direction_consensus == "mixed":
            risk_level = "medium"
        else:
            risk_level = "low"
        if len(conflicts) >= 2 or direction_consensus == "bearish":
            risk_level = "high"
        if missing_dimensions:
            risk_level = "high" if risk_level == "low" else risk_level

        signal = trading_signal.get("signal", "hold")
        if position_status == "未持有":
            if signal in ("buy", "strong_buy") and direction_consensus == "bullish" and confidence >= allow_buy_threshold:
                if surge_risk:
                    action_gate = "cautious_buy"
                elif fund_ml_diverged or boll_narrow:
                    action_gate = "cautious_buy"
                else:
                    action_gate = "allow_buy"
            elif signal in ("buy", "strong_buy") and direction_consensus == "bullish" and confidence >= cautious_buy_threshold:
                if surge_risk:
                    action_gate = "watch"
                elif fund_ml_diverged or boll_narrow:
                    action_gate = "watch"
                else:
                    action_gate = "cautious_buy"
            elif direction_consensus == "bearish" and confidence >= 0.6:
                action_gate = "avoid_buy"
            else:
                action_gate = "watch"
        else:
            if direction_consensus == "bearish" and risk_level == "high":
                action_gate = "reduce_position"
            elif direction_consensus == "bearish" and risk_level == "medium":
                action_gate = "cautious_hold"
            else:
                action_gate = "hold_position"

        # P5: 交叉验证关键日志
        analyzer_logger.info(
            f"交叉验证评分: 技术={technical_score:.3f}, 资金={fund_score:.3f}, "
            f"情绪={sentiment_score:.3f}, 信号={signal_score:.3f}"
        )
        analyzer_logger.info(
            f"方向共识: {direction_consensus}, bull_ratio={bull_ratio:.3f}, "
            f"bear_ratio={bear_ratio:.3f}, active_weight={active_weight_total:.3f}"
        )
        if supporting_factors:
            analyzer_logger.info(f"支持因素: {', '.join(supporting_factors)}")
        if opposing_factors:
            analyzer_logger.info(f"反对因素: {', '.join(opposing_factors)}")
        if conflicts:
            analyzer_logger.info(f"冲突检测: {', '.join(conflicts)}")
        analyzer_logger.info(
            f"置信度: signal={signal_score:.3f}*{signal_weight} + "
            f"agreement={agreement_ratio:.3f}*{agreement_weight} - "
            f"conflict={conflict_penalty:.3f} - missing={missing_penalty:.3f}"
            + (f" - fund_ml_div={fund_ml_divergence_penalty:.3f}" if fund_ml_divergence_penalty > 0 else "")
            + f" = {confidence:.3f}"
        )
        if hmm_decay < 1.0:
            analyzer_logger.info(
                f"HMM衰减: 状态={hmm_state}, 衰减因子={hmm_decay}, "
                f"confidence {confidence_before_decay:.3f}→{confidence:.3f}"
            )
        if mtf_factor != 1.0:
            analyzer_logger.info(
                f"多时间框架: consistency={mtf_consistency}, factor={mtf_factor}, "
                f"confidence {confidence_before_mtf:.3f}→{confidence:.3f}"
            )
        downgrade_reasons = []
        if surge_risk:
            downgrade_reasons.append("追高风险降级")
        if fund_ml_diverged:
            downgrade_reasons.append("资金-ML背离降级")
        if boll_narrow:
            downgrade_reasons.append("布林带极窄降级")
        analyzer_logger.info(
            f"行动门控: action_gate={action_gate}, risk_level={risk_level}, "
            f"position={position_status}, original_signal={signal}"
            + (f", {','.join(downgrade_reasons)}" if downgrade_reasons else "")
        )

        missing_note = f"缺失维度：{'、'.join(missing_dimensions)}。" if missing_dimensions else ""

        distribution = indicators.get("Distribution", {})
        dist_w20 = distribution.get("W20", {})
        dist_w60 = distribution.get("W60", {})
        dist_window = dist_w20 if dist_w20.get("skewness", {}).get("latest") is not None else dist_w60

        skewness_val = None
        kurtosis_val = None
        skew_data = dist_window.get("skewness", {})
        kurt_data = dist_window.get("kurtosis", {})
        if isinstance(skew_data, dict):
            skewness_val = skew_data.get("latest")
        if isinstance(kurt_data, dict):
            kurtosis_val = kurt_data.get("latest")

        try:
            skewness_val = float(skewness_val) if skewness_val is not None else None
        except (TypeError, ValueError):
            skewness_val = None
        try:
            kurtosis_val = float(kurtosis_val) if kurtosis_val is not None else None
        except (TypeError, ValueError):
            kurtosis_val = None

        if skewness_val is not None and skewness_val < -0.5:
            confidence = confidence * 0.8
            if direction_consensus == "bullish":
                weighted_bullish *= 0.8
            opposing_factors.append("收益率左偏分布")

        if kurtosis_val is not None and kurtosis_val > 5:
            risk_level_map = {"low": "medium", "medium": "high"}
            risk_level = risk_level_map.get(risk_level, risk_level)
            conflicts.append("尾部风险显著")

        market_structure = indicators.get("MarketStructure", {})
        rs_data = market_structure.get("RelativeStrength", {})
        beta_data = market_structure.get("Beta", {})

        rs_latest = rs_data.get("latest") if isinstance(rs_data, dict) else None
        beta_latest = beta_data.get("latest") if isinstance(beta_data, dict) else None

        try:
            rs_latest = float(rs_latest) if rs_latest is not None else None
        except (TypeError, ValueError):
            rs_latest = None
        try:
            beta_latest = float(beta_latest) if beta_latest is not None else None
        except (TypeError, ValueError):
            beta_latest = None

        if rs_latest is not None and rs_latest > 1.2:
            confidence = min(1.0, confidence * 1.1)
            supporting_factors.append("相对强度强势")

        if beta_latest is not None and beta_latest > 1.5:
            risk_level_map = {"low": "medium", "medium": "high"}
            risk_level = risk_level_map.get(risk_level, risk_level)
            opposing_factors.append("高Beta风险")

        validation_note = (
            f"方向{direction_consensus}，置信度{confidence:.3f}，风险{risk_level}。"
            f"支持因素{len(supporting_factors)}项，反对因素{len(opposing_factors)}项，"
            f"冲突{len(conflicts)}项。{missing_note}"
        )

        result = {
            "direction_consensus": direction_consensus,
            "action_gate": action_gate,
            "risk_level": risk_level,
            "confidence": confidence,
            "supporting_factors": supporting_factors,
            "opposing_factors": opposing_factors,
            "conflicts": conflicts,
            "validation_note": validation_note,
            "weighted_bullish": round(weighted_bullish, 3),
            "weighted_bearish": round(weighted_bearish, 3),
            "active_weight_total": round(active_weight_total, 3),
            "missing_dimensions": missing_dimensions,
        }
        if persistence_info:
            result["signal_persistence"] = persistence_info

        if self._stress_test_config.get("enabled", False) and history_df is not None:
            try:
                from scripts.core.stress_test import MonteCarloStressTest
                original_signal = trading_signal.get("signal", "hold")
                self._pending_stress_test = {
                    "analyzer": self,
                    "history_df": history_df,
                    "indicators": indicators,
                    "original_signal": original_signal,
                }
                result["stress_test"] = {
                    "status": "computing",
                    "signal_flip_rate": None,
                    "is_robust": None,
                    "risk_metrics": None,
                    "simulation_count": 0,
                    "original_signal": original_signal,
                }
            except Exception as e:
                analyzer_logger.warning(f"蒙特卡洛压力测试配置异常: {e}")

        return result

    def get_limit_pct(self, stock_code: str, stock_name: str = "") -> float:
        """根据股票代码和名称获取涨跌停比例

        参数:
            stock_code: 股票代码
            stock_name: 股票名称（用于判断ST股）
        """
        # M-04: ST股判断
        if stock_name:
            name_upper = str(stock_name).upper()
            if "ST" in name_upper or "*ST" in name_upper or "S*" in name_upper:
                return 0.05

        if stock_code.startswith("30") or stock_code.startswith("68"):
            return 0.20
        else:
            return 0.10

    def predict_price_range(
        self,
        data: Dict,
        indicators: Dict,
        stock_code: str = "",
        trading_signal: Dict = None,
    ) -> Dict:
        """预测价格区间（含未来两天预测，涨跌停校验）"""
        analyzer_logger.info("=" * 50)
        analyzer_logger.info("开始价格预测...")

        info = data.get("stock_info", {})
        history_df = data.get("history_data")

        current_price = info.get("最新价", 0)
        try:
            current_price = float(current_price)
        except (ValueError, TypeError):
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

        closes = history_df["收盘"]
        if hasattr(closes, "values"):
            closes = pd.Series(closes.values, index=history_df.index)

        boll = indicators.get("BOLL", {})
        boll_latest = boll.get("latest", {})
        if isinstance(boll_latest, dict):
            lower = boll_latest.get("lower")
            upper = boll_latest.get("upper")
        else:
            lower = None
            upper = None

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

        trend_direction = TREND_NEUTRAL
        technical_analysis = data.get("technical_analysis", {})
        tech_score = technical_analysis.get("score", 0.5)

        # M-07: 趋势持续性判断 - 基于历史评分
        history_df = data.get("history_data")
        trend_persistence = "new"

        if history_df is not None and len(history_df) >= 20:
            macd_series = indicators.get("MACD", {}).get("series", {})
            dif_series = macd_series.get("DIF") if isinstance(macd_series, dict) else None
            dea_series = macd_series.get("DEA") if isinstance(macd_series, dict) else None

            recent_scores = []
            lookback = min(5, len(history_df) - 5)
            step = max(1, lookback // 3)

            if dif_series is not None and dea_series is not None and hasattr(dif_series, '__len__') and len(dif_series) >= 30:
                for i in range(len(history_df) - lookback, len(history_df) - 1, step):
                    window_start = max(0, i - 30)
                    window_dif = dif_series.iloc[window_start:i+1] if hasattr(dif_series, 'iloc') else dif_series[window_start:i+1]
                    window_dea = dea_series.iloc[window_start:i+1] if hasattr(dea_series, 'iloc') else dea_series[window_start:i+1]
                    if len(window_dif) >= 2 and len(window_dea) >= 2:
                        last_dif = window_dif.iloc[-1] if hasattr(window_dif, 'iloc') else window_dif[-1]
                        prev_dif = window_dif.iloc[-2] if hasattr(window_dif, 'iloc') else window_dif[-2]
                        last_dea = window_dea.iloc[-1] if hasattr(window_dea, 'iloc') else window_dea[-1]
                        prev_dea = window_dea.iloc[-2] if hasattr(window_dea, 'iloc') else window_dea[-2]
                        try:
                            last_dif = float(last_dif)
                            prev_dif = float(prev_dif)
                            last_dea = float(last_dea)
                            prev_dea = float(prev_dea)
                            s = 0.5
                            if last_dif > last_dea and prev_dif <= prev_dea:
                                s += 0.2
                            elif last_dif < last_dea and prev_dif >= prev_dea:
                                s -= 0.2
                            elif last_dif > last_dea:
                                s += 0.1
                            elif last_dif < last_dea:
                                s -= 0.1
                            recent_scores.append(s)
                        except (TypeError, ValueError):
                            pass

            if len(recent_scores) >= 5:
                avg_recent = sum(recent_scores[-3:]) / 3
                avg_all = sum(recent_scores) / len(recent_scores)

                if avg_recent > 0.6 and avg_all > 0.55:
                    trend_persistence = "strong"
                elif avg_recent < 0.4 and avg_all < 0.45:
                    trend_persistence = "strong"
                elif abs(avg_recent - avg_all) < 0.1:
                    trend_persistence = "stable"
                else:
                    trend_persistence = "weak"

        if tech_score > 0.6:
            trend_direction = TREND_UP
        elif tech_score < 0.4:
            trend_direction = TREND_DOWN

        trading_signal = trading_signal or {}
        signal_name = trading_signal.get("signal", "")
        signal_score = self._safe_score(trading_signal.get("score"), default=0.5)
        rsi_12_data = indicators.get("RSI", {}).get("RSI(12)", {})
        rsi_12_signal = rsi_12_data.get("signal", "") if isinstance(rsi_12_data, dict) else ""
        rsi_12_value = None
        if isinstance(rsi_12_data, dict):
            rsi_12_value = rsi_12_data.get("latest")
        else:
            rsi_12_value = rsi_12_data
        rsi_12_value = self._latest_indicator_value(rsi_12_value)
        kdj_signal_for_risk = (
            indicators.get("KDJ", {}).get("signal", "")
            if isinstance(indicators.get("KDJ"), dict)
            else ""
        )
        has_overheat_risk = (
            rsi_12_signal == "超买"
            or (rsi_12_value is not None and rsi_12_value >= 70)
            or kdj_signal_for_risk == "超买"
        )

        if signal_name in ("strong_buy", "buy") and tech_score >= 0.5 and not has_overheat_risk:
            trend_direction = TREND_UP
        elif signal_name in ("sell", "watch") and tech_score <= 0.5:
            trend_direction = TREND_DOWN
        elif signal_score >= 0.7 and tech_score >= 0.5 and not has_overheat_risk:
            trend_direction = TREND_UP

        if trend_direction == TREND_UP:
            if tech_score >= 0.8 and trend_persistence != "weak":
                trend = TREND_STRONG_UP
            else:
                trend = TREND_UP
        elif trend_direction == TREND_DOWN:
            if tech_score <= 0.2 and trend_persistence != "weak":
                trend = TREND_STRONG_DOWN
            else:
                trend = TREND_DOWN
        else:
            trend = TREND_NEUTRAL

        trend_strength = abs(tech_score - 0.5) / 0.5 if tech_score != 0.5 else 0

        atr_mult = self.prediction_config.get("atr_multiplier", 1.5)
        atr_mult = atr_mult * (0.8 + 0.4 * trend_strength)

        if trend_persistence == "strong":
            atr_mult *= 1.3
        elif trend_persistence == "weak":
            atr_mult *= 0.8

        # 使用ATR（任务T-03）
        atr_data = indicators.get("ATR", {})
        atr_value = None
        if isinstance(atr_data, dict):
            atr_value = atr_data.get("latest")
            if hasattr(atr_value, "iloc"):
                atr_value = atr_value.iloc[-1] if not pd.isna(atr_value.iloc[-1]) else None
            try:
                atr_value = float(atr_value) if atr_value is not None else None
            except (TypeError, ValueError):
                atr_value = None

        closes = history_df["收盘"]
        if hasattr(closes, "values"):
            closes = pd.Series(closes.values, index=history_df.index)
            closes = closes.dropna()

        if atr_value and current_price:
            price_range = atr_value
        else:
            price_range = resistance - support

        day_range = price_range * 0.5

        if len(closes) >= 20:
            ma20 = closes.rolling(window=20).mean().iloc[-1]
            if pd.isna(ma20):
                ma20 = current_price
        else:
            ma20 = current_price

        deviation = (current_price - ma20) / ma20 if ma20 > 0 and current_price else 0
        deviation = max(-0.15, min(0.15, deviation))

        mean_reversion_strength = abs(deviation) * 2
        mean_reversion_factor = 1 - mean_reversion_strength * 0.3

        if abs(deviation) > 0.1:
            ma_target = ma20
        else:
            ma_target = None

        # 涨跌停校验（任务T-14）
        stock_name = info.get("名称", "")
        limit_pct = self.get_limit_pct(stock_code, stock_name) if stock_code else 0.10
        limit_up = current_price * (1 + limit_pct) if current_price else None
        limit_down = current_price * (1 - limit_pct) if current_price else None

        if trend == TREND_STRONG_UP:
            if ma_target and deviation > 0.1:
                base_target_high = min(current_price + price_range * atr_mult * 1.3, ma_target * 1.02) * mean_reversion_factor + ma_target * (1 - mean_reversion_factor)
            else:
                base_target_high = current_price + price_range * atr_mult * 1.3
            base_target_low = current_price + price_range * 0.4
        elif trend == TREND_UP:
            if ma_target and deviation > 0.1:
                base_target_high = min(current_price + price_range * atr_mult, ma_target * 1.02) * mean_reversion_factor + ma_target * (1 - mean_reversion_factor)
            else:
                base_target_high = current_price + price_range * atr_mult
            base_target_low = current_price + price_range * 0.3
        elif trend == TREND_DOWN:
            if ma_target and deviation < -0.1:
                base_target_low = max(current_price - price_range * atr_mult, ma_target * 0.98) * mean_reversion_factor + ma_target * (1 - mean_reversion_factor)
            else:
                base_target_low = current_price - price_range * atr_mult
            base_target_high = current_price - price_range * 0.3
        elif trend == TREND_STRONG_DOWN:
            if ma_target and deviation < -0.1:
                base_target_low = max(current_price - price_range * atr_mult * 1.3, ma_target * 0.98) * mean_reversion_factor + ma_target * (1 - mean_reversion_factor)
            else:
                base_target_low = current_price - price_range * atr_mult * 1.3
            base_target_high = current_price - price_range * 0.4
        else:
            base_target_low = support
            base_target_high = resistance

        # 涨跌停限制
        if limit_up and base_target_high:
            base_target_high = min(base_target_high, limit_up)
        if limit_down and base_target_low:
            base_target_low = max(base_target_low, limit_down)

        day1_trend = trend
        day2_trend = trend

        macd = indicators.get("MACD", {}).get("signal", "")
        rsi_6 = indicators.get("RSI", {}).get("RSI(6)", {}).get("signal", "")
        rsi_12 = indicators.get("RSI", {}).get("RSI(12)", {}).get("signal", "")

        # M-04：价格预测比例与趋势强度挂钩
        tech_score = technical_analysis.get("score", 0.5)
        if tech_score >= 0.7:
            day_range_mult_low, day_range_mult_high = 0.2, 0.8
        elif tech_score >= 0.5:
            day_range_mult_low, day_range_mult_high = 0.4, 0.6
        else:
            day_range_mult_low, day_range_mult_high = 0.3, 0.7

        # M-08：day2趋势修正改用RSI(12)（更稳定）
        if rsi_12 == "超买":
            day2_trend = TREND_DOWN
        elif rsi_12 == "超卖":
            day2_trend = TREND_UP

        if trend == TREND_STRONG_UP:
            day1 = {
                "target_low": round(current_price + day_range * day_range_mult_low, 2),
                "target_high": round(current_price + day_range * day_range_mult_high, 2),
                "trend": day1_trend,
                "signal": "强势看涨",
            }
            day2 = {
                "target_low": round(base_target_low + day_range * 0.5, 2),
                "target_high": round(base_target_high, 2),
                "trend": day2_trend,
                "signal": "强势延续" if day2_trend in (TREND_STRONG_UP, TREND_UP) else "注意获利回吐",
            }
        elif trend == TREND_UP:
            day1 = {
                "target_low": round(current_price + day_range * day_range_mult_low, 2),
                "target_high": round(current_price + day_range * day_range_mult_high, 2),
                "trend": day1_trend,
                "signal": "看涨延续",
            }
            day2 = {
                "target_low": round(base_target_low + day_range * 0.5, 2),
                "target_high": round(base_target_high, 2),
                "trend": day2_trend,
                "signal": "持续上涨" if day2_trend in (TREND_STRONG_UP, TREND_UP) else "注意回调",
            }
        elif trend == TREND_DOWN:
            day1 = {
                "target_low": round(current_price - day_range * day_range_mult_high, 2),
                "target_high": round(current_price - day_range * day_range_mult_low, 2),
                "trend": day1_trend,
                "signal": "看跌延续",
            }
            day2 = {
                "target_low": round(base_target_low, 2),
                "target_high": round(base_target_high - day_range * 0.5, 2),
                "trend": day2_trend,
                "signal": "持续下跌" if day2_trend in (TREND_STRONG_DOWN, TREND_DOWN) else "注意反弹",
            }
        elif trend == TREND_STRONG_DOWN:
            day1 = {
                "target_low": round(current_price - day_range * day_range_mult_high, 2),
                "target_high": round(current_price - day_range * day_range_mult_low, 2),
                "trend": day1_trend,
                "signal": "强势看跌",
            }
            day2 = {
                "target_low": round(base_target_low, 2),
                "target_high": round(base_target_high - day_range * 0.5, 2),
                "trend": day2_trend,
                "signal": "跌势加速" if day2_trend in (TREND_STRONG_DOWN, TREND_DOWN) else "注意超跌反弹",
            }
        else:
            day1 = {
                "target_low": round(current_price - day_range * 0.5, 2),
                "target_high": round(current_price + day_range * 0.5, 2),
                "trend": TREND_NEUTRAL,
                "signal": "震荡整理",
            }
            day2 = {
                "target_low": round(support, 2),
                "target_high": round(resistance, 2),
                "trend": TREND_NEUTRAL,
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
            "limit_pct": limit_pct,
        }

        if self._ml_enabled and stock_code:
            try:
                model_dir = self._ml_config.get("model_dir", "models/")
                stock_model_dir = os.path.join(model_dir, stock_code)

                # 每次分析都检查是否需要加载对应股票的模型
                need_load = False
                need_load_reason = ""
                if self._ml_loaded_stock != stock_code:
                    need_load = True
                    need_load_reason = f"当前加载={self._ml_loaded_stock}, 目标={stock_code}"
                elif not self._ml_predictor.is_ready():
                    need_load = True
                    need_load_reason = f"模型未就绪(loaded_stock={self._ml_loaded_stock})"

                if need_load:
                    analyzer_logger.info(f"ML模型需加载: {need_load_reason}")
                    if os.path.isdir(stock_model_dir):
                        load_ok = self._ml_predictor.load(stock_model_dir)
                        if load_ok:
                            self._ml_loaded_stock = stock_code
                            analyzer_logger.info(f"ML模型加载成功: {stock_code} -> {stock_model_dir}")
                        else:
                            analyzer_logger.warning(f"ML模型加载失败: {stock_model_dir}")
                            self._ml_loaded_stock = None
                    else:
                        analyzer_logger.info(f"ML模型目录不存在: {stock_model_dir}, 使用纯规则预测")
                        self._ml_loaded_stock = None

                if self._ml_predictor.is_ready():
                    from scripts.core.feature_engineering import extract_feature_vector
                    feature_names, feature_values = extract_feature_vector(indicators)
                    if len(feature_values) > 0:
                        X = feature_values.reshape(1, -1)
                        ml_prediction = self._ml_predictor.predict(X, feature_names=feature_names)
                        if ml_prediction:
                            alpha = self._ml_alpha
                            result = hybrid_predict(result, ml_prediction, alpha)
                            analyzer_logger.info(
                                f"  ML混合预测: alpha={alpha}, "
                                f"ml_return={ml_prediction.get('next_day_return', 'N/A')}, "
                                f"ml_direction={ml_prediction.get('direction', 'N/A')}"
                            )
                    else:
                        analyzer_logger.warning("ML特征提取为空，跳过ML预测")
                else:
                    analyzer_logger.info(f"ML模型未就绪，使用纯规则预测: {stock_code}")
            except Exception as e:
                analyzer_logger.warning(f"ML混合预测异常，使用纯规则预测: {e}")

        if "ml_prediction" not in result:
            result["ml_prediction"] = None
            result["hybrid_alpha"] = 1.0

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

    def generate_recommendation(
        self,
        all_data: Dict,
        position_status: str = "未持有",
        cost_price: float = None,
    ) -> Dict:
        indicators = all_data.get("indicators")
        if not indicators or "error" in indicators:
            history_df = all_data.get("history_data")
            if history_df is not None and not history_df.empty:
                from scripts.technical_indicators import calculate_all_indicators
                indicators = calculate_all_indicators(history_df)
            else:
                indicators = {"error": "无法计算技术指标"}
            all_data["indicators"] = indicators

        current_price = all_data.get("stock_info", {}).get("最新价", 0)
        try:
            current_price = float(current_price) if current_price else 0
        except (TypeError, ValueError):
            current_price = 0

        stock_code = all_data.get("stock_code", "")

        technical_analysis = self.analyze_technical(indicators, current_price)
        fund_flow_analysis = self.analyze_fund_flow(
            all_data.get("fund_flow", {}), all_data.get("stock_info", {})
        )

        market_data = all_data.get("market_data")
        sentiment_analysis = self.analyze_market_sentiment(all_data, market_data)

        all_data["technical_analysis"] = technical_analysis

        analysis = {
            "technical": technical_analysis,
            "fund_flow": fund_flow_analysis,
            "sentiment": sentiment_analysis,
            "data_quality": all_data.get("data_quality", "normal"),
        }

        trading_signal = self.generate_trading_signal(analysis, position_status, market_data)
        price_prediction = self.predict_price_range(
            all_data, indicators, stock_code, trading_signal
        )
        validation = self.cross_validate_analysis(
            analysis,
            price_prediction,
            indicators,
            trading_signal,
            position_status,
            current_price,
            history_df=all_data.get("history_data"),
        )
        trading_signal["reason"] = validation.get("validation_note", "")
        price_prediction["validation_confidence"] = validation.get("confidence", 0.5)
        price_prediction["validation_note"] = validation.get("validation_note", "")

        if position_status == "已持有":
            position_strategy = self.generate_position_strategy(
                all_data, indicators, current_price, cost_price, trading_signal, validation
            )
        else:
            position_strategy = self.generate_buy_strategy(
                all_data, indicators, current_price, trading_signal, validation
            )

        result = {
            "analysis": analysis,
            "trading_signal": trading_signal,
            "price_prediction": price_prediction,
            "validation": validation,
            "indicators": indicators,
            "position_strategy": position_strategy,
            "position_status": position_status,
        }

        if self._hmm_detector is not None and self._hmm_detector.is_ready():
            history_df = all_data.get("history_data")
            if history_df is not None and not history_df.empty and "收盘" in history_df.columns:
                try:
                    closes = history_df["收盘"].values.astype(np.float64)
                    returns = np.diff(closes) / closes[:-1]
                    vols = np.zeros_like(returns)
                    window = 20
                    for i in range(len(returns)):
                        start = max(0, i - window + 1)
                        vols[i] = np.std(returns[start:i + 1]) if i > 0 else 0.0
                    volumes = history_df["成交量"].values.astype(np.float64) if "成交量" in history_df.columns else np.ones(len(closes))
                    volume_changes = np.diff(volumes) / (volumes[:-1] + 1e-10)
                    hmm_result = self._hmm_detector.predict(returns, vols, volume_changes)
                    result["hmm_state"] = {
                        "current_state": hmm_result.get("current_state", "未知"),
                        "state_probabilities": hmm_result.get("state_probabilities", {}),
                        "transition_matrix": hmm_result.get("transition_matrix"),
                    }
                except Exception as e:
                    analyzer_logger.warning(f"HMM状态预测失败: {e}")
        elif self._regime_detector is not None:
            history_df = all_data.get("history_data")
            if history_df is not None and not history_df.empty and "收盘" in history_df.columns:
                try:
                    latest_close = float(history_df["收盘"].iloc[-1])
                    prev_close = float(history_df["收盘"].iloc[-2]) if len(history_df) > 1 else latest_close
                    change_pct = (latest_close - prev_close) / prev_close * 100 if prev_close != 0 else 0
                    vol_col = "成交量" if "成交量" in history_df.columns else None
                    volume_ratio = 1.0
                    if vol_col and len(history_df) > 1:
                        latest_vol = float(history_df[vol_col].iloc[-1])
                        prev_vol = float(history_df[vol_col].iloc[-2])
                        volume_ratio = latest_vol / prev_vol if prev_vol != 0 else 1.0
                    boll = indicators.get("BOLL", {})
                    bandwidth = boll.get("latest", {}).get("bandwidth") if isinstance(boll.get("latest"), dict) else None
                    volatility_signal = "正常"
                    if bandwidth is not None:
                        if bandwidth < 10:
                            volatility_signal = "低波动"
                        elif bandwidth > 25:
                            volatility_signal = "高波动"
                    market_data = {
                        "volatility_signal": volatility_signal,
                        "volume_ratio": volume_ratio,
                        "market_change_pct": change_pct,
                    }
                    regime = self._regime_detector.detect_regime(market_data)
                    result["hmm_state"] = {
                        "current_state": regime,
                        "state_probabilities": {},
                        "transition_matrix": None,
                    }
                except Exception as e:
                    analyzer_logger.warning(f"规则市场状态检测失败: {e}")

        return result

    def generate_position_strategy(
        self,
        all_data: Dict,
        indicators: Dict,
        current_price: float,
        cost_price: float = None,
        trading_signal: Dict = None,
        validation: Dict = None,
    ) -> Dict:
        """生成持仓策略（已持有时使用）"""
        validation = validation or {}
        history_df = all_data.get("history_data")

        if cost_price:
            avg_cost = cost_price
        else:
            avg_cost = current_price

        price_change = ((current_price - avg_cost) / avg_cost) * 100 if avg_cost else 0

        macd = indicators.get("MACD", {})
        rsi = indicators.get("RSI", {})
        kdj = indicators.get("KDJ", {})
        boll = indicators.get("BOLL", {})

        macd_signal = macd.get("signal", "")
        rsi_value = rsi.get("RSI(12)", {}).get("latest")
        if hasattr(rsi_value, "iloc"):
            rsi_value = rsi_value.iloc[-1]
        kdj_signal = kdj.get("signal", "")

        # 兼容新旧BOLL返回格式
        boll_latest = boll.get("latest", {})
        if isinstance(boll_latest, dict):
            boll_upper = boll_latest.get("upper")
            boll_lower = boll_latest.get("lower")
            if hasattr(boll_upper, "iloc"):
                boll_upper = boll_upper.iloc[-1]
                boll_lower = boll_lower.iloc[-1] if boll_lower is not None else None
            try:
                boll_upper = float(boll_upper) if boll_upper is not None else None
                boll_lower = float(boll_lower) if boll_lower is not None else None
            except (TypeError, ValueError):
                boll_upper, boll_lower = None, None
        else:
            boll_upper = None
            boll_lower = None

        # 获取ATR用于动态止损
        atr = indicators.get("ATR", {})
        atr_value = None
        if isinstance(atr, dict):
            atr_latest = atr.get("latest")
            if isinstance(atr_latest, (int, float)):
                atr_value = float(atr_latest)
            elif hasattr(atr_latest, "iloc"):
                atr_value = float(atr_latest.iloc[-1]) if not atr_latest.empty else None
        elif isinstance(atr, (int, float)):
            atr_value = float(atr)

        # 动态止损（M-05止盈也基于ATR）
        if atr_value and atr_value > 0:
            atr_stop_loss_multiplier = 2.0
            atr_stop_profit_multiplier = 2.5
            atr_based_stop_loss = current_price - atr_value * atr_stop_loss_multiplier
            atr_based_stop_profit = current_price + atr_value * atr_stop_profit_multiplier
            target_price = atr_based_stop_profit
            stop_price = max(atr_based_stop_loss, current_price * (1 - 0.05))
            stop_profit_pct = round((atr_based_stop_profit - current_price) / current_price * 100, 2)
            stop_loss_pct = round(((stop_price - current_price) / current_price) * 100, 2)
        else:
            if price_change > 15:
                stop_profit_pct = 10
            elif price_change > 8:
                stop_profit_pct = 5
            else:
                stop_profit_pct = 3

            if price_change < -8:
                stop_loss_pct = -5
            elif price_change < -5:
                stop_loss_pct = -3
            else:
                stop_loss_pct = -2

            target_price = current_price * (1 + stop_profit_pct / 100)
            stop_price = current_price * (1 + stop_loss_pct / 100)

        signal_name = trading_signal.get("signal", "hold") if trading_signal else "hold"
        action_gate = validation.get("action_gate", "")
        direction_consensus = validation.get("direction_consensus", "")

        if action_gate in ("reduce", "reduce_position") or signal_name == "sell":
            position_adjust = "建议减仓"
        elif validation and direction_consensus != "bullish":
            position_adjust = "继续持有，等待趋势确认"
        elif signal_name in ("strong_buy", "buy") and direction_consensus and direction_consensus != "bullish":
            position_adjust = "继续持有，等待趋势确认"
        elif signal_name == "strong_buy":
            position_adjust = "可考虑加仓"
        elif rsi_value and rsi_value > 80:
            position_adjust = "建议减仓"
        elif rsi_value and rsi_value < 30:
            position_adjust = "可考虑补仓"
        elif macd_signal == "死叉" or kdj_signal == "死叉":
            position_adjust = "建议减仓"
        elif macd_signal == "金叉" or kdj_signal == "金叉":
            position_adjust = "继续持有"
        else:
            position_adjust = "继续持有"

        return {
            "avg_cost": round(avg_cost, 2),
            "current_price": current_price,
            "price_change_pct": round(price_change, 2),
            "stop_profit_price": round(target_price, 2),
            "stop_profit_pct": stop_profit_pct,
            "stop_loss_price": round(stop_price, 2),
            "stop_loss_pct": stop_loss_pct,
            "position_adjust": position_adjust,
            "cost_provided": cost_price is not None,
            "validation_note": validation.get("validation_note", ""),
            "validation_risk_level": validation.get("risk_level", ""),
            "reason": self._generate_position_reason(
                macd_signal, rsi_value, kdj_signal, price_change
            ),
        }

    def _generate_position_reason(
        self, macd_sig: str, rsi_val: float, kdj_sig: str, price_chg: float
    ) -> str:
        """生成持仓调整原因"""
        reasons = []
        if rsi_val and rsi_val > 70:
            reasons.append(f"RSI偏高({rsi_val:.1f})，注意回调风险")
        elif rsi_val and rsi_val < 30:
            reasons.append(f"RSI偏低({rsi_val:.1f})，存在反弹机会")
        if macd_sig == "死叉":
            reasons.append("MACD死叉，短期看跌")
        elif macd_sig == "金叉":
            reasons.append("MACD金叉，短期看涨")
        if kdj_sig == "死叉":
            reasons.append("KDJ死叉")
        elif kdj_sig == "超买":
            reasons.append("KDJ超买")
        if price_chg > 15:
            reasons.append("涨幅较大，注意止盈")
        if price_chg < -8:
            reasons.append("跌幅较大，注意止损")
        return "; ".join(reasons) if reasons else "无明显信号"

    def generate_buy_strategy(
        self,
        all_data: Dict,
        indicators: Dict,
        current_price: float,
        trading_signal: Dict = None,
        validation: Dict = None,
    ) -> Dict:
        """生成买入策略（未持有时使用）"""
        validation = validation or {}
        history_df = all_data.get("history_data")

        macd = indicators.get("MACD", {})
        rsi = indicators.get("RSI", {})
        kdj = indicators.get("KDJ", {})
        boll = indicators.get("BOLL", {})

        macd_signal = macd.get("signal", "")
        rsi_data = rsi.get("RSI(12)", {})
        if isinstance(rsi_data, dict):
            rsi_value = rsi_data.get("latest")
            series = rsi_data.get("series")
            if rsi_value is None and hasattr(series, "iloc"):
                rsi_value = series.iloc[-1]
        else:
            rsi_value = rsi_data
        if hasattr(rsi_value, "iloc"):
            rsi_value = rsi_value.iloc[-1]
        try:
            rsi_value = float(rsi_value) if rsi_value is not None else None
        except (TypeError, ValueError):
            rsi_value = None
        kdj_signal = kdj.get("signal", "") if isinstance(kdj, dict) else ""

        # 统一使用新格式访问BOLL
        boll_latest = boll.get("latest", {})
        if isinstance(boll_latest, dict):
            upper = boll_latest.get("upper")
            lower = boll_latest.get("lower")
        else:
            upper = None
            lower = None
        try:
            upper = float(upper) if upper is not None else None
            lower = float(lower) if lower is not None else None
        except (TypeError, ValueError):
            upper, lower = None, None

        technical_analysis = all_data.get("technical_analysis", {})
        tech_score = technical_analysis.get("score", 0)

        # 获取ATR用于动态止损
        atr = indicators.get("ATR", {})
        atr_value = None
        if isinstance(atr, dict):
            atr_latest = atr.get("latest")
            if isinstance(atr_latest, (int, float)):
                atr_value = float(atr_latest)
            elif hasattr(atr_latest, "iloc"):
                atr_value = float(atr_latest.iloc[-1]) if not atr_latest.empty else None
        elif isinstance(atr, (int, float)):
            atr_value = float(atr)

        signal_name = trading_signal.get("signal", "hold") if trading_signal else "hold"
        action_gate = validation.get("action_gate", "")
        validation_risk_level = validation.get("risk_level", "")
        buy_timing = "不建议买入"
        total_score = trading_signal.get("score", 0) if trading_signal else 0
        if validation and action_gate != "allow_buy":
            if signal_name in ("strong_buy", "buy"):
                buy_timing = "等待确认"
            else:
                buy_timing = "不建议买入"
        elif validation_risk_level == "high" or action_gate == "avoid_buy":
            if signal_name in ("strong_buy", "buy"):
                buy_timing = "等待确认"
            else:
                buy_timing = "不建议买入"
        elif signal_name == "strong_buy" and validation_risk_level != "high":
            buy_timing = "建议买入"
        elif signal_name == "buy" and validation_risk_level != "high":
            buy_timing = "可考虑买入"
        elif validation_risk_level != "high" and (tech_score >= 0.7 or total_score >= 0.7):
            buy_timing = "建议买入"
        elif validation_risk_level != "high" and total_score >= 0.5:
            buy_timing = "可考虑买入"
        elif macd_signal in ("金叉", "金叉确认", "多头"):
            buy_timing = "建议买入"
        elif kdj_signal == "金叉":
            buy_timing = "可考虑买入"
        elif rsi_value and rsi_value < 25:
            buy_timing = "RSI严重超卖，可以关注"
        elif rsi_value and rsi_value < 30:
            buy_timing = "RSI超卖，可以关注"

        # 基于ATR计算买入止损价
        if atr_value and atr_value > 0:
            atr_stop_loss_multiplier = 2.0
            risk_price = current_price - atr_value * atr_stop_loss_multiplier
            risk_price = max(risk_price, current_price * 0.90)  # 不超过10%止损
            risk_level = "中等（基于ATR）"
        elif upper and lower:
            if current_price < lower:
                risk_price = lower
                risk_level = "较低"
            elif current_price > upper:
                risk_price = upper
                risk_level = "较高"
            else:
                risk_price = current_price * 0.95
                risk_level = "中等"
        else:
            risk_price = current_price * 0.95
            risk_level = "中等"

        # C-07: 仓位计算逻辑修正
        # 公式: RSI=0时30%, RSI=50时20%, RSI=100时10%
        rsi_for_position = rsi_value if rsi_value and 0 < rsi_value < 100 else 50
        position_size = 10 + 20 * (1 - rsi_for_position / 100)
        position_size = max(10, min(30, position_size))

        # 下跌趋势中仓位减半
        is_downtrend = macd_signal in ("空头", "死叉") or kdj_signal in ("死叉", "超买")
        if is_downtrend:
            position_size = max(10, position_size / 2)

        distribution = indicators.get("Distribution", {})
        dist_w20 = distribution.get("W20", {})
        dist_w60 = distribution.get("W60", {})
        dist_window = dist_w20 if dist_w20.get("skewness", {}).get("latest") is not None else dist_w60
        skew_data = dist_window.get("skewness", {})
        skewness_val = skew_data.get("latest") if isinstance(skew_data, dict) else None
        try:
            skewness_val = float(skewness_val) if skewness_val is not None else None
        except (TypeError, ValueError):
            skewness_val = None
        if skewness_val is not None and skewness_val < -0.5:
            position_size = max(10, position_size / 2)

        market_structure = indicators.get("MarketStructure", {})
        beta_data = market_structure.get("Beta", {})
        beta_latest = beta_data.get("latest") if isinstance(beta_data, dict) else None
        try:
            beta_latest = float(beta_latest) if beta_latest is not None else None
        except (TypeError, ValueError):
            beta_latest = None
        if beta_latest is not None and beta_latest > 1.5:
            risk_price = current_price - (current_price - risk_price) * 0.7

        return {
            "current_price": current_price,
            "buy_timing": buy_timing,
            "position_size_pct": round(position_size, 1),
            "stop_loss_price": round(risk_price, 2),
            "validation_note": validation.get("validation_note", ""),
            "risk_level": risk_level,
            "validation_risk_level": validation.get("risk_level", ""),
            "risk_control": self._generate_risk_control(
                macd_signal, rsi_value, kdj_signal, upper, lower
            ),
        }

    def _generate_risk_control(
        self,
        macd_sig: str,
        rsi_val: float,
        kdj_sig: str,
        upper: float,
        lower: float,
    ) -> str:
        """生成风险控制建议"""
        controls = []
        if rsi_val and rsi_val > 70:
            controls.append("RSI偏高建仓风险大")
        if upper and rsi_val and rsi_val > 80:
            controls.append("接近上轨，建议观望")
        if kdj_sig == "超买":
            controls.append("KDJ超买，等回调")
        if macd_sig == "死叉":
            controls.append("MACD死叉，暂缓建仓")
        if not controls:
            controls.append("技术面无明显风险信号")
        return "; ".join(controls)
