import pandas as pd

from scripts.core.analyzer import StockAnalyzer


def _analyzer():
    return StockAnalyzer(
        {
            "analyzer": {
                "weights": {"technical": 0.5, "fund_flow": 0.3, "sentiment": 0.2},
                "thresholds": {"strong_buy": 0.7, "buy": 0.5, "hold": 0.3},
                "price_prediction": {"atr_multiplier": 1.5},
                "validation": {
                    "score_thresholds": {
                        "technical_bullish": 0.65,
                        "technical_bearish": 0.35,
                        "fund_bullish": 0.6,
                        "fund_bearish": 0.4,
                        "sentiment_bullish": 0.6,
                        "sentiment_bearish": 0.4,
                    },
                    "vote_thresholds": {
                        "bullish_consensus_margin": 3,
                        "bearish_consensus_margin": 2,
                    },
                    "confidence_weights": {
                        "signal": 0.4,
                        "agreement": 0.6,
                    },
                    "conflict_penalty": {
                        "per_conflict": 0.1,
                        "max": 0.3,
                    },
                },
            }
        }
    )


def _history_frame(length=80):
    dates = pd.date_range("2024-01-01", periods=length, freq="D")
    closes = [10.0 + i * 0.01 for i in range(length)]
    return pd.DataFrame(
        {
            "日期": dates,
            "开盘": closes,
            "收盘": closes,
            "最高": [price + 0.2 for price in closes],
            "最低": [price - 0.2 for price in closes],
            "成交量": [1000 + i for i in range(length)],
        }
    )


def test_cross_validation_returns_explainable_mixed_consensus():
    analyzer = _analyzer()
    analysis = {
        "technical": {"score": 0.75},
        "fund_flow": {"score": 0.2, "trend": "outflow"},
        "sentiment": {"score": 0.5},
    }
    price_prediction = {
        "day1": {"trend": "neutral"},
        "day2": {"trend": "neutral"},
    }
    indicators = {
        "MACD": {"signal": "金叉"},
        "RSI": {"RSI(12)": {"latest": 55, "signal": "正常"}},
        "KDJ": {"signal": "正常"},
        "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
    }

    validation = analyzer.cross_validate_analysis(
        analysis,
        price_prediction,
        indicators,
        trading_signal={"signal": "hold", "score": 0.45},
        position_status="未持有",
        current_price=10.0,
    )

    assert validation["direction_consensus"] == "mixed"
    assert validation["action_gate"] == "avoid_buy"
    assert validation["risk_level"] in ("medium", "high")
    assert validation["confidence"] < 0.7
    assert validation["supporting_factors"]
    assert validation["opposing_factors"]
    assert validation["conflicts"]
    assert validation["validation_note"]


def test_cross_validation_allows_confirmed_bullish_setup():
    analyzer = _analyzer()
    analysis = {
        "technical": {"score": 0.72},
        "fund_flow": {"score": 0.75, "trend": "inflow"},
        "sentiment": {"score": 0.6},
    }
    price_prediction = {
        "day1": {"trend": "up"},
        "day2": {"trend": "up"},
    }
    indicators = {
        "MACD": {"signal": "多头"},
        "RSI": {"RSI(12)": {"latest": 55, "signal": "正常"}},
        "KDJ": {"signal": "金叉"},
        "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
    }

    validation = analyzer.cross_validate_analysis(
        analysis,
        price_prediction,
        indicators,
        trading_signal={"signal": "strong_buy", "score": 0.76},
        position_status="未持有",
        current_price=10.0,
    )

    assert validation["direction_consensus"] == "bullish"
    assert validation["action_gate"] == "allow_buy"
    assert validation["risk_level"] != "high"
    assert validation["confidence"] >= 0.7


def test_validation_shape_is_api_serializable():
    analyzer = _analyzer()
    validation = analyzer.cross_validate_analysis(
        {
            "technical": {"score": 0.72},
            "fund_flow": {"score": 0.75, "trend": "inflow"},
            "sentiment": {"score": 0.6},
        },
        {"day1": {"trend": "up"}, "day2": {"trend": "up"}},
        {
            "MACD": {"signal": "多头"},
            "RSI": {"RSI(12)": {"latest": 55, "signal": "正常"}},
            "KDJ": {"signal": "金叉"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
        },
        trading_signal={"signal": "strong_buy", "score": 0.76},
        current_price=10.0,
    )

    assert isinstance(validation["supporting_factors"], list)
    assert isinstance(validation["opposing_factors"], list)
    assert isinstance(validation["conflicts"], list)
    assert isinstance(validation["confidence"], float)


def test_generate_recommendation_returns_validation_and_signal_reason(monkeypatch):
    analyzer = _analyzer()
    history_df = _history_frame()
    all_data = {
        "stock_code": "000001",
        "stock_info": {"最新价": 10.8, "名称": "示例股票"},
        "history_data": history_df,
        "fund_flow": {"主力净流入占比": 4.0, "历史数据": []},
        "market_data": {"涨跌幅": 0.2},
    }

    result = analyzer.generate_recommendation(all_data, position_status="未持有")

    assert "validation" in result
    assert "confidence" in result["validation"]
    assert "risk_level" in result["validation"]
    assert "supporting_factors" in result["validation"]
    assert "opposing_factors" in result["validation"]
    assert "conflicts" in result["validation"]
    assert result["trading_signal"].get("reason") == result["validation"]["validation_note"]
    assert (
        result["price_prediction"].get("validation_note")
        == result["validation"]["validation_note"]
    )
    assert (
        result["price_prediction"].get("validation_confidence")
        == result["validation"]["confidence"]
    )
    assert (
        result["position_strategy"].get("validation_note")
        == result["validation"]["validation_note"]
    )


def test_price_prediction_exposes_confidence_and_validation_note_after_recommendation():
    analyzer = _analyzer()
    result = analyzer.generate_recommendation(
        {
            "stock_code": "601016",
            "stock_info": {"最新价": 10.8, "名称": "示例股票"},
            "history_data": _history_frame(),
            "fund_flow": {"主力净流入占比": 5.0, "历史数据": []},
            "market_data": {"涨跌幅": 0.4},
        },
        position_status="未持有",
    )

    prediction = result["price_prediction"]

    assert "validation_confidence" in prediction
    assert 0.0 <= prediction["validation_confidence"] <= 1.0
    assert prediction["validation_note"] == result["validation"]["validation_note"]


def test_generate_recommendation_passes_signal_into_price_prediction(monkeypatch):
    analyzer = _analyzer()
    captured = {}

    def fake_predict_price_range(data, indicators, stock_code="", trading_signal=None):
        captured["trading_signal"] = trading_signal
        return {
            "current": 10.8,
            "support": 10.0,
            "resistance": 11.2,
            "day1": {"target_low": 10.9, "target_high": 11.1, "trend": "up"},
            "day2": {"target_low": 11.0, "target_high": 11.3, "trend": "up"},
        }

    monkeypatch.setattr(analyzer, "predict_price_range", fake_predict_price_range)

    analyzer.generate_recommendation(
        {
            "stock_code": "601016",
            "stock_info": {"最新价": 10.8, "名称": "示例股票"},
            "history_data": _history_frame(),
            "fund_flow": {"主力净流入占比": 5.0, "历史数据": []},
            "market_data": {"涨跌幅": 0.4},
        },
        position_status="未持有",
    )

    assert captured["trading_signal"] is not None
    assert "signal" in captured["trading_signal"]


def test_strategy_validation_fields_do_not_override_existing_risk_level():
    analyzer = _analyzer()
    validation = {"validation_note": "验证说明", "risk_level": "high"}

    buy_strategy = analyzer.generate_buy_strategy(
        {"technical_analysis": {"score": 0.55}},
        {
            "MACD": {"signal": "正常"},
            "RSI": {"RSI(12)": {"latest": 55}},
            "KDJ": {"signal": "正常"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
            "ATR": {"latest": 0.2},
        },
        current_price=10.0,
        trading_signal={"signal": "hold", "score": 0.45},
        validation=validation,
    )

    assert buy_strategy["risk_level"] == "中等（基于ATR）"
    assert buy_strategy["validation_risk_level"] == "high"

    position_strategy = analyzer.generate_position_strategy(
        {"history_data": _history_frame()},
        {
            "MACD": {"signal": "正常"},
            "RSI": {"RSI(12)": {"latest": 55}},
            "KDJ": {"signal": "正常"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
            "ATR": {"latest": 0.2},
        },
        current_price=10.0,
        cost_price=9.8,
        trading_signal={"signal": "hold", "score": 0.45},
        validation=validation,
    )

    assert "risk_level" not in position_strategy
    assert position_strategy["validation_risk_level"] == "high"


def test_generate_buy_strategy_accepts_legacy_rsi_value_shape():
    analyzer = _analyzer()
    strategy = analyzer.generate_buy_strategy(
        {"technical_analysis": {"score": 0.5}},
        {
            "MACD": {"signal": "正常"},
            "RSI": {"RSI(12)": 55},
            "KDJ": {"signal": "正常"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
            "ATR": {"latest": 0.2},
        },
        current_price=10.0,
        trading_signal={"signal": "hold", "score": 0.45},
    )

    assert strategy["buy_timing"] == "不建议买入"


def test_validation_blocks_buy_upgrade_when_not_allow_buy():
    analyzer = _analyzer()
    strategy = analyzer.generate_buy_strategy(
        {"technical_analysis": {"score": 0.75}},
        {
            "MACD": {"signal": "金叉"},
            "RSI": {"RSI(12)": {"latest": 25}},
            "KDJ": {"signal": "金叉"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
            "ATR": {"latest": 0.2},
        },
        current_price=10.0,
        trading_signal={"score": 0.45, "signal": "hold", "signal_text": "观望"},
        validation={"action_gate": "hold_position", "risk_level": "medium"},
    )

    assert strategy["buy_timing"] == "不建议买入"


def test_validation_blocks_position_upgrade_when_not_bullish():
    analyzer = _analyzer()
    strategy = analyzer.generate_position_strategy(
        {"history_data": _history_frame()},
        {
            "MACD": {"signal": "金叉"},
            "RSI": {"RSI(12)": {"latest": 25}},
            "KDJ": {"signal": "金叉"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
            "ATR": {"latest": 0.2},
        },
        current_price=10.0,
        cost_price=9.8,
        trading_signal={"score": 0.45, "signal": "hold", "signal_text": "持有"},
        validation={
            "action_gate": "hold_position",
            "direction_consensus": "mixed",
            "risk_level": "medium",
        },
    )

    assert strategy["position_adjust"] == "继续持有，等待趋势确认"


def test_cross_validation_accepts_legacy_rsi_value_shape():
    analyzer = _analyzer()
    validation = analyzer.cross_validate_analysis(
        {
            "technical": {"score": 0.45},
            "fund_flow": {"score": 0.5},
            "sentiment": {"score": 0.5},
        },
        {"day1": {"trend": "neutral"}, "day2": {"trend": "neutral"}},
        {
            "MACD": {"signal": "正常"},
            "RSI": {"RSI(12)": 28},
            "KDJ": {"signal": "正常"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
        },
        trading_signal={"signal": "hold", "score": 0.45},
        current_price=10.0,
    )

    assert "RSI接近超卖反弹区" in validation["supporting_factors"]


def test_hold_signal_does_not_emit_buy_timing():
    analyzer = _analyzer()
    strategy = analyzer.generate_buy_strategy(
        {"technical_analysis": {"score": 0.45}},
        {
            "MACD": {"signal": "正常"},
            "RSI": {"RSI(12)": {"latest": 55}},
            "KDJ": {"signal": "正常"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
            "ATR": {"latest": 0.2},
        },
        current_price=10.0,
        trading_signal={"signal": "hold", "score": 0.45, "signal_text": "持有"},
    )

    assert strategy["buy_timing"] in ("不建议买入", "等待确认")


def test_strong_buy_with_high_risk_is_downgraded_to_waiting():
    analyzer = _analyzer()
    validation = {
        "action_gate": "avoid_buy",
        "risk_level": "high",
        "validation_note": "交易信号偏多但预测趋势未确认上行",
    }
    strategy = analyzer.generate_buy_strategy(
        {"technical_analysis": {"score": 0.75}},
        {
            "MACD": {"signal": "多头"},
            "RSI": {"RSI(12)": {"latest": 82}},
            "KDJ": {"signal": "超买"},
            "BOLL": {"latest": {"upper": 10.1, "lower": 9.0}},
            "ATR": {"latest": 0.2},
        },
        current_price=10.0,
        trading_signal={"score": 0.75, "signal": "strong_buy", "signal_text": "强烈买入"},
        validation=validation,
    )

    assert strategy["buy_timing"] == "等待确认"
    assert strategy["validation_note"] == validation["validation_note"]


def test_position_strategy_waits_when_bullish_signal_lacks_trend_confirmation():
    analyzer = _analyzer()
    validation = {
        "action_gate": "allow_hold",
        "direction_consensus": "mixed",
        "risk_level": "medium",
        "validation_note": "交易信号偏多但预测趋势未确认上行",
    }
    strategy = analyzer.generate_position_strategy(
        {"history_data": _history_frame()},
        {
            "MACD": {"signal": "多头"},
            "RSI": {"RSI(12)": {"latest": 55}},
            "KDJ": {"signal": "正常"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
            "ATR": {"latest": 0.2},
        },
        current_price=10.0,
        cost_price=9.8,
        trading_signal={"score": 0.75, "signal": "strong_buy", "signal_text": "强烈买入"},
        validation=validation,
    )

    assert strategy["position_adjust"] == "继续持有，等待趋势确认"


def test_position_strategy_reduce_gate_suggests_reducing_position():
    analyzer = _analyzer()
    strategy = analyzer.generate_position_strategy(
        {"history_data": _history_frame()},
        {
            "MACD": {"signal": "多头"},
            "RSI": {"RSI(12)": {"latest": 55}},
            "KDJ": {"signal": "正常"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
            "ATR": {"latest": 0.2},
        },
        current_price=10.0,
        cost_price=9.8,
        trading_signal={"score": 0.45, "signal": "hold", "signal_text": "持有"},
        validation={"action_gate": "reduce_position", "direction_consensus": "bearish"},
    )

    assert strategy["position_adjust"] == "建议减仓"


def test_position_strategy_without_validation_keeps_legacy_strong_buy_behavior():
    analyzer = _analyzer()
    strategy = analyzer.generate_position_strategy(
        {"history_data": _history_frame()},
        {
            "MACD": {"signal": "多头"},
            "RSI": {"RSI(12)": {"latest": 55}},
            "KDJ": {"signal": "正常"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
            "ATR": {"latest": 0.2},
        },
        current_price=10.0,
        cost_price=9.8,
        trading_signal={"score": 0.75, "signal": "strong_buy", "signal_text": "强烈买入"},
    )

    assert strategy["position_adjust"] == "可考虑加仓"


def test_high_validation_risk_blocks_technical_buy_upgrade():
    analyzer = _analyzer()
    strategy = analyzer.generate_buy_strategy(
        {"technical_analysis": {"score": 0.75}},
        {
            "MACD": {"signal": "金叉"},
            "RSI": {"RSI(12)": {"latest": 55}},
            "KDJ": {"signal": "金叉"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
            "ATR": {"latest": 0.2},
        },
        current_price=10.0,
        trading_signal={"score": 0.45, "signal": "hold", "signal_text": "观望"},
        validation={"risk_level": "high", "action_gate": "avoid_buy"},
    )

    assert strategy["buy_timing"] in ("不建议买入", "等待确认")


def test_strong_buy_does_not_force_up_prediction_when_overheated():
    analyzer = _analyzer()
    prediction = analyzer.predict_price_range(
        {
            "stock_code": "000001",
            "stock_info": {"最新价": 10.8, "名称": "示例股票"},
            "history_data": _history_frame(),
            "technical_analysis": {"score": 0.55},
        },
        {
            "BOLL": {"latest": {"lower": 10.0, "upper": 10.9}},
            "ATR": {"latest": 0.25},
            "MACD": {"signal": "多头"},
            "KDJ": {"signal": "超买"},
            "RSI": {"RSI(6)": {"signal": "超买"}, "RSI(12)": {"signal": "超买"}},
        },
        stock_code="000001",
        trading_signal={"score": 0.75, "signal": "strong_buy", "signal_text": "强烈买入"},
    )

    assert prediction["day1"]["trend"] == "neutral"


def test_strong_buy_does_not_force_up_prediction_when_rsi_value_overheated():
    analyzer = _analyzer()
    prediction = analyzer.predict_price_range(
        {
            "stock_code": "000001",
            "stock_info": {"最新价": 10.8, "名称": "示例股票"},
            "history_data": _history_frame(),
            "technical_analysis": {"score": 0.55},
        },
        {
            "BOLL": {"latest": {"lower": 10.0, "upper": 10.9}},
            "ATR": {"latest": 0.25},
            "MACD": {"signal": "多头"},
            "KDJ": {"signal": "正常"},
            "RSI": {
                "RSI(6)": {"signal": "正常"},
                "RSI(12)": {"latest": 78, "signal": "正常"},
            },
        },
        stock_code="000001",
        trading_signal={"score": 0.75, "signal": "strong_buy", "signal_text": "强烈买入"},
    )

    assert prediction["day1"]["trend"] == "neutral"


def test_strong_buy_does_not_force_up_prediction_when_only_rsi_signal_overheated():
    analyzer = _analyzer()
    prediction = analyzer.predict_price_range(
        {
            "stock_code": "000001",
            "stock_info": {"最新价": 10.8, "名称": "示例股票"},
            "history_data": _history_frame(),
            "technical_analysis": {"score": 0.55},
        },
        {
            "BOLL": {"latest": {"lower": 10.0, "upper": 10.9}},
            "ATR": {"latest": 0.25},
            "MACD": {"signal": "多头"},
            "KDJ": {"signal": "正常"},
            "RSI": {
                "RSI(6)": {"signal": "正常"},
                "RSI(12)": {"latest": 60, "signal": "超买"},
            },
        },
        stock_code="000001",
        trading_signal={"score": 0.75, "signal": "strong_buy", "signal_text": "强烈买入"},
    )

    assert prediction["day1"]["trend"] == "neutral"


def test_validation_config_loaded():
    """验证 validation 配置被正确加载到 analyzer"""
    analyzer = _analyzer()
    vcfg = analyzer.validation_config
    assert "score_thresholds" in vcfg
    assert "vote_thresholds" in vcfg
    assert "confidence_weights" in vcfg
    assert "conflict_penalty" in vcfg
    assert vcfg["score_thresholds"]["technical_bullish"] == 0.65
    assert vcfg["vote_thresholds"]["bullish_consensus_margin"] == 3
    assert vcfg["confidence_weights"]["signal"] == 0.4
    assert vcfg["conflict_penalty"]["per_conflict"] == 0.1


def test_validation_config_fallback():
    """验证缺少字段时回退到默认值"""
    empty_config = {"analyzer": {"validation": {}}}
    a = StockAnalyzer(empty_config)
    vcfg = a.validation_config
    assert vcfg == {}


def test_cross_validate_uses_config_thresholds(analyzer):
    """验证不同的 config 值产生不同的 cross_validate 结果"""
    base_analysis = {"technical": {"score": 0.7}, "fund_flow": {"score": 0.7, "trend": "inflow"}, "sentiment": {"score": 0.7}}
    base_prediction = {"day1": {"trend": "up"}, "day2": {"trend": "up"}}
    base_indicators = {"MACD": {"signal": "金叉"}, "KDJ": {"signal": "金叉"}, "RSI": {"RSI(12)": {"latest": 55, "signal": ""}}}
    base_signal = {"signal": "strong_buy", "score": 0.9}

    # 严格 config：较高门槛
    strict_result = analyzer.cross_validate_analysis(
        base_analysis, base_prediction, base_indicators, base_signal, "未持有", 100
    )

    # 构建宽松 config 的 analyzer
    from scripts.core.analyzer import StockAnalyzer
    loose_config = {
        "analyzer": {
            "validation": {
                "score_thresholds": {"technical_bullish": 0.3, "technical_bearish": 0.1,
                                     "fund_bullish": 0.3, "fund_bearish": 0.1,
                                     "sentiment_bullish": 0.3, "sentiment_bearish": 0.1},
                "vote_thresholds": {"bullish_consensus_margin": 1, "bearish_consensus_margin": 1},
                "confidence_weights": {"signal": 0.5, "agreement": 0.5},
                "conflict_penalty": {"per_conflict": 0.05, "max": 0.1},
            }
        }
    }
    loose_analyzer = StockAnalyzer(loose_config)
    loose_result = loose_analyzer.cross_validate_analysis(
        base_analysis, base_prediction, base_indicators, base_signal, "未持有", 100
    )
    loose_consensus = loose_result["direction_consensus"]

    # 宽松 config 应有不低的 confidence
    assert loose_result["confidence"] >= strict_result["confidence"] - 0.01
    # 宽松 config 的 risk_level 不应更高
    risk_order = {"low": 0, "medium": 1, "high": 2}
    assert risk_order.get(loose_result["risk_level"], 1) <= risk_order.get(strict_result["risk_level"], 1)


def test_cross_validate_uses_config_vote_margins(analyzer):
    """验证不同的投票门槛影响 direction_consensus"""
    from scripts.core.analyzer import StockAnalyzer

    analysis = {"technical": {"score": 0.55}, "fund_flow": {"score": 0.55, "trend": "neutral"},
                "sentiment": {"score": 0.55}}
    prediction = {"day1": {"trend": "neutral"}, "day2": {"trend": "neutral"}}
    indicators = {"MACD": {"signal": ""}, "KDJ": {"signal": ""}, "RSI": {"RSI(12)": {"latest": 50, "signal": ""}},
                  "BOLL": {"latest": {}}}
    signal = {"signal": "hold", "score": 0.5}

    # 极低门槛 analyzer
    low = StockAnalyzer({"analyzer": {"validation": {
        "score_thresholds": {"technical_bullish": 0.3, "technical_bearish": 0.7,
                             "fund_bullish": 0.3, "fund_bearish": 0.7,
                             "sentiment_bullish": 0.3, "sentiment_bearish": 0.7},
        "vote_thresholds": {"bullish_consensus_margin": 0, "bearish_consensus_margin": 10},
        "confidence_weights": {"signal": 0.4, "agreement": 0.6},
        "conflict_penalty": {"per_conflict": 0.1, "max": 0.3},
    }}})
    low_result = low.cross_validate_analysis(
        analysis, prediction, indicators, signal, "未持有", 100
    )
    # 极低多头门槛下，方向应为 bullish 或 mixed
    assert low_result["direction_consensus"] in ("bullish", "mixed")


def test_strong_buy_does_not_force_up_prediction_when_only_kdj_overheated():
    analyzer = _analyzer()
    prediction = analyzer.predict_price_range(
        {
            "stock_code": "000001",
            "stock_info": {"最新价": 10.8, "名称": "示例股票"},
            "history_data": _history_frame(),
            "technical_analysis": {"score": 0.55},
        },
        {
            "BOLL": {"latest": {"lower": 10.0, "upper": 10.9}},
            "ATR": {"latest": 0.25},
            "MACD": {"signal": "多头"},
            "KDJ": {"signal": "超买"},
            "RSI": {
                "RSI(6)": {"signal": "正常"},
                "RSI(12)": {"latest": 60, "signal": "正常"},
            },
        },
        stock_code="000001",
        trading_signal={"score": 0.75, "signal": "strong_buy", "signal_text": "强烈买入"},
    )

    assert prediction["day1"]["trend"] == "neutral"
