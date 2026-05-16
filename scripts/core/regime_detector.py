"""
市场状态检测与动态权重管理模块
基于规则的市场状态识别，配合EMA平滑的权重过渡机制
支持HMM隐马尔可夫模型的市场状态识别
"""

from typing import Dict, Optional
import numpy as np
from scripts.logger import get_logger

try:
    from hmmlearn.hmm import GaussianHMM
    HMMLEARN_AVAILABLE = True
except ImportError:
    HMMLEARN_AVAILABLE = False

try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False

regime_logger = get_logger("RegimeDetector")

REGIME_ALIASES = {
    "恐慌": "极端恐慌",
}

DEFAULT_REGIMES = {
    "趋势牛市": {"technical": 0.6, "fund_flow": 0.2, "sentiment": 0.2},
    "极端恐慌": {"technical": 0.2, "fund_flow": 0.2, "sentiment": 0.6},
    "机构行情": {"technical": 0.3, "fund_flow": 0.5, "sentiment": 0.2},
    "缩量震荡": {"technical": 0.4, "fund_flow": 0.3, "sentiment": 0.3},
}

DEFAULT_WEIGHTS = {"technical": 0.5, "fund_flow": 0.3, "sentiment": 0.2}


HMM_STATE_LABELS_4 = {0: "趋势上涨", 1: "趋势下跌", 2: "高波动", 3: "低波动震荡"}
HMM_STATE_LABELS_5 = {0: "趋势上涨", 1: "趋势下跌", 2: "高波动", 3: "低波动震荡", 4: "恐慌"}


class HMMRegimeDetector:
    """基于HMM隐马尔可夫模型的市场状态识别器"""

    def __init__(self, n_components: int = 4, config: dict = None):
        self.n_components = n_components
        self.config = config or {}
        self._model = None
        self._state_mapping: Dict[int, str] = {}
        self._ready = False

    def train(self, returns: np.ndarray, volatilities: np.ndarray, volume_changes: np.ndarray) -> dict:
        if not HMMLEARN_AVAILABLE:
            regime_logger.warning("hmmlearn未安装，无法训练HMM模型")
            return {"converged": False, "n_iter": 0, "state_mapping": {}, "error": "hmmlearn未安装"}

        returns = np.asarray(returns, dtype=np.float64).ravel()
        volatilities = np.asarray(volatilities, dtype=np.float64).ravel()
        volume_changes = np.asarray(volume_changes, dtype=np.float64).ravel()

        min_len = min(len(returns), len(volatilities), len(volume_changes))
        if min_len < self.n_components * 10:
            regime_logger.warning(f"训练数据不足: {min_len} < {self.n_components * 10}")
            return {"converged": False, "n_iter": 0, "state_mapping": {}, "error": "训练数据不足"}

        returns = returns[:min_len]
        volatilities = volatilities[:min_len]
        volume_changes = volume_changes[:min_len]

        obs = np.column_stack([returns, volatilities, volume_changes])

        model = GaussianHMM(
            n_components=self.n_components,
            covariance_type="diag",
            n_iter=200,
            random_state=42,
            tol=1e-4,
        )

        try:
            model.fit(obs)
        except ValueError:
            model = GaussianHMM(
                n_components=self.n_components,
                covariance_type="spherical",
                n_iter=200,
                random_state=42,
                tol=1e-4,
            )
            try:
                model.fit(obs)
            except Exception as e:
                regime_logger.error(f"HMM训练失败: {e}")
                return {"converged": False, "n_iter": 0, "state_mapping": {}, "error": str(e)}

        self._model = model
        self._state_mapping = self._build_state_mapping(model.means_)
        self._ready = True

        regime_logger.info(f"HMM训练完成: converged={model.monitor_.converged}, n_iter={model.monitor_.iter}, state_mapping={self._state_mapping}")

        return {
            "converged": bool(model.monitor_.converged),
            "n_iter": int(model.monitor_.iter),
            "state_mapping": dict(self._state_mapping),
        }

    def _build_state_mapping(self, means: np.ndarray) -> Dict[int, str]:
        n = self.n_components
        mapping: Dict[int, str] = {}

        if n == 4:
            labels_pool = ["趋势上涨", "趋势下跌", "高波动", "低波动震荡"]
        elif n == 5:
            labels_pool = ["趋势上涨", "趋势下跌", "高波动", "低波动震荡", "恐慌"]
        else:
            for i in range(n):
                mapping[i] = f"状态{i}"
            return mapping

        assigned = set()
        mean_returns = means[:, 0]
        mean_vols = means[:, 1]

        idx_highest_return = int(np.argmax(mean_returns))
        mapping[idx_highest_return] = "趋势上涨"
        assigned.add(idx_highest_return)

        idx_lowest_return = int(np.argmin(mean_returns))
        if idx_lowest_return not in assigned:
            mapping[idx_lowest_return] = "趋势下跌"
            assigned.add(idx_lowest_return)
        else:
            remaining = [i for i in range(n) if i not in assigned]
            if remaining:
                idx = remaining[int(np.argmin(mean_returns[remaining]))]
                mapping[idx] = "趋势下跌"
                assigned.add(idx)

        idx_highest_vol = int(np.argmax(mean_vols))
        if idx_highest_vol not in assigned:
            mapping[idx_highest_vol] = "高波动"
            assigned.add(idx_highest_vol)
        else:
            remaining = [i for i in range(n) if i not in assigned]
            if remaining:
                idx = remaining[int(np.argmax(mean_vols[remaining]))]
                mapping[idx] = "高波动"
                assigned.add(idx)

        if n == 5:
            panic_candidates = [i for i in range(n) if i not in assigned]
            if panic_candidates:
                panic_scores = []
                for i in panic_candidates:
                    score = -mean_returns[i] + mean_vols[i]
                    panic_scores.append(score)
                idx_panic = panic_candidates[int(np.argmax(panic_scores))]
                mapping[idx_panic] = "恐慌"
                assigned.add(idx_panic)

        remaining = [i for i in range(n) if i not in assigned]
        if remaining:
            idx = remaining[0]
            if "低波动震荡" not in mapping.values():
                mapping[idx] = "低波动震荡"
                assigned.add(idx)

        remaining = [i for i in range(n) if i not in assigned]
        for i, idx in enumerate(remaining):
            for label in labels_pool:
                if label not in mapping.values():
                    mapping[idx] = label
                    break
            else:
                mapping[idx] = f"状态{idx}"

        return mapping

    def predict(self, returns: np.ndarray, volatilities: np.ndarray, volume_changes: np.ndarray) -> dict:
        if not self.is_ready():
            return {"current_state": "未知", "state_probabilities": {}, "transition_matrix": None}

        returns = np.asarray(returns, dtype=np.float64).ravel()
        volatilities = np.asarray(volatilities, dtype=np.float64).ravel()
        volume_changes = np.asarray(volume_changes, dtype=np.float64).ravel()

        min_len = min(len(returns), len(volatilities), len(volume_changes))
        if min_len < self.n_components:
            return {"current_state": "未知", "state_probabilities": {}, "transition_matrix": None}

        obs = np.column_stack([
            returns[:min_len],
            volatilities[:min_len],
            volume_changes[:min_len],
        ])

        state_seq = self._model.predict(obs)
        current_state_idx = int(state_seq[-1])

        current_state = self._state_mapping.get(current_state_idx, f"状态{current_state_idx}")

        posteriors = self._model.predict_proba(obs)
        last_posteriors = posteriors[-1]

        state_probabilities = {}
        for i in range(self.n_components):
            label = self._state_mapping.get(i, f"状态{i}")
            state_probabilities[label] = round(float(last_posteriors[i]), 4)

        transition_matrix = self.get_transition_probabilities()

        regime_logger.info(f"HMM预测: current_state={current_state}, probabilities={state_probabilities}")

        return {
            "current_state": current_state,
            "state_probabilities": state_probabilities,
            "transition_matrix": transition_matrix,
        }

    def get_transition_probabilities(self) -> Optional[np.ndarray]:
        if not self.is_ready():
            return None
        return self._model.transmat_.copy()

    def save(self, model_path: str) -> bool:
        if not self.is_ready():
            regime_logger.warning("模型未训练，无法保存")
            return False

        if not JOBLIB_AVAILABLE:
            regime_logger.warning("joblib未安装，无法保存模型")
            return False

        try:
            import os
            os.makedirs(os.path.dirname(model_path), exist_ok=True)
            save_data = {
                "model": self._model,
                "state_mapping": self._state_mapping,
                "n_components": self.n_components,
            }
            joblib.dump(save_data, model_path)
            regime_logger.info(f"HMM模型已保存: {model_path}")
            return True
        except Exception as e:
            regime_logger.error(f"HMM模型保存失败: {e}")
            return False

    def load(self, model_path: str) -> bool:
        if not JOBLIB_AVAILABLE:
            regime_logger.warning("joblib未安装，无法加载模型")
            return False

        try:
            save_data = joblib.load(model_path)
            self._model = save_data["model"]
            self._state_mapping = save_data["state_mapping"]
            self.n_components = save_data.get("n_components", self.n_components)
            self._ready = True
            regime_logger.info(f"HMM模型已加载: {model_path}, state_mapping={self._state_mapping}")
            return True
        except Exception as e:
            regime_logger.error(f"HMM模型加载失败: {e}")
            self._ready = False
            return False

    def is_ready(self) -> bool:
        return self._ready and self._model is not None


class RegimeDetector:
    """基于规则的市场状态检测器"""

    def __init__(self, config: dict = None):
        self.config = config or {}

    def detect_regime(self, market_data: dict) -> str:
        volatility_signal = market_data.get("volatility_signal", "")
        volume_ratio = market_data.get("volume_ratio", 1.0)
        market_change_pct = market_data.get("market_change_pct", 0.0)
        volatility_value = market_data.get("volatility_value", 0.0)

        try:
            volume_ratio = float(volume_ratio) if volume_ratio else 1.0
        except (TypeError, ValueError):
            volume_ratio = 1.0

        try:
            market_change_pct = float(market_change_pct) if market_change_pct else 0.0
        except (TypeError, ValueError):
            market_change_pct = 0.0

        if volatility_signal == "高波动" and market_change_pct < -3:
            regime = "恐慌"
        elif volatility_signal == "高波动" and market_change_pct > 3:
            regime = "趋势牛市"
        elif volatility_signal in ("正常", "低波动") and volume_ratio < 0.8:
            regime = "缩量震荡"
        elif volume_ratio > 2.0 and abs(market_change_pct) < 1:
            regime = "机构行情"
        else:
            regime = "缩量震荡"

        regime_logger.info(f"市场状态检测: {regime} (volatility_signal={volatility_signal}, volume_ratio={volume_ratio}, market_change_pct={market_change_pct})")
        return regime


class DynamicWeightManager:
    """动态权重管理器，基于市场状态切换权重配置，使用EMA平滑过渡"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        dw_config = self.config.get("dynamic_weights", {})

        self.enabled = dw_config.get("enabled", True)
        self.alpha = dw_config.get("smoothing_alpha", 0.3)

        regimes_config = dw_config.get("regimes", {})
        self.regimes = {}
        for regime_name, weights in DEFAULT_REGIMES.items():
            self.regimes[regime_name] = regimes_config.get(regime_name, weights)

        self.current_weights = dict(DEFAULT_WEIGHTS)
        self.current_regime = "缩量震荡"

        self._detector = RegimeDetector(self.config)
        self.hmm_detector: Optional[HMMRegimeDetector] = None

    def set_hmm_detector(self, detector: HMMRegimeDetector) -> None:
        self.hmm_detector = detector
        regime_logger.info(f"HMM检测器已设置: ready={detector.is_ready()}")

    def _resolve_regime(self, regime: str) -> str:
        return REGIME_ALIASES.get(regime, regime)

    def _normalize_weights(self, weights: dict) -> dict:
        total = sum(weights.values())
        if total <= 0:
            return dict(DEFAULT_WEIGHTS)
        return {k: v / total for k, v in weights.items()}

    def update_weights(self, regime: str) -> dict:
        resolved = self._resolve_regime(regime)
        target = self.regimes.get(resolved, self.regimes.get("缩量震荡", DEFAULT_WEIGHTS))

        new_weights = {}
        for key in self.current_weights:
            current = self.current_weights.get(key, 0.0)
            tgt = target.get(key, 0.0)
            new_weights[key] = self.alpha * tgt + (1 - self.alpha) * current

        new_weights = self._normalize_weights(new_weights)
        self.current_weights = new_weights
        self.current_regime = resolved

        regime_logger.info(f"权重更新: regime={resolved}, weights={new_weights}")
        return dict(self.current_weights)

    def get_current_weights(self) -> dict:
        return dict(self.current_weights)

    def get_regime(self) -> str:
        return self.current_regime

    def detect_and_update(self, market_data: dict) -> dict:
        if self.hmm_detector is not None and self.hmm_detector.is_ready():
            hmm_result = self.hmm_detector.predict(
                np.asarray(market_data.get("returns", []), dtype=np.float64),
                np.asarray(market_data.get("volatilities", []), dtype=np.float64),
                np.asarray(market_data.get("volume_changes", []), dtype=np.float64),
            )
            hmm_state = hmm_result.get("current_state", "")
            if hmm_state and hmm_state != "未知":
                regime_logger.info(f"使用HMM检测市场状态: {hmm_state}")
                return self.update_weights(hmm_state)

        regime = self._detector.detect_regime(market_data)
        return self.update_weights(regime)
