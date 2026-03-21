---
name: stock-query
description: 获取A股股票详细信息，包括基本信息、实时行情、资金流向和技术指标。当用户需要查询股票数据、分析股票行情、获取资金流向、计算技术指标（MACD、RSI、KDJ）时使用此技能。支持通过股票代码或股票名称进行查询。
---

# A股股票信息查询技能

本技能基于 AkShare 和 efinance 库，提供全面的A股股票数据查询功能。

## 功能概述

当用户提供股票代码时，本技能将：

1. **获取股票基本信息**：公司名称、行业分类、上市日期、总市值、流通市值等
2. **获取实时行情数据**：分钟级开盘价、最高价、最低价、最新价、成交量、成交额
3. **获取资金流向数据**：主力资金流入流出、大单/中单/小单资金流向
4. **计算技术指标**：MACD、RSI、KDJ等常用技术指标
5. **获取当日历史数据**：完整的分钟级历史数据

## 依赖安装

```bash
pip install akshare efinance pandas numpy ta
```

## 使用方法

### 输入格式

用户可以通过以下方式提供股票信息：
- 股票代码：如 "000001"、"600519"、"300750"
- 股票名称：如 "平安银行"、"贵州茅台"、"宁德时代"
- 混合格式：如 "000001 平安银行"

### 输出格式

输出采用结构化的Markdown格式，包含以下部分：

```markdown
# [股票名称] (股票代码) 股票信息报告

## 一、基本信息
| 项目 | 内容 |
|------|------|
| 股票代码 | xxx |
| 股票名称 | xxx |
| 所属行业 | xxx |
| 上市日期 | xxx |
| 总市值 | xxx |
| 流通市值 | xxx |

## 二、实时行情
| 项目 | 数值 |
|------|------|
| 最新价 | xxx |
| 涨跌幅 | xxx |
| 开盘价 | xxx |
| 最高价 | xxx |
| 最低价 | xxx |
| 成交量 | xxx |
| 成交额 | xxx |
| 换手率 | xxx |
| 量比 | xxx |
| 市盈率 | xxx |

## 三、资金流向
### 3.1 今日资金流向
| 项目 | 金额(万元) | 占比 |
|------|-----------|------|
| 主力净流入 | xxx | xxx% |
| 超大单净流入 | xxx | xxx% |
| 大单净流入 | xxx | xxx% |
| 中单净流入 | xxx | xxx% |
| 小单净流入 | xxx | xxx% |

### 3.2 近期资金流向趋势
[资金流向历史数据表格]

## 四、技术指标
### 4.1 MACD指标
| 项目 | 数值 |
|------|------|
| DIF | xxx |
| DEA | xxx |
| MACD柱 | xxx |
| 信号 | 金叉/死叉/多头/空头 |

### 4.2 RSI指标
| 周期 | 数值 | 状态 |
|------|------|------|
| RSI(6) | xxx | 超买/超卖/正常 |
| RSI(12) | xxx | 超买/超卖/正常 |
| RSI(24) | xxx | 超买/超卖/正常 |

### 4.3 KDJ指标
| 项目 | 数值 |
|------|------|
| K值 | xxx |
| D值 | xxx |
| J值 | xxx |
| 信号 | 金叉/死叉/超买/超卖 |

## 五、当日分钟级行情
[分钟级数据表格，包含时间、开盘、收盘、最高、最低、成交量、成交额]
```

## 数据获取流程

### 步骤1：解析股票代码

```python
import akshare as ak
import efinance as ef

def parse_stock_code(user_input: str) -> tuple:
    """
    解析用户输入，返回股票代码和市场标识
    返回: (stock_code, market)
    market: 'sh' 或 'sz'
    """
    user_input = user_input.strip().replace(' ', '')
    
    if user_input.isdigit():
        code = user_input.zfill(6)
        if code.startswith(('60', '68')):
            market = 'sh'
        else:
            market = 'sz'
        return code, market
    
    try:
        df = ak.stock_zh_a_spot_em()
        match = df[df['名称'].str.contains(user_input, na=False)]
        if not match.empty:
            code = match.iloc[0]['代码']
            market = 'sh' if code.startswith(('60', '68')) else 'sz'
            return code, market
    except:
        pass
    
    return None, None
```

### 步骤2：获取基本信息

使用 AkShare 获取股票基本信息：

```python
def get_stock_info(stock_code: str) -> dict:
    """获取股票基本信息"""
    import akshare as ak
    
    info = {}
    
    try:
        df = ak.stock_zh_a_spot_em()
        stock_data = df[df['代码'] == stock_code]
        if not stock_data.empty:
            row = stock_data.iloc[0]
            info['代码'] = row['代码']
            info['名称'] = row['名称']
            info['最新价'] = row['最新价']
            info['涨跌幅'] = row['涨跌幅']
            info['涨跌额'] = row['涨跌额']
            info['成交量'] = row['成交量']
            info['成交额'] = row['成交额']
            info['振幅'] = row['振幅']
            info['最高'] = row['最高']
            info['最低'] = row['最低']
            info['今开'] = row['今开']
            info['昨收'] = row['昨收']
            info['换手率'] = row['换手率']
            info['市盈率-动态'] = row.get('市盈率-动态', 'N/A')
            info['市净率'] = row.get('市净率', 'N/A')
            info['总市值'] = row.get('总市值', 'N/A')
            info['流通市值'] = row.get('流通市值', 'N/A')
            info['量比'] = row.get('量比', 'N/A')
    except Exception as e:
        print(f"获取实时行情失败: {e}")
    
    return info
```

### 步骤3：获取资金流向

使用 efinance 获取资金流向数据：

```python
def get_fund_flow(stock_code: str) -> dict:
    """获取资金流向数据"""
    import efinance as ef
    
    fund_flow = {}
    
    try:
        df = ef.stock.get_history_bill(stock_code)
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            fund_flow['日期'] = latest['日期']
            fund_flow['主力净流入'] = latest['主力净流入']
            fund_flow['小单净流入'] = latest['小单净流入']
            fund_flow['中单净流入'] = latest['中单净流入']
            fund_flow['大单净流入'] = latest['大单净流入']
            fund_flow['超大单净流入'] = latest['超大单净流入']
            fund_flow['主力净流入占比'] = latest['主力净流入占比']
            fund_flow['历史数据'] = df.tail(10).to_dict('records')
    except Exception as e:
        print(f"获取资金流向失败: {e}")
    
    try:
        df_minute = ef.stock.get_today_bill(stock_code)
        if df_minute is not None and not df_minute.empty:
            fund_flow['分钟级数据'] = df_minute.to_dict('records')
    except Exception as e:
        print(f"获取分钟级资金流向失败: {e}")
    
    return fund_flow
```

### 步骤4：获取分钟级行情

```python
def get_minute_data(stock_code: str) -> dict:
    """获取分钟级行情数据"""
    import efinance as ef
    
    minute_data = {}
    
    try:
        df = ef.stock.get_quote_history(stock_code, klt=1, fqt=1)
        if df is not None and not df.empty:
            today = df.iloc[-1]['日期'][:10] if not df.empty else None
            if today:
                today_data = df[df['日期'].str.startswith(today)]
                minute_data['当日数据'] = today_data.to_dict('records')
                minute_data['最新数据'] = today_data.iloc[-1].to_dict() if not today_data.empty else None
    except Exception as e:
        print(f"获取分钟级行情失败: {e}")
    
    return minute_data
```

### 步骤5：计算技术指标

使用 `scripts/technical_indicators.py` 脚本计算技术指标。该脚本提供以下函数：

- `calculate_macd()` - 计算MACD指标
- `calculate_rsi()` - 计算RSI指标  
- `calculate_kdj()` - 计算KDJ指标

详细实现请参考脚本文件。

## 执行流程

当用户请求股票信息时，按以下顺序执行：

1. **解析输入**：识别股票代码或名称
2. **获取基本信息**：调用 AkShare 获取实时行情和基本信息
3. **获取资金流向**：调用 efinance 获取资金流向数据
4. **获取分钟数据**：调用 efinance 获取当日分钟级行情
5. **计算技术指标**：基于历史数据计算 MACD、RSI、KDJ
6. **格式化输出**：生成结构化的Markdown报告

## 注意事项

1. **数据时效性**：实时数据在交易时间内更新，非交易时间显示最后收盘数据
2. **数据来源**：数据来自东方财富、新浪财经等公开数据源，仅供参考
3. **调用频率**：避免过于频繁的API调用，建议间隔1秒以上
4. **错误处理**：如果某个数据获取失败，继续获取其他数据并在报告中标注

## 示例用法

用户输入：
- "查询 000001 股票信息"
- "贵州茅台 股票详情"
- "帮我看看宁德时代的资金流向"
- "300750 技术指标分析"

## 数据使用规范

本技能仅供学习和研究使用，不得用于商业用途。数据来源于公开渠道，准确性请以官方数据为准。
