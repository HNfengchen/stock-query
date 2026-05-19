"""
LightGBM模型训练CLI脚本
支持股票池批量训练、dry-run模式
"""

import argparse
import json
import os
import sys

import yaml

from scripts.logger import get_logger

train_logger = get_logger("train_model")


def load_config(config_path: str = "config/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def train_stock(stock_code: str, config: dict, model_dir: str, dry_run: bool = False) -> dict:
    from scripts.core.ml_model import LightGBMPredictor, build_feature_matrix
    from scripts.database import StockDataManager

    db_manager = StockDataManager(stock_code)

    X, y, feature_names, dates = build_feature_matrix(db_manager, stock_code)

    if X.size == 0:
        train_logger.warning(f"[{stock_code}] 特征矩阵为空，跳过")
        return {"stock_code": stock_code, "status": "skipped", "reason": "insufficient data"}

    min_days = config.get("ml_model", {}).get("min_training_days", 60)
    if X.shape[0] < min_days:
        train_logger.warning(f"[{stock_code}] 数据不足: {X.shape[0]} < {min_days}")
        return {"stock_code": stock_code, "status": "skipped", "reason": f"insufficient data: {X.shape[0]} < {min_days}"}

    stats = {
        "stock_code": stock_code,
        "n_samples": X.shape[0],
        "n_features": X.shape[1],
        "feature_names": feature_names[:10],
        "date_range": f"{dates[0]} ~ {dates[-1]}" if dates else "N/A",
        "return_mean": float(y["next_day_return"].mean()),
        "return_std": float(y["next_day_return"].std()),
        "direction_ratio": float(y["direction"].mean()),
        "volatility_mean": float(y["volatility"].mean()),
    }

    if dry_run:
        train_logger.info(f"[{stock_code}] Dry-run: {json.dumps(stats, ensure_ascii=False, default=str)}")
        return {"stock_code": stock_code, "status": "dry_run", "stats": stats}

    predictor = LightGBMPredictor(config)
    predictor._feature_names = feature_names

    metrics = predictor.train(X, y)

    if "error" in metrics:
        train_logger.warning(f"[{stock_code}] 训练失败: {metrics['error']}")
        return {"stock_code": stock_code, "status": "failed", "reason": metrics["error"]}

    stock_model_dir = os.path.join(model_dir, stock_code)
    predictor.save(stock_model_dir)

    try:
        from scripts.database import save_model_record
        save_model_record(stock_code, stock_model_dir, metrics, predictor.hyperparams)
    except Exception as e:
        train_logger.warning(f"[{stock_code}] 保存模型记录失败: {e}")

    train_logger.info(f"[{stock_code}] 训练完成: {json.dumps(metrics, ensure_ascii=False, default=str)}")

    return {"stock_code": stock_code, "status": "success", "metrics": metrics, "model_dir": stock_model_dir}


def main():
    parser = argparse.ArgumentParser(description="LightGBM模型训练")
    parser.add_argument("--stock-pool", type=str, default="",
                        help="股票代码，逗号分隔 (e.g. 000001,600519)")
    parser.add_argument("--model-dir", type=str, default=None,
                        help="模型保存目录")
    parser.add_argument("--alpha", type=float, default=None,
                        help="混合预测alpha值")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅显示数据统计，不训练")
    parser.add_argument("--config", type=str, default="config/config.yaml",
                        help="配置文件路径")

    args = parser.parse_args()

    config = load_config(args.config)

    ml_config = config.get("ml_model", {})
    model_dir = args.model_dir or ml_config.get("model_dir", "models/")
    alpha = args.alpha if args.alpha is not None else ml_config.get("alpha", 0.5)

    if args.stock_pool:
        stock_codes = [code.strip() for code in args.stock_pool.split(",") if code.strip()]
    else:
        train_logger.error("请通过 --stock-pool 指定股票代码")
        sys.exit(1)

    train_logger.info(f"开始训练: stocks={stock_codes}, model_dir={model_dir}, alpha={alpha}, dry_run={args.dry_run}")

    results = []
    for stock_code in stock_codes:
        try:
            result = train_stock(stock_code, config, model_dir, dry_run=args.dry_run)
            results.append(result)
        except Exception as e:
            train_logger.error(f"[{stock_code}] 训练异常: {e}")
            results.append({"stock_code": stock_code, "status": "error", "reason": str(e)})

    print("\n" + "=" * 60)
    print("训练结果汇总:")
    print("=" * 60)
    for r in results:
        status = r.get("status", "unknown")
        stock = r.get("stock_code", "unknown")
        if status == "success":
            metrics = r.get("metrics", {})
            print(f"  {stock}: 成功 | samples={metrics.get('n_samples', 'N/A')} | "
                  f"return_val_loss={metrics.get('return_val_loss', 'N/A'):.6f} | "
                  f"direction_val_acc={metrics.get('direction_val_acc', 'N/A'):.3f}")
        elif status == "dry_run":
            stats = r.get("stats", {})
            print(f"  {stock}: Dry-run | samples={stats.get('n_samples', 'N/A')} | "
                  f"features={stats.get('n_features', 'N/A')}")
        else:
            reason = r.get("reason", "unknown")
            print(f"  {stock}: {status} | reason={reason}")

    success_count = sum(1 for r in results if r.get("status") == "success")
    print(f"\n成功: {success_count}/{len(results)}")


if __name__ == "__main__":
    main()
