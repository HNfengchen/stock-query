"""
数据获取层
负责从 xtquant/AkShare/efinance 获取数据，处理网络错误和重试逻辑
"""

import time
import atexit
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
from scripts.core.circuit_breaker import CircuitBreaker
from scripts.stock_query import (
    parse_stock_code,
    get_stock_info,
    get_fund_flow,
    get_history_data,
    get_minute_data,
)
import efinance as ef

fetcher_logger = get_logger("data_fetcher")

# 模块级线程池，供 fetch_all_data 复用，避免每次调用都创建新线程池
_fetch_executor = ThreadPoolExecutor(max_workers=3)
atexit.register(_fetch_executor.shutdown)

# baostock 不支持并发 login/logout，用全局锁串行化
_baostock_lock = threading.Lock()

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
        print("[数据库] 连接测试成功!")
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
        # 超时执行器在任务取消/失败时统一返回None，由调用方决定重试
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

        dv_config = config.get("data_validation", {})
        self._circuit_breaker = CircuitBreaker(
            timeout=dv_config.get("circuit_breaker_timeout", 300),
            source_priority=["xtquant", "efinance", "baostock", "tencent"],
            health_check_interval=dv_config.get("health_check_interval", 60),
        )
        self._circuit_breaker.set_health_check_callback(self.create_health_check_callback())
        if dv_config.get("enabled", True):
            self._circuit_breaker.start_health_check()
            fetcher_logger.info(
                "[熔断器] 已初始化: timeout=%d, health_check_interval=%d",
                self._circuit_breaker._timeout,
                self._circuit_breaker._health_check_interval,
            )

    def close(self):
        """关闭数据获取器。

        线程池已由模块级 _fetch_executor 复用，并通过 atexit 统一清理。
        """
        pass

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
            # 该辅助函数设计为静默 swallow，由外层熔断器/重试逻辑处理
            return None

    def _fetch_with_circuit_breaker(self, source: str, func, *args, **kwargs):
        """带熔断器保护的数据获取

        先检查数据源健康状态，不健康则跳过；调用成功后恢复状态，
        失败或返回空结果则标记为不健康。
        """
        if not self._circuit_breaker.is_healthy(source):
            fetcher_logger.info("[熔断器] 数据源 %s 当前不健康，跳过调用", source)
            return None

        try:
            result = func(*args, **kwargs)
            is_empty = result is None
            if isinstance(result, pd.DataFrame):
                is_empty = result.empty
            elif isinstance(result, dict):
                is_empty = len(result) == 0

            if is_empty:
                self._circuit_breaker.mark_unhealthy(source, "返回空结果")
                return None

            self._circuit_breaker.mark_healthy(source)
            return result
        except Exception as e:
            self._circuit_breaker.mark_unhealthy(source, str(e))
            fetcher_logger.warning("[熔断器] 数据源 %s 调用失败并标记不健康: %s", source, e)
            return None

    def get_circuit_breaker_status(self) -> dict:
        """获取熔断器当前状态（用于监控和测试）"""
        return self._circuit_breaker.get_status()

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
        # 防御：efinance/pandas可能返回float(NaN)作为名称
        if not isinstance(raw_name, str):
            import pandas as pd
            if raw_name is None or (isinstance(raw_name, float) and pd.isna(raw_name)):
                raw_name = user_input
            else:
                raw_name = str(raw_name)

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
                fetcher_logger.debug(f"[{stock_code}] 从watchlist读取缓存名称失败", exc_info=True)

            # 回退：尝试get_base_info
            if clean_name == raw_name and self._circuit_breaker.is_healthy("efinance"):
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
                    fetcher_logger.debug(f"[{stock_code}] 从efinance获取基础信息失败", exc_info=True)

            # 最终回退：剥离前缀（可能少字符，但总比带前缀好）
            if clean_name == raw_name:
                clean_name = raw_name[len(market_tag):]

        return stock_code, clean_name, market, market_tag

    def fetch_stock_info(self, stock_code: str) -> Dict:
        """获取股票基本信息"""
        info = self._fetch_with_circuit_breaker(
            "efinance", self._retry_wrapper, get_stock_info, stock_code
        )
        if info is None:
            info = {}

        if self._xtquant_adapter and self._circuit_breaker.is_healthy("xtquant"):
            try:
                xtquant_info = self._xtquant_adapter.get_instrument_detail(
                    f"{stock_code}.{'SH' if stock_code.startswith(('60', '68')) else 'SZ'}"
                )
                if xtquant_info and not xtquant_info.get("error"):
                    for key in ["上市日期", "交易所", "总股本", "流通股本"]:
                        if key in xtquant_info and key not in info:
                            info[key] = xtquant_info[key]
            except Exception as e:
                self._circuit_breaker.mark_unhealthy("xtquant", str(e))
                print(f"xtquant 补充信息失败: {e}")

        return info

    def fetch_fund_flow(self, stock_code: str) -> Dict:
        """获取资金流向数据"""
        result = self._fetch_with_circuit_breaker(
            "efinance", self._retry_wrapper, get_fund_flow, stock_code
        )
        return result if result is not None else {}

    def fetch_history_data(
        self, stock_code: str, bars: int = 60, klt: int = None, days: int = None
    ) -> pd.DataFrame:
        """获取历史 K 线数据

        参数:
            bars: 请求的 K 线条数（明确语义），默认 60
            klt: K 线类型，None/1=日线, 101=周线, 102=月线
            days: 已废弃，仅作为 bars 的别名保留向后兼容
        """
        if days is not None:
            bars = days
        result = self._fetch_with_circuit_breaker(
            "efinance", self._retry_wrapper, get_history_data, stock_code, bars, klt=klt
        )
        return result if result is not None else pd.DataFrame()

    def fetch_minute_data(self, stock_code: str) -> Dict:
        """获取分钟级行情数据"""
        result = self._fetch_with_circuit_breaker(
            "efinance", self._retry_wrapper, get_minute_data, stock_code
        )
        return result if result is not None else {}

    def fetch_financial_data(self, stock_code: str) -> Dict:
        """获取财务数据"""
        def _xtquant_fetch():
            if not self._xtquant_adapter:
                return None
            full_code = f"{stock_code}.{'SH' if stock_code.startswith(('60', '68')) else 'SZ'}"
            return self._xtquant_adapter.get_financial_data([full_code])

        result = self._fetch_with_circuit_breaker("xtquant", _xtquant_fetch)
        return result if result is not None else {}

    def fetch_sector_momentum(self, stock_code: str, shared_sector_quotes: pd.DataFrame = None) -> Optional[Dict]:
        """获取个股所属板块的动量信息（板块涨幅、排名、资金方向）

        数据源: efinance get_belong_board (返回个股所属板块+板块涨幅)
        批量分析时传入 shared_sector_quotes 避免重复获取行业板块行情

        Returns:
            dict: {
                'best_sector_name': str,     # 最强行业板块名称
                'best_sector_change': float,  # 最强行业板块涨幅(%)
                'sector_rank': int,           # 最强行业板块在所有行业中的涨幅排名(1-based)
                'total_sectors': int,         # 行业板块总数
                'sector_net_inflow_positive': bool,  # 板块资金净流入方向(涨幅>0视为净流入)
            } 或 None(获取失败时)
        """
        if not self._circuit_breaker.is_healthy("efinance"):
            fetcher_logger.info("[熔断器] efinance 当前不健康，跳过板块动量获取")
            return None

        try:
            import efinance as ef

            # 获取个股所属板块
            try:
                belong_df = ef.stock.get_belong_board(stock_code)
            except TypeError:
                # ETF/基金等非股票代码，efinance不支持获取板块信息
                fetcher_logger.info(f"板块动量[{stock_code}]: ETF/基金不支持板块查询，跳过板块修正")
                return None
            except Exception as e:
                fetcher_logger.warning(f"获取{stock_code}所属板块失败: {e}")
                self._circuit_breaker.mark_unhealthy("efinance", str(e))
                return None

            if belong_df is None or belong_df.empty:
                fetcher_logger.warning(f"获取{stock_code}所属板块返回空")
                self._circuit_breaker.mark_unhealthy("efinance", "返回空结果")
                return None

            # 从所属板块中筛选行业板块（排除地域、指数、风格等非行业板块）
            # 行业板块特征: 板块名称较短且不含"板块"/"概念"/"风格"等关键词
            non_industry_keywords = ["板块", "概念", "风格", "股", "重仓", "持股", "融资", "热股",
                                     "高振幅", "预增", "预减", "预盈", "预亏", "昨"]
            industry_sectors = []
            for _, row in belong_df.iterrows():
                name = str(row.get("板块名称", ""))
                change = row.get("板块涨幅", 0)
                try:
                    change = float(change)
                except (TypeError, ValueError):
                    change = 0.0
                # 排除非行业板块
                skip = False
                for kw in non_industry_keywords:
                    if kw in name:
                        skip = True
                        break
                if not skip and len(name) <= 6:  # 行业名称通常较短
                    industry_sectors.append({"name": name, "change": change})

            if not industry_sectors:
                # 回退: 使用涨幅最高的前3个板块
                for _, row in belong_df.head(3).iterrows():
                    name = str(row.get("板块名称", ""))
                    change = row.get("板块涨幅", 0)
                    try:
                        change = float(change)
                    except (TypeError, ValueError):
                        change = 0.0
                    industry_sectors.append({"name": name, "change": change})

            if not industry_sectors:
                return None

            # 取涨幅最高的行业板块
            best = max(industry_sectors, key=lambda x: x["change"])

            # 获取行业板块行情来计算排名
            total_sectors = 31  # 申万一级行业约31个
            sector_rank = total_sectors  # 默认排名靠后

            if shared_sector_quotes is not None and not shared_sector_quotes.empty:
                # 从共享的行业板块行情中计算排名
                try:
                    sector_changes = shared_sector_quotes["涨跌幅"].dropna().astype(float)
                    total_sectors = len(sector_changes)
                    # 涨幅从高到低排名
                    sector_rank = int((sector_changes > best["change"]).sum()) + 1
                except Exception:
                    fetcher_logger.debug(f"[{stock_code}] 从共享板块行情计算排名失败", exc_info=True)
            else:
                # 尝试获取行业板块行情来计算排名
                # 优先efinance，回退新浪财经
                sector_rank_found = False
                try:
                    sector_df = ef.stock.get_realtime_quotes(fs='行业板块')
                    if sector_df is not None and not sector_df.empty:
                        sector_changes = sector_df["涨跌幅"].dropna().astype(float)
                        total_sectors = len(sector_changes)
                        sector_rank = int((sector_changes > best["change"]).sum()) + 1
                        sector_rank_found = True
                except Exception:
                    fetcher_logger.debug(f"[{stock_code}] 从efinance获取行业板块行情失败", exc_info=True)

                if not sector_rank_found:
                    # 回退: 新浪财经行业板块行情
                    try:
                        import requests as _req
                        _r = _req.get('https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php', timeout=5)
                        if _r.status_code == 200 and _r.text:
                            import json as _json
                            _raw = _r.text
                            _start = _raw.index('{')
                            _end = _raw.rindex('}') + 1
                            _data = _json.loads(_raw[_start:_end])
                            _industry_changes = []
                            for _key, _val in _data.items():
                                _fields = _val.split(',')
                                if len(_fields) >= 6:
                                    try:
                                        _ch = float(_fields[5])  # [5]=涨跌幅(%), [4]=涨跌额
                                        _industry_changes.append(_ch)
                                    except (ValueError, IndexError):
                                        pass
                            if _industry_changes:
                                total_sectors = len(_industry_changes)
                                sector_rank = int(sum(1 for c in _industry_changes if c > best["change"])) + 1
                                sector_rank_found = True
                    except Exception:
                        fetcher_logger.debug(f"[{stock_code}] 从新浪获取行业板块行情失败", exc_info=True)

                if not sector_rank_found:
                    # efinance和新浪均不可用时，不返回排名数据
                    # 宁可不触发板块修正，也不给出不准确的估算排名
                    fetcher_logger.info(f"板块动量[{stock_code}]: 行业排名数据源均不可用，跳过板块修正")
                    return None

            result = {
                "best_sector_name": best["name"],
                "best_sector_change": best["change"],
                "sector_rank": sector_rank,
                "total_sectors": total_sectors,
                "sector_net_inflow_positive": best["change"] > 0,
            }
            fetcher_logger.info(
                f"板块动量[{stock_code}]: 最强行业={best['name']}({best['change']:.2f}%), "
                f"排名={sector_rank}/{total_sectors}, 净流入方向={'正' if best['change'] > 0 else '负'}"
            )
            return result

        except Exception as e:
            fetcher_logger.warning(f"获取板块动量数据失败[{stock_code}]: {e}")
            self._circuit_breaker.mark_unhealthy("efinance", str(e))
            return None

    def fetch_sector_info(self, stock_code: str) -> Dict:
        """获取板块信息"""
        sector_info = {"所属行业": "N/A", "所属概念": []}

        def _xtquant_fetch():
            if not self._xtquant_adapter:
                return None
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
            return sector_info

        result = self._fetch_with_circuit_breaker("xtquant", _xtquant_fetch)
        return result if result is not None else sector_info

    def fetch_market_data(self) -> Optional[Dict]:
        """获取大盘数据（上证指数涨跌幅）

        数据源回退链: efinance(仅股票快照，不支持指数) -> baostock(支持指数历史数据)
        baostock 不支持并发，使用全局锁串行化。
        """
        # 优先尝试 efinance（无需登录）
        def _efinance_fetch():
            import efinance as ef

            snapshot = _call_with_timeout(ef.stock.get_quote_snapshot, "000001")
            if snapshot is not None and not snapshot.empty:
                change = snapshot.get("涨跌幅")
                if change is not None and not pd.isna(change):
                    return {"涨跌幅": float(change), "名称": "上证指数"}
            return None

        result = self._fetch_with_circuit_breaker("efinance", _efinance_fetch)
        if result:
            log_data('fetch', 'efinance', 'market_data', 'success',
                     change_pct=result.get("涨跌幅"))
            return result

        # 回退到 baostock
        def _baostock_fetch():
            import baostock as bs
            from datetime import datetime, timedelta

            with _baostock_lock:
                lg = bs.login()
                if lg.error_code != "0":
                    raise DataFetchError(
                        f"baostock login failed: {lg.error_code} {lg.error_msg}"
                    )
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

        result = self._fetch_with_circuit_breaker("baostock", _baostock_fetch)
        if result:
            log_data('fetch', 'baostock', 'market_data', 'success',
                     change_pct=result.get("涨跌幅"))
            return result

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
                fetcher_logger.warning("数据源健康检查异常", exc_info=True)
                return False
        return callback

    def fetch_index_data(self, index_code: str = "000300") -> pd.DataFrame:
        def _efinance_fetch():
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
            return None

        df = self._fetch_with_circuit_breaker("efinance", _efinance_fetch)
        if df is not None:
            return df

        def _baostock_fetch():
            import baostock as bs

            with _baostock_lock:
                lg = bs.login()
                if lg.error_code != "0":
                    raise DataFetchError(
                        f"baostock login failed: {lg.error_code} {lg.error_msg}"
                    )
                try:
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
                finally:
                    bs.logout()
            if rows:
                df = pd.DataFrame(rows, columns=["日期", "收盘"])
                df["收盘"] = df["收盘"].astype(float)
                return df
            return None

        df = self._fetch_with_circuit_breaker("baostock", _baostock_fetch)
        if df is not None:
            return df

        return pd.DataFrame()

    def fetch_industry_data(self, stock_code: str) -> pd.DataFrame:
        def _xtquant_fetch():
            if not self._xtquant_adapter:
                return None
            sectors = self._xtquant_adapter.get_sector_list()
            for sector in sectors:
                stocks = self._xtquant_adapter.get_stock_list_in_sector(sector)
                if stock_code in stocks:
                    industry_index_code = self._resolve_industry_index(sector)
                    if industry_index_code:
                        df = self.fetch_index_data(industry_index_code)
                        if df is not None and not df.empty:
                            return df
                    break
            return None

        df = self._fetch_with_circuit_breaker("xtquant", _xtquant_fetch)
        if df is not None:
            return df

        def _efinance_fetch():
            import efinance as ef

            sector_df = _call_with_timeout(ef.stock.get_quote_snapshot, stock_code)
            if sector_df is not None and not sector_df.empty:
                # efinance 板块快照不直接返回指数 K 线，当前仅作为健康探测
                return pd.DataFrame({"探测": [True]})
            return None

        self._fetch_with_circuit_breaker("efinance", _efinance_fetch)

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

        stock_code, stock_name, market, market_tag = self.resolve_stock_code(stock_input)
        fetcher_logger.info(
            f"[DataFetcher] 解析股票代码: {stock_code}, 名称: {stock_name}, 市场: {market}"
            + (f", 标识: {market_tag}" if market_tag else "")
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
            fetcher_logger.warning("[DataFetcher] 数据库不可用，从API获取数据...")
            info = None

        if info is None:
            fetcher_logger.info("[DataFetcher] 从API并发获取最新数据...")
            result = {}
            executor = _fetch_executor
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
                        fetcher_logger.warning(f"[DataFetcher] 获取{key}结果异常", exc_info=True)
                        result[key] = None
            except TimeoutError:
                fetcher_logger.warning("[DataFetcher] 并发获取数据超时，收集已完成的结果")
                for future, key in futures.items():
                    if key not in result:
                        if future.done():
                            try:
                                result[key] = future.result()
                            except Exception:
                                fetcher_logger.warning(f"[DataFetcher] 获取{key}结果异常", exc_info=True)
                                result[key] = None
                        else:
                            future.cancel()
                            result[key] = None

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

        fetcher_logger.info("[DataFetcher] 获取分钟级数据...")
        minute_data = self.fetch_minute_data(stock_code)

        fetcher_logger.info("[DataFetcher] 获取财务数据和板块信息...")
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

        fetcher_logger.info("[DataFetcher] 数据获取完成，返回结果")

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
