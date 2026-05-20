# Stock Query - A股量化分析平台

Stock Query 是一个功能完善的 A 股量化分析平台，集成多源数据获取、技术指标计算、多维评分体系、交叉验证校准、ML 混合预测、蒙特卡洛压力测试、回测验证和 Web 可视化界面，覆盖从数据采集到决策输出的完整量化分析链路。

---

## 目录

- [核心模块总览](#核心模块总览)
- [分析引擎](#分析引擎)
- [技术指标体系](#技术指标体系)
- [交叉验证体系](#交叉验证体系)
- [价格预测与ML混合](#价格预测与ml混合)
- [市场状态检测](#市场状态检测)
- [回测与验证系统](#回测与验证系统)
- [数据获取与保障](#数据获取与保障)
- [日志系统](#日志系统)
- [Web 界面](#web-界面)
- [项目结构](#项目结构)
- [环境要求与快速开始](#环境要求与快速开始)
- [API 接口](#api-接口)
- [数据库设计](#数据库设计)
- [配置说明](#配置说明)
- [命令行使用](#命令行使用)
- [技术栈](#技术栈)
- [常见问题](#常见问题)
- [部署](#部署)

---

## 核心模块总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web 界面 (Vue 3)                         │
│  分析报告页 │ 回测中心 │ 自选股管理 │ 实时日志 │ 响应式布局       │
├─────────────────────────────────────────────────────────────────┤
│                      后端服务 (FastAPI)                          │
│  SSE 流式分析 │ 批量并发 │ 结果缓存 │ 请求追踪 │ 日志上报        │
├──────────┬──────────┬──────────┬──────────┬─────────────────────┤
│ 分析引擎  │ 技术指标  │ 交叉验证  │ ML 混合   │ 市场状态检测        │
│ 五级趋势  │ MACD/RSI │ 方向共识  │ LightGBM  │ HMM + 规则         │
│ 多维评分  │ KDJ/BOLL │ 冲突惩罚  │ 规则混合  │ 动态权重            │
│ 信号生成  │ ATR/OBV  │ 置信度    │ 涨跌停校验 │ EMA 平滑           │
├──────────┴──────────┴──────────┴──────────┴─────────────────────┤
│  回测引擎  │ Walk-Forward │ 蒙特卡洛压力测试 │ 校准器              │
├─────────────────────────────────────────────────────────────────┤
│  数据获取层 (多源回退 + 超时重试 + 熔断器 + 连接池)               │
│  efinance → xtquant → AkShare → baostock                       │
├─────────────────────────────────────────────────────────────────┤
│  数据库层 (PostgreSQL + TimescaleDB + pgvector)                  │
│  独立表结构 │ 空值检测刷新 │ 市值反推 │ 向量索引                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 分析引擎

分析引擎是系统核心，综合技术面、资金面、市场情绪三个维度生成交易信号和操作建议。

### 五级趋势分类

基于涨跌幅阈值 + 趋势持续性判定，将市场趋势分为五个等级：

| 趋势 | 涨跌幅阈值 | 趋势值 |
|------|-----------|--------|
| 大幅上涨 (strong_up) | ≥ +3% | +2 |
| 上涨 (up) | ≥ +1% | +1 |
| 震荡 (neutral) | -1% ~ +1% | 0 |
| 下跌 (down) | ≤ -1% | -1 |
| 大幅下跌 (strong_down) | ≤ -3% | -2 |

### 多维评分体系

综合三个维度生成加权评分，默认权重可通过配置或动态权重管理器调整：

| 维度 | 默认权重 | 评分范围 | 核心逻辑 |
|------|---------|---------|---------|
| 技术面 (technical) | 50% | 0~1 | MACD/RSI/KDJ/BOLL/均线信号加权，冲突惩罚 |
| 资金面 (fund_flow) | 30% | 0~1 | 主力净流入占比，按市值分档设定阈值 |
| 市场情绪 (sentiment) | 20% | 0~1 | 换手率 + 量比 + 大盘涨跌幅 |

**综合评分** = technical × 0.5 + fund_flow × 0.3 + sentiment × 0.2

### 技术面评分信号

技术面原始分范围 -75 ~ +75，归一化到 0~1：

| 信号 | 分值 | 业务意义 |
|------|------|---------|
| MACD 金叉确认 | +30 | DIF 上穿 DEA 且柱状图为正，强买入 |
| MACD 死叉确认 | -30 | DIF 下穿 DEA 且柱状图为负，强卖出 |
| MACD 金叉/死叉 | ±25 | DIF 与 DEA 交叉，趋势转折信号 |
| MACD 多头/空头 | ±15 | DIF 与 DEA 位置关系，趋势延续信号 |
| RSI(12) 超卖/超买 | ±10 | 超卖反弹/超买回调信号 |
| RSI(12) 偏强/偏弱 | ±5 | 中间区间的趋势辅助判断 |
| RSI 金叉/死叉 | ±5 | RSI(6) 与 RSI(12) 交叉 |
| RSI 顶/底背离 | ±10 | RSI(6)>70 且 RSI(24)<40 顶背离；反之底背离 |
| KDJ 金叉/死叉 | ±15 | K 线与 D 线交叉，短期转折信号 |
| KDJ 超卖/超买 | ±10 | K/D 值 <20 / >80 |
| BOLL 超卖/超买 | ±10 | 价格突破下轨/上轨 |
| BOLL 中轨上方/下方 | ±5 | 价格相对中轨位置 |
| BOLL 收窄/扩张 | ±5/−5 | bandwidth<10 收窄(变盘前兆)；>25 扩张(趋势加速) |
| 均线多头/空头排列 | ±10 | MA5>MA10>MA20 多头；MA5<MA10<MA20 空头 |

**冲突惩罚**：多空信号同时存在时，penalty = min(0.15, abs(多-空)×0.03)；ATR 剧烈 + BOLL 收窄/扩张时额外 +0.05。

**特征正交化**：当 `feature_engineering.enabled=true` 且高相关特征对存在时，用 PCA 正交化，blend=0.3 混合原始评分与正交评分。

### 资金面评分

按市值分档设定主力净流入占比阈值：

| 市值范围 | 高阈值 | 低阈值 |
|----------|--------|--------|
| >500 亿（大盘股） | 1% | 0.5% |
| 50~500 亿（中盘股） | 3% | 1.5% |
| <50 亿（小盘股） | 5% | 2.5% |

评分规则：inflow_ratio > 高阈值=1.0, >低阈值=0.7, >0=0.5, >-低阈值=0.4, >-高阈值=0.3, 其他=0.1。连续 3 日主力净流入/流出额外 ±0.2。

### 市场情绪评分

| 因素 | 评分调整 | 业务意义 |
|------|---------|---------|
| 换手率 >15% | +0.15 | 高度活跃 |
| 换手率 >8% | +0.1 | 较活跃 |
| 换手率 <2% | -0.05 | 交投清淡 |
| 量比 >2 | +0.15 | 明显放量 |
| 量比 >1.5 | +0.1 | 温和放量 |
| 量比 <0.5 | -0.05 | 明显缩量 |
| 大盘涨跌幅 >1% | +0.1 | 大盘走强 |
| 大盘涨跌幅 <-1% | -0.1 | 大盘走弱 |

### 交易信号生成

基于综合评分的信号阈值：

| 信号 | 评分范围 | 未持有建议 | 已持有建议 |
|------|---------|-----------|-----------|
| strong_buy | ≥ 0.7 | 强烈买入 | 强烈加仓 |
| buy | ≥ 0.5 | 买入 | 加仓 |
| hold | ≥ 0.3 | 持有观望 | 持有 |
| watch | > 0 | 关注 | 观望 |
| sell | ≤ 0 | 回避 | 减仓 |

---

## 技术指标体系

### MACD（12, 26, 9）

| 指标 | 计算方式 |
|------|---------|
| DIF (快线) | EMA(close, 12) - EMA(close, 26) |
| DEA (慢线) | EMA(DIF, 9) |
| MACD 柱 | (DIF - DEA) × 2 |

**信号判定**：金叉确认（DIF 上穿 DEA 且柱状图为正）、死叉确认（DIF 下穿 DEA 且柱状图为负）、多头/空头排列。

### RSI（6/12/24，自适应阈值）

| 指标 | 计算方式 |
|------|---------|
| RSI | 100 - 100/(1 + RS)，RS = EWM 平滑上涨均值/下跌均值 |
| 自适应阈值 | 60 日分位数 P80/P20 动态调整超买超卖线 |

**信号判定**：超买/超卖、多周期背离（RSI(6) 与 RSI(24) 方向相反）、偏强/偏弱。

### KDJ（9, 3, 3）

| 指标 | 计算方式 |
|------|---------|
| RSV | (Close - Low9) / (High9 - Low9) × 100 |
| K | 2/3 × prev_K + 1/3 × RSV |
| D | 2/3 × prev_D + 1/3 × K |
| J | 3K - 2D |

**信号判定**：K/D 金叉死叉、超买(K/D>80)/超卖(K/D<20)。

### BOLL（20, 2）

| 指标 | 计算方式 |
|------|---------|
| 中轨 | SMA(close, 20) |
| 上轨 | 中轨 + 2 × std(close, 20, ddof=1) |
| 下轨 | 中轨 - 2 × std(close, 20, ddof=1) |
| bandwidth | (上轨 - 中轨) / 中轨 × 100 |
| %B | (Close - 下轨) / (上轨 - 下轨) |

使用样本标准差（ddof=1），与主流行情软件一致。bandwidth<10 为收窄（变盘前兆），>25 为扩张（趋势加速）。

### ATR（14）

| 指标 | 计算方式 |
|------|---------|
| True Range | max(H-L, \|H-prevC\|, \|L-prevC\|) |
| ATR | Wilder 平滑（EWM com=13） |

ATR 用于止损止盈计算和价格预测区间宽度。

### 其他指标

| 指标 | 计算方式 | 业务意义 |
|------|---------|---------|
| OBV | 涨加量，跌减量，平不变 | 量价背离判断 |
| 量比 | 今日量 / 前 5 日均量 | >2.5 巨量，>1.5 放量，<0.8 缩量 |
| 偏度 (Skewness) | 收益率分布三阶矩 | <−0.5 左偏（下行风险大） |
| 峰度 (Kurtosis) | 收益率分布四阶矩 | >5 厚尾（极端事件概率高） |
| VaR 95%/99% | 收益率分位数 | 最大可能损失 |
| CVaR 95%/99% | 超过 VaR 的条件期望 | 尾部风险度量 |
| Beta | cov(个股,指数)/var(指数) | >1.5 高 Beta，止损距离缩短 30% |
| 相对强度 | 个股累计收益/指数累计收益 | >1.2 强势，<0.8 弱势 |
| 历史波动率 | log 收益 rolling.std × √252 | 年化波动率 |
| Parkinson 波动率 | √(1/(4ln2) × mean((ln(H/L))²)) × √252 | 利用高低价的波动率 |
| Garman-Klass 波动率 | √(mean(0.5(ln(H/L))² - (2ln2-1)(ln(C/O))²)) × √252 | 利用 OHLC 的波动率 |
| 已实现波动率 | √(sum(log_ret²)) × √(252/window) | 高频波动率估计 |

波动率信号：25/75 百分位分界 → 低波动/正常/高波动。

---

## 交叉验证体系

交叉验证是系统的核心风控机制，通过多维度方向共识检测、信号一致性验证和冲突惩罚，将原始交易信号转化为可信的操作建议。

### 方向共识检测

| 维度 | 看多阈值 | 看空阈值 |
|------|---------|---------|
| 技术面 | ≥ 0.65 | ≤ 0.35 |
| 资金面 | ≥ 0.60 | ≤ 0.40 |
| 市场情绪 | ≥ 0.60 | ≤ 0.40 |

**额外投票权重**：价格预测(0.15)、MACD 信号(0.10)、KDJ 信号(0.08)、RSI 信号(0.07)、BOLL 位置(0.05)、信号持续性(0.05)。

**方向共识**：bull_ratio ≥ 0.6 → 看多；bear_ratio ≥ 0.6 → 看空；否则为分歧。

### 冲突检测与惩罚

系统自动检测 5 种冲突模式：

| 冲突模式 | 说明 |
|----------|------|
| 技术偏强但资金未确认 | 技术看多但资金面不支持 |
| 技术偏弱但资金流入 | 技术看空但资金在流入 |
| 交易信号偏强但价格预测转弱 | 信号与预测方向不一致 |
| 多项指标偏多但综合信号未确认 | 个别指标看多但整体不确认 |
| RSI 超买/超卖与方向背离 | RSI 超买却看多或超卖却看空 |

**惩罚规则**：每项冲突 −0.1，上限 −0.3。

### 置信度计算

```
confidence = signal × 0.4 + agreement × 0.6 − conflict_penalty − missing_penalty
```

**分布特征修正**：
- 左偏(skewness < −0.5)：置信度 × 0.8
- 厚尾(kurtosis > 5)：风险升级
- 高 Beta(>1.5)：风险升级
- 相对强度 >1.2：置信度 × 1.1

### 操作建议（行动门控）

| 操作建议 | action_gate | 条件 | 含义 |
|---------|-------------|------|------|
| 建议买入 | allow_buy | 看多 + 置信度≥0.7 | 多维度一致看多，高置信度 |
| 可考虑买入 | cautious_buy | 看多 + 置信度≥0.5 | 多数看多，但存在分歧 |
| 观望 | watch | 方向不明确 | 多空方向不明确 |
| 回避 | avoid_buy | 看空 + 置信度≥0.6 | 多维度一致看空 |
| 减仓 | reduce_position | 已持有 + 看空 + 高置信度 | 已持仓且多维度看空 |
| 谨慎持有 | cautious_hold | 已持有 + 看空 + 中等置信度 | 已持仓但存在风险信号 |
| 继续持有 | hold_position | 已持有 + 趋势稳定 | 已持仓且趋势稳定 |

---

## 价格预测与ML混合

### 规则引擎预测

基于技术评分 + ATR + 布林带预测短期价格区间：

1. **趋势分类**：根据涨跌幅确定五级趋势
2. **ATR 乘数**：基础 1.5，乘以 (0.8 + 0.4 × trend_strength)；强趋势 ×1.3，弱趋势 ×0.8
3. **均值回归**：偏离 MA20 超 10% 时引入回归因子
4. **涨跌停校验**：创业板/科创板 20%，主板 10%，ST 股 5%
5. **Day2 修正**：RSI(12) 超买→下移，超卖→上移

### ML 混合预测

LightGBM 模型与规则引擎混合输出：

| 子模型 | 类型 | 预测目标 |
|--------|------|---------|
| return_model | LGBMRegressor | 次日收益率 |
| direction_model | LGBMClassifier | 涨跌方向 |
| volatility_model | LGBMRegressor | 波动率 |

**混合公式**（alpha=0.5）：
```
hybrid_low = alpha × rule_low + (1-alpha) × ml_low
hybrid_high = alpha × rule_high + (1-alpha) × ml_high
```

**方向判定**：weighted_rule + weighted_ml > 0.5 → 上涨

**置信度**：max(rule_conf, ml_conf) × (1 − |rule_dir − ml_dir| × 0.3)

### 持仓策略

| 策略项 | 计算方式 |
|--------|---------|
| 止损价 | max(2 × ATR, 5%) 距离 |
| 止盈价 | 2.5 × ATR 距离 |
| 建议仓位 | 10 + 20 × (1 − RSI/100)，范围 10%~30% |
| 下跌趋势 | 仓位减半 |
| 左偏分布 | 仓位再减半 |
| 高 Beta(>1.5) | 止损距离缩短 30% |

---

## 市场状态检测

### 规则检测

| 市场状态 | 检测规则 | 权重分配 (技术/资金/情绪) |
|----------|---------|--------------------------|
| 趋势牛市 | 高波动 + 涨>3% | 0.6 / 0.2 / 0.2 |
| 极端恐慌 | 高波动 + 跌>3% | 0.2 / 0.2 / 0.6 |
| 机构行情 | 量比>2 + 振幅<1% | 0.3 / 0.5 / 0.2 |
| 缩量震荡 | 低波动 + 量比<0.8 | 0.4 / 0.3 / 0.3 |

### HMM 检测

基于 GaussianHMM 的市场状态识别：

- **模型**：GaussianHMM, n_components=4 或 5
- **观测**：[收益率, 波动率, 成交量变化] 三维序列
- **状态映射**：按均值收益率最高→趋势上涨，最低→趋势下跌，波动率最高→高波动，恐慌得分最高→恐慌
- **训练**：n_iter=200, tol=1e-4, covariance_type=diag

### 动态权重管理

- **EMA 平滑**：alpha=0.3，权重更新公式 `new = alpha × target + (1-alpha) × current`，归一化
- **优先使用 HMM**：若 HMM 就绪则用 HMM 检测结果，否则用规则检测

---

## 回测与验证系统

### 预测验证

从数据库读取历史预测数据，与实际价格对比，统计以下指标：

| 指标 | 定义 | 业务意义 |
|------|------|---------|
| hit_rate | 实际价格落在预测区间内的比例 | 预测区间覆盖率 |
| direction_accuracy | 预测涨跌方向与实际一致的比例 | 方向判断能力 |
| trend_accuracy | 预测趋势等级与实际精确匹配的比例 | 趋势判断精度 |
| mean_width_pct | 平均(区间宽度/当前价) × 100 | 预测区间宽度 |
| midpoint_mae_pct | 区间中点与实际价格的平均绝对误差 | 预测精度 |
| coverage_width_score | 命中率/宽度比 | 预测效率 |

### Walk-Forward 验证

滚动前进验证，避免前视偏差：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| train_window | 60 | 训练窗口（天） |
| test_window | 20 | 测试窗口（天） |
| step | 20 | 滑动步长（天） |

**稳定性指标**：命中率标准差、方向准确率标准差、趋势准确率标准差、Sharpe 比率（hit_mean/hit_std）。

### 蒙特卡洛压力测试

对历史收益率添加高斯噪声，验证信号鲁棒性：

1. 生成噪声：noise ~ N(0, noise_scale × std(returns))，默认 200 次模拟
2. 重建价格序列，重新计算 MACD/RSI/KDJ 指标
3. 获取新信号，判断是否翻转（买入 ↔ 卖出）
4. **鲁棒性判定**：signal_flip_rate < 0.3 为鲁棒

**风险指标**：

| 指标 | 定义 |
|------|------|
| max_drawdown | 最大回撤 |
| sharpe | (mean_return − risk_free) / std |
| sortino | (mean_return − risk_free) / downside_std |
| calmar | 年化收益 / 最大回撤 |

### 校准器

自适应步长单参数轮换扫描，优化交叉验证阈值：

- **扫描参数**（9 个）：technical_bullish/bearish, fund_bullish/bearish, sentiment_bullish/bearish, signal_weight, agreement_weight, per_conflict_penalty
- **自适应步长**：先粗扫（大步长），再在最优值附近细扫（1/5 步长）
- **多目标评分**：composite = 0.35×accuracy + 0.25×trend_accuracy + 0.25×consistency − 0.10×width_penalty − 0.05×drawdown_penalty
- **自动应用**：非 dry_run 时自动写入 config.yaml

---

## 数据获取与保障

### 多源回退链

```
xtquant → efinance → AkShare → baostock
```

每个数据源独立超时（15s），失败自动切换下一源。并发获取 stock_info/fund_flow/history_data 三个维度。

### 超时与重试

| 参数 | 默认值 | 说明 |
|------|--------|------|
| max_retries | 2 | 最大重试次数 |
| retry_delay | 1s | 重试间隔 |
| request_timeout | 15s | 单次请求超时 |
| baostock_timeout | 20s | baostock 查询超时 |

### 熔断器

| 参数 | 默认值 | 说明 |
|------|--------|------|
| timeout | 300s | 数据源不健康标记持续时间 |
| health_check_interval | 60s | 健康检查间隔 |

标记不健康的数据源在超时后自动恢复，定时回调检测主动恢复。

### 数据库缓存

- **连接池**：ThreadedConnectionPool(min=2, max=20)，获取连接超时 10s 轮询等待
- **分析缓存**：600 秒 TTL，双写（原始输入 + 解析后代码）
- **空值检测**：自动检测 change_pct/amount/turnover_rate 为空或总市值仅 1 个不同值，触发强制刷新
- **市值反推**：最新市值 × (历史收盘价 / 最新收盘价)
- **盘中覆盖**：收盘后再分析自动用收盘价覆盖盘中价

---

## 日志系统

### 分类存储

| 日志文件 | 记录内容 |
|----------|---------|
| app.log | 应用主日志（分析流程、SSE 事件、缓存操作） |
| request.log | HTTP 请求日志（方法/URL/状态码/耗时/trace_id） |
| business.log | 业务日志（分析开始/完成、回测、自选股操作） |
| data.log | 数据流转日志（获取/缓存/刷新/回退） |
| system.log | 系统日志（启动/关闭、配置加载、连接池） |
| error.log | 错误日志（仅 ERROR+ 级别） |

### 日志格式

JSON 结构化格式，包含时间戳、级别、模块名、trace_id、span_id：

```json
{"timestamp": "2026-05-19T19:00:00+08:00", "level": "INFO", "module": "stock_query.sse", "trace_id": "abc123", "message": "SSE事件发送"}
```

### 日志轮转

- **按大小 + 日期轮转**：单文件最大 100MB，保留 30 个备份
- **gzip 压缩**：旧日志自动压缩
- **前端日志上报**：WARN+ 级别自动上报到后端 `/api/logs`

### 请求追踪

每个 HTTP 请求自动生成 trace_id/span_id，支持跨日志按 trace_id 查询完整请求链路。

---

## Web 界面

### 分析报告页

**驾驶舱布局**：左侧栏(市场环境) + 中央主区(报告+预测+图表) + 右侧栏(风险评估+交叉验证)，左右侧栏可折叠。

| 区域 | 组件 | 展示内容 |
|------|------|---------|
| 头部 | 股票信息 | 名称/代码/价格/涨跌/11 项关键指标/行业 |
| 左侧栏 | MarketStatusPanel | 大盘状态/情绪/波动率/风险/HMM |
| 中央 | KlineChart | K 线 + 均线 + 布林带 + 成交量 |
| 中央 | TechnicalChart | MACD/RSI/KDJ 三图并列 |
| 中央 | FundFlowChart | 主力/小单资金流向 + 占比 |
| 中央 | ReportPanel | 交易信号/评分/持仓策略/指标详情 |
| 中央 | PredictionCenter | Day1/Day2 预测区间/规则vsML/置信度 |
| 右侧栏 | RiskCenter | VaR/CVaR/尾部风险 |
| 右侧栏 | ValidationPanel | 方向共识/置信度/压力测试/多空比 |
| 底部 | AnalysisLogPanel | 实时运行日志（可折叠/过滤/复制） |

**SSE 流式分析**：分 5 阶段实时推送（基础数据→技术指标→风险评估→预测分析→完成），每阶段即时更新 UI。

**缓存优先**：分析前先查询缓存，命中直接展示结果。

### 回测中心

| 模式 | 功能 |
|------|------|
| 预测验证 | 12 项统计指标 + Day1/Day2 预测区间对比图 + 趋势准确性柱状图 + 逐日明细表 + CSV 导出 |
| Walk-Forward | 可配置训练/测试窗口 + 逐窗口准确率折线图 + 稳定性指标 + 窗口明细表 |

### 自选股管理

- **卡片网格**：代码/名称/持仓/成本/信号/分数/时间
- **信号分类**：看多(绿)/看空(红)/中性(蓝)颜色标识
- **一键批量分析**：SSE 流式进度推送，实时显示进度/当前股票/耗时/ETA
- **点击跳转**：点击卡片直接跳转分析页，携带持仓和成本参数

### 响应式布局

| 断点 | 布局调整 |
|------|---------|
| >1200px | 三栏驾驶舱布局 |
| 768~1200px | 侧栏换行到下方，主内容优先 |
| <768px | 单列布局，指标网格 4 列 |

---

## 项目结构

```
stock-query/
├── backend/                            # 后端服务 (FastAPI)
│   ├── app.py                          # 应用入口 + 中间件注册
│   ├── config.py                       # 后端配置
│   ├── exceptions.py                   # 自定义异常
│   ├── routers/
│   │   ├── analysis.py                 # 分析接口 (单股/批量/SSE流式/缓存查询)
│   │   ├── backtest.py                 # 回测接口 (预测验证/Walk-Forward)
│   │   ├── history.py                  # 自选股接口 (CRUD+信号缓存)
│   │   └── logs.py                     # 日志接口 (查询/前端上报)
│   ├── services/
│   │   ├── analysis_service.py         # 分析服务 (分阶段+缓存+DB写回)
│   │   ├── backtest_service.py         # 回测服务 (超时保护+连接池)
│   │   └── history_service.py          # 自选股服务 (JSON+文件锁)
│   ├── logging/                        # 日志系统
│   │   ├── config.py                   # 统一日志配置 (6类文件)
│   │   ├── handler.py                  # 按大小+日期轮转+gzip
│   │   ├── formatter.py                # JSON/控制台格式化
│   │   ├── middleware.py               # 请求日志中间件
│   │   ├── trace.py                    # trace_id/span_id 追踪
│   │   ├── helpers.py                  # 结构化日志辅助函数
│   │   └── sensitive.py                # 敏感数据脱敏
│   └── utils/
│       └── __init__.py                 # 序列化/清洗工具
├── frontend/                           # 前端应用 (Vue 3 + TypeScript)
│   ├── src/
│   │   ├── views/
│   │   │   ├── AnalysisView.vue        # 分析报告页 (驾驶舱布局)
│   │   │   ├── BacktestView.vue        # 回测中心页 (双模式Tab)
│   │   │   └── HistoryView.vue         # 自选股管理页 (卡片+批量分析)
│   │   ├── components/
│   │   │   ├── KlineChart.vue          # K线图+均线+布林带+成交量
│   │   │   ├── TechnicalChart.vue      # MACD/RSI/KDJ 三图
│   │   │   ├── FundFlowChart.vue       # 资金流向图
│   │   │   ├── ReportPanel.vue         # 交易信号+持仓策略面板
│   │   │   ├── ValidationPanel.vue     # 交叉验证+压力测试面板
│   │   │   ├── PredictionCenter.vue    # 价格预测+ML对比面板
│   │   │   ├── RiskCenter.vue          # VaR/CVaR风险评估面板
│   │   │   ├── MarketStatusPanel.vue   # 市场环境+HMM状态面板
│   │   │   ├── AnalysisLogPanel.vue    # 实时运行日志面板
│   │   │   ├── SideWatchlist.vue       # 侧边自选股列表
│   │   │   ├── NavHeader.vue           # 导航栏
│   │   │   └── StockInput.vue          # 股票输入面板
│   │   ├── stores/                     # Pinia 状态管理
│   │   │   ├── stockStore.ts           # 聚合 Store (Facade 模式)
│   │   │   ├── analysisStore.ts        # 分析核心 (SSE+代际控制)
│   │   │   ├── watchlistStore.ts       # 自选股 CRUD
│   │   │   ├── batchStore.ts           # 批量分析进度
│   │   │   ├── backtestStore.ts        # 回测结果
│   │   │   └── logStore.ts             # 运行日志
│   │   ├── api/                        # API 调用模块
│   │   │   ├── analysis.ts             # 分析 API + SSE 流
│   │   │   ├── history.ts              # 自选股 API
│   │   │   ├── backtest.ts             # 回测 API
│   │   │   └── config.ts               # API 超时配置
│   │   ├── composables/
│   │   │   ├── useSSEStream.ts         # SSE 流连接封装
│   │   │   └── useAsyncState.ts        # 异步状态管理
│   │   ├── utils/
│   │   │   ├── format.ts               # 格式化工具 (趋势/数字/市值)
│   │   │   └── logger/                 # 前端日志系统
│   │   └── types/                      # TypeScript 类型定义
│   └── vite.config.ts
├── scripts/                            # 核心分析引擎
│   ├── cli.py                          # CLI 入口
│   ├── logger.py                       # 日志工具 (薄封装)
│   ├── stock_query.py                  # 数据获取 (多源回退+字段补全)
│   ├── technical_indicators.py         # 技术指标计算 (18种指标)
│   ├── database.py                     # PostgreSQL 数据库层
│   └── core/
│       ├── data_fetcher.py             # 数据获取层 (并发+超时+熔断)
│       ├── analyzer.py                 # 分析逻辑 (五级趋势+交叉验证)
│       ├── backtest.py                 # 回测引擎
│       ├── walk_forward.py             # Walk-Forward 验证
│       ├── stress_test.py              # 蒙特卡洛压力测试
│       ├── calibration.py              # 交叉验证校准器
│       ├── ml_model.py                 # LightGBM 混合预测
│       ├── regime_detector.py          # 市场状态检测 (规则+HMM)
│       ├── circuit_breaker.py          # 数据源熔断器
│       ├── config_loader.py            # 配置加载器
│       └── report_generator.py         # 报告生成
├── config/
│   └── config.yaml                     # 配置文件
├── deploy/                             # 部署配置
│   ├── install.sh                      # 一键部署脚本
│   ├── stock-query-backend.service     # systemd 后端服务
│   └── stock-query-frontend.service    # systemd 前端服务
├── logs/                               # 日志目录 (6类分类存储)
├── data/                               # 数据目录
│   └── watchlist.json                  # 自选股持久化
├── models/                             # 模型目录
│   └── hmm_regime.pkl                  # HMM 模型文件
├── start.sh                            # 启动脚本
└── README.md
```

---

## 环境要求与快速开始

### 环境要求

| 依赖 | 版本要求 |
|------|---------|
| Python | 3.8+ |
| Node.js | ^20.19.0 或 >=22.12.0 |
| npm | 9+ |
| PostgreSQL | 12+ (建议安装 TimescaleDB + pgvector 扩展) |
| 操作系统 | Linux / Windows / macOS |

### 1. 安装依赖

```bash
# Python 核心依赖
pip install -r backend/requirements.txt
pip install pyyaml pandas numpy psycopg2-binary sse-starlette

# 数据源依赖（按需安装）
pip install efinance akshare          # 基础数据源
pip install xtquant                    # 迅投QMT数据源
pip install baostock                   # 历史数据补充（推荐）
pip install lightgbm                   # ML混合预测（推荐）
pip install hmmlearn                   # HMM市场状态检测（推荐）

# 前端依赖
cd frontend && npm install && cd ..
```

### 2. 配置数据库

确保 PostgreSQL 服务运行，创建数据库：

```sql
CREATE DATABASE stock_data;
-- 可选：安装扩展
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;
```

数据库连接配置位于 `scripts/database.py`，默认连接参数：

| 参数 | 默认值 |
|------|--------|
| host | localhost |
| port | 5432 |
| user | postgres |
| password | postgres |
| database | stock_data |

### 3. 启动服务

**方式一：启动脚本（推荐）**

```bash
./start.sh start
```

**方式二：手动启动**

```bash
# 后端
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8002

# 前端（新终端）
cd frontend && npm run dev
```

**方式三：systemd 开机自启动**

```bash
sudo bash deploy/install.sh
```

### 4. 访问界面

浏览器打开 http://localhost:5173

### 启动脚本

```bash
./start.sh start      # 启动前后端
./start.sh stop       # 停止前后端
./start.sh restart    # 重启前后端
./start.sh status     # 查看运行状态
./start.sh backend    # 仅启动后端
./start.sh frontend   # 仅启动前端
```

环境变量配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| BACKEND_PORT | 后端端口 | 8002 |
| FRONTEND_PORT | 前端端口 | 5173 |
| CORS_ORIGINS | 允许的前端源 | http://localhost:5173 |

---

## API 接口

### 分析接口

**单股分析（SSE 流式）**

```
GET /api/analysis/stream?stock_input=603956&position_status=未持有
响应: Server-Sent Events 流
event: stage_basic
data: {"stock_code": "603956", "stock_name": "威派格", ...}

event: stage_technical
data: {"indicators": {...}, ...}

event: stage_risk
data: {"risk": {...}, ...}

event: stage_prediction
data: {"prediction": {...}, ...}

event: stage_complete
data: {完整分析结果}
```

**单股分析（同步）**

```
POST /api/analysis
Content-Type: application/json

请求体:
{
  "stock_input": "603956",
  "position_status": "未持有",
  "cost_price": null
}

响应体:
{
  "stock_code": "603956",
  "stock_name": "威派格",
  "analysis": {
    "technical_score": 0.72,
    "fund_flow_score": 0.55,
    "sentiment_score": 0.60,
    "overall_score": 0.64,
    "recommendation": "可考虑买入"
  },
  "trading_signal": { ... },
  "price_prediction": { ... },
  "position_strategy": { ... },
  "validation": { ... },
  "indicators": { ... },
  "charts": { ... }
}
```

**查询缓存**

```
GET /api/analysis/cache?stock_input=603956&position_status=未持有
响应: {"cached": true, "age_seconds": 120, "result": {...}}
```

**批量快速分析（SSE 流式）**

```
POST /api/analysis/batch-quick
Content-Type: application/json

请求体:
{
  "stocks": [
    {"stock_input": "603956"},
    {"stock_input": "000001"}
  ]
}

响应: Server-Sent Events 流
event: progress
data: {"current": 1, "total": 5, "summary": {"stock_code": "603956", "signal_text": "建议买入", "score": 0.72}}

event: complete
data: {"total": 5, "success_count": 5, "error_count": 0, "summaries": [...]}
```

### 回测接口

**预测验证**

```
POST /api/backtest
请求体: {"stock_code": "603956"}
响应: {"statistics": {...}, "predictions": [...]}
```

**Walk-Forward 验证**

```
POST /api/backtest/walk-forward
请求体: {"stock_code": "603956", "train_window": 60, "test_window": 20, "step": 20}
响应: {"windows": [...], "overall": {...}, "stability": {...}}
```

### 自选股接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/watchlist` | 获取自选股列表 |
| POST | `/api/watchlist` | 添加自选股 |
| PUT | `/api/watchlist/{stock_code}` | 更新持仓状态/成本价 |
| DELETE | `/api/watchlist/{stock_code}` | 删除自选股 |

### 日志接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/logs?type=app&lines=100` | 查询日志 |
| GET | `/api/logs/trace/{trace_id}` | 按 trace_id 跨日志查询 |
| POST | `/api/logs` | 接收前端上报日志 |

### 健康检查

```
GET /health
响应: {"status": "ok"}
```

---

## 数据库设计

每只股票创建独立表 `stock_{code}`，核心字段：

| 分类 | 字段 | 类型 | 说明 |
|------|------|------|------|
| 行情 | trade_date | DATE | 交易日期（唯一约束） |
| 行情 | open/high/low/close | NUMERIC(12,2) | OHLC 价格 |
| 行情 | volume | BIGINT | 成交量（手） |
| 行情 | amount | NUMERIC(20,2) | 成交额（元） |
| 涨跌 | change_pct | NUMERIC(10,4) | 涨跌幅（%） |
| 涨跌 | change_amount | NUMERIC(12,2) | 涨跌额（元） |
| 涨跌 | turnover_rate | NUMERIC(10,4) | 换手率（%） |
| 估值 | pe_dynamic | NUMERIC(12,4) | 市盈率（动态） |
| 估值 | pb | NUMERIC(12,4) | 市净率 |
| 估值 | total_market_cap | NUMERIC(20,2) | 总市值（元） |
| 估值 | circ_market_cap | NUMERIC(20,2) | 流通市值（元） |
| 资金 | main_flow | NUMERIC(20,2) | 主力净流入（仅最新日） |
| 资金 | main_flow_ratio | NUMERIC(10,4) | 主力净流入占比（仅最新日） |
| 指标 | macd/dea/dif | NUMERIC(12,4) | MACD 指标值 |
| 指标 | rsi_6/rsi_12/rsi_24 | NUMERIC(12,4) | RSI 指标值 |
| 指标 | k/d/j | NUMERIC(12,4) | KDJ 指标值 |
| 预测 | day1_pred_high/low | NUMERIC(12,2) | Day1 预测区间 |
| 预测 | day2_pred_high/low | NUMERIC(12,2) | Day2 预测区间 |
| 向量 | features_vector | VECTOR(384) | 特征向量（pgvector 索引） |

**数据写入策略**：

| 字段 | 历史行数据来源 | 最新行数据来源 |
|------|--------------|--------------|
| 涨跌幅/涨跌额 | 收盘价计算 | 收盘价计算 |
| 成交额 | baostock → 成交量×均价估算 | 同左 |
| PE/PB/换手率 | baostock 逐日数据 | baostock → 实时快照回退 |
| 总市值/流通市值 | 收盘价反推 | 收盘价反推 |
| 主力资金/占比 | NULL | efinance 实时数据 |

---

## 配置说明

配置文件位于 `config/config.yaml`：

```yaml
# 数据获取
data_fetcher:
  max_retries: 2
  retry_delay: 1
  request_timeout: 15

# 技术指标参数
technical_indicators:
  macd: {fast: 12, slow: 26, signal: 9}
  rsi: {periods: [6, 12, 24]}
  kdj: {n: 9, m1: 3, m2: 3}
  ma: {periods: [5, 10, 20, 60]}
  boll: {n: 20, k: 2}

# 分析权重与阈值
analyzer:
  weights: {technical: 0.5, fund_flow: 0.3, sentiment: 0.2}
  thresholds: {strong_buy: 0.7, buy: 0.5, hold: 0.3}
  trend_thresholds: {strong_threshold: 0.03, normal_threshold: 0.01}

# 交叉验证参数
analyzer.validation:
  score_thresholds: {technical_bullish: 0.65, fund_bullish: 0.6, sentiment_bullish: 0.6}
  vote_thresholds: {bullish_consensus_margin: 3, bearish_consensus_margin: 2}
  confidence_weights: {signal: 0.4, agreement: 0.6}
  conflict_penalty: {per_conflict: 0.1, max: 0.3}

# 价格预测
analyzer.price_prediction:
  atr_multiplier: 1.5
  boll_multiplier: 1.0

# 特征工程
feature_engineering:
  enabled: true
  variance_threshold: 0.95
  correlation_threshold: 0.7
  method: pca

# 动态权重
dynamic_weights:
  enabled: true
  smoothing_alpha: 0.3
  regimes:
    trend_bull: {technical: 0.6, fund_flow: 0.2, sentiment: 0.2}
    extreme_panic: {technical: 0.2, fund_flow: 0.2, sentiment: 0.6}
    institutional: {technical: 0.3, fund_flow: 0.5, sentiment: 0.2}
    low_volume: {technical: 0.4, fund_flow: 0.3, sentiment: 0.3}

# HMM 市场状态检测
hmm:
  enabled: true
  n_components: 4
  model_path: models/hmm_regime.pkl

# ML 混合预测
ml_model:
  enabled: true
  alpha: 0.5
  num_leaves: 31
  learning_rate: 0.05
  n_estimators: 200

# 蒙特卡洛压力测试
stress_test:
  enabled: true
  n_simulations: 200
  noise_scale: 0.5

# 数据预处理
preprocessing:
  robust_z_threshold: 3.0
  outlier_method: winsorize
  denoise: kalman

# 数据验证与熔断
data_validation:
  circuit_breaker_timeout: 300
  health_check_interval: 60

# 波动率
volatility:
  hv_windows: [20, 60]
  parkinson_window: 20
  garman_klass_window: 20
  realized_window: 20
```

---

## 命令行使用

```bash
# 分析单只股票
python -m scripts.cli 603956

# 使用股票名称
python -m scripts.cli 威派格

# 回测
python -m scripts.cli --backtest 603956

# 交叉验证校准
python -m scripts.cli --calibrate

# 训练 HMM 模型
python -m scripts.train_hmm

# 训练 ML 模型
python -m scripts.train_model

# 指定配置
python -m scripts.cli 威派格 --config config/config.yaml

# 指定输出目录
python -m scripts.cli 威派格 --output-dir ./my_reports
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Vue 3 + TypeScript + Vite |
| UI 组件 | Element Plus |
| 图表 | ECharts 6 (vue-echarts) |
| 状态管理 | Pinia (Facade 模式) |
| 后端框架 | FastAPI + Uvicorn |
| 实时通信 | SSE (sse-starlette) |
| 数据库 | PostgreSQL + TimescaleDB + pgvector |
| 数据获取 | efinance + AkShare + baostock + xtquant |
| 数据处理 | Pandas + NumPy |
| 机器学习 | LightGBM + hmmlearn |
| 日志 | 结构化 JSON + 分类存储 + 轮转压缩 |
| 部署 | systemd + nginx |

---

## 常见问题

### Q: 分析时提示"无法获取历史数据"

A: 检查网络连接。系统按 xtquant → efinance → AkShare → baostock 顺序回退，所有源均失败时会出现此提示。建议安装 baostock（`pip install baostock`）作为兜底数据源。

### Q: 批量分析卡在某只股票不动

A: 系统已为每只股票设置 90 秒超时保护，超时后自动跳过并标记错误。如果频繁超时，可能是网络不稳定，检查数据源连接。

### Q: 数据库字段为空

A: 系统会在下次分析时自动检测空值字段并触发刷新。也可以手动触发：在分析页面重新分析该股票。

### Q: 盘中分析和收盘后分析数据不一致

A: 盘中分析写入的是盘中价格，收盘后再分析会自动用收盘价覆盖当日数据。建议收盘后再进行分析以获取准确数据。

### Q: PE（市盈率）为负数

A: 亏损公司的市盈率为负数，这是正常现象。系统不会过滤负 PE。

### Q: 历史市值数据准确吗

A: 历史总市值和流通市值通过 `最新市值 × (历史收盘价 / 最新收盘价)` 反推，在总股本不变的假设下精确。如遇增发等情况会有偏差。

### Q: ML 混合预测和规则预测哪个更准

A: 系统默认 alpha=0.5，即规则和 ML 各占 50% 权重。可在 config.yaml 中调整 alpha 值：alpha=1.0 为纯规则预测，alpha=0.0 为纯 ML 预测。建议保持 0.5 以获得最佳混合效果。

### Q: HMM 市场状态检测需要训练吗

A: 首次使用时系统会自动训练 HMM 模型并保存到 `models/hmm_regime.pkl`。后续启动时自动加载。也可手动训练：`python -m scripts.train_hmm`。

### Q: 日志文件太大怎么办

A: 系统自动按大小（100MB）和日期轮转，旧日志 gzip 压缩，保留 30 个备份。如需手动清理，删除 `logs/` 目录下的 `.gz` 文件即可。

---

## 部署

### systemd 开机自启动

```bash
# 一键部署
sudo bash deploy/install.sh

# 手动管理
sudo systemctl start stock-query-backend stock-query-frontend
sudo systemctl stop stock-query-backend stock-query-frontend
sudo systemctl status stock-query-backend stock-query-frontend

# 查看日志
journalctl -u stock-query-backend -f
journalctl -u stock-query-frontend -f

# 取消自启动
sudo systemctl disable stock-query-backend stock-query-frontend
```

### 生产环境部署

```bash
# 构建前端
cd frontend && npm run build

# 使用 nginx 代理
# 将 frontend/dist 目录部署到 nginx
# 将 /api 请求代理到后端 8002 端口
# SSE 需要禁用缓冲: proxy_buffering off;
```

nginx 参考配置：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        root /path/to/stock-query/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8002;
        proxy_buffering off;          # SSE 必需
        proxy_read_timeout 300s;      # 长连接超时
    }
}
```

---

## 贡献指南

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m "feat: 添加新功能"`
4. 推送分支：`git push origin feature/your-feature`
5. 提交 Pull Request

### 代码规范

- **Python**：遵循 PEP 8，使用有意义的变量名
- **TypeScript**：使用 Vue 3 Composition API + `<script setup>` 语法
- **提交信息**：使用中文，简短精炼

---

## 免责声明

本工具仅供学习和研究使用，不构成任何投资建议。股市有风险，投资需谨慎。使用本工具产生的任何投资损失，开发者不承担任何责任。

## 许可证

MIT License
