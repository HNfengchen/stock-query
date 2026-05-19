import numpy as np
import pandas as pd
from typing import Dict, Optional
from scripts.logger import get_logger

stress_logger = get_logger("StressTest")


class MonteCarloStressTest:
    def __init__(self, n_simulations: int = 200, config: dict = None):
        self.n_simulations = n_simulations
        self.config = config or {}
        self.noise_scale = self.config.get("noise_scale", 0.5)

    @staticmethod
    def _calculate_core_indicators_only(df: pd.DataFrame) -> dict:
        from scripts.technical_indicators import calculate_macd, calculate_rsi, calculate_kdj

        if "收盘" in df.columns:
            close = df["收盘"]
        elif "close" in df.columns:
            close = df["close"]
        else:
            return {"MACD": {}, "RSI": {}, "KDJ": {}}

        macd = calculate_macd(close)
        rsi = calculate_rsi(close)

        if "最高" in df.columns and "最低" in df.columns:
            high = df["最高"]
            low = df["最低"]
        elif "high" in df.columns and "low" in df.columns:
            high = df["high"]
            low = df["low"]
        else:
            kdj = {}
            return {"MACD": macd, "RSI": rsi, "KDJ": kdj}

        kdj = calculate_kdj(high, low, close)
        return {"MACD": macd, "RSI": rsi, "KDJ": kdj}

    def run(self, analyzer, history_df: pd.DataFrame, indicators: dict) -> dict:
        if history_df is None or history_df.empty or "收盘" not in history_df.columns:
            stress_logger.warning("历史数据不足，跳过压力测试")
            return self._empty_result()

        original_close = history_df["收盘"].values.astype(np.float64)
        if len(original_close) < 2:
            stress_logger.warning("收盘数据不足2条，跳过压力测试")
            return self._empty_result()

        original_returns = np.diff(original_close) / original_close[:-1]
        original_signal = self._get_signal(analyzer, history_df, indicators)

        if original_signal is None:
            stress_logger.warning("无法获取原始信号，跳过压力测试")
            return self._empty_result()

        flip_count = 0
        simulated_returns_list = []
        max_drawdown_list = []

        for _ in range(self.n_simulations):
            perturbed_returns = self._perturb_returns(original_returns, self.noise_scale)
            perturbed_prices = self._reconstruct_prices(original_close, perturbed_returns)

            perturbed_df = history_df.copy()
            perturbed_df["收盘"] = perturbed_prices

            try:
                perturbed_indicators = self._calculate_core_indicators_only(perturbed_df)
            except Exception as e:
                stress_logger.debug(f"扰动指标计算失败: {e}")
                continue

            new_signal = self._get_signal(analyzer, perturbed_df, perturbed_indicators)
            if new_signal is None:
                continue

            if self._signal_flipped(original_signal, new_signal):
                flip_count += 1

            sim_total_returns = perturbed_returns
            simulated_returns_list.append(sim_total_returns)

            dd = self._compute_max_drawdown(perturbed_prices)
            max_drawdown_list.append(dd)

        signal_flip_rate = flip_count / self.n_simulations if self.n_simulations > 0 else 0.0

        if simulated_returns_list:
            all_returns = np.concatenate(simulated_returns_list)
            mean_return = np.mean(all_returns)
            max_dd = np.max(max_drawdown_list) if max_drawdown_list else 0.0
            sharpe = self._compute_sharpe(all_returns)
            sortino = self._compute_sortino(all_returns)
            calmar = self._compute_calmar(all_returns, max_dd)
        else:
            mean_return = 0.0
            max_dd = 0.0
            sharpe = 0.0
            sortino = 0.0
            calmar = 0.0

        is_robust = signal_flip_rate < 0.3

        result = {
            "status": "completed",
            "signal_flip_rate": round(signal_flip_rate, 4),
            "is_robust": is_robust,
            "risk_metrics": {
                "max_drawdown": round(max_dd, 4),
                "sharpe": round(sharpe, 4),
                "sortino": round(sortino, 4),
                "calmar": round(calmar, 4),
            },
            "original_signal": original_signal,
            "simulation_count": self.n_simulations,
        }

        stress_logger.info(
            f"压力测试完成: 翻转率={signal_flip_rate:.4f}, "
            f"鲁棒={'是' if is_robust else '否'}, "
            f"最大回撤={max_dd:.4f}, Sharpe={sharpe:.4f}"
        )

        return result

    def _get_signal(self, analyzer, history_df: pd.DataFrame, indicators: dict) -> Optional[str]:
        try:
            current_price = float(history_df["收盘"].iloc[-1])
        except (IndexError, TypeError, ValueError):
            return None

        try:
            tech_result = analyzer.analyze_technical(indicators, current_price)
            fund_result = analyzer.analyze_fund_flow({})
            sentiment_result = analyzer.analyze_market_sentiment({"stock_info": {}})

            analysis = {
                "technical": tech_result,
                "fund_flow": fund_result,
                "sentiment": sentiment_result,
            }
            signal_result = analyzer.generate_trading_signal(analysis)
            return signal_result.get("signal", "hold")
        except Exception as e:
            stress_logger.debug(f"获取信号失败: {e}")
            return None

    def _signal_flipped(self, original: str, new: str) -> bool:
        buy_signals = {"strong_buy", "buy"}
        sell_signals = {"sell", "watch"}

        if original in buy_signals and new in sell_signals:
            return True
        if original in sell_signals and new in buy_signals:
            return True
        return False

    def _perturb_returns(self, returns: np.ndarray, noise_scale: float = 0.5) -> np.ndarray:
        std = np.std(returns)
        if std == 0:
            return returns.copy()
        noise = np.random.normal(0, noise_scale * std, size=returns.shape)
        return returns + noise

    def _reconstruct_prices(self, original_close: np.ndarray, perturbed_returns: np.ndarray) -> np.ndarray:
        prices = np.empty(len(original_close))
        prices[0] = original_close[0]
        for i in range(len(perturbed_returns)):
            prices[i + 1] = prices[i] * (1 + perturbed_returns[i])
        return prices

    def _compute_max_drawdown(self, prices: np.ndarray) -> float:
        if len(prices) < 2:
            return 0.0
        peak = prices[0]
        max_dd = 0.0
        for p in prices[1:]:
            if p > peak:
                peak = p
            dd = (peak - p) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _compute_sharpe(self, returns: np.ndarray, risk_free: float = 0.0) -> float:
        if len(returns) == 0:
            return 0.0
        std = np.std(returns)
        if std == 0:
            return 0.0
        return (np.mean(returns) - risk_free) / std

    def _compute_sortino(self, returns: np.ndarray, risk_free: float = 0.0) -> float:
        if len(returns) == 0:
            return 0.0
        negative_returns = returns[returns < 0]
        if len(negative_returns) == 0:
            downside_std = 0.0
        else:
            downside_std = np.std(negative_returns)
        if downside_std == 0:
            return 0.0 if np.mean(returns) - risk_free <= 0 else float("inf")
        return (np.mean(returns) - risk_free) / downside_std

    def _compute_calmar(self, returns: np.ndarray, max_drawdown: float) -> float:
        if max_drawdown == 0:
            return 0.0
        annualized_return = np.mean(returns) * 252
        return annualized_return / max_drawdown

    def _empty_result(self) -> dict:
        return {
            "status": "completed",
            "signal_flip_rate": 0.0,
            "is_robust": True,
            "risk_metrics": {
                "max_drawdown": 0.0,
                "sharpe": 0.0,
                "sortino": 0.0,
                "calmar": 0.0,
            },
            "original_signal": "unknown",
            "simulation_count": 0,
        }
