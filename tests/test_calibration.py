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


def test_single_param_scan_returns_sensitivity():
    """验证单参数扫描返回 sensitivity 结构"""
    from scripts.core.calibration import ValidationCalibrator

    cb = ValidationCalibrator({}, [])
    scan_results = cb._scan_single_param(
        param_name="technical_bullish",
        param_path=["score_thresholds", "technical_bullish"],
        base_overrides={},
        current_value=0.65,
        scan_values=[0.5, 0.65, 0.8],
        evaluate_fn=lambda cfg: {"accuracy": 0.5, "trend_accuracy": 0.5, "consistency": 0.5},
    )
    assert "values" in scan_results
    assert "scores" in scan_results
    assert len(scan_results["values"]) == 3
    assert len(scan_results["scores"]) == 3
    assert scan_results["best_value"] in (0.5, 0.65, 0.8)


def test_calibration_report_returns_full_structure():
    """验证校准报告包含所有必要字段"""
    from scripts.core.calibration import ValidationCalibrator

    cb = ValidationCalibrator({}, [])
    report = cb.run(
        evaluate_fn=lambda cfg: {"accuracy": 0.5, "trend_accuracy": 0.5, "consistency": 0.5},
        dry_run=True,
    )
    assert "target" in report
    assert "baseline" in report
    assert "calibrated" in report
    assert "optimal_params" in report
    assert "param_sensitivity" in report
    assert "improvement" in report
    assert report["target"] == "validation"
    assert report["baseline"]["composite_score"] >= 0


def test_calibration_dry_run_does_not_modify_config(tmp_path):
    """验证 dry_run=True 不修改 config"""
    import yaml
    from scripts.core.calibration import ValidationCalibrator

    cfg = {"analyzer": {"validation": {}}}
    cfg_path = tmp_path / "test_config.yaml"
    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f)

    cb = ValidationCalibrator(str(cfg_path), [])
    report = cb.run(
        evaluate_fn=lambda cfg: {"accuracy": 0.5, "trend_accuracy": 0.5, "consistency": 0.5},
        dry_run=True,
    )

    with open(cfg_path) as f:
        after = yaml.safe_load(f)
    assert after == cfg  # 未修改


def test_calibration_baseline_matches_current():
    """验证以当前值为最优时, baseline == calibrated"""
    from scripts.core.calibration import ValidationCalibrator

    cb = ValidationCalibrator({}, [])
    # 所有扫描值都返回相同结果：最优等于当前值
    report = cb.run(
        evaluate_fn=lambda cfg: {"accuracy": 0.6, "trend_accuracy": 0.6, "consistency": 0.5},
        dry_run=True,
    )
    # composite_score 基线应与校准后一致
    assert abs(report["improvement"]["composite_score_delta"]) < 0.001
