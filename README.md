# Stock Query - A股量化分析平台

Stock Query 是一个功能完善的A股量化分析平台，提供实时行情获取、技术指标计算、资金流向分析、智能交易信号生成、回测验证和Web可视化界面。

## 功能特点

### 核心分析
- **多数据源支持**：集成 xtquant、efinance、AkShare、baostock 等多个数据源，自动切换保障数据获取稳定性
- **技术指标计算**：MACD、RSI(6/12/24)、KDJ、MA、BOLL、ATR、量比
- **智能分析建议**：综合技术面(45%)、资金面(30%)、市场情绪(25%)生成交易信号
- **价格预测**：基于技术评分+ATR+趋势强度预测短期价格区间
- **资金流向分析**：追踪主力资金、大单、中单、小单的流入流出情况

### Web界面
- **分析报告页**：K线图、技术指标图(MACD/RSI/KDJ)、资金流向图、交易信号面板
- **回测中心**：内置策略回测+自定义算法编辑器，权益曲线与预测明细
- **历史列表**：自选股管理，持仓状态与成本价跟踪
- **响应式布局**：适配桌面端与移动端

### 回测系统
- **内置策略回测**：基于技术评分的预测区间回测，统计命中率与夏普比率
- **自定义算法**：支持用户编写交易信号函数，沙箱安全执行
- **交易成本模拟**：佣金0.025%+印花税0.05%+滑点0.1%

### CLI命令行
- 单股分析：`python -m scripts.cli 603956`
- 批量回测：`python -m scripts.cli --backtest 603956`
- HTML报告生成

## 项目结构

```
stock-query/
├── backend/                        # 后端服务 (FastAPI)
│   ├── app.py                      # 应用入口
│   ├── routers/                    # API路由
│   │   ├── analysis.py             # 分析接口 (含批量并发)
│   │   ├── backtest.py             # 回测接口
│   │   ├── history.py              # 自选股接口
│   │   └── websocket.py            # WebSocket进度推送
│   ├── services/                   # 业务逻辑
│   │   ├── analysis_service.py     # 分析服务 (含缓存+单例)
│   │   ├── backtest_service.py     # 回测服务 (含安全沙箱)
│   │   └── history_service.py      # 自选股服务 (含文件锁)
│   └── utils/
│       └── __init__.py             # 共享序列化工具
├── frontend/                       # 前端应用 (Vue 3 + TypeScript)
│   ├── src/
│   │   ├── views/                  # 页面组件
│   │   │   ├── AnalysisView.vue    # 分析报告页
│   │   │   ├── BacktestView.vue    # 回测中心页
│   │   │   └── HistoryView.vue     # 自选股管理页
│   │   ├── components/             # UI组件
│   │   │   ├── KlineChart.vue      # K线图+成交量
│   │   │   ├── TechnicalChart.vue  # MACD/RSI/KDJ三图
│   │   │   ├── FundFlowChart.vue   # 资金流向图
│   │   │   ├── ReportPanel.vue     # 信号面板
│   │   │   ├── NavHeader.vue       # 导航栏
│   │   │   ├── SideWatchlist.vue   # 侧边自选股
│   │   │   └── StockInput.vue      # 股票输入
│   │   ├── stores/                 # Pinia状态管理
│   │   ├── api/                    # API调用模块
│   │   └── types/                  # TypeScript类型定义
│   └── vite.config.ts              # Vite配置 (含代理)
├── scripts/                        # 核心分析引擎
│   ├── cli.py                      # CLI入口
│   ├── stock_query.py              # 命令行逻辑
│   ├── technical_indicators.py     # 技术指标计算
│   └── core/
│       ├── data_fetcher.py         # 数据获取层
│       ├── analyzer.py             # 分析逻辑层
│       ├── backtest.py             # 回测引擎
│       ├── report_generator.py     # 报告生成层
│       └── database.py             # 数据库层
├── config/
│   └── config.yaml                 # 配置文件
├── deploy/                         # 部署配置
│   ├── install.sh                  # 一键部署脚本
│   ├── stock-query-backend.service # systemd后端服务
│   └── stock-query-frontend.service# systemd前端服务
├── docs/                           # 文档
├── start.sh                        # 启动脚本
└── README.md
```

## 环境要求

- Python 3.8+
- Node.js 20+
- npm 9+
- Linux / Windows / macOS

## 快速开始

### 1. 安装依赖

```bash
# Python依赖
pip install -r backend/requirements.txt
pip install pyyaml pandas numpy akshare efinance

# 可选依赖（增强数据获取）
pip install xtquant baostock

# 前端依赖
cd frontend && npm install && cd ..
```

### 2. 启动服务

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

**方式三：systemd开机自启动**

```bash
sudo bash deploy/install.sh
```

### 3. 访问界面

浏览器打开 http://localhost:5173

## 启动脚本

`start.sh` 支持以下命令：

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

## 部署

### systemd开机自启动

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

# 使用nginx代理
# 将 frontend/dist 目录部署到nginx
# 将 /api 请求代理到后端 8002 端口
```

## API接口

### 分析接口

```
POST /api/analysis
Body: {"stock_input": "603956", "position_status": "未持有", "cost_price": null}
Response: {stock_code, stock_name, analysis, trading_signal, price_prediction, position_strategy, indicators, charts}

POST /api/analysis/batch
Body: {"stocks": [{"stock_input": "603956"}, {"stock_input": "000001"}]}
Response: {results: [...], errors: [...]}
```

### 回测接口

```
POST /api/backtest
Body: {"stock_code": "603956", "mode": "builtin", "params": {"atr_multiplier": 1.5}}
Response: {stock_code, statistics, predictions, equity_curve}

POST /api/backtest/custom
Body: {"stock_code": "603956", "algorithm_code": "def signal(df, ind): ..."}
```

### 自选股接口

```
GET    /api/watchlist
POST   /api/watchlist
PUT    /api/watchlist/{stock_code}
DELETE /api/watchlist/{stock_code}
```

### 健康检查

```
GET /health
```

## 命令行使用

```bash
# 分析单只股票
python -m scripts.cli 603956

# 使用股票名称
python -m scripts.cli 威派格

# 回测
python -m scripts.cli --backtest 603956

# 指定配置
python -m scripts.cli 威派格 --config config/config.yaml

# 指定输出目录
python -m scripts.cli 威派格 --output-dir ./my_reports
```

## 配置说明

配置文件位于 `config/config.yaml`：

```yaml
data_fetcher:
  max_retries: 3
  retry_delay: 1
  request_timeout: 30

technical_indicators:
  macd: {fast: 12, slow: 26, signal: 9}
  rsi: {periods: [6, 12, 24]}
  kdj: {n: 9, m1: 3, m2: 3}
  boll: {period: 20, std_dev: 2}

analyzer:
  weights: {technical: 0.45, fund_flow: 0.30, sentiment: 0.25}
  thresholds: {strong_buy: 0.7, buy: 0.5, hold: 0.3}

prediction:
  atr_multiplier: 1.5
  price_range_days: 20
```

## 技术指标说明

### MACD
- **金叉确认**：DIF上穿DEA且柱状图为正，强买入信号
- **死叉确认**：DIF下穿DEA且柱状图为负，强卖出信号
- **多头/空头**：DIF与DEA的位置关系判断趋势

### RSI（自适应阈值）
- **超买/超卖**：基于60日分位数动态调整阈值（默认80/20）
- **多周期背离**：RSI(6)与RSI(24)方向相反时产生背离信号
- **偏强/偏弱**：中间区间的趋势判断

### KDJ
- **金叉/死叉**：K线与D线的交叉信号
- **超买/超卖**：K/D值超过80/低于20

### BOLL
- 使用样本标准差(ddof=1)，与主流行情软件一致
- 上轨=中轨+2σ，下轨=中轨-2σ

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Vue 3 + TypeScript + Vite |
| UI组件 | Element Plus |
| 图表 | ECharts (vue-echarts) |
| 状态管理 | Pinia |
| 后端框架 | FastAPI + Uvicorn |
| 数据获取 | efinance + AkShare + baostock |
| 数据处理 | Pandas + NumPy |
| 部署 | systemd + nginx |

## 注意事项

1. **数据时效性**：实时数据在交易时间内更新，非交易时间显示最后收盘数据
2. **调用频率**：避免过于频繁的API调用，建议间隔1秒以上
3. **数据准确性**：数据来源于公开渠道，准确性请以官方数据为准
4. **网络依赖**：需要稳定的网络连接以获取实时数据
5. **交易成本**：回测权益曲线已包含佣金+印花税+滑点，更接近真实收益
6. **安全限制**：自定义回测算法在受限沙箱中执行，禁止系统调用

## 免责声明

本工具仅供学习和研究使用，不构成任何投资建议。股市有风险，投资需谨慎。使用本工具产生的任何投资损失，开发者不承担任何责任。

## 许可证

MIT License
