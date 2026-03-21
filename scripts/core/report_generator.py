"""
报告生成层
负责生成 HTML 格式报告，包含交互式图表
使用 Chart.js 进行图表渲染
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
from jinja2 import Template

from scripts.technical_indicators import calculate_all_indicators


class ReportGenerationError(Exception):
    """报告生成错误"""

    pass


class ReportGenerator:
    """报告生成器"""

    def __init__(self, config: dict, template_path: Optional[str] = None):
        self.config = config
        self.chart_height = config.get("report", {}).get("chart_height", 600)
        self.include_charts = config.get("report", {}).get("include_charts", True)

        if template_path is None:
            template_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "templates",
                "report_template.html",
            )

        with open(template_path, "r", encoding="utf-8") as f:
            self.template = Template(f.read())

    def _format_number(self, value, unit: str = "", auto_unit: bool = True) -> str:
        """格式化数字"""
        if value is None or value == "N/A":
            return "N/A"
        try:
            num = float(value)
            if auto_unit:
                if abs(num) >= 1e8:
                    return f"{num / 1e8:.2f}亿{unit}"
                elif abs(num) >= 1e4:
                    return f"{num / 1e4:.2f}万{unit}"
            return f"{num:.2f}{unit}"
        except (ValueError, TypeError):
            return str(value)

    def _format_market_value(self, value) -> str:
        """格式化市值"""
        if value is None or value == "N/A":
            return "N/A"
        try:
            num = float(value)
            if num >= 1e8:
                return f"{num / 1e8:.2f}亿"
            elif num >= 1e4:
                return f"{num / 1e4:.2f}万"
            return f"{num:.2f}"
        except (ValueError, TypeError):
            return str(value)

    def _format_trend(self, trend: str) -> str:
        """格式化趋势"""
        trend_map = {
            "inflow": "净流入",
            "outflow": "净流出",
            "neutral": "持平",
        }
        return trend_map.get(trend, trend)

    def _safe_float(self, value, default=0.0):
        """安全转换为浮点数"""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _to_list(self, value) -> List:
        """转换为列表"""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def _prepare_kline_data(self, df: pd.DataFrame) -> Dict:
        """准备K线图数据"""
        if df is None or df.empty:
            return {
                "labels": [],
                "candles": [],
                "ma5": [],
                "ma10": [],
                "ma20": [],
                "opens": [],
                "highs": [],
                "lows": [],
                "closes": [],
            }

        df = df.copy()

        close = df["收盘"].tolist() if "收盘" in df.columns else []
        high = df["最高"].tolist() if "最高" in df.columns else []
        low = df["最低"].tolist() if "最低" in df.columns else []
        open_price = df["开盘"].tolist() if "开盘" in df.columns else []

        df["ma5"] = df["收盘"].rolling(window=5).mean()
        df["ma10"] = df["收盘"].rolling(window=10).mean()
        df["ma20"] = df["收盘"].rolling(window=20).mean()

        ma5 = df["ma5"].fillna(0).tolist()
        ma10 = df["ma10"].fillna(0).tolist()
        ma20 = df["ma20"].fillna(0).tolist()

        if "日期" in df.columns:
            labels = (
                pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d").tolist()
                if hasattr(df["日期"], "dt")
                else [str(d) for d in df["日期"]]
            )
        elif df.index.name == "date":
            labels = pd.to_datetime(df.index).strftime("%Y-%m-%d").tolist()
        else:
            date_col = df.get("日期", df.index)
            if date_col is None:
                date_col = df.index
            labels = [str(d) for d in date_col]

        return {
            "labels": labels,
            "opens": [float(o) if o is not None and not pd.isna(o) else 0.0 for o in open_price],
            "highs": [float(h) if h is not None and not pd.isna(h) else 0.0 for h in high],
            "lows": [float(l) if l is not None and not pd.isna(l) else 0.0 for l in low],
            "closes": [float(c) if c is not None and not pd.isna(c) else 0.0 for c in close],
            "ma5": [float(m) if m is not None and not pd.isna(m) else 0.0 for m in ma5],
            "ma10": [float(m) if m is not None and not pd.isna(m) else 0.0 for m in ma10],
            "ma20": [float(m) if m is not None and not pd.isna(m) else 0.0 for m in ma20],
        }

    def _prepare_technical_data(self, history_df: pd.DataFrame) -> Dict:
        """从历史数据计算并准备技术指标图数据"""
        if history_df is None or history_df.empty:
            return {
                "labels": [],
                "macd": [],
                "dif": [],
                "dea": [],
                "rsi6": [],
                "rsi12": [],
                "k": [],
                "d": [],
                "j": [],
            }

        closes = history_df["收盘"].tolist()
        highs = history_df["最高"].tolist()
        lows = history_df["最低"].tolist()

        if "日期" in history_df.columns:
            dates = (
                pd.to_datetime(history_df["日期"]).dt.strftime("%Y-%m-%d").tolist()
                if hasattr(history_df["日期"], "dt")
                else [str(d)[:10] for d in history_df["日期"]]
            )
        else:
            dates = [str(d)[:10] for d in history_df.index]

        closes_series = pd.Series(closes)
        highs_series = pd.Series(highs)
        lows_series = pd.Series(lows)
        n = len(closes)

        dif_list = [None] * n
        dea_list = [None] * n
        macd_list = [None] * n
        rsi6_list = [None] * n
        rsi12_list = [None] * n
        k_list = [None] * n
        d_list = [None] * n
        j_list = [None] * n

        if n >= 34:
            ema_fast = closes_series.ewm(span=12, adjust=False).mean()
            ema_slow = closes_series.ewm(span=26, adjust=False).mean()
            dif = ema_fast - ema_slow
            dea = dif.ewm(span=9, adjust=False).mean()
            macd_bar = (dif - dea) * 2

            dif_list = [float(x) if not pd.isna(x) else 0.0 for x in dif.tolist()]
            dea_list = [float(x) if not pd.isna(x) else 0.0 for x in dea.tolist()]
            macd_list = [float(x) if not pd.isna(x) else 0.0 for x in macd_bar.tolist()]

        if n >= 7:
            deltas = closes_series.diff()
            for period, rsi_list in [(6, rsi6_list), (12, rsi12_list)]:
                if n >= period + 1:
                    gain = deltas.where(deltas > 0, 0)
                    loss = -deltas.where(deltas < 0, 0)
                    avg_gain = gain.rolling(window=period, min_periods=period).mean()
                    avg_loss = loss.rolling(window=period, min_periods=period).mean()
                    rs = avg_gain / avg_loss.replace(0, float("inf"))
                    rsi = (100 - (100 / (1 + rs))).fillna(0)
                    rsi_list[:] = [float(x) if not pd.isna(x) else 0.0 for x in rsi.tolist()]

        if n >= 9:
            low_nine = lows_series.rolling(window=9, min_periods=9).min()
            high_nine = highs_series.rolling(window=9, min_periods=9).max()
            rsv = (
                (closes_series - low_nine) / (high_nine - low_nine).replace(0, 1) * 100
            )
            rsv = rsv.fillna(50)

            k = [50.0] * n
            d = [50.0] * n
            for i in range(1, n):
                k[i] = (
                    2 / 3 * k[i - 1] + 1 / 3 * rsv.iloc[i]
                    if not pd.isna(rsv.iloc[i])
                    else k[i - 1]
                )
                d[i] = (
                    2 / 3 * d[i - 1] + 1 / 3 * k[i] if not pd.isna(k[i]) else d[i - 1]
                )

            k_list = [float(v) if not pd.isna(v) else 0.0 for v in k]
            d_list = [float(v) if not pd.isna(v) else 0.0 for v in d]
            j_list = [float(3 * k[i] - 2 * d[i]) for i in range(n)]

        return {
            "labels": dates,
            "dif": dif_list,
            "dea": dea_list,
            "macd": macd_list,
            "rsi6": rsi6_list,
            "rsi12": rsi12_list,
            "k": k_list,
            "d": d_list,
            "j": j_list,
        }

    def _prepare_fund_flow_data(self, fund_flow: Dict) -> Dict:
        """准备资金流向图数据"""
        if not fund_flow:
            return {"labels": [], "values": []}

        history = fund_flow.get("历史数据", [])
        if history:
            dates = [item.get("日期", "") for item in history]
            values = [item.get("主力净流入", 0) for item in history]
        else:
            dates = fund_flow.get("dates", [])
            values = fund_flow.get("values", [])

        return {
            "labels": dates,
            "values": [float(v) / 10000 if v else 0 for v in values],
        }

    def create_kline_chart_config(self, history_df: pd.DataFrame) -> str:
        """生成K线蜡烛图配置 (Chart.js + chartjs-chart-financial)"""
        data = self._prepare_kline_data(history_df)

        if not data["labels"]:
            return "{}"

        up_color = "#26A69A"
        down_color = "#EF5350"

        opens = data["opens"]
        closes = data["closes"]
        highs = data["highs"]
        lows = data["lows"]

        candle_data = []
        for i, label in enumerate(data["labels"]):
            try:
                if len(str(label)) == 8:
                    dt = pd.to_datetime(str(label), format="%Y%m%d")
                else:
                    dt = pd.to_datetime(str(label)[:10])
                candle_data.append({
                    "x": int(dt.timestamp() * 1000),
                    "o": float(opens[i]) if opens[i] else 0.0,
                    "h": float(highs[i]) if highs[i] else 0.0,
                    "l": float(lows[i]) if lows[i] else 0.0,
                    "c": float(closes[i]) if closes[i] else 0.0,
                })
            except Exception:
                continue

        ma5_data = []
        ma10_data = []
        ma20_data = []
        for i, label in enumerate(data["labels"]):
            try:
                if len(str(label)) == 8:
                    dt = pd.to_datetime(str(label), format="%Y%m%d")
                else:
                    dt = pd.to_datetime(str(label)[:10])
                ts = int(dt.timestamp() * 1000)
                if data["ma5"][i]:
                    ma5_data.append({"x": ts, "y": float(data["ma5"][i])})
                if data["ma10"][i]:
                    ma10_data.append({"x": ts, "y": float(data["ma10"][i])})
                if data["ma20"][i]:
                    ma20_data.append({"x": ts, "y": float(data["ma20"][i])})
            except Exception:
                continue

        datasets = [
            {
                "label": "K线",
                "type": "candlestick",
                "data": candle_data,
                "borderColor": {
                    "up": up_color,
                    "down": down_color,
                    "unchanged": up_color,
                },
                "backgroundColor": {
                    "up": up_color,
                    "down": down_color,
                    "unchanged": up_color,
                },
                "order": 0,
            },
            {
                "label": "MA5",
                "data": ma5_data,
                "borderColor": "#F59E0B",
                "borderWidth": 1.5,
                "pointRadius": 0,
                "fill": False,
                "tension": 0.1,
                "type": "line",
                "order": 1,
            },
            {
                "label": "MA10",
                "data": ma10_data,
                "borderColor": "#8B5CF6",
                "borderWidth": 1.5,
                "pointRadius": 0,
                "fill": False,
                "tension": 0.1,
                "type": "line",
                "order": 2,
            },
            {
                "label": "MA20",
                "data": ma20_data,
                "borderColor": "#3B82F6",
                "borderWidth": 1.5,
                "pointRadius": 0,
                "fill": False,
                "tension": 0.1,
                "type": "line",
                "order": 3,
            },
        ]

        config = {
            "type": "candlestick",
            "data": {
                "datasets": datasets,
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "top",
                        "labels": {
                            "color": "#94A3B8",
                            "padding": 15,
                            "usePointStyle": True,
                        },
                    },
                    "tooltip": {
                        "mode": "index",
                        "intersect": False,
                        "backgroundColor": "#1E293B",
                        "titleColor": "#F8FAFC",
                        "bodyColor": "#94A3B8",
                        "borderColor": "#334155",
                        "borderWidth": 1,
                    },
                },
                "scales": {
                    "x": {
                        "type": "time",
                        "time": {
                            "unit": "day",
                            "displayFormats": {"day": "MM-dd"},
                        },
                        "grid": {"color": "#334155", "drawBorder": False},
                        "ticks": {"color": "#64748B", "maxTicksLimit": 10},
                    },
                    "y": {
                        "position": "right",
                        "grid": {"color": "#334155", "drawBorder": False},
                        "ticks": {"color": "#64748B"},
                    },
                },
            },
        }
        return json.dumps(config, ensure_ascii=False)

    def create_technical_chart_config(self, history_df: pd.DataFrame) -> str:
        """生成技术指标图配置 (Chart.js)"""
        data = self._prepare_technical_data(history_df)

        if not data["labels"]:
            return "{}"

        config = {
            "type": "line",
            "data": {
                "labels": data["labels"],
                "datasets": [
                    {
                        "label": "DIF",
                        "data": data["dif"],
                        "borderColor": "#F8FAFC",
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "fill": False,
                        "tension": 0.1,
                    },
                    {
                        "label": "DEA",
                        "data": data["dea"],
                        "borderColor": "#F59E0B",
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "fill": False,
                        "tension": 0.1,
                    },
                    {
                        "label": "MACD",
                        "data": data["macd"],
                        "borderColor": "#8B5CF6",
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "fill": False,
                        "tension": 0.1,
                    },
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "top",
                        "labels": {
                            "color": "#94A3B8",
                            "padding": 15,
                            "usePointStyle": True,
                        },
                    },
                    "tooltip": {
                        "mode": "index",
                        "intersect": False,
                        "backgroundColor": "#1E293B",
                        "titleColor": "#F8FAFC",
                        "bodyColor": "#94A3B8",
                        "borderColor": "#334155",
                        "borderWidth": 1,
                    },
                },
                "scales": {
                    "x": {
                        "type": "category",
                        "grid": {"color": "#334155", "drawBorder": False},
                        "ticks": {"color": "#64748B", "maxTicksLimit": 10},
                    },
                    "y": {
                        "position": "right",
                        "grid": {"color": "#334155", "drawBorder": False},
                        "ticks": {"color": "#64748B"},
                    },
                },
            },
        }
        return json.dumps(config, ensure_ascii=False)

    def create_fund_flow_chart_config(self, fund_flow: Dict) -> str:
        """生成资金流向图配置 (Chart.js)"""
        data = self._prepare_fund_flow_data(fund_flow)
        up_color = "#26A69A"
        down_color = "#EF5350"
        colors = [up_color if v >= 0 else down_color for v in data["values"]]
        config = {
            "type": "bar",
            "data": {
                "labels": data["labels"],
                "datasets": [
                    {
                        "label": "主力净流入(万元)",
                        "data": data["values"],
                        "backgroundColor": colors,
                        "borderColor": colors,
                        "borderWidth": 1,
                        "borderRadius": 4,
                    },
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "top",
                        "labels": {
                            "color": "#94A3B8",
                            "padding": 15,
                            "usePointStyle": True,
                        },
                    },
                    "tooltip": {
                        "mode": "index",
                        "intersect": False,
                        "backgroundColor": "#1E293B",
                        "titleColor": "#F8FAFC",
                        "bodyColor": "#94A3B8",
                        "borderColor": "#334155",
                        "borderWidth": 1,
                    },
                },
                "scales": {
                    "x": {
                        "type": "category",
                        "grid": {"color": "#334155", "drawBorder": False},
                        "ticks": {"color": "#64748B"},
                    },
                    "y": {
                        "position": "right",
                        "grid": {"color": "#334155", "drawBorder": False},
                        "ticks": {"color": "#64748B"},
                    },
                },
            },
        }
        return json.dumps(config, ensure_ascii=False)

    def generate_html_report(self, data: Dict, analysis: Dict) -> str:
        """生成 HTML 报告"""
        info = data.get("stock_info", {})
        fund_flow = data.get("fund_flow", {})
        indicators = analysis.get("indicators", {})

        price_change = info.get("涨跌幅", 0)
        try:
            price_change = float(str(price_change).replace("%", ""))
        except:
            price_change = 0

        current_price = info.get("最新价", 0)
        try:
            current_price = float(current_price)
        except:
            current_price = 0

        signal = analysis.get("trading_signal", {})
        signal_name = signal.get("signal", "hold")
        signal_text = signal.get("signal_text", "持有")

        price_pred = analysis.get("price_prediction", {})

        macd = indicators.get("MACD", {})
        rsi = indicators.get("RSI", {})
        kdj = indicators.get("KDJ", {})
        boll = indicators.get("BOLL", {})

        context = {
            "stock_name": data.get("stock_name", "N/A"),
            "stock_code": data.get("stock_code", "N/A"),
            "current_price": current_price,
            "price_change": price_change,
            "score": signal.get("score", 0),
            "score_percent": signal.get("score", 0) * 100,
            "signal": signal_name,
            "signal_text": signal_text,
            "industry": info.get("所属行业", info.get("所处行业", "N/A")),
            "total_market_value": self._format_market_value(info.get("总市值")),
            "circulating_market_value": self._format_market_value(info.get("流通市值")),
            "pe": info.get("市盈率-动态", info.get("市盈率(动)", "N/A")),
            "pb": info.get("市净率", "N/A"),
            "macd_signal": macd.get("signal", "N/A"),
            "macd_dif": macd.get("DIF", "N/A"),
            "macd_dea": macd.get("DEA", "N/A"),
            "rsi_6_value": rsi.get("RSI(6)", {}).get("value", "N/A"),
            "rsi_6_status": rsi.get("RSI(6)", {}).get("status", "N/A"),
            "rsi_12_value": rsi.get("RSI(12)", {}).get("value", "N/A"),
            "rsi_12_status": rsi.get("RSI(12)", {}).get("status", "N/A"),
            "kdj_k": kdj.get("K", "N/A"),
            "kdj_d": kdj.get("D", "N/A"),
            "kdj_j": kdj.get("J", "N/A"),
            "kdj_signal": kdj.get("signal", "N/A"),
            "boll_upper": boll.get("upper", "N/A"),
            "boll_middle": boll.get("middle", "N/A"),
            "boll_lower": boll.get("lower", "N/A"),
            "main_inflow": f"{fund_flow.get('主力净流入', 0) / 10000:.2f}万",
            "main_inflow_ratio": f"{fund_flow.get('主力净流入占比', 'N/A')}",
            "fund_flow_trend": self._format_trend(
                analysis.get("analysis", {}).get("fund_flow", {}).get("trend", "N/A")
            ),
            "support": price_pred.get("support", "N/A"),
            "resistance": price_pred.get("resistance", "N/A"),
            "target_low": price_pred.get("target_low", "N/A"),
            "target_high": price_pred.get("target_high", "N/A"),
            "day1_target_low": price_pred.get("day1", {}).get("target_low", "N/A"),
            "day1_target_high": price_pred.get("day1", {}).get("target_high", "N/A"),
            "day1_trend": price_pred.get("day1", {}).get("trend", "N/A"),
            "day2_target_low": price_pred.get("day2", {}).get("target_low", "N/A"),
            "day2_target_high": price_pred.get("day2", {}).get("target_high", "N/A"),
            "day2_trend": price_pred.get("day2", {}).get("trend", "N/A"),
            "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "include_charts": self.include_charts,
            "chart_height": self.chart_height,
            "kline_chart_config": "{}",
            "technical_chart_config": "{}",
            "fund_flow_chart_config": "{}",
        }

        if self.include_charts:
            history_df = data.get("history_data")
            if history_df is not None and not history_df.empty:
                context["kline_chart_config"] = self.create_kline_chart_config(
                    history_df
                )
                context["technical_chart_config"] = self.create_technical_chart_config(
                    history_df
                )

                if fund_flow:
                    context["fund_flow_chart_config"] = (
                        self.create_fund_flow_chart_config(fund_flow)
                    )

        return self.template.render(**context)

    def save_report(
        self, html_content: str, stock_code: str, output_dir: Optional[str] = None
    ) -> str:
        """保存报告到文件"""
        if output_dir is None:
            output_dir = os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "output",
                "reports",
            )

        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{stock_code}_{timestamp}.html"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)

        return filepath
