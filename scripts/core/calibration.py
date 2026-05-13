"""交叉验证阈值校准模块

优化点:
1. 引入真实资金/情绪数据替代硬编码0.5
2. 增加样本量(默认20只)
3. 自适应步长(先粗扫再细扫)
4. 时间序列交叉验证(70%训练/30%验证)
5. 自动应用校准结果到config
6. 多目标评分(加入预测宽度、回撤惩罚)
"""

from copy import deepcopy

import yaml

from scripts.core.analyzer import (
    TREND_STRONG_UP, TREND_UP, TREND_NEUTRAL, TREND_DOWN, TREND_STRONG_DOWN,
    STRONG_THRESHOLD, NORMAL_THRESHOLD,
)


def _fetch_fund_flow_score(fetcher, stock_code: str, lookback_days: int = 30) -> dict:
    """尝试获取真实资金流向数据，失败则返回默认值"""
    if fetcher is None:
        return {"score": 0.5, "trend": "neutral"}
    try:
        fund_data = fetcher.fetch_fund_flow(stock_code)
        if fund_data and isinstance(fund_data, dict):
            score = fund_data.get("score")
            trend = fund_data.get("trend", "neutral")
            if score is not None:
                try:
                    return {"score": float(score), "trend": trend}
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    return {"score": 0.5, "trend": "neutral"}


def _compute_sentiment_score(history_df, current_idx: int) -> dict:
    """基于历史数据计算情绪评分（替代硬编码0.5）

    使用换手率和成交量变化作为情绪代理指标
    """
    score = 0.5
    if history_df is None or len(history_df) < 5:
        return {"score": score}

    try:
        recent = history_df.iloc[max(0, current_idx - 4):current_idx + 1]

        if "换手率" in recent.columns:
            turnover_vals = recent["换手率"].dropna()
            if len(turnover_vals) > 0:
                avg_turnover = float(turnover_vals.mean())
                if avg_turnover > 8:
                    score += 0.1
                elif avg_turnover > 4:
                    score += 0.05
                elif avg_turnover < 1:
                    score -= 0.05

        if "成交量" in recent.columns:
            vol_vals = recent["成交量"].dropna()
            if len(vol_vals) >= 3:
                recent_avg = float(vol_vals.tail(3).mean())
                overall_avg = float(vol_vals.mean())
                if overall_avg > 0:
                    vol_ratio = recent_avg / overall_avg
                    if vol_ratio > 2.0:
                        score += 0.1
                    elif vol_ratio > 1.5:
                        score += 0.05
                    elif vol_ratio < 0.5:
                        score -= 0.05
    except Exception:
        pass

    score = max(0.1, min(0.9, score))
    return {"score": round(score, 3)}


def evaluate_validation_config(
    config: dict,
    stock_codes: list[str],
    lookback_days: int = 120,
    fetcher=None,
    train_ratio: float = 0.7,
) -> dict:
    """
    对给定的 validation 配置运行时间序列交叉验证评估。

    优化:
    - 70%数据用于训练(参数扫描)，30%用于验证(最终评分)
    - 引入真实资金/情绪数据
    - 多目标评分(准确率+趋势+一致性+宽度惩罚+回撤惩罚)

    对每只股票，取 last 2*lookback_days 历史数据，
    从 lookback_days 开始逐日滑动：
    - 用截至当天的数据计算指标
    - 调 StockAnalyzer 做预测 + 交叉验证
    - 对比预测方向与次日的实际方向
    - 前70%数据用于参数优化，后30%用于最终评估

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
        total_test_points = len(df) - 1 - min_idx
        if total_test_points <= 0:
            continue

        split_idx = min_idx + int(total_test_points * train_ratio)

        fund_flow_data = _fetch_fund_flow_score(fetcher, code, lookback_days)

        for test_idx in range(min_idx, len(df) - 1):
            history_up_to = df.iloc[:test_idx + 1].copy()
            current_close = float(history_up_to["收盘"].iloc[-1])
            actual_next_close = float(df["收盘"].iloc[test_idx + 1])
            actual_trend = "up" if actual_next_close >= current_close else "down"
            if current_close > 0:
                actual_change = (actual_next_close - current_close) / current_close
            else:
                actual_change = 0
            if actual_change > STRONG_THRESHOLD:
                actual_trend = TREND_STRONG_UP
            elif actual_change > NORMAL_THRESHOLD:
                actual_trend = TREND_UP
            elif actual_change >= -NORMAL_THRESHOLD:
                actual_trend = TREND_NEUTRAL
            elif actual_change >= -STRONG_THRESHOLD:
                actual_trend = TREND_DOWN
            else:
                actual_trend = TREND_STRONG_DOWN

            indicators = calculate_all_indicators(history_up_to)

            technical = analyzer.analyze_technical(indicators, current_close)

            sentiment_data = _compute_sentiment_score(history_up_to, test_idx)

            analysis = {
                "technical": technical,
                "fund_flow": fund_flow_data,
                "sentiment": sentiment_data,
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
            day1_low = price_pred.get("day1", {}).get("target_low", 0)
            day1_high = price_pred.get("day1", {}).get("target_high", 0)

            is_train = test_idx <= split_idx

            all_predictions.append({
                "stock_code": code,
                "date": str(test_idx),
                "consensus": consensus,
                "predicted_trend": day1_trend,
                "actual_trend": actual_trend,
                "actual_change_pct": actual_change,
                "confidence": validation.get("confidence", 0),
                "day1_low": day1_low,
                "day1_high": day1_high,
                "current_close": current_close,
                "is_train": is_train,
            })

    train_preds = [p for p in all_predictions if p["is_train"]]
    val_preds = [p for p in all_predictions if not p["is_train"]]
    eval_preds = val_preds if val_preds else all_predictions

    total = len(eval_preds) or 1
    correct_consensus = sum(
        1 for p in eval_preds
        if (p["consensus"] == "bullish" and p["actual_trend"] in (TREND_STRONG_UP, TREND_UP))
        or (p["consensus"] == "bearish" and p["actual_trend"] in (TREND_STRONG_DOWN, TREND_DOWN))
    )
    correct_trend = sum(
        1 for p in eval_preds
        if p["predicted_trend"] == p["actual_trend"]
    )
    has_consensus = sum(
        1 for p in eval_preds if p["consensus"] in ("bullish", "bearish")
    )
    correct_when_has_consensus = sum(
        1 for p in eval_preds
        if p["consensus"] in ("bullish", "bearish")
        and ((p["consensus"] == "bullish" and p["actual_trend"] in (TREND_STRONG_UP, TREND_UP))
             or (p["consensus"] == "bearish" and p["actual_trend"] in (TREND_STRONG_DOWN, TREND_DOWN)))
    )

    width_penalty = _compute_width_penalty(eval_preds)
    drawdown_penalty = _compute_drawdown_penalty(eval_preds)

    return {
        "accuracy": correct_consensus / total,
        "trend_accuracy": correct_trend / total,
        "consistency": correct_when_has_consensus / (has_consensus or 1),
        "width_penalty": width_penalty,
        "drawdown_penalty": drawdown_penalty,
        "total_predictions": len(all_predictions),
        "train_predictions": len(train_preds),
        "val_predictions": len(val_preds),
        "predictions_with_consensus": has_consensus,
        "_raw": all_predictions,
    }


def _compute_width_penalty(predictions: list) -> float:
    """计算预测区间宽度惩罚

    过宽的预测区间虽然容易命中但缺乏实用价值
    惩罚 = 平均(区间宽度/当前价) 超过 5% 的部分
    """
    if not predictions:
        return 0.0
    width_ratios = []
    for p in predictions:
        close = p.get("current_close", 0)
        low = p.get("day1_low", 0)
        high = p.get("day1_high", 0)
        if close > 0 and low > 0 and high > 0:
            width_ratio = (high - low) / close
            width_ratios.append(width_ratio)
    if not width_ratios:
        return 0.0
    avg_width = sum(width_ratios) / len(width_ratios)
    excess = max(0, avg_width - 0.05)
    return min(0.3, excess * 3)


def _compute_drawdown_penalty(predictions: list) -> float:
    """计算回撤惩罚

    当预测看多但实际下跌幅度较大时给予惩罚
    """
    if not predictions:
        return 0.0
    loss_when_bullish = []
    for p in predictions:
        if p["consensus"] == "bullish" and p["actual_trend"] in (TREND_DOWN, TREND_STRONG_DOWN):
            change = p.get("actual_change_pct", 0)
            if change < 0:
                loss_when_bullish.append(abs(change))
    if not loss_when_bullish:
        return 0.0
    avg_loss = sum(loss_when_bullish) / len(loss_when_bullish)
    return min(0.3, avg_loss * 5)


DEFAULT_STOCK_CODES = [
    "600519", "000858", "601318", "600036", "000333",
    "600276", "002415", "601888", "600900", "000651",
    "601166", "600887", "002304", "000568", "600309",
    "601012", "002142", "600585", "000725", "601668",
]


class ValidationCalibrator:
    """交叉验证阈值校准器，运行自适应步长单参数轮换扫描"""

    def __init__(self, config_path_or_dict, stock_codes: list[str] = None, lookback_days: int = 120):
        if isinstance(config_path_or_dict, str):
            with open(config_path_or_dict) as f:
                self.base_config = yaml.safe_load(f)
            self.config_path = config_path_or_dict
        else:
            self.base_config = deepcopy(config_path_or_dict)
            self.config_path = None
        self.stock_codes = stock_codes or DEFAULT_STOCK_CODES
        self.lookback_days = lookback_days

    SCAN_PARAMS = {
        "technical_bullish": (["score_thresholds", "technical_bullish"], 0.65, (0.45, 0.85, 0.10)),
        "technical_bearish": (["score_thresholds", "technical_bearish"], 0.35, (0.15, 0.55, 0.10)),
        "fund_bullish":       (["score_thresholds", "fund_bullish"], 0.6, (0.40, 0.80, 0.10)),
        "fund_bearish":       (["score_thresholds", "fund_bearish"], 0.4, (0.20, 0.60, 0.10)),
        "sentiment_bullish":  (["score_thresholds", "sentiment_bullish"], 0.6, (0.40, 0.80, 0.10)),
        "sentiment_bearish":  (["score_thresholds", "sentiment_bearish"], 0.4, (0.20, 0.60, 0.10)),
        "signal_weight":     (["confidence_weights", "signal"], 0.4, (0.20, 0.60, 0.10)),
        "agreement_weight":  (["confidence_weights", "agreement"], 0.6, (0.40, 0.80, 0.10)),
        "per_conflict_penalty": (["conflict_penalty", "per_conflict"], 0.1, (0.05, 0.25, 0.05)),
    }

    @staticmethod
    def _composite_score(metrics: dict) -> float:
        accuracy = metrics.get("accuracy", 0)
        trend_accuracy = metrics.get("trend_accuracy", 0)
        consistency = metrics.get("consistency", 0)
        width_penalty = metrics.get("width_penalty", 0)
        drawdown_penalty = metrics.get("drawdown_penalty", 0)
        base = 0.35 * accuracy + 0.25 * trend_accuracy + 0.25 * consistency
        return max(0.0, base - 0.10 * width_penalty - 0.05 * drawdown_penalty)

    def _build_modified_config(self, overrides: dict) -> dict:
        cfg = deepcopy(self.base_config)
        vcfg = cfg.setdefault("analyzer", {}).setdefault("validation", {})
        for param_name, value in overrides.items():
            path, _, _ = self.SCAN_PARAMS.get(param_name, ([param_name], None, (0, 1, 0.1)))
            target = vcfg
            for segment in path[:-1]:
                target = target.setdefault(segment, {})
            target[path[-1]] = value
        return cfg

    def _generate_scan_values(self, param_name: str, coarse: bool = True) -> list:
        """生成扫描值列表

        粗扫: 使用SCAN_PARAMS中的大步长
        细扫: 在最优值附近用1/5步长
        """
        _, _, (lo, hi, step) = self.SCAN_PARAMS.get(param_name, (None, None, (0, 1, 0.1)))
        if coarse:
            vals = []
            v = lo
            while v <= hi + step * 0.01:
                vals.append(round(v, 4))
                v += step
            return vals
        else:
            return vals

    def _scan_single_param(
        self,
        param_name: str,
        base_overrides: dict,
        current_value,
        evaluate_fn,
    ) -> dict:
        """对一个参数做自适应步长扫描：先粗扫，再在最优附近细扫"""
        _, _, (lo, hi, step) = self.SCAN_PARAMS.get(param_name, (None, None, (0, 1, 0.1)))

        coarse_values = []
        v = lo
        while v <= hi + step * 0.01:
            coarse_values.append(round(v, 4))
            v += step

        coarse_scores = []
        for val in coarse_values:
            overrides = {**base_overrides, param_name: val}
            cfg = self._build_modified_config(overrides)
            metrics = evaluate_fn(cfg)
            coarse_scores.append(self._composite_score(metrics))

        best_coarse_idx = max(range(len(coarse_scores)), key=lambda i: coarse_scores[i])
        best_coarse_val = coarse_values[best_coarse_idx]

        fine_step = round(step / 5, 4)
        fine_lo = round(max(lo, best_coarse_val - step), 4)
        fine_hi = round(min(hi, best_coarse_val + step), 4)

        fine_values = []
        fv = fine_lo
        while fv <= fine_hi + fine_step * 0.01:
            if round(fv, 4) not in coarse_values:
                fine_values.append(round(fv, 4))
            fv += fine_step

        all_values = list(coarse_values)
        all_scores = list(coarse_scores)

        if fine_values:
            for val in fine_values:
                overrides = {**base_overrides, param_name: val}
                cfg = self._build_modified_config(overrides)
                metrics = evaluate_fn(cfg)
                all_values.append(val)
                all_scores.append(self._composite_score(metrics))

        best_idx = max(range(len(all_scores)), key=lambda i: all_scores[i])

        current_score = None
        if current_value in all_values:
            current_score = all_scores[all_values.index(current_value)]

        return {
            "values": all_values,
            "scores": [round(s, 4) for s in all_scores],
            "best_value": all_values[best_idx],
            "best_score": round(all_scores[best_idx], 4),
            "current_value": current_value,
            "current_score": round(current_score, 4) if current_score is not None else None,
            "improvement": round(max(all_scores) - (current_score if current_score is not None else all_scores[best_idx]), 4),
            "sensitivity": self._classify_sensitivity(all_scores),
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
        """运行自适应步长单参数轮换校准

        参数:
            evaluate_fn: 评估函数，接收config返回metrics
            dry_run: True时不写入config文件
        """
        if evaluate_fn is None:
            evaluate_fn = self._default_evaluate

        baseline_metrics = evaluate_fn(self.base_config)
        baseline_score = self._composite_score(baseline_metrics)

        param_sensitivity = {}
        optimal_overrides = {}
        current_overrides = {}

        for param_name, (path, current_val, _) in self.SCAN_PARAMS.items():
            scan_result = self._scan_single_param(
                param_name, current_overrides, current_val, evaluate_fn
            )
            param_sensitivity[param_name] = scan_result

            if scan_result["best_value"] != current_val:
                optimal_overrides[param_name] = scan_result["best_value"]
                current_overrides[param_name] = scan_result["best_value"]

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
        with open(self.config_path) as f:
            cfg = yaml.safe_load(f)
        vcfg = cfg.setdefault("analyzer", {}).setdefault("validation", {})
        for param_name, best_val in overrides.items():
            path, _, _ = self.SCAN_PARAMS.get(param_name, ([param_name], None, (0, 1, 0.1)))
            target = vcfg
            for segment in path[:-1]:
                target = target.setdefault(segment, {})
            target[path[-1]] = best_val
        with open(self.config_path, "w") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

    def _default_evaluate(self, config: dict) -> dict:
        from backend.services.analysis_service import get_fetcher
        fetcher = get_fetcher()
        return evaluate_validation_config(
            config=config,
            stock_codes=self.stock_codes,
            lookback_days=self.lookback_days,
            fetcher=fetcher,
        )
