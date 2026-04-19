"""
股票信息查询主模块
使用 xtquant 和 efinance 提供全面的股票数据查询功能
"""

import efinance as ef
import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from datetime import datetime
import time

from .technical_indicators import calculate_all_indicators

XTQUANT_AVAILABLE = False

try:
    from xtquant import xtdata

    XTQUANT_AVAILABLE = True
except ImportError:
    xtdata = None


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    数据清洗：过滤停牌日、检测异常值

    处理步骤：
    1. 过滤成交量<=0或为NaN的行（停牌日）
    2. 过滤涨跌幅异常（单日>15%的极端行情）
    3. 不使用3σ过滤（对妖股/周期股不适用）

    参数:
        df: 原始DataFrame

    返回:
        DataFrame: 清洗后的数据
    """
    if df is None or df.empty:
        return df

    original_len = len(df)

    df = df.copy()

    if "成交量" in df.columns:
        df = df[df["成交量"] > 0]
        df = df.dropna(subset=["成交量"])

    if "收盘" in df.columns:
        df = df.dropna(subset=["收盘"])

    if "涨跌幅" in df.columns:
        df = df.dropna(subset=["涨跌幅"])
        df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
        pct_col = df["涨跌幅"]
        df = df[(pct_col > -15) & (pct_col < 15)]

    cleaned_len = len(df)
    if cleaned_len < original_len:
        print(f"数据清洗: 原始 {original_len} 条 -> 清洗后 {cleaned_len} 条 (过滤 {original_len - cleaned_len} 条)")

    return df


def _get_xtdata():
    """获取 xtquant 数据接口"""
    if XTQUANT_AVAILABLE:
        return xtdata
    return None


def parse_stock_code(user_input: str) -> Tuple[Optional[str], Optional[str]]:
    """
    解析用户输入，返回股票代码和市场标识

    参数:
        user_input: 用户输入的股票代码或名称

    返回:
        tuple: (stock_code, market) market为'sh'或'sz'
    """
    user_input = user_input.strip().replace(" ", "")

    if user_input.isdigit():
        code = user_input.zfill(6)
        if code.startswith(("60", "68")):
            market = "sh"
        elif code.startswith(("00", "30")):
            market = "sz"
        else:
            market = "sz"
        return code, market

    xdata = _get_xtdata()
    if xdata:
        try:
            sectors = xdata.get_sector_list()
            for sector in sectors[:50]:
                try:
                    stocks = xdata.get_stock_list_in_sector(sector)
                    for stock in stocks:
                        if user_input in stock:
                            code = stock.split(".")[0]
                            market = "sh" if stock.endswith(".SH") else "sz"
                            return code, market
                except:
                    continue
        except Exception as e:
            print(f"通过 xtquant 查询失败: {e}")

    try:
        df = ef.stock.get_base_info()
        if df is not None and not df.empty:
            if "股票简称" in df.columns:
                match = df[df["股票简称"].str.contains(user_input, na=False)]
            elif "名称" in df.columns:
                match = df[df["名称"].str.contains(user_input, na=False)]
            else:
                match = pd.DataFrame()
            if not match.empty:
                code = str(match.iloc[0].get("代码", match.iloc[0].get("股票代码", "")))
                if code:
                    market = "sh" if code.startswith(("60", "68")) else "sz"
                    return code, market
    except Exception as e:
        print(f"通过 efinance 查询失败: {e}")

    return None, None


def _get_full_code(stock_code: str, market: str) -> str:
    """获取完整股票代码"""
    return f"{stock_code}.{'SH' if market == 'sh' else 'SZ'}"


def get_stock_info(stock_code: str) -> Dict:
    """
    获取股票基本信息

    参数:
        stock_code: 股票代码

    返回:
        dict: 股票基本信息
    """
    info = {"代码": stock_code}

    xdata = _get_xtdata()
    if xdata:
        try:
            full_code = _get_full_code(
                stock_code, "sh" if stock_code.startswith(("60", "68")) else "sz"
            )
            detail = xdata.get_instrument_detail(full_code)
            if detail:
                info["名称"] = detail.get("InstrumentName", "N/A")
                info["上市日期"] = detail.get("OpenDate", "N/A")
                info["交易所"] = detail.get("ExchangeID", "N/A")

            market_data = xdata.get_market_data(
                field_list=["close", "open", "high", "low", "volume", "amount", "turn"],
                stock_list=[full_code],
                period="1d",
                count=1,
            )
            if market_data:
                close_data = market_data.get("close")
                if close_data is not None and not close_data.empty:
                    info["最新价"] = close_data.iloc[0, 0]

                open_data = market_data.get("open")
                if open_data is not None and not open_data.empty:
                    info["今开"] = open_data.iloc[0, 0]

                high_data = market_data.get("high")
                if high_data is not None and not high_data.empty:
                    info["最高"] = high_data.iloc[0, 0]

                low_data = market_data.get("low")
                if low_data is not None and not low_data.empty:
                    info["最低"] = low_data.iloc[0, 0]

                volume_data = market_data.get("volume")
                if volume_data is not None and not volume_data.empty:
                    info["成交量"] = volume_data.iloc[0, 0]

                amount_data = market_data.get("amount")
                if amount_data is not None and not amount_data.empty:
                    info["成交额"] = amount_data.iloc[0, 0]

                turn_data = market_data.get("turn")
                if turn_data is not None and not turn_data.empty:
                    info["换手率"] = turn_data.iloc[0, 0]

        except Exception as e:
            print(f"xtquant 获取实时行情失败: {e}")

    try:
        s = ef.stock.get_quote_snapshot(stock_code)
        if s is not None and not s.empty:
            if info.get("名称") == "N/A" or "名称" not in info:
                info["名称"] = s.get("名称", s.get("代码", "N/A"))

            mapping = {
                "最新价": "最新价",
                "涨跌幅": "涨跌幅",
                "涨跌额": "涨跌额",
                "最高": "最高",
                "最低": "最低",
                "今开": "今开",
                "昨收": "昨收",
                "成交量": "成交量",
                "成交额": "成交额",
                "换手率": "换手率",
            }

            for dest_key, src_key in mapping.items():
                if dest_key not in info or info.get(dest_key) is None:
                    val = s.get(src_key)
                    if val is not None and not pd.isna(val):
                        info[dest_key] = val

            pe_val = s.get("市盈率-动态")
            if pe_val is not None and not pd.isna(pe_val):
                info["市盈率-动态"] = pe_val
    except Exception as e:
        print(f"efinance 获取实时行情失败: {e}")

    try:
        base_info = ef.stock.get_base_info(stock_code)
        if base_info is not None:
            if isinstance(base_info, pd.DataFrame) and not base_info.empty:
                row = base_info.iloc[0]
            elif isinstance(base_info, pd.Series):
                row = base_info
            else:
                row = None

            if row is not None:
                if info.get("名称") == "N/A" or "名称" not in info:
                    info["名称"] = row.get("股票名称", info.get("名称", "N/A"))

                if info.get("所属行业") == "N/A" or "所属行业" not in info:
                    industry = row.get("所处行业", "N/A")
                    if industry and industry != "N/A":
                        info["所属行业"] = industry

                if info.get("总市值") is None or info.get("总市值") == "N/A":
                    total_mv = row.get("总市值")
                    if total_mv is not None and not pd.isna(total_mv):
                        info["总市值"] = total_mv

                if info.get("流通市值") is None or info.get("流通市值") == "N/A":
                    circ_mv = row.get("流通市值")
                    if circ_mv is not None and not pd.isna(circ_mv):
                        info["流通市值"] = circ_mv

                if info.get("市盈率-动态") == "N/A" or "市盈率-动态" not in info:
                    pe = row.get("市盈率(动)")
                    if pe is not None and not pd.isna(pe):
                        info["市盈率-动态"] = pe

                if info.get("市净率") == "N/A" or "市净率" not in info:
                    pb = row.get("市净率")
                    if pb is not None and not pd.isna(pb):
                        info["市净率"] = pb
    except Exception as e:
        print(f"efinance 获取基础信息失败: {e}")

    if "名称" not in info or info.get("名称") is None:
        info["名称"] = stock_code
    if "所属行业" not in info or info.get("所属行业") is None:
        info["所属行业"] = "N/A"

    return info


def get_fund_flow(stock_code: str) -> Dict:
    """
    获取资金流向数据

    参数:
        stock_code: 股票代码

    返回:
        dict: 资金流向数据
    """
    fund_flow = {}

    try:
        df = ef.stock.get_history_bill(stock_code)
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            fund_flow["日期"] = latest.get("日期", "N/A")
            fund_flow["主力净流入"] = latest.get("主力净流入", 0)
            fund_flow["小单净流入"] = latest.get("小单净流入", 0)
            fund_flow["中单净流入"] = latest.get("中单净流入", 0)
            fund_flow["大单净流入"] = latest.get("大单净流入", 0)
            fund_flow["超大单净流入"] = latest.get("超大单净流入", 0)
            fund_flow["主力净流入占比"] = latest.get("主力净流入占比", 0)
            fund_flow["收盘价"] = latest.get("收盘价", "N/A")
            fund_flow["涨跌幅"] = latest.get("涨跌幅", "N/A")

            history = []
            for _, row in df.tail(10).iterrows():
                history.append(
                    {
                        "日期": row.get("日期", "N/A"),
                        "主力净流入": row.get("主力净流入", 0),
                        "主力净流入占比": row.get("主力净流入占比", 0),
                        "涨跌幅": row.get("涨跌幅", "N/A"),
                    }
                )
            fund_flow["历史数据"] = history
    except Exception as e:
        fund_flow["error"] = f"获取资金流向失败: {e}"

    try:
        df_minute = ef.stock.get_today_bill(stock_code)
        if df_minute is not None and not df_minute.empty:
            minute_data = []
            for _, row in df_minute.iterrows():
                minute_data.append(
                    {
                        "时间": row.get("时间", "N/A"),
                        "主力净流入": row.get("主力净流入", 0),
                        "小单净流入": row.get("小单净流入", 0),
                        "中单净流入": row.get("中单净流入", 0),
                        "大单净流入": row.get("大单净流入", 0),
                        "超大单净流入": row.get("超大单净流入", 0),
                    }
                )
            fund_flow["分钟级数据"] = minute_data
    except Exception as e:
        fund_flow["minute_error"] = f"获取分钟级资金流向失败: {e}"

    return fund_flow


def get_minute_data(stock_code: str) -> Dict:
    """
    获取分钟级行情数据

    参数:
        stock_code: 股票代码

    返回:
        dict: 分钟级行情数据
    """
    minute_data = {}

    try:
        df = ef.stock.get_quote_history(stock_code, klt=1, fqt=1)
        if df is not None and not df.empty:
            today = str(df.iloc[-1]["日期"])[:10]
            today_data = df[df["日期"].astype(str).str.startswith(today)]

            if not today_data.empty:
                records = []
                for _, row in today_data.iterrows():
                    records.append(
                        {
                            "时间": row.get("日期", "N/A"),
                            "开盘": row.get("开盘", "N/A"),
                            "收盘": row.get("收盘", "N/A"),
                            "最高": row.get("最高", "N/A"),
                            "最低": row.get("最低", "N/A"),
                            "成交量": row.get("成交量", 0),
                            "成交额": row.get("成交额", 0),
                            "振幅": row.get("振幅", "N/A"),
                            "涨跌幅": row.get("涨跌幅", "N/A"),
                            "涨跌额": row.get("涨跌额", "N/A"),
                            "换手率": row.get("换手率", "N/A"),
                        }
                    )
                minute_data["当日数据"] = records
                minute_data["最新数据"] = records[-1] if records else None
            else:
                minute_data["error"] = "当日无交易数据"
    except Exception as e:
        minute_data["error"] = f"获取分钟级行情失败: {e}"

    return minute_data


def get_history_data(stock_code: str, days: int = 60) -> pd.DataFrame:
    """
    获取历史K线数据

    参数:
        stock_code: 股票代码
        days: 获取天数

    返回:
        DataFrame: 历史K线数据
    """
    xdata = _get_xtdata()
    market = "sh" if stock_code.startswith(("60", "68")) else "sz"
    full_code = _get_full_code(stock_code, market)

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - pd.Timedelta(days=days * 2)).strftime("%Y%m%d")

    if xdata:
        try:
            xdata.download_history_data(full_code, "1d", start_date, end_date)
            time.sleep(1)

            market_data = xdata.get_market_data(
                field_list=["date", "open", "close", "high", "low", "volume", "amount"],
                stock_list=[full_code],
                period="1d",
                start_time=start_date,
                end_time=end_date,
                count=days + 10,
                dividend_type="front",
            )

            if market_data:
                close_data = market_data.get("close")
                if close_data is not None and not close_data.empty:
                    df = close_data.T.copy()
                    df.columns = ["收盘"]

                    if "open" in market_data:
                        df["开盘"] = market_data["open"].T.iloc[:, 0]
                    if "high" in market_data:
                        df["最高"] = market_data["high"].T.iloc[:, 0]
                    if "low" in market_data:
                        df["最低"] = market_data["low"].T.iloc[:, 0]
                    if "volume" in market_data:
                        df["成交量"] = market_data["volume"].T.iloc[:, 0]
                    if "amount" in market_data:
                        df["成交额"] = market_data["amount"].T.iloc[:, 0]
                    if "date" in market_data:
                        df.index = pd.to_datetime(market_data["date"])
                        df.index.name = "日期"

                    df = clean_data(df)
                    result = df.tail(days)
                    if not result.empty:
                        print(f"xtquant（前复权）获取历史数据成功: {len(result)} 条")
                        return result
        except Exception as e:
            print(f"xtquant 获取历史数据失败: {e}")

    try:
        df = ef.stock.get_quote_history(stock_code, klt=101, fqt=1)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df = df.rename(
                columns={
                    "日期": "日期",
                    "开盘": "开盘",
                    "收盘": "收盘",
                    "最高": "最高",
                    "最低": "最低",
                    "成交量": "成交量",
                    "成交额": "成交额",
                }
            )
            df = clean_data(df)
            result = df.tail(days)
            if not result.empty:
                print(f"efinance（前复权）获取历史数据成功: {len(result)} 条")
                return result
    except Exception as e:
        print(f"efinance 获取历史数据失败: {e}")

    try:
        import baostock as bs

        bs.login()
        rs = bs.query_history_k_data_plus(
            f"{'sh' if market == 'sh' else 'sz'}.{stock_code}",
            "date,open,high,low,close,volume,amount",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="2",
        )

        data_list = []
        while rs.error_code == "0" and rs.next():
            data_list.append(rs.get_row_data())

        bs.logout()

        if data_list:
            df = pd.DataFrame(
                data_list,
                columns=["日期", "开盘", "最高", "最低", "收盘", "成交量", "成交额"],
            )
            df["开盘"] = pd.to_numeric(df["开盘"], errors="coerce")
            df["最高"] = pd.to_numeric(df["最高"], errors="coerce")
            df["最低"] = pd.to_numeric(df["最低"], errors="coerce")
            df["收盘"] = pd.to_numeric(df["收盘"], errors="coerce")
            df["成交量"] = pd.to_numeric(df["成交量"], errors="coerce")
            df["成交额"] = pd.to_numeric(df["成交额"], errors="coerce")
            df = clean_data(df)
            print(f"baostock（前复权）获取历史数据成功: {len(df)} 条")
            return df.tail(days)
    except ImportError:
        print("baostock 未安装")
    except Exception as e:
        print(f"baostock 获取历史数据失败: {e}")

    return pd.DataFrame()


def get_technical_indicators(stock_code: str) -> Dict:
    """
    获取技术指标

    参数:
        stock_code: 股票代码

    返回:
        dict: 技术指标数据
    """
    indicators = {}

    try:
        df = get_history_data(stock_code, 60)
        if df is not None and not df.empty:
            indicators = calculate_all_indicators(df)
        else:
            indicators["error"] = "无法获取历史数据"
    except Exception as e:
        indicators["error"] = f"计算技术指标失败: {e}"

    return indicators


def format_number(value, unit: str = "") -> str:
    """格式化数字显示"""
    if value is None or value == "N/A":
        return "N/A"

    try:
        num = float(value)
        if abs(num) >= 1e8:
            return f"{num / 1e8:.2f}亿{unit}"
        elif abs(num) >= 1e4:
            return f"{num / 1e4:.2f}万{unit}"
        else:
            return f"{num:.2f}{unit}"
    except:
        return str(value)


def generate_report(stock_input: str) -> str:
    """
    生成股票信息报告

    参数:
        stock_input: 股票代码或名称

    返回:
        str: Markdown格式的报告
    """
    stock_code, market = parse_stock_code(stock_input)

    if not stock_code:
        return f"错误：无法识别股票 '{stock_input}'，请检查输入"

    info = get_stock_info(stock_code)
    fund_flow = get_fund_flow(stock_code)
    minute_data = get_minute_data(stock_code)
    indicators = get_technical_indicators(stock_code)

    stock_name = info.get("名称", stock_code)

    report = f"# {stock_name} ({stock_code}) 股票信息报告\n\n"
    report += f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n"
    report += f"*数据来源: xtquant, efinance*\n\n"

    report += "## 一、基本信息\n\n"
    report += "| 项目 | 内容 |\n"
    report += "|------|------|\n"
    report += f"| 股票代码 | {stock_code} |\n"
    report += f"| 股票名称 | {info.get('名称', 'N/A')} |\n"
    report += f"| 所属行业 | {info.get('所属行业', 'N/A')} |\n"
    report += f"| 总市值 | {format_number(info.get('总市值'), '元')} |\n"
    report += f"| 流通市值 | {format_number(info.get('流通市值'), '元')} |\n"
    report += f"| 市盈率(动态) | {info.get('市盈率-动态', 'N/A')} |\n"
    report += f"| 市净率 | {info.get('市净率', 'N/A')} |\n"
    report += "\n"

    report += "## 二、实时行情\n\n"
    report += "| 项目 | 数值 |\n"
    report += "|------|------|\n"
    report += f"| 最新价 | {info.get('最新价', 'N/A')} 元 |\n"
    report += f"| 涨跌幅 | {info.get('涨跌幅', 'N/A')}% |\n"
    report += f"| 涨跌额 | {info.get('涨跌额', 'N/A')} 元 |\n"
    report += f"| 今开 | {info.get('今开', 'N/A')} 元 |\n"
    report += f"| 最高 | {info.get('最高', 'N/A')} 元 |\n"
    report += f"| 最低 | {info.get('最低', 'N/A')} 元 |\n"
    report += f"| 昨收 | {info.get('昨收', 'N/A')} 元 |\n"
    report += f"| 成交量 | {format_number(info.get('成交量'), '股')} |\n"
    report += f"| 成交额 | {format_number(info.get('成交额'), '元')} |\n"
    report += f"| 振幅 | {info.get('振幅', 'N/A')}% |\n"
    report += f"| 换手率 | {info.get('换手率', 'N/A')}% |\n"
    report += f"| 量比 | {info.get('量比', 'N/A')} |\n"
    report += "\n"

    report += "## 三、资金流向\n\n"
    report += "### 3.1 今日资金流向\n\n"

    if "error" not in fund_flow:
        report += "| 项目 | 金额(万元) | 占比 |\n"
        report += "|------|-----------|------|\n"
        report += f"| 主力净流入 | {format_number(fund_flow.get('主力净流入'))} | {fund_flow.get('主力净流入占比', 'N/A')}% |\n"
        report += (
            f"| 超大单净流入 | {format_number(fund_flow.get('超大单净流入'))} | - |\n"
        )
        report += f"| 大单净流入 | {format_number(fund_flow.get('大单净流入'))} | - |\n"
        report += f"| 中单净流入 | {format_number(fund_flow.get('中单净流入'))} | - |\n"
        report += f"| 小单净流入 | {format_number(fund_flow.get('小单净流入'))} | - |\n"
        report += "\n"

        report += "### 3.2 近期资金流向趋势\n\n"
        report += "| 日期 | 主力净流入(万元) | 占比 | 涨跌幅 |\n"
        report += "|------|----------------|------|--------|\n"
        for item in fund_flow.get("历史数据", []):
            report += f"| {item.get('日期', 'N/A')} | {format_number(item.get('主力净流入'))} | {item.get('主力净流入占比', 'N/A')}% | {item.get('涨跌幅', 'N/A')}% |\n"
        report += "\n"
    else:
        report += f"*{fund_flow.get('error', '数据获取失败')}*\n\n"

    report += "## 四、技术指标\n\n"

    if "error" not in indicators:
        report += "### 4.1 MACD指标\n\n"
        macd = indicators.get("MACD", {})
        report += "| 项目 | 数值 |\n"
        report += "|------|------|\n"
        report += f"| DIF | {macd.get('DIF', 'N/A')} |\n"
        report += f"| DEA | {macd.get('DEA', 'N/A')} |\n"
        report += f"| MACD柱 | {macd.get('MACD', 'N/A')} |\n"
        report += f"| 信号 | {macd.get('signal', 'N/A')} |\n"
        report += "\n"

        report += "### 4.2 RSI指标\n\n"
        rsi = indicators.get("RSI", {})
        report += "| 周期 | 数值 | 状态 |\n"
        report += "|------|------|------|\n"
        for key, val in rsi.items():
            report += (
                f"| {key} | {val.get('value', 'N/A')} | {val.get('status', 'N/A')} |\n"
            )
        report += "\n"

        report += "### 4.3 KDJ指标\n\n"
        kdj = indicators.get("KDJ", {})
        report += "| 项目 | 数值 |\n"
        report += "|------|------|\n"
        report += f"| K值 | {kdj.get('K', 'N/A')} |\n"
        report += f"| D值 | {kdj.get('D', 'N/A')} |\n"
        report += f"| J值 | {kdj.get('J', 'N/A')} |\n"
        report += f"| 信号 | {kdj.get('signal', 'N/A')} |\n"
        report += "\n"

        report += "### 4.4 均线系统\n\n"
        ma = indicators.get("MA", {})
        report += "| 均线 | 价格 |\n"
        report += "|------|------|\n"
        for key, val in ma.items():
            report += f"| {key} | {val if val else 'N/A'} |\n"
        report += "\n"

        report += "### 4.5 布林带\n\n"
        boll = indicators.get("BOLL", {})
        report += "| 项目 | 价格 |\n"
        report += "|------|------|\n"
        report += f"| 上轨 | {boll.get('upper', 'N/A')} |\n"
        report += f"| 中轨 | {boll.get('middle', 'N/A')} |\n"
        report += f"| 下轨 | {boll.get('lower', 'N/A')} |\n"
        report += "\n"
    else:
        report += f"*{indicators.get('error', '技术指标计算失败')}*\n\n"

    report += "## 五、当日分钟级行情\n\n"

    if "当日数据" in minute_data:
        data = minute_data["当日数据"]
        if data:
            report += "| 时间 | 开盘 | 收盘 | 最高 | 最低 | 成交量 | 成交额 |\n"
            report += "|------|------|------|------|------|--------|--------|\n"
            for item in data[-20:]:
                report += f"| {str(item.get('时间', 'N/A'))[-8:]} | {item.get('开盘', 'N/A')} | {item.get('收盘', 'N/A')} | {item.get('最高', 'N/A')} | {item.get('最低', 'N/A')} | {format_number(item.get('成交量'))} | {format_number(item.get('成交额'))} |\n"
            report += "\n*（显示最近20条数据）*\n"
    else:
        report += f"*{minute_data.get('error', '分钟级数据获取失败')}*\n"

    report += "\n---\n"
    report += "\n**免责声明**：本报告数据仅供参考，不构成投资建议。数据来源于 xtquant 和 efinance，请以官方数据为准。\n"

    return report
