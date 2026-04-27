# 量化分析方案审查与改进建议

> 审查日期：2025年7月
> 审查范围：stock-query 项目全部核心模块（基于最新代码）
> 审查目标：识别改进空间，提升分析结果精确性
> 接口约束：所有改进建议严格限定在项目已使用的接口范围内

---

## 项目现有接口资源清单

| 数据源 | 可用方法 | 用途 |
|--------|----------|------|
| efinance | `get_base_info()` / `get_base_info(code)` | 全量股票列表 / 单只股票基本信息 |
| efinance | `get_quote_snapshot(code)` | 实时行情快照 |
| efinance | `get_history_bill(code)` | 历史资金流向（日线） |
| efinance | `get_today_bill(code)` | 当日分钟级资金流向 |
| efinance | `get_quote_history(code, klt=1, fqt=1)` | 分钟K线（前复权） |
| efinance | `get_quote_history(code, klt=101, fqt=1)` | 日K线（前复权） |
| xtquant | `download_history_data()` | 下载历史数据 |
| xtquant | `get_market_data()` | 获取行情数据 |
| xtquant | `get_instrument_detail()` | 合约基本信息 |
| xtquant | `get_sector_list()` / `get_stock_list_in_sector()` | 板块列表 / 成分股 |
| xtquant | `get_financial_data()` | 财务数据 |
| xtquant | `get_holidays()` / `get_trading_calendar()` | 节假日 / 交易日历 |
| baostock | `query_history_k_data_plus()` | 历史K线（降级兜底） |
| 计算库 | pandas / numpy | 数据处理与数值计算 |

---

## 优先级定义与判断依据

| 级别 | 定义 | 判断依据 |
|------|------|----------|
| **高** | 直接影响分析结果正确性或导致运行时错误 | ① 计算逻辑错误导致结果失真；② 数据质量问题直接污染指标计算；③ 类型不一致导致运行时崩溃；④ 评分体系数学错误 |
| **中** | 影响分析精确性但不致结果完全错误的问题 | ① 指标计算与主流标准存在偏差；② 评分体系可优化但当前可运行；③ 缺少可增强分析维度的指标；④ 验证机制缺失但不影响主流程 |
| **低** | 优化体验或代码质量但不影响分析结果的问题 | ① 代码风格与可维护性优化；② 文档完善；③ 性能优化；④ 边界场景处理 |

---

## 一、数据采集与预处理环节

### 1.1 发现的问题

#### 问题1：数据交叉验证传入空字典，形同虚设 [高]

`fetch_all_data()` 中调用验证时传入空字典，且代码注释已承认此问题：

```python
# data_fetcher.py L255-260
# TODO: D-02 数据交叉验证需要同时获取xtquant和efinance数据进行对比
# 当前架构仅在数据库模式或API模式下获取数据，暂无法实现真正的交叉验证
if DATABASE_AVAILABLE and db_result.get("source") == "api":
    try:
        validator_result = self.validate_data({}, {})  # 两个参数都是空字典
```

`DataValidator.cross_validate()` 接收两个空字典，无法进行任何有意义的比较，验证结果恒为默认值。`data_quality` 字段始终为 `"validated"` 或 `"unknown"`，无法区分真实的数据质量差异。

**可操作方案**：在 `fetch_all_data()` 中，当 xtquant 可用时，额外调用一次 efinance 获取同一股票的行情数据进行交叉验证。两个数据源的数据在 `fetch_stock_info()` 和 `get_stock_info()` 返回结果中均已获取，仅需在流程中增加对比步骤。

#### 问题2：数据库缓存无TTL机制 [中]

`get_or_fetch_stock_data()` 从数据库读取数据后无过期检查：

```python
# data_fetcher.py L214
db_result = get_or_fetch_stock_data(stock_code, force_refresh=False, days=120)
```

**可操作方案**：利用 xtquant 已有的 `get_trading_calendar()` 判断最近交易日，与数据库记录时间对比，超过阈值则刷新。

#### 问题3：clean_data()中ST股判断在非xtquant路径下可能缺失股票名称 [中]

`clean_data()` 已支持通过 `stock_name` 参数判断ST股，但 `get_history_data()` 中调用 `clean_data()` 时仅传入了 `stock_code`，未传入 `stock_name`：

```python
# stock_query.py L464
df = clean_data(df, stock_code)  # 缺少 stock_name 参数
```

在 efinance 和 baostock 降级路径中同样未传入 `stock_name`。

**可操作方案**：在 `get_history_data()` 中增加 `stock_name` 参数，从 `get_stock_info()` 获取股票名称后传入 `clean_data()`。

### 1.2 改进建议

| 编号 | 改进措施 | 优先级 | 实现方式 | 预期效果 |
|------|----------|--------|----------|----------|
| D-01 | 数据交叉验证传入实际数据源 | 高 | 同时获取xtquant和efinance数据传入validate_data() | 数据质量标记真实有效 |
| D-03 | get_history_data()传入stock_name | 中 | 增加stock_name参数，传递给clean_data() | ST股涨跌幅阈值在所有路径下正确应用 |

---

## 二、指标体系构建

### 2.1 发现的问题

#### 问题1：report_generator中RSI仍使用SMA计算 [高]

`technical_indicators.py` 中RSI已改用Wilder平滑（`ewm`），但 `report_generator.py` 的 `_prepare_technical_data()` 仍使用SMA：

```python
# report_generator.py L225-226
avg_gain = gain.rolling(window=period, min_periods=period).mean()  # SMA！
avg_loss = loss.rolling(window=period, min_periods=period).mean()  # SMA！
```

**风险**：图表中显示的RSI值与报告中分析使用的RSI值不一致。SMA版本的RSI更平滑、反应更慢，可能导致图表上的金叉/死叉信号与分析报告中的信号出现时机不同。

**可操作方案**：复用 `calculate_all_indicators()` 的计算结果传入图表数据准备方法。将 `indicators` 字典传入 `_prepare_technical_data()`，直接使用其中的 `series` 数据。`_prepare_technical_data()` 方法签名改为接收 `indicators` 字典，从中提取RSI/KDJ/MACD的series数据用于图表。

#### 问题2：report_generator中KDJ计算硬编码平滑系数 [中]

`_prepare_technical_data()` 中KDJ使用硬编码平滑系数：

```python
# report_generator.py L244-245
k[i] = 2/3 * k[i-1] + 1/3 * rsv.iloc[i]  # 硬编码 2/3 和 1/3
```

当 `m1=3` 时与 `technical_indicators.py` 等价，但如果配置修改了 `m1` 参数，图表将与分析结果不一致。

**可操作方案**：同问题1，复用 `calculate_all_indicators()` 的结果。

#### 问题3：缺少成交量MA指标 [低]

当前有OBV和量比两个成交量指标，但缺少成交量移动平均线（VOL-MA），这是判断放量/缩量的直观工具。

**可操作方案**：在 `calculate_volume_ratio()` 基础上增加成交量MA计算，仅需 `rolling().mean()`，pandas原生支持。

### 2.2 改进建议

| 编号 | 改进措施 | 优先级 | 实现方式 | 预期效果 |
|------|----------|--------|----------|----------|
| I-01 | report_generator复用指标计算结果 | 高 | 将indicators字典传入_prepare_technical_data() | 图表数据与分析数据一致 |
| I-02 | 增加成交量MA指标 | 低 | pandas rolling().mean() | 判断放量/缩量更直观 |

---

## 三、分析模型与算法选择

### 3.1 发现的问题

#### 问题1：情绪分析维度单一 [中]

当前情绪分析仅考虑换手率和量比，缺少大盘环境参考。

**可操作方案**：利用 efinance 的 `get_quote_snapshot('000001')` 获取上证指数涨跌作为大盘参考，在现有接口范围内可实现。

#### 问题2：持仓策略中未提供成本价时仍使用硬编码估算 [中]

```python
# analyzer.py L623
if cost_price:
    avg_cost = cost_price
else:
    avg_cost = current_price * 0.95  # 硬编码估算
```

当用户未提供 `--cost` 参数时，成本价仍为现价的95%，基于此计算的盈亏比例和止盈止损策略失真。

**可操作方案**：当未提供成本价时，在返回结果中明确标注 `cost_provided=False`，报告模板中显示"未提供成本价，以下数据仅供参考"。同时在报告模板中增加提示。

### 3.2 改进建议

| 编号 | 改进措施 | 优先级 | 实现方式 | 预期效果 |
|------|----------|--------|----------|----------|
| M-01 | 情绪分析增加大盘维度 | 中 | efinance get_quote_snapshot('000001') | 情绪分析更全面 |
| M-02 | 未提供成本价时标注提示 | 中 | 返回结果增加cost_provided字段 | 用户明确止盈止损数据的可靠性 |

---

## 四、计算逻辑与实现

### 4.1 发现的问题

#### 问题1：analyzer.py中BOLL兼容代码仍存在 [中]

`analyze_technical()` 和 `generate_position_strategy()` 中仍保留了BOLL新旧格式兼容代码：

```python
# analyzer.py L103-111
boll_latest = boll.get("latest", {})
if isinstance(boll_latest, dict):
    boll_upper = boll_latest.get("upper")
    ...
else:
    boll_upper = boll.get("upper")  # 旧格式兼容
    ...
```

由于 `calculate_boll()` 已统一返回 `{"latest": {...}, "series": {...}}` 结构，`else` 分支永远不会执行，属于冗余代码。

**可操作方案**：移除 `else` 分支，统一使用 `boll.get("latest", {}).get("upper")` 方式访问。纯代码清理。

#### 问题2：predict_price_range()中BOLL兼容代码 [中]

```python
# analyzer.py L388-393
boll_latest = boll.get("latest", {})
if isinstance(boll_latest, dict):
    lower = boll_latest.get("lower")
    upper = boll_latest.get("upper")
else:
    lower = boll.get("lower")  # 旧格式兼容
    upper = boll.get("upper")
```

同问题1，`else` 分支冗余。

#### 问题3：report_generator.py中BOLL兼容代码 [中]

```python
# report_generator.py L652-655
# 兼容新旧BOLL返回格式
"boll_upper": extract_latest(boll.get("latest", {}).get("upper")) if isinstance(boll.get("latest"), dict) else extract_latest(boll.get("upper")),
```

同问题1，`else` 分支冗余。

### 4.2 改进建议

| 编号 | 改进措施 | 优先级 | 实现方式 | 预期效果 |
|------|----------|--------|----------|----------|
| C-01 | 移除BOLL新旧格式兼容代码 | 中 | 统一使用.latest.get()方式，移除else分支 | 代码更简洁，减少维护负担 |

---

## 五、结果验证与评估

### 5.1 发现的问题

#### 问题1：数据验证传入空字典 [高]

（与1.1问题1重复，此处从验证角度分析）

当前验证调用 `self.validate_data({}, {})` 传入空字典，验证结果无意义。

#### 问题2：无信号准确性验证 [中]

交易信号的准确性完全未经验证，无胜率/盈亏比统计。

**可操作方案**：利用 efinance 的 `get_quote_history()` 获取历史数据，在本地模拟历史信号生成，统计信号后N日收益，纯pandas计算可实现简单回测。

#### 问题3：evals.json评估用例过于简单 [低]

评估用例仅验证"能否生成报告"，未验证计算正确性和边界情况。

### 5.2 改进建议

| 编号 | 改进措施 | 优先级 | 实现方式 | 预期效果 |
|------|----------|--------|----------|----------|
| V-01 | 修复数据验证传入实际数据 | 高 | 传入xtquant和efinance的实际数据 | 数据质量标记真实有效 |
| V-02 | 利用历史数据实现简单信号回测 | 中 | efinance获取历史数据+pandas模拟信号 | 量化评估信号质量 |
| V-03 | 完善evals.json评估用例 | 低 | 增加边界场景测试描述 | 提升系统鲁棒性 |

---

## 六、文档与说明

### 6.1 发现的问题

#### 问题1：评分体系缺乏说明文档 [中]

评分权重、阈值、分值设定均无文档说明其依据。

#### 问题2：限制因素和假设条件未充分说明 [低]

以下限制条件未在文档中明确说明：
- 分析结果仅适用于A股市场
- 不适用于ST股、新股、停牌股
- 历史数据仅60天，长周期指标可能不准确
- 未提供成本价时止盈止损仅供参考

### 6.2 改进建议

| 编号 | 改进措施 | 优先级 | 实现方式 | 预期效果 |
|------|----------|--------|----------|----------|
| DOC-01 | 增加评分体系说明文档 | 中 | 新增ANALYSIS_METHOD.md | 评分体系透明可审计 |
| DOC-02 | 在README中增加适用范围与限制 | 低 | 补充README章节 | 用户明确分析边界 |

---

## 七、实施路线

### 阶段一：修复正确性错误（高优先级项）

**目标**：修复影响分析结果正确性和运行时稳定性的问题。

| 任务编号 | 任务内容 | 涉及模块 | 依赖 | 交付物 |
|----------|----------|----------|------|--------|
| 1.1 | 数据交叉验证传入实际数据 | data_fetcher.py | 无 | 修复后的validate_data()调用 |
| 1.2 | report_generator复用指标计算结果 | report_generator.py | 无 | _prepare_technical_data()接收indicators字典 |

**关键里程碑**：数据验证真实有效，图表数据与分析数据一致。

**所需资源**：1名开发人员，无需新增第三方依赖。

### 阶段二：提升精确性与代码质量（中优先级项）

**目标**：增加分析维度，完善策略逻辑，清理冗余代码。

| 任务编号 | 任务内容 | 涉及模块 | 依赖 | 交付物 |
|----------|----------|----------|------|--------|
| 2.1 | get_history_data()传入stock_name | stock_query.py | 无 | ST股判断在所有路径下生效 |
| 2.2 | 数据库缓存TTL机制 | data_fetcher.py | 无 | 缓存过期逻辑 |
| 2.3 | 情绪分析增加大盘维度 | analyzer.py | 无 | 大盘涨跌评分 |
| 2.4 | 未提供成本价时标注提示 | analyzer.py, report_template.html | 无 | cost_provided字段+报告提示 |
| 2.5 | 移除BOLL新旧格式兼容代码 | analyzer.py, report_generator.py | 无 | 代码简化 |
| 2.6 | 利用历史数据实现简单信号回测 | 新增backtest模块 | 无 | 信号胜率统计 |
| 2.7 | 增加评分体系说明文档 | 新增ANALYSIS_METHOD.md | 无 | 方法论文档 |

**关键里程碑**：ST股判断全面覆盖，情绪分析增加大盘维度，代码冗余清理，信号质量可量化评估。

**所需资源**：1名开发人员，无需新增第三方依赖。

### 阶段三：体验优化（低优先级项）

**目标**：完善边界处理、文档和评估体系。

| 任务编号 | 任务内容 | 涉及模块 | 依赖 | 交付物 |
|----------|----------|----------|------|--------|
| 3.1 | 增加成交量MA指标 | technical_indicators.py | 无 | calculate_vol_ma()函数 |
| 3.2 | 完善evals.json评估用例 | evals.json | 无 | 边界场景测试 |
| 3.3 | 在README中增加适用范围与限制 | README.md | 无 | 限制说明章节 |

**关键里程碑**：边界场景覆盖完善，文档齐全。

---

## 八、改进项总览

| 编号 | 改进措施 | 优先级 | 阶段 | 判断依据 |
|------|----------|--------|------|----------|
| D-01 | 数据交叉验证传入实际数据 | 高 | 一 | 传入空字典导致验证形同虚设 |
| I-01 | report_generator复用指标结果 | 高 | 一 | 图表RSI用SMA与分析用Wilder不一致 |
| D-03 | get_history_data()传入stock_name | 中 | 二 | ST股判断在efinance/baostock路径下缺失 |
| D-02 | 数据库缓存TTL | 中 | 二 | 可能使用过时数据 |
| M-01 | 情绪分析增加大盘维度 | 中 | 二 | 情绪分析维度单一 |
| M-02 | 未提供成本价时标注提示 | 中 | 二 | 硬编码估算导致策略失真 |
| C-01 | 移除BOLL兼容代码 | 中 | 二 | 冗余代码增加维护负担 |
| V-02 | 简单信号回测 | 中 | 二 | 信号质量无法量化 |
| DOC-01 | 评分体系说明文档 | 中 | 二 | 评分依据不透明 |
| I-02 | 增加成交量MA | 低 | 三 | 缺少量价直观判断工具 |
| V-03 | 完善评估用例 | 低 | 三 | 边界场景覆盖不足 |
| DOC-02 | 适用范围与限制说明 | 低 | 三 | 用户不了解分析边界 |

---

## 九、预期效果

| 维度 | 当前状态 | 阶段一完成后 | 阶段二完成后 | 阶段三完成后 |
|------|----------|-------------|-------------|-------------|
| 数据质量 | 验证形同虚设 | 验证真实有效 | +缓存TTL+ST判断全覆盖 | — |
| 指标一致性 | 图表RSI用SMA | 图表与分析一致 | +兼容代码清理 | +成交量MA |
| 分析维度 | 情绪仅换手率+量比 | — | +大盘情绪+成本价提示 | — |
| 代码质量 | BOLL兼容代码冗余 | — | 兼容代码清理 | — |
| 结果可信度 | 验证无效、无回测 | 验证有效 | +信号回测 | +边界覆盖 |

> **核心结论**：经过多轮改进，当前系统的高优先级问题已大幅减少，仅剩**数据交叉验证形同虚设**和**report_generator中RSI仍用SMA**两项。阶段一修复这两项后，系统的基本正确性将得到全面保障。阶段二的重点转向提升精确性（大盘情绪、成本价提示）和代码质量（兼容代码清理），阶段三为锦上添花的优化项。
