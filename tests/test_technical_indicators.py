from scripts.technical_indicators import calculate_volume_ratio


def test_volume_ratio_uses_previous_n_days_as_baseline():
    result = calculate_volume_ratio([100, 100, 100, 100, 100, 300], n=5)

    assert result["latest"] == 3.0
    assert result["signal"] == "巨量"
