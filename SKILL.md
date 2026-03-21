---
name: stock-query
description: 获取A股股票详细信息，包括基本信息、实时行情、资金流向和技术指标。当用户需要查询股票数据、分析股票行情、获取资金流向、计算技术指标（MACD、RSI、KDJ）时使用此技能。支持通过股票代码或股票名称进行查询，并生成包含交互式图表的HTML分析报告。
---

# A股股票信息查询技能

本技能基于 xtquant、efinance、AkShare 和 baostock 库，提供全面的A股股票数据查询与分析功能。

## 功能概述

当用户提供股票代码或名称时，本技能将：

1. **获取股票基本信息**：公司名称、行业分类、上市日期、总市值、流通市值、市盈率、市净率等
2. **获取实时行情数据**：分钟级开盘价、最高价、最低价、最新价、成交量、成交额、换手率、量比等
3. **获取资金流向数据**：主力资金流入流出、超大单/大单/中单/小单资金流向及历史趋势
4. **计算技术指标**：MACD、RSI、KDJ、MA、BOLL、量比等常用技术指标
5. **生成交易信号**：综合技术面、资金面、市场情绪生成买卖建议
6. **价格预测**：基于技术分析预测短期价格区间
7. **生成分析报告**：输出包含交互式图表的HTML格式分析报告

## 依赖安装

```bash
# 核心依赖
pip install akshare efinance pandas numpy pyyaml jinja2

# 可选依赖（增强数据获取能力）
pip install xtquant baostock
```

## 使用方法

### 输入格式

用户可以通过以下方式提供股票信息：

- **股票代码**：如 "000001"、"600519"、"300750"
- **股票名称**：如 "平安银行"、"贵州茅台"、"宁德时代"
- **混合格式**：如 "000001 平安银行"

### 命令行使用

```bash
# 基本用法
python -m scripts.cli <股票代码或名称>

# 示例
python -m scripts.cli 威派格
python -m scripts.cli 603956
python -m scripts.cli 威派格 --output-dir ./reports
python -m scripts.cli 威派格 --no-charts
```

### 参数说明

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| stock | - | 股票代码或名称（必填） | - |
| --config | -c | 配置文件路径 | config/config.yaml |
| --output-dir | -o | 报告输出目录 | output/reports |
| --output | -t | 输出格式（html/markdown） | html |
| --no-charts | - | 不生成图表 | false |

## 数据获取流程

### 步骤1：解析股票代码

系统支持多种输入格式的智能解析，自动识别股票代码或名称，并确定所属市场（上海/深圳）。

```python
from scripts.stock_query import parse_stock_code

stock_code, market = parse_stock_code("威派格")
# 返回: ('603956', 'sh')

stock_code, market = parse_stock_code("000001")
# 返回: ('000001', 'sz')
```

**市场判断规则**：
- 代码以 `60`、`68` 开头 → 上海证券交易所（sh）
- 代码以 `00`、`30` 开头 → 深圳证券交易所（sz）

### 步骤2：获取基本信息

使用多数据源获取股票基本信息，优先使用 xtquant，失败时自动切换到 efinance。

```python
from scripts.stock_query import get_stock_info

info = get_stock_info("603956")
# 返回包含以下字段的字典：
# - 代码、名称、所属行业
# - 最新价、涨跌幅、涨跌额
# - 今开、最高、最低、昨收
# - 成交量、成交额、振幅、换手率
# - 总市值、流通市值
# - 市盈率-动态、市净率
```

### 步骤3：获取资金流向

使用 efinance 获取资金流向数据，包括当日流向和历史趋势。

```python
from scripts.stock_query import get_fund_flow

fund_flow = get_fund_flow("603956")
# 返回包含以下字段的字典：
# - 主力净流入、主力净流入占比
# - 超大单净流入、大单净流入
# - 中单净流入、小单净流入
# - 历史数据（最近10天）
# - 分钟级数据（当日）
```

### 步骤4：获取历史K线数据

获取历史K线数据用于技术指标计算，支持多数据源自动切换。

```python
from scripts.stock_query import get_history_data

df = get_history_data("603956", days=60)
# 返回 DataFrame，包含以下列：
# - 日期、开盘、收盘、最高、最低
# - 成交量、成交额
```

**数据源优先级**：
1. xtquant（需安装并配置）
2. efinance
3. baostock

### 步骤5：获取分钟级行情

获取当日分钟级行情数据。

```python
from scripts.stock_query import get_minute_data

minute_data = get_minute_data("603956")
# 返回包含以下字段的字典：
# - 当日数据：分钟级OHLCV数据列表
# - 最新数据：最新一条分钟数据
```

## 技术指标计算

使用 `scripts/technical_indicators.py` 模块计算技术指标。

### MACD 指标

```python
from scripts.technical_indicators import calculate_macd

macd = calculate_macd(close_prices, fast=12, slow=26, signal=9)
# 返回：
# {
#     'DIF': 0.1234,
#     'DEA': 0.0987,
#     'MACD': 0.0494,
#     'signal': '金叉' | '死叉' | '多头' | '空头'
# }
```

**信号判断逻辑**：
- **金叉**：DIF 上穿 DEA（当日 DIF > DEA，前一日 DIF ≤ DEA）
- **死叉**：DIF 下穿 DEA（当日 DIF < DEA，前一日 DIF ≥ DEA）
- **多头**：DIF > DEA（非金叉情况）
- **空头**：DIF < DEA（非死叉情况）

### RSI 指标

```python
from scripts.technical_indicators import calculate_rsi

rsi = calculate_rsi(close_prices, periods=[6, 12, 24])
# 返回：
# {
#     'RSI(6)': {'value': 65.32, 'status': '正常'},
#     'RSI(12)': {'value': 58.45, 'status': '正常'},
#     'RSI(24)': {'value': 52.18, 'status': '正常'}
# }
```

**状态判断逻辑**：
- **超买**：RSI > 80
- **超卖**：RSI < 20
- **偏强**：70 < RSI ≤ 80
- **偏弱**：20 ≤ RSI < 30
- **正常**：30 ≤ RSI ≤ 70

### KDJ 指标

```python
from scripts.technical_indicators import calculate_kdj

kdj = calculate_kdj(high_prices, low_prices, close_prices, n=9, m1=3, m2=3)
# 返回：
# {
#     'K': 65.32,
#     'D': 58.45,
#     'J': 79.06,
#     'signal': '金叉' | '死叉' | '超买' | '超卖' | '正常'
# }
```

**信号判断逻辑**：
- **金叉**：K 上穿 D
- **死叉**：K 下穿 D
- **超买**：K > 80 且 D > 80
- **超卖**：K < 20 且 D < 20

### 均线系统 (MA)

```python
from scripts.technical_indicators import calculate_ma

ma = calculate_ma(close_prices, periods=[5, 10, 20, 60])
# 返回：
# {
#     'MA5': 25.32,
#     'MA10': 24.85,
#     'MA20': 24.12,
#     'MA60': 23.45
# }
```

### 布林带 (BOLL)

```python
from scripts.technical_indicators import calculate_boll

boll = calculate_boll(close_prices, n=20, k=2)
# 返回：
# {
#     'upper': 26.50,   # 上轨
#     'middle': 25.00,  # 中轨
#     'lower': 23.50    # 下轨
# }
```

### 量比指标

```python
from scripts.technical_indicators import calculate_volume_ratio

vr = calculate_volume_ratio(volume, n=5)
# 返回：
# {
#     'volume_ratio': 1.25,
#     'status': '正常' | '放量' | '巨量' | '缩量'
# }
```

**状态判断逻辑**：
- **巨量**：量比 > 2.5
- **放量**：1.5 < 量比 ≤ 2.5
- **正常**：0.8 ≤ 量比 ≤ 1.5
- **缩量**：量比 < 0.8

### 批量计算所有指标

```python
from scripts.technical_indicators import calculate_all_indicators

indicators = calculate_all_indicators(df)
# 返回包含 MACD、RSI、KDJ、MA、BOLL、Volume_Ratio 的字典
```

## 分析逻辑

### 交易信号生成

系统综合技术面、资金面、市场情绪三个维度生成交易信号。

```python
from scripts.core.analyzer import StockAnalyzer

analyzer = StockAnalyzer(config)
analysis = analyzer.generate_recommendation(data)

# 返回：
# {
#     'analysis': {
#         'technical': {'score': 0.65, 'signals': [...]},
#         'fund_flow': {'score': 0.70, 'trend': 'inflow'},
#         'sentiment': {'score': 0.55}
#     },
#     'trading_signal': {
#         'score': 0.635,
#         'signal': 'buy',
#         'signal_text': '买入'
#     },
#     'price_prediction': {...},
#     'indicators': {...}
# }
```

**评分权重**（可在配置文件中调整）：
- 技术面：50%
- 资金面：30%
- 市场情绪：20%

**信号阈值**：
- **强烈买入**：评分 ≥ 0.7
- **买入**：评分 ≥ 0.5
- **持有**：评分 ≥ 0.3
- **观望**：评分 > 0
- **卖出**：评分 ≤ 0

### 价格预测

基于技术指标预测短期价格区间，包括未来两天的目标价格。

```python
price_pred = analyzer.predict_price_range(data, indicators)
# 返回：
# {
#     'current': 25.50,
#     'support': 24.00,
#     'resistance': 27.00,
#     'trend': 'up',
#     'day1': {
#         'target_low': 25.80,
#         'target_high': 26.50,
#         'trend': 'up',
#         'signal': '看涨延续'
#     },
#     'day2': {
#         'target_low': 26.00,
#         'target_high': 27.00,
#         'trend': 'up',
#         'signal': '持续上涨'
#     }
# }
```

## 报告生成

### HTML 报告

系统生成包含交互式图表的 HTML 报告，使用 Chart.js 进行图表渲染。

```python
from scripts.core.report_generator import ReportGenerator

generator = ReportGenerator(config)
html = generator.generate_html_report(data, analysis)
output_path = generator.save_report(html, stock_code, output_dir)
```

**报告内容**：
- 股票基本信息卡片
- 实时行情数据
- 技术指标分析
- 资金流向分析
- 交易信号与评分
- 价格预测
- K线图（含均线）
- MACD/RSI/KDJ 技术指标图
- 资金流向柱状图

## 输出格式

输出采用结构化的 HTML 格式，包含交互式图表。报告文件命名格式：

```
{股票代码}_{时间戳}.html
```

示例：`603956_20240115_143025.html`

## 配置文件

配置文件位于 `config/config.yaml`，支持自定义各项参数：

```yaml
# 数据获取配置
data_fetcher:
  max_retries: 3
  retry_delay: 1
  request_timeout: 30

# xtquant 配置
xtquant:
  enabled: true
  max_retries: 3
  retry_delay: 1
  data_dir: ""

# 技术指标参数
technical_indicators:
  macd:
    fast: 12
    slow: 26
    signal: 9
  rsi:
    periods: [6, 12, 24]
  kdj:
    n: 9
    m1: 3
    m2: 3
  ma:
    periods: [5, 10, 20, 60]
  boll:
    n: 20
    k: 2

# 分析参数
analyzer:
  weights:
    technical: 0.5
    fund_flow: 0.3
    sentiment: 0.2
  thresholds:
    strong_buy: 0.7
    buy: 0.5
    hold: 0.3
  price_prediction:
    atr_multiplier: 1.5
    boll_multiplier: 1.0

# 报告配置
report:
  default_format: html
  include_charts: true
  chart_height: 600

# 输出配置
output:
  directory: output/reports
  filename_pattern: "{stock_code}_{date}"
```

## 执行流程

当用户请求股票信息时，按以下顺序执行：

1. **解析输入**：识别股票代码或名称，确定市场
2. **获取基本信息**：调用多数据源获取实时行情和基本信息
3. **获取资金流向**：调用 efinance 获取资金流向数据
4. **获取历史数据**：获取60天历史K线数据
5. **获取分钟数据**：获取当日分钟级行情
6. **计算技术指标**：基于历史数据计算 MACD、RSI、KDJ、MA、BOLL
7. **生成分析建议**：综合分析生成交易信号和价格预测
8. **生成报告**：输出 HTML 格式的分析报告

## 注意事项

1. **数据时效性**：实时数据在交易时间内更新，非交易时间显示最后收盘数据
2. **数据来源**：数据来自东方财富、新浪财经等公开数据源，仅供参考
3. **调用频率**：避免过于频繁的API调用，建议间隔1秒以上
4. **错误处理**：如果某个数据获取失败，继续获取其他数据并在报告中标注
5. **网络依赖**：需要稳定的网络连接以获取实时数据

## 示例用法

用户输入示例：
- "查询 000001 股票信息"
- "贵州茅台 股票详情"
- "帮我看看宁德时代的资金流向"
- "300750 技术指标分析"
- "威派格 生成分析报告"

## 数据使用规范

本技能仅供学习和研究使用，不得用于商业用途。数据来源于公开渠道，准确性请以官方数据为准。使用本工具进行投资决策产生的任何损失，开发者不承担任何责任。
