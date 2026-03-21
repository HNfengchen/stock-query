# Stock Query - A股股票信息查询与分析工具

Stock Query 是一个功能完善的A股股票信息查询与分析工具，提供实时行情获取、技术指标计算、资金流向分析、智能交易信号生成等功能，并支持生成包含交互式图表的HTML分析报告。

## 功能特点

- **多数据源支持**：集成 xtquant、efinance、AkShare、baostock 等多个数据源，自动切换保障数据获取稳定性
- **实时行情数据**：获取股票基本信息、实时价格、成交量、换手率等行情数据
- **资金流向分析**：追踪主力资金、大单、中单、小单的流入流出情况
- **技术指标计算**：
  - MACD（指数平滑异同移动平均线）
  - RSI（相对强弱指标）
  - KDJ（随机指标）
  - MA（移动平均线）
  - BOLL（布林带）
  - 量比指标
- **智能分析建议**：综合技术面、资金面、市场情绪生成交易信号
- **价格预测**：基于技术分析预测短期价格区间
- **可视化报告**：生成包含 K 线图、技术指标图、资金流向图的交互式 HTML 报告

## 项目结构

```
stock-query/
├── config/
│   └── config.yaml          # 配置文件
├── scripts/
│   ├── __init__.py
│   ├── cli.py               # 命令行入口
│   ├── stock_query.py       # 核心数据获取模块
│   ├── technical_indicators.py  # 技术指标计算
│   └── core/
│       ├── __init__.py
│       ├── data_fetcher.py  # 数据获取层
│       ├── analyzer.py      # 分析逻辑层
│       ├── report_generator.py  # 报告生成层
│       └── xtquant_adapter.py   # xtquant适配器
├── templates/
│   └── report_template.html # HTML报告模板
├── static/
│   └── chart.umd.min.js     # 图表库
├── output/
│   └── reports/             # 报告输出目录
├── evals/
│   └── evals.json           # 评估配置
├── README.md
└── SKILL.md
```

## 环境要求

- Python 3.8+
- Windows / Linux / macOS

## 安装说明

### 1. 克隆项目

```bash
git clone <repository-url>
cd stock-query
```

### 2. 安装依赖

```bash
pip install akshare efinance pandas numpy ta pyyaml jinja2
```

可选依赖（用于增强数据获取能力）：

```bash
pip install xtquant baostock
```

## 使用方法

### 命令行使用

基本用法：

```bash
python -m scripts.cli <股票代码或名称>
```

示例：

```bash
# 使用股票名称查询
python -m scripts.cli 威派格

# 使用股票代码查询
python -m scripts.cli 603956

# 指定配置文件
python -m scripts.cli 威派格 --config config/config.yaml

# 指定输出目录
python -m scripts.cli 威派格 --output-dir ./my_reports

# 不生成图表
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

### Python API 使用

```python
from scripts.core.data_fetcher import DataFetcher
from scripts.core.analyzer import StockAnalyzer
from scripts.core.report_generator import ReportGenerator

# 加载配置
import yaml
with open('config/config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 获取数据
fetcher = DataFetcher(config)
data = fetcher.fetch_all_data('威派格')

# 分析数据
analyzer = StockAnalyzer(config)
analysis = analyzer.generate_recommendation(data)

# 生成报告
generator = ReportGenerator(config)
html = generator.generate_html_report(data, analysis)
generator.save_report(html, data['stock_code'], './reports')
```

## 配置说明

配置文件位于 `config/config.yaml`，主要配置项：

```yaml
# 数据获取配置
data_fetcher:
  max_retries: 3        # 最大重试次数
  retry_delay: 1        # 重试间隔（秒）
  request_timeout: 30   # 请求超时（秒）

# 技术指标参数
technical_indicators:
  macd:
    fast: 12            # 快线周期
    slow: 26            # 慢线周期
    signal: 9           # 信号线周期
  rsi:
    periods: [6, 12, 24]  # RSI周期
  kdj:
    n: 9                # RSV周期
    m1: 3               # K值平滑周期
    m2: 3               # D值平滑周期

# 分析参数
analyzer:
  weights:
    technical: 0.5      # 技术面权重
    fund_flow: 0.3      # 资金面权重
    sentiment: 0.2      # 情绪面权重
  thresholds:
    strong_buy: 0.7     # 强烈买入阈值
    buy: 0.5            # 买入阈值
    hold: 0.3           # 持有阈值

# 报告配置
report:
  default_format: html
  include_charts: true
  chart_height: 600
```

## 技术指标说明

### MACD 指标

- **金叉**：DIF 上穿 DEA，通常为买入信号
- **死叉**：DIF 下穿 DEA，通常为卖出信号
- **多头**：DIF > DEA，趋势偏多
- **空头**：DIF < DEA，趋势偏空

### RSI 指标

- **超买**：RSI > 80，可能面临回调
- **超卖**：RSI < 20，可能存在反弹机会
- **偏强**：RSI > 70，相对强势
- **偏弱**：RSI < 30，相对弱势

### KDJ 指标

- **金叉**：K 上穿 D，通常为买入信号
- **死叉**：K 下穿 D，通常为卖出信号
- **超买**：K > 80 且 D > 80
- **超卖**：K < 20 且 D < 20

## 数据来源

本项目数据来源于以下公开数据接口：

- **xtquant**：迅投量化数据接口（需单独安装）
- **efinance**：东方财富数据接口
- **AkShare**：开源财经数据接口
- **baostock**：证券宝数据接口

## 注意事项

1. **数据时效性**：实时数据在交易时间内更新，非交易时间显示最后收盘数据
2. **调用频率**：避免过于频繁的 API 调用，建议间隔 1 秒以上
3. **数据准确性**：数据来源于公开渠道，准确性请以官方数据为准
4. **网络依赖**：需要稳定的网络连接以获取实时数据

## 免责声明

本工具仅供学习和研究使用，不构成任何投资建议。股市有风险，投资需谨慎。使用本工具产生的任何投资损失，开发者不承担任何责任。

## 许可证

MIT License
