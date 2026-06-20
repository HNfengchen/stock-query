import sys
import os
import math
from typing import Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.logger import get_logger

backtest_logger = get_logger("backtest")

TREND_STRONG_UP = "strong_up"
TREND_UP = "up"
TREND_NEUTRAL = "neutral"
TREND_DOWN = "down"
TREND_STRONG_DOWN = "strong_down"

# 从配置读取趋势阈值，保留硬编码默认值以防配置缺失
try:
    from scripts.core.config_loader import load_config

    _BACKTEST_CFG = load_config().get("backtest", {})
    _TREND_CFG = _BACKTEST_CFG.get("trend_thresholds", {})
    _STRONG_THRESHOLD = _TREND_CFG.get("strong", 0.03)
    _NORMAL_THRESHOLD = _TREND_CFG.get("normal", 0.01)
except Exception:
    _STRONG_THRESHOLD = 0.03
    _NORMAL_THRESHOLD = 0.01

# 从配置读取交易成本，保留硬编码默认值以防配置缺失
try:
    _COST_CFG = _BACKTEST_CFG.get("cost", {})
    _DEFAULT_BUY_COMMISSION = _COST_CFG.get("buy_commission", 0.0003)
    _DEFAULT_SELL_COMMISSION = _COST_CFG.get("sell_commission", 0.0003)
    _DEFAULT_STAMP_TAX = _COST_CFG.get("stamp_tax", 0.001)
    _DEFAULT_SLIPPAGE = _COST_CFG.get("slippage", 0.001)
except Exception:
    _DEFAULT_BUY_COMMISSION = 0.0003
    _DEFAULT_SELL_COMMISSION = 0.0003
    _DEFAULT_STAMP_TAX = 0.001
    _DEFAULT_SLIPPAGE = 0.001


def _get_trend_from_change(change_pct: float, is_ratio: bool = False) -> str:
    if isinstance(change_pct, str):
        try:
            change_pct = float(change_pct)
        except (TypeError, ValueError):
            return TREND_NEUTRAL
    if not math.isfinite(change_pct):
        return TREND_NEUTRAL
    if is_ratio:
        ratio = change_pct
    else:
        ratio = change_pct / 100.0
    if ratio > _STRONG_THRESHOLD:
        return TREND_STRONG_UP
    if ratio > _NORMAL_THRESHOLD:
        return TREND_UP
    if ratio < -_STRONG_THRESHOLD:
        return TREND_STRONG_DOWN
    if ratio < -_NORMAL_THRESHOLD:
        return TREND_DOWN
    return TREND_NEUTRAL


def _trend_direction(trend: str) -> int:
    if trend in (TREND_STRONG_UP, TREND_UP):
        return 1
    if trend in (TREND_STRONG_DOWN, TREND_DOWN):
        return -1
    return 0


def _is_trend_consistent(pred_trend: str, actual_trend: str) -> bool:
    if pred_trend == actual_trend:
        return True
    pred_dir = _trend_direction(pred_trend)
    actual_dir = _trend_direction(actual_trend)
    if pred_dir == 0 or actual_dir == 0:
        return pred_dir == actual_dir
    return pred_dir == actual_dir


class TransactionCostModel:
    """交易成本模型：佣金、印花税、滑点。"""

    def __init__(
        self,
        buy_commission: float = None,
        sell_commission: float = None,
        stamp_tax: float = None,
        slippage: float = None,
    ):
        self.buy_commission = (
            buy_commission if buy_commission is not None else _DEFAULT_BUY_COMMISSION
        )
        self.sell_commission = (
            sell_commission if sell_commission is not None else _DEFAULT_SELL_COMMISSION
        )
        self.stamp_tax = stamp_tax if stamp_tax is not None else _DEFAULT_STAMP_TAX
        self.slippage = slippage if slippage is not None else _DEFAULT_SLIPPAGE

    def buy_fill_price(self, signal_price: float) -> float:
        """买入实际成交价 = 信号价 × (1 + 滑点)。"""
        return signal_price * (1 + self.slippage)

    def sell_fill_price(self, signal_price: float) -> float:
        """卖出实际成交价 = 信号价 × (1 - 滑点)。"""
        return signal_price * (1 - self.slippage)

    def buy_cost(self, amount: float) -> float:
        """买入成本 = 买入成交金额 × 买入佣金。"""
        return amount * self.buy_commission

    def sell_cost(self, amount: float) -> float:
        """卖出成本 = 卖出成交金额 × (卖出佣金 + 印花税)。"""
        return amount * (self.sell_commission + self.stamp_tax)


def _safe_float_value(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        num = float(value)
        if not math.isfinite(num):
            return default
        return num
    except (TypeError, ValueError):
        return default


def _simulate_trade_return(
    entry_price,
    exit_price,
    cost_model: TransactionCostModel = None,
    notional: float = 10000.0,
) -> Dict:
    """对单笔交易分别计算不含成本与含成本的收益率。

    买入成交价 = 信号价 × (1 + slippage)
    卖出成交价 = 信号价 × (1 - slippage)
    买入成本 = 买入成交金额 × buy_commission
    卖出成本 = 卖出成交金额 × (sell_commission + stamp_tax)
    """
    cost_model = cost_model or TransactionCostModel()
    entry = _safe_float_value(entry_price)
    exit_ = _safe_float_value(exit_price)
    if entry <= 0 or exit_ <= 0 or notional <= 0:
        return {"return_without_cost": 0.0, "return_with_cost": 0.0}

    buy_price = cost_model.buy_fill_price(entry)
    shares = notional / buy_price
    buy_fee = cost_model.buy_cost(notional)
    cash_out = notional + buy_fee

    sell_price = cost_model.sell_fill_price(exit_)
    sell_notional = shares * sell_price
    sell_fee = cost_model.sell_cost(sell_notional)
    cash_in = sell_notional - sell_fee

    return_without_cost = (exit_ - entry) / entry
    return_with_cost = (cash_in - cash_out) / cash_out

    return {
        "return_without_cost": return_without_cost,
        "return_with_cost": return_with_cost,
    }


def run_simple_backtest(
    df,
    signal_col: str = "predicted_direction",
    price_col: str = "current_close",
    next_price_col: str = "close",
    cost_model: TransactionCostModel = None,
    bullish_signals=None,
) -> Dict:
    """根据信号列进行简单回测，返回含/不含交易成本的累计收益。

    仅对看涨信号做多，其余情况持币，保持原有验证逻辑不变。
    """
    cost_model = cost_model or TransactionCostModel()
    if df is None or len(df) == 0:
        return {
            "return_without_cost": 0.0,
            "return_with_cost": 0.0,
            "trades": [],
        }

    if bullish_signals is None:
        bullish_signals = {TREND_STRONG_UP, TREND_UP}

    equity_no_cost = 1.0
    equity_with_cost = 1.0
    trades = []

    for _, row in df.iterrows():
        signal = row.get(signal_col)
        entry = _safe_float_value(row.get(price_col))
        exit_ = _safe_float_value(row.get(next_price_col))
        if entry <= 0 or exit_ <= 0:
            trades.append({"return_without_cost": 0.0, "return_with_cost": 0.0})
            continue

        if signal in bullish_signals:
            trade = _simulate_trade_return(entry, exit_, cost_model)
            equity_no_cost *= 1 + trade["return_without_cost"]
            equity_with_cost *= 1 + trade["return_with_cost"]
            trades.append(trade)
        else:
            trades.append({"return_without_cost": 0.0, "return_with_cost": 0.0})

    return {
        "return_without_cost": equity_no_cost - 1,
        "return_with_cost": equity_with_cost - 1,
        "trades": trades,
    }
