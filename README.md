# Stock Query - A股量化分析平台

Stock Query 是一个功能完善的 A 股量化分析平台，提供实时行情获取、技术指标计算、资金流向分析、智能交易信号生成、交叉验证校准、回测验证和 Web 可视化界面。

## 功能特点

### 核心分析引擎

- **五级趋势分类**：大幅上涨 / 上涨 / 震荡 / 下跌 / 大幅下跌，基于涨跌幅阈值（±1%/±3%）+ 趋势持续性判定
- **多维评分体系**：综合技术面（50%）、资金面（30%）、市场情绪（20%）生成加权评分
- **交叉验证校准**：多维度方向共识检测、信号一致性验证、冲突惩罚机制，生成操作建议（建议买入 / 可考虑买入 / 观望 / 减仓 / 谨慎持有 / 回避）
- **价格预测**：基于技术评分 + ATR + 布林带预测短期价格区间，含置信度评估
- **持仓策略**：根据持仓状态（已持有/未持有）生成差异化止盈止损和仓位建议

### 数据保障机制

- **多数据源回退链**：efinance → xtquant → 腾讯财经 → baostock，自动切换保障数据获取稳定性
- **字段自动补全**：从收盘价计算涨跌幅/涨跌额，从成交量 × 均价估算成交额
- **baostock 历史补充**：自动从 baostock 获取逐日 PE/PB/换手率/成交额，覆盖估算值
- **市值反推计算**：从最新市值 × 收盘价比例反推历史总市值和流通市值
- **空值检测刷新**：自动检测数据库空值字段并触发强制刷新
- **盘中数据更新**：当日盘中分析后，收盘再分析会自动用收盘价覆盖盘中价

### Web 界面

- **分析报告页**：K 线图、技术指标图（MACD/RSI/KDJ）、资金流向图、交易信号面板、交叉验证面板
- **回测中心**：内置策略回测 + Monaco 代码编辑器自定义算法，权益曲线与预测明细
- **自选股管理**：一键批量分析（SSE 实时进度推送），信号颜色分类，持仓状态与成本价跟踪
- **响应式布局**：适配桌面端与移动端

### 回测系统

- **内置策略回测**：基于分析引擎的预测区间回测，统计命中率、夏普比率、最大回撤
- **自定义算法**：支持用户编写交易信号函数，沙箱安全执行
- **交易成本模拟**：佣金 0.025% + 印花税 0.05% + 滑点 0.1%

### CLI 命令行

- 单股分析：`python -m scripts.cli 603956`
- 批量回测：`python -m scripts.cli --backtest 603956`
- HTML 报告生成

## 项目结构

```
stock-query/
├── backend/                        # 后端服务 (FastAPI)
│   ├── app.py                      # 应用入口
│   ├── routers/
│   │   ├── analysis.py             # 分析接口 (单股/批量/SSE流式)
│   │   ├── backtest.py             # 回测接口 (内置/自定义)
│   │   ├── history.py              # 自选股接口 (CRUD+信号缓存)
│   │   └── websocket.py            # WebSocket 进度推送
│   ├── services/
│   │   ├── analysis_service.py     # 分析服务 (5分钟缓存+单例)
│   │   ├── backtest_service.py     # 回测服务 (安全沙箱)
│   │   └── history_service.py      # 自选股服务 (文件锁)
│   └── utils/
│       └── __init__.py             # 序列化/清洗工具
├── frontend/                       # 前端应用 (Vue 3 + TypeScript)
│   ├── src/
│   │   ├── views/
│   │   │   ├── AnalysisView.vue    # 分析报告页
│   │   │   ├── BacktestView.vue    # 回测中心页
│   │   │   └── HistoryView.vue     # 自选股管理页 (一键分析)
│   │   ├── components/
│   │   │   ├── KlineChart.vue      # K线图+成交量
│   │   │   ├── TechnicalChart.vue  # MACD/RSI/KDJ 三图
│   │   │   ├── FundFlowChart.vue   # 资金流向图
│   │   │   ├── ReportPanel.vue     # 信号面板
│   │   │   ├── ValidationPanel.vue # 交叉验证面板
│   │   │   ├── NavHeader.vue       # 导航栏
│   │   │   └── StockInput.vue      # 股票输入
│   │   ├── stores/                 # Pinia 状态管理
│   │   ├── api/                    # API 调用模块
│   │   ├── utils/
│   │   │   └── format.ts           # 共享格式化工具 (趋势/数字/市值)
│   │   └── types/                  # TypeScript 类型定义
│   └── vite.config.ts
├── scripts/                        # 核心分析引擎
│   ├── cli.py                      # CLI 入口
│   ├── stock_query.py              # 数据获取 (多源回退+字段补全)
│   ├── technical_indicators.py     # 技术指标计算
│   ├── database.py                 # PostgreSQL 数据库层 (空值检测+自动刷新)
│   └── core/
│       ├── data_fetcher.py         # 数据获取层
│       ├── analyzer.py             # 分析逻辑 (五级趋势+交叉验证)
│       ├── backtest.py             # 回测引擎
│       ├── calibration.py          # 交叉验证校准
│       └── report_generator.py     # 报告生成
├── config/
│   └── config.yaml                 # 配置文件
├── deploy/                         # 部署配置
│   ├── install.sh                  # 一键部署脚本
│   ├── stock-query-backend.service # systemd 后端服务
│   └── stock-query-frontend.service# systemd 前端服务
├── start.sh                        # 启动脚本
└── README.md
```

## 环境要求

| 依赖 | 版本要求 |
|------|---------|
| Python | 3.8+ |
| Node.js | ^20.19.0 或 >=22.12.0 |
| npm | 9+ |
| PostgreSQL | 12+ (建议安装 TimescaleDB + pgvector 扩展) |
| 操作系统 | Linux / Windows / macOS |

## 快速开始

### 1. 安装依赖

```bash
# Python 核心依赖
pip install -r backend/requirements.txt
pip install pyyaml pandas numpy psycopg2-binary sse-starlette

# 数据源依赖（按需安装）
pip install efinance akshare          # 基础数据源
pip install xtquant                    # 迅投QMT数据源
pip install baostock                   # 历史数据补充（推荐）

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

## API 接口

### 分析接口

**单股分析**

```
POST /api/analysis
Content-Type: application/json

请求体:
{
  "stock_input": "603956",       // 股票代码或名称
  "position_status": "未持有",    // 持仓状态: 未持有/已持有
  "cost_price": null             // 成本价（已持有时填写）
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
    "recommendation": "可考虑买入",   // 交叉验证操作建议
    "details": { ... }
  },
  "trading_signal": {
    "score": 0.64,
    "signal": "buy",
    "signal_text": "可考虑买入",     // 交叉验证操作建议
    "action_gate": "cautious_buy",  // 原始操作门控
    "reason": "..."
  },
  "price_prediction": { ... },
  "position_strategy": { ... },
  "validation": { ... },
  "indicators": { ... },
  "charts": { ... }
}
```

**批量分析（一次性返回）**

```
POST /api/analysis/batch
Content-Type: application/json

请求体:
{
  "stocks": [
    {"stock_input": "603956"},
    {"stock_input": "000001"}
  ]
}

响应体:
{
  "results": [ ... ],
  "errors": [ ... ]
}
```

**批量快速分析（SSE 流式返回）**

```
POST /api/analysis/batch-quick
Content-Type: application/json

请求体: 同 /api/analysis/batch

响应: Server-Sent Events 流
event: progress
data: {"current": 1, "total": 5, "summary": {"stock_code": "603956", "signal_text": "建议买入", "score": 0.72}}

event: complete
data: {"total": 5}
```

### 回测接口

**内置策略回测**

```
POST /api/backtest
Content-Type: application/json

请求体:
{
  "stock_code": "603956",
  "mode": "builtin",
  "params": {"atr_multiplier": 1.5}
}
```

**自定义算法回测**

```
POST /api/backtest/custom
Content-Type: application/json

请求体:
{
  "stock_code": "603956",
  "algorithm_code": "def signal(df, ind):\n    return 1 if ind['rsi_6'] < 30 else -1"
}
```

### 自选股接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/watchlist` | 获取自选股列表 |
| POST | `/api/watchlist` | 添加自选股 |
| PUT | `/api/watchlist/{stock_code}` | 更新持仓状态/成本价 |
| DELETE | `/api/watchlist/{stock_code}` | 删除自选股 |

### 健康检查

```
GET /health
响应: {"status": "ok"}
```

### WebSocket

```
WS /ws/progress/{task_id}
消息: {"type": "progress", "current": 3, "total": 10, "message": "正在分析 000001..."}
```

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

**数据写入策略**：

| 字段 | 历史行数据来源 | 最新行数据来源 |
|------|--------------|--------------|
| 涨跌幅/涨跌额 | 收盘价计算 | 收盘价计算 |
| 成交额 | baostock → 成交量×均价估算 | 同左 |
| PE/PB/换手率 | baostock 逐日数据 | baostock → 实时快照回退 |
| 总市值/流通市值 | 收盘价反推 | 收盘价反推 |
| 主力资金/占比 | NULL | efinance 实时数据 |

## 配置说明

配置文件位于 `config/config.yaml`：

```yaml
# 数据获取
data_fetcher:
  max_retries: 3
  retry_delay: 1
  request_timeout: 30

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
```

## 技术指标说明

### MACD（12, 26, 9）

- **金叉确认**：DIF 上穿 DEA 且柱状图为正，强买入信号
- **死叉确认**：DIF 下穿 DEA 且柱状图为负，强卖出信号
- **多头/空头**：DIF 与 DEA 的位置关系判断趋势

### RSI（6/12/24，自适应阈值）

- **超买/超卖**：基于 60 日分位数动态调整阈值（默认 80/20）
- **多周期背离**：RSI(6) 与 RSI(24) 方向相反时产生背离信号
- **偏强/偏弱**：中间区间的趋势判断

### KDJ（9, 3, 3）

- **金叉/死叉**：K 线与 D 线的交叉信号
- **超买/超卖**：K/D 值超过 80 / 低于 20

### BOLL（20, 2）

- 使用样本标准差（ddof=1），与主流行情软件一致
- 上轨 = 中轨 + 2σ，下轨 = 中轨 - 2σ

## 交叉验证体系

分析引擎通过多维度交叉验证生成操作建议：

| 操作建议 | action_gate | 含义 |
|---------|-------------|------|
| 建议买入 | allow_buy | 多维度一致看多，置信度高 |
| 可考虑买入 | cautious_buy | 多数维度看多，但存在分歧 |
| 观望 | watch | 多空方向不明确 |
| 回避 | avoid_buy | 多维度一致看空 |
| 减仓 | reduce_position | 已持仓且多维度看空 |
| 谨慎持有 | cautious_hold | 已持仓但存在风险信号 |
| 持有 | hold_position | 已持仓且趋势稳定 |

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

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Vue 3 + TypeScript + Vite |
| UI 组件 | Element Plus |
| 图表 | ECharts 6 (vue-echarts) |
| 代码编辑器 | Monaco Editor |
| 状态管理 | Pinia |
| 后端框架 | FastAPI + Uvicorn |
| 实时通信 | SSE (sse-starlette) + WebSocket |
| 数据库 | PostgreSQL + TimescaleDB + pgvector |
| 数据获取 | efinance + AkShare + baostock + xtquant + 腾讯财经 |
| 数据处理 | Pandas + NumPy |
| 部署 | systemd + nginx |

## 常见问题

### Q: 分析时提示"无法获取历史数据"

A: 检查网络连接。系统按 efinance → xtquant → 腾讯财经 → baostock 顺序回退，所有源均失败时会出现此提示。建议安装 baostock（`pip install baostock`）作为兜底数据源。

### Q: 数据库字段为空

A: 系统会在下次分析时自动检测空值字段并触发刷新。也可以手动触发：在分析页面重新分析该股票。

### Q: 盘中分析和收盘后分析数据不一致

A: 盘中分析写入的是盘中价格，收盘后再分析会自动用收盘价覆盖当日数据。建议收盘后再进行分析以获取准确数据。

### Q: 自定义回测算法安全吗

A: 自定义算法在受限沙箱中执行，禁止 `import os`、`open()`、`exec()` 等危险操作。但建议不要运行来源不明的算法代码。

### Q: PE（市盈率）为负数

A: 亏损公司的市盈率为负数，这是正常现象。系统不会过滤负 PE。

### Q: 历史市值数据准确吗

A: 历史总市值和流通市值通过 `最新市值 × (历史收盘价 / 最新收盘价)` 反推，在总股本不变的假设下精确。如遇增发等情况会有偏差。

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

    location /ws/ {
        proxy_pass http://127.0.0.1:8002;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

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

## 免责声明

本工具仅供学习和研究使用，不构成任何投资建议。股市有风险，投资需谨慎。使用本工具产生的任何投资损失，开发者不承担任何责任。

## 许可证

MIT License
