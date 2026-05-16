import numpy as np
import pandas as pd
import pytest

from scripts.technical_indicators import (
    calculate_relative_strength,
    calculate_beta,
    calculate_industry_strength,
    calculate_sector_fund_flow,
    calculate_market_structure,
    calculate_all_indicators,
)
from scripts.core.analyzer import StockAnalyzer


def _make_df(closes, highs=None, lows=None, volumes=None):
    length = len(closes)
    return pd.DataFrame(
        {
            "收盘": closes,
            "最高": highs if highs is not None else [c + 0.2 for c in closes],
            "最低": lows if lows is not None else [c - 0.2 for c in closes],
            "成交量": volumes if volumes is not None else [1000] * length,
        }
    )


def _make_returns_df(n=120, seed=42, drift=0.001):
    rng = np.random.RandomState(seed)
    base = 100.0
    closes = [base]
    for _ in range(n - 1):
        ret = rng.normal(drift, 0.02)
        closes.append(closes[-1] * (1 + ret))
    return _make_df(closes)


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
                    "confidence_weights": {"signal": 0.4, "agreement": 0.6},
                    "conflict_penalty": {"per_conflict": 0.1, "max": 0.3},
                },
            }
        }
    )


class TestRelativeStrength:
    def test_basic_calculation(self):
        rng = np.random.RandomState(42)
        stock_ret = pd.Series(rng.normal(0.002, 0.02, 30))
        index_ret = pd.Series(rng.normal(0.001, 0.02, 30))
        result = calculate_relative_strength(stock_ret, index_ret, window=20)
        rs = result["RelativeStrength"]
        assert rs["latest"] is not None
        assert isinstance(rs["latest"], float)
        assert rs["signal"] in ("强势", "偏强", "偏弱", "弱势")
        assert isinstance(rs["series"], list)

    def test_strong_stock(self):
        stock_ret = pd.Series([0.02] * 20)
        index_ret = pd.Series([0.005] * 20)
        result = calculate_relative_strength(stock_ret, index_ret, window=20)
        rs = result["RelativeStrength"]
        assert rs["latest"] > 1.2
        assert rs["signal"] == "强势"

    def test_weak_stock(self):
        stock_ret = pd.Series([-0.01] * 20)
        index_ret = pd.Series([0.005] * 20)
        result = calculate_relative_strength(stock_ret, index_ret, window=20)
        rs = result["RelativeStrength"]
        assert rs["latest"] <= 0.8
        assert rs["signal"] == "弱势"

    def test_none_index(self):
        stock_ret = pd.Series([0.01] * 20)
        result = calculate_relative_strength(stock_ret, None, window=20)
        rs = result["RelativeStrength"]
        assert rs["latest"] == 1.0
        assert rs["signal"] == "数据不可用"

    def test_empty_index(self):
        stock_ret = pd.Series([0.01] * 20)
        result = calculate_relative_strength(stock_ret, pd.Series([], dtype=float), window=20)
        rs = result["RelativeStrength"]
        assert rs["latest"] == 1.0
        assert rs["signal"] == "数据不可用"

    def test_moderate_strength(self):
        stock_ret = pd.Series([0.008] * 20)
        index_ret = pd.Series([0.005] * 20)
        result = calculate_relative_strength(stock_ret, index_ret, window=20)
        rs = result["RelativeStrength"]
        assert rs["latest"] > 1.0
        assert rs["signal"] in ("偏强", "强势")


class TestBeta:
    def test_basic_calculation(self):
        rng = np.random.RandomState(42)
        stock_ret = pd.Series(rng.normal(0.001, 0.02, 100))
        index_ret = pd.Series(rng.normal(0.001, 0.015, 100))
        result = calculate_beta(stock_ret, index_ret, window=60)
        beta = result["Beta"]
        assert beta["latest"] is not None
        assert isinstance(beta["latest"], float)
        assert beta["signal"] in ("高Beta", "中高Beta", "中低Beta", "低Beta")
        assert isinstance(beta["series"], list)

    def test_high_beta(self):
        rng = np.random.RandomState(42)
        index_ret = pd.Series(rng.normal(0.001, 0.01, 100))
        stock_ret = index_ret * 2.0 + pd.Series(rng.normal(0, 0.005, 100))
        result = calculate_beta(stock_ret, index_ret, window=60)
        beta = result["Beta"]
        assert beta["latest"] > 1.5
        assert beta["signal"] == "高Beta"

    def test_low_beta(self):
        rng = np.random.RandomState(42)
        index_ret = pd.Series(rng.normal(0.001, 0.02, 100))
        stock_ret = pd.Series(rng.normal(0.0005, 0.005, 100))
        result = calculate_beta(stock_ret, index_ret, window=60)
        beta = result["Beta"]
        assert beta["latest"] <= 0.5
        assert beta["signal"] == "低Beta"

    def test_none_index(self):
        stock_ret = pd.Series([0.01] * 60)
        result = calculate_beta(stock_ret, None, window=60)
        beta = result["Beta"]
        assert beta["latest"] == 1.0
        assert beta["signal"] == "数据不可用"

    def test_insufficient_data(self):
        stock_ret = pd.Series([0.01])
        index_ret = pd.Series([0.01])
        result = calculate_beta(stock_ret, index_ret, window=60)
        beta = result["Beta"]
        assert beta["latest"] == 1.0
        assert beta["signal"] == "数据不可用"


class TestIndustryStrength:
    def test_basic_calculation(self):
        rng = np.random.RandomState(42)
        ind_ret = pd.Series(rng.normal(0.002, 0.02, 30))
        idx_ret = pd.Series(rng.normal(0.001, 0.02, 30))
        result = calculate_industry_strength(ind_ret, idx_ret, window=20)
        is_result = result["IndustryStrength"]
        assert is_result["latest"] is not None
        assert isinstance(is_result["latest"], float)
        assert is_result["signal"] in ("强势", "偏强", "偏弱", "弱势")
        assert isinstance(is_result["series"], list)

    def test_strong_industry(self):
        ind_ret = pd.Series([0.02] * 20)
        idx_ret = pd.Series([0.005] * 20)
        result = calculate_industry_strength(ind_ret, idx_ret, window=20)
        is_result = result["IndustryStrength"]
        assert is_result["latest"] > 0.05
        assert is_result["signal"] == "强势"

    def test_weak_industry(self):
        ind_ret = pd.Series([-0.01] * 20)
        idx_ret = pd.Series([0.005] * 20)
        result = calculate_industry_strength(ind_ret, idx_ret, window=20)
        is_result = result["IndustryStrength"]
        assert is_result["latest"] <= -0.05
        assert is_result["signal"] == "弱势"

    def test_none_industry(self):
        result = calculate_industry_strength(None, pd.Series([0.01] * 20), window=20)
        is_result = result["IndustryStrength"]
        assert is_result["latest"] == 0.0
        assert is_result["signal"] == "数据不可用"

    def test_no_index(self):
        ind_ret = pd.Series([0.01] * 20)
        result = calculate_industry_strength(ind_ret, None, window=20)
        is_result = result["IndustryStrength"]
        assert is_result["latest"] is not None
        assert is_result["signal"] in ("强势", "偏强", "偏弱", "弱势")


class TestSectorFundFlow:
    def test_none_data(self):
        result = calculate_sector_fund_flow(None)
        flow = result["SectorFundFlow"]
        assert flow["latest"] == 0.0
        assert flow["signal"] == "数据不可用"

    def test_large_inflow(self):
        result = calculate_sector_fund_flow({"net_inflow": 2e9})
        flow = result["SectorFundFlow"]
        assert flow["latest"] > 1e9
        assert flow["signal"] == "大幅流入"

    def test_inflow(self):
        result = calculate_sector_fund_flow({"net_inflow": 5e8})
        flow = result["SectorFundFlow"]
        assert 0 < flow["latest"] <= 1e9
        assert flow["signal"] == "流入"

    def test_outflow(self):
        result = calculate_sector_fund_flow({"net_inflow": -5e8})
        flow = result["SectorFundFlow"]
        assert -1e9 < flow["latest"] < 0
        assert flow["signal"] == "流出"

    def test_large_outflow(self):
        result = calculate_sector_fund_flow({"net_inflow": -2e9})
        flow = result["SectorFundFlow"]
        assert flow["latest"] <= -1e9
        assert flow["signal"] == "大幅流出"

    def test_chinese_key(self):
        result = calculate_sector_fund_flow({"主力净流入": 3e9})
        flow = result["SectorFundFlow"]
        assert flow["latest"] > 1e9
        assert flow["signal"] == "大幅流入"


class TestMarketStructure:
    def test_basic_calculation(self):
        df = _make_returns_df(120)
        result = calculate_market_structure(df)
        ms = result["MarketStructure"]
        assert "RelativeStrength" in ms
        assert "Beta" in ms
        assert "IndustryStrength" in ms
        assert "SectorFundFlow" in ms

    def test_with_index_data(self):
        df = _make_returns_df(120)
        index_df = _make_returns_df(120, seed=99, drift=0.0005)
        result = calculate_market_structure(df, index_df=index_df)
        ms = result["MarketStructure"]
        assert ms["RelativeStrength"]["signal"] != "数据不可用"
        assert ms["Beta"]["signal"] != "数据不可用"

    def test_with_industry_data(self):
        df = _make_returns_df(120)
        industry_df = _make_returns_df(120, seed=77, drift=0.002)
        result = calculate_market_structure(df, industry_df=industry_df)
        ms = result["MarketStructure"]
        assert ms["IndustryStrength"]["signal"] != "数据不可用"

    def test_with_sector_fund(self):
        df = _make_returns_df(120)
        result = calculate_market_structure(df, sector_fund_data={"net_inflow": 1.5e9})
        ms = result["MarketStructure"]
        assert ms["SectorFundFlow"]["signal"] == "大幅流入"

    def test_no_close_column(self):
        df = pd.DataFrame({"open": [10, 11, 12]})
        result = calculate_market_structure(df)
        assert result["MarketStructure"] == {}

    def test_custom_config(self):
        df = _make_returns_df(120)
        result = calculate_market_structure(df, config={"rs_window": 10, "beta_window": 30, "is_window": 10})
        ms = result["MarketStructure"]
        assert "RelativeStrength" in ms


class TestIntegrationWithCalculateAllIndicators:
    def test_market_structure_in_result(self):
        df = _make_returns_df(120)
        result = calculate_all_indicators(df)
        assert "MarketStructure" in result
        ms = result["MarketStructure"]
        assert "RelativeStrength" in ms
        assert "Beta" in ms
        assert "IndustryStrength" in ms
        assert "SectorFundFlow" in ms

    def test_with_index_and_industry(self):
        df = _make_returns_df(120)
        index_df = _make_returns_df(120, seed=99, drift=0.0005)
        industry_df = _make_returns_df(120, seed=77, drift=0.002)
        result = calculate_all_indicators(df, index_df=index_df, industry_df=industry_df)
        ms = result["MarketStructure"]
        assert ms["RelativeStrength"]["signal"] != "数据不可用"
        assert ms["Beta"]["signal"] != "数据不可用"
        assert ms["IndustryStrength"]["signal"] != "数据不可用"

    def test_other_indicators_still_work(self):
        df = _make_returns_df(120)
        result = calculate_all_indicators(df)
        assert "MACD" in result
        assert "RSI" in result
        assert "KDJ" in result
        assert "MA" in result
        assert "BOLL" in result
        assert "ATR" in result
        assert "MarketStructure" in result

    def test_backward_compatible_no_extra_args(self):
        df = _make_returns_df(120)
        result = calculate_all_indicators(df)
        assert "MarketStructure" in result
        ms = result["MarketStructure"]
        assert ms["RelativeStrength"]["signal"] == "数据不可用"
        assert ms["Beta"]["signal"] == "数据不可用"
        assert ms["IndustryStrength"]["signal"] == "数据不可用"
        assert ms["SectorFundFlow"]["signal"] == "数据不可用"


class TestAnalyzerCrossValidation:
    def test_rs_strong_boosts_confidence(self):
        analyzer = _analyzer()

        indicators_no_ms = {
            "MACD": {"signal": "多头"},
            "RSI": {"RSI(12)": {"latest": 55, "signal": "正常"}},
            "KDJ": {"signal": "金叉"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
        }

        indicators_with_rs = dict(indicators_no_ms)
        indicators_with_rs["MarketStructure"] = {
            "RelativeStrength": {"latest": 1.5, "series": [], "signal": "强势"},
            "Beta": {"latest": 1.0, "series": [], "signal": "中高Beta"},
            "IndustryStrength": {"latest": 0.02, "series": [], "signal": "偏强"},
            "SectorFundFlow": {"latest": 0.0, "signal": "数据不可用"},
        }

        analysis = {
            "technical": {"score": 0.72},
            "fund_flow": {"score": 0.75, "trend": "inflow"},
            "sentiment": {"score": 0.6},
        }
        price_prediction = {"day1": {"trend": "up"}, "day2": {"trend": "up"}}

        validation_normal = analyzer.cross_validate_analysis(
            analysis,
            price_prediction,
            indicators_no_ms,
            trading_signal={"signal": "strong_buy", "score": 0.76},
            position_status="未持有",
            current_price=10.0,
        )

        validation_rs = analyzer.cross_validate_analysis(
            analysis,
            price_prediction,
            indicators_with_rs,
            trading_signal={"signal": "strong_buy", "score": 0.76},
            position_status="未持有",
            current_price=10.0,
        )

        assert validation_rs["confidence"] > validation_normal["confidence"]
        assert "相对强度强势" in validation_rs["supporting_factors"]

    def test_high_beta_elevates_risk(self):
        analyzer = _analyzer()

        indicators_with_high_beta = {
            "MACD": {"signal": "多头"},
            "RSI": {"RSI(12)": {"latest": 55, "signal": "正常"}},
            "KDJ": {"signal": "金叉"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
            "MarketStructure": {
                "RelativeStrength": {"latest": 1.0, "series": [], "signal": "偏强"},
                "Beta": {"latest": 2.0, "series": [], "signal": "高Beta"},
                "IndustryStrength": {"latest": 0.0, "series": [], "signal": "偏弱"},
                "SectorFundFlow": {"latest": 0.0, "signal": "数据不可用"},
            },
        }

        analysis = {
            "technical": {"score": 0.72},
            "fund_flow": {"score": 0.75, "trend": "inflow"},
            "sentiment": {"score": 0.6},
        }
        price_prediction = {"day1": {"trend": "up"}, "day2": {"trend": "up"}}

        validation = analyzer.cross_validate_analysis(
            analysis,
            price_prediction,
            indicators_with_high_beta,
            trading_signal={"signal": "strong_buy", "score": 0.76},
            position_status="未持有",
            current_price=10.0,
        )

        assert "高Beta风险" in validation["opposing_factors"]
        risk_order = {"low": 0, "medium": 1, "high": 2}
        assert risk_order.get(validation["risk_level"], 0) >= 1


class TestAnalyzerBuyStrategy:
    def test_high_beta_narrows_stop_loss(self):
        analyzer = _analyzer()

        indicators_normal = {
            "MACD": {"signal": "金叉"},
            "RSI": {"RSI(12)": {"latest": 50}},
            "KDJ": {"signal": "正常"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
            "ATR": {"latest": 0.2},
        }

        indicators_high_beta = dict(indicators_normal)
        indicators_high_beta["MarketStructure"] = {
            "RelativeStrength": {"latest": 1.0, "series": [], "signal": "偏强"},
            "Beta": {"latest": 2.0, "series": [], "signal": "高Beta"},
            "IndustryStrength": {"latest": 0.0, "series": [], "signal": "偏弱"},
            "SectorFundFlow": {"latest": 0.0, "signal": "数据不可用"},
        }

        strategy_normal = analyzer.generate_buy_strategy(
            {"technical_analysis": {"score": 0.5}},
            indicators_normal,
            current_price=10.0,
            trading_signal={"signal": "buy", "score": 0.55},
        )

        strategy_high_beta = analyzer.generate_buy_strategy(
            {"technical_analysis": {"score": 0.5}},
            indicators_high_beta,
            current_price=10.0,
            trading_signal={"signal": "buy", "score": 0.55},
        )

        normal_distance = 10.0 - strategy_normal["stop_loss_price"]
        high_beta_distance = 10.0 - strategy_high_beta["stop_loss_price"]
        assert high_beta_distance < normal_distance

    def test_normal_beta_no_change(self):
        analyzer = _analyzer()

        indicators = {
            "MACD": {"signal": "金叉"},
            "RSI": {"RSI(12)": {"latest": 50}},
            "KDJ": {"signal": "正常"},
            "BOLL": {"latest": {"upper": 12.0, "lower": 9.0}},
            "ATR": {"latest": 0.2},
            "MarketStructure": {
                "RelativeStrength": {"latest": 1.0, "series": [], "signal": "偏强"},
                "Beta": {"latest": 1.0, "series": [], "signal": "中高Beta"},
                "IndustryStrength": {"latest": 0.0, "series": [], "signal": "偏弱"},
                "SectorFundFlow": {"latest": 0.0, "signal": "数据不可用"},
            },
        }

        strategy = analyzer.generate_buy_strategy(
            {"technical_analysis": {"score": 0.5}},
            indicators,
            current_price=10.0,
            trading_signal={"signal": "buy", "score": 0.55},
        )

        assert strategy["stop_loss_price"] is not None
