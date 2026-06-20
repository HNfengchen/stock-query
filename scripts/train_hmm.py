"""
HMM市场状态识别模型训练脚本
支持为个股、自选股列表或全局指数训练 GaussianHMM
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import yaml

from scripts.core.regime_detector import HMMRegimeDetector, HMMLEARN_AVAILABLE
from scripts.logger import get_logger

train_logger = get_logger("train_hmm")

DEFAULT_WATCHLIST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "watchlist.json"
)

DEFAULT_TRAINING_DAYS = 252


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_stock_codes_from_watchlist(watchlist_path: str) -> list:
    """从 watchlist.json 读取股票代码列表"""
    if not os.path.exists(watchlist_path):
        train_logger.warning(f"自选股列表不存在: {watchlist_path}")
        return []
    try:
        with open(watchlist_path, "r", encoding="utf-8") as f:
            watchlist = json.load(f)
        codes = [item["stock_code"] for item in watchlist if "stock_code" in item]
        train_logger.info(f"从自选股列表读取 {len(codes)} 只股票: {watchlist_path}")
        return codes
    except Exception as e:
        train_logger.error(f"读取自选股列表失败: {e}")
        return []


def fetch_training_data(index_code: str) -> dict:
    train_logger.info(f"获取指数数据: {index_code}")

    try:
        import efinance as ef

        # efinance 指数代码不加交易所前缀，直接用6位代码
        df = ef.stock.get_quote_history(index_code)
        if df is not None and not df.empty:
            train_logger.info(f"efinance获取数据成功: {len(df)}条")
            return _process_dataframe(df)
    except Exception as e:
        train_logger.warning(f"efinance获取失败: {e}")

    try:
        from scripts.core.data_fetcher import _baostock_lock
        import baostock as bs

        with _baostock_lock:
            lg = bs.login()
            try:
                prefix = "sh" if index_code.startswith(("000", "9")) else "sz"
                bs_code = f"{prefix}.{index_code}"
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,close,volume",
                    start_date="2020-01-01",
                    frequency="d",
                )
                rows = []
                while rs.error_code == "0" and rs.next():
                    rows.append(rs.get_row_data())
            finally:
                bs.logout()
        if rows:
            import pandas as pd

            df = pd.DataFrame(rows, columns=["日期", "收盘", "成交量"])
            df["收盘"] = df["收盘"].astype(float)
            df["成交量"] = df["成交量"].astype(float)
            train_logger.info(f"baostock获取数据成功: {len(df)}条")
            return _process_dataframe(df)
    except Exception as e:
        train_logger.warning(f"baostock获取失败: {e}")

    return {}


def _process_dataframe(df) -> dict:
    close_col = "收盘" if "收盘" in df.columns else "close"
    volume_col = "成交量" if "成交量" in df.columns else "volume"

    if close_col not in df.columns:
        return {}

    closes = df[close_col].values.astype(np.float64)

    returns = np.diff(closes) / closes[:-1]

    window = 20
    vols = np.zeros_like(returns)
    for i in range(len(returns)):
        start = max(0, i - window + 1)
        vols[i] = np.std(returns[start:i + 1]) if i > 0 else 0.0

    if volume_col in df.columns:
        volumes = df[volume_col].values.astype(np.float64)
        volume_changes = np.diff(volumes) / (volumes[:-1] + 1e-10)
    else:
        volume_changes = np.zeros_like(returns)

    return {
        "returns": returns,
        "volatilities": vols,
        "volume_changes": volume_changes,
        "n_samples": len(returns),
    }


def fetch_stock_training_data(stock_code: str, config: dict, days: int = DEFAULT_TRAINING_DAYS) -> dict:
    """获取个股历史数据并转换为 HMM 训练所需格式。"""
    train_logger.info(f"[{stock_code}] 获取个股训练数据: days={days}")

    try:
        from scripts.core.data_fetcher import DataFetcher

        fetcher = DataFetcher(config)
        history_df = fetcher.fetch_history_data(stock_code, days=days)
        if history_df is None or history_df.empty:
            train_logger.warning(f"[{stock_code}] 获取历史数据为空")
            return {}
        return _process_dataframe(history_df)
    except Exception as e:
        train_logger.warning(f"[{stock_code}] 获取个股训练数据失败: {e}")
        return {}


def _train_hmm(detector: HMMRegimeDetector, data: dict) -> dict:
    return detector.train(data["returns"], data["volatilities"], data["volume_changes"])


def train_single_stock(stock_code: str, model_path: str, n_components: int, config: dict, days: int) -> dict:
    """训练单只个股的 HMM 模型。"""
    train_logger.info(f"[{stock_code}] 开始训练个股HMM")

    data = fetch_stock_training_data(stock_code, config, days=days)
    if not data:
        train_logger.warning(f"[{stock_code}] 训练失败: 无法获取训练数据")
        return {"stock_code": stock_code, "status": "failed", "reason": "无法获取训练数据"}

    min_required = n_components * 10
    if data["n_samples"] < min_required:
        train_logger.warning(f"[{stock_code}] 训练失败: 数据不足 {data['n_samples']} < {min_required}")
        return {
            "stock_code": stock_code,
            "status": "failed",
            "reason": f"insufficient data: {data['n_samples']} < {min_required}",
        }

    detector = HMMRegimeDetector(n_components=n_components, config=config.get("hmm", {}))
    result = _train_hmm(detector, data)

    if not result.get("converged"):
        train_logger.warning(f"[{stock_code}] 模型未收敛 (n_iter={result.get('n_iter')})")

    train_logger.info(f"[{stock_code}] 状态映射: {result.get('state_mapping')}")

    saved = detector.save(model_path)
    if not saved:
        train_logger.error(f"[{stock_code}] 训练失败: 模型保存失败")
        return {"stock_code": stock_code, "status": "failed", "reason": "模型保存失败"}

    train_logger.info(f"[{stock_code}] HMM训练完成，模型已保存: {model_path}")
    return {"stock_code": stock_code, "status": "success", "state_mapping": result.get("state_mapping")}


def train_global_hmm(model_path: str, index_code: str, n_components: int, config: dict) -> dict:
    """训练全局（指数）HMM 模型。"""
    train_logger.info(f"开始训练全局HMM: index={index_code}")

    data = fetch_training_data(index_code)
    if not data:
        train_logger.error("无法获取训练数据")
        return {"status": "failed", "reason": "无法获取训练数据"}

    train_logger.info(f"训练数据: {data['n_samples']}条样本")

    detector = HMMRegimeDetector(n_components=n_components, config=config.get("hmm", {}))
    result = _train_hmm(detector, data)

    if not result.get("converged"):
        train_logger.warning(f"模型未收敛 (n_iter={result.get('n_iter')})")

    train_logger.info(f"状态映射: {result.get('state_mapping')}")

    transmat = detector.get_transition_probabilities()
    if transmat is not None:
        train_logger.info("转移矩阵:")
        for i, row in enumerate(transmat):
            state_name = result.get("state_mapping", {}).get(i, f"状态{i}")
            train_logger.info(f"  {state_name}: {row}")

    saved = detector.save(model_path)
    if not saved:
        train_logger.error("模型保存失败")
        return {"status": "failed", "reason": "模型保存失败"}

    train_logger.info(f"全局模型已保存: {model_path}")
    return {"status": "success", "state_mapping": result.get("state_mapping")}


def main():
    parser = argparse.ArgumentParser(description="训练HMM市场状态识别模型")
    parser.add_argument("--config", type=str, default="config/config.yaml", help="配置文件路径")
    parser.add_argument("--n-components", type=int, default=None, help="隐状态数量")
    parser.add_argument("--model-path", type=str, default=None, help="模型保存路径")
    parser.add_argument("--index", type=str, default=None, help="训练用指数代码")
    parser.add_argument("--stock-code", type=str, default=None, help="个股代码，训练该股HMM")
    parser.add_argument(
        "--all-watchlist",
        type=str,
        nargs="?",
        const=DEFAULT_WATCHLIST_PATH,
        default=None,
        help="为自选股列表训练HMM（默认: data/watchlist.json）",
    )
    parser.add_argument("--skip-existing", action="store_true", help="跳过已有个股HMM模型")
    parser.add_argument("--days", type=int, default=None, help="个股训练数据天数")
    args = parser.parse_args()

    if not HMMLEARN_AVAILABLE:
        train_logger.error("hmmlearn未安装，请执行: pip install hmmlearn")
        sys.exit(1)

    config = load_config(args.config)
    hmm_config = config.get("hmm", {})

    n_components = args.n_components or hmm_config.get("n_components", 4)
    days = args.days or hmm_config.get("training_days", DEFAULT_TRAINING_DAYS)

    if args.stock_code:
        model_path = args.model_path or f"models/hmm_{args.stock_code}.pkl"
        result = train_single_stock(args.stock_code, model_path, n_components, config, days)
        sys.exit(0 if result["status"] == "success" else 1)

    if args.all_watchlist:
        stock_codes = load_stock_codes_from_watchlist(args.all_watchlist)
        if not stock_codes:
            train_logger.error("自选股列表为空")
            sys.exit(1)

        train_logger.info(f"开始批量训练自选股HMM: count={len(stock_codes)}")
        results = []
        for code in stock_codes:
            model_path = f"models/hmm_{code}.pkl"
            if args.skip_existing and os.path.exists(model_path):
                train_logger.info(f"[{code}] 个股HMM已存在，跳过")
                results.append({"stock_code": code, "status": "skipped"})
                continue
            result = train_single_stock(code, model_path, n_components, config, days)
            results.append(result)

        success_count = sum(1 for r in results if r.get("status") == "success")
        skipped_count = sum(1 for r in results if r.get("status") == "skipped")
        failed_count = len(results) - success_count - skipped_count

        print("\n" + "=" * 60)
        print("个股HMM训练结果汇总:")
        print("=" * 60)
        for r in results:
            status = r.get("status", "unknown")
            code = r.get("stock_code", "unknown")
            if status == "success":
                print(f"  {code}: 成功 | mapping={r.get('state_mapping')}")
            elif status == "skipped":
                print(f"  {code}: 跳过")
            else:
                print(f"  {code}: {status} | reason={r.get('reason', 'unknown')}")
        print(f"\n成功: {success_count}, 跳过: {skipped_count}, 失败: {failed_count}, 总计: {len(results)}")

        sys.exit(0 if failed_count == 0 else 1)

    # 默认：训练全局 HMM
    model_path = args.model_path or hmm_config.get("model_path", "models/hmm_regime.pkl")
    index_code = args.index or hmm_config.get("training_index", "000300")

    train_logger.info(f"配置: n_components={n_components}, model_path={model_path}, index={index_code}")

    result = train_global_hmm(model_path, index_code, n_components, config)
    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
