"""
数据获取层
负责从 xtquant/AkShare/efinance 获取数据，处理网络错误和重试逻辑
"""

import time
from typing import Dict, Optional
import pandas as pd

from scripts.stock_query import (
    parse_stock_code,
    get_stock_info,
    get_fund_flow,
    get_history_data,
    get_minute_data,
)

try:
    from scripts.core.xtquant_adapter import XtQuantAdapter, DataValidator

    XTQUANT_AVAILABLE = True
except ImportError:
    XTQUANT_AVAILABLE = False


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
        self.max_retries = config.get("data_fetcher", {}).get("max_retries", 3)
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
        """带重试的函数包装器"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                continue
        raise NetworkError(f"重试{self.max_retries}次后仍失败：{last_error}")

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
        stock_name = info.get("名称", user_input)

        return stock_code, stock_name, market

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

    def fetch_history_data(self, stock_code: str, days: int = 60) -> pd.DataFrame:
        """获取历史 K 线数据"""
        return self._retry_wrapper(get_history_data, stock_code, days)

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

    def validate_data(self, xtquant_data: Dict, backup_data: Dict) -> Dict:
        """交叉验证数据"""
        if self._validator:
            return self._validator.cross_validate(xtquant_data, backup_data)
        return {"is_valid": True, "source": "backup", "overall_confidence": 0.5}

    def fetch_all_data(self, stock_input: str) -> Dict:
        """
        获取所有需要的数据

        参数:
            stock_input: 股票代码或名称

        返回:
            dict: 包含所有数据的字典
        """
        stock_code, stock_name, market = self.resolve_stock_code(stock_input)

        info = self.fetch_stock_info(stock_code)
        fund_flow = self.fetch_fund_flow(stock_code)
        history_df = self.fetch_history_data(stock_code, 60)
        minute_data = self.fetch_minute_data(stock_code)

        financial_data = self.fetch_financial_data(stock_code)
        sector_info = self.fetch_sector_info(stock_code)

        if sector_info.get("所属行业") != "N/A" and "所属行业" not in info:
            info["所属行业"] = sector_info["所属行业"]

        return {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "market": market,
            "stock_info": info,
            "fund_flow": fund_flow,
            "history_data": history_df,
            "minute_data": minute_data,
            "financial_data": financial_data,
            "sector_info": sector_info,
        }
