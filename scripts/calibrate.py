#!/usr/bin/env python3
"""交叉验证阈值校准 CLI"""

import argparse
import sys

from scripts.core.calibration import ValidationCalibrator


def main():
    parser = argparse.ArgumentParser(description="校准交叉验证阈值参数")
    parser.add_argument(
        "--target", default="validation", choices=["validation"],
        help="校准目标（当前仅支持 validation）"
    )
    parser.add_argument(
        "--stock-pool", type=str, default="000001,000002,000333,600519,601012",
        help="用于校准的股票池（逗号分隔）"
    )
    parser.add_argument(
        "--lookback-days", type=int, default=120,
        help="回测窗口天数"
    )
    parser.add_argument(
        "--config", type=str, default="config/config.yaml",
        help="配置文件路径"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅输出报告，不修改配置文件"
    )

    args = parser.parse_args()
    stock_codes = [s.strip() for s in args.stock_pool.split(",") if s.strip()]

    calibrator = ValidationCalibrator(
        config_path_or_dict=args.config,
        stock_codes=stock_codes,
        lookback_days=args.lookback_days,
    )

    print(f"开始校准 validation 阈值...")
    print(f"股票池: {stock_codes}")
    print(f"回测天数: {args.lookback_days}")
    print(f"配置路径: {args.config}")
    if args.dry_run:
        print("模式: 仅预览 (dry-run)")
    print()

    report = calibrator.run(dry_run=args.dry_run)

    print("=" * 60)
    print("校准报告")
    print("=" * 60)

    print(f"\n基线 composite_score: {report['baseline']['composite_score']:.4f}")
    print(f"校准后 composite_score: {report['calibrated']['composite_score']:.4f}")
    delta = report['improvement']['composite_score_delta']
    print(f"改善: {delta:+.4f} ({'↑' if delta > 0 else '↓' if delta < 0 else '='})")

    print(f"\n最优参数:")
    for param, val in report["optimal_params"].items():
        print(f"  {param}: {val}")

    print(f"\n参数敏感度:")
    for param, info in report["param_sensitivity"].items():
        improvement = info.get("improvement", 0)
        print(f"  {param}: 敏感度={info['sensitivity']}, 最优={info['best_value']}, 改善={improvement:+.4f}")

    if args.dry_run:
        print("\n(dry-run 模式，未修改配置文件)")
    else:
        print(f"\n已更新配置文件: {args.config}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
