"""
PostgreSQL数据库操作模块
支持时序数据和向量数据存储
"""

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

from scripts.logger import db_logger


def to_python_type(val):
    """将numpy类型转换为Python原生类型"""
    if val is None:
        return None
    if isinstance(val, np.ndarray):
        return val.tolist()
    try:
        return val.item()
    except (AttributeError, ValueError):
        return val


DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "postgres",
    "database": "stock_data",
}


def get_connection():
    """获取数据库连接"""
    return psycopg2.connect(**DB_CONFIG)


def init_database():
    """初始化数据库：创建数据库和扩展"""
    db_logger.info("=" * 50)
    db_logger.info("开始初始化数据库...")
    db_logger.info(
        f"数据库配置: host={DB_CONFIG['host']}, port={DB_CONFIG['port']}, database={DB_CONFIG['database']}"
    )

    conn = psycopg2.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database="postgres",
    )
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s", (DB_CONFIG["database"],)
    )
    if not cur.fetchone():
        cur.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_CONFIG["database"]))
        )
        db_logger.info(f"数据库 {DB_CONFIG['database']} 创建成功")
    else:
        db_logger.info(f"数据库 {DB_CONFIG['database']} 已存在")

    cur.close()
    conn.close()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector CASCADE")
    db_logger.info("TimescaleDB 和 Vector 扩展已启用")

    cur.close()
    conn.close()
    db_logger.info("数据库初始化完成")
    db_logger.info("=" * 50)


class StockDataManager:
    """股票数据管理器"""

    def __init__(self, stock_code: str):
        self.stock_code = stock_code.zfill(6)
        self.table_name = f"stock_{self.stock_code}"

    def table_exists(self) -> bool:
        """检查表是否存在"""
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(f"""
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = '{self.table_name}'
            """)
            return cur.fetchone() is not None
        finally:
            cur.close()
            conn.close()

    def create_table(self):
        """为单个股票创建独立的数据表"""
        db_logger.info(f"[{self.stock_code}] 开始创建数据表: {self.table_name}")

        conn = get_connection()
        conn.autocommit = True
        cur = conn.cursor()

        try:
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id SERIAL,
                trade_date DATE NOT NULL,
                trade_time TIMESTAMP NOT NULL,
                
                open NUMERIC(12, 2),
                high NUMERIC(12, 2),
                low NUMERIC(12, 2),
                close NUMERIC(12, 2),
                volume BIGINT,
                amount NUMERIC(20, 2),
                
                change_pct NUMERIC(10, 4),
                change_amount NUMERIC(12, 2),
                turnover_rate NUMERIC(10, 4),
                
                pe_dynamic NUMERIC(12, 4),
                pb NUMERIC(12, 4),
                total_market_cap NUMERIC(20, 2),
                circ_market_cap NUMERIC(20, 2),
                
                macd_dif NUMERIC(12, 6),
                macd_dea NUMERIC(12, 6),
                macd_hist NUMERIC(12, 6),
                
                rsi_6 NUMERIC(10, 4),
                rsi_12 NUMERIC(10, 4),
                rsi_24 NUMERIC(10, 4),
                
                k NUMERIC(10, 4),
                d NUMERIC(10, 4),
                j NUMERIC(10, 4),
                
                ma5 NUMERIC(12, 2),
                ma10 NUMERIC(12, 2),
                ma20 NUMERIC(12, 2),
                ma60 NUMERIC(12, 2),
                
                boll_upper NUMERIC(12, 2),
                boll_middle NUMERIC(12, 2),
                boll_lower NUMERIC(12, 2),
                
                main_flow NUMERIC(20, 2),
                main_flow_ratio NUMERIC(10, 4),
                
                features_vector vector(384),
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                PRIMARY KEY (id, trade_time)
            );
            """

            cur.execute(create_table_sql)
            db_logger.info(f"[{self.stock_code}] 表创建成功")

            comments = [
                ("id", "自增主键ID"),
                ("trade_date", "交易日期"),
                ("trade_time", "交易时间戳"),
                ("open", "开盘价"),
                ("high", "最高价"),
                ("low", "最低价"),
                ("close", "收盘价"),
                ("volume", "成交量(手)"),
                ("amount", "成交额(元)"),
                ("change_pct", "涨跌幅(%)"),
                ("change_amount", "涨跌额(元)"),
                ("turnover_rate", "换手率(%)"),
                ("pe_dynamic", "市盈率(动态)"),
                ("pb", "市净率"),
                ("total_market_cap", "总市值(元)"),
                ("circ_market_cap", "流通市值(元)"),
                ("macd_dif", "MACD DIF线"),
                ("macd_dea", "MACD DEA线"),
                ("macd_hist", "MACD 柱状图"),
                ("rsi_6", "RSI 6日"),
                ("rsi_12", "RSI 12日"),
                ("rsi_24", "RSI 24日"),
                ("k", "KDJ K值"),
                ("d", "KDJ D值"),
                ("j", "KDJ J值"),
                ("ma5", "5日均线"),
                ("ma10", "10日均线"),
                ("ma20", "20日均线"),
                ("ma60", "60日均线"),
                ("boll_upper", "布林带上轨"),
                ("boll_middle", "布林带中轨"),
                ("boll_lower", "布林带下轨"),
                ("main_flow", "主力净流入(元)"),
                ("main_flow_ratio", "主力净流入占比(%)"),
                ("features_vector", "特征向量(用于相似股票查询)"),
                ("created_at", "记录创建时间"),
            ]

            for col, desc in comments:
                cur.execute(f"COMMENT ON COLUMN {self.table_name}.{col} IS %s", (desc,))

            cur.execute(
                f"COMMENT ON TABLE {self.table_name} IS %s",
                (f"股票{self.stock_code}历史行情数据",),
            )
            db_logger.info(f"[{self.stock_code}] 字段注释添加完成")

            try:
                cur.execute(
                    f"SELECT create_hypertable('{self.table_name}', 'trade_time', migrate_data => TRUE)"
                )
                db_logger.info(f"[{self.stock_code}] 已转换为时序超表")
            except psycopg2.errors.DuplicateObject:
                db_logger.info(f"[{self.stock_code}] 已经是时序超表")
            except Exception as e:
                db_logger.warning(f"[{self.stock_code}] 时序超表创建跳过: {e}")

            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.stock_code}_trade_date ON {self.table_name} (trade_date)"
            )
            try:
                cur.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{self.stock_code}_features ON {self.table_name} USING ivfflat (features_vector vector_cosine_ops) WITH (lists = 100)"
                )
            except Exception as e:
                db_logger.warning(f"[{self.stock_code}] 向量索引创建失败(可忽略): {e}")
            db_logger.info(f"[{self.stock_code}] 索引创建完成")
            db_logger.info(f"[{self.stock_code}] 表 {self.table_name} 创建完成!")

        except Exception as e:
            db_logger.error(f"[{self.stock_code}] 创建表出错: {e}")
            raise
        finally:
            cur.close()
            conn.close()

    def get_latest_trade_date(self) -> Optional[datetime]:
        """获取数据库中最新交易日期"""
        db_logger.debug(f"[{self.stock_code}] 查询最新交易日期")
        conn = get_connection()
        cur = conn.cursor()

        try:
            cur.execute(f"SELECT MAX(trade_date) FROM {self.table_name}")
            result = cur.fetchone()
            latest = result[0] if result and result[0] else None
            db_logger.debug(f"[{self.stock_code}] 最新交易日期: {latest}")
            return latest
        except psycopg2.errors.UndefinedTable:
            db_logger.debug(f"[{self.stock_code}] 表不存在")
            return None
        finally:
            cur.close()
            conn.close()

    def check_data_exists(self, trade_date: datetime) -> bool:
        """检查指定交易日的数据是否存在"""
        db_logger.debug(f"[{self.stock_code}] 检查数据是否存在: {trade_date}")
        conn = get_connection()
        cur = conn.cursor()

        try:
            cur.execute(
                f"""
                SELECT 1 FROM {self.table_name} 
                WHERE trade_date = %s LIMIT 1
            """,
                (trade_date,),
            )

            exists = cur.fetchone() is not None
            db_logger.debug(f"[{self.stock_code}] 数据存在: {exists}")
        except psycopg2.errors.UndefinedTable:
            exists = False
        finally:
            cur.close()
            conn.close()
        return exists

    def insert_daily_data(self, data: Dict[str, Any]):
        """插入日线数据"""
        db_logger.info(f"[{self.stock_code}] 插入日线数据: {data.get('trade_date')}")
        conn = get_connection()
        cur = conn.cursor()

        insert_sql = f"""
        INSERT INTO {self.table_name} (
            trade_date, trade_time,
            open, high, low, close, volume, amount,
            change_pct, change_amount, turnover_rate,
            pe_dynamic, pb, total_market_cap, circ_market_cap,
            main_flow, main_flow_ratio
        ) VALUES (
            %(trade_date)s, %(trade_time)s,
            %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(amount)s,
            %(change_pct)s, %(change_amount)s, %(turnover_rate)s,
            %(pe_dynamic)s, %(pb)s, %(total_market_cap)s, %(circ_market_cap)s,
            %(main_flow)s, %(main_flow_ratio)s
        ) ON CONFLICT DO NOTHING
        """

        cur.execute(insert_sql, data)
        conn.commit()
        cur.close()
        conn.close()
        db_logger.info(f"[{self.stock_code}] 日线数据插入完成")

    def update_technical_indicators(
        self, trade_date: datetime, indicators: Dict[str, Any]
    ):
        """更新技术指标数据"""
        db_logger.info(f"[{self.stock_code}] 更新技术指标: {trade_date}")
        conn = get_connection()
        cur = conn.cursor()

        update_sql = f"""
        UPDATE {self.table_name} SET
            macd_dif = %(macd_dif)s,
            macd_dea = %(macd_dea)s,
            macd_hist = %(macd_hist)s,
            rsi_6 = %(rsi_6)s,
            rsi_12 = %(rsi_12)s,
            rsi_24 = %(rsi_24)s,
            k = %(k)s,
            d = %(d)s,
            j = %(j)s,
            ma5 = %(ma5)s,
            ma10 = %(ma10)s,
            ma20 = %(ma20)s,
            ma60 = %(ma60)s,
            boll_upper = %(boll_upper)s,
            boll_middle = %(boll_middle)s,
            boll_lower = %(boll_lower)s
        WHERE trade_date = %(trade_date)s
        """

        cur.execute(update_sql, {**indicators, "trade_date": trade_date})
        conn.commit()
        cur.close()
        conn.close()

    def update_vector_features(self, trade_date: datetime, vector: List[float]):
        """更新向量特征"""
        conn = get_connection()
        cur = conn.cursor()

        update_sql = f"""
        UPDATE {self.table_name} SET
            features_vector = %s
        WHERE trade_date = %s
        """

        cur.execute(update_sql, (vector, trade_date))
        conn.commit()
        cur.close()
        conn.close()

    def get_historical_data(self, days: int = 60) -> pd.DataFrame:
        """获取历史数据"""
        conn = get_connection()

        query_sql = f"""
        SELECT 
            trade_date, open, high, low, close, volume, amount,
            change_pct, turnover_rate,
            macd_dif, macd_dea, macd_hist,
            rsi_6, rsi_12, rsi_24,
            k, d, j,
            ma5, ma10, ma20, ma60,
            boll_upper, boll_middle, boll_lower,
            main_flow, main_flow_ratio
        FROM {self.table_name}
        ORDER BY trade_date DESC
        LIMIT {days}
        """

        df = pd.read_sql(query_sql, conn)
        conn.close()
        return df


def ensure_stock_table(stock_code: str):
    """确保股票数据表存在"""
    manager = StockDataManager(stock_code)
    manager.create_table()


def get_or_fetch_stock_data(
    stock_code: str, force_refresh: bool = False
) -> Dict[str, Any]:
    """
    获取股票数据：先检查数据库，若无最新数据则从API获取并存储

    Args:
        stock_code: 股票代码
        force_refresh: 是否强制刷新数据

    Returns:
        dict: 包含数据和来源信息
    """
    from . import stock_query

    db_logger.info("=" * 50)
    db_logger.info(f"[{stock_code}] 开始获取数据 (force_refresh={force_refresh})")

    manager = StockDataManager(stock_code)

    try:
        manager.create_table()
    except Exception as e:
        db_logger.error(f"[{stock_code}] 创建表失败: {e}")

    latest_date = manager.get_latest_trade_date()
    today = datetime.now().date()

    should_fetch = force_refresh or latest_date is None or latest_date < today

    if should_fetch:
        db_logger.info(
            f"[{stock_code}] 需要获取最新数据 (最新日期={latest_date}, 今天={today})"
        )

        try:
            from .stock_query import get_stock_info, get_fund_flow, get_history_data
            from .technical_indicators import calculate_all_indicators

            stock_info = get_stock_info(stock_code)
            fund_flow = get_fund_flow(stock_code)
            history_df = get_history_data(stock_code, days=60)

            if history_df is not None and not history_df.empty:
                indicators = calculate_all_indicators(history_df)

                latest = history_df.iloc[-1]
                trade_date = pd.to_datetime(latest.get("日期", latest.name))
                if isinstance(trade_date, pd.Timestamp):
                    trade_date = trade_date.to_pydatetime()

                daily_data = {
                    "trade_date": trade_date.date()
                    if hasattr(trade_date, "date")
                    else trade_date,
                    "trade_time": trade_date,
                    "open": float(latest.get("开盘", 0))
                    if pd.notna(latest.get("开盘"))
                    else None,
                    "high": float(latest.get("最高", 0))
                    if pd.notna(latest.get("最高"))
                    else None,
                    "low": float(latest.get("最低", 0))
                    if pd.notna(latest.get("最低"))
                    else None,
                    "close": float(latest.get("收盘", 0))
                    if pd.notna(latest.get("收盘"))
                    else None,
                    "volume": int(latest.get("成交量", 0))
                    if pd.notna(latest.get("成交量"))
                    else 0,
                    "amount": float(latest.get("成交额", 0))
                    if pd.notna(latest.get("成交额"))
                    else None,
                    "change_pct": float(stock_info.get("涨跌幅", 0))
                    if pd.notna(stock_info.get("涨跌幅"))
                    else None,
                    "change_amount": float(stock_info.get("涨跌额", 0))
                    if pd.notna(stock_info.get("涨跌额"))
                    else None,
                    "turnover_rate": float(stock_info.get("换手率", 0))
                    if pd.notna(stock_info.get("换手率"))
                    else None,
                    "pe_dynamic": float(stock_info.get("市盈率-动态", 0))
                    if pd.notna(stock_info.get("市盈率-动态"))
                    else None,
                    "pb": float(stock_info.get("市净率", 0))
                    if pd.notna(stock_info.get("市净率"))
                    else None,
                    "total_market_cap": float(stock_info.get("总市值", 0))
                    if pd.notna(stock_info.get("总市值"))
                    else None,
                    "circ_market_cap": float(stock_info.get("流通市值", 0))
                    if pd.notna(stock_info.get("流通市值"))
                    else None,
                    "main_flow": float(fund_flow.get("主力净流入", 0))
                    if fund_flow.get("主力净流入")
                    else 0,
                    "main_flow_ratio": float(fund_flow.get("主力净流入占比", 0))
                    if fund_flow.get("主力净流入占比")
                    else 0,
                }

                try:
                    manager.insert_daily_data(daily_data)
                except Exception as e:
                    db_logger.error(f"[{stock_code}] 存储日线数据失败: {e}")

                if "MACD" in indicators:
                    macd = indicators["MACD"]
                    ind_data = {
                        "trade_date": trade_date.date()
                        if hasattr(trade_date, "date")
                        else trade_date,
                        "macd_dif": to_python_type(macd.get("DIF")),
                        "macd_dea": to_python_type(macd.get("DEA")),
                        "macd_hist": to_python_type(macd.get("MACD")),
                    }

                    if "RSI" in indicators:
                        rsi = indicators["RSI"]
                        ind_data["rsi_6"] = to_python_type(
                            rsi.get("RSI6", {}).get("value")
                        )
                        ind_data["rsi_12"] = to_python_type(
                            rsi.get("RSI12", {}).get("value")
                        )
                        ind_data["rsi_24"] = to_python_type(
                            rsi.get("RSI24", {}).get("value")
                        )

                    if "KDJ" in indicators:
                        kdj = indicators["KDJ"]
                        ind_data["k"] = to_python_type(kdj.get("K"))
                        ind_data["d"] = to_python_type(kdj.get("D"))
                        ind_data["j"] = to_python_type(kdj.get("J"))

                    if "MA" in indicators:
                        ma = indicators["MA"]
                        ind_data["ma5"] = to_python_type(ma.get("MA5"))
                        ind_data["ma10"] = to_python_type(ma.get("MA10"))
                        ind_data["ma20"] = to_python_type(ma.get("MA20"))
                        ind_data["ma60"] = to_python_type(ma.get("MA60"))

                    if "BOLL" in indicators:
                        boll = indicators["BOLL"]
                        ind_data["boll_upper"] = to_python_type(boll.get("upper"))
                        ind_data["boll_middle"] = to_python_type(boll.get("middle"))
                        ind_data["boll_lower"] = to_python_type(boll.get("lower"))

                    try:
                        manager.update_technical_indicators(trade_date.date(), ind_data)
                    except Exception as e:
                        db_logger.error(f"[{stock_code}] 更新技术指标失败: {e}")

            db_logger.info(f"[{stock_code}] 从API获取数据成功")

            return {
                "source": "api",
                "stock_info": stock_info,
                "fund_flow": fund_flow,
                "history_df": history_df,
                "indicators": indicators,
            }

        except Exception as e:
            db_logger.error(f"[{stock_code}] 从API获取数据失败: {e}")
            return {"source": "error", "error": str(e)}
    else:
        db_logger.info(f"[{stock_code}] 使用数据库中现有数据，最新日期: {latest_date}")

        try:
            df = manager.get_historical_data(60)
            return {"source": "database", "dataframe": df, "latest_date": latest_date}
        except Exception as e:
            db_logger.error(f"[{stock_code}] 从数据库获取数据失败: {e}")
            return {"source": "error", "error": str(e)}
