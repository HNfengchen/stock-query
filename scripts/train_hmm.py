"""
HMM市场状态识别模型训练脚本
使用沪深300历史数据训练GaussianHMM，保存模型供分析时使用
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import yaml

from scripts.core.regime_detector import HMMRegimeDetector, HMMLEARN_AVAILABLE
from scripts.logger import get_logger

train_logger = get_logger("train_hmm")


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_training_data(index_code: str) -> dict:
    train_logger.info(f"获取指数数据: {index_code}")

    try:
        import efinance as ef

        prefix = "sh" if index_code.startswith(("000", "9")) else "sz"
        ef_code = f"{prefix}{index_code}"
        df = ef.stock.get_quote_history(ef_code)
        if df is not None and not df.empty:
            train_logger.info(f"efinance获取数据成功: {len(df)}条")
            return _process_dataframe(df)
    except Exception as e:
        train_logger.warning(f"efinance获取失败: {e}")

    try:
        import baostock as bs

        lg = bs.login()
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


def main():
    parser = argparse.ArgumentParser(description="训练HMM市场状态识别模型")
    parser.add_argument("--config", type=str, default="config/config.yaml", help="配置文件路径")
    parser.add_argument("--n-components", type=int, default=None, help="隐状态数量")
    parser.add_argument("--model-path", type=str, default=None, help="模型保存路径")
    parser.add_argument("--index", type=str, default=None, help="训练用指数代码")
    args = parser.parse_args()

    if not HMMLEARN_AVAILABLE:
        train_logger.error("hmmlearn未安装，请执行: pip install hmmlearn")
        sys.exit(1)

    config = load_config(args.config)
    hmm_config = config.get("hmm", {})

    n_components = args.n_components or hmm_config.get("n_components", 4)
    model_path = args.model_path or hmm_config.get("model_path", "models/hmm_regime.pkl")
    index_code = args.index or hmm_config.get("training_index", "000300")

    train_logger.info(f"配置: n_components={n_components}, model_path={model_path}, index={index_code}")

    data = fetch_training_data(index_code)
    if not data:
        train_logger.error("无法获取训练数据")
        sys.exit(1)

    train_logger.info(f"训练数据: {data['n_samples']}条样本")

    detector = HMMRegimeDetector(n_components=n_components, config=hmm_config)

    result = detector.train(data["returns"], data["volatilities"], data["volume_changes"])

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
    if saved:
        train_logger.info(f"模型已保存: {model_path}")
    else:
        train_logger.error("模型保存失败")
        sys.exit(1)

    train_logger.info("训练完成!")


if __name__ == "__main__":
    main()
