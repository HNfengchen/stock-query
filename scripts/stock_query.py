"""
股票信息查询主模块
使用 xtquant 和 efinance 提供全面的股票数据查询功能
"""

import efinance as ef
import pandas as pd
from typing import Dict, Optional, Tuple
from datetime import datetime
import time
import concurrent.futures

from .technical_indicators import calculate_all_indicators

XTQUANT_AVAILABLE = False

try:
    from xtquant import xtdata

    XTQUANT_AVAILABLE = True
except ImportError:
    xtdata = None


def _call_with_timeout(func, *args, timeout=15, **kwargs):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(func, *args, **kwargs)
        done, not_done = concurrent.futures.wait([future], timeout=timeout)
        if not_done:
            not_done.pop().cancel()
            return None
        return future.result()
    except Exception:
        return None
    finally:
        executor.shutdown(wait=False)


def clean_data(df: pd.DataFrame, stock_code: str = None, stock_name: str = None) -> pd.DataFrame:
    """
    数据清洗：过滤停牌日、检测异常值、缺失值填充

    处理步骤：
    1. 过滤成交量<=0或为NaN的行（停牌日）
    2. 过滤涨跌幅异常（根据板块设定不同阈值）
    3. 对OHLCV核心字段dropna，对辅助字段用前值填充
    4. 不使用3σ过滤（对妖股/周期股不适用）

    参数:
        df: 原始DataFrame
        stock_code: 股票代码，用于判断板块设定涨跌幅阈值
        stock_name: 股票名称，用于判断是否为ST股

    返回:
        DataFrame: 清洗后的数据
    """
    if df is None or df.empty:
        return df

    original_len = len(df)

    df = df.copy()

    core_fields = ["收盘", "开盘", "最高", "最低"]
    aux_fields = ["成交量", "成交额", "涨跌幅", "振幅"]

    for field in aux_fields:
        if field in df.columns:
            df[field] = df[field].ffill()

    if "成交量" in df.columns:
        df = df[df["成交量"] > 0]
        df = df.dropna(subset=["成交量"])

    if "收盘" in df.columns:
        df = df.dropna(subset=["收盘"])

    if "涨跌幅" in df.columns:
        df = df.dropna(subset=["涨跌幅"])
        df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
        pct_col = df["涨跌幅"]

        # 根据股票代码判断板块，设定不同的涨跌幅阈值
        pct_min, pct_max = -15, 15  # 默认值
        is_st = False

        # 首先检查股票名称是否包含ST（更可靠）
        if stock_name:
            name_upper = str(stock_name).upper()
            if "ST" in name_upper or "*ST" in name_upper or "S*" in name_upper:
                is_st = True

        # 备用：根据股票代码判断（代码中包含ST的情况极少）
        if stock_code and not is_st:
            code_str = str(stock_code)
            if code_str.startswith("30") or code_str.startswith("68"):
                pct_min, pct_max = -21, 21  # 创业板/科创板
            elif code_str.startswith("00") or code_str.startswith("60") or code_str.startswith("01"):
                pct_min, pct_max = -11, 11  # 主板
        elif is_st:
            pct_min, pct_max = -6, 6  # ST股

        df = df[(pct_col > pct_min) & (pct_col < pct_max)]

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
    # 防御：确保输入为字符串（前端可能传入数字类型）
    if not isinstance(user_input, str):
        user_input = str(int(user_input)) if isinstance(user_input, (int, float)) and user_input == int(user_input) else str(user_input)
    user_input = user_input.strip().replace(" ", "")
    # 防御：去除数字字符串末尾的.0（如"159032.0"→"159032"）
    if user_input.endswith(".0") and user_input[:-2].isdigit():
        user_input = user_input[:-2]

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
                except Exception:
                    continue
        except Exception as e:
            print(f"通过 xtquant 查询失败: {e}")

    try:
        df = _call_with_timeout(ef.stock.get_base_info)
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


def _calc_change_fields(df: pd.DataFrame) -> pd.DataFrame:
    """从收盘价计算涨跌幅和涨跌额（如果缺失）"""
    if df is None or df.empty or "收盘" not in df.columns:
        return df
    df = df.copy()
    close = pd.to_numeric(df["收盘"], errors="coerce")
    prev_close = close.shift(1)
    if "涨跌幅" not in df.columns or df["涨跌幅"].isna().all():
        mask = prev_close.notna() & (prev_close != 0)
        df["涨跌幅"] = float('nan')
        df.loc[mask, "涨跌幅"] = ((close[mask] - prev_close[mask]) / prev_close[mask] * 100).round(4)
    elif df["涨跌幅"].isna().any():
        mask = df["涨跌幅"].isna() & prev_close.notna() & (prev_close != 0)
        df.loc[mask, "涨跌幅"] = ((close[mask] - prev_close[mask]) / prev_close[mask] * 100).round(4)
    if "涨跌额" not in df.columns or df["涨跌额"].isna().all():
        mask = prev_close.notna()
        df["涨跌额"] = float('nan')
        df.loc[mask, "涨跌额"] = (close[mask] - prev_close[mask]).round(2)
    elif df["涨跌额"].isna().any():
        mask = df["涨跌额"].isna() & prev_close.notna()
        df.loc[mask, "涨跌额"] = (close[mask] - prev_close[mask]).round(2)
    return df


def _estimate_amount(df: pd.DataFrame) -> pd.DataFrame:
    """当成交额缺失时，用成交量×均价估算成交额"""
    if df is None or df.empty:
        return df
    if "成交额" not in df.columns or df["成交额"].isna().all():
        if "成交量" in df.columns and "最高" in df.columns and "最低" in df.columns:
            vol = pd.to_numeric(df["成交量"], errors="coerce")
            high = pd.to_numeric(df["最高"], errors="coerce")
            low = pd.to_numeric(df["最低"], errors="coerce")
            avg_price = (high + low) / 2
            df["成交额"] = (vol * avg_price * 100).round(2)
    return df


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
        s = _call_with_timeout(ef.stock.get_quote_snapshot, stock_code)
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
                "量比": "量比",
                "市盈率-动态": "市盈率(动)",
                "市净率": "市净率",
                "总市值": "总市值",
                "流通市值": "流通市值",
            }

            for dest_key, src_key in mapping.items():
                if dest_key not in info or info.get(dest_key) is None:
                    val = s.get(src_key)
                    if val is None and src_key == "市盈率(动)":
                        val = s.get("市盈率-动态")
                    if val is None and src_key == "市净率":
                        val = s.get("市净率(动)")
                    if val is not None and not pd.isna(val):
                        info[dest_key] = val

            if "振幅" not in info or info.get("振幅") is None:
                high_val = info.get("最高") or s.get("最高")
                low_val = info.get("最低") or s.get("最低")
                pre_close = info.get("昨收") or s.get("昨收")
                if high_val and low_val and pre_close and pre_close != 0:
                    try:
                        info["振幅"] = round((float(high_val) - float(low_val)) / float(pre_close) * 100, 2)
                    except (ValueError, TypeError):
                        pass
    except Exception as e:
        print(f"efinance 获取实时行情失败: {e}")

    try:
        base_info = _call_with_timeout(ef.stock.get_base_info, stock_code)
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

    try:
        import requests as _req

        market_prefix = "sh" if stock_code.startswith(("6", "5")) else "sz"
        tencent_url = f"http://qt.gtimg.cn/q={market_prefix}{stock_code}"
        tencent_resp = _req.get(tencent_url, timeout=10)
        tencent_text = tencent_resp.text.strip()
        if tencent_text and "~" in tencent_text:
            tp = tencent_text.split("~")
            if len(tp) > 35:
                if not info.get("市盈率-动态") or info.get("市盈率-动态") == "N/A":
                    pe_val = None
                    for pe_idx in [39, 52, 47]:
                        try:
                            v = float(tp[pe_idx])
                            if v != 0:
                                pe_val = v
                                break
                        except (ValueError, IndexError):
                            pass
                    if pe_val is not None:
                        info["市盈率-动态"] = pe_val
                if not info.get("市净率") or info.get("市净率") == "N/A":
                    try:
                        info["市净率"] = float(tp[46])
                    except (ValueError, IndexError):
                        pass
                if not info.get("总市值") or info.get("总市值") == "N/A":
                    try:
                        mv = float(tp[44])
                        if mv > 0:
                            info["总市值"] = mv * 100000000
                    except (ValueError, IndexError):
                        pass
                if not info.get("流通市值") or info.get("流通市值") == "N/A":
                    try:
                        cmv = float(tp[45])
                        if cmv > 0:
                            info["流通市值"] = cmv * 100000000
                    except (ValueError, IndexError):
                        pass
                if not info.get("振幅") or info.get("振幅") == "N/A":
                    try:
                        info["振幅"] = float(tp[43])
                    except (ValueError, IndexError):
                        pass
    except Exception as e:
        print(f"腾讯接口获取补充信息失败: {e}")

    try:
        import requests as _req

        secid = f"1.{stock_code}" if stock_code.startswith(("6", "5")) else f"0.{stock_code}"
        dc_url = "http://datacenter-web.eastmoney.com/api/data/v1/get"
        dc_params = {
            "reportName": "RPT_F10_BASIC_ORGINFO",
            "columns": "SECURITY_CODE,EM2016,BOARD_NAME_LEVEL",
            "filter": f'(SECURITY_CODE="{stock_code}")',
            "pageNumber": 1,
            "pageSize": 1,
        }
        dc_resp = _req.get(dc_url, params=dc_params, timeout=10)
        dc_data = dc_resp.json()
        dc_result = dc_data.get("result", {})
        if dc_result and dc_result.get("data"):
            row = dc_result["data"][0]
            if not info.get("所属行业") or info.get("所属行业") == "N/A":
                industry = row.get("EM2016") or row.get("BOARD_NAME_LEVEL")
                if industry and str(industry) not in ("None", "", "-"):
                    info["所属行业"] = str(industry).split("-")[-1] if "-" in str(industry) else str(industry)
    except Exception as e:
        print(f"datacenter 获取行业信息失败: {e}")

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
        df = _call_with_timeout(ef.stock.get_history_bill, stock_code)
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
            for _, row in df.tail(30).iterrows():
                history.append(
                    {
                        "日期": row.get("日期", "N/A"),
                        "主力净流入": row.get("主力净流入", 0),
                        "小单净流入": row.get("小单净流入", 0),
                        "中单净流入": row.get("中单净流入", 0),
                        "大单净流入": row.get("大单净流入", 0),
                        "超大单净流入": row.get("超大单净流入", 0),
                        "主力净流入占比": row.get("主力净流入占比", 0),
                        "涨跌幅": row.get("涨跌幅", 0),
                    }
                )
            fund_flow["历史数据"] = history
    except Exception as e:
        fund_flow["error"] = f"获取资金流向失败: {e}"

    try:
        df_minute = _call_with_timeout(ef.stock.get_today_bill, stock_code)
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
        df = _call_with_timeout(ef.stock.get_quote_history, stock_code, klt=1, fqt=1)
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


def get_history_data(stock_code: str, days: int = 60, stock_name: str = None, klt: int = None) -> pd.DataFrame:
    """
    获取历史K线数据

    参数:
        stock_code: 股票代码
        days: 获取天数
        stock_name: 股票名称，用于ST股检测
        klt: K线类型，1=日线, 101=周线, 102=月线，None默认日线

    返回:
        DataFrame: 历史K线数据
    """
    xdata = _get_xtdata()
    market = "sh" if stock_code.startswith(("60", "68")) else "sz"
    full_code = _get_full_code(stock_code, market)

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - pd.Timedelta(days=days * 2)).strftime("%Y%m%d")

    stock_name = stock_name or None

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

                    df = clean_data(df, stock_code, stock_name)
                    df = _calc_change_fields(df)
                    result = df.tail(days)
                    if not result.empty:
                        print(f"xtquant（前复权）获取历史数据成功: {len(result)} 条")
                        return result
        except Exception as e:
            print(f"xtquant 获取历史数据失败: {e}")

    try:
        df = _call_with_timeout(ef.stock.get_quote_history, stock_code, klt=klt if klt else 1, fqt=1)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df = clean_data(df, stock_code, stock_name)
            result = df.tail(days)
            if not result.empty:
                print(f"efinance（前复权）获取历史数据成功: {len(result)} 条")
                return result
    except Exception as e:
        print(f"efinance 获取历史数据失败: {e}")

    try:
        import requests as _req

        market_prefix = "sh" if stock_code.startswith(("6", "5")) else "sz"
        tencent_url = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        tencent_params = {"param": f"{market_prefix}{stock_code},day,,,{days},qfq"}
        tencent_resp = _req.get(tencent_url, params=tencent_params, timeout=10)
        tencent_data = tencent_resp.json()
        stock_key = f"{market_prefix}{stock_code}"
        stock_info = tencent_data.get("data", {}).get(stock_key, {})
        day_lines = stock_info.get("qfqday", stock_info.get("day", []))
        if day_lines:
            rows = []
            for line in day_lines:
                if len(line) >= 6:
                    rows.append({
                        "日期": line[0],
                        "开盘": float(line[1]),
                        "收盘": float(line[2]),
                        "最高": float(line[3]),
                        "最低": float(line[4]),
                        "成交量": float(line[5]),
                    })
            if rows:
                df = pd.DataFrame(rows)
                df["日期"] = pd.to_datetime(df["日期"])
                df = df.set_index("日期")
                df.index.name = "日期"
                df = df.reset_index()
                df = clean_data(df, stock_code, stock_name)
                df = _estimate_amount(df)
                df = _calc_change_fields(df)
                result = df.tail(days)
                if not result.empty:
                    print(f"腾讯接口获取历史数据成功: {len(result)} 条")
                    return result
    except Exception as e:
        print(f"腾讯接口获取历史数据失败: {e}")

    try:
        import baostock as bs

        bs.login()
        try:
            _freq_map = {None: 'd', 1: 'd', 101: 'w', 102: 'm'}
            _frequency = _freq_map.get(klt, 'd')
            rs = bs.query_history_k_data_plus(
                f"{'sh' if market == 'sh' else 'sz'}.{stock_code}",
                "date,open,high,low,close,volume,amount,turn,peTTM,pbMRQ",
                start_date=start_date,
                end_date=end_date,
                frequency=_frequency,
                adjustflag="2",
            )

            data_list = []
            while rs.error_code == "0" and rs.next():
                data_list.append(rs.get_row_data())
        finally:
            bs.logout()

        if data_list:
            df = pd.DataFrame(
                data_list,
                columns=["日期", "开盘", "最高", "最低", "收盘", "成交量", "成交额", "换手率", "市盈率TTM", "市净率MRQ"],
            )
            df["开盘"] = pd.to_numeric(df["开盘"], errors="coerce")
            df["最高"] = pd.to_numeric(df["最高"], errors="coerce")
            df["最低"] = pd.to_numeric(df["最低"], errors="coerce")
            df["收盘"] = pd.to_numeric(df["收盘"], errors="coerce")
            df["成交量"] = pd.to_numeric(df["成交量"], errors="coerce")
            df["成交额"] = pd.to_numeric(df["成交额"], errors="coerce")
            df["换手率"] = pd.to_numeric(df["换手率"], errors="coerce")
            df["市盈率TTM"] = pd.to_numeric(df["市盈率TTM"], errors="coerce")
            df["市净率MRQ"] = pd.to_numeric(df["市净率MRQ"], errors="coerce")
            df = df.rename(columns={"市盈率TTM": "市盈率-动态", "市净率MRQ": "市净率"})
            df = clean_data(df, stock_code, stock_name)
            df = _calc_change_fields(df)
            print(f"baostock（前复权）获取历史数据成功: {len(df)} 条")
            return df.tail(days)
    except ImportError:
        print("baostock 未安装")
    except Exception as e:
        print(f"baostock 获取历史数据失败: {e}")

    try:
        from scripts.database import StockDataManager
        db = StockDataManager(stock_code)
        db_df = db.get_historical_data(days)
        if db_df is not None and not db_df.empty:
            required_cols = ["开盘", "收盘", "最高", "最低", "成交量"]
            if all(c in db_df.columns for c in required_cols):
                if db_df.index.name == "日期" and "日期" in db_df.columns:
                    db_df = db_df.drop(columns=["日期"])
                db_df = db_df.reset_index()
                if "index" in db_df.columns:
                    db_df = db_df.rename(columns={"index": "日期"})
                db_df = clean_data(db_df, stock_code, stock_name)
                result = db_df.tail(days)
                if not result.empty:
                    print(f"数据库回退获取历史数据成功: {len(result)} 条")
                    return result
    except Exception as e:
        print(f"数据库回退获取历史数据失败: {e}")

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
    except (ValueError, TypeError, KeyError):
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
        macd_series = macd.get("series", {})
        dif = macd_series.get("DIF")
        dea = macd_series.get("DEA")
        macd_val = macd_series.get("MACD")
        if hasattr(dif, "iloc"):
            dif = dif.iloc[-1]
            dea = dea.iloc[-1] if dea is not None else None
            macd_val = macd_val.iloc[-1] if macd_val is not None else None
        report += "| 项目 | 数值 |\n"
        report += "|------|------|\n"
        report += f"| DIF | {dif} |\n"
        report += f"| DEA | {dea} |\n"
        report += f"| MACD柱 | {macd_val} |\n"
        report += f"| 信号 | {macd.get('signal', 'N/A')} |\n"
        report += "\n"

        report += "### 4.2 RSI指标\n\n"
        rsi = indicators.get("RSI", {})
        report += "| 周期 | 数值 | 状态 |\n"
        report += "|------|------|------|\n"
        for key, val in rsi.items():
            latest_val = val.get("latest") if isinstance(val, dict) else val
            signal_val = val.get("signal") if isinstance(val, dict) else val
            if hasattr(latest_val, "iloc"):
                latest_val = latest_val.iloc[-1]
            report += f"| {key} | {latest_val} | {signal_val} |\n"
        report += "\n"

        report += "### 4.3 KDJ指标\n\n"
        kdj = indicators.get("KDJ", {})
        kdj_latest = kdj.get("latest", {})
        k_val = kdj_latest.get("K") if isinstance(kdj_latest, dict) else kdj.get("K")
        d_val = kdj_latest.get("D") if isinstance(kdj_latest, dict) else kdj.get("D")
        j_val = kdj_latest.get("J") if isinstance(kdj_latest, dict) else kdj.get("J")
        if hasattr(k_val, "iloc"):
            k_val = k_val.iloc[-1] if not k_val.empty else None
            d_val = d_val.iloc[-1] if d_val is not None and not d_val.empty else None
            j_val = j_val.iloc[-1] if j_val is not None and not j_val.empty else None
        report += "| 项目 | 数值 |\n"
        report += "|------|------|\n"
        report += f"| K值 | {k_val if k_val is not None else 'N/A'} |\n"
        report += f"| D值 | {d_val if d_val is not None else 'N/A'} |\n"
        report += f"| J值 | {j_val if j_val is not None else 'N/A'} |\n"
        report += f"| 信号 | {kdj.get('signal', 'N/A')} |\n"
        report += "\n"

        report += "### 4.4 均线系统\n\n"
        ma = indicators.get("MA", {})
        report += "| 均线 | 价格 |\n"
        report += "|------|------|\n"
        for key, val in ma.items():
            if isinstance(val, dict):
                ma_val = val.get("latest")
                if hasattr(ma_val, "iloc"):
                    ma_val = ma_val.iloc[-1] if not ma_val.empty else None
            else:
                ma_val = val
            report += f"| {key} | {ma_val if ma_val is not None else 'N/A'} |\n"
        report += "\n"

        report += "### 4.5 布林带\n\n"
        boll = indicators.get("BOLL", {})
        boll_latest = boll.get("latest", {})
        if isinstance(boll_latest, dict):
            upper_val = boll_latest.get("upper")
            middle_val = boll_latest.get("middle")
            lower_val = boll_latest.get("lower")
            if hasattr(upper_val, "iloc"):
                upper_val = upper_val.iloc[-1] if not upper_val.empty else None
                middle_val = middle_val.iloc[-1] if middle_val is not None and not middle_val.empty else None
                lower_val = lower_val.iloc[-1] if lower_val is not None and not lower_val.empty else None
        else:
            upper_val = None
            middle_val = None
            lower_val = None
        report += "| 项目 | 价格 |\n"
        report += "|------|------|\n"
        report += f"| 上轨 | {upper_val if upper_val is not None else 'N/A'} |\n"
        report += f"| 中轨 | {middle_val if middle_val is not None else 'N/A'} |\n"
        report += f"| 下轨 | {lower_val if lower_val is not None else 'N/A'} |\n"
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
