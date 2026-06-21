import sys
import os
import re
import logging
import math
import threading
import time
from collections import OrderedDict
from datetime import datetime
from typing import Dict, Optional

import numpy as np
import pandas as pd
from psycopg2 import sql

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.core.data_fetcher import DataFetcher
from scripts.core.analyzer import StockAnalyzer
from scripts.technical_indicators import calculate_all_indicators

from backend.utils import clean_float, to_list, deep_clean_nan, clean_nested, sanitize_for_json
from backend.logging import log_data
from backend.logging.trace import set_stock_code

_svc_logger = logging.getLogger("stock_query.analysis_service")


class AnalysisLogger:
    def __init__(self, stock_code: str = ""):
        self.entries = []
        self.callback = None
        self.stock_code = stock_code

    def set_callback(self, callback):
        self.callback = callback

    def log(self, level: str, message: str):
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "message": message,
            "stock_code": self.stock_code,
        }
        self.entries.append(entry)

        # 同时写入文件日志，并带上结构化 stock_code 字段，便于检索与关联
        level_value = getattr(logging, level.upper(), logging.INFO)
        extra = {"stock_code": self.stock_code} if self.stock_code else {}
        _svc_logger.log(level_value, message, extra=extra)

        if self.callback:
            try:
                self.callback(entry)
            except Exception:
                _svc_logger.warning("分析日志回调异常", exc_info=True)

    def info(self, message: str):
        self.log("INFO", message)

    def warn(self, message: str):
        self.log("WARN", message)

    def error(self, message: str):
        self.log("ERROR", message)

    def get_entries(self):
        return self.entries.copy()

    def clear(self):
        self.entries = []


_fetcher_cache = None
_analyzer_cache = None
_RESULT_CACHE_MAX_SIZE = 100
_result_cache = OrderedDict()
_cache_lock = threading.Lock()


def _validate_stock_code(stock_code: str):
    if not re.match(r'^\d{6}$', stock_code):
        raise ValueError(f"无效的股票代码格式: {stock_code}，必须为6位数字")


def _load_config():
    """延迟加载配置，避免模块顶层导入触发路径问题。"""
    from scripts.core.config_loader import load_config
    return load_config()


def get_fetcher():
    global _fetcher_cache
    if _fetcher_cache is None:
        _fetcher_cache = DataFetcher(_load_config())
    return _fetcher_cache


def get_analyzer():
    global _analyzer_cache
    if _analyzer_cache is None:
        _analyzer_cache = StockAnalyzer(_load_config())
    return _analyzer_cache


def build_chart_data(history_df, indicators: Dict, fund_flow: Dict = None) -> Dict:
    if history_df is None or history_df.empty:
        return {
            "kline": {"dates": [], "opens": [], "closes": [], "highs": [], "lows": [], "volumes": [],
                      "ma5": [], "ma10": [], "ma20": [], "ma60": [], "boll_upper": [], "boll_middle": [], "boll_lower": []},
            "technical": {"dates": [], "macd": [], "dif": [], "dea": [], "rsi6": [], "rsi12": [], "k": [], "d": [], "j": []},
            "fund_flow": {"dates": [], "main_flow": [], "main_flow_ratio": [], "small_flow": [], "change_pct": []},
        }

    df = history_df.copy()

    if "日期" in df.columns:
        dates = [str(d)[:10] for d in df["日期"]]
    else:
        dates = [str(d)[:10] for d in df.index]

    opens = to_list(df.get("开盘", []))
    closes = to_list(df.get("收盘", []))
    highs = to_list(df.get("最高", []))
    lows = to_list(df.get("最低", []))
    volumes = to_list(df.get("成交量", []))

    ma_data = indicators.get("MA", {})
    ma5 = to_list(ma_data.get("MA5", {}).get("series", [])) if isinstance(ma_data.get("MA5"), dict) else []
    ma10 = to_list(ma_data.get("MA10", {}).get("series", [])) if isinstance(ma_data.get("MA10"), dict) else []
    ma20 = to_list(ma_data.get("MA20", {}).get("series", [])) if isinstance(ma_data.get("MA20"), dict) else []
    ma60 = to_list(ma_data.get("MA60", {}).get("series", [])) if isinstance(ma_data.get("MA60"), dict) else []

    if not ma5 and "收盘" in df.columns:
        ma5 = to_list(df["收盘"].rolling(window=5).mean().fillna(0))
    if not ma10 and "收盘" in df.columns:
        ma10 = to_list(df["收盘"].rolling(window=10).mean().fillna(0))
    if not ma20 and "收盘" in df.columns:
        ma20 = to_list(df["收盘"].rolling(window=20).mean().fillna(0))
    if not ma60 and "收盘" in df.columns:
        ma60 = to_list(df["收盘"].rolling(window=60).mean().fillna(0))

    boll_data = indicators.get("BOLL", {}).get("series", {})
    boll_upper = to_list(boll_data.get("upper", [])) if isinstance(boll_data, dict) else []
    boll_middle = to_list(boll_data.get("middle", [])) if isinstance(boll_data, dict) else []
    boll_lower = to_list(boll_data.get("lower", [])) if isinstance(boll_data, dict) else []

    if not boll_upper and "收盘" in df.columns and len(df) >= 20:
        middle = df["收盘"].rolling(window=20).mean()
        std = df["收盘"].rolling(window=20).std(ddof=1)
        boll_upper = to_list((middle + 2 * std).fillna(0))
        boll_middle = to_list(middle.fillna(0))
        boll_lower = to_list((middle - 2 * std).fillna(0))

    macd_series = indicators.get("MACD", {}).get("series", {})
    rsi_series = indicators.get("RSI", {})
    kdj_series = indicators.get("KDJ", {}).get("series", {})

    macd_vals = to_list(macd_series.get("MACD", []))
    dif_vals = to_list(macd_series.get("DIF", []))
    dea_vals = to_list(macd_series.get("DEA", []))
    rsi6_val = rsi_series.get("RSI(6)", {})
    rsi6_vals = to_list(rsi6_val.get("series", [])) if isinstance(rsi6_val, dict) else []
    rsi12_val = rsi_series.get("RSI(12)", {})
    rsi12_vals = to_list(rsi12_val.get("series", [])) if isinstance(rsi12_val, dict) else []
    k_vals = to_list(kdj_series.get("K", []))
    d_vals = to_list(kdj_series.get("D", []))
    j_vals = to_list(kdj_series.get("J", []))

    ff_dates = []
    ff_main_flow = []
    ff_main_flow_ratio = []
    ff_small_flow = []
    ff_change_pct = []
    if fund_flow and isinstance(fund_flow, dict):
        hist = fund_flow.get("历史数据", [])
        if isinstance(hist, list):
            for item in hist:
                ff_dates.append(str(item.get("日期", ""))[:10])
                ff_main_flow.append(clean_float(item.get("主力净流入")))
                ff_main_flow_ratio.append(clean_float(item.get("主力净流入占比")))
                ff_small_flow.append(clean_float(item.get("小单净流入", 0)))
                ff_change_pct.append(clean_float(item.get("涨跌幅", 0)))

    return {
        "kline": {
            "dates": dates, "opens": opens, "closes": closes, "highs": highs, "lows": lows, "volumes": volumes,
            "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
            "boll_upper": boll_upper, "boll_middle": boll_middle, "boll_lower": boll_lower,
        },
        "technical": {
            "dates": dates, "macd": macd_vals, "dif": dif_vals, "dea": dea_vals,
            "rsi6": rsi6_vals, "rsi12": rsi12_vals, "k": k_vals, "d": d_vals, "j": j_vals,
        },
        "fund_flow": {"dates": ff_dates, "main_flow": ff_main_flow, "main_flow_ratio": ff_main_flow_ratio, "small_flow": ff_small_flow, "change_pct": ff_change_pct},
    }


def _prepare_analysis_inputs(stock_input, position_type, cost_price, logger, stage_callback=None, shared_market_data=None, shared_sector_quotes=None):
    """参数校验、默认值填充、返回规整后的参数字典"""
    if not stock_input:
        raise ValueError("股票代码不能为空")

    position_type = position_type or "观望"
    cost_price = cost_price if cost_price is not None else 0.0

    fetcher = get_fetcher()
    try:
        stock_code, stock_name, market, market_tag = fetcher.resolve_stock_code(stock_input)
        logger.info(f"股票代码解析: {stock_code} ({stock_name})" + (f" [{market_tag}]" if market_tag else ""))
    except Exception as e:
        logger.warn(f"股票代码解析失败，使用原始输入: {e}")
        stock_code = stock_input
        stock_name = stock_input
        market = None
        market_tag = ""

    # 让 logger 与当前线程上下文都绑定到实际股票代码，保证后续日志可检索
    if hasattr(logger, "stock_code"):
        logger.stock_code = stock_code

    return {
        "stock_input": stock_input,
        "stock_code": stock_code,
        "stock_name": stock_name,
        "market": market,
        "market_tag": market_tag,
        "position_type": position_type,
        "cost_price": cost_price,
        "stage_callback": stage_callback,
        "shared_market_data": shared_market_data,
        "shared_sector_quotes": shared_sector_quotes,
    }


def _fetch_analysis_data(stock_code, stock_name, market, market_tag, fetcher, logger, shared_market_data=None, shared_sector_quotes=None):
    """调用 data_fetcher / indicator_service 获取行情和指标数据"""
    info = None
    fund_flow = None
    history_df = None
    indicators = None
    data_source = None
    db_data = None
    fetch_start = time.time()

    try:
        from scripts.database import get_or_fetch_stock_data
        db_data = get_or_fetch_stock_data(stock_code, force_refresh=False, days=120)
        if db_data:
            data_source = db_data.get("source", "unknown")
            logger.info(f"数据来源: {data_source}")
            if db_data.get("history_df") is not None and not db_data["history_df"].empty:
                history_df = db_data["history_df"]
            if db_data.get("stock_info") and len(db_data["stock_info"]) > 0:
                info = db_data["stock_info"]
                logger.info(f"stock_info从DB获取({len(info)}字段)")
            if db_data.get("fund_flow") and len(db_data["fund_flow"]) > 0:
                fund_flow = db_data["fund_flow"]
                logger.info(f"fund_flow从DB获取({len(fund_flow)}字段)")
            if db_data.get("indicators"):
                indicators = db_data["indicators"]
    except Exception as e:
        logger.warn(f"数据库获取数据异常: {e}")

    # 仅在DB回退模式下跳过API重试（避免API超时导致二次阻塞）
    is_fallback = data_source == "database_fallback"

    if info is None and not is_fallback:
        try:
            info = fetcher.fetch_stock_info(stock_code)
            logger.info("stock_info通过API补充获取")
        except Exception:
            logger.warn("stock_info获取失败")
    else:
        if info is not None:
            logger.info(f"stock_info来源: DB缓存({len(info)}字段)")
        else:
            logger.info("stock_info: 无数据(API补充已跳过)")
    if fund_flow is None and not is_fallback:
        try:
            fund_flow = fetcher.fetch_fund_flow(stock_code)
            logger.info("fund_flow通过API补充获取")
        except Exception:
            logger.warn("fund_flow获取失败")
    else:
        if fund_flow is not None:
            logger.info(f"fund_flow来源: DB缓存({len(fund_flow)}字段)")
        else:
            logger.info("fund_flow: 无数据(API补充已跳过)")
    if history_df is None:
        try:
            history_df = fetcher.fetch_history_data(stock_code, days=120)
        except Exception:
            logger.warn("历史数据获取失败")

    # 获取周线/月线数据用于多时间框架分析
    # bars 表示请求的 K 线条数：周线约两年(104条)，月线约五年(60条)
    weekly_df = None
    monthly_df = None
    try:
        weekly_df = fetcher.fetch_history_data(stock_code, bars=104, klt=101)
    except Exception as e:
        logger.warn(f"周线数据获取失败: {e}")
    try:
        monthly_df = fetcher.fetch_history_data(stock_code, bars=60, klt=102)
    except Exception as e:
        logger.warn(f"月线数据获取失败: {e}")

    info = info or {}
    fund_flow = fund_flow or {}

    fetch_elapsed = time.time() - fetch_start
    if not info or not fund_flow:
        logger.warn("部分数据获取失败")
    else:
        logger.info(f"数据获取完成 (耗时: {fetch_elapsed:.1f}s)")

    if history_df is None or history_df.empty:
        return None

    # 清理 stock_info 中名称的市场标识前缀
    # efinance在除权除息日会在名称前加XD/XR/DR且可能截断原名称字符
    # 因此优先使用resolve_stock_code已清理的名称
    raw_info_name = info.get("名称", stock_code) if info else stock_code
    if not market_tag:
        for prefix in ("XD", "XR", "DR", "N"):
            if raw_info_name.startswith(prefix) and len(raw_info_name) > len(prefix):
                market_tag = prefix
                break

    all_data = {
        "stock_code": stock_code,
        "stock_name": stock_name or stock_code,
        "market_tag": market_tag,
        "market": market,
        "stock_info": info,
        "fund_flow": fund_flow,
        "history_data": history_df,
        "data_quality": db_data.get("data_quality", "normal") if db_data else "normal",
    }

    # 获取大盘数据，避免后续 analyze_market_sentiment 重复调用 efinance
    # 优先使用批量分析共享的大盘数据，避免并发时重复调用 baostock
    market_data = shared_market_data
    if market_data is not None:
        logger.info(f"使用共享大盘数据: change={market_data.get('涨跌幅', 'N/A')}")
    else:
        try:
            market_data = fetcher.fetch_market_data()
            if market_data:
                logger.info(f"独立获取大盘数据成功: change={market_data.get('涨跌幅', 'N/A')}")
            else:
                logger.warning("独立获取大盘数据返回空")
        except Exception as e:
            logger.warning(f"获取大盘数据失败: {e}")
    # 即使获取失败也传入空 dict，避免 analyze_market_sentiment 再次调用 efinance
    if not market_data:
        market_data = {}
    all_data["market_data"] = market_data

    # 获取板块动量数据（行业涨幅、排名等，用于板块轮动修正）
    sector_momentum = None
    try:
        sector_momentum = fetcher.fetch_sector_momentum(stock_code, shared_sector_quotes=shared_sector_quotes)
        if sector_momentum:
            logger.info(f"板块动量数据: {sector_momentum['best_sector_name']}({sector_momentum['best_sector_change']:.2f}%), 排名={sector_momentum['sector_rank']}/{sector_momentum['total_sectors']}")
        else:
            logger.info("板块动量数据获取失败，将跳过板块修正")
    except Exception as e:
        logger.warning(f"获取板块动量数据失败: {e}")
    all_data["sector_momentum"] = sector_momentum

    log_data('transfer', 'data_fetcher', 'analyzer', 'success',
             stock_code=stock_code,
             has_history=all_data.get('history_data') is not None,
             has_stock_info=all_data.get('stock_info') is not None,
             has_market_data='market_data' in all_data)

    if not indicators:
        indicators = calculate_all_indicators(history_df)
    logger.info(f"指标计算完成: {len(indicators)}组指标")

    all_data["indicators"] = indicators
    all_data["weekly_df"] = weekly_df
    all_data["monthly_df"] = monthly_df

    return all_data


def _detect_hmm_state(analyzer, history_df, indicators, logger):
    """检测 HMM 或市场状态"""
    hmm_state = None
    if hasattr(analyzer, '_hmm_detector') and analyzer._hmm_detector is not None and analyzer._hmm_detector.is_ready():
        if history_df is not None and not history_df.empty and "收盘" in history_df.columns:
            try:
                closes = history_df["收盘"].values.astype(np.float64)
                returns = np.diff(closes) / closes[:-1]
                vols = np.zeros_like(returns)
                window = 20
                for i_hmm in range(len(returns)):
                    start = max(0, i_hmm - window + 1)
                    vols[i_hmm] = np.std(returns[start:i_hmm + 1]) if i_hmm > 0 else 0.0
                volumes = history_df["成交量"].values.astype(np.float64) if "成交量" in history_df.columns else np.ones(len(closes))
                volume_changes = np.diff(volumes) / (volumes[:-1] + 1e-10)
                hmm_result = analyzer._hmm_detector.predict(returns, vols, volume_changes)
                hmm_state = {
                    "current_state": hmm_result.get("current_state", "未知"),
                    "state_probabilities": hmm_result.get("state_probabilities", {}),
                    "transition_matrix": hmm_result.get("transition_matrix"),
                }
            except Exception:
                logger.warning("HMM预测异常", exc_info=True)
    elif hasattr(analyzer, '_regime_detector') and analyzer._regime_detector is not None:
        if history_df is not None and not history_df.empty and "收盘" in history_df.columns:
            try:
                latest_close = float(history_df["收盘"].iloc[-1])
                prev_close = float(history_df["收盘"].iloc[-2]) if len(history_df) > 1 else latest_close
                change_pct = (latest_close - prev_close) / prev_close * 100 if prev_close != 0 else 0
                vol_col = "成交量" if "成交量" in history_df.columns else None
                volume_ratio = 1.0
                if vol_col and len(history_df) > 1:
                    latest_vol = float(history_df[vol_col].iloc[-1])
                    prev_vol = float(history_df[vol_col].iloc[-2])
                    volume_ratio = latest_vol / prev_vol if prev_vol != 0 else 1.0
                boll = indicators.get("BOLL", {})
                bandwidth = boll.get("latest", {}).get("bandwidth") if isinstance(boll.get("latest"), dict) else None
                volatility_signal = "正常"
                if bandwidth is not None:
                    if bandwidth < 10:
                        volatility_signal = "低波动"
                    elif bandwidth > 25:
                        volatility_signal = "高波动"
                market_data_hmm = {
                    "volatility_signal": volatility_signal,
                    "volume_ratio": volume_ratio,
                    "market_change_pct": change_pct,
                }
                regime = analyzer._regime_detector.detect_regime(market_data_hmm)
                hmm_state = {
                    "current_state": regime,
                    "state_probabilities": {},
                    "transition_matrix": None,
                }
            except Exception:
                logger.warning("市场状态检测异常", exc_info=True)
    return hmm_state


def _execute_analysis(analyzer, stock_code, all_data, history_df, indicators, position_type, cost_price, logger, stage_callback=None):
    """调用 StockAnalyzer 的 analyze_technical 等方法执行分析"""
    if stage_callback:
        stage_callback('stage_technical', {
            'indicators': indicators,
            'technical_chart_data': build_chart_data(history_df, indicators, all_data.get('fund_flow')) if indicators else None,
        })

    current_price = 0
    try:
        current_price = float(all_data.get('stock_info', {}).get('最新价', 0)) if all_data.get('stock_info', {}).get('最新价') else 0
    except (TypeError, ValueError):
        current_price = 0

    technical_analysis = analyzer.analyze_technical(indicators, current_price) if indicators else {"score": 0.5}
    tech_score = technical_analysis.get('score', 0.5) if technical_analysis else 0.5
    logger.info(f"技术分析完成: 评分={tech_score:.2f}")

    # 计算周线/月线技术指标和评分
    weekly_df = all_data.get('weekly_df')
    monthly_df = all_data.get('monthly_df')
    weekly_indicators = None
    weekly_tech = None
    monthly_indicators = None
    monthly_tech = None

    if weekly_df is not None and not weekly_df.empty and len(weekly_df) >= 10:
        try:
            weekly_indicators = calculate_all_indicators(weekly_df)
            weekly_current_price = float(weekly_df["收盘"].iloc[-1])
            weekly_tech = analyzer.analyze_technical(weekly_indicators, weekly_current_price)
        except Exception as e:
            logger.warn(f"周线技术分析失败: {e}")

    if monthly_df is not None and not monthly_df.empty and len(monthly_df) >= 5:
        try:
            monthly_indicators = calculate_all_indicators(monthly_df)
            monthly_current_price = float(monthly_df["收盘"].iloc[-1])
            monthly_tech = analyzer.analyze_technical(monthly_indicators, monthly_current_price)
        except Exception as e:
            logger.warn(f"月线技术分析失败: {e}")

    fund_flow_analysis = analyzer.analyze_fund_flow(all_data.get('fund_flow'), all_data.get('stock_info'), history_df=history_df)
    fund_score = fund_flow_analysis.get('score', 0.5) if fund_flow_analysis else 0.5
    logger.info(f"资金流向分析完成: 评分={fund_score:.2f}")

    market_data = all_data.get('market_data')
    sentiment_analysis = analyzer.analyze_market_sentiment(all_data, market_data)
    sentiment_score = sentiment_analysis.get('score', 0.5) if sentiment_analysis else 0.5
    logger.info(f"市场情绪分析完成: 评分={sentiment_score:.2f}")

    analysis = {
        "technical": technical_analysis,
        "fund_flow": fund_flow_analysis,
        "sentiment": sentiment_analysis,
    }

    all_data["technical_analysis"] = technical_analysis

    trading_signal = analyzer.generate_trading_signal(analysis, position_type, market_data)
    logger.info(f"交易信号: {trading_signal.get('signal', 'N/A')}")

    price_prediction = analyzer.predict_price_range(all_data, indicators, stock_code, trading_signal)

    # 多时间框架趋势一致性检测
    multi_timeframe = None
    if weekly_tech or monthly_tech:
        multi_timeframe = analyzer.analyze_multi_timeframe(
            technical_analysis, weekly_tech, monthly_tech
        )
        logger.info(f"多时间框架: {multi_timeframe.get('description', 'N/A')}")

    validation = analyzer.cross_validate_analysis(
        analysis, price_prediction, indicators,
        trading_signal, position_type, current_price,
        history_df=history_df,
        multi_timeframe=multi_timeframe,
        sector_momentum=all_data.get("sector_momentum")
    )

    trading_signal["reason"] = validation.get("validation_note", "")
    price_prediction["validation_confidence"] = validation.get("confidence", 0.5)
    price_prediction["validation_note"] = validation.get("validation_note", "")

    stress_test_info = validation.get("stress_test", {})
    if stress_test_info.get("status") == "computing":
        logger.info("压力测试异步执行中，主请求立即返回")

    if validation.get("conflicts"):
        logger.warn("交叉验证发现冲突")
    else:
        logger.info("交叉验证完成")

    if stage_callback:
        stage_callback('stage_risk', {
            'tech_score': technical_analysis.get('score', 0.5),
            'fund_score': fund_flow_analysis.get('score', 0.5),
            'sentiment_score': sentiment_analysis.get('score', 0.5),
            'signal': trading_signal,
            'validation': validation,
        })

    if position_type == "已持有":
        strategy = analyzer.generate_position_strategy(
            all_data, indicators, current_price, cost_price, trading_signal, validation
        )
    else:
        strategy = analyzer.generate_buy_strategy(
            all_data, indicators, current_price, trading_signal, validation
        )

    logger.info("价格预测完成")
    logger.info("策略生成完成")

    if stage_callback:
        stage_callback('stage_prediction', {
            'price_prediction': price_prediction,
            'position_strategy': strategy,
        })

    hmm_state = _detect_hmm_state(analyzer, history_df, indicators, logger)

    action_gate = validation.get('action_gate', '')
    action_gate_text_map = {
        "allow_buy": "建议买入",
        "cautious_buy": "可考虑买入",
        "avoid_buy": "回避",
        "watch": "观望",
        "reduce_position": "减仓",
        "cautious_hold": "谨慎持有",
        "hold_position": "持有",
    }
    action_gate_text = action_gate_text_map.get(action_gate, trading_signal.get('signal_text', '观望'))

    return {
        "technical_analysis": technical_analysis,
        "fund_flow_analysis": fund_flow_analysis,
        "sentiment_analysis": sentiment_analysis,
        "tech_score": tech_score,
        "fund_score": fund_score,
        "sentiment_score": sentiment_score,
        "trading_signal": trading_signal,
        "price_prediction": price_prediction,
        "multi_timeframe": multi_timeframe,
        "validation": validation,
        "strategy": strategy,
        "hmm_state": hmm_state,
        "action_gate": action_gate,
        "action_gate_text": action_gate_text,
    }


def _persist_analysis_result(stock_code, all_data, analysis_outputs, logger):
    """结果持久化准备、缓存写入前处理、日志记录"""
    info = all_data.get("stock_info") or {}
    market_data = all_data.get("market_data") or {}
    history_df = all_data.get("history_data")
    indicators = all_data.get("indicators")
    fund_flow = all_data.get("fund_flow") or {}

    technical_analysis = analysis_outputs["technical_analysis"]
    fund_flow_analysis = analysis_outputs["fund_flow_analysis"]
    sentiment_analysis = analysis_outputs["sentiment_analysis"]
    trading_signal = analysis_outputs["trading_signal"]
    price_prediction = analysis_outputs["price_prediction"]
    validation = analysis_outputs["validation"]
    strategy = analysis_outputs["strategy"]
    hmm_state = analysis_outputs["hmm_state"]
    action_gate = analysis_outputs["action_gate"]
    action_gate_text = analysis_outputs["action_gate_text"]

    charts = build_chart_data(history_df, indicators, fund_flow)

    result = {
        "stock_code": stock_code,
        "stock_name": all_data.get("stock_name") or stock_code,
        "market_tag": all_data.get("market_tag") or "",
        "analysis": {
            "technical_score": clean_float(analysis_outputs["tech_score"]),
            "fund_flow_score": clean_float(analysis_outputs["fund_score"]),
            "sentiment_score": clean_float(analysis_outputs["sentiment_score"]),
            "overall_score": clean_float(trading_signal.get('score', 0)),
            "recommendation": action_gate_text,
            "details": clean_nested({
                "technical": technical_analysis,
                "fund_flow": fund_flow_analysis,
                "sentiment": sentiment_analysis,
            }),
        },
        "trading_signal": {
            "score": clean_float(trading_signal.get('score', 0)),
            "signal": trading_signal.get('signal', 'hold'),
            "signal_text": action_gate_text,
            "action_gate": action_gate,
            "reason": trading_signal.get('reason', ''),
            "raw_signal": trading_signal.get('signal', 'hold'),
            "raw_signal_text": trading_signal.get('signal_text', ''),
        },
        "price_prediction": {
            "current": clean_float(price_prediction.get('current')),
            "support": clean_float(price_prediction.get('support')),
            "resistance": clean_float(price_prediction.get('resistance')),
            "validation_confidence": clean_float(price_prediction.get('validation_confidence')),
            "validation_note": price_prediction.get('validation_note', ''),
            "hybrid_alpha": clean_float(price_prediction.get('hybrid_alpha')),
            "ml_prediction": price_prediction.get('ml_prediction'),
            "day1": {
                "target_low": clean_float(price_prediction.get('day1', {}).get('target_low')),
                "target_high": clean_float(price_prediction.get('day1', {}).get('target_high')),
                "trend": price_prediction.get('day1', {}).get('trend', 'neutral'),
                "signal": price_prediction.get('day1', {}).get('signal', ''),
            },
            "day2": {
                "target_low": clean_float(price_prediction.get('day2', {}).get('target_low')),
                "target_high": clean_float(price_prediction.get('day2', {}).get('target_high')),
                "trend": price_prediction.get('day2', {}).get('trend', 'neutral'),
                "signal": price_prediction.get('day2', {}).get('signal', ''),
            },
        },
        "indicators": _clean_indicators(indicators),
        "position_strategy": clean_nested(strategy),
        "validation": clean_nested(validation),
        "stock_info": {k: clean_float(v) for k, v in info.items()},
        "market_data": market_data,
        "sector_momentum": all_data.get("sector_momentum"),
        "charts": charts,
    }

    if hmm_state:
        result["hmm_state"] = clean_nested(hmm_state)

    result = deep_clean_nan(result)
    logger.info("分析结果构建完成")
    return result


def _run_analysis_core(stock_input, position_type, cost_price, logger, stage_callback=None, shared_market_data=None, shared_sector_quotes=None):
    fetcher = get_fetcher()
    analyzer = get_analyzer()

    inputs = _prepare_analysis_inputs(
        stock_input, position_type, cost_price, logger,
        stage_callback=stage_callback,
        shared_market_data=shared_market_data,
        shared_sector_quotes=shared_sector_quotes,
    )
    stock_code = inputs["stock_code"]
    stock_name = inputs["stock_name"]

    # 绑定当前线程/协程的 stock_code，使未使用 AnalysisLogger 的标准日志也能关联到股票
    set_stock_code(stock_code)
    market = inputs["market"]
    market_tag = inputs["market_tag"]
    position_type = inputs["position_type"]
    cost_price = inputs["cost_price"]
    stage_callback = inputs["stage_callback"]

    all_data = _fetch_analysis_data(
        stock_code, stock_name, market, market_tag,
        fetcher, logger,
        shared_market_data=inputs["shared_market_data"],
        shared_sector_quotes=inputs["shared_sector_quotes"],
    )
    if all_data is None:
        return None

    if stage_callback:
        stage_callback('stage_basic', {
            'stock_info': all_data.get('stock_info', {}),
            'stock_name': all_data.get('stock_name'),
            'fund_flow': all_data.get('fund_flow', {}),
        })

    analysis_outputs = _execute_analysis(
        analyzer, stock_code, all_data,
        all_data.get('history_data'), all_data.get('indicators'),
        position_type, cost_price, logger,
        stage_callback=stage_callback,
    )

    result = _persist_analysis_result(stock_code, all_data, analysis_outputs, logger)
    return result


def run_analysis(stock_input: str, position_status: str, cost_price: Optional[float] = None, skip_signal_cache: bool = False, shared_market_data: dict = None, shared_sector_quotes=None) -> Dict:
    cache_key = (stock_input, position_status, cost_price)
    now = datetime.now()
    with _cache_lock:
        if cache_key in _result_cache:
            cached_result, cached_time = _result_cache[cache_key]
            _result_cache.move_to_end(cache_key)
            if (now - cached_time).total_seconds() < 600:
                if not skip_signal_cache:
                    try:
                        from backend.services.history_service import update_signal_cache
                        stock_code = cached_result.get("stock_code", stock_input)
                        update_signal_cache(stock_code, position_status, cached_result.get("trading_signal", {}), cost_price=cost_price)
                    except Exception as e:
                        cached_code = cached_result.get("stock_code", stock_input)
                        _svc_logger.warning(f"更新信号缓存失败: {e}", extra={"stock_code": cached_code} if cached_code else {})
                return cached_result

    logger = AnalysisLogger(stock_code=stock_input)
    start_time = time.time()
    logger.info(f"开始分析: {stock_input}")

    result = _run_analysis_core(stock_input, position_status, cost_price, logger, shared_market_data=shared_market_data, shared_sector_quotes=shared_sector_quotes)

    if result is None:
        raise ValueError(f"无法完成 {stock_input} 的分析")

    total_elapsed = time.time() - start_time
    logger.info(f"分析完成 (总耗时: {total_elapsed:.1f}s)")
    result["analysis_log"] = logger.entries

    with _cache_lock:
        _set_cache_item(cache_key, (result, now))
        # 双写：用解析后的 stock_code 也缓存一份，确保通过代码查询时也能命中
        resolved_code = result.get("stock_code", stock_input)
        if resolved_code and resolved_code != stock_input:
            cache_key_resolved = (resolved_code, position_status, cost_price)
            _set_cache_item(cache_key_resolved, (result, now))
        _cleanup_cache()

    resolved_code = result.get("stock_code", stock_input)
    extra = {"stock_code": resolved_code} if resolved_code else {}

    if not skip_signal_cache:
        try:
            from backend.services.history_service import update_signal_cache
            update_signal_cache(resolved_code, position_status, result.get("trading_signal", {}), cost_price=cost_price)
        except Exception as e:
            _svc_logger.warning(f"更新信号缓存失败: {e}", extra=extra)

    try:
        pred = result.get("price_prediction", {})
        _svc_logger.info(f"写入预测值到DB: {resolved_code}, day1={pred.get('day1', {})}, day2={pred.get('day2', {})}", extra=extra)
        _update_prediction_to_db(resolved_code, pred)
    except Exception as e:
        _svc_logger.warning(f"更新预测值到数据库失败: {e}", extra=extra)

    return result


def _update_prediction_to_db(stock_code: str, price_prediction: Dict):
    _validate_stock_code(stock_code)
    logger = _svc_logger
    extra = {"stock_code": stock_code}

    if not price_prediction:
        logger.debug(f"[{stock_code}] 无预测数据，跳过写入", extra=extra)
        return

    day1 = price_prediction.get("day1", {})
    day2 = price_prediction.get("day2", {})
    # 确保转换为原生 Python float，避免 np.float64 被 psycopg2 序列化为 "np.float64(xxx)"
    def _to_native_float(v):
        if v is None:
            return None
        try:
            f = float(v)
            if math.isnan(f) or math.isinf(f):
                return None
            return round(f, 2)
        except (TypeError, ValueError):
            return None

    day1_high = _to_native_float(day1.get("target_high"))
    day1_low = _to_native_float(day1.get("target_low"))
    day2_high = _to_native_float(day2.get("target_high"))
    day2_low = _to_native_float(day2.get("target_low"))

    if all(v is None for v in [day1_high, day1_low, day2_high, day2_low]):
        logger.debug(f"[{stock_code}] 预测值全为None，跳过写入", extra=extra)
        return

    from scripts.database import get_connection, release_connection
    try:
        conn = get_connection()
    except Exception as e:
        logger.error(f"[{stock_code}] 获取数据库连接失败: {e}", extra=extra)
        return
    cur = conn.cursor()
    try:
        table_ident = sql.Identifier(f"stock_{stock_code}")
        query = sql.SQL("""
            UPDATE {}
            SET day1_pred_high = %s,
                day1_pred_low = %s,
                day2_pred_high = %s,
                day2_pred_low = %s
            WHERE trade_date = (SELECT MAX(trade_date) FROM {})
        """).format(table_ident, table_ident)
        cur.execute(query, (day1_high, day1_low, day2_high, day2_low))
        updated = cur.rowcount
        conn.commit()
        if updated > 0:
            logger.info(f"[{stock_code}] 预测值写入DB成功: day1={day1_low}-{day1_high}, day2={day2_low}-{day2_high}, 影响行数={updated}", extra=extra)
        else:
            logger.warning(f"[{stock_code}] 预测值写入DB: 无匹配行更新，表stock_{stock_code}可能无数据", extra=extra)
    except Exception as e:
        logger.error(f"[{stock_code}] 预测值写入DB SQL执行失败: {e}", extra=extra)
        try:
            conn.rollback()
        except Exception:
            # 回滚失败时连接可能已关闭，静默忽略以保证资源释放
            pass
    finally:
        cur.close()
        release_connection(conn)


def _set_cache_item(key, value):
    """写入结果缓存，并在超过容量上限时按 LRU 驱逐最旧条目。"""
    _result_cache[key] = value
    _result_cache.move_to_end(key)
    while len(_result_cache) > _RESULT_CACHE_MAX_SIZE:
        _result_cache.popitem(last=False)


def _cleanup_cache():
    now = datetime.now()
    expired = [k for k, (_, t) in _result_cache.items() if (now - t).total_seconds() > 600]
    for k in expired:
        del _result_cache[k]


def _clean_indicators(indicators: Dict) -> Dict:
    result = {}
    for key, val in indicators.items():
        if isinstance(val, dict):
            cleaned = {}
            for k, v in val.items():
                if isinstance(v, pd.Series):
                    cleaned[k] = to_list(v)
                elif isinstance(v, pd.DataFrame):
                    cleaned[k] = sanitize_for_json(v.to_dict(orient="list"))
                elif isinstance(v, np.ndarray):
                    cleaned[k] = to_list(v)
                elif hasattr(v, 'tolist'):
                    cleaned[k] = to_list(v)
                elif hasattr(v, 'item'):
                    try:
                        cleaned[k] = clean_float(v.item())
                    except Exception:
                        # 标量转换失败时回退到通用安全序列化
                        cleaned[k] = _safe_item(v)
                elif isinstance(v, dict):
                    cleaned[k] = {kk: _safe_item(vv) for kk, vv in v.items()}
                elif isinstance(v, list):
                    cleaned[k] = [_safe_item(x) for x in v]
                else:
                    cleaned[k] = clean_float(v)
            result[key] = cleaned
        elif isinstance(val, pd.Series):
            result[key] = to_list(val)
        elif isinstance(val, pd.DataFrame):
            result[key] = sanitize_for_json(val.to_dict(orient="list"))
        elif isinstance(val, np.ndarray):
            result[key] = to_list(val)
        else:
            result[key] = clean_float(val)
    return result


def run_analysis_staged(stock_code: str, position_type: str = "未持有", cost_price: float = None, stage_callback=None, logger=None):
    if logger is None:
        logger = AnalysisLogger(stock_code=stock_code)
    elif hasattr(logger, "stock_code") and not logger.stock_code:
        logger.stock_code = stock_code
    start_time = time.time()
    logger.info(f"开始分析: {stock_code}")

    try:
        result = _run_analysis_core(stock_code, position_type, cost_price, logger, stage_callback)
    except Exception as e:
        logger.error(f"分析过程异常: {e}")
        if stage_callback:
            stage_callback('error', {'error': str(e)})
        return None

    total_elapsed = time.time() - start_time
    logger.info(f"分析完成 (总耗时: {total_elapsed:.1f}s)")

    if result is not None:
        result["analysis_log"] = logger.entries
        # 写入结果缓存，供后续查询
        # 同时用 stock_input 和解析后的 stock_code 做双写，确保缓存查询能命中
        now = datetime.now()
        cache_key_input = (stock_code, position_type, cost_price)
        with _cache_lock:
            _set_cache_item(cache_key_input, (result, now))
            # 如果 result 中有解析后的 stock_code 且与输入不同，也用 stock_code 缓存
            resolved_code = result.get("stock_code", stock_code)
            if resolved_code and resolved_code != stock_code:
                cache_key_resolved = (resolved_code, position_type, cost_price)
                _set_cache_item(cache_key_resolved, (result, now))
            _cleanup_cache()

        # 写入预测值到数据库
        try:
            resolved_code = result.get("stock_code", stock_code)
            pred = result.get("price_prediction", {})
            _svc_logger.info(
                f"[staged] 写入预测值到DB: {resolved_code}, "
                f"day1_low={pred.get('day1', {}).get('target_low')}, "
                f"day1_high={pred.get('day1', {}).get('target_high')}, "
                f"day2_low={pred.get('day2', {}).get('target_low')}, "
                f"day2_high={pred.get('day2', {}).get('target_high')}",
                extra={"stock_code": resolved_code},
            )
            _update_prediction_to_db(resolved_code, pred)
        except Exception as e:
            _svc_logger.warning(f"[staged] 预测值写入数据库失败: {stock_code}, error={e}", extra={"stock_code": stock_code})

        if stage_callback:
            log_data('transfer', 'analyzer', 'sse_callback', 'success',
                     stock_code=stock_code,
                     has_signal=result.get('trading_signal') is not None,
                     has_prediction=result.get('price_prediction') is not None)
            stage_callback('stage_complete', result)
        return result
    else:
        if stage_callback:
            stage_callback('stage_complete', {'error': '分析失败'})
        return None


def _safe_item(v):
    if hasattr(v, 'item'):
        try:
            return clean_float(v.item())
        except Exception:
            # 标量转换失败时回退到 tolist/clean_float，保持序列化不中断
            pass
    if hasattr(v, 'tolist'):
        return to_list(v)
    return clean_float(v)
