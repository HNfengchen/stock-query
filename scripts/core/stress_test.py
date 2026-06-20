import numpy as np
import pandas as pd
from typing import Dict, Optional
from scipy.stats import t as t_dist
from scripts.logger import get_logger

stress_logger = get_logger("stress_test")


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
        close_col = "收盘" if "收盘" in history_df.columns else "close" if "close" in history_df.columns else None
        if history_df is None or history_df.empty or close_col is None:
            stress_logger.warning("历史数据不足，跳过压力测试")
            return self._empty_result()

        original_close = history_df[close_col].values.astype(np.float64)
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

            perturbed_df = self._perturb_ohlc(history_df, perturbed_prices)

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
            max_dd = np.max(max_drawdown_list) if max_drawdown_list else 0.0
            sharpe = self._compute_sharpe(all_returns)
            sortino = self._compute_sortino(all_returns)
            calmar = self._compute_calmar(all_returns, max_dd)
        else:
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
            "stress_scenarios": self._run_stress_scenarios(
                analyzer, history_df, original_close, original_signal
            ),
        }

        stress_logger.info(
            f"压力测试完成: 翻转率={signal_flip_rate:.4f}, "
            f"鲁棒={'是' if is_robust else '否'}, "
            f"最大回撤={max_dd:.4f}, Sharpe={sharpe:.4f}"
        )

        return result

    def _get_signal(self, analyzer, history_df: pd.DataFrame, indicators: dict) -> Optional[str]:
        close_col = "收盘" if "收盘" in history_df.columns else "close" if "close" in history_df.columns else None
        if close_col is None:
            return None

        _al = None
        _rl = None
        _orig_al_level = None
        _orig_rl_level = None

        try:
            current_price = float(history_df[close_col].iloc[-1])
        except (IndexError, TypeError, ValueError):
            return None

        try:
            # 压力测试期间临时提高日志级别，避免大量重复日志
            _al = get_logger("analyzer")
            _rl = get_logger("regime_detector")
            _orig_al_level = _al.level
            _orig_rl_level = _rl.level
            _al.setLevel(max(_orig_al_level, 30))  # WARNING=30
            _rl.setLevel(max(_orig_rl_level, 30))

            tech_result = analyzer.analyze_technical(indicators, current_price)
            fund_result = {"score": 0.5, "trend": "neutral"}
            # 压力测试中使用中性情绪评分，避免触发外部API调用
            sentiment_result = {"score": 0.5, "details": {}, "market_status": "未知"}

            analysis = {
                "technical": tech_result,
                "fund_flow": fund_result,
                "sentiment": sentiment_result,
            }
            signal_result = analyzer.generate_trading_signal(analysis, market_data=None)

            return signal_result.get("signal", "hold")
        except Exception as e:
            stress_logger.debug(f"获取信号失败: {e}")
            return None
        finally:
            if _al is not None and _orig_al_level is not None:
                _al.setLevel(_orig_al_level)
            if _rl is not None and _orig_rl_level is not None:
                _rl.setLevel(_orig_rl_level)

    def _signal_flipped(self, original: str, new: str) -> bool:
        buy_signals = {"strong_buy", "buy"}
        sell_signals = {"sell", "watch"}
        neutral_signals = {"hold"}

        if original in buy_signals and new in (sell_signals | neutral_signals):
            return True
        if original in sell_signals and new in (buy_signals | neutral_signals):
            return True
        if original in neutral_signals and new in (buy_signals | sell_signals):
            return True
        return False

    def _perturb_returns(self, returns: np.ndarray, noise_scale: float = 0.5) -> np.ndarray:
        std = np.std(returns)
        if std == 0:
            return returns.copy()
        noise = t_dist.rvs(df=5, scale=noise_scale * std * 0.775, size=returns.shape)
        return returns + noise

    def _reconstruct_prices(self, original_close: np.ndarray, perturbed_returns: np.ndarray) -> np.ndarray:
        prices = np.empty(len(original_close))
        prices[0] = original_close[0]
        for i in range(len(perturbed_returns)):
            prices[i + 1] = prices[i] * (1 + perturbed_returns[i])
        return prices

    def _perturb_ohlc(self, history_df: pd.DataFrame, perturbed_prices: np.ndarray) -> pd.DataFrame:
        perturbed_df = history_df.copy()

        if "收盘" in history_df.columns:
            close_col = "收盘"
            open_col = "开盘" if "开盘" in history_df.columns else None
            high_col = "最高" if "最高" in history_df.columns else None
            low_col = "最低" if "最低" in history_df.columns else None
        elif "close" in history_df.columns:
            close_col = "close"
            open_col = "open" if "open" in history_df.columns else None
            high_col = "high" if "high" in history_df.columns else None
            low_col = "low" if "low" in history_df.columns else None
        else:
            return perturbed_df

        original_close = history_df[close_col].values.astype(np.float64)
        if len(original_close) != len(perturbed_prices):
            return perturbed_df

        for i in range(1, len(perturbed_prices)):
            if original_close[i] == 0 or pd.isna(original_close[i]):
                continue

            ratio = perturbed_prices[i] / original_close[i]
            new_close = float(perturbed_prices[i])

            new_open = None
            new_high = None
            new_low = None

            if open_col is not None:
                new_open = float(history_df.iloc[i][open_col]) * ratio
            if high_col is not None:
                new_high = float(history_df.iloc[i][high_col]) * ratio
            if low_col is not None:
                new_low = float(history_df.iloc[i][low_col]) * ratio

            # 确保 high >= max(open, close)
            if new_high is not None:
                candidates = [new_high, new_close]
                if new_open is not None:
                    candidates.append(new_open)
                new_high = max(candidates)

            # 确保 low <= min(open, close)
            if new_low is not None:
                candidates = [new_low, new_close]
                if new_open is not None:
                    candidates.append(new_open)
                new_low = min(candidates)

            # 确保 open 在 [low, high] 范围内
            if new_open is not None:
                low_bound = new_low if new_low is not None else new_close
                high_bound = new_high if new_high is not None else new_close
                new_open = max(low_bound, min(new_open, high_bound))

            perturbed_df.at[perturbed_df.index[i], close_col] = new_close
            if open_col is not None:
                perturbed_df.at[perturbed_df.index[i], open_col] = new_open
            if high_col is not None:
                perturbed_df.at[perturbed_df.index[i], high_col] = new_high
            if low_col is not None:
                perturbed_df.at[perturbed_df.index[i], low_col] = new_low

        return perturbed_df

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
        return (np.mean(returns) - risk_free) / std * np.sqrt(252)

    def _compute_sortino(self, returns: np.ndarray, risk_free: float = 0.0) -> float:
        if len(returns) == 0:
            return 0.0
        negative_returns = returns[returns < 0]
        if len(negative_returns) == 0:
            downside_std = 0.0
        else:
            downside_std = np.std(negative_returns, ddof=1)
        if downside_std == 0:
            return 0.0 if np.mean(returns) - risk_free <= 0 else float("inf")
        return (np.mean(returns) - risk_free) / downside_std * np.sqrt(252)

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
            "stress_scenarios": {},
        }

    def _run_stress_scenarios(
        self,
        analyzer,
        history_df: pd.DataFrame,
        original_close: np.ndarray,
        original_signal: str,
    ) -> dict:
        """运行历史压力场景，返回各场景独立结果。"""
        scenario_prices = self._generate_stress_scenarios(original_close)
        results = {}
        for name, prices in scenario_prices.items():
            results[name] = self._run_single_scenario(
                analyzer, history_df, prices, original_signal
            )
        return results

    def _generate_stress_scenarios(
        self, original_close: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """生成与现有接口兼容的压力场景价格序列。"""
        n = len(original_close)
        start_price = float(original_close[0])
        return {
            "2008_crash": self._scenario_2008_crash(start_price, n),
            "2015_volatility": self._scenario_2015_volatility(start_price, n),
            "2020_liquidity_crisis": self._scenario_2020_liquidity_crisis(
                start_price, n
            ),
        }

    def _run_single_scenario(
        self,
        analyzer,
        history_df: pd.DataFrame,
        scenario_prices: np.ndarray,
        original_signal: str,
    ) -> dict:
        """对单一场景计算信号与风险指标。"""
        perturbed_df = history_df.copy()
        perturbed_df["收盘"] = scenario_prices

        try:
            perturbed_indicators = self._calculate_core_indicators_only(perturbed_df)
        except Exception as e:
            stress_logger.debug(f"压力场景指标计算失败: {e}")
            return self._empty_scenario_result()

        new_signal = self._get_signal(analyzer, perturbed_df, perturbed_indicators)
        if new_signal is None:
            return self._empty_scenario_result()

        returns = np.diff(scenario_prices) / scenario_prices[:-1]
        max_dd = self._compute_max_drawdown(scenario_prices)
        final_return = scenario_prices[-1] / scenario_prices[0] - 1
        volatility = np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0.0
        sharpe = self._compute_sharpe(returns)
        sortino = self._compute_sortino(returns)
        calmar = self._compute_calmar(returns, max_dd)

        return {
            "signal": new_signal,
            "signal_flipped": self._signal_flipped(original_signal, new_signal),
            "final_return": round(final_return, 4),
            "max_drawdown": round(max_dd, 4),
            "volatility": round(volatility, 4),
            "sharpe": round(sharpe, 4),
            "sortino": round(sortino, 4),
            "calmar": round(calmar, 4),
        }

    def _empty_scenario_result(self) -> dict:
        return {
            "signal": "unknown",
            "signal_flipped": False,
            "final_return": 0.0,
            "max_drawdown": 0.0,
            "volatility": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "calmar": 0.0,
        }

    def _scenario_2008_crash(self, start_price: float, n: int) -> np.ndarray:
        """2008 年式急跌：连续大幅下跌伴随偶发极端暴跌。"""
        rng = np.random.default_rng(2008)
        returns = rng.normal(-0.03, 0.04, n - 1)
        crash_days = rng.choice(n - 1, size=max(1, (n - 1) // 10), replace=False)
        returns[crash_days] = rng.uniform(-0.15, -0.08, size=len(crash_days))
        return self._reconstruct_prices_from_start(start_price, returns)

    def _scenario_2015_volatility(
        self, start_price: float, n: int
    ) -> np.ndarray:
        """2015 年式波动：连续涨停/跌停交替，叠加微小扰动。"""
        rng = np.random.default_rng(2015)
        returns = np.empty(n - 1)
        returns[::2] = 0.10
        returns[1::2] = -0.10
        returns += rng.normal(0, 0.01, n - 1)
        return self._reconstruct_prices_from_start(start_price, returns)

    def _scenario_2020_liquidity_crisis(
        self, start_price: float, n: int
    ) -> np.ndarray:
        """2020 年式流动性危机：前半段急跌，后半段 V 型反转，高波动。"""
        rng = np.random.default_rng(2020)
        half = (n - 1) // 2
        returns1 = rng.normal(-0.04, 0.05, half)
        returns2 = rng.normal(0.035, 0.04, n - 1 - half)
        returns = np.concatenate([returns1, returns2])
        return self._reconstruct_prices_from_start(start_price, returns)

    def _reconstruct_prices_from_start(
        self, start_price: float, returns: np.ndarray
    ) -> np.ndarray:
        """由收益率序列和起始价格重构价格序列。"""
        prices = np.empty(len(returns) + 1)
        prices[0] = start_price
        for i in range(len(returns)):
            prices[i + 1] = prices[i] * (1 + returns[i])
        return prices
