import pandas as pd
import pytest

from backend.services import analysis_service


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


@pytest.fixture(autouse=True)
def clear_analysis_cache():
    analysis_service._result_cache.clear()
    yield
    analysis_service._result_cache.clear()


def test_analysis_service_serializes_validation_fields(monkeypatch):
    class FakeFetcher:
        def resolve_stock_code(self, stock_input):
            return "000001", "示例股票", "sz"

        def fetch_stock_info(self, stock_code):
            return {"最新价": 10.0, "名称": "示例股票"}

        def fetch_fund_flow(self, stock_code):
            return {}

        def fetch_history_data(self, stock_code, days=120):
            return _history_frame()

    class FakeAnalyzer:
        def generate_recommendation(self, all_data, position_status, cost_price):
            return {
                "analysis": {
                    "technical": {"score": 0.7},
                    "fund_flow": {"score": 0.6},
                    "sentiment": {"score": 0.5},
                },
                "trading_signal": {
                    "score": 0.72,
                    "signal": "strong_buy",
                    "signal_text": "强烈买入",
                    "reason": "多项证据偏多",
                },
                "price_prediction": {
                    "current": 10.0,
                    "support": 9.5,
                    "resistance": 10.8,
                    "validation_confidence": 0.8,
                    "validation_note": "多项证据偏多",
                    "day1": {
                        "target_low": 10.1,
                        "target_high": 10.5,
                        "trend": "up",
                        "signal": "看涨延续",
                    },
                    "day2": {
                        "target_low": 10.2,
                        "target_high": 10.7,
                        "trend": "up",
                        "signal": "持续上涨",
                    },
                },
                "indicators": {},
                "position_strategy": {
                    "buy_timing": "建议买入",
                    "validation_note": "多项证据偏多",
                },
                "validation": {
                    "direction_consensus": "bullish",
                    "confidence": 0.8,
                    "risk_level": "low",
                    "action_gate": "allow_buy",
                    "supporting_factors": ["技术评分偏强"],
                    "opposing_factors": [],
                    "conflicts": [],
                    "validation_note": "多项证据偏多",
                },
            }

    monkeypatch.setattr(analysis_service, "get_fetcher", lambda: FakeFetcher())
    monkeypatch.setattr(analysis_service, "get_analyzer", lambda: FakeAnalyzer())
    monkeypatch.setattr(
        "backend.services.history_service.update_signal_cache",
        lambda *args, **kwargs: None,
    )

    result = analysis_service.run_analysis("000001", "未持有")

    assert result["trading_signal"]["reason"] == "多项证据偏多"
    assert result["price_prediction"]["validation_confidence"] == 0.8
    assert result["price_prediction"]["validation_note"] == "多项证据偏多"
    assert result["validation"]["direction_consensus"] == "bullish"
    assert result["validation"]["supporting_factors"] == ["技术评分偏强"]
