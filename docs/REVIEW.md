# 量化分析方案审查与改进建议

> 审查日期：2025年7月
> 审查范围：stock-query 项目全部核心模块（基于最新代码）
> 审查目标：识别改进空间，提升分析结果精确性
> 接口约束：所有改进建议严格限定在项目已使用的接口范围内

---

## 已实施改进确认

相较于初始版本，以下改进已落地实施：

| 改进项                           | 状态      | 实施位置                                    |
| -------------------------------- | --------- | ------------------------------------------- |
| 数据清洗（停牌过滤、异常值检测） | ✅ 已实施 | stock_query.py `clean_data()`             |
| 统一前复权                       | ✅ 已实施 | 三个数据源均改为前复权                      |
| ATR指标计算                      | ✅ 已实施 | technical_indicators.py `calculate_atr()` |
| RSI改用Wilder平滑                | ✅ 已实施 | technical_indicators.py `calculate_rsi()` |
| KDJ初始值设为50                  | ✅ 已实施 | technical_indicators.py `calculate_kdj()` |
| OBV指标                          | ✅ 已实施 | technical_indicators.py `calculate_obv()` |
| BOLL纳入评分                     | ✅ 已实施 | analyzer.py `analyze_technical()`         |
| 均线排列判断                     | ✅ 已实施 | analyzer.py `analyze_technical()`         |
| 评分归一化修正                   | ✅ 已实施 | analyzer.py `analyze_technical()`         |
| 资金流向相对指标                 | ✅ 已实施 | analyzer.py `analyze_fund_flow()`         |
| 持仓成本用户输入                 | ✅ 已实施 | cli.py `--cost` 参数                      |
| 涨跌停校验                       | ✅ 已实施 | analyzer.py `get_limit_pct()`             |
| 数据质量标记                     | ✅ 已实施 | data_fetcher.py `data_quality` 字段       |

---

## 项目现有接口资源清单

| 数据源   | 可用方法                                               | 用途                            |
| -------- | ------------------------------------------------------ | ------------------------------- |
| efinance | `get_base_info()` / `get_base_info(code)`          | 全量股票列表 / 单只股票基本信息 |
| efinance | `get_quote_snapshot(code)`                           | 实时行情快照                    |
| efinance | `get_history_bill(code)`                             | 历史资金流向（日线）            |
| efinance | `get_today_bill(code)`                               | 当日分钟级资金流向              |
| efinance | `get_quote_history(code, klt=1, fqt=1)`              | 分钟K线（前复权）               |
| efinance | `get_quote_history(code, klt=101, fqt=1)`            | 日K线（前复权）                 |
| xtquant  | `download_history_data()`                            | 下载历史数据                    |
| xtquant  | `get_market_data()`                                  | 获取行情数据                    |
| xtquant  | `get_instrument_detail()`                            | 合约基本信息                    |
| xtquant  | `get_sector_list()` / `get_stock_list_in_sector()` | 板块列表 / 成分股               |
| xtquant  | `get_financial_data()`                               | 财务数据                        |
| xtquant  | `get_holidays()` / `get_trading_calendar()`        | 节假日 / 交易日历               |
| baostock | `query_history_k_data_plus()`                        | 历史K线（降级兜底）             |
| 计算库   | pandas / numpy                                         | 数据处理与数值计算              |

---

## 优先级定义与判断依据

| 级别         | 定义                                     | 判断依据                                                                                                                 |
| ------------ | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **高** | 直接影响分析结果正确性或导致运行时错误   | ① 计算逻辑错误导致结果失真；② 数据质量问题直接污染指标计算；③ 类型不一致导致运行时崩溃；④ 评分体系数学错误           |
| **中** | 影响分析精确性但不致结果完全错误的问题   | ① 指标计算与主流标准存在偏差；② 评分体系可优化但当前可运行；③ 缺少可增强分析维度的指标；④ 验证机制缺失但不影响主流程 |
| **低** | 优化体验或代码质量但不影响分析结果的问题 | ① 代码风格与可维护性优化；② 文档完善；③ 性能优化；④ 边界场景处理                                                     |

---

## 一、数据采集与预处理环节

### 1.1 发现的问题

#### 问题1：数据清洗涨跌幅阈值过滤了合法涨停/跌停数据 [高]

`clean_data()` 使用15%阈值过滤涨跌幅，会误删创业板/科创板涨停（20%）的正常数据：

```python
# stock_query.py L58
df = df[(pct_col > -15) & (pct_col < 15)]
```

**风险**：创业板（30开头）和科创板（68开头）涨跌停为±20%，主板ST股为±5%。固定15%阈值会：

- 误删创业板/科创板涨停日的数据（涨跌幅=20%）
- 误删主板正常涨停日的数据（涨跌幅=10%）
- 删除这些关键行情日会导致技术指标在突破点处缺失

**可操作方案**：根据股票代码判断板块，设定不同的涨跌幅阈值。主板±11%（留余量）、创业板/科创板±21%、ST股±6%。纯逻辑判断，无需新接口。

#### 问题2：数据交叉验证传入空字典，形同虚设 [高]

`fetch_all_data()` 中调用验证时传入空字典：

```python
# data_fetcher.py L257
validator_result = self.validate_data({}, {})  # 两个参数都是空字典
```

`DataValidator.cross_validate()` 接收两个空字典，无法进行任何有意义的比较，验证结果恒为默认值。

**风险**：数据质量标记 `data_quality` 始终基于无效验证，无法真正反映数据可信度。

**可操作方案**：将 xtquant 获取的数据和 efinance 获取的数据分别作为两个参数传入，实现真正的交叉验证。两个数据源的数据在 `fetch_all_data()` 中均已获取。

### 1.2 改进建议

| 编号 | 改进措施                                                      | 优先级 | 实现方式                                       | 预期效果                                  |
| ---- | ------------------------------------------------------------- | ------ | ---------------------------------------------- | ----------------------------------------- |
| D-01 | 涨跌幅阈值按板块区分（主板±11%、创业板/科创板±21%、ST±6%） | 高     | 根据股票代码前缀判断板块，设定对应阈值         | 保留合法涨停/跌停数据，避免关键行情日缺失 |
| D-02 | 数据交叉验证传入实际数据源                                    | 高     | 将xtquant和efinance数据分别传入validate_data() | 数据质量标记真实有效                      |

---

## 二、指标体系构建

### 2.1 发现的问题

#### 问题1：MACD和BOLL返回类型未统一 [高]

部分指标已统一为 `{"latest": float, "series": pd.Series, "signal": str}` 结构，但 MACD 和 BOLL 仍返回原始 pd.Series：

```python
# MACD 返回（未统一）
calculate_macd() → {"DIF": pd.Series, "DEA": pd.Series, "MACD": pd.Series, "signal": str}

# BOLL 返回（未统一）
calculate_boll() → {"upper": pd.Series, "middle": pd.Series, "lower": pd.Series}

# RSI 已统一
calculate_rsi() → {"RSI(6)": {"latest": float, "series": pd.Series, "signal": str}, ...}

# KDJ 已统一
calculate_kdj() → {"latest": {...}, "series": {...}, "signal": str}
```

**风险**：

- 上游代码需要大量 `hasattr(value, "iloc")` / `isinstance(value, pd.Series)` 类型判断
- `analyzer.py` 第101-109行对BOLL做了6行类型转换代码，第611-613行对RSI做了兼容处理
- `report_generator.py` 第644-654行对RSI/KDJ做了复杂的嵌套类型判断
- 类型不一致是当前代码中最主要的运行时错误来源

**可操作方案**：统一 MACD 返回 `{"latest": {"DIF": float, "DEA": float, "MACD": float}, "series": {"DIF": pd.Series, ...}, "signal": str}`；BOLL 返回 `{"latest": {"upper": float, "middle": float, "lower": float}, "series": {"upper": pd.Series, ...}}`。纯重构，无新依赖。

#### 问题2：缺少成交量MA指标 [中]

当前有OBV和量比两个成交量指标，但缺少成交量移动平均线（VOL-MA），这是判断放量/缩量的直观工具。

**可操作方案**：在 `calculate_volume_ratio()` 基础上增加成交量MA计算，仅需 `rolling().mean()`，pandas原生支持。

#### 问题3：ATR未用于止损止盈策略 [中]

ATR指标已实现并计算，`predict_price_range()` 中已使用ATR值替代布林带宽度作为价格区间，但 `generate_position_strategy()` 和 `generate_buy_strategy()` 的止损价设置仍使用固定百分比：

```python
# analyzer.py L630-631 止损止盈用固定百分比
target_price = current_price * (1 + stop_profit_pct / 100)
stop_price = current_price * (1 + stop_loss_pct / 100)

# analyzer.py L732 买入止损用固定比例
risk_price = current_price * 0.95
```

**可操作方案**：利用已计算的ATR值设定止损位（如止损价=当前价-2×ATR），使止损距离与市场波动率挂钩。

### 2.2 改进建议

| 编号 | 改进措施               | 优先级 | 实现方式                                 | 预期效果                     |
| ---- | ---------------------- | ------ | ---------------------------------------- | ---------------------------- |
| I-01 | 统一MACD和BOLL返回类型 | 高     | 重构为{"latest", "series", "signal"}结构 | 消除类型不一致，简化上游代码 |
| I-02 | 增加成交量MA指标       | 中     | pandas rolling().mean()                  | 判断放量/缩量更直观          |
| I-03 | 止损止盈策略使用ATR    | 中     | 止损价=当前价-N×ATR                     | 止损距离与波动率挂钩         |

---

## 三、分析模型与算法选择

### 3.1 发现的问题

#### 问题1：评分归一化范围与实际分数不匹配 [高]

BOLL评分（±10）和均线排列评分（±10）已加入评分体系，但归一化范围仍为[-70, 70]：

```python
# analyzer.py L148-149
MIN_SCORE = -70
MAX_SCORE = 70
```

实际最大正分 = 25(MACD金叉) + 10×3(三个RSI超卖) + 15(KDJ金叉) + 10(BOLL超卖) + 10(多头排列) = **90**
实际最大负分 = -25 - 30 - 15 - 10 - 10 = **-90**

**风险**：评分超过70的部分被截断，BOLL和均线排列的评分贡献被压缩，区分度降低。

**可操作方案**：更新 `MIN_SCORE = -90`，`MAX_SCORE = 90`，纯数值修正。

#### 问题2：持仓策略中RSI字段名不一致 [高]

`generate_position_strategy()` 访问RSI数据时使用旧字段名 `"value"`：

```python
# analyzer.py L611
rsi_value = rsi.get("RSI(12)", {}).get("value")  # 旧字段名
```

但 `calculate_rsi()` 已改为返回 `"latest"` 字段：

```python
# technical_indicators.py L122
result[f"RSI({period})"] = {"latest": latest, "series": rsi_series[period], "signal": signal}
```

**风险**：`rsi_value` 始终为 `None`，导致持仓策略中基于RSI的判断逻辑（建议减仓/可考虑补仓）永远不会触发。

**可操作方案**：将 `"value"` 改为 `"latest"`，一行代码修复。

#### 问题3：情绪分析维度单一 [中]

当前情绪分析仅考虑换手率和量比，缺少大盘环境参考。

**可操作方案**：利用 efinance 的 `get_quote_snapshot('000001')` 获取上证指数涨跌作为大盘参考，在现有接口范围内可实现。

### 3.2 改进建议

| 编号 | 改进措施                           | 优先级 | 实现方式                              | 预期效果                    |
| ---- | ---------------------------------- | ------ | ------------------------------------- | --------------------------- |
| M-01 | 更新评分归一化范围为[-90, 90]      | 高     | 修改MIN_SCORE和MAX_SCORE常量          | BOLL和均线评分不被截断      |
| M-02 | 修复RSI字段名（"value"→"latest"） | 高     | 一行代码修改                          | 持仓策略RSI判断逻辑恢复工作 |
| M-03 | 情绪分析增加大盘维度               | 中     | efinance get_quote_snapshot('000001') | 情绪分析更全面              |

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

**风险**：图表中显示的RSI值与报告中分析使用的RSI值不一致，用户无法验证分析结果。

**可操作方案**：复用 `calculate_all_indicators()` 的计算结果传入图表数据准备方法，消除重复计算并保证一致性。

#### 问题2：report_generator中KDJ计算与technical_indicators不一致 [高]

`_prepare_technical_data()` 中KDJ使用列表递推计算，但平滑系数与 `technical_indicators.py` 不同：

```python
# report_generator.py L244-245
k[i] = 2/3 * k[i-1] + 1/3 * rsv.iloc[i]  # 硬编码 2/3 和 1/3

# technical_indicators.py L174
k.iloc[i] = (k.iloc[i-1] * (m1-1) + rsv.iloc[i]) / m1  # 使用 m1 参数
```

当 `m1=3` 时两者等价，但如果配置修改了 `m1` 参数，report_generator 的图表将与分析结果不一致。

**可操作方案**：同问题1，复用 `calculate_all_indicators()` 的结果。

#### 问题3：多处裸except捕获 [中]

`analyzer.py` 中仍有多处裸 `except` 或 `except:` 捕获：

```python
# analyzer.py L263
except:
    pass

# analyzer.py L275
except:
    pass

# analyzer.py L357
except:
    current_price = 0
```

**风险**：吞掉所有异常（包括 `KeyboardInterrupt`），不利于问题排查。

**可操作方案**：改为 `except Exception as e` 并记录日志。

#### 问题4：format_number中裸except [低]

```python
# stock_query.py L549
except:
    return str(value)
```

### 4.2 改进建议

| 编号 | 改进措施                                         | 优先级 | 实现方式                                      | 预期效果               |
| ---- | ------------------------------------------------ | ------ | --------------------------------------------- | ---------------------- |
| C-01 | report_generator复用technical_indicators计算结果 | 高     | 将indicators字典传入_prepare_technical_data() | 图表数据与分析数据一致 |
| C-02 | 修正裸except捕获                                 | 中     | 改为except Exception as e + 日志记录          | 便于问题排查           |
| C-03 | format_number裸except修正                        | 低     | 改为except (ValueError, TypeError)            | 规范异常处理           |

---

## 五、结果验证与评估

### 5.1 发现的问题

#### 问题1：数据验证传入空字典 [高]

（与1.1问题2重复，此处从验证角度分析）

当前验证调用 `self.validate_data({}, {})` 传入空字典，验证结果无意义。`data_quality` 字段始终为 `"validated"` 或 `"unknown"`，无法区分真实的数据质量差异。

#### 问题2：无信号准确性验证 [中]

交易信号的准确性完全未经验证，无胜率/盈亏比统计。

**可操作方案**：利用 efinance 的 `get_quote_history()` 获取历史数据，在本地模拟历史信号生成，统计信号后N日收益，纯pandas计算可实现简单回测。

#### 问题3：evals.json评估用例过于简单 [低]

评估用例仅验证"能否生成报告"，未验证计算正确性和边界情况。

### 5.2 改进建议

| 编号 | 改进措施                     | 优先级 | 实现方式                            | 预期效果             |
| ---- | ---------------------------- | ------ | ----------------------------------- | -------------------- |
| V-01 | 修复数据验证传入实际数据     | 高     | 传入xtquant和efinance的实际数据     | 数据质量标记真实有效 |
| V-02 | 利用历史数据实现简单信号回测 | 中     | efinance获取历史数据+pandas模拟信号 | 量化评估信号质量     |
| V-03 | 完善evals.json评估用例       | 低     | 增加边界场景测试描述                | 提升系统鲁棒性       |

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

| 编号   | 改进措施                     | 优先级 | 实现方式               | 预期效果           |
| ------ | ---------------------------- | ------ | ---------------------- | ------------------ |
| DOC-01 | 增加评分体系说明文档         | 中     | 新增ANALYSIS_METHOD.md | 评分体系透明可审计 |
| DOC-02 | 在README中增加适用范围与限制 | 低     | 补充README章节         | 用户明确分析边界   |

---

## 七、实施路线

### 阶段一：修复正确性错误（高优先级项）

**目标**：修复影响分析结果正确性和运行时稳定性的问题。

| 任务编号 | 任务内容                           | 涉及模块                | 依赖 | 交付物                                 |
| -------- | ---------------------------------- | ----------------------- | ---- | -------------------------------------- |
| 1.1      | 涨跌幅阈值按板块区分               | stock_query.py          | 无   | 修改后的clean_data()                   |
| 1.2      | 数据交叉验证传入实际数据           | data_fetcher.py         | 无   | 修复后的validate_data()调用            |
| 1.3      | 统一MACD和BOLL返回类型             | technical_indicators.py | 无   | 统一的{"latest","series","signal"}结构 |
| 1.4      | 修复RSI字段名（"value"→"latest"） | analyzer.py             | 无   | 一行代码修复                           |
| 1.5      | 更新评分归一化范围为[-90, 90]      | analyzer.py             | 无   | 修改MIN_SCORE/MAX_SCORE                |
| 1.6      | report_generator复用指标计算结果   | report_generator.py     | 1.3  | 消除重复计算                           |

**关键里程碑**：所有高优先级项完成，分析结果正确性和运行时稳定性得到保障。

**所需资源**：1名开发人员，无需新增第三方依赖。

### 阶段二：提升精确性（中优先级项）

**目标**：增加分析维度，完善策略逻辑，提升分析精确性。

| 任务编号 | 任务内容                     | 涉及模块                    | 依赖 | 交付物                 |
| -------- | ---------------------------- | --------------------------- | ---- | ---------------------- |
| 2.1      | 止损止盈策略使用ATR          | analyzer.py                 | 无   | ATR-based止损逻辑      |
| 2.2      | 增加成交量MA指标             | technical_indicators.py     | 无   | calculate_vol_ma()函数 |
| 2.3      | 情绪分析增加大盘维度         | analyzer.py                 | 无   | 大盘涨跌评分           |
| 2.4      | 数据库缓存TTL机制            | data_fetcher.py             | 无   | 缓存过期逻辑           |
| 2.5      | 修正裸except捕获             | analyzer.py, stock_query.py | 无   | 具体异常类型捕获       |
| 2.6      | 利用历史数据实现简单信号回测 | 新增backtest模块            | 无   | 信号胜率统计           |
| 2.7      | 增加评分体系说明文档         | 新增ANALYSIS_METHOD.md      | 1.5  | 方法论文档             |

**关键里程碑**：止损策略基于波动率，情绪分析增加大盘维度，信号质量可量化评估。

**所需资源**：1名开发人员，无需新增第三方依赖。

### 阶段三：体验优化（低优先级项）

**目标**：完善边界处理、文档和评估体系。

| 任务编号 | 任务内容                     | 涉及模块   | 依赖 | 交付物       |
| -------- | ---------------------------- | ---------- | ---- | ------------ |
| 3.1      | 完善evals.json评估用例       | evals.json | 无   | 边界场景测试 |
| 3.2      | 在README中增加适用范围与限制 | README.md  | 无   | 限制说明章节 |

**关键里程碑**：边界场景覆盖完善，文档齐全。

---

## 八、改进项总览

| 编号   | 改进措施                     | 优先级 | 阶段 | 判断依据                          |
| ------ | ---------------------------- | ------ | ---- | --------------------------------- |
| D-01   | 涨跌幅阈值按板块区分         | 高     | 一   | 固定15%阈值误删合法涨停数据       |
| D-02   | 数据交叉验证传入实际数据     | 高     | 一   | 传入空字典导致验证形同虚设        |
| I-01   | 统一MACD和BOLL返回类型       | 高     | 一   | 类型不一致是主要运行时错误来源    |
| M-02   | 修复RSI字段名                | 高     | 一   | 字段名不一致导致RSI判断永远不触发 |
| M-01   | 更新评分归一化范围           | 高     | 一   | BOLL和均线评分被截断              |
| C-01   | report_generator复用指标结果 | 高     | 一   | 图表RSI用SMA与分析用Wilder不一致  |
| I-03   | 止损止盈使用ATR              | 中     | 二   | 固定百分比止损不适应市场波动      |
| I-02   | 增加成交量MA                 | 中     | 二   | 缺少量价直观判断工具              |
| M-03   | 情绪分析增加大盘维度         | 中     | 二   | 情绪分析维度单一                  |
| D-03   | 数据库缓存TTL                | 中     | 二   | 可能使用过时数据                  |
| C-02   | 修正裸except                 | 中     | 二   | 吞掉异常不利于排查                |
| V-02   | 简单信号回测                 | 中     | 二   | 信号质量无法量化                  |
| DOC-01 | 评分体系说明文档             | 中     | 二   | 评分依据不透明                    |
| V-03   | 完善评估用例                 | 低     | 三   | 边界场景覆盖不足                  |
| DOC-02 | 适用范围与限制说明           | 低     | 三   | 用户不了解分析边界                |
| C-03   | format_number异常处理        | 低     | 三   | 规范性不足                        |

---

## 九、预期效果

| 维度       | 当前状态                           | 阶段一完成后                 | 阶段二完成后      | 阶段三完成后 |
| ---------- | ---------------------------------- | ---------------------------- | ----------------- | ------------ |
| 数据质量   | 涨幅阈值误删合法数据、验证形同虚设 | 阈值按板块区分、验证真实有效 | +缓存TTL保障时效  | —           |
| 指标一致性 | 图表RSI用SMA、类型不统一           | 图表与分析一致、类型统一     | +成交量MA         | —           |
| 评分正确性 | RSI判断失效、归一化截断            | RSI判断恢复、归一化修正      | +ATR止损          | —           |
| 分析维度   | 情绪仅换手率+量比                  | —                           | +大盘情绪+ATR止损 | —           |
| 结果可信度 | 验证无效、无回测                   | 验证有效                     | +信号回测         | +边界覆盖    |

> **核心结论**：阶段一的6项修复是当前最紧迫的工作，其中**RSI字段名不一致（M-02）**和**涨跌幅阈值误删合法数据（D-01）**是影响最大的两个问题——前者导致持仓策略中RSI判断完全失效，后者导致涨停日数据被错误删除。修复这两项后，分析结果的基本正确性将得到保障。
