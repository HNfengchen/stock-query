import sys
import os
import json
import copy
import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.technical_indicators import (
    calculate_macd,
    calculate_rsi,
    calculate_kdj,
    calculate_ma,
    calculate_boll,
    calculate_atr,
    calculate_obv,
    calculate_all_indicators,
    calculate_all_indicators_incremental,
)


def _generate_sample_data(n=120, seed=42):
    rng = np.random.RandomState(seed)
    base = 20.0
    closes = []
    highs = []
    lows = []
    volumes = []
    for i in range(n):
        change = rng.randn() * 0.5
        close = base + change
        high = close + abs(rng.randn()) * 0.3
        low = close - abs(rng.randn()) * 0.3
        vol = int(1000000 + rng.randn() * 200000)
        closes.append(round(close, 2))
        highs.append(round(high, 2))
        lows.append(round(low, 2))
        volumes.append(max(vol, 100000))
        base = close
    return closes, highs, lows, volumes


def _make_df(closes, highs, lows, volumes):
    return pd.DataFrame({
        "收盘": closes,
        "最高": highs,
        "最低": lows,
        "成交量": volumes,
    })


class TestMacdIncremental:
    def test_incremental_matches_full(self):
        closes, highs, lows, volumes = _generate_sample_data(120)
        full_result = calculate_macd(closes)
        state = full_result["state"]

        new_close = closes[-1] + 0.5
        extended_closes = closes + [new_close]

        full_extended = calculate_macd(extended_closes)
        incr_result = calculate_macd([new_close], prev_state=state)

        assert abs(full_extended["latest"]["DIF"] - incr_result["latest"]["DIF"]) < 1e-4
        assert abs(full_extended["latest"]["DEA"] - incr_result["latest"]["DEA"]) < 1e-4
        assert abs(full_extended["latest"]["MACD"] - incr_result["latest"]["MACD"]) < 1e-4

    def test_backward_compatible(self):
        closes, _, _, _ = _generate_sample_data(50)
        result_old = calculate_macd(closes)
        result_new = calculate_macd(closes, prev_state=None)
        assert result_old["latest"]["DIF"] == result_new["latest"]["DIF"]
        assert result_old["latest"]["DEA"] == result_new["latest"]["DEA"]

    def test_state_present(self):
        closes, _, _, _ = _generate_sample_data(50)
        result = calculate_macd(closes)
        assert "state" in result
        assert "prev_ema_fast" in result["state"]
        assert "prev_ema_slow" in result["state"]
        assert "prev_dea" in result["state"]

    def test_multiple_new_points(self):
        closes, _, _, _ = _generate_sample_data(120)
        full_result = calculate_macd(closes)
        state = full_result["state"]

        new_closes = [closes[-1] + 0.3, closes[-1] + 0.8]
        extended_closes = closes + new_closes

        full_extended = calculate_macd(extended_closes)
        incr_result = calculate_macd(new_closes, prev_state=state)

        assert abs(full_extended["latest"]["DIF"] - incr_result["latest"]["DIF"]) < 1e-4


class TestRsiIncremental:
    def test_incremental_matches_full(self):
        closes, _, _, _ = _generate_sample_data(120)
        full_result = calculate_rsi(closes)
        first_key = next(iter(full_result))
        state = full_result[first_key]["state"]

        new_close = closes[-1] + 1.0
        extended_closes = closes + [new_close]

        full_extended = calculate_rsi(extended_closes)
        incr_result = calculate_rsi([new_close], prev_state=state)

        for period in [6, 12, 24]:
            full_latest = full_extended.get(f"RSI({period})", {}).get("latest")
            incr_latest = incr_result.get(f"RSI({period})", {}).get("latest")
            if full_latest is not None and incr_latest is not None:
                assert abs(full_latest - incr_latest) < 1e-2

    def test_state_present(self):
        closes, _, _, _ = _generate_sample_data(120)
        result = calculate_rsi(closes)
        first_key = next(iter(result))
        assert "state" in result[first_key]
        state = result[first_key]["state"]
        assert "prev_close" in state
        assert "period_states" in state


class TestKdjIncremental:
    def test_incremental_matches_full(self):
        closes, highs, lows, _ = _generate_sample_data(120)
        full_result = calculate_kdj(highs, lows, closes)
        state = full_result["state"]

        new_close = closes[-1] + 0.5
        new_high = new_close + 0.3
        new_low = new_close - 0.3
        extended_closes = closes + [new_close]
        extended_highs = highs + [new_high]
        extended_lows = lows + [new_low]

        full_extended = calculate_kdj(extended_highs, extended_lows, extended_closes)
        incr_result = calculate_kdj([new_high], [new_low], [new_close], prev_state=state)

        assert abs(full_extended["latest"]["K"] - incr_result["latest"]["K"]) < 1e-2
        assert abs(full_extended["latest"]["D"] - incr_result["latest"]["D"]) < 1e-2
        assert abs(full_extended["latest"]["J"] - incr_result["latest"]["J"]) < 1e-2

    def test_state_present(self):
        closes, highs, lows, _ = _generate_sample_data(120)
        result = calculate_kdj(highs, lows, closes)
        assert "state" in result
        assert "prev_k" in result["state"]
        assert "prev_d" in result["state"]


class TestMaIncremental:
    def test_incremental_matches_full(self):
        closes, _, _, _ = _generate_sample_data(120)
        full_result = calculate_ma(closes)
        state = full_result["state"]

        new_close = closes[-1] + 0.5
        extended_closes = closes + [new_close]

        full_extended = calculate_ma(extended_closes)
        incr_result = calculate_ma([new_close], prev_state=state)

        for period in [5, 10, 20, 60]:
            full_latest = full_extended.get(f"MA{period}", {}).get("latest")
            incr_latest = incr_result.get(f"MA{period}", {}).get("latest")
            if full_latest is not None and incr_latest is not None:
                assert abs(full_latest - incr_latest) < 1e-2

    def test_state_present(self):
        closes, _, _, _ = _generate_sample_data(120)
        result = calculate_ma(closes)
        assert "state" in result
        assert "period_states" in result["state"]


class TestBollIncremental:
    def test_incremental_matches_full(self):
        closes, _, _, _ = _generate_sample_data(120)
        full_result = calculate_boll(closes)
        state = full_result["state"]

        new_close = closes[-1] + 0.5
        extended_closes = closes + [new_close]

        full_extended = calculate_boll(extended_closes)
        incr_result = calculate_boll([new_close], prev_state=state)

        assert abs(full_extended["latest"]["upper"] - incr_result["latest"]["upper"]) < 1e-2
        assert abs(full_extended["latest"]["middle"] - incr_result["latest"]["middle"]) < 1e-2
        assert abs(full_extended["latest"]["lower"] - incr_result["latest"]["lower"]) < 1e-2

    def test_state_present(self):
        closes, _, _, _ = _generate_sample_data(120)
        result = calculate_boll(closes)
        assert "state" in result
        assert "prev_closes" in result["state"]


class TestAtrIncremental:
    def test_incremental_matches_full(self):
        closes, highs, lows, _ = _generate_sample_data(120)
        full_result = calculate_atr(highs, lows, closes)
        state = full_result["state"]

        new_close = closes[-1] + 0.5
        new_high = new_close + 0.3
        new_low = new_close - 0.3
        extended_closes = closes + [new_close]
        extended_highs = highs + [new_high]
        extended_lows = lows + [new_low]

        full_extended = calculate_atr(extended_highs, extended_lows, extended_closes)
        incr_result = calculate_atr([new_high], [new_low], [new_close], prev_state=state)

        assert abs(full_extended["latest"] - incr_result["latest"]) < 1e-2

    def test_state_present(self):
        closes, highs, lows, _ = _generate_sample_data(120)
        result = calculate_atr(highs, lows, closes)
        assert "state" in result
        assert "prev_atr" in result["state"]
        assert "prev_close" in result["state"]


class TestObvIncremental:
    def test_incremental_matches_full(self):
        closes, _, _, volumes = _generate_sample_data(120)
        full_result = calculate_obv(closes, volumes)
        state = full_result["state"]

        new_close = closes[-1] + 0.5
        new_vol = 1500000
        extended_closes = closes + [new_close]
        extended_volumes = volumes + [new_vol]

        full_extended = calculate_obv(extended_closes, extended_volumes)
        incr_result = calculate_obv([new_close], [new_vol], prev_state=state)

        assert abs(full_extended["latest"] - incr_result["latest"]) < 1.0

    def test_state_present(self):
        closes, _, _, volumes = _generate_sample_data(120)
        result = calculate_obv(closes, volumes)
        assert "state" in result
        assert "prev_obv" in result["state"]
        assert "prev_close" in result["state"]


class TestCalculateAllIndicatorsIncremental:
    def test_incremental_matches_full(self):
        closes, highs, lows, volumes = _generate_sample_data(120)
        df = _make_df(closes, highs, lows, volumes)

        full_result = calculate_all_indicators_incremental(df)
        states = full_result["states"]

        new_close = closes[-1] + 0.5
        new_high = new_close + 0.3
        new_low = new_close - 0.3
        new_vol = 1500000

        new_df = _make_df([new_close], [new_high], [new_low], [new_vol])
        incr_result = calculate_all_indicators_incremental(new_df, prev_states=states)

        extended_df = _make_df(
            closes + [new_close],
            highs + [new_high],
            lows + [new_low],
            volumes + [new_vol],
        )
        full_extended = calculate_all_indicators_incremental(extended_df)

        assert abs(full_extended["MACD"]["latest"]["DIF"] - incr_result["MACD"]["latest"]["DIF"]) < 1e-4
        assert abs(full_extended["ATR"]["latest"] - incr_result["ATR"]["latest"]) < 1e-2
        assert abs(full_extended["BOLL"]["latest"]["middle"] - incr_result["BOLL"]["latest"]["middle"]) < 1e-2

    def test_no_prev_states_returns_states(self):
        closes, highs, lows, volumes = _generate_sample_data(120)
        df = _make_df(closes, highs, lows, volumes)
        result = calculate_all_indicators_incremental(df)
        assert "states" in result
        assert "MACD" in result["states"]
        assert "RSI" in result["states"]
        assert "KDJ" in result["states"]
        assert "MA" in result["states"]
        assert "BOLL" in result["states"]
        assert "ATR" in result["states"]

    def test_fallback_no_states(self):
        closes, highs, lows, volumes = _generate_sample_data(120)
        df = _make_df(closes, highs, lows, volumes)

        result_incremental = calculate_all_indicators_incremental(df)
        result_full = calculate_all_indicators(df)

        assert abs(result_incremental["MACD"]["latest"]["DIF"] - result_full["MACD"]["latest"]["DIF"]) < 1e-4
        assert abs(result_incremental["ATR"]["latest"] - result_full["ATR"]["latest"]) < 1e-2


class TestStateSerialization:
    def test_json_roundtrip(self):
        closes, highs, lows, volumes = _generate_sample_data(120)
        df = _make_df(closes, highs, lows, volumes)
        result = calculate_all_indicators_incremental(df)
        states = result["states"]

        json_str = json.dumps(states, ensure_ascii=False)
        loaded = json.loads(json_str)

        for key in ["MACD", "KDJ", "BOLL", "ATR", "MA", "OBV"]:
            if key in states:
                assert key in loaded

        macd_state = loaded["MACD"]
        assert "prev_ema_fast" in macd_state
        assert isinstance(macd_state["prev_ema_fast"], float)

        kdj_state = loaded["KDJ"]
        assert "prev_k" in kdj_state
        assert "recent_highs" in kdj_state
        assert isinstance(kdj_state["recent_highs"], list)

    def test_incremental_after_json_roundtrip(self):
        closes, highs, lows, volumes = _generate_sample_data(120)
        df = _make_df(closes, highs, lows, volumes)
        result = calculate_all_indicators_incremental(df)
        states = result["states"]

        json_str = json.dumps(states, ensure_ascii=False)
        loaded_states = json.loads(json_str)

        new_close = closes[-1] + 0.5
        new_high = new_close + 0.3
        new_low = new_close - 0.3
        new_vol = 1500000

        new_df = _make_df([new_close], [new_high], [new_low], [new_vol])
        incr_result = calculate_all_indicators_incremental(new_df, prev_states=loaded_states)

        assert incr_result["MACD"]["latest"]["DIF"] is not None
        assert incr_result["KDJ"]["latest"]["K"] is not None
        assert incr_result["ATR"]["latest"] is not None

    def test_deep_copy_independence(self):
        closes, _, _, _ = _generate_sample_data(120)
        full_result = calculate_macd(closes)
        state = full_result["state"]

        state_copy = copy.deepcopy(state)
        new_close = closes[-1] + 0.5
        calculate_macd([new_close], prev_state=state)

        assert state["prev_ema_fast"] != state_copy["prev_ema_fast"] or new_close == closes[-1]


class TestEdgeCases:
    def test_insufficient_data_returns_empty_state(self):
        result = calculate_macd([10, 20, 30])
        assert result["state"] == {}
        assert result["latest"]["DIF"] is None

    def test_incremental_with_nan(self):
        closes, _, _, _ = _generate_sample_data(120)
        full_result = calculate_macd(closes)
        state = full_result["state"]
        result = calculate_macd([float("nan"), 25.0], prev_state=state)
        assert result["latest"]["DIF"] is not None

    def test_rsi_incremental_preserves_period_states(self):
        closes, _, _, _ = _generate_sample_data(120)
        full_result = calculate_rsi(closes)
        first_key = next(iter(full_result))
        state = full_result[first_key]["state"]

        new_close = closes[-1] + 1.0
        incr_result = calculate_rsi([new_close], prev_state=state)
        first_key_incr = next(iter(incr_result))
        new_state = incr_result[first_key_incr]["state"]

        assert "period_states" in new_state
        for period in ["6", "12", "24"]:
            assert period in new_state["period_states"]
