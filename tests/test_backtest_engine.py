from scripts.core.backtest import _get_trend_from_change, _is_trend_consistent, _trend_direction


def test_get_trend_strong_up():
    assert _get_trend_from_change(5) == "strong_up"
    assert _get_trend_from_change(3.5) == "strong_up"
    assert _get_trend_from_change(0.035, is_ratio=True) == "strong_up"


def test_get_trend_up():
    assert _get_trend_from_change(2) == "up"
    assert _get_trend_from_change(1.5) == "up"
    assert _get_trend_from_change(0.015, is_ratio=True) == "up"


def test_get_trend_neutral():
    assert _get_trend_from_change(0) == "neutral"
    assert _get_trend_from_change(0.5) == "neutral"
    assert _get_trend_from_change(-0.5) == "neutral"
    assert _get_trend_from_change(0.008, is_ratio=True) == "neutral"
    assert _get_trend_from_change(-0.008, is_ratio=True) == "neutral"


def test_get_trend_down():
    assert _get_trend_from_change(-2) == "down"
    assert _get_trend_from_change(-1.5) == "down"
    assert _get_trend_from_change(-0.015, is_ratio=True) == "down"


def test_get_trend_strong_down():
    assert _get_trend_from_change(-5) == "strong_down"
    assert _get_trend_from_change(-3.5) == "strong_down"
    assert _get_trend_from_change(-0.035, is_ratio=True) == "strong_down"


def test_trend_direction():
    assert _trend_direction("strong_up") == 1
    assert _trend_direction("up") == 1
    assert _trend_direction("neutral") == 0
    assert _trend_direction("down") == -1
    assert _trend_direction("strong_down") == -1


def test_is_trend_consistent():
    assert _is_trend_consistent("up", "up") is True
    assert _is_trend_consistent("up", "strong_up") is True
    assert _is_trend_consistent("strong_up", "up") is True
    assert _is_trend_consistent("down", "strong_down") is True
    assert _is_trend_consistent("up", "down") is False
    assert _is_trend_consistent("up", "neutral") is False
    assert _is_trend_consistent("neutral", "neutral") is True
    assert _is_trend_consistent("neutral", "up") is False
