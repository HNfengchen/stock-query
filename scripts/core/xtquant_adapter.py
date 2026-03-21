"""
xtquant 数据适配器
基于迅投接口文档重构数据获取层
"""

import time
from typing import Dict, Optional, List
import pandas as pd
import numpy as np


class XtQuantAdapter:
    """xtquant 数据适配器"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._client = None
        self._connected = False
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 1)

    def _ensure_connection(self):
        """确保连接到 xtquant"""
        if self._connected:
            return True

        try:
            from xtquant import xtdata

            self._xtdata = xtdata
            self._connected = True
            return True
        except ImportError:
            print("警告: xtquant 未安装，将回退到原始数据源")
            return False
        except Exception as e:
            print(f"xtquant 连接失败: {e}")
            return False

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
        raise Exception(f"重试{self.max_retries}次后仍失败：{last_error}")

    def download_stock_data(
        self,
        stock_code: str,
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
    ):
        """下载股票历史数据"""
        if not self._ensure_connection():
            return None

        try:
            self._xtdata.download_history_data(stock_code, period, start_time, end_time)
            return True
        except Exception as e:
            print(f"下载数据失败: {e}")
            return False

    def get_market_data(
        self,
        stock_list: List[str],
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        count: int = -1,
        dividend_type: str = "none",
    ) -> Dict:
        """获取市场行情数据"""
        if not self._ensure_connection():
            return {}

        try:
            data = self._xtdata.get_market_data(
                field_list=[],
                stock_list=stock_list,
                period=period,
                start_time=start_time,
                end_time=end_time,
                count=count,
                dividend_type=dividend_type,
            )
            return data if data else {}
        except Exception as e:
            print(f"获取行情数据失败: {e}")
            return {}

    def get_instrument_detail(self, stock_code: str, iscomplete: bool = False) -> Dict:
        """获取合约基础信息"""
        if not self._ensure_connection():
            return {}

        try:
            return self._xtdata.get_instrument_detail(stock_code, iscomplete) or {}
        except Exception as e:
            print(f"获取合约信息失败: {e}")
            return {}

    def get_stock_info(self, stock_code: str) -> Dict:
        """获取股票基本信息 - 使用 xtquant"""
        info = {"代码": stock_code}

        detail = self.get_instrument_detail(stock_code)
        if detail:
            info["名称"] = detail.get("InstrumentName", "N/A")
            info["上市日期"] = detail.get("OpenDate", "N/A")
            info["交易所"] = detail.get("ExchangeID", "N/A")

        market_data = self.get_market_data([stock_code], "1d", count=1)
        if market_data:
            close_data = market_data.get("close")
            if close_data is not None and not close_data.empty:
                info["最新价"] = (
                    close_data.iloc[0, 0] if not close_data.empty else "N/A"
                )

            volume_data = market_data.get("volume")
            if volume_data is not None and not volume_data.empty:
                info["成交量"] = (
                    volume_data.iloc[0, 0] if not volume_data.empty else "N/A"
                )

            amount_data = market_data.get("amount")
            if amount_data is not None and not amount_data.empty:
                info["成交额"] = (
                    amount_data.iloc[0, 0] if not amount_data.empty else "N/A"
                )

        return info

    def get_financial_data(
        self, stock_list: List[str], table_list: List[str] = None
    ) -> Dict:
        """获取财务数据"""
        if not self._ensure_connection():
            return {}

        if table_list is None:
            table_list = [
                "Balance",
                "Income",
                "CashFlow",
                "Capital",
                "Holdernum",
                "Top10holder",
                "Top10flowholder",
                "Pershareindex",
            ]

        try:
            return self._xtdata.get_financial_data(stock_list, table_list) or {}
        except Exception as e:
            print(f"获取财务数据失败: {e}")
            return {}

    def get_sector_list(self) -> List[str]:
        """获取板块列表"""
        if not self._ensure_connection():
            return []

        try:
            return self._xtdata.get_sector_list() or []
        except Exception as e:
            print(f"获取板块列表失败: {e}")
            return []

    def get_stock_list_in_sector(self, sector_name: str) -> List[str]:
        """获取板块成分股"""
        if not self._ensure_connection():
            return []

        try:
            return self._xtdata.get_stock_list_in_sector(sector_name) or []
        except Exception as e:
            print(f"获取板块成分股失败: {e}")
            return []

    def get_holidays(self) -> List[str]:
        """获取节假日列表"""
        if not self._ensure_connection():
            return []

        try:
            return self._xtdata.get_holidays() or []
        except Exception as e:
            print(f"获取节假日失败: {e}")
            return []

    def get_trading_calendar(
        self, market: str = "SZ", start_time: str = "", end_time: str = ""
    ) -> List:
        """获取交易日历"""
        if not self._ensure_connection():
            return []

        try:
            return self._xtdata.get_trading_calendar(market, start_time, end_time) or []
        except Exception as e:
            print(f"获取交易日历失败: {e}")
            return []

    def parse_stock_code(self, user_input: str) -> tuple:
        """解析用户输入为股票代码"""
        user_input = user_input.strip().replace(" ", "")

        if user_input.isdigit():
            code = user_input.zfill(6)
            if code.startswith(("60", "68")):
                market = "sh"
            elif code.startswith(("00", "30", "688")):
                market = "sz"
            else:
                market = "sz"
            return code, market

        return None, None

    def resolve_stock_code(self, user_input: str) -> tuple:
        """解析用户输入，返回完整股票代码和市场"""
        stock_code, market = self.parse_stock_code(user_input)
        if not stock_code:
            return None, None, None

        full_code = f"{stock_code}.{'SH' if market == 'sh' else 'SZ'}"

        info = self.get_stock_info(full_code)
        stock_name = info.get("名称", user_input)

        return full_code, stock_name, market


class DataValidator:
    """多源数据交叉验证器"""

    def __init__(self):
        self.validation_results = {}

    def validate_price(
        self, price_xtquant: float, price_backup: float, tolerance: float = 0.05
    ) -> Dict:
        """验证价格一致性"""
        if price_xtquant is None or price_backup is None:
            return {"valid": False, "reason": "数据缺失"}

        if price_backup == 0:
            return {"valid": True, "source": "xtquant", "confidence": 1.0}

        diff_ratio = abs(price_xtquant - price_backup) / price_backup

        if diff_ratio <= tolerance:
            return {
                "valid": True,
                "match": True,
                "diff_ratio": diff_ratio,
                "confidence": 1.0 - diff_ratio,
            }
        else:
            return {
                "valid": True,
                "match": False,
                "diff_ratio": diff_ratio,
                "confidence": 0.5,
                "source": "xtquant" if price_xtquant else "backup",
            }

    def validate_volume(
        self, volume_xtquant: float, volume_backup: float, tolerance: float = 0.1
    ) -> Dict:
        """验证成交量一致性"""
        if volume_xtquant is None or volume_backup is None:
            return {"valid": False, "reason": "数据缺失"}

        if volume_backup == 0:
            return {"valid": True, "source": "xtquant", "confidence": 1.0}

        diff_ratio = abs(volume_xtquant - volume_backup) / volume_backup

        if diff_ratio <= tolerance:
            return {
                "valid": True,
                "match": True,
                "diff_ratio": diff_ratio,
                "confidence": 1.0 - diff_ratio,
            }
        else:
            return {
                "valid": True,
                "match": False,
                "diff_ratio": diff_ratio,
                "confidence": 0.5,
                "source": "xtquant" if volume_xtquant else "backup",
            }

    def cross_validate(self, xtquant_data: Dict, backup_data: Dict) -> Dict:
        """交叉验证两个数据源"""
        results = {"is_valid": True, "checks": {}, "overall_confidence": 1.0}

        if not xtquant_data and not backup_data:
            results["is_valid"] = False
            results["reason"] = "两个数据源都不可用"
            return results

        if not xtquant_data and backup_data:
            results["is_valid"] = True
            results["source"] = "backup"
            results["overall_confidence"] = 0.6
            return results

        if xtquant_data and not backup_data:
            results["is_valid"] = True
            results["source"] = "xtquant"
            results["overall_confidence"] = 1.0
            return results

        price_result = self.validate_price(
            xtquant_data.get("最新价"), backup_data.get("最新价")
        )
        results["checks"]["price"] = price_result

        volume_result = self.validate_volume(
            xtquant_data.get("成交量"), backup_data.get("成交量")
        )
        results["checks"]["volume"] = volume_result

        confidences = [
            price_result.get("confidence", 0),
            volume_result.get("confidence", 0),
        ]
        results["overall_confidence"] = sum(confidences) / len(confidences)

        return results
