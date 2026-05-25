"""
LightGBM混合预测模型模块
提供ML预测能力，与规则引擎混合输出最终预测
"""

import os
import numpy as np
from typing import Dict, Optional, Tuple

from scripts.logger import get_logger

ml_logger = get_logger("ml_model")

try:
    import lightgbm as lgb
    _LGB_AVAILABLE = True
except ImportError:
    _LGB_AVAILABLE = False

try:
    import joblib
    _JOBLIB_AVAILABLE = True
except ImportError:
    _JOBLIB_AVAILABLE = False


DEFAULT_HYPERPARAMS = {
    "num_leaves": 31,
    "learning_rate": 0.05,
    "n_estimators": 200,
    "min_child_samples": 20,
}


class LightGBMPredictor:
    def __init__(self, config: dict = None):
        self.config = config or {}
        ml_config = self.config.get("ml_model", {})
        self.hyperparams = ml_config.get("hyperparams", DEFAULT_HYPERPARAMS)
        self.min_training_days = ml_config.get("min_training_days", 60)

        self._return_model = None
        self._direction_model = None
        self._volatility_model = None
        self._feature_names = []
        self._is_ready = False

    def train(self, X: np.ndarray, y: dict, params: dict = None, feature_names: list = None) -> dict:
        if not _LGB_AVAILABLE:
            ml_logger.warning("lightgbm未安装，无法训练模型")
            return {"error": "lightgbm not available"}

        if X.shape[0] < self.min_training_days:
            ml_logger.warning(f"训练数据不足: {X.shape[0]} < {self.min_training_days}")
            return {"error": f"insufficient data: {X.shape[0]} < {self.min_training_days}"}

        # 保存特征名，用于特征重要性和预测时构造 DataFrame
        if feature_names and len(feature_names) == X.shape[1]:
            self._feature_names = feature_names

        train_params = params or self.hyperparams

        split_idx = int(X.shape[0] * 0.8)
        X_train, X_val = X[:split_idx], X[split_idx:]

        # 如果有特征名，构造 DataFrame 以消除 sklearn 特征名警告
        if self._feature_names:
            import pandas as pd
            X_train_df = pd.DataFrame(X_train, columns=self._feature_names)
            X_val_df = pd.DataFrame(X_val, columns=self._feature_names)
        else:
            X_train_df, X_val_df = X_train, X_val

        metrics = {}
        feature_importance = {}

        y_return = y.get("next_day_return")
        if y_return is not None:
            y_train_r, y_val_r = y_return[:split_idx], y_return[split_idx:]
            self._return_model = lgb.LGBMRegressor(
                num_leaves=train_params.get("num_leaves", 31),
                learning_rate=train_params.get("learning_rate", 0.05),
                n_estimators=train_params.get("n_estimators", 200),
                min_child_samples=train_params.get("min_child_samples", 20),
                verbose=-1,
            )
            self._return_model.fit(
                X_train_df, y_train_r,
                eval_set=[(X_train_df, y_train_r), (X_val_df, y_val_r)],
                callbacks=[lgb.early_stopping(stopping_rounds=20, verbose=False)],
            )
            train_pred_r = self._return_model.predict(X_train_df)
            val_pred_r = self._return_model.predict(X_val_df)
            metrics["return_train_loss"] = float(np.mean((train_pred_r - y_train_r) ** 2))
            metrics["return_val_loss"] = float(np.mean((val_pred_r - y_val_r) ** 2))
            feature_importance["return"] = dict(zip(
                self._feature_names if self._feature_names else [f"f{i}" for i in range(X.shape[1])],
                self._return_model.feature_importances_.tolist(),
            ))

        y_direction = y.get("direction")
        if y_direction is not None:
            y_train_d, y_val_d = y_direction[:split_idx], y_direction[split_idx:]
            self._direction_model = lgb.LGBMClassifier(
                num_leaves=train_params.get("num_leaves", 31),
                learning_rate=train_params.get("learning_rate", 0.05),
                n_estimators=train_params.get("n_estimators", 200),
                min_child_samples=train_params.get("min_child_samples", 20),
                verbose=-1,
            )
            self._direction_model.fit(
                X_train_df, y_train_d,
                eval_set=[(X_train_df, y_train_d), (X_val_df, y_val_d)],
                callbacks=[lgb.early_stopping(stopping_rounds=20, verbose=False)],
            )
            train_pred_d = self._direction_model.predict(X_train_df)
            val_pred_d = self._direction_model.predict(X_val_df)
            metrics["direction_train_acc"] = float(np.mean(train_pred_d == y_train_d))
            metrics["direction_val_acc"] = float(np.mean(val_pred_d == y_val_d))
            feature_importance["direction"] = dict(zip(
                self._feature_names if self._feature_names else [f"f{i}" for i in range(X.shape[1])],
                self._direction_model.feature_importances_.tolist(),
            ))

        y_volatility = y.get("volatility")
        if y_volatility is not None:
            y_train_v, y_val_v = y_volatility[:split_idx], y_volatility[split_idx:]
            self._volatility_model = lgb.LGBMRegressor(
                num_leaves=train_params.get("num_leaves", 31),
                learning_rate=train_params.get("learning_rate", 0.05),
                n_estimators=train_params.get("n_estimators", 200),
                min_child_samples=train_params.get("min_child_samples", 20),
                verbose=-1,
            )
            self._volatility_model.fit(
                X_train_df, y_train_v,
                eval_set=[(X_train_df, y_train_v), (X_val_df, y_val_v)],
                callbacks=[lgb.early_stopping(stopping_rounds=20, verbose=False)],
            )
            train_pred_v = self._volatility_model.predict(X_train_df)
            val_pred_v = self._volatility_model.predict(X_val_df)
            metrics["volatility_train_loss"] = float(np.mean((train_pred_v - y_train_v) ** 2))
            metrics["volatility_val_loss"] = float(np.mean((val_pred_v - y_val_v) ** 2))
            feature_importance["volatility"] = dict(zip(
                self._feature_names if self._feature_names else [f"f{i}" for i in range(X.shape[1])],
                self._volatility_model.feature_importances_.tolist(),
            ))

        self._is_ready = True
        metrics["feature_importance"] = feature_importance
        metrics["n_samples"] = X.shape[0]
        metrics["n_features"] = X.shape[1]

        ml_logger.info(f"模型训练完成: samples={X.shape[0]}, features={X.shape[1]}, metrics={metrics}")

        return metrics

    def predict(self, X: np.ndarray, feature_names: list = None) -> dict:
        if not self.is_ready():
            ml_logger.warning("predict调用但模型未就绪")
            return {}

        import pandas as pd

        # 特征对齐：预测时特征数可能与训练时不一致，需要对齐
        if feature_names and self._feature_names:
            n_model_features = len(self._feature_names)
            if len(feature_names) != n_model_features or feature_names != self._feature_names:
                # 构造与训练时特征顺序一致的DataFrame，缺失特征填0
                if X.ndim == 1:
                    X_flat = X
                else:
                    X_flat = X[-1] if len(X) > 0 else X.flatten()
                pred_dict = dict(zip(feature_names, X_flat))
                aligned_values = [pred_dict.get(fn, 0.0) for fn in self._feature_names]
                X_input = pd.DataFrame([aligned_values], columns=self._feature_names)
                ml_logger.info(
                    f"特征对齐: 输入{len(feature_names)}个→模型{ n_model_features}个, "
                    f"缺失{set(self._feature_names) - set(feature_names)}, "
                    f"多余{set(feature_names) - set(self._feature_names)}"
                )
            else:
                if X.ndim == 1:
                    X_input = pd.DataFrame([X], columns=feature_names)
                else:
                    X_input = pd.DataFrame(X, columns=feature_names)
        elif feature_names and len(feature_names) == X.shape[-1]:
            if X.ndim == 1:
                X_input = pd.DataFrame([X], columns=feature_names)
            else:
                X_input = pd.DataFrame(X, columns=feature_names)
        else:
            X_input = X

        result = {}

        if self._return_model is not None:
            pred_return = self._return_model.predict(X_input)
            result["next_day_return"] = float(pred_return[-1]) if len(pred_return) > 0 else 0.0

        if self._direction_model is not None:
            pred_direction = self._direction_model.predict(X_input)
            pred_proba = self._direction_model.predict_proba(X_input)
            result["direction"] = int(pred_direction[-1]) if len(pred_direction) > 0 else 0
            if pred_proba.ndim == 2:
                result["direction_confidence"] = float(np.max(pred_proba[-1]))
            else:
                result["direction_confidence"] = 0.5

        if self._volatility_model is not None:
            pred_volatility = self._volatility_model.predict(X_input)
            result["volatility"] = float(pred_volatility[-1]) if len(pred_volatility) > 0 else 0.0

        if "next_day_return" in result and "direction_confidence" in result:
            result["confidence"] = result["direction_confidence"]
        elif "next_day_return" in result:
            result["confidence"] = min(1.0, abs(result["next_day_return"]) * 10)
        else:
            result["confidence"] = 0.0

        ml_logger.info(
            f"ML predict: return={result.get('next_day_return', 'N/A'):.4f}, "
            f"direction={result.get('direction', 'N/A')}, "
            f"volatility={result.get('volatility', 'N/A'):.4f}, "
            f"confidence={result.get('confidence', 'N/A'):.3f}"
        )

        return result

    def save(self, model_dir: str) -> str:
        os.makedirs(model_dir, exist_ok=True)

        saved_files = []

        if self._return_model is not None:
            if _JOBLIB_AVAILABLE:
                path = os.path.join(model_dir, "return_model.joblib")
                joblib.dump(self._return_model, path)
                saved_files.append(path)
            path = os.path.join(model_dir, "return_model.txt")
            self._return_model.booster_.save_model(path)
            saved_files.append(path)

        if self._direction_model is not None:
            if _JOBLIB_AVAILABLE:
                path = os.path.join(model_dir, "direction_model.joblib")
                joblib.dump(self._direction_model, path)
                saved_files.append(path)
            path = os.path.join(model_dir, "direction_model.txt")
            self._direction_model.booster_.save_model(path)
            saved_files.append(path)

        if self._volatility_model is not None:
            if _JOBLIB_AVAILABLE:
                path = os.path.join(model_dir, "volatility_model.joblib")
                joblib.dump(self._volatility_model, path)
                saved_files.append(path)
            path = os.path.join(model_dir, "volatility_model.txt")
            self._volatility_model.booster_.save_model(path)
            saved_files.append(path)

        meta = {
            "feature_names": self._feature_names,
            "is_ready": self._is_ready,
            "hyperparams": self.hyperparams,
            "min_training_days": self.min_training_days,
        }
        if _JOBLIB_AVAILABLE:
            meta_path = os.path.join(model_dir, "meta.joblib")
            joblib.dump(meta, meta_path)
            saved_files.append(meta_path)

        ml_logger.info(f"模型已保存到 {model_dir}: {saved_files}")
        return model_dir

    def load(self, model_dir: str) -> bool:
        if not _LGB_AVAILABLE:
            ml_logger.warning("lightgbm未安装，无法加载模型")
            return False

        if not os.path.isdir(model_dir):
            ml_logger.warning(f"模型目录不存在: {model_dir}")
            return False

        try:
            meta_path = os.path.join(model_dir, "meta.joblib")
            if _JOBLIB_AVAILABLE and os.path.exists(meta_path):
                meta = joblib.load(meta_path)
                self._feature_names = meta.get("feature_names", [])
                self._is_ready = meta.get("is_ready", False)
            else:
                self._feature_names = []

            if _JOBLIB_AVAILABLE:
                return_joblib_path = os.path.join(model_dir, "return_model.joblib")
                if os.path.exists(return_joblib_path):
                    self._return_model = joblib.load(return_joblib_path)

                direction_joblib_path = os.path.join(model_dir, "direction_model.joblib")
                if os.path.exists(direction_joblib_path):
                    self._direction_model = joblib.load(direction_joblib_path)

                volatility_joblib_path = os.path.join(model_dir, "volatility_model.joblib")
                if os.path.exists(volatility_joblib_path):
                    self._volatility_model = joblib.load(volatility_joblib_path)
            else:
                return_model_path = os.path.join(model_dir, "return_model.txt")
                if os.path.exists(return_model_path):
                    booster = lgb.Booster(model_file=return_model_path)
                    self._return_model = lgb.LGBMRegressor(verbose=-1)
                    self._return_model._Booster = booster
                    self._return_model._fitted = True

                direction_model_path = os.path.join(model_dir, "direction_model.txt")
                if os.path.exists(direction_model_path):
                    booster = lgb.Booster(model_file=direction_model_path)
                    self._direction_model = lgb.LGBMClassifier(verbose=-1)
                    self._direction_model._Booster = booster
                    self._direction_model._fitted = True

                volatility_model_path = os.path.join(model_dir, "volatility_model.txt")
                if os.path.exists(volatility_model_path):
                    booster = lgb.Booster(model_file=volatility_model_path)
                    self._volatility_model = lgb.LGBMRegressor(verbose=-1)
                    self._volatility_model._Booster = booster
                    self._volatility_model._fitted = True

            if any([self._return_model, self._direction_model, self._volatility_model]):
                self._is_ready = True
                ml_logger.info(f"模型加载成功: {model_dir}")
                return True
            else:
                ml_logger.warning(f"未找到有效模型文件: {model_dir}")
                return False

        except Exception as e:
            ml_logger.error(f"模型加载失败: {e}")
            self._is_ready = False
            return False

    def is_ready(self) -> bool:
        if not _LGB_AVAILABLE:
            return False
        return self._is_ready

    def get_feature_importance(self) -> dict:
        result = {}
        if self._return_model is not None:
            names = self._feature_names if self._feature_names else [f"f{i}" for i in range(len(self._return_model.feature_importances_))]
            result["return"] = dict(zip(names, self._return_model.feature_importances_.tolist()))
        if self._direction_model is not None:
            names = self._feature_names if self._feature_names else [f"f{i}" for i in range(len(self._direction_model.feature_importances_))]
            result["direction"] = dict(zip(names, self._direction_model.feature_importances_.tolist()))
        if self._volatility_model is not None:
            names = self._feature_names if self._feature_names else [f"f{i}" for i in range(len(self._volatility_model.feature_importances_))]
            result["volatility"] = dict(zip(names, self._volatility_model.feature_importances_.tolist()))
        return result


def build_feature_matrix(
    db_manager,
    stock_code: str,
    indicators_list: list = None,
) -> tuple:
    from scripts.core.feature_engineering import extract_feature_vector

    min_days = 60

    try:
        history_df = db_manager.get_historical_data()
    except Exception as e:
        ml_logger.warning(f"获取历史数据失败: {e}")
        return (np.array([]), {}, [], [])

    if history_df is None or history_df.empty or len(history_df) < min_days:
        ml_logger.warning(f"数据不足: {len(history_df) if history_df is not None else 0} < {min_days}")
        return (np.array([]), {}, [], [])

    try:
        from scripts.technical_indicators import calculate_all_indicators
        indicators = calculate_all_indicators(history_df)
    except Exception as e:
        ml_logger.warning(f"计算技术指标失败: {e}")
        return (np.array([]), {}, [], [])

    feature_names, _ = extract_feature_vector(indicators)
    if not feature_names:
        ml_logger.warning("特征提取结果为空")
        return (np.array([]), {}, [], [])

    n_days = len(history_df)
    n_features = len(feature_names)
    X = np.zeros((n_days, n_features), dtype=np.float64)

    closes = history_df["收盘"].values if "收盘" in history_df.columns else None
    if closes is None:
        return (np.array([]), {}, [], [])

    for i in range(n_days):
        window_df = history_df.iloc[:i + 1]
        if len(window_df) < 5:
            continue
        try:
            window_indicators = calculate_all_indicators(window_df)
            _, feature_values = extract_feature_vector(window_indicators)
            if len(feature_values) == n_features:
                X[i] = feature_values
            elif len(feature_values) > 0:
                min_len = min(len(feature_values), n_features)
                X[i, :min_len] = feature_values[:min_len]
        except Exception:
            continue

    next_day_return = np.zeros(n_days, dtype=np.float64)
    for i in range(n_days - 1):
        if closes[i] > 0:
            next_day_return[i] = (closes[i + 1] - closes[i]) / closes[i]
    next_day_return[-1] = 0.0

    direction = (next_day_return > 0).astype(int)

    volatility = np.zeros(n_days, dtype=np.float64)
    if n_days >= 5:
        for i in range(4, n_days):
            window_closes = closes[i - 4:i + 1]
            volatility[i] = float(np.std(np.diff(window_closes) / window_closes[:-1]))

    dates = []
    if "日期" in history_df.columns:
        dates = history_df["日期"].tolist()
    else:
        dates = list(range(n_days))

    y = {
        "next_day_return": next_day_return,
        "direction": direction,
        "volatility": volatility,
    }

    return (X, y, feature_names, dates)


def hybrid_predict(
    rule_prediction: dict,
    ml_prediction: dict,
    alpha: float = 0.5,
) -> dict:
    if not ml_prediction:
        return dict(rule_prediction)

    if not rule_prediction:
        return dict(ml_prediction)

    result = {}

    rule_low = rule_prediction.get("target_low") or rule_prediction.get("day1", {}).get("target_low")
    rule_high = rule_prediction.get("target_high") or rule_prediction.get("day1", {}).get("target_high")
    current_price = rule_prediction.get("current", 0)

    ml_return = ml_prediction.get("next_day_return", 0.0)
    ml_volatility = ml_prediction.get("volatility", 0.0)
    ml_direction = ml_prediction.get("direction", 0)
    ml_confidence = ml_prediction.get("confidence", 0.0)

    if current_price and current_price > 0:
        ml_low = current_price * (1 + ml_return - ml_volatility)
        ml_high = current_price * (1 + ml_return + ml_volatility)
    else:
        ml_low = rule_low
        ml_high = rule_high

    if rule_low is not None and ml_low is not None:
        hybrid_low = alpha * rule_low + (1 - alpha) * ml_low
        result["target_low"] = round(hybrid_low, 2)
    elif rule_low is not None:
        result["target_low"] = rule_low

    if rule_high is not None and ml_high is not None:
        hybrid_high = alpha * rule_high + (1 - alpha) * ml_high
        result["target_high"] = round(hybrid_high, 2)
    elif rule_high is not None:
        result["target_high"] = rule_high

    rule_direction = 0
    rule_trend = rule_prediction.get("trend", "neutral")
    if rule_trend in ("up", "strong_up"):
        rule_direction = 1
    elif rule_trend in ("down", "strong_down"):
        rule_direction = 0
    else:
        rule_direction = 0.5

    rule_conf = rule_prediction.get("validation_confidence", 0.5)
    weighted_rule = alpha * rule_direction
    weighted_ml = (1 - alpha) * ml_direction
    hybrid_direction_score = weighted_rule + weighted_ml
    if hybrid_direction_score > 0.55:
        hybrid_direction = 1
    elif hybrid_direction_score < 0.45:
        hybrid_direction = 0
    else:
        hybrid_direction = 0.5  # 中性

    result["direction"] = hybrid_direction

    if hybrid_direction == 1:
        result["trend"] = "up" if hybrid_direction_score < 0.7 else "strong_up"
    elif hybrid_direction == 0:
        result["trend"] = "down" if hybrid_direction_score > 0.3 else "strong_down"
    else:
        result["trend"] = "neutral"

    rule_dir_binary = 1 if rule_direction > 0.5 else 0
    ml_dir_binary = ml_direction
    direction_agreement = 1 if rule_dir_binary == ml_dir_binary else 0

    confidence = max(rule_conf, ml_confidence) * (1 - abs(rule_dir_binary - ml_dir_binary) * 0.3)
    result["confidence"] = round(max(0.0, min(1.0, confidence)), 3)

    limit_pct = rule_prediction.get("limit_pct", 0.10)
    if current_price and current_price > 0 and limit_pct > 0:
        limit_up = current_price * (1 + limit_pct)
        limit_down = current_price * (1 - limit_pct)

        if "target_high" in result and result["target_high"] is not None:
            result["target_high"] = min(result["target_high"], round(limit_up, 2))
        if "target_low" in result and result["target_low"] is not None:
            result["target_low"] = max(result["target_low"], round(limit_down, 2))

    result["hybrid_alpha"] = alpha
    result["ml_prediction"] = ml_prediction

    ml_logger.info(
        f"hybrid_predict: alpha={alpha}, "
        f"rule_low={rule_low}, rule_high={rule_high}, "
        f"ml_low={ml_low:.2f}, ml_high={ml_high:.2f}, "
        f"hybrid_low={result.get('target_low')}, hybrid_high={result.get('target_high')}, "
        f"direction_agreement={direction_agreement}, trend={result.get('trend')}"
    )

    for key in ("current", "support", "resistance", "day1", "day2"):
        if key in rule_prediction:
            result[key] = rule_prediction[key]

    hybrid_trend = result.get("trend")
    if hybrid_trend:
        if "day1" in result and isinstance(result["day1"], dict):
            result["day1"]["trend"] = hybrid_trend
        if "day2" in result and isinstance(result["day2"], dict):
            result["day2"]["trend"] = hybrid_trend

    return result
