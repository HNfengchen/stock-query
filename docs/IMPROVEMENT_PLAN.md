# Stock Query 量化分析系统改进方案

> **生成日期：** 2026年4月20日
> **目标：** 基于 REVIEW.md 的改进建议，制定阶段一（高优先级）+阶段二（中优先级）的具体可实施计划
> **时间范围：** 1-2周
> **风险偏好：** 平衡

---

## 一、改进目标与背景

### 1.1 项目现状

Stock Query 项目是一个A股量化分析工具，主要功能包括：
- 数据获取：efinance、xtquant、baostock 三个数据源
- 技术指标计算：MACD、RSI、KDJ、MA、BOLL等
- 分析逻辑：技术评分、资金流向评分、市场情绪评分
- 报告生成：HTML可视化报告

### 1.2 核心问题域

基于 REVIEW.md 的分析，主要问题集中在：

| 问题域 | 当前状态 | 影响程度 |
|--------|----------|----------|
| 数据质量 | 无清洗、无验证 | 高 |
| 指标准确性 | ATR缺失、归一化截断 | 高 |
| 计算逻辑 | 类型不一致、绝对值阈值 | 高 |
| 分析维度 | BOLL未参与评分、缺OBV | 中 |

### 1.3 改进目标

**阶段一目标：数据基础加固（高优先级）**
- 实现数据清洗：过滤停牌日、异常值检测
- 统一使用前复权数据
- 实现ATR指标计算（配置已引用但未实现）
- 统一技术指标返回类型
- 修正评分归一化公式
- 资金流向评分改用相对指标
- 持仓成本改为用户可选输入
- 启用DataValidator交叉验证

**阶段二目标：分析精确性提升（中优先级）**
- RSI改用Wilder平滑方法
- KDJ初始值显式设为50
- 增加OBV指标
- BOLL纳入技术评分
- 增加均线排列判断
- 价格预测增加涨跌停校验
- 关键字段缺失标记数据质量
- 消除report_generator重复计算
- 简单信号回测（可选）

---

## 二、改进项详细设计

### 2.1 数据清洗模块（D-01）

**问题描述：**
当前代码从数据源获取数据后直接使用，未进行任何数据清洗。停牌日成交量为0或NaN，直接参与技术指标计算将导致MA、BOLL等指标失真。

**实现方案：**
在 `stock_query.py` 中新增数据清洗函数：

```python
def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    数据清洗：过滤停牌日、检测异常值
    
    处理步骤：
    1. 过滤成交量<=0或为NaN的行（停牌日）
    2. 基于3σ原则检测价格异常值
    3. 填充必要的缺失值
    """
    # 过滤停牌日
    df = df[df["成交量"] > 0]
    df = df.dropna(subset=["成交量", "收盘"])
    
    # 3σ异常值检测
    for col in ["收盘", "最高", "最低"]:
        mean = df[col].mean()
        std = df[col].std()
        df = df[(df[col] >= mean - 3*std) & (df[col] <= mean + 3*std)]
    
    return df
```

**涉及文件：**
- 修改：`scripts/stock_query.py` - 新增 clean_data 函数
- 修改：`scripts/database.py` - 在 get_or_fetch_stock_data 中调用清洗

### 2.2 统一前复权数据（D-02）

**问题描述：**
三个数据源的复权方式不统一，技术指标计算基于不复权数据，在除权除息日会产生虚假的价格跳空。

**实现方案：**
修改各数据源的复权参数：

| 数据源 | 当前 | 修改后 |
|--------|------|--------|
| efinance 日K线 | fqt=0（不复权） | fqt=1（前复权） |
| xtquant | dividend_type="none" | dividend_type="front" |
| baostock | adjustflag="3" | adjustflag="2" |

**涉及文件：**
- 修改：`scripts/stock_query.py` - get_history_data() 中的复权参数
- 修改：`scripts/core/data_fetcher.py` - xtquant 数据获��

### 2.3 ATR指标计算（I-01）

**问题描述：**
`config.yaml` 中有 `atr_multiplier` 配置项，但实际未计算ATR指标，导致止损止盈价位设置缺乏波动率依据。

**实现方案：**
在 `technical_indicators.py` 中新增 calculate_atr 函数：

```python
def calculate_atr(
    high_prices: Union[List, pd.Series,
    low_prices: Union[List, pd.Series,
    close_prices: Union[List, pd.Series],
    period: int = 14
) -> Dict:
    """
    计算ATR（Average True Range）指标
    
    True Range = max(
        高-低,
        |高-前一收盘|,
        |低-前一收盘|
    )
    ATR = TR的N周期简单移动平均
    """
    high = pd.Series(high_prices)
    low = pd.Series(low_prices)
    close = pd.Series(close_prices)
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean().round(2)
    
    latest = atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else None
    status = "波动剧烈" if latest and latest > current_price * 0.03 else "正常"
    
    return {"atr": atr, "latest": latest, "status": status}
```

**涉及文件：**
- 修改：`scripts/technical_indicators.py` - 新增 calculate_atr 函数
- 修改：`scripts/technical_indicators.py` - calculate_all_indicators 中调用

### 2.4 统一技术指标返回类型（C-01）

**问题描述：**
当前各指标返回值类型不一致：
- MACD 返回 `{"DIF": pd.Series, ...}`
- RSI 返回 `{"RSI(6)": {"value": pd.Series, "status": str}, ...}`
- MA 返回 `{"MA5": pd.Series, ...}`
- 量比返回 `{"volume_ratio": float, ...}`

**实现方案：**
统一返回结构为 `{"latest": float, "series": pd.Series, "signal": str}`：

```python
def calculate_rsi(...) -> Dict:
    # 现有逻辑...
    return {
        "RSI(6)": {"latest": rsi6_latest, "series": rsi6_series, "signal": rsi6_status},
        "RSI(12)": {...},
        "RSI(24)": {...},
    }
```

**涉及文件：**
- 修改：`scripts/technical_indicators.py` - 所有指标计算函数
- 修改：`scripts/core/analyzer.py` - 指标调用处适配新类型

### 2.5 修正评分归一化公式（M-01）

**问题描述：**
当前公式 `(score + 50) / 100` 假设范围[-50, 50]，但实际最大正分=70、最大负分=-70，导致强信号被截断。

**实现方案：**
基于实际分数范围归一化：

```python
# analyzer.py - analyze_technical()
# 最大正分: 25(MACD) + 30(3个RSI超卖) + 15(KDJ) = 70
# 最大负分: -25(MACD) - 30(3个RSI超买) - 15(KDJ) = -70
MIN_SCORE = -70
MAX_SCORE = 70

normalized_score = (score - MIN_SCORE) / (MAX_SCORE - MIN_SCORE)
normalized_score = max(0, min(1, normalized_score))
```

**涉及文件：**
- 修改：`scripts/core/analyzer.py` - analyze_technical()

### 2.6 资金流向评分改用相对指标（M-02）

**问题描述：**
当前使用绝对值阈值（>10000元），未考虑市值差异。1万元对大盘股微不足道，对小盘股可能显著。

**实现方案：**
计算相对指标（主力净流入/成交额）：

```python
def analyze_fund_flow(self, fund_flow: Dict) -> Dict:
    main_inflow = fund_flow.get("主力净流入", 0)
    amount = fund_flow.get("成交额", 1)
    
    # 相对流入率
    inflow_ratio = main_inflow / amount if amount else 0
    
    if inflow_ratio > 0.05:  # >5% 成交额
        score = 1.0
    elif inflow_ratio > 0.02:
        score = 0.7
    elif inflow_ratio > 0:
        score = 0.4
    elif inflow_ratio < -0.05:
        score = 0
    # ... 
```

**涉及文件：**
- 修改：`scripts/core/analyzer.py` - analyze_fund_flow()

### 2.7 持仓成本改为用户可选输入（M-03）

**问题描述：**
当前硬编码 `avg_cost = current_price * 0.95`，基于虚假成本价计算的盈亏比例、止盈止损策略全部失真。

**实现方案：**
1. cli.py 增加 `--cost` 参数
2. analyzer.py 接收 cost 参数，未提供时标注"仅供参考"

```bash
# 使用示例
./analyze_report.sh 000001 已持有 --cost 10.50
```

**涉及文件：**
- 修改：`scripts/cli.py` - 添加 --cost 参数解析
- 修改：`scripts/core/analyzer.py` - generate_position_strategy() 接收 cost

### 2.8 启用DataValidator交叉验证（V-01）

**问题描述：**
`xtquant_adapter.py` 中定义了 `DataValidator` 类，但在 `fetch_all_data()` 主流程中从未调用。

**实现方案：**
在数据获取流程中调用交叉验证：

```python
# database.py - get_or_fetch_stock_data()
from scripts.core.data_fetcher import DataValidator

# 获取完成后验证
if result.get("source") == "api":
    validator = DataValidator()
    is_valid = validator.cross_validate(result, db_data)
    result["data_quality"] = "validated" if is_valid else "unvalidated"
```

**涉及文件：**
- 修改：`scripts/database.py` - get_or_fetch_stock_data() 中调用验证

### 2.9 RSI改用Wilder平滑（C-02）

**问题描述：**
标准RSI计算应使用Wilder平滑方法，当前使用SMA导致RSI值与主流行情软件不一致。

**实现方案：**
将 `rolling().mean()` 替换为 `ewm(com=period-1, adjust=False).mean()`：

```python
# technical_indicators.py - calculate_rsi()
avg_gain = gain.ewm(com=period-1, adjust=False).mean()
avg_loss = loss.ewm(com=period-1, adjust=False).mean()
```

**涉及文件：**
- 修改：`scripts/technical_indicators.py` - calculate_rsi()

### 2.10 KDJ初始值修正（C-03）

**问题描述：**
标准KDJ计算中K和D的初始值应设为50，当前ewm的默认初始化可能导致前几个值偏离。

**实现方案：**
手动递推计算K/D值：

```python
# technical_indicators.py - calculate_kdj()
# 初始化K、D为50
k = pd.Series([50.0] * len(rsv))
d = pd.Series([50.0] * len(rsv))

for i in range(1, len(rsv)):
    k.iloc[i] = (k.iloc[i-1] * (m1-1) + rsv.iloc[i]) / m1
    d.iloc[i] = (d.iloc[i-1] * (m2-1) + k.iloc[i]) / m2
```

**涉及文件：**
- 修改：`scripts/technical_indicators.py` - calculate_kdj()

### 2.11 增加OBV指标（I-03）

**问题描述：**
当前仅有"量比"一个成交量指标，缺少量价配合分析能力。

**实现方案：**
在 technical_indicators.py 中新增 calculate_obv 函数：

```python
def calculate_obv(
    close_prices: Union[List, pd.Series],
    volumes: Union[List, pd.Series]
) -> Dict:
    """计算OBV（能量潮）"""
    close = pd.Series(close_prices)
    volume = pd.Series(volumes)
    
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    obv = (volume * direction).cumsum()
    
    latest = obv.iloc[-1]
    signal = "上涨" if obv.iloc[-1] > obv.iloc[-5] else "下跌"
    
    return {"obv": obv, "latest": latest, "signal": signal}
```

**涉及文件：**
- 修改：`scripts/technical_indicators.py` - 新增 calculate_obv 函数
- 修改：`scripts/technical_indicators.py` - calculate_all_indicators 中调用

### 2.12 BOLL纳入技术评分（I-02）

**问题描述：**
`analyze_technical()` 方法中获取了BOLL数据但未用于评分。

**实现方案：**
在 analyzer.py 的 analyze_technical() 中增加BOLL评分：

```python
# analyzer.py - analyze_technical()
boll = indicators.get("BOLL", {})
if current_price > upper:
    score -= 10
    signals.append("BOLL超买")
elif current_price < lower:
    score += 10
    signals.append("BOLL超卖")
elif current_price > middle:
    score += 5
    signals.append("BOLL中轨上方")
else:
    score -= 5
```

**涉及文件：**
- 修改：`scripts/core/analyzer.py` - analyze_technical()

### 2.13 增加均线排列判断（I-04）

**问题描述：**
当前MA指标仅计算各均线值，未判断均线排列状态（多头排列/空头排列/交叉）。

**实现方案：**
在 analyzer.py 中增加均线排列判断：

```python
# analyzer.py - analyze_technical()
ma = indicators.get("MA", {})
ma5 = ma.get("MA5", pd.Series()).iloc[-1]
ma10 = ma.get("MA10", pd.Series()).iloc[-1]
ma20 = ma.get("MA20", pd.Series()).iloc[-1]
ma60 = ma.get("MA60", pd.Series()).iloc[-1]

if ma5 > ma10 > ma20:
    score += 10
    signals.append("多头排列")
elif ma5 < ma10 < ma20:
    score -= 10
    signals.append("空头排列")
```

**涉及文件：**
- 修改：`scripts/core/analyzer.py` - analyze_technical()

### 2.14 价格预测涨跌停校验（M-04）

**问题描述：**
A股涨跌停限制为主板±10%、创业板/科创板±20%，当前预测价格可能超出涨跌停范围。

**实现方案：**
根据股票代码判断板块，限制预测范围：

```python
# analyzer.py - predict_price_range()
def get_limit_pct(stock_code: str) -> float:
    code = stock_code.lstrip("0")
    if code.startswith("30") or code.startswith("68"):
        return 0.20  # 创业板/科创板
    else:
        return 0.10  # 主板

limit_pct = get_limit_pct(stock_code)
# 限制预测价格不超出涨跌停
target_high = min(target_high, current_price * (1 + limit_pct))
target_low = max(target_low, current_price * (1 - limit_pct))
```

**涉及文件：**
- 修改：`scripts/core/analyzer.py` - predict_price_range()

---

## 三、实施步骤与任务分解

### 3.1 任务分解总览

| 编号 | 任务 | 优先级 | 阶段 | 依赖 | 文件 |
|------|------|--------|------|------|------|
| T-01 | 数据清洗模块 | 高 | 一 | 无 | stock_query.py |
| T-02 | 统一前复权 | 高 | 一 | 无 | stock_query.py |
| T-03 | ATR指标计算 | 高 | 一 | T-01 | technical_indicators.py |
| T-04 | 统一返回类型 | 高 | 一 | 无 | technical_indicators.py |
| T-05 | 评分归一化修正 | 高 | 一 | T-04 | analyzer.py |
| T-06 | 资金流向相对指标 | 高 | 一 | 无 | analyzer.py |
| T-07 | 持仓成本用户输入 | 高 | 一 | 无 | cli.py, analyzer.py |
| T-08 | DataValidator启用 | 高 | 一 | 无 | database.py |
| T-09 | RSI Wilder平滑 | 中 | 二 | T-04 | technical_indicators.py |
| T-10 | KDJ初始值修正 | 中 | 二 | T-04 | technical_indicators.py |
| T-11 | OBV指标 | 中 | 二 | T-01 | technical_indicators.py |
| T-12 | BOLL评分 | 中 | 二 | T-04 | analyzer.py |
| T-13 | 均线排列判断 | 中 | 二 | T-04 | analyzer.py |
| T-14 | 涨跌停校验 | 中 | 二 | 无 | analyzer.py |

### 3.2 详细实施步骤

#### 阶段一：数据基础加固（第1周）

**任务T-01：数据清洗模块**
- [ ] Step 1: 在 stock_query.py 中新增 clean_data() 函数
  - 过滤成交量<=0的行
  - 基于3σ原则过滤价格异常值
- [ ] Step 2: 在 get_history_data() 调用 clean_data()
- [ ] Step 3: 测试数据清洗效果

**任务T-02：统一前复权**
- [ ] Step 1: 修改 efinance 日K线获取参数 fqt=1
- [ ] Step 2: 修改 xtquant 数据获取参数 dividend_type="front"
- [ ] Step 3: 修改 baostock 参数 adjustflag="2"

**任务T-03：ATR指标计算**
- [ ] Step 1: 在 technical_indicators.py 新增 calculate_atr()
- [ ] Step 2: 在 calculate_all_indicators() 中调用
- [ ] Step 3: 在 analyzer.py 的 predict_price_range() 中使用ATR

**任务T-04：统一返回类型**
- [ ] Step 1: 修改 calculate_rsi() 返回结构
- [ ] Step 2: 修改 calculate_ma() 返回结构
- [ ] Step 3: 修改 calculate_volume_ratio() 返回结构
- [ ] Step 4: 更新 analyzer.py 中的指标调用

**任务T-05：评分归一化修正**
- [ ] Step 1: 计算实际最大/最小分数范围
- [ ] Step 2: 修改归一化公式
- [ ] Step 3: 测试评分区分度

**任务T-06：资金流向相对指标**
- [ ] Step 1: 修改 analyze_fund_flow() 计算相对指标
- [ ] Step 2: 使用 主力净流入/成交额 替代绝对值阈值
- [ ] Step 3: 测试不同市值股票的评分

**任务T-07：持仓成本用户输入**
- [ ] Step 1: 在 cli.py 添加 --cost 参数解析
- [ ] Step 2: 传递 cost 到 analyzer.py
- [ ] Step 3: 修改 generate_position_strategy() 接收 cost

**任务T-08：DataValidator启用**
- [ ] Step 1: 在 database.py 导入 DataValidator
- [ ] Step 2: 在 get_or_fetch_stock_data() 调用交叉验证
- [ ] Step 3: 标记数据质量

#### 阶段二：分析精确性提升（第2周）

**任务T-09：RSI Wilder平滑**
- [ ] Step 1: 修改 calculate_rsi() 使用 ewm 平滑
- [ ] Step 2: 对比验证与行情软件一致性

**任务T-10：KDJ初始值修正**
- [ ] Step 1: 修改 calculate_kdj() 手动递推
- [ ] Step 2: 验证前几个值正确

**任务T-11：OBV指标**
- [ ] Step 1: 在 technical_indicators.py 新增 calculate_obv()
- [ ] Step 2: 在 calculate_all_indicators() 中调用
- [ ] Step 3: 在 analyzer.py 中增加OBV分析

**任务T-12：BOLLL评分**
- [ ] Step 1: 在 analyze_technical() 中增加BOLL评分逻辑
- [ ] Step 2: 测试不同价格位置的评分

**任务T-13：均线排列判断**
- [ ] Step 1: 在 analyze_technical() 中增加均线排列判断
- [ ] Step 2: 测试多头/空头排列的评分

**任务T-14：涨跌停校验**
- [ ] Step 1: 新增 get_limit_pct() 函数
- [ ] Step 2: 在 predict_price_range() 中限制预测范围

---

## 四、资源需求评估

### 4.1 开发人员
- 1名开发人员
- 熟悉Python/pandas技术栈
- 了解A股交易规则

### 4.2 技术依赖
无需新增第三方依赖，全部使用现有接口和计算库。

### 4.3 测试资源
- 使用 efinance 开放接口获取真实数据测试
- 对比主流行情软件（如同花顺）验证指标一致性

---

## 五、风险分析与应对措施

### 5.1 技术风险

| 风险 | 可能性 | 影响 | 应对措施 |
|------|--------|------|----------|
| 前复权数据获取失败 | 中 | 高 | 保留原参数作为兜底 |
| ATR计算导致性能下降 | 低 | 低 | 仅计算需要的指标 |
| 评分变化导致现有策略失配 | 中 | 中 | 提供参数控制新旧逻辑 |

### 5.2 实施风险

| 风险 | 可能性 | 影响 | 应对措施 |
|------|--------|------|----------|
| 任务延期 | 中 | 中 | 优先保证高优先级任务 |
| 测试不充分 | 中 | 低 | 增加回归测试 |

### 5.3 应对策略
1. 每个任务完成后进行功能测试
2. 保留原有逻辑作为兜底
3. 使用配置开关控制新旧逻辑切换

---

## 六、验收标准

### 6.1 阶段一验收（高优先级）

| 验收项 | 标准 | 验证方式 |
|--------|------|----------|
| 数据清洗 | 停牌日数据不参与计算 | 打印数据对比 |
| 前复权 | 除权日无价格跳空 | 视觉检查K线图 |
| ATR指标 | predict_price_range使用ATR | 代码审查 |
| 返回类型 | 所有指标返回结构一致 | 接口测试 |
| 评分归一化 | 强信号不被截断 | 分数打印 |
| 相对指标 | 评分考虑市值 | 对比不同股票 |
| 持仓成本 | 支持--cost参数 | 命令行测试 |
| 交叉验证 | 数据有质量标记 | 输出检查 |

### 6.2 阶段二验收（中优先级）

| 验收项 | 标准 | 验证方式 |
|--------|------|----------|
| RSI Wilder | 与行情软件一致 | 数值对比 |
| KDJ初始值 | 前几个值为50 | 打印验证 |
| OBV指标 | 正确计算 | 数值检验 |
| BOLL评分 | 纳入评分体系 | 分数组成 |
| 均线排列 | 判断逻辑正确 | 测试用例 |
| 涨跌停 | 预测不超限 | 边界测试 |

---

## 七、预期效果

### 7.1 数据质量

| 维度 | 当前 | 改进后 |
|------|------|----------|
| 停牌日处理 | 无 | 自动过滤 |
| 异常值 | 可能存在 | 3σ过滤 |
| 前复权 | 不统一 | 统一 |
| 交叉验证 | 未启用 | 启用 |

### 7.2 指标准确性

| 指标 | 当前 | 改进后 |
|------|------|----------|
| ATR | 未实现 | 实现 |
| RSI | SMA | Wilder |
| KDJ | 递推 | 显式50 |
| OBV | 无 | 有 |
| BOLL | 未评分 | 评分 |

### 7.3 评分合理性

| 维度 | 当前 | 改进后 |
|------|------|----------|
| 归一化 | 截断 | 完整范围 |
| 资金流向 | 绝对值 | 相对比 |
| 持仓成本 | 硬编码95% | 用户输入 |

---

## 八、后续工作（低优先级）

如需继续改进，建议：
- 指标协同信号检测
- 大盘情绪维度补充
- 完善评估用例
- 文档完善

---

> **结论：** 本方案整合了 REVIEW.md 中阶段一（高优先级）和阶段二（中优先级）的改进项，共计14个任务，预计1-2周完成。方案充分利用现有接口和计算库，无需新增依赖。