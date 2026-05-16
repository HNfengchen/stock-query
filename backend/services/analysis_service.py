import sys
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import yaml
from scripts.core.data_fetcher import DataFetcher
from scripts.core.analyzer import StockAnalyzer
from scripts.technical_indicators import calculate_all_indicators
from backend.utils import clean_float, to_list, deep_clean_nan, clean_nested

_config_cache = None
_fetcher_cache = None
_analyzer_cache = None
_result_cache = {}


def load_config():
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f)
    return _config_cache


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
    rsi6_vals = to_list(rsi_series.get("RSI(6)", {}).get("series", []))
    rsi12_vals = to_list(rsi_series.get("RSI(12)", {}).get("series", []))
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


def run_analysis(stock_input: str, position_status: str, cost_price: Optional[float] = None, skip_signal_cache: bool = False) -> Dict:
    cache_key = (stock_input, position_status, cost_price)
    now = datetime.now()
    if cache_key in _result_cache:
        cached_result, cached_time = _result_cache[cache_key]
        if (now - cached_time).total_seconds() < 300:
            if not skip_signal_cache:
                try:
                    from backend.services.history_service import update_signal_cache
                    stock_code = cached_result.get("stock_code", stock_input)
                    update_signal_cache(stock_code, position_status, cached_result.get("trading_signal", {}), cost_price=cost_price)
                except Exception as e:
                    import logging
                    logging.getLogger("stock_query").warning(f"更新信号缓存失败: {e}")
            return cached_result

    fetcher = get_fetcher()
    analyzer = get_analyzer()

    stock_code, stock_name, market = fetcher.resolve_stock_code(stock_input)

    info = None
    fund_flow = None
    history_df = None
    indicators = None

    try:
        from scripts.database import get_or_fetch_stock_data
        db_data = get_or_fetch_stock_data(stock_code, force_refresh=False, days=120)
        if db_data:
            if db_data.get("history_df") is not None and not db_data["history_df"].empty:
                history_df = db_data["history_df"]
            if db_data.get("stock_info"):
                info = db_data["stock_info"]
            if db_data.get("fund_flow"):
                fund_flow = db_data["fund_flow"]
            if db_data.get("indicators"):
                indicators = db_data["indicators"]
    except Exception:
        pass

    if info is None:
        info = fetcher.fetch_stock_info(stock_code)
    if fund_flow is None:
        fund_flow = fetcher.fetch_fund_flow(stock_code)
    if history_df is None:
        history_df = fetcher.fetch_history_data(stock_code, days=120)

    if history_df is None or history_df.empty:
        raise ValueError(f"无法获取 {stock_code} 的历史数据")

    if not indicators:
        indicators = calculate_all_indicators(history_df)

    analysis = analyzer.generate_recommendation({
        "stock_code": stock_code,
        "stock_name": stock_name,
        "market": market,
        "stock_info": info,
        "fund_flow": fund_flow,
        "history_data": history_df,
        "indicators": indicators,
    }, position_status, cost_price)

    charts = build_chart_data(history_df, indicators, fund_flow)

    trading_signal = analysis.get("trading_signal", {})
    price_prediction = analysis.get("price_prediction", {})
    position_strategy = analysis.get("position_strategy", {})
    analysis_data = analysis.get("analysis", {})
    validation = analysis.get("validation", {})
    hmm_state = analysis.get("hmm_state")

    action_gate = validation.get("action_gate", "")
    action_gate_text_map = {
        "allow_buy": "建议买入",
        "cautious_buy": "可考虑买入",
        "avoid_buy": "回避",
        "watch": "观望",
        "reduce_position": "减仓",
        "cautious_hold": "谨慎持有",
        "hold_position": "持有",
    }
    action_gate_text = action_gate_text_map.get(action_gate, trading_signal.get("signal_text", "观望"))

    result = {
        "stock_code": stock_code,
        "stock_name": stock_name or info.get("名称", stock_code),
        "analysis": {
            "technical_score": clean_float(analysis_data.get("technical", {}).get("score", 0)),
            "fund_flow_score": clean_float(analysis_data.get("fund_flow", {}).get("score", 0)),
            "sentiment_score": clean_float(analysis_data.get("sentiment", {}).get("score", 0)),
            "overall_score": clean_float(trading_signal.get("score", 0)),
            "recommendation": action_gate_text,
            "details": clean_nested(analysis_data),
        },
        "trading_signal": {
            "score": clean_float(trading_signal.get("score", 0)),
            "signal": trading_signal.get("signal", "hold"),
            "signal_text": action_gate_text,
            "action_gate": action_gate,
            "reason": trading_signal.get("reason", ""),
        },
        "price_prediction": {
            "current": clean_float(price_prediction.get("current")),
            "support": clean_float(price_prediction.get("support")),
            "resistance": clean_float(price_prediction.get("resistance")),
            "validation_confidence": clean_float(price_prediction.get("validation_confidence")),
            "validation_note": price_prediction.get("validation_note", ""),
            "hybrid_alpha": clean_float(price_prediction.get("hybrid_alpha")),
            "ml_prediction": price_prediction.get("ml_prediction"),
            "day1": {
                "target_low": clean_float(price_prediction.get("day1", {}).get("target_low")),
                "target_high": clean_float(price_prediction.get("day1", {}).get("target_high")),
                "trend": price_prediction.get("day1", {}).get("trend", "neutral"),
                "signal": price_prediction.get("day1", {}).get("signal", ""),
            },
            "day2": {
                "target_low": clean_float(price_prediction.get("day2", {}).get("target_low")),
                "target_high": clean_float(price_prediction.get("day2", {}).get("target_high")),
                "trend": price_prediction.get("day2", {}).get("trend", "neutral"),
                "signal": price_prediction.get("day2", {}).get("signal", ""),
            },
        },
        "indicators": _clean_indicators(indicators),
        "position_strategy": clean_nested(position_strategy),
        "validation": clean_nested(validation),
        "stock_info": {k: clean_float(v) for k, v in info.items()},
        "charts": charts,
    }

    if hmm_state:
        result["hmm_state"] = clean_nested(hmm_state)

    result = deep_clean_nan(result)
    _result_cache[cache_key] = (result, now)
    _cleanup_cache()

    if not skip_signal_cache:
        try:
            from backend.services.history_service import update_signal_cache
            update_signal_cache(stock_code, position_status, result.get("trading_signal", {}), cost_price=cost_price)
        except Exception as e:
            import logging
            logging.getLogger("stock_query").warning(f"更新信号缓存失败: {e}")

    try:
        _update_prediction_to_db(stock_code, result.get("price_prediction", {}))
    except Exception as e:
        import logging
        logging.getLogger("stock_query").warning(f"更新预测值到数据库失败: {e}")

    return result


def _update_prediction_to_db(stock_code: str, price_prediction: Dict):
    import logging
    logger = logging.getLogger("stock_query")

    if not price_prediction:
        logger.debug(f"[{stock_code}] 无预测数据，跳过写入")
        return

    day1 = price_prediction.get("day1", {})
    day2 = price_prediction.get("day2", {})
    day1_high = day1.get("target_high")
    day1_low = day1.get("target_low")
    day2_high = day2.get("target_high")
    day2_low = day2.get("target_low")

    if all(v is None for v in [day1_high, day1_low, day2_high, day2_low]):
        logger.debug(f"[{stock_code}] 预测值全为None，跳过写入")
        return

    from scripts.database import get_connection
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            UPDATE stock_{stock_code}
            SET day1_pred_high = COALESCE(%s, day1_pred_high),
                day1_pred_low = COALESCE(%s, day1_pred_low),
                day2_pred_high = COALESCE(%s, day2_pred_high),
                day2_pred_low = COALESCE(%s, day2_pred_low)
            WHERE trade_date = (SELECT MAX(trade_date) FROM stock_{stock_code})
        """, (day1_high, day1_low, day2_high, day2_low))
        updated = cur.rowcount
        conn.commit()
        logger.info(f"[{stock_code}] 预测值写入DB: day1={day1_low}-{day1_high}, day2={day2_low}-{day2_high}, 影响行数={updated}")
    finally:
        cur.close()
        conn.close()


def _cleanup_cache():
    now = datetime.now()
    expired = [k for k, (_, t) in _result_cache.items() if (now - t).total_seconds() > 300]
    for k in expired:
        del _result_cache[k]


def _clean_indicators(indicators: Dict) -> Dict:
    result = {}
    for key, val in indicators.items():
        if isinstance(val, dict):
            cleaned = {}
            for k, v in val.items():
                if hasattr(v, 'tolist'):
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
        else:
            result[key] = clean_float(val)
    return result


def run_analysis_staged(stock_code: str, position_type: str = "未持有", cost_price: float = None, stage_callback=None):
    fetcher = get_fetcher()
    analyzer = get_analyzer()

    all_data = {}

    try:
        all_data = fetcher.fetch_all_data(stock_code)
        if stage_callback:
            stage_callback('stage_basic', {
                'stock_info': all_data.get('stock_info'),
                'stock_name': all_data.get('stock_name'),
                'history_data': all_data.get('history_data'),
                'fund_flow': all_data.get('fund_flow'),
            })
    except Exception as e:
        if stage_callback:
            stage_callback('stage_basic', {'error': str(e)})

    indicators = {}
    try:
        history_df = all_data.get('history_data')
        if history_df is not None and len(history_df) > 0:
            indicators = calculate_all_indicators(history_df)
        if stage_callback:
            stage_callback('stage_technical', {
                'indicators': indicators,
                'technical_chart_data': build_chart_data(history_df, indicators, 'technical') if indicators else None,
            })
    except Exception as e:
        if stage_callback:
            stage_callback('stage_technical', {'error': str(e)})

    try:
        stock_info = all_data.get('stock_info', {})
        current_price = 0
        try:
            current_price = float(stock_info.get('最新价', 0)) if stock_info.get('最新价') else 0
        except (TypeError, ValueError):
            current_price = 0

        technical_analysis = analyzer.analyze_technical(indicators, current_price) if indicators else {"score": 0.5}
        fund_flow_analysis = analyzer.analyze_fund_flow(all_data.get('fund_flow', {}), stock_info)
        market_data = all_data.get('market_data')
        sentiment_analysis = analyzer.analyze_market_sentiment(all_data, market_data)

        analysis = {
            "technical": technical_analysis,
            "fund_flow": fund_flow_analysis,
            "sentiment": sentiment_analysis,
        }

        trading_signal = analyzer.generate_trading_signal(analysis, position_type, market_data)

        resolved_code = all_data.get('stock_code', stock_code)
        price_prediction = analyzer.predict_price_range(all_data, indicators, resolved_code, trading_signal)

        validation = analyzer.cross_validate_analysis(
            analysis, price_prediction, indicators,
            trading_signal, position_type, current_price,
            history_df=all_data.get('history_data'),
        )

        if stage_callback:
            stage_callback('stage_risk', {
                'tech_score': technical_analysis.get('score', 0.5),
                'fund_score': fund_flow_analysis.get('score', 0.5),
                'sentiment_score': sentiment_analysis.get('score', 0.5),
                'signal': trading_signal,
                'validation': validation,
            })
    except Exception as e:
        if stage_callback:
            stage_callback('stage_risk', {'error': str(e)})

    try:
        stock_info = all_data.get('stock_info', {})
        current_price = 0
        try:
            current_price = float(stock_info.get('最新价', 0)) if stock_info.get('最新价') else 0
        except (TypeError, ValueError):
            current_price = 0

        if position_type == "已持有" and cost_price:
            strategy = analyzer.generate_position_strategy(
                all_data, indicators, current_price, cost_price, trading_signal, validation
            )
        else:
            strategy = analyzer.generate_buy_strategy(
                all_data, indicators, current_price, trading_signal, validation
            )

        if stage_callback:
            stage_callback('stage_prediction', {
                'price_prediction': price_prediction,
                'position_strategy': strategy,
            })
    except Exception as e:
        if stage_callback:
            stage_callback('stage_prediction', {'error': str(e)})

    try:
        full_result = run_analysis(stock_code, position_type, cost_price)
        if stage_callback:
            stage_callback('stage_complete', full_result)
        return full_result
    except Exception as e:
        if stage_callback:
            stage_callback('stage_complete', {'error': str(e)})
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
