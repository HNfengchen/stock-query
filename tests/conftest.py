"""测试 fixtures"""

import pytest
from scripts.core.analyzer import StockAnalyzer


@pytest.fixture
def analyzer():
    """使用标准测试配置的 StockAnalyzer 实例"""
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
