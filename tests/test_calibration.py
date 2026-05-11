"""校准机制测试"""
import pytest


def test_evaluate_config_returns_correct_structure():
    """验证评估函数返回正确的指标结构"""
    from scripts.core.calibration import evaluate_validation_config

    cfg = {"analyzer": {"validation": {}}}
    result = evaluate_validation_config(
        config=cfg,
        stock_codes=[],
        lookback_days=60,
    )
    assert "accuracy" in result
    assert "trend_accuracy" in result
    assert "consistency" in result
    assert "total_predictions" in result
    assert 0 <= result["accuracy"] <= 1
    assert 0 <= result["trend_accuracy"] <= 1
    assert 0 <= result["consistency"] <= 1
