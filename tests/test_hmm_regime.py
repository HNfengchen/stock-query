import pytest
import numpy as np
import os
import tempfile

from scripts.core.regime_detector import (
    HMMRegimeDetector,
    DynamicWeightManager,
    RegimeDetector,
    HMMLEARN_AVAILABLE,
    JOBLIB_AVAILABLE,
)


def _generate_synthetic_data(n_samples: int = 500, seed: int = 42):
    rng = np.random.RandomState(seed)

    returns = np.concatenate([
        rng.normal(0.002, 0.005, n_samples // 4),
        rng.normal(-0.002, 0.005, n_samples // 4),
        rng.normal(0.0, 0.03, n_samples // 4),
        rng.normal(0.0, 0.003, n_samples // 4),
    ])

    volatilities = np.concatenate([
        np.full(n_samples // 4, 0.005) + rng.normal(0, 0.001, n_samples // 4),
        np.full(n_samples // 4, 0.005) + rng.normal(0, 0.001, n_samples // 4),
        np.full(n_samples // 4, 0.03) + rng.normal(0, 0.005, n_samples // 4),
        np.full(n_samples // 4, 0.003) + rng.normal(0, 0.001, n_samples // 4),
    ])

    volume_changes = rng.normal(0, 0.1, n_samples)

    return returns, volatilities, volume_changes


@pytest.mark.skipif(not HMMLEARN_AVAILABLE, reason="hmmlearn未安装")
class TestHMMRegimeDetector:

    def setup_method(self):
        self.detector = HMMRegimeDetector(n_components=4)

    def test_initial_not_ready(self):
        assert not self.detector.is_ready()

    def test_train_success(self):
        returns, vols, volume_changes = _generate_synthetic_data()
        result = self.detector.train(returns, vols, volume_changes)
        assert "converged" in result
        assert "n_iter" in result
        assert "state_mapping" in result
        assert self.detector.is_ready()

    def test_state_mapping_has_all_labels(self):
        returns, vols, volume_changes = _generate_synthetic_data()
        result = self.detector.train(returns, vols, volume_changes)
        mapping = result["state_mapping"]
        assert len(mapping) == 4
        labels = set(mapping.values())
        assert "趋势上涨" in labels
        assert "趋势下跌" in labels
        assert "高波动" in labels
        assert "低波动震荡" in labels

    def test_state_mapping_highest_return_is_trend_up(self):
        returns, vols, volume_changes = _generate_synthetic_data()
        self.detector.train(returns, vols, volume_changes)
        mapping = self.detector._state_mapping
        model_means = self.detector._model.means_
        idx_highest_return = int(np.argmax(model_means[:, 0]))
        assert mapping[idx_highest_return] == "趋势上涨"

    def test_state_mapping_lowest_return_is_trend_down(self):
        returns, vols, volume_changes = _generate_synthetic_data()
        self.detector.train(returns, vols, volume_changes)
        mapping = self.detector._state_mapping
        model_means = self.detector._model.means_
        idx_lowest_return = int(np.argmin(model_means[:, 0]))
        assert mapping[idx_lowest_return] == "趋势下跌"

    def test_predict_after_train(self):
        returns, vols, volume_changes = _generate_synthetic_data()
        self.detector.train(returns, vols, volume_changes)
        result = self.detector.predict(returns[-50:], vols[-50:], volume_changes[-50:])
        assert "current_state" in result
        assert "state_probabilities" in result
        assert "transition_matrix" in result
        assert result["current_state"] != "未知"
        assert len(result["state_probabilities"]) == 4

    def test_predict_state_probabilities_sum_near_one(self):
        returns, vols, volume_changes = _generate_synthetic_data()
        self.detector.train(returns, vols, volume_changes)
        result = self.detector.predict(returns[-50:], vols[-50:], volume_changes[-50:])
        total_prob = sum(result["state_probabilities"].values())
        assert abs(total_prob - 1.0) < 0.01

    def test_predict_not_ready_returns_unknown(self):
        result = self.detector.predict(
            np.array([0.01]), np.array([0.02]), np.array([0.03])
        )
        assert result["current_state"] == "未知"
        assert result["state_probabilities"] == {}
        assert result["transition_matrix"] is None

    def test_get_transition_probabilities(self):
        returns, vols, volume_changes = _generate_synthetic_data()
        self.detector.train(returns, vols, volume_changes)
        transmat = self.detector.get_transition_probabilities()
        assert transmat is not None
        assert transmat.shape == (4, 4)
        for row in transmat:
            assert abs(sum(row) - 1.0) < 1e-6

    def test_get_transition_probabilities_not_ready(self):
        assert self.detector.get_transition_probabilities() is None

    @pytest.mark.skipif(not JOBLIB_AVAILABLE, reason="joblib未安装")
    def test_save_and_load_roundtrip(self):
        returns, vols, volume_changes = _generate_synthetic_data()
        self.detector.train(returns, vols, volume_changes)
        original_mapping = dict(self.detector._state_mapping)

        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, "test_hmm.pkl")
            saved = self.detector.save(model_path)
            assert saved
            assert os.path.exists(model_path)

            new_detector = HMMRegimeDetector(n_components=4)
            loaded = new_detector.load(model_path)
            assert loaded
            assert new_detector.is_ready()
            assert new_detector._state_mapping == original_mapping

            result = new_detector.predict(returns[-50:], vols[-50:], volume_changes[-50:])
            assert result["current_state"] != "未知"

    def test_save_not_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, "test_hmm.pkl")
            assert not self.detector.save(model_path)

    def test_train_insufficient_data(self):
        returns = np.array([0.01, 0.02])
        vols = np.array([0.01, 0.02])
        volume_changes = np.array([0.01, 0.02])
        result = self.detector.train(returns, vols, volume_changes)
        assert not result.get("converged", True)
        assert "error" in result

    def test_five_components(self):
        detector = HMMRegimeDetector(n_components=5)
        returns, vols, volume_changes = _generate_synthetic_data(n_samples=600)
        result = detector.train(returns, vols, volume_changes)
        mapping = result["state_mapping"]
        assert len(mapping) == 5
        labels = set(mapping.values())
        assert "恐慌" in labels


class TestHMMRegimeDetectorWithoutHmmlearn:

    def test_not_ready_when_no_model(self):
        detector = HMMRegimeDetector(n_components=4)
        assert not detector.is_ready()

    def test_predict_returns_unknown_when_not_ready(self):
        detector = HMMRegimeDetector(n_components=4)
        result = detector.predict(np.array([0.01]), np.array([0.02]), np.array([0.03]))
        assert result["current_state"] == "未知"


class TestDynamicWeightManagerHMMIntegration:

    def test_set_hmm_detector(self):
        config = {"dynamic_weights": {"enabled": True, "smoothing_alpha": 0.3, "regimes": {}}}
        manager = DynamicWeightManager(config)
        detector = HMMRegimeDetector(n_components=4)
        manager.set_hmm_detector(detector)
        assert manager.hmm_detector is detector

    def test_fallback_to_rule_based_when_hmm_not_ready(self):
        config = {"dynamic_weights": {"enabled": True, "smoothing_alpha": 0.3, "regimes": {}}}
        manager = DynamicWeightManager(config)
        detector = HMMRegimeDetector(n_components=4)
        manager.set_hmm_detector(detector)

        market_data = {
            "volatility_signal": "高波动",
            "volume_ratio": 1.2,
            "market_change_pct": 5.0,
            "volatility_value": 0.04,
        }
        weights = manager.detect_and_update(market_data)
        assert isinstance(weights, dict)
        assert "technical" in weights
        assert manager.get_regime() == "趋势牛市"

    def test_rule_based_detection_without_hmm(self):
        config = {"dynamic_weights": {"enabled": True, "smoothing_alpha": 0.3, "regimes": {}}}
        manager = DynamicWeightManager(config)
        assert manager.hmm_detector is None

        market_data = {
            "volatility_signal": "高波动",
            "volume_ratio": 1.2,
            "market_change_pct": 5.0,
            "volatility_value": 0.04,
        }
        weights = manager.detect_and_update(market_data)
        assert manager.get_regime() == "趋势牛市"

    @pytest.mark.skipif(not HMMLEARN_AVAILABLE, reason="hmmlearn未安装")
    def test_hmm_detection_used_when_ready(self):
        config = {"dynamic_weights": {"enabled": True, "smoothing_alpha": 0.3, "regimes": {}}}
        manager = DynamicWeightManager(config)

        returns, vols, volume_changes = _generate_synthetic_data()
        detector = HMMRegimeDetector(n_components=4)
        detector.train(returns, vols, volume_changes)
        manager.set_hmm_detector(detector)

        market_data = {
            "returns": returns[-50:],
            "volatilities": vols[-50:],
            "volume_changes": volume_changes[-50:],
            "volatility_signal": "高波动",
            "volume_ratio": 1.2,
            "market_change_pct": 5.0,
        }
        weights = manager.detect_and_update(market_data)
        assert isinstance(weights, dict)
        assert abs(sum(weights.values()) - 1.0) < 1e-6


class TestAnalyzerHMMIntegration:

    def test_hmm_disabled_by_default(self):
        from scripts.core.analyzer import StockAnalyzer

        config = {
            "analyzer": {
                "weights": {"technical": 0.5, "fund_flow": 0.3, "sentiment": 0.2},
                "thresholds": {"strong_buy": 0.7, "buy": 0.5, "hold": 0.3},
            },
        }
        analyzer = StockAnalyzer(config)
        assert analyzer._hmm_detector is None

    def test_hmm_enabled_but_no_model(self):
        from scripts.core.analyzer import StockAnalyzer

        config = {
            "analyzer": {
                "weights": {"technical": 0.5, "fund_flow": 0.3, "sentiment": 0.2},
                "thresholds": {"strong_buy": 0.7, "buy": 0.5, "hold": 0.3},
            },
            "hmm": {
                "enabled": True,
                "n_components": 4,
                "model_path": "",
            },
        }
        analyzer = StockAnalyzer(config)
        assert analyzer._hmm_detector is not None
        assert not analyzer._hmm_detector.is_ready()

    @pytest.mark.skipif(not HMMLEARN_AVAILABLE, reason="hmmlearn未安装")
    def test_hmm_state_in_recommendation(self):
        from scripts.core.analyzer import StockAnalyzer
        import pandas as pd

        returns, vols, volume_changes = _generate_synthetic_data()
        detector = HMMRegimeDetector(n_components=4)
        detector.train(returns, vols, volume_changes)

        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, "test_hmm.pkl")
            detector.save(model_path)

            config = {
                "analyzer": {
                    "weights": {"technical": 0.5, "fund_flow": 0.3, "sentiment": 0.2},
                    "thresholds": {"strong_buy": 0.7, "buy": 0.5, "hold": 0.3},
                },
                "hmm": {
                    "enabled": True,
                    "n_components": 4,
                    "model_path": model_path,
                },
            }
            analyzer = StockAnalyzer(config)

            n = 60
            closes = np.cumprod(1 + returns[:n]) * 100
            volumes = np.abs(volume_changes[:n]) * 1e6 + 1e6
            history_df = pd.DataFrame({
                "收盘": closes,
                "成交量": volumes,
            })

            all_data = {
                "stock_info": {"最新价": float(closes[-1])},
                "fund_flow": {},
                "history_data": history_df,
                "market_data": {},
                "indicators": {"error": "skip"},
            }

            result = analyzer.generate_recommendation(all_data)
            if "hmm_state" in result:
                assert "current_state" in result["hmm_state"]
                assert "state_probabilities" in result["hmm_state"]
