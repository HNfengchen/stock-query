import sys
import os
import re
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta
from typing import Dict, Optional

import numpy as np
import pandas as pd
from psycopg2 import sql

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.core.data_fetcher import DataFetcher
from scripts.core.analyzer import StockAnalyzer
from scripts.technical_indicators import calculate_all_indicators

from backend.utils import clean_float, to_list, deep_clean_nan, clean_nested
from backend.logging import log_data

_svc_logger = logging.getLogger("stock_query.analysis_service")


class AnalysisLogger:
    def __init__(self):
        self.entries = []
        self.callback = None

    def set_callback(self, callback):
        self.callback = callback

    def log(self, level: str, message: str):
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "message": message
        }
        self.entries.append(entry)
        if self.callback:
            try:
                self.callback(entry)
            except Exception:
                pass

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
_result_cache = {}
_cache_lock = threading.Lock()


def _validate_stock_code(stock_code: str):
    if not re.match(r'^\d{6}$', stock_code):
        raise ValueError(f"无效的股票代码格式: {stock_code}，必须为6位数字")


from scripts.core.config_loader import load_config


def get_fetcher():
    global _fetcher_cache
    if _fetcher_cache is None:
        _fetcher_cache = DataFetcher(load_config())
    return _fetcher_cache


def get_analyzer():
    global _analyzer_cache
    if _analyzer_cache is None:
        _analyzer_cache = StockAnalyzer(load_config())
    return _analyzer_cache


def build_chart_data(history_df, indicators: Dict, fund_flow: Dict = None) -> Dict:
    if history_df is None or history_df.empty:
        return {
            "kline": {"dates": [], "opens": [], "closes": [], "highs": [], "lows": [], "volumes": [],
                      "ma5": [], "ma10": [], "ma20": [], "ma60": [], "boll_upper": [], "boll_middle": [], "boll_lower": []},
            "technical": {"dates": [], "macd": [], "dif": [], "dea": [], "rsi6": [], "rsi12": [], "k": [], "d": [], "j": []},
            "fund_flow": {"dates": [], "main_flow": [], "main_flow_ratio": [], "small_flow": [], "change_pct": []},
        }

    import pandas as pd
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


def _run_analysis_core(stock_input, position_type, cost_price, logger, stage_callback=None):
    fetcher = get_fetcher()
    analyzer = get_analyzer()

    try:
        stock_code, stock_name, market = fetcher.resolve_stock_code(stock_input)
        logger.info(f"股票代码解析: {stock_code} ({stock_name})")
    except Exception as e:
        logger.warn(f"股票代码解析失败，使用原始输入: {e}")
        stock_code = stock_input
        stock_name = stock_input
        market = None

    info = None
    fund_flow = None
    history_df = None
    indicators = None
    data_source = None
    fetch_start = time.time()

    try:
        from scripts.database import get_or_fetch_stock_data
        db_data = get_or_fetch_stock_data(stock_code, force_refresh=False, days=120)
        if db_data:
            data_source = db_data.get("source", "unknown")
            if db_data.get("history_df") is not None and not db_data["history_df"].empty:
                history_df = db_data["history_df"]
            if db_data.get("stock_info"):
                info = db_data["stock_info"]
            if db_data.get("fund_flow"):
                fund_flow = db_data["fund_flow"]
            if db_data.get("indicators"):
                indicators = db_data["indicators"]
    except Exception as e:
        logger.warn(f"数据库获取数据异常: {e}")

    # 仅在DB回退模式下跳过API重试（避免API超时导致二次阻塞）
    is_fallback = data_source == "database_fallback"

    if info is None and not is_fallback:
        try:
            info = fetcher.fetch_stock_info(stock_code)
        except Exception:
            logger.warn("stock_info获取失败")
    if fund_flow is None and not is_fallback:
        try:
            fund_flow = fetcher.fetch_fund_flow(stock_code)
        except Exception:
            logger.warn("fund_flow获取失败")
    if history_df is None:
        try:
            history_df = fetcher.fetch_history_data(stock_code, days=120)
        except Exception:
            logger.warn("历史数据获取失败")

    info = info or {}
    fund_flow = fund_flow or {}

    fetch_elapsed = time.time() - fetch_start
    if not info or not fund_flow:
        logger.warn("部分数据获取失败")
    else:
        logger.info(f"数据获取完成 (耗时: {fetch_elapsed:.1f}s)")

    if history_df is None or history_df.empty:
        return None

    all_data = {
        "stock_code": stock_code,
        "stock_name": stock_name or info.get("名称", stock_code),
        "market": market,
        "stock_info": info,
        "fund_flow": fund_flow,
        "history_data": history_df,
        "data_quality": db_data.get("data_quality", "normal") if db_data else "normal",
    }

    # 获取大盘数据，避免后续 analyze_market_sentiment 重复调用 efinance
    market_data = None
    try:
        market_data = fetcher.fetch_market_data()
    except Exception as e:
        logger.debug(f"获取大盘数据失败: {e}")
    # 即使获取失败也传入空 dict，避免 analyze_market_sentiment 再次调用 efinance
    if not market_data:
        market_data = {}
    all_data["market_data"] = market_data

    log_data('transfer', 'data_fetcher', 'analyzer', 'success',
             stock_code=stock_code,
             has_history=all_data.get('history_data') is not None,
             has_stock_info=all_data.get('stock_info') is not None,
             has_market_data='market_data' in all_data)

    if stage_callback:
        stage_callback('stage_basic', {
            'stock_info': info,
            'stock_name': all_data.get('stock_name'),
            'fund_flow': fund_flow,
        })

    if not indicators:
        indicators = calculate_all_indicators(history_df)
    logger.info(f"指标计算完成: {len(indicators)}组指标")

    all_data["indicators"] = indicators

    if stage_callback:
        stage_callback('stage_technical', {
            'indicators': indicators,
            'technical_chart_data': build_chart_data(history_df, indicators, fund_flow) if indicators else None,
        })

    current_price = 0
    try:
        current_price = float(info.get('最新价', 0)) if info.get('最新价') else 0
    except (TypeError, ValueError):
        current_price = 0

    technical_analysis = analyzer.analyze_technical(indicators, current_price) if indicators else {"score": 0.5}
    tech_score = technical_analysis.get('score', 0.5) if technical_analysis else 0.5
    logger.info(f"技术分析完成: 评分={tech_score:.2f}")

    fund_flow_analysis = analyzer.analyze_fund_flow(fund_flow, info)
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

    validation = analyzer.cross_validate_analysis(
        analysis, price_prediction, indicators,
        trading_signal, position_type, current_price,
        history_df=history_df,
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
                pass
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
                pass

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

    charts = build_chart_data(history_df, indicators, fund_flow)

    result = {
        "stock_code": stock_code,
        "stock_name": stock_name or info.get('名称', stock_code),
        "analysis": {
            "technical_score": clean_float(tech_score),
            "fund_flow_score": clean_float(fund_score),
            "sentiment_score": clean_float(sentiment_score),
            "overall_score": clean_float(trading_signal.get('score', 0)),
            "recommendation": action_gate_text,
            "details": clean_nested(analysis),
        },
        "trading_signal": {
            "score": clean_float(trading_signal.get('score', 0)),
            "signal": trading_signal.get('signal', 'hold'),
            "signal_text": action_gate_text,
            "action_gate": action_gate,
            "reason": trading_signal.get('reason', ''),
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
        "market_data": market_data if market_data else {},
        "charts": charts,
    }

    if hmm_state:
        result["hmm_state"] = clean_nested(hmm_state)

    result = deep_clean_nan(result)
    return result


def run_analysis(stock_input: str, position_status: str, cost_price: Optional[float] = None, skip_signal_cache: bool = False) -> Dict:
    cache_key = (stock_input, position_status, cost_price)
    now = datetime.now()
    with _cache_lock:
        if cache_key in _result_cache:
            cached_result, cached_time = _result_cache[cache_key]
            if (now - cached_time).total_seconds() < 600:
                if not skip_signal_cache:
                    try:
                        from backend.services.history_service import update_signal_cache
                        stock_code = cached_result.get("stock_code", stock_input)
                        update_signal_cache(stock_code, position_status, cached_result.get("trading_signal", {}), cost_price=cost_price)
                    except Exception as e:
                        _svc_logger.warning(f"更新信号缓存失败: {e}")
                return cached_result

    logger = AnalysisLogger()
    start_time = time.time()
    logger.info(f"开始分析: {stock_input}")

    result = _run_analysis_core(stock_input, position_status, cost_price, logger)

    if result is None:
        raise ValueError(f"无法完成 {stock_input} 的分析")

    total_elapsed = time.time() - start_time
    logger.info(f"分析完成 (总耗时: {total_elapsed:.1f}s)")
    result["analysis_log"] = logger.entries

    with _cache_lock:
        _result_cache[cache_key] = (result, now)
        # 双写：用解析后的 stock_code 也缓存一份，确保通过代码查询时也能命中
        resolved_code = result.get("stock_code", stock_input)
        if resolved_code and resolved_code != stock_input:
            cache_key_resolved = (resolved_code, position_status, cost_price)
            _result_cache[cache_key_resolved] = (result, now)
        _cleanup_cache()

    if not skip_signal_cache:
        try:
            from backend.services.history_service import update_signal_cache
            update_signal_cache(result.get("stock_code", stock_input), position_status, result.get("trading_signal", {}), cost_price=cost_price)
        except Exception as e:
            _svc_logger.warning(f"更新信号缓存失败: {e}")

    try:
        pred = result.get("price_prediction", {})
        resolved = result.get("stock_code", stock_input)
        _svc_logger.info(f"写入预测值到DB: {resolved}, day1={pred.get('day1', {})}, day2={pred.get('day2', {})}")
        _update_prediction_to_db(resolved, pred)
    except Exception as e:
        _svc_logger.warning(f"更新预测值到数据库失败: {e}")

    return result


def _update_prediction_to_db(stock_code: str, price_prediction: Dict):
    _validate_stock_code(stock_code)
    logger = _svc_logger

    if not price_prediction:
        logger.debug(f"[{stock_code}] 无预测数据，跳过写入")
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
        logger.debug(f"[{stock_code}] 预测值全为None，跳过写入")
        return

    from scripts.database import get_connection, release_connection
    try:
        conn = get_connection()
    except Exception as e:
        logger.error(f"[{stock_code}] 获取数据库连接失败: {e}")
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
            logger.info(f"[{stock_code}] 预测值写入DB成功: day1={day1_low}-{day1_high}, day2={day2_low}-{day2_high}, 影响行数={updated}")
        else:
            logger.warning(f"[{stock_code}] 预测值写入DB: 无匹配行更新，表stock_{stock_code}可能无数据")
    except Exception as e:
        logger.error(f"[{stock_code}] 预测值写入DB SQL执行失败: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        cur.close()
        release_connection(conn)


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
        logger = AnalysisLogger()
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
            _result_cache[cache_key_input] = (result, now)
            # 如果 result 中有解析后的 stock_code 且与输入不同，也用 stock_code 缓存
            resolved_code = result.get("stock_code", stock_code)
            if resolved_code and resolved_code != stock_code:
                cache_key_resolved = (resolved_code, position_type, cost_price)
                _result_cache[cache_key_resolved] = (result, now)
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
                f"day2_high={pred.get('day2', {}).get('target_high')}"
            )
            _update_prediction_to_db(resolved_code, pred)
        except Exception as e:
            _svc_logger.warning(f"[staged] 预测值写入数据库失败: {stock_code}, error={e}")

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
            pass
    if hasattr(v, 'tolist'):
        return to_list(v)
    return clean_float(v)
