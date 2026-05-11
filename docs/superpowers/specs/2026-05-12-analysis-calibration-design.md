# 校准机制设计文档

## 概述

对 `cross_validate_analysis` 中的硬编码阈值进行配置化提取，并通过回测驱动网格搜索自动校准，使交叉验证系统具备可调优能力和实证验证基础。

## 架构

```
StockAnalyzer 初始化
    │
    ├── 读取 config.yaml
    │       └── analyzer.validation.*  (阈值配置)
    │
    ├── cross_validate_analysis()
    │       └── 所有阈值取值改为从 self.validation_config 读取
    │           无配置时回退到当前硬编码值（向后兼容）
    │
scripts/core/calibration.py 模块
    │
    ├── run_validation_calibration()
    │       ├── 对每个参数做单参数轮换扫描（固定其他参数）
    │       │       └── 对每个候选值运行回测 → 计算 composite_score
    │       ├── 选取最优参数组合
    │       └── 返回 CalibrationReport
    │
    └── 输出：更新 config.yaml 中的最优值 + 敏感度分析报告
```

## 改动范围

### 1. config.yaml 扩展

在现有 `analyzer` 节点下新增 `validation` 子节点：

```yaml
analyzer:
  weights:
    technical: 0.5
    fund_flow: 0.3
    sentiment: 0.2
  thresholds:
    strong_buy: 0.7
    buy: 0.5
    hold: 0.3
  validation:
    score_thresholds:
      technical_bullish: 0.65
      technical_bearish: 0.35
      fund_bullish: 0.6
      fund_bearish: 0.4
      sentiment_bullish: 0.6
      sentiment_bearish: 0.4
    vote_thresholds:
      bullish_consensus_margin: 3
      bearish_consensus_margin: 2
    confidence_weights:
      signal: 0.4
      agreement: 0.6
    conflict_penalty:
      per_conflict: 0.1
      max: 0.3
  price_prediction:
    atr_multiplier: 1.5
    boll_multiplier: 1.0
```

### 2. StockAnalyzer

```python
# __init__ 新增
self.validation_config = config.get("analyzer", {}).get("validation", {})
```

`cross_validate_analysis` 中所有以前硬编码的阈值改为从 `self.validation_config` 读取，每个取值格式：

```python
vcfg = self.validation_config
st = vcfg.get("score_thresholds", {})
tech_bullish = st.get("technical_bullish", 0.65)
tech_bearish = st.get("technical_bearish", 0.35)
# ... 其余阈值同理，使用 .get(key, default) 模式
```

修改位置清单：

| 方法 | 行号范围 | 改动 |
|------|---------|------|
| `__init__` | 23-27 | 新增 `self.validation_config` 一行 |
| `cross_validate_analysis` | 567-695 | 所有 hardcode → config 读取 |

### 3. `scripts/core/calibration.py` — 新增

```python
def run_validation_calibration(
    config: dict,
    stock_codes: list[str] = None,
    lookback_days: int = 120,
) -> dict:
    """
    对 cross_validate_analysis 的阈值做单参数轮换校准。

    参数:
        config: 当前完整配置
        stock_codes: 用于校准的股票列表（默认用代表性股票池）
        lookback_days: 回测窗口

    返回:
        CalibrationReport
    """
```

**校准流程：**
1. 以当前 config 阈值运行回测 → baseline metrics
2. 对每个参数在 [0.5×当前值, 1.5×当前值] 范围扫描
3. 每步运行回测并计算 composite_score
4. composite_score = 0.30×accuracy + 0.25×sharpe + 0.20×win_rate + 0.15×(-max_dd) + 0.10×consistency
5. 选 composite_score 最高的参数组合
6. 以最优组合运行回测 → calibrated metrics
7. 返回 CalibrationReport + 写入 config.yaml

**Composition Score 各维度说明：**

| 维度 | 权重 | 来源 | 说明 |
|------|------|------|------|
| accuracy | 0.30 | backtest.accuracy | day1/day2 价格区间命中率的均值 |
| sharpe | 0.25 | backtest.sharpe | 夏普比率，反映风险调整后收益 |
| win_rate | 0.20 | backtest.win_rate | 盈利交易占比 |
| -max_dd | 0.15 | backtest.max_drawdown | 取负值，控制回撤 |
| consistency | 0.10 | 新增 | cross_validate 方向与 day1 实际趋势的一致率 |

**参数扫描范围：**

| 参数 | 当前值 | 扫描范围 | 步长 |
|------|--------|---------|------|
| technical_bullish | 0.65 | [0.45, 0.85] | 0.05 |
| technical_bearish | 0.35 | [0.15, 0.55] | 0.05 |
| fund_bullish | 0.60 | [0.40, 0.80] | 0.05 |
| fund_bearish | 0.40 | [0.20, 0.60] | 0.05 |
| sentiment_bullish | 0.60 | [0.40, 0.80] | 0.05 |
| sentiment_bearish | 0.40 | [0.20, 0.60] | 0.05 |
| bullish_consensus_margin | 3 | [1, 6] | 1 |
| bearish_consensus_margin | 2 | [1, 5] | 1 |
| signal_weight | 0.4 | [0.2, 0.6] | 0.05 |
| agreement_weight | 0.6 | [0.4, 0.8] | 0.05 |
| per_conflict_penalty | 0.1 | [0.05, 0.25] | 0.05 |

共 11 参数 × 约 9 步/参数 ≈ 99 轮回测，每轮回测覆盖多个股票。

### 4. CalibrationReport 结构

```python
CalibrationReport = {
    "target": "validation",
    "stock_sample": list[str],          # 使用的股票样本
    "lookback_days": int,
    "baseline": {
        "composite_score": float,
        "accuracy": float,
        "sharpe": float,
        "win_rate": float,
        "max_drawdown": float,
        "consistency": float,
    },
    "calibrated": {
        "composite_score": float,
        "accuracy": float,
        "sharpe": float,
        "win_rate": float,
        "max_drawdown": float,
        "consistency": float,
    },
    "optimal_params": {
        "technical_bullish": float,
        # ... 所有参数的最优值
    },
    "param_sensitivity": {
        "technical_bullish": {
            "values": list[float],      # 扫描值序列
            "scores": list[float],      # 对应的 composite_score
            "sensitivity": "high"|"medium"|"low",  # 波动幅度分级
            "improvement": float,       # 最优 vs 当前差值
        },
        # ... 每个参数一条
    },
    "improvement": {
        "composite_score_delta": float,
        "accuracy_delta": float,
        "sharpe_delta": float,
        "win_rate_delta": float,
        "maxdd_delta": float,
        "consistency_delta": float,
    },
}
```

### 5. 主入口（CLI / API）

新增 `scripts/calibrate.py`：

```bash
python scripts/calibrate.py \
    --target validation \
    --stock-pool 000001,000002,000333,600519,601012 \
    --lookback-days 120 \
    --output config.yaml
```

可选 `--dry-run` 只输出报告不修改 config。

## 不受影响的部分

- 现有 `analysis_service.py`：完全无变化
- 现有 `StockAnalyzer` 测试：不需要改动（or fallback 保证向后兼容）
- 回测服务：复用以有 API，无需修改
- 前端类型：无变化
- 价格预测 / 资金流 / 情绪分析：完全不受影响

## 测试计划

| 测试 | 文件 | 内容 |
|------|------|------|
| `test_validation_config_loaded` | `tests/test_analyzer_consistency.py` | 验证 config 正确传递到 StockAnalyzer |
| `test_cross_validate_uses_config` | `tests/test_analyzer_consistency.py` | 不同 config 值产生不同结果（如 tech_bullish=0.9 更严） |
| `test_calibration_engine_init` | `tests/test_calibration.py` | CalibrationEngine 初始化并返回正确结构 |
| `test_calibration_single_param_scan` | `tests/test_calibration.py` | 单参数扫描返回正确的 values/scores 序列 |
| `test_calibration_baseline_matches_current` | `tests/test_calibration.py` | 以当前值作为最优值时，baseline == calibrated |
| `test_calibration_improvement_non_negative` | `tests/test_calibration.py` | 校准后 composite_score ≥ 校准前 |
| `test_calibration_dry_run_no_side_effects` | `tests/test_calibration.py` | dry_run 不修改 config.yaml |

## 实施步骤

1. config.yaml 扩展 validation 阈值节点
2. `StockAnalyzer.__init__` + `cross_validate_analysis` 配置化改造
3. 新增 `scripts/core/calibration.py`（`run_validation_calibration` + 单参数轮换 + report 聚合）
4. 新增 `scripts/calibrate.py` CLI 入口
5. 跑现有 37 个回归测试确认无破坏
6. 新增 7 个校准测试
7. 全量测试通过后提交
