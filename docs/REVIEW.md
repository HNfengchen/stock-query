# 量化分析方案审查与改进建议

> 审查日期：2025年7月
> 审查范围：stock-query 项目全部核心模块（基于最新代码）
> 审查目标：识别改进空间，提升分析结果精确性
> 接口约束：所有改进建议严格限定在项目已使用的接口范围内

---

## 已实施改进确认

相较于初始版本，以下改进已落地实施：

| 改进项 | 状态 | 实施位置 |
|--------|------|----------|
| 数据清洗（停牌过滤、异常值检测） | ✅ 已实施 | stock_query.py `clean_data()` |
| 统一前复权 | ✅ 已实施 | 三个数据源均改为前复权 |
| ATR指标计算 | ✅ 已实施 | technical_indicators.py `calculate_atr()` |
| RSI改用Wilder平滑 | ✅ 已实施 | technical_indicators.py `calculate_rsi()` |
| KDJ初始值设为50 | ✅ 已实施 | technical_indicators.py `calculate_kdj()` |
| OBV指标 | ✅ 已实施 | technical_indicators.py `calculate_obv()` |
| BOLL纳入评分 | ✅ 已实施 | analyzer.py `analyze_technical()` |
| 均线排列判断 | ✅ 已实施 | analyzer.py `analyze_technical()` |
| 评分归一化修正 | ✅ 已实施 | analyzer.py `analyze_technical()` |
| 资金流向相对指标 | ✅ 已实施 | analyzer.py `analyze_fund_flow()` |
| 持仓成本用户输入 | ✅ 已实施 | cli.py `--cost` 参数 |
| 涨跌停校验 | ✅ 已实施 | analyzer.py `get_limit_pct()` |
| 数据质量标记 | ✅ 已实施 | data_fetcher.py `data_quality` 字段 |
| 涨跌幅阈值按板块区分 | ✅ 已实施 | stock_query.py `clean_data()` |
| RSI字段名修复（"value"→"latest"） | ✅ 已实施 | analyzer.py `generate_position_strategy()` |

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
# 需要重构以支持同时获取两个数据源
if DATABASE_AVAILABLE and db_result.get("source") == "api":
    try:
        validator_result = self.validate_data({}, {})  # 两个参数都是空字典
```

`DataValidator.cross_validate()` 接收两个空字典，无法进行任何有意义的比较，验证结果恒为默认值。`data_quality` 字段始终为 `"validated"` 或 `"unknown"`，无法区分真实的数据质量差异。

**风险**：数据质量标记 `data_quality` 无实际参考价值，用户无法判断数据可信度。

**可操作方案**：在 `fetch_all_data()` 中，当 xtquant 可用时，额外调用一次 efinance 获取同一股票的行情数据进行交叉验证。两个数据源的数据在 `fetch_stock_info()` 和 `get_stock_info()` 中均已获取，仅需在流程中增加对比步骤。具体做法：将 xtquant 获取的 `info` 字典和 efinance 的 `get_stock_info()` 返回结果分别作为两个参数传入 `validate_data()`。

#### 问题2：数据库缓存无TTL机制 [中]

`get_or_fetch_stock_data()` 从数据库读取数据后无过期检查：

```python
# data_fetcher.py L214
db_result = get_or_fetch_stock_data(stock_code, force_refresh=False, days=120)
```

**风险**：数据库中的历史数据可能已过时，非交易时段使用缓存可接受，但交易时段使用过时数据会导致分析结果偏差。

**可操作方案**：利用 xtquant 已有的 `get_trading_calendar()` 判断最近交易日，与数据库记录时间对比，超过阈值则刷新。纯逻辑判断，无需新接口。

#### 问题3：ST股涨跌幅阈值判断逻辑有误 [中]

`clean_data()` 中ST股的判断逻辑存在缺陷：

```python
# stock_query.py L68-69
elif "ST" in code_str or "*ST" in code_str:
    pct_min, pct_max = -6, 6  # ST股
```

`code_str` 是股票代码（如 "000001"），不包含股票名称，因此 `"ST" in code_str` 永远为 `False`。ST股的涨跌停为±5%，但当前代码无法识别ST股。

**可操作方案**：利用 efinance 的 `get_base_info(code)` 返回的股票名称判断是否为ST股，或在 `clean_data()` 中增加 `stock_name` 参数。在现有接口范围内可实现。

### 1.2 改进建议

| 编号 | 改进措施 | 优先级 | 实现方式 | 预期效果 |
|------|----------|--------|----------|----------|
| D-01 | 数据交叉验证传入实际数据源 | 高 | 同时获取xtquant和efinance数据传入validate_data() | 数据质量标记真实有效 |
| D-02 | 数据库缓存增加TTL机制 | 中 | 利用get_trading_calendar()判断数据新鲜度 | 避免使用过时数据 |
| D-03 | ST股判断改为基于股票名称 | 中 | clean_data()增加stock_name参数，从名称判断ST | ST股涨跌幅阈值正确应用 |

---

## 二、指标体系构建

### 2.1 发现的问题

#### 问题1：MACD和BOLL返回类型未统一 [高]

部分指标已统一为 `{"latest": float, "series": pd.Series, "signal": str}` 结构，但 MACD 和 BOLL 仍返回混合结构：

```python
# MACD 已统一（有latest和series）
calculate_macd() → {"latest": {"DIF": float, "DEA": float, "MACD": float}, "series": {...}, "signal": str}

# BOLL 已统一（有latest和series）
calculate_boll() → {"latest": {"upper": float, "middle": float, "lower": float}, "series": {...}}

# 但 analyzer.py 中仍使用旧字段名访问BOLL
boll_upper = boll.get("upper")  # L97-98 应该用 boll.get("latest", {}).get("upper")
```

**风险**：
- `analyzer.py` 第97-104行对BOLL做了6行类型转换代码来兼容新旧格式，增加了代码复杂度
- `report_generator.py` 第652-655行对BOLL也做了兼容处理
- 未来修改指标返回结构时，需要同步修改多处兼容代码

**可操作方案**：统一所有上游代码使用 `boll.get("latest", {}).get("upper")` 方式访问，移除兼容旧格式的代码。纯重构，无新依赖。

#### 问题2：ATR未用于止损止盈策略 [中]

ATR指标已实现并计算，`predict_price_range()` 中已使用ATR值替代布林带宽度作为价格区间，但 `generate_position_strategy()` 和 `generate_buy_strategy()` 的止损价设置仍使用固定百分比：

```python
# analyzer.py L647-648 止损止盈用固定百分比
target_price = current_price * (1 + stop_profit_pct / 100)
stop_price = current_price * (1 + stop_loss_pct / 100)

# analyzer.py L752-755 买入止损用固定比例
risk_price = current_price * 0.95
```

**风险**：固定百分比止损不考虑市场波动率，在高波动股上止损过近（频繁触发），在低波动股上止损过远（损失过大）。

**可操作方案**：利用已计算的ATR值设定止损位（如止损价=当前价-2×ATR），使止损距离与市场波动率挂钩。ATR值在 `indicators` 字典中已可用。

#### 问题3：缺少成交量MA指标 [低]

当前有OBV和量比两个成交量指标，但缺少成交量移动平均线（VOL-MA），这是判断放量/缩量的直观工具。

**可操作方案**：在 `calculate_volume_ratio()` 基础上增加成交量MA计算，仅需 `rolling().mean()`，pandas原生支持。

### 2.2 改进建议

| 编号 | 改进措施 | 优先级 | 实现方式 | 预期效果 |
|------|----------|--------|----------|----------|
| I-01 | 统一BOLL访问方式，移除旧格式兼容代码 | 高 | 统一使用boll.get("latest",{}).get("upper") | 消除兼容代码，简化维护 |
| I-02 | 止损止盈策略使用ATR | 中 | 止损价=当前价-N×ATR | 止损距离与波动率挂钩 |
| I-03 | 增加成交量MA指标 | 低 | pandas rolling().mean() | 判断放量/缩量更直观 |

---

## 三、分析模型与算法选择

### 3.1 发现的问题

#### 问题1：评分归一化范围与实际分数不匹配 [高]

BOLL评分（±10）和均线排列评分（±10）已加入评分体系，归一化范围已更新为[-90, 90]。但实际最大分数计算有误：

```python
# analyzer.py L148-149
MIN_SCORE = -90
MAX_SCORE = 90
```

实际最大正分计算：
- MACD金叉 +25
- RSI超卖 × 3个周期 = +30（三个RSI周期可能同时超卖）
- KDJ金叉 +15
- BOLL超卖 +10
- 多头排列 +10
- **合计 = +90** ✅

实际最大负分计算：
- MACD死叉 -25
- RSI超买 × 3个周期 = -30
- KDJ死叉 -15
- BOLL超买 -10
- 空头排列 -10
- **合计 = -90** ✅

归一化范围已正确。但存在一个**边界问题**：当RSI(6)超卖但RSI(12)和RSI(24)不超卖时，RSI仅贡献+10分；当三个RSI同时超卖时贡献+30分。RSI的权重因周期重叠而放大了3倍，这在统计学上不合理。

**风险**：RSI的三个周期高度相关，同时触发的概率较高，导致RSI的实际权重远超设计意图（10分 vs 30分）。

**可操作方案**：RSI评分改为仅使用RSI(12)作为代表周期（最常用的中期RSI），或将三个RSI的评分按权重衰减（如RSI(6)×0.5 + RSI(12)×1.0 + RSI(24)×0.5），总分上限仍为10分。纯逻辑修改。

#### 问题2：情绪分析维度单一 [中]

当前情绪分析仅考虑换手率和量比，缺少大盘环境参考。

**可操作方案**：利用 efinance 的 `get_quote_snapshot('000001')` 获取上证指数涨跌作为大盘参考，在现有接口范围内可实现。

#### 问题3：资金流向评分中成交额字段可能缺失 [中]

`analyze_fund_flow()` 使用 `fund_flow.get("成交额", 0)` 计算相对指标，但 `get_fund_flow()` 返回的字典中不包含 `成交额` 字段：

```python
# stock_query.py get_fund_flow() 返回的字段
fund_flow["日期"] = ...
fund_flow["主力净流入"] = ...
fund_flow["小单净流入"] = ...
# ... 没有 "成交额" 字段

# analyzer.py L186
amount = fund_flow.get("成交额", 0)  # 始终为0
```

**风险**：`inflow_ratio = main_inflow / amount`，当 `amount=0` 时，`inflow_ratio` 始终为0或触发除零保护，资金流向评分实际上退化为固定值。

**可操作方案**：在 `get_fund_flow()` 中增加 `成交额` 字段（efinance 的 `get_history_bill()` 返回数据中可能包含此字段），或使用 `stock_info` 中的 `成交额` 字段。需确认 efinance 接口返回的实际字段名。

### 3.2 改进建议

| 编号 | 改进措施 | 优先级 | 实现方式 | 预期效果 |
|------|----------|--------|----------|----------|
| M-01 | RSI评分改为仅使用RSI(12)或按权重衰减 | 高 | 修改analyze_technical()中RSI评分逻辑 | RSI权重合理，不被周期重叠放大 |
| M-02 | 情绪分析增加大盘维度 | 中 | efinance get_quote_snapshot('000001') | 情绪分析更全面 |
| M-03 | 修复资金流向评分中成交额缺失 | 中 | 从stock_info获取成交额或确认efinance字段 | 资金流向评分真实有效 |

---

## 四、计算逻辑与实现

### 4.1 发现的问题

#### 问题1：report_generator中RSI仍使用SMA计算 [高]

`technical_indicators.py` 中RSI已改用Wilder平滑（`ewm`），但 `report_generator.py` 的 `_prepare_technical_data()` 仍使用SMA：

```python
# report_generator.py L225-226
avg_gain = gain.rolling(window=period, min_periods=period).mean()  # SMA！
avg_loss = loss.rolling(window=period, min_periods=period).mean()  # SMA！
```

**风险**：图表中显示的RSI值与报告中分析使用的RSI值不一致，用户无法验证分析结果。SMA版本的RSI更平滑、反应更慢，可能导致图表上的金叉/死叉信号与分析报告中的信号出现时机不同。

**可操作方案**：复用 `calculate_all_indicators()` 的计算结果传入图表数据准备方法，消除重复计算并保证一致性。将 `indicators` 字典传入 `_prepare_technical_data()`，直接使用其中的 `series` 数据。

#### 问题2：report_generator中KDJ计算与technical_indicators不一致 [高]

`_prepare_technical_data()` 中KDJ使用硬编码平滑系数：

```python
# report_generator.py L244-245
k[i] = 2/3 * k[i-1] + 1/3 * rsv.iloc[i]  # 硬编码 2/3 和 1/3

# technical_indicators.py L184
k.iloc[i] = (k.iloc[i-1] * (m1-1) + rsv.iloc[i]) / m1  # 使用 m1 参数
```

当 `m1=3` 时两者等价，但如果配置修改了 `m1` 参数，report_generator 的图表将与分析结果不一致。

**可操作方案**：同问题1，复用 `calculate_all_indicators()` 的结果。

#### 问题3：generate_html_report中裸except捕获 [中]

```python
# report_generator.py L593-595
try:
    price_change = float(str(price_change).replace("%", ""))
except:
    price_change = 0

# report_generator.py L599-601
try:
    current_price = float(current_price)
except:
    current_price = 0
```

**风险**：吞掉所有异常（包括 `KeyboardInterrupt`），不利于问题排查。

**可操作方案**：改为 `except (ValueError, TypeError) as e`。

#### 问题4：stock_query.py中generate_report()使用旧字段名访问指标 [中]

`generate_report()` 函数中访问MACD和KDJ指标时使用旧字段名：

```python
# stock_query.py L651-653
macd_series = macd.get("series", {})
dif = macd_series.get("DIF")  # 正确，使用series

# stock_query.py L682-685
report += f"| K值 | {kdj.get('K', 'N/A')} |\n"  # 旧字段名，应使用 kdj.get("latest", {}).get("K")
report += f"| D值 | {kdj.get('D', 'N/A')} |\n"  # 旧字段名
report += f"| J值 | {kdj.get('J', 'N/A')} |\n"  # 旧字段名
```

**风险**：KDJ已统一为 `{"latest": {"K": ..., "D": ..., "J": ...}, "series": {...}}` 结构，使用 `kdj.get('K')` 将返回 `None`，报告中KDJ值显示为 "N/A"。

**可操作方案**：改为 `kdj.get("latest", {}).get("K", "N/A")`。

#### 问题5：stock_query.py中generate_report()访问BOLL使用旧字段名 [中]

```python
# stock_query.py L700-702
report += f"| 上轨 | {boll.get('upper', 'N/A')} |\n"  # 旧字段名
report += f"| 中轨 | {boll.get('middle', 'N/A')} |\n"  # 旧字段名
report += f"| 下轨 | {boll.get('lower', 'N/A')} |\n"  # 旧字段名
```

BOLL已统一为 `{"latest": {"upper": ..., "middle": ..., "lower": ...}, "series": {...}}` 结构，使用 `boll.get('upper')` 将返回 `None`，报告中BOLL值显示为 "N/A"。

**可操作方案**：改为 `boll.get("latest", {}).get("upper", "N/A")`。

### 4.2 改进建议

| 编号 | 改进措施 | 优先级 | 实现方式 | 预期效果 |
|------|----------|--------|----------|----------|
| C-01 | report_generator复用technical_indicators计算结果 | 高 | 将indicators字典传入_prepare_technical_data() | 图表数据与分析数据一致 |
| C-02 | 修复generate_report()中KDJ/BOLL旧字段名 | 高 | 改为.latest.get()方式访问 | Markdown报告中指标值正确显示 |
| C-03 | 修正裸except捕获 | 中 | 改为except (ValueError, TypeError) | 便于问题排查 |

---

## 五、结果验证与评估

### 5.1 发现的问题

#### 问题1：数据验证传入空字典 [高]

（与1.1问题1重复，此处从验证角度分析）

当前验证调用 `self.validate_data({}, {})` 传入空字典，验证结果无意义。`data_quality` 字段始终为 `"validated"` 或 `"unknown"`，无法区分真实的数据质量差异。

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

评分权重、阈值、分值设定均无文档说明其依据：
- 为什么技术面权重50%、资金面30%、情绪面20%？
- MACD金叉为什么+25分？BOLL超买为什么-10分？
- 买入阈值0.5是如何确定的？

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
| 1.2 | 统一BOLL访问方式，移除旧格式兼容代码 | analyzer.py, report_generator.py | 无 | 统一使用.latest.get() |
| 1.3 | RSI评分改为仅使用RSI(12)或按权重衰减 | analyzer.py | 无 | 修改后的RSI评分逻辑 |
| 1.4 | report_generator复用指标计算结果 | report_generator.py | 1.2 | 消除重复计算，图表数据一致 |
| 1.5 | 修复generate_report()中KDJ/BOLL旧字段名 | stock_query.py | 无 | Markdown报告中指标值正确显示 |

**关键里程碑**：所有高优先级项完成，分析结果正确性和运行时稳定性得到保障。

**所需资源**：1名开发人员，无需新增第三方依赖。

### 阶段二：提升精确性（中优先级项）

**目标**：增加分析维度，完善策略逻辑，提升分析精确性。

| 任务编号 | 任务内容 | 涉及模块 | 依赖 | 交付物 |
|----------|----------|----------|------|--------|
| 2.1 | 止损止盈策略使用ATR | analyzer.py | 无 | ATR-based止损逻辑 |
| 2.2 | 修复资金流向评分中成交额缺失 | stock_query.py, analyzer.py | 无 | 成交额字段正确传递 |
| 2.3 | 情绪分析增加大盘维度 | analyzer.py | 无 | 大盘涨跌评分 |
| 2.4 | ST股判断改为基于股票名称 | stock_query.py | 无 | clean_data()增加stock_name参数 |
| 2.5 | 数据库缓存TTL机制 | data_fetcher.py | 无 | 缓存过期逻辑 |
| 2.6 | 修正裸except捕获 | report_generator.py | 无 | 具体异常类型捕获 |
| 2.7 | 利用历史数据实现简单信号回测 | 新增backtest模块 | 无 | 信号胜率统计 |
| 2.8 | 增加评分体系说明文档 | 新增ANALYSIS_METHOD.md | 1.3 | 方法论文档 |

**关键里程碑**：止损策略基于波动率，资金流向评分真实有效，情绪分析增加大盘维度，信号质量可量化评估。

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
| I-01 | 统一BOLL访问方式 | 高 | 一 | 新旧格式兼容代码增加复杂度 |
| M-01 | RSI评分改为单周期或权重衰减 | 高 | 一 | 三周期重叠导致RSI权重放大3倍 |
| C-01 | report_generator复用指标结果 | 高 | 一 | 图表RSI用SMA与分析用Wilder不一致 |
| C-02 | 修复generate_report()旧字段名 | 高 | 一 | KDJ/BOLL值在Markdown报告中显示为N/A |
| I-02 | 止损止盈使用ATR | 中 | 二 | 固定百分比止损不适应市场波动 |
| M-03 | 修复资金流向评分成交额缺失 | 中 | 二 | 成交额为0导致评分退化为固定值 |
| M-02 | 情绪分析增加大盘维度 | 中 | 二 | 情绪分析维度单一 |
| D-03 | ST股判断改为基于股票名称 | 中 | 二 | 代码中ST判断基于股票代码，永远为False |
| D-02 | 数据库缓存TTL | 中 | 二 | 可能使用过时数据 |
| C-03 | 修正裸except | 中 | 二 | 吞掉异常不利于排查 |
| V-02 | 简单信号回测 | 中 | 二 | 信号质量无法量化 |
| DOC-01 | 评分体系说明文档 | 中 | 二 | 评分依据不透明 |
| I-03 | 增加成交量MA | 低 | 三 | 缺少量价直观判断工具 |
| V-03 | 完善评估用例 | 低 | 三 | 边界场景覆盖不足 |
| DOC-02 | 适用范围与限制说明 | 低 | 三 | 用户不了解分析边界 |

---

## 九、预期效果

| 维度 | 当前状态 | 阶段一完成后 | 阶段二完成后 | 阶段三完成后 |
|------|----------|-------------|-------------|-------------|
| 数据质量 | 验证形同虚设 | 验证真实有效 | +缓存TTL+ST判断 | — |
| 指标一致性 | 图表RSI用SMA、旧字段名 | 图表与分析一致、字段名统一 | — | +成交量MA |
| 评分正确性 | RSI权重放大3倍、资金评分退化 | RSI权重合理 | +资金评分有效+ATR止损 | — |
| 分析维度 | 情绪仅换手率+量比 | — | +大盘情绪+ATR止损 | — |
| 报告显示 | KDJ/BOLL显示N/A | 指标值正确显示 | — | — |
| 结果可信度 | 验证无效、无回测 | 验证有效 | +信号回测 | +边界覆盖 |

> **核心结论**：阶段一的5项修复是当前最紧迫的工作，其中**report_generator中RSI仍用SMA（C-01）**和**generate_report()中KDJ/BOLL旧字段名（C-02）**是影响最大的两个问题——前者导致图表与分析数据矛盾，后者导致Markdown报告中KDJ和BOLL值始终显示为"N/A"。修复这两项后，分析结果的基本正确性和显示完整性将得到保障。
