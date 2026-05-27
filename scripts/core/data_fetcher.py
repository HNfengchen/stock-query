"""
数据获取层
负责从 xtquant/AkShare/efinance 获取数据，处理网络错误和重试逻辑
"""

import time
import threading
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional
import pandas as pd

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.logger import get_logger
from backend.logging import log_data

fetcher_logger = get_logger("data_fetcher")

# baostock 不支持并发 login/logout，用全局锁串行化
_baostock_lock = threading.Lock()

from scripts.stock_query import (
    parse_stock_code,
    get_stock_info,
    get_fund_flow,
    get_history_data,
    get_minute_data,
)
import efinance as ef

_db_module = None
_get_or_fetch_stock_data = None
_database_available = None

try:
    from scripts.database import get_or_fetch_stock_data as _get_or_fetch_fn
    import scripts.database as _db_mod
    _db_module = _db_mod
    _get_or_fetch_stock_data = _get_or_fetch_fn
except ImportError as e:
    print(f"[数据库] 模块导入失败: {e}")


def is_database_available() -> bool:
    global _database_available
    if _database_available is not None:
        return _database_available
    if _db_module is None:
        _database_available = False
        return False
    try:
        conn = _db_module.get_connection()
        conn.close()
        _database_available = True
        print(f"[数据库] 连接测试成功!")
    except Exception as e:
        _database_available = False
        print(f"[数据库] 连接失败: {e}")
    return _database_available


def reset_database_available():
    global _database_available
    _database_available = None

try:
    from scripts.core.xtquant_adapter import XtQuantAdapter, DataValidator

    XTQUANT_AVAILABLE = True
except ImportError:
    XTQUANT_AVAILABLE = False


_timeout_executor = None


def _get_timeout_executor():
    global _timeout_executor
    if _timeout_executor is None:
        _timeout_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
    return _timeout_executor


def _call_with_timeout(func, *args, timeout=15, **kwargs):
    executor = _get_timeout_executor()
    try:
        future = executor.submit(func, *args, **kwargs)
        done, not_done = concurrent.futures.wait([future], timeout=timeout)
        if not_done:
            not_done.pop().cancel()
            return None
        return future.result()
    except Exception:
        return None


class DataFetchError(Exception):
    """数据获取错误基类"""

    pass


class NetworkError(DataFetchError):
    """网络请求错误"""

    pass


class DataParseError(DataFetchError):
    """数据解析错误"""

    pass


class InvalidStockCodeError(Exception):
    """无效股票代码错误"""

    pass


class DataFetcher:
    """数据获取器"""

    def __init__(self, config: dict):
        self.config = config
        self.max_retries = config.get("data_fetcher", {}).get("max_retries", 2)
        self.retry_delay = config.get("data_fetcher", {}).get("retry_delay", 1)
        self.timeout = config.get("data_fetcher", {}).get("request_timeout", 30)

        self._xtquant_adapter = None
        self._validator = None

        if XTQUANT_AVAILABLE:
            try:
                self._xtquant_adapter = XtQuantAdapter(config.get("xtquant", {}))
                self._validator = DataValidator()
            except Exception as e:
                print(f"xtquant 初始化失败: {e}")

    def _retry_wrapper(self, func, *args, **kwargs):
        """带重试和超时的函数包装器"""
        last_error = None
        for attempt in range(self.max_retries):
            result = _call_with_timeout(func, *args, timeout=self.timeout, **kwargs)
            if result is not None:
                return result
            last_error = TimeoutError(f"Function {func.__name__} timed out after {self.timeout}s")
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)
        raise NetworkError(f"重试{self.max_retries}次后仍失败：{last_error}")

    def _safe_fetch(self, func, *args, **kwargs):
        """安全执行函数，捕获异常返回None"""
        try:
            return func(*args, **kwargs)
        except Exception:
            return None

    def resolve_stock_code(self, user_input: str) -> tuple:
        """
        解析用户输入为股票代码

        参数:
            user_input: 股票代码或名称

        返回:
            tuple: (stock_code, stock_name, market)
        """
        stock_code, market = parse_stock_code(user_input)
        if not stock_code:
            raise InvalidStockCodeError(f"无法识别股票 '{user_input}'，请检查输入")

        info = self._retry_wrapper(get_stock_info, stock_code)
        raw_name = info.get("名称", user_input)

        # 从带前缀的名称中提取市场标识（XD=除息, XR=除权, DR=除权除息, N=新股）
        market_tag = ""
        for prefix in ("XD", "XR", "DR", "N"):
            if raw_name.startswith(prefix) and len(raw_name) > len(prefix):
                market_tag = prefix
                break

        # 获取不带前缀的原始名称
        # efinance在除权除息日会在名称前加XD/XR/DR，且可能截断原名称字符
        # 优先级：watchlist缓存 > get_base_info > 剥离前缀
        clean_name = raw_name
        if market_tag:
            # 优先从watchlist获取缓存名称（添加自选股时名称是正确的）
            try:
                import json
                from pathlib import Path
                wl_path = Path(os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)))), "data", "watchlist.json")
                if wl_path.exists():
                    with open(wl_path, "r", encoding="utf-8") as f:
                        wl = json.load(f)
                    for item in wl:
                        if item.get("stock_code") == stock_code:
                            cached_name = item.get("stock_name", "")
                            if cached_name:
                                clean_name = cached_name
                                break
            except Exception:
                pass

            # 回退：尝试get_base_info
            if clean_name == raw_name:
                try:
                    base_info = self._retry_wrapper(ef.stock.get_base_info, stock_code)
                    if base_info is not None:
                        if isinstance(base_info, pd.DataFrame) and not base_info.empty:
                            base_name = base_info.iloc[0].get("股票名称", "")
                        elif isinstance(base_info, pd.Series):
                            base_name = base_info.get("股票名称", "")
                        else:
                            base_name = ""
                        if base_name and not pd.isna(base_name):
                            clean_name = str(base_name)
                except Exception:
                    pass

            # 最终回退：剥离前缀（可能少字符，但总比带前缀好）
            if clean_name == raw_name:
                clean_name = raw_name[len(market_tag):]

        return stock_code, clean_name, market, market_tag

    def fetch_stock_info(self, stock_code: str) -> Dict:
        """获取股票基本信息"""
        info = self._retry_wrapper(get_stock_info, stock_code)

        if self._xtquant_adapter:
            try:
                xtquant_info = self._xtquant_adapter.get_instrument_detail(
                    f"{stock_code}.{'SH' if stock_code.startswith(('60', '68')) else 'SZ'}"
                )
                if xtquant_info and not xtquant_info.get("error"):
                    for key in ["上市日期", "交易所", "总股本", "流通股本"]:
                        if key in xtquant_info and key not in info:
                            info[key] = xtquant_info[key]
            except Exception as e:
                print(f"xtquant 补充信息失败: {e}")

        return info

    def fetch_fund_flow(self, stock_code: str) -> Dict:
        """获取资金流向数据"""
        return self._retry_wrapper(get_fund_flow, stock_code)

    def fetch_history_data(self, stock_code: str, days: int = 60, klt: int = None) -> pd.DataFrame:
        """获取历史 K 线数据"""
        return self._retry_wrapper(get_history_data, stock_code, days, klt=klt)

    def fetch_minute_data(self, stock_code: str) -> Dict:
        """获取分钟级行情数据"""
        return self._retry_wrapper(get_minute_data, stock_code)

    def fetch_financial_data(self, stock_code: str) -> Dict:
        """获取财务数据"""
        if self._xtquant_adapter:
            try:
                full_code = f"{stock_code}.{'SH' if stock_code.startswith(('60', '68')) else 'SZ'}"
                return self._xtquant_adapter.get_financial_data([full_code])
            except Exception as e:
                print(f"获取财务数据失败: {e}")
        return {}

    def fetch_sector_info(self, stock_code: str) -> Dict:
        """获取板块信息"""
        sector_info = {"所属行业": "N/A", "所属概念": []}

        if self._xtquant_adapter:
            try:
                sectors = self._xtquant_adapter.get_sector_list()
                for sector in sectors:
                    stocks = self._xtquant_adapter.get_stock_list_in_sector(sector)
                    if stock_code in stocks:
                        if (
                            "所属概念" not in sector_info
                            or sector not in sector_info["所属概念"]
                        ):
                            sector_info["所属概念"].append(sector)

                if sector_info["所属概念"]:
                    sector_info["所属行业"] = sector_info["所属概念"][0]
            except Exception as e:
                print(f"获取板块信息失败: {e}")

        return sector_info

    def fetch_market_data(self) -> Optional[Dict]:
        """获取大盘数据（上证指数涨跌幅）

        数据源回退链: efinance(仅股票快照，不支持指数) -> baostock(支持指数历史数据)
        baostock 不支持并发，使用全局锁串行化。
        """
        try:
            import baostock as bs
            from datetime import datetime, timedelta

            def _baostock_fetch():
                with _baostock_lock:
                    lg = bs.login()
                    try:
                        today = datetime.now().strftime('%Y-%m-%d')
                        start = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
                        rs = bs.query_history_k_data_plus(
                            'sh.000001',
                            'date,pctChg',
                            start_date=start, end_date=today,
                            frequency='d'
                        )
                        rows = []
                        while rs.error_code == '0' and rs.next():
                            rows.append(rs.get_row_data())
                        if rows:
                            last = rows[-1]
                            change_val = float(last[1]) if len(last) > 1 else 0
                            return {"涨跌幅": change_val, "名称": "上证指数"}
                    finally:
                        bs.logout()
                return None

            result = _call_with_timeout(_baostock_fetch, timeout=20)
            if result:
                log_data('fetch', 'baostock', 'market_data', 'success',
                         change_pct=result.get("涨跌幅"))
                return result
        except Exception as e:
            log_data('fetch', 'baostock', 'market_data', 'failure', error=str(e))
            fetcher_logger.debug(f"[DataFetcher] baostock获取大盘数据失败: {e}")

        return None

    def validate_data(self, xtquant_data: Dict, backup_data: Dict) -> Dict:
        """交叉验证数据"""
        if self._validator:
            return self._validator.cross_validate(xtquant_data, backup_data)
        return {"is_valid": True, "source": "backup", "overall_confidence": 0.5}

    def create_health_check_callback(self):
        def callback(source):
            try:
                if source == "xtquant" and self._xtquant_adapter:
                    detail = self._xtquant_adapter.get_instrument_detail("000001.SH")
                    return detail is not None and not detail.get("error")
                info = self._safe_fetch(get_stock_info, "000001")
                return info is not None and len(info) > 0
            except Exception:
                return False
        return callback

    def fetch_index_data(self, index_code: str = "000300") -> pd.DataFrame:
        try:
            import efinance as ef

            prefix = "sh" if index_code.startswith(("000", "9")) else "sz"
            ef_code = f"{prefix}{index_code}"
            df = _call_with_timeout(ef.stock.get_quote_history, ef_code)
            if df is not None and not df.empty:
                col_map = {}
                if "收盘" not in df.columns and "close" in df.columns:
                    col_map["close"] = "收盘"
                if "日期" not in df.columns and "date" in df.columns:
                    col_map["date"] = "日期"
                if col_map:
                    df = df.rename(columns=col_map)
                if "收盘" in df.columns:
                    return df
        except Exception as e:
            fetcher_logger.debug(f"[DataFetcher] efinance获取指数数据失败: {e}")

        try:
            import baostock as bs

            lg = bs.login()
            prefix = "sh" if index_code.startswith(("000", "9")) else "sz"
            bs_code = f"{prefix}.{index_code}"
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,close",
                start_date="2024-01-01",
                frequency="d",
            )
            rows = []
            while rs.error_code == "0" and rs.next():
                rows.append(rs.get_row_data())
            bs.logout()
            if rows:
                df = pd.DataFrame(rows, columns=["日期", "收盘"])
                df["收盘"] = df["收盘"].astype(float)
                return df
        except Exception as e:
            fetcher_logger.debug(f"[DataFetcher] baostock获取指数数据失败: {e}")

        return pd.DataFrame()

    def fetch_industry_data(self, stock_code: str) -> pd.DataFrame:
        if self._xtquant_adapter:
            try:
                sectors = self._xtquant_adapter.get_sector_list()
                for sector in sectors:
                    stocks = self._xtquant_adapter.get_stock_list_in_sector(sector)
                    if stock_code in stocks:
                        industry_index_code = self._resolve_industry_index(sector)
                        if industry_index_code:
                            return self.fetch_index_data(industry_index_code)
                        break
            except Exception as e:
                fetcher_logger.debug(f"[DataFetcher] xtquant获取行业数据失败: {e}")

        try:
            import efinance as ef

            sector_df = _call_with_timeout(ef.stock.get_quote_snapshot, stock_code)
            if sector_df is not None and not sector_df.empty:
                pass
        except Exception:
            pass

        return pd.DataFrame()

    def _resolve_industry_index(self, industry_name: str) -> Optional[str]:
        industry_map = {
            "银行": "000801",
            "证券": "000802",
            "保险": "000803",
            "房地产": "000804",
            "医药生物": "000805",
            "食品饮料": "000806",
            "计算机": "000807",
            "电子": "000808",
            "通信": "000809",
            "传媒": "000810",
            "电力设备": "000811",
            "汽车": "000812",
            "机械设备": "000813",
            "化工": "000814",
            "钢铁": "000815",
            "有色金属": "000816",
            "采掘": "000817",
            "建筑材料": "000818",
            "建筑装饰": "000819",
            "国防军工": "000820",
            "家用电器": "000821",
            "轻工制造": "000822",
            "纺织服饰": "000823",
            "商贸零售": "000824",
            "社会服务": "000825",
            "农林牧渔": "000826",
            "公用事业": "000827",
            "交通运输": "000828",
            "综合": "000829",
        }
        for key, code in industry_map.items():
            if key in industry_name:
                return code
        return None

    def fetch_all_data(self, stock_input: str) -> Dict:
        """
        获取所有需要的数据

        参数:
            stock_input: 股票代码或名称

        返回:
            dict: 包含所有数据的字典
        """
        fetcher_logger.info("=" * 50)
        fetcher_logger.info(f"[DataFetcher] 开始获取股票数据: {stock_input}")

        stock_code, stock_name, market = self.resolve_stock_code(stock_input)
        fetcher_logger.info(
            f"[DataFetcher] 解析股票代码: {stock_code}, 名称: {stock_name}, 市场: {market}"
        )

        db_result = None
        if is_database_available():
            fetcher_logger.info(
                f"[DataFetcher] 数据库可用，检查并获取股票 {stock_code} 数据..."
            )
            db_result = _get_or_fetch_stock_data(
                stock_code, force_refresh=False, days=120
            )

            if db_result.get("source") == "database" and "history_df" in db_result:
                fetcher_logger.info(
                    f"[DataFetcher] 使用数据库中的历史数据 ({len(db_result['history_df'])} 条)"
                )
                history_df = db_result["history_df"]
                info = db_result.get("stock_info", {})
                fund_flow = db_result.get("fund_flow", {})
                log_data('fetch', 'database', 'history_df', 'success',
                         stock_code=stock_code, data_count=len(history_df))
                log_data('fetch', 'database', 'stock_info', 'success' if info else 'failure',
                         stock_code=stock_code)
                log_data('fetch', 'database', 'fund_flow', 'success' if fund_flow else 'failure',
                         stock_code=stock_code)
            else:
                info = None
        else:
            fetcher_logger.warning(f"[DataFetcher] 数据库不可用，从API获取数据...")
            info = None

        if info is None:
            fetcher_logger.info(f"[DataFetcher] 从API并发获取最新数据...")
            result = {}
            executor = ThreadPoolExecutor(max_workers=3)
            try:
                futures = {
                    executor.submit(self._safe_fetch, self.fetch_stock_info, stock_code): 'stock_info',
                    executor.submit(self._safe_fetch, self.fetch_fund_flow, stock_code): 'fund_flow',
                    executor.submit(self._safe_fetch, self.fetch_history_data, stock_code, 60): 'history_data',
                }
                try:
                    for future in as_completed(futures, timeout=20):
                        key = futures[future]
                        try:
                            result[key] = future.result(timeout=15)
                        except Exception:
                            result[key] = None
                except TimeoutError:
                    fetcher_logger.warning("[DataFetcher] 并发获取数据超时，收集已完成的结果")
                    for future, key in futures.items():
                        if key not in result:
                            if future.done():
                                try:
                                    result[key] = future.result()
                                except Exception:
                                    result[key] = None
                            else:
                                future.cancel()
                                result[key] = None
            finally:
                executor.shutdown(wait=False)

            info = result.get('stock_info')
            fund_flow = result.get('fund_flow')
            history_df = result.get('history_data')

            log_data('fetch', 'efinance', 'stock_info', 'success' if info else 'failure',
                     stock_code=stock_code)
            log_data('fetch', 'efinance', 'fund_flow', 'success' if fund_flow else 'failure',
                     stock_code=stock_code)
            if history_df is not None and not history_df.empty:
                log_data('fetch', 'baostock/efinance', 'history_df', 'success',
                         stock_code=stock_code, data_count=len(history_df))
            else:
                log_data('fetch', 'baostock/efinance', 'history_df', 'failure',
                         stock_code=stock_code)

            fetcher_logger.debug(
                f"[DataFetcher] 股票基本信息获取完成: {info.get('名称') if info else None}, 最新价: {info.get('最新价') if info else None}"
            )
            fetcher_logger.debug(
                f"[DataFetcher] 历史数据获取完成: {len(history_df) if history_df is not None else 0} 条"
            )

        info = info or {}
        fund_flow = fund_flow or {}

        fetcher_logger.info(f"[DataFetcher] 获取分钟级数据...")
        minute_data = self.fetch_minute_data(stock_code)

        fetcher_logger.info(f"[DataFetcher] 获取财务数据和板块信息...")
        financial_data = self.fetch_financial_data(stock_code)
        sector_info = self.fetch_sector_info(stock_code)

        if sector_info.get("所属行业") != "N/A" and "所属行业" not in info:
            info["所属行业"] = sector_info["所属行业"]

        market_data = {}
        # 使用 fetch_market_data() 获取上证指数（baostock 回退）
        try:
            result = self.fetch_market_data()
            if result:
                market_data = result
        except Exception as e:
            log_data('fetch', 'baostock', 'market_data', 'failure', error=str(e))
            fetcher_logger.debug(f"[DataFetcher] 获取大盘数据失败: {e}")

        fetcher_logger.info(f"[DataFetcher] 数据获取完成，返回结果")

        data_quality = "unknown"
        if is_database_available():
            try:
                if self._xtquant_adapter and db_result and db_result.get("source") == "api":
                    xtquant_full_code = f"{stock_code}.{'SH' if stock_code.startswith(('60', '68')) else 'SZ'}"
                    xtquant_info = self._xtquant_adapter.get_instrument_detail(xtquant_full_code)
                    if xtquant_info and not xtquant_info.get("error"):
                        xtquant_data = {
                            "最新价": xtquant_info.get("close"),
                            "成交量": xtquant_info.get("volume"),
                        }
                    else:
                        xtquant_data = {}
                    validator_result = self.validate_data(xtquant_data, info)
                    data_quality = (
                        "validated"
                        if validator_result.get("is_valid", False)
                        else "unvalidated"
                    )
                elif not is_database_available():
                    validator_result = self.validate_data(info, {})
                    data_quality = (
                        "validated"
                        if validator_result.get("is_valid", False)
                        else "unvalidated"
                    )
            except Exception as e:
                fetcher_logger.warning(f"[DataFetcher] 数据验证失败: {e}")
                data_quality = "validation_failed"

        all_data = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "market": market,
            "stock_info": info,
            "fund_flow": fund_flow,
            "history_data": history_df,
            "minute_data": minute_data,
            "financial_data": financial_data,
            "sector_info": sector_info,
            "data_quality": data_quality,
            "market_data": market_data,
        }
        has_all = (history_df is not None and not history_df.empty
                   and info and fund_flow and market_data)
        log_data('assemble', 'all_sources', 'all_data', 'success' if has_all else 'partial',
                 stock_code=stock_code,
                 has_history=history_df is not None and not history_df.empty,
                 has_stock_info=bool(info),
                 has_fund_flow=bool(fund_flow),
                 has_market_data=bool(market_data))
        return all_data
