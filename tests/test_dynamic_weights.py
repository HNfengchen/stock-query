import pytest
from scripts.core.regime_detector import RegimeDetector, DynamicWeightManager, DEFAULT_WEIGHTS


class TestRegimeDetector:

    def setup_method(self):
        self.detector = RegimeDetector()

    def test_panic_regime(self):
        market_data = {
            "volatility_signal": "高波动",
            "volume_ratio": 1.5,
            "market_change_pct": -5.0,
            "volatility_value": 0.04,
        }
        assert self.detector.detect_regime(market_data) == "恐慌"

    def test_trend_bull_regime(self):
        market_data = {
            "volatility_signal": "高波动",
            "volume_ratio": 1.2,
            "market_change_pct": 5.0,
            "volatility_value": 0.04,
        }
        assert self.detector.detect_regime(market_data) == "趋势牛市"

    def test_low_volume_consolidation(self):
        market_data = {
            "volatility_signal": "正常",
            "volume_ratio": 0.5,
            "market_change_pct": 0.2,
            "volatility_value": 0.01,
        }
        assert self.detector.detect_regime(market_data) == "缩量震荡"

    def test_institutional_regime(self):
        market_data = {
            "volatility_signal": "正常",
            "volume_ratio": 2.5,
            "market_change_pct": 0.5,
            "volatility_value": 0.02,
        }
        assert self.detector.detect_regime(market_data) == "机构行情"

    def test_default_consolidation(self):
        market_data = {
            "volatility_signal": "正常",
            "volume_ratio": 1.0,
            "market_change_pct": 0.5,
            "volatility_value": 0.01,
        }
        assert self.detector.detect_regime(market_data) == "缩量震荡"

    def test_low_volatility_consolidation(self):
        market_data = {
            "volatility_signal": "低波动",
            "volume_ratio": 0.6,
            "market_change_pct": 0.1,
            "volatility_value": 0.005,
        }
        assert self.detector.detect_regime(market_data) == "缩量震荡"

    def test_high_volatility_but_not_extreme_change(self):
        market_data = {
            "volatility_signal": "高波动",
            "volume_ratio": 1.0,
            "market_change_pct": -1.0,
            "volatility_value": 0.04,
        }
        assert self.detector.detect_regime(market_data) == "缩量震荡"

    def test_missing_fields_default(self):
        market_data = {}
        assert self.detector.detect_regime(market_data) == "缩量震荡"

    def test_institutional_beats_consolidation(self):
        market_data = {
            "volatility_signal": "高波动",
            "volume_ratio": 2.5,
            "market_change_pct": 0.5,
            "volatility_value": 0.04,
        }
        assert self.detector.detect_regime(market_data) == "机构行情"

    def test_string_volume_ratio(self):
        market_data = {
            "volatility_signal": "正常",
            "volume_ratio": "0.5",
            "market_change_pct": 0.2,
            "volatility_value": 0.01,
        }
        assert self.detector.detect_regime(market_data) == "缩量震荡"


class TestDynamicWeightManager:

    def setup_method(self):
        self.config = {
            "dynamic_weights": {
                "enabled": True,
                "smoothing_alpha": 0.3,
                "regimes": {
                    "趋势牛市": {"technical": 0.6, "fund_flow": 0.2, "sentiment": 0.2},
                    "极端恐慌": {"technical": 0.2, "fund_flow": 0.2, "sentiment": 0.6},
                    "机构行情": {"technical": 0.3, "fund_flow": 0.5, "sentiment": 0.2},
                    "缩量震荡": {"technical": 0.4, "fund_flow": 0.3, "sentiment": 0.3},
                },
            }
        }
        self.manager = DynamicWeightManager(self.config)

    def test_default_weights(self):
        weights = self.manager.get_current_weights()
        assert abs(weights["technical"] - 0.5) < 1e-6
        assert abs(weights["fund_flow"] - 0.3) < 1e-6
        assert abs(weights["sentiment"] - 0.2) < 1e-6

    def test_weights_sum_to_one(self):
        weights = self.manager.get_current_weights()
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_update_weights_ema_smoothing(self):
        self.manager.update_weights("趋势牛市")
        weights = self.manager.get_current_weights()
        assert weights["technical"] < 0.6
        assert weights["technical"] > 0.5

    def test_ema_converges_to_target(self):
        for _ in range(50):
            self.manager.update_weights("趋势牛市")
        weights = self.manager.get_current_weights()
        assert abs(weights["technical"] - 0.6) < 0.01
        assert abs(weights["fund_flow"] - 0.2) < 0.01
        assert abs(weights["sentiment"] - 0.2) < 0.01

    def test_weights_always_sum_to_one_after_update(self):
        for regime in ["趋势牛市", "极端恐慌", "机构行情", "缩量震荡"]:
            self.manager.update_weights(regime)
            weights = self.manager.get_current_weights()
            assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_regime_alias_panic(self):
        self.manager.update_weights("恐慌")
        assert self.manager.get_regime() == "极端恐慌"
        for _ in range(30):
            self.manager.update_weights("恐慌")
        weights = self.manager.get_current_weights()
        assert weights["sentiment"] > weights["technical"]

    def test_get_regime_initial(self):
        assert self.manager.get_regime() == "缩量震荡"

    def test_get_regime_after_update(self):
        self.manager.update_weights("趋势牛市")
        assert self.manager.get_regime() == "趋势牛市"

    def test_detect_and_update(self):
        market_data = {
            "volatility_signal": "高波动",
            "volume_ratio": 1.2,
            "market_change_pct": 5.0,
            "volatility_value": 0.04,
        }
        weights = self.manager.detect_and_update(market_data)
        assert isinstance(weights, dict)
        assert "technical" in weights
        assert "fund_flow" in weights
        assert "sentiment" in weights
        assert self.manager.get_regime() == "趋势牛市"

    def test_detect_and_update_panic(self):
        market_data = {
            "volatility_signal": "高波动",
            "volume_ratio": 1.5,
            "market_change_pct": -5.0,
            "volatility_value": 0.04,
        }
        weights = self.manager.detect_and_update(market_data)
        assert self.manager.get_regime() == "极端恐慌"

    def test_smooth_transition_no_jump(self):
        initial = self.manager.get_current_weights()
        self.manager.update_weights("极端恐慌")
        after = self.manager.get_current_weights()
        for key in initial:
            assert abs(after[key] - initial[key]) < 0.5

    def test_disabled_falls_back_to_fixed(self):
        config = {
            "dynamic_weights": {
                "enabled": False,
                "smoothing_alpha": 0.3,
                "regimes": {},
            }
        }
        manager = DynamicWeightManager(config)
        assert not manager.enabled

    def test_no_config_uses_defaults(self):
        manager = DynamicWeightManager()
        weights = manager.get_current_weights()
        assert abs(weights["technical"] - 0.5) < 1e-6
        assert abs(weights["fund_flow"] - 0.3) < 1e-6
        assert abs(weights["sentiment"] - 0.2) < 1e-6

    def test_unknown_regime_uses_default(self):
        self.manager.update_weights("未知状态")
        weights = self.manager.get_current_weights()
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_multiple_regime_switches(self):
        self.manager.update_weights("趋势牛市")
        self.manager.update_weights("极端恐慌")
        self.manager.update_weights("机构行情")
        weights = self.manager.get_current_weights()
        assert abs(sum(weights.values()) - 1.0) < 1e-6
        assert self.manager.get_regime() == "机构行情"


class TestAnalyzerDynamicWeights:

    def test_generate_trading_signal_with_dynamic_weights(self):
        from scripts.core.analyzer import StockAnalyzer

        config = {
            "analyzer": {
                "weights": {"technical": 0.5, "fund_flow": 0.3, "sentiment": 0.2},
                "thresholds": {"strong_buy": 0.7, "buy": 0.5, "hold": 0.3},
            },
            "dynamic_weights": {
                "enabled": True,
                "smoothing_alpha": 0.3,
                "regimes": {
                    "趋势牛市": {"technical": 0.6, "fund_flow": 0.2, "sentiment": 0.2},
                    "极端恐慌": {"technical": 0.2, "fund_flow": 0.2, "sentiment": 0.6},
                    "机构行情": {"technical": 0.3, "fund_flow": 0.5, "sentiment": 0.2},
                    "缩量震荡": {"technical": 0.4, "fund_flow": 0.3, "sentiment": 0.3},
                },
            },
        }
        analyzer = StockAnalyzer(config)

        analysis = {
            "technical": {"score": 0.7},
            "fund_flow": {"score": 0.5},
            "sentiment": {"score": 0.6},
        }

        market_data = {
            "volatility_signal": "高波动",
            "volume_ratio": 1.2,
            "market_change_pct": 5.0,
            "volatility_value": 0.04,
        }

        result = analyzer.generate_trading_signal(analysis, "未持有", market_data)
        assert "market_regime" in result
        assert result["market_regime"] == "趋势牛市"

    def test_generate_trading_signal_without_market_data(self):
        from scripts.core.analyzer import StockAnalyzer

        config = {
            "analyzer": {
                "weights": {"technical": 0.5, "fund_flow": 0.3, "sentiment": 0.2},
                "thresholds": {"strong_buy": 0.7, "buy": 0.5, "hold": 0.3},
            },
            "dynamic_weights": {
                "enabled": True,
                "smoothing_alpha": 0.3,
                "regimes": {},
            },
        }
        analyzer = StockAnalyzer(config)

        analysis = {
            "technical": {"score": 0.7},
            "fund_flow": {"score": 0.5},
            "sentiment": {"score": 0.6},
        }

        result = analyzer.generate_trading_signal(analysis, "未持有")
        assert "market_regime" not in result

    def test_generate_trading_signal_disabled_dynamic_weights(self):
        from scripts.core.analyzer import StockAnalyzer

        config = {
            "analyzer": {
                "weights": {"technical": 0.5, "fund_flow": 0.3, "sentiment": 0.2},
                "thresholds": {"strong_buy": 0.7, "buy": 0.5, "hold": 0.3},
            },
            "dynamic_weights": {
                "enabled": False,
                "smoothing_alpha": 0.3,
                "regimes": {},
            },
        }
        analyzer = StockAnalyzer(config)

        analysis = {
            "technical": {"score": 0.7},
            "fund_flow": {"score": 0.5},
            "sentiment": {"score": 0.6},
        }

        market_data = {
            "volatility_signal": "高波动",
            "volume_ratio": 1.2,
            "market_change_pct": 5.0,
            "volatility_value": 0.04,
        }

        result = analyzer.generate_trading_signal(analysis, "未持有", market_data)
        assert "market_regime" not in result
