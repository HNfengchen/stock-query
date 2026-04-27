# 量化分析审查

## 优先级定义

| 级别 | 判断依据 |
|------|----------|
| 高 | 计算错误/数据污染/运行时崩溃/数学错误 |
| 中 | 精确性偏差/评分可优化/维度缺失/验证缺失 |
| 低 | 代码风格/文档/性能/边界处理 |

---

## 一、数据采集与预处理

| # | 问题 | 位置 | 级别 | 状态 | 方案 |
|---|------|------|------|------|------|
| D-01 | `validate_data({}, {})`传入空字典，data_quality字段无意义 | data_fetcher.py L260 | 高 | ✅已修复 | 传入xtquant和efinance的info分别验证 |
| D-02 | `get_history_data()`调用`clean_data()`未传stock_name，ST股阈值在efinance/baostock路径下不生效 | stock_query.py L464,486,524 | ✅已修复 | 增加stock_name参数传递 |
| D-03 | 数据库缓存无TTL，可能使用过时数据 | database.py | ⏳待处理 | 利用get_trading_calendar()判断数据新鲜度 |

---

## 二、指标体系

| # | 问题 | 位置 | 级别 | 状态 | 方案 |
|---|------|------|------|------|------|
| I-01 | `_prepare_technical_data()`中RSI用SMA计算，与technical_indicators.py的Wilder平滑不一致 | report_generator.py L225-226 | ✅已修复 | 将indicators字典传入，复用calculate_all_indicators()的series数据 |
| I-02 | `_prepare_technical_data()`中KDJ硬编码2/3+1/3平滑系数，配置修改m1后图表与分析不一致 | report_generator.py L244-245 | ✅已修复 | 同I-01，复用indicators结果 |
| I-03 | 缺少成交量MA指标 | technical_indicators.py | ✅已修复 | pandas rolling().mean() |

---

## 三、分析模型

| # | 问题 | 位置 | 级别 | 状态 | 方案 |
|---|------|------|------|------|------|
| M-01 | 未提供成本价时`avg_cost=current_price*0.95`硬编码，cost_provided字段未在报告模板中使用 | analyzer.py L652; report_template.html | ✅已修复 | 模板增加cost_provided条件判断，显示提示 |

---

## 四、计算逻辑

| # | 问题 | 位置 | 级别 | 状态 | 方案 |
|---|------|------|------|------|------|
| C-01 | BOLL新旧格式兼容代码冗余（3处else分支永不执行） | analyzer.py L108-111,L680-682,L800-802; report_generator.py L653-656; stock_query.py L731-734 | ✅已修复 | 统一使用boll.get("latest",{}).get("upper")，移除else分支 |

---

## 五、结果验证

| # | 问题 | 位置 | 级别 | 状态 | 方案 |
|---|------|------|------|------|------|
| V-01 | 同D-01 | data_fetcher.py | ✅已修复 | - |
| V-02 | 无信号回测，胜率/盈亏比未知 | - | ⏳待处理 | efinance获取历史数据+pandas模拟信号 |
| V-03 | evals.json评估用例过于简单 | evals.json | ⏳待处理 | 增加边界场景 |

---

## 六、文档

| # | 问题 | 级别 | 状态 | 方案 |
|---|------|------|------|------|
| DOC-01 | 评分权重/阈值/分值无说明文档 | 中 | ⏳待处理 | 新增ANALYSIS_METHOD.md |
| DOC-02 | 适用范围与限制未说明 | 低 | ⏳待处理 | 补充README章节 |

---

## 实施路线

### 阶段一（高优先级）✅已完成

| 任务 | 模块 | 交付物 |
|------|------|--------|
| D-01: 数据验证传入实际数据 | data_fetcher.py | validate_data()接收真实数据 |
| I-01: report_generator复用指标结果 | report_generator.py | _prepare_technical_data()接收indicators字典 |

里程碑：数据验证有效，图表与分析数据一致。

### 阶段二（中优先级）🔄进行中

| 任务 | 模块 | 状态 |
|------|------|------|
| D-02: get_history_data()传入stock_name | stock_query.py | ✅已完成 |
| M-01: 报告模板增加cost_provided提示 | report_template.html | ✅已完成 |
| C-01: 移除BOLL兼容代码 | analyzer.py, report_generator.py, stock_query.py | ✅已��成 |
| D-03: 数据库缓存TTL | database.py | ⏳待处理 |
| V-02: 简单信号回测 | 新增backtest模块 | ⏳待处理 |
| DOC-01: 评分体系说明 | 新增ANALYSIS_METHOD.md | ⏳待处理 |

里程碑：ST股全覆盖，代码简化，信号质量可量化。

### 阶段三（低优先级）

| 任务 | 模块 | 状态 |
|------|------|------|
| I-03: 成交量MA | technical_indicators.py | ✅已完成 |
| V-03: 完善evals.json | evals.json | ⏳待处理 |
| DOC-02: 适用范围说明 | README.md | ⏳待处理 |

---

## 预期效果

| 维度 | 当前 | 阶段一后 | 阶段二后 | 阶段三后 |
|------|------|----------|----------|----------|
| 数据质量 | 验证无效 | 验证有效 | +TTL+ST全覆盖 | - |
| 指标一致性 | 图表RSI用SMA | 一致 | +兼容代码清理 | +成交量MA |
| 策略可靠性 | 成本价提示缺失 | - | +提示 | - |
| 结果可信度 | 无回测 | - | +回测 | +边界覆盖 |