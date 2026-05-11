"""交叉验证阈值校准模块"""

from copy import deepcopy
from typing import Optional

import pandas as pd
import yaml


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


class ValidationCalibrator:
    """交叉验证阈值校准器，运行单参数轮换扫描"""

    def __init__(self, config_path_or_dict, stock_codes: list[str], lookback_days: int = 120):
        if isinstance(config_path_or_dict, str):
            with open(config_path_or_dict) as f:
                self.base_config = yaml.safe_load(f)
            self.config_path = config_path_or_dict
        else:
            self.base_config = deepcopy(config_path_or_dict)
            self.config_path = None
        self.stock_codes = stock_codes or []
        self.lookback_days = lookback_days

    # 扫描参数定义：参数名 → (路径列表, 当前值, 扫描范围)
    SCAN_PARAMS = {
        "technical_bullish": (["score_thresholds", "technical_bullish"], 0.65, [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]),
        "technical_bearish": (["score_thresholds", "technical_bearish"], 0.35, [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55]),
        "fund_bullish":       (["score_thresholds", "fund_bullish"], 0.6, [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]),
        "fund_bearish":       (["score_thresholds", "fund_bearish"], 0.4, [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]),
        "sentiment_bullish":  (["score_thresholds", "sentiment_bullish"], 0.6, [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]),
        "sentiment_bearish":  (["score_thresholds", "sentiment_bearish"], 0.4, [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]),
        "bullish_consensus_margin": (["vote_thresholds", "bullish_consensus_margin"], 3, [1, 2, 3, 4, 5, 6]),
        "bearish_consensus_margin": (["vote_thresholds", "bearish_consensus_margin"], 2, [1, 2, 3, 4, 5]),
        "signal_weight":     (["confidence_weights", "signal"], 0.4, [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]),
        "agreement_weight":  (["confidence_weights", "agreement"], 0.6, [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]),
        "per_conflict_penalty": (["conflict_penalty", "per_conflict"], 0.1, [0.05, 0.10, 0.15, 0.20, 0.25]),
    }

    @staticmethod
    def _composite_score(metrics: dict) -> float:
        accuracy = metrics.get("accuracy", 0)
        trend_accuracy = metrics.get("trend_accuracy", 0)
        consistency = metrics.get("consistency", 0)
        return 0.40 * accuracy + 0.30 * trend_accuracy + 0.30 * consistency

    def _build_modified_config(self, overrides: dict) -> dict:
        """在 base_config 上应用 validation overrides"""
        cfg = deepcopy(self.base_config)
        vcfg = cfg.setdefault("analyzer", {}).setdefault("validation", {})
        for param_name, value in overrides.items():
            path, _, _ = self.SCAN_PARAMS.get(param_name, ([param_name], None, []))
            target = vcfg
            for segment in path[:-1]:
                target = target.setdefault(segment, {})
            target[path[-1]] = value
        return cfg

    def _scan_single_param(
        self,
        param_name: str,
        param_path: list,
        base_overrides: dict,
        current_value,
        scan_values: list,
        evaluate_fn,
    ) -> dict:
        """对一个参数做单参数轮换扫描"""
        scores = []
        for val in scan_values:
            overrides = {**base_overrides, param_name: val}
            cfg = self._build_modified_config(overrides)
            metrics = evaluate_fn(cfg)
            scores.append(self._composite_score(metrics))

        best_idx = max(range(len(scores)), key=lambda i: scores[i])
        return {
            "values": list(scan_values),
            "scores": scores,
            "best_value": scan_values[best_idx],
            "best_score": scores[best_idx],
            "current_value": current_value,
            "current_score": scores[scan_values.index(current_value)] if current_value in scan_values else None,
            "improvement": max(scores) - (scores[scan_values.index(current_value)] if current_value in scan_values else scores[best_idx]),
            "sensitivity": self._classify_sensitivity(scores),
        }

    @staticmethod
    def _classify_sensitivity(scores: list) -> str:
        if not scores or max(scores) == min(scores):
            return "none"
        pct_range = (max(scores) - min(scores)) / max(abs(s) for s in scores) * 100
        if pct_range >= 20:
            return "high"
        elif pct_range >= 10:
            return "medium"
        return "low"

    def run(
        self,
        evaluate_fn=None,
        dry_run: bool = False,
    ) -> dict:
        """运行单参数轮换校准"""
        if evaluate_fn is None:
            evaluate_fn = self._default_evaluate

        baseline_metrics = evaluate_fn(self.base_config)
        baseline_score = self._composite_score(baseline_metrics)

        param_sensitivity = {}
        optimal_overrides = {}
        current_overrides = {}

        for param_name, (path, current_val, scan_values) in self.SCAN_PARAMS.items():
            scan_result = self._scan_single_param(
                param_name, path, current_overrides, current_val, scan_values, evaluate_fn
            )
            param_sensitivity[param_name] = scan_result

            if scan_result["best_value"] != current_val:
                optimal_overrides[param_name] = scan_result["best_value"]

        calibrated_metrics = None
        if optimal_overrides:
            calibrated_cfg = self._build_modified_config(optimal_overrides)
            calibrated_metrics = evaluate_fn(calibrated_cfg)
        else:
            calibrated_metrics = baseline_metrics

        calibrated_score = self._composite_score(calibrated_metrics)

        report = {
            "target": "validation",
            "stock_sample": list(self.stock_codes),
            "lookback_days": self.lookback_days,
            "baseline": {
                "composite_score": round(baseline_score, 4),
                **{k: round(v, 4) for k, v in baseline_metrics.items() if isinstance(v, float)},
            },
            "calibrated": {
                "composite_score": round(calibrated_score, 4),
                **{k: round(v, 4) for k, v in calibrated_metrics.items() if isinstance(v, float)},
            },
            "optimal_params": {k: v["best_value"] for k, v in param_sensitivity.items()},
            "param_sensitivity": param_sensitivity,
            "improvement": {
                "composite_score_delta": round(calibrated_score - baseline_score, 4),
            },
        }

        if not dry_run and self.config_path and optimal_overrides:
            self._apply_config(optimal_overrides)

        return report

    def _apply_config(self, overrides: dict):
        """将最优参数写入 config.yaml"""
        with open(self.config_path) as f:
            cfg = yaml.safe_load(f)
        vcfg = cfg.setdefault("analyzer", {}).setdefault("validation", {})
        for param_name, best_val in overrides.items():
            path, _, _ = self.SCAN_PARAMS.get(param_name, ([param_name], None, []))
            target = vcfg
            for segment in path[:-1]:
                target = target.setdefault(segment, {})
            target[path[-1]] = best_val
        with open(self.config_path, "w") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

    def _default_evaluate(self, config: dict) -> dict:
        """默认评估：创建 fetcher 后调用 evaluate_validation_config"""
        from backend.services.analysis_service import get_fetcher
        fetcher = get_fetcher()
        return evaluate_validation_config(
            config=config,
            stock_codes=self.stock_codes,
            lookback_days=self.lookback_days,
            fetcher=fetcher,
        )
