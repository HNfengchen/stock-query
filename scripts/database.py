"""
PostgreSQL数据库操作模块
支持时序数据和向量数据存储
"""

import psycopg2
import json
import os
import re
import threading
import yaml
from psycopg2 import pool, sql
from datetime import datetime, date as date_type, timedelta
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

from scripts.logger import db_logger


def to_python_type(val):
    """将numpy类型转换为Python原生类型，'-'等非数值字符串转为None"""
    if val is None:
        return None
    if isinstance(val, np.ndarray):
        return val.tolist()
    # efinance对缺失数值返回'-'字符串，PostgreSQL NUMERIC列不接受
    if isinstance(val, str) and val.strip() in ('-', ''):
        return None
    try:
        if pd.isna(val):
            return None
    except (ValueError, TypeError):
        pass
    try:
        return val.item()
    except (AttributeError, ValueError):
        return val


DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "5432")),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", "postgres"),
    "database": os.environ.get("DB_NAME", "stock_data"),
}

def _load_db_config():
    global DB_CONFIG
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "config.yaml")
        if os.path.exists(config_path):
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            if cfg and "database" in cfg:
                db_cfg = cfg["database"]
                DB_CONFIG.update({
                    "host": db_cfg.get("host", DB_CONFIG["host"]),
                    "port": db_cfg.get("port", DB_CONFIG["port"]),
                    "user": db_cfg.get("user", DB_CONFIG["user"]),
                    "password": db_cfg.get("password", DB_CONFIG["password"]),
                    "database": db_cfg.get("database", DB_CONFIG["database"]),
            })
    except Exception:
        # config.yaml 可选，读取失败时使用默认 DB 配置
        pass

_load_db_config()


_connection_pool = None
_pool_lock = threading.Lock()

def _init_pool():
    global _connection_pool
    _connection_pool = pool.ThreadedConnectionPool(
        minconn=2, maxconn=20, **DB_CONFIG
    )

def get_connection(timeout: float = 30.0):
    global _connection_pool
    with _pool_lock:
        if _connection_pool is None:
            _init_pool()
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return _connection_pool.getconn()
        except pool.PoolError:
            time.sleep(0.1)
    raise pool.PoolError(f"获取数据库连接超时({timeout}秒)，连接池已耗尽")

def release_connection(conn):
    global _connection_pool
    if _connection_pool and conn:
        try:
            conn.rollback()
        except Exception:
            # 连接可能已关闭，回滚失败时忽略以保证连接归还
            pass
        _connection_pool.putconn(conn)


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
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector CASCADE")
        db_logger.info("TimescaleDB 和 Vector 扩展已启用")
    finally:
        cur.close()
        release_connection(conn)
    db_logger.info("数据库初始化完成")
    db_logger.info("=" * 50)


class StockDataManager:
    """股票数据管理器"""

    def __init__(self, stock_code: str):
        if not re.match(r'^\d{6}$', stock_code.zfill(6)):
            raise ValueError(f"Invalid stock code: {stock_code}")
        self.stock_code = stock_code.zfill(6)
        self.table_name = f"stock_{self.stock_code}"

    def _migrate_table(self):
        new_columns = [
            ("day1_pred_high", "NUMERIC(12, 2)"),
            ("day1_pred_low", "NUMERIC(12, 2)"),
            ("day2_pred_high", "NUMERIC(12, 2)"),
            ("day2_pred_low", "NUMERIC(12, 2)"),
            ("trend", "VARCHAR(20)"),
        ]
        column_comments = {
            "day1_pred_high": "预测1日最高价",
            "day1_pred_low": "预测1日最低价",
            "day2_pred_high": "预测2日最高价",
            "day2_pred_low": "预测2日最低价",
            "trend": "趋势方向",
        }
        conn = get_connection()
        conn.autocommit = True
        cur = conn.cursor()
        try:
            for col_name, col_type in new_columns:
                cur.execute(
                    "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
                    (self.table_name, col_name),
                )
                if not cur.fetchone():
                    cur.execute(
                        sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
                            sql.Identifier(self.table_name),
                            sql.Identifier(col_name),
                            sql.SQL(col_type),
                        )
                    )
                    db_logger.info(f"[{self.stock_code}] 添加字段 {col_name}")
            for col_name, comment in column_comments.items():
                cur.execute(
                    sql.SQL("COMMENT ON COLUMN {}.{} IS %s").format(
                        sql.Identifier(self.table_name),
                        sql.Identifier(col_name),
                    ),
                    (comment,),
                )
            db_logger.info(f"[{self.stock_code}] 迁移字段注释更新完成")
        finally:
            cur.close()
            release_connection(conn)

    def table_exists(self) -> bool:
        """检查表是否存在"""
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
                (self.table_name,),
            )
            return cur.fetchone() is not None
        finally:
            cur.close()
            release_connection(conn)

    def create_table(self):
        """为单个股票创建独立的数据表"""
        if self.table_exists():
            self._migrate_table()
            db_logger.info(f"[{self.stock_code}] 表 {self.table_name} 已存在，跳过创建")
            return

        db_logger.info(f"[{self.stock_code}] 开始创建数据表: {self.table_name}")

        conn = get_connection()
        conn.autocommit = True
        cur = conn.cursor()

        try:
            create_table_sql = sql.SQL("""
            CREATE TABLE IF NOT EXISTS {} (
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
                
                day1_pred_high NUMERIC(12, 2),
                day1_pred_low NUMERIC(12, 2),
                day2_pred_high NUMERIC(12, 2),
                day2_pred_low NUMERIC(12, 2),

                trend VARCHAR(20),

                features_vector vector(384),
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                PRIMARY KEY (id, trade_time)
            );
            """).format(sql.Identifier(self.table_name))

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
                ("day1_pred_high", "预测1日最高价"),
                ("day1_pred_low", "预测1日最低价"),
                ("day2_pred_high", "预测2日最高价"),
                ("day2_pred_low", "预测2日最低价"),
            ]

            for col, desc in comments:
                cur.execute(
                    sql.SQL("COMMENT ON COLUMN {}.{} IS %s").format(
                        sql.Identifier(self.table_name),
                        sql.Identifier(col),
                    ),
                    (desc,),
                )

            cur.execute(
                sql.SQL("COMMENT ON TABLE {} IS %s").format(
                    sql.Identifier(self.table_name),
                ),
                (f"股票{self.stock_code}历史行情数据",),
            )

            cur.execute(
                sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} UNIQUE (trade_date)").format(
                    sql.Identifier(self.table_name),
                    sql.Identifier(f"{self.table_name}_trade_date_key"),
                )
            )
            db_logger.info(f"[{self.stock_code}] trade_date唯一约束添加完成")
            db_logger.info(f"[{self.stock_code}] 字段注释添加完成")

            try:
                cur.execute(
                    "SELECT create_hypertable(%s, 'trade_time', migrate_data => TRUE)",
                    (self.table_name,),
                )
                db_logger.info(f"[{self.stock_code}] 已转换为时序超表")
            except psycopg2.errors.DuplicateObject:
                db_logger.info(f"[{self.stock_code}] 已经是时序超表")
            except Exception as e:
                db_logger.warning(f"[{self.stock_code}] 时序超表创建跳过: {e}")

            cur.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (trade_date)").format(
                    sql.Identifier(f"idx_{self.stock_code}_trade_date"),
                    sql.Identifier(self.table_name),
                )
            )
            try:
                cur.execute(
                    sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} USING ivfflat (features_vector vector_cosine_ops) WITH (lists = 100)").format(
                        sql.Identifier(f"idx_{self.stock_code}_features"),
                        sql.Identifier(self.table_name),
                    )
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
            release_connection(conn)

    def get_latest_trade_date(self) -> Optional[datetime]:
        """获取数据库中最新交易日期"""
        db_logger.debug(f"[{self.stock_code}] 查询最新交易日期")
        conn = get_connection()
        cur = conn.cursor()

        try:
            cur.execute(sql.SQL("SELECT MAX(trade_date) FROM {}").format(sql.Identifier(self.table_name)))
            result = cur.fetchone()
            latest = result[0] if result and result[0] else None
            db_logger.debug(f"[{self.stock_code}] 最新交易日期: {latest}")
            return latest
        except psycopg2.errors.UndefinedTable:
            db_logger.debug(f"[{self.stock_code}] 表不存在")
            return None
        finally:
            cur.close()
            release_connection(conn)

    def check_data_exists(self, trade_date: datetime) -> bool:
        """检查指定交易日的数据是否存在"""
        db_logger.debug(f"[{self.stock_code}] 检查数据是否存在: {trade_date}")
        conn = get_connection()
        cur = conn.cursor()

        try:
            cur.execute(
                sql.SQL("SELECT 1 FROM {} WHERE trade_date = %s LIMIT 1").format(
                    sql.Identifier(self.table_name),
                ),
                (trade_date,),
            )

            exists = cur.fetchone() is not None
            db_logger.debug(f"[{self.stock_code}] 数据存在: {exists}")
        except psycopg2.errors.UndefinedTable:
            exists = False
        finally:
            cur.close()
            release_connection(conn)
        return exists

    def insert_daily_data(self, data: Dict[str, Any]):
        """插入单条日线数据"""
        conn = get_connection()
        conn.autocommit = False
        cur = conn.cursor()
        try:
            insert_sql = sql.SQL("""
        INSERT INTO {} (
            trade_date, trade_time,
            open, high, low, close, volume, amount,
            change_pct, change_amount, turnover_rate,
            pe_dynamic, pb, total_market_cap, circ_market_cap,
            main_flow, main_flow_ratio,
            day1_pred_high, day1_pred_low, day2_pred_high, day2_pred_low,
            trend
        ) VALUES (
            %(trade_date)s, %(trade_time)s,
            %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(amount)s,
            %(change_pct)s, %(change_amount)s, %(turnover_rate)s,
            %(pe_dynamic)s, %(pb)s, %(total_market_cap)s, %(circ_market_cap)s,
            %(main_flow)s, %(main_flow_ratio)s,
            %(day1_pred_high)s, %(day1_pred_low)s, %(day2_pred_high)s, %(day2_pred_low)s,
            %(trend)s
        ) ON CONFLICT (trade_date) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            amount = COALESCE(EXCLUDED.amount, {}.amount),
            change_pct = COALESCE(EXCLUDED.change_pct, {}.change_pct),
            change_amount = COALESCE(EXCLUDED.change_amount, {}.change_amount),
            turnover_rate = COALESCE(EXCLUDED.turnover_rate, {}.turnover_rate),
            pe_dynamic = COALESCE(EXCLUDED.pe_dynamic, {}.pe_dynamic),
            pb = COALESCE(EXCLUDED.pb, {}.pb),
            total_market_cap = COALESCE(EXCLUDED.total_market_cap, {}.total_market_cap),
            circ_market_cap = COALESCE(EXCLUDED.circ_market_cap, {}.circ_market_cap),
            main_flow = COALESCE(EXCLUDED.main_flow, {}.main_flow),
            main_flow_ratio = COALESCE(EXCLUDED.main_flow_ratio, {}.main_flow_ratio),
            day1_pred_high = COALESCE(EXCLUDED.day1_pred_high, {}.day1_pred_high),
            day1_pred_low = COALESCE(EXCLUDED.day1_pred_low, {}.day1_pred_low),
            day2_pred_high = COALESCE(EXCLUDED.day2_pred_high, {}.day2_pred_high),
            day2_pred_low = COALESCE(EXCLUDED.day2_pred_low, {}.day2_pred_low),
            trend = COALESCE(EXCLUDED.trend, {}.trend)
        """).format(*([sql.Identifier(self.table_name)] * 16))

            cur.execute(insert_sql, data)
            conn.commit()
        finally:
            cur.close()
            release_connection(conn)

    def batch_insert_daily_data(self, data_list: List[Dict[str, Any]]) -> tuple:
        """批量插入日线数据，返回 (新增数, 更新数)"""
        if not data_list:
            return (0, 0)

        conn = get_connection()
        conn.autocommit = False
        cur = conn.cursor()
        try:
            cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(self.table_name)))
            before_count = cur.fetchone()[0]

            db_logger.info(f"[{self.stock_code}] 批量插入 {len(data_list)} 条数据")

            insert_sql = sql.SQL("""
        INSERT INTO {} (
            trade_date, trade_time,
            open, high, low, close, volume, amount,
            change_pct, change_amount, turnover_rate,
            pe_dynamic, pb, total_market_cap, circ_market_cap,
            main_flow, main_flow_ratio,
            day1_pred_high, day1_pred_low, day2_pred_high, day2_pred_low,
            trend
        ) VALUES (
            %(trade_date)s, %(trade_time)s,
            %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(amount)s,
            %(change_pct)s, %(change_amount)s, %(turnover_rate)s,
            %(pe_dynamic)s, %(pb)s, %(total_market_cap)s, %(circ_market_cap)s,
            %(main_flow)s, %(main_flow_ratio)s,
            %(day1_pred_high)s, %(day1_pred_low)s, %(day2_pred_high)s, %(day2_pred_low)s,
            %(trend)s
        ) ON CONFLICT (trade_date) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            amount = COALESCE(EXCLUDED.amount, {}.amount),
            change_pct = COALESCE(EXCLUDED.change_pct, {}.change_pct),
            change_amount = COALESCE(EXCLUDED.change_amount, {}.change_amount),
            turnover_rate = COALESCE(EXCLUDED.turnover_rate, {}.turnover_rate),
            pe_dynamic = COALESCE(EXCLUDED.pe_dynamic, {}.pe_dynamic),
            pb = COALESCE(EXCLUDED.pb, {}.pb),
            total_market_cap = COALESCE(EXCLUDED.total_market_cap, {}.total_market_cap),
            circ_market_cap = COALESCE(EXCLUDED.circ_market_cap, {}.circ_market_cap),
            main_flow = COALESCE(EXCLUDED.main_flow, {}.main_flow),
            main_flow_ratio = COALESCE(EXCLUDED.main_flow_ratio, {}.main_flow_ratio),
            day1_pred_high = COALESCE(EXCLUDED.day1_pred_high, {}.day1_pred_high),
            day1_pred_low = COALESCE(EXCLUDED.day1_pred_low, {}.day1_pred_low),
            day2_pred_high = COALESCE(EXCLUDED.day2_pred_high, {}.day2_pred_high),
            day2_pred_low = COALESCE(EXCLUDED.day2_pred_low, {}.day2_pred_low),
            trend = COALESCE(EXCLUDED.trend, {}.trend)
        """).format(*([sql.Identifier(self.table_name)] * 16))

            cur.executemany(insert_sql, data_list)
            conn.commit()

            try:
                cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(self.table_name)))
                after_count = cur.fetchone()[0]
            except Exception as e:
                db_logger.warning(f"[{self.stock_code}] commit 后查询行数失败: {e}")
                after_count = before_count
        except Exception as e:
            db_logger.error(f"[{self.stock_code}] 批量插入失败: {e}")
            try:
                conn.rollback()
            except Exception:
                # 回滚失败时连接可能已失效，忽略后抛原始异常
                pass
            raise
        finally:
            cur.close()
            release_connection(conn)

        inserted = after_count - before_count
        updated = len(data_list) - inserted

        db_logger.info(
            f"[{self.stock_code}] 批量插入完成: 新增 {inserted} 条, 更新 {updated} 条"
        )

        return (inserted, updated)

    def batch_update_technical_indicators(
        self, history_df: pd.DataFrame, indicators: Dict
    ):
        """批量更新技术指标"""
        if history_df is None or history_df.empty:
            return

        db_logger.info(f"[{self.stock_code}] 批量更新技术指标...")

        macd_data = indicators.get("MACD", {})
        rsi_data = indicators.get("RSI", {})
        kdj_data = indicators.get("KDJ", {})
        ma_data = indicators.get("MA", {})
        boll_data = indicators.get("BOLL", {})

        conn = get_connection()
        conn.autocommit = False
        cur = conn.cursor()

        update_sql = sql.SQL("""
        UPDATE {} SET
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
        """).format(sql.Identifier(self.table_name))

        update_list = []

        for i, row in enumerate(history_df.itertuples()):
            trade_date = pd.to_datetime(getattr(row, '日期', row.Index))
            if isinstance(trade_date, pd.Timestamp):
                trade_date = trade_date.to_pydatetime()
            trade_date_only = (
                trade_date.date() if hasattr(trade_date, "date") else trade_date
            )

            ind_data = {"trade_date": trade_date_only}

            # 兼容新旧MACD返回格式
            macd_series = macd_data.get("series", {})
            if isinstance(macd_series, dict):
                macd_dif = macd_series.get("DIF")
                macd_dea = macd_series.get("DEA")
                macd_hist = macd_series.get("MACD")
            else:
                macd_dif = macd_data.get("DIF")
                macd_dea = macd_data.get("DEA")
                macd_hist = macd_data.get("MACD")
            if isinstance(macd_dif, (list, pd.Series)) and i < len(macd_dif):
                macd_dif = (
                    macd_dif.iloc[i] if hasattr(macd_dif, "iloc") else macd_dif[i]
                )
                macd_dea = (
                    macd_dea.iloc[i] if hasattr(macd_dea, "iloc") else macd_dea[i]
                )
                macd_hist = (
                    macd_hist.iloc[i] if hasattr(macd_hist, "iloc") else macd_hist[i]
                )
            ind_data["macd_dif"] = to_python_type(macd_dif)
            ind_data["macd_dea"] = to_python_type(macd_dea)
            ind_data["macd_hist"] = to_python_type(macd_hist)

            rsi6_series = rsi_data.get("RSI(6)", {}).get("series")
            rsi12_series = rsi_data.get("RSI(12)", {}).get("series")
            rsi24_series = rsi_data.get("RSI(24)", {}).get("series")
            if rsi6_series is not None and i < len(rsi6_series):
                rsi6 = rsi6_series.iloc[i] if hasattr(rsi6_series, "iloc") else rsi6_series[i]
            else:
                rsi6 = None
            if rsi12_series is not None and i < len(rsi12_series):
                rsi12 = rsi12_series.iloc[i] if hasattr(rsi12_series, "iloc") else rsi12_series[i]
            else:
                rsi12 = None
            if rsi24_series is not None and i < len(rsi24_series):
                rsi24 = rsi24_series.iloc[i] if hasattr(rsi24_series, "iloc") else rsi24_series[i]
            else:
                rsi24 = None
            ind_data["rsi_6"] = to_python_type(rsi6)
            ind_data["rsi_12"] = to_python_type(rsi12)
            ind_data["rsi_24"] = to_python_type(rsi24)

            kdj_series = kdj_data.get("series", {})
            kdj_k = kdj_series.get("K") if isinstance(kdj_series, dict) else kdj_data.get("K")
            kdj_d = kdj_series.get("D") if isinstance(kdj_series, dict) else kdj_data.get("D")
            kdj_j = kdj_series.get("J") if isinstance(kdj_series, dict) else kdj_data.get("J")
            if isinstance(kdj_k, pd.Series) and i < len(kdj_k):
                kdj_k = kdj_k.iloc[i]
                kdj_d = kdj_d.iloc[i] if kdj_d is not None else None
                kdj_j = kdj_j.iloc[i] if kdj_j is not None else None
            ind_data["k"] = to_python_type(kdj_k)
            ind_data["d"] = to_python_type(kdj_d)
            ind_data["j"] = to_python_type(kdj_j)

            ma5_series = ma_data.get("MA5", {}).get("series") if isinstance(ma_data.get("MA5"), dict) else ma_data.get("MA5")
            ma10_series = ma_data.get("MA10", {}).get("series") if isinstance(ma_data.get("MA10"), dict) else ma_data.get("MA10")
            ma20_series = ma_data.get("MA20", {}).get("series") if isinstance(ma_data.get("MA20"), dict) else ma_data.get("MA20")
            ma60_series = ma_data.get("MA60", {}).get("series") if isinstance(ma_data.get("MA60"), dict) else ma_data.get("MA60")
            if isinstance(ma5_series, pd.Series) and i < len(ma5_series):
                ma5 = ma5_series.iloc[i]
                ma10 = ma10_series.iloc[i] if ma10_series is not None else None
                ma20 = ma20_series.iloc[i] if ma20_series is not None else None
                ma60 = ma60_series.iloc[i] if ma60_series is not None else None
            else:
                ma5 = ma10 = ma20 = ma60 = None
            ind_data["ma5"] = to_python_type(ma5)
            ind_data["ma10"] = to_python_type(ma10)
            ind_data["ma20"] = to_python_type(ma20)
            ind_data["ma60"] = to_python_type(ma60)

            # 兼容新旧BOLL返回格式
            boll_series = boll_data.get("series", {})
            if isinstance(boll_series, dict):
                boll_upper = boll_series.get("upper")
                boll_middle = boll_series.get("middle")
                boll_lower = boll_series.get("lower")
            else:
                boll_upper = boll_data.get("upper")
                boll_middle = boll_data.get("middle")
                boll_lower = boll_data.get("lower")
            if isinstance(boll_upper, (list, pd.Series)) and i < len(boll_upper):
                boll_upper = (
                    boll_upper.iloc[i] if hasattr(boll_upper, "iloc") else boll_upper[i]
                )
                boll_middle = (
                    boll_middle.iloc[i]
                    if hasattr(boll_middle, "iloc")
                    else boll_middle[i]
                )
                boll_lower = (
                    boll_lower.iloc[i] if hasattr(boll_lower, "iloc") else boll_lower[i]
                )
            ind_data["boll_upper"] = to_python_type(boll_upper)
            ind_data["boll_middle"] = to_python_type(boll_middle)
            ind_data["boll_lower"] = to_python_type(boll_lower)

            update_list.append(ind_data)

        try:
            if update_list:
                cur.executemany(update_sql, update_list)
                conn.commit()
        except Exception as e:
            db_logger.warning(f"[{self.stock_code}] 技术指标批量更新失败: {e}")
            try:
                conn.rollback()
            except Exception:
                # 回滚失败时连接可能已失效，忽略后继续关闭游标
                pass
        finally:
            cur.close()
            release_connection(conn)
        db_logger.info(f"[{self.stock_code}] 技术指标批量更新完成")

    def has_null_fields(self) -> bool:
        """检查表中是否有重要字段为空的记录"""
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                sql.SQL("SELECT COUNT(*) FROM {} WHERE change_pct IS NULL OR amount IS NULL OR turnover_rate IS NULL").format(
                    sql.Identifier(self.table_name),
                )
            )
            null_count = cur.fetchone()[0]
            if null_count > 0:
                return True
            cur.execute(
                sql.SQL("SELECT COUNT(DISTINCT total_market_cap) FROM {} WHERE total_market_cap IS NOT NULL").format(
                    sql.Identifier(self.table_name),
                )
            )
            distinct_cap = cur.fetchone()[0]
            if distinct_cap <= 1:
                return True
            return False
        except psycopg2.errors.UndefinedTable:
            return False
        finally:
            cur.close()
            release_connection(conn)

    def get_historical_data(self, days: int = None) -> pd.DataFrame:
        conn = get_connection()
        try:
            base_query = sql.SQL("""
        SELECT 
            trade_date, open, high, low, close, volume, amount,
            change_pct, turnover_rate,
            macd_dif, macd_dea, macd_hist,
            rsi_6, rsi_12, rsi_24,
            k, d, j,
            ma5, ma10, ma20, ma60,
            boll_upper, boll_middle, boll_lower,
            main_flow, main_flow_ratio
        FROM {}
        ORDER BY trade_date DESC
        """).format(sql.Identifier(self.table_name))

            if days is not None and days > 0:
                query_sql = sql.SQL("{} LIMIT {}").format(base_query, sql.Literal(int(days)))
            else:
                query_sql = base_query

            query_str = query_sql.as_string(conn)
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*pandas only supports SQLAlchemy.*", category=UserWarning)
                df = pd.read_sql(query_str, conn)
        finally:
            release_connection(conn)

        column_mapping = {
            "trade_date": "日期",
            "open": "开盘",
            "high": "最高",
            "low": "最低",
            "close": "收盘",
            "volume": "成交量",
            "amount": "成交额",
            "change_pct": "涨跌幅",
            "turnover_rate": "换手率",
            "macd_dif": "DIF",
            "macd_dea": "DEA",
            "macd_hist": "MACD",
            "rsi_6": "RSI6",
            "rsi_12": "RSI12",
            "rsi_24": "RSI24",
            "k": "K",
            "d": "D",
            "j": "J",
            "ma5": "MA5",
            "ma10": "MA10",
            "ma20": "MA20",
            "ma60": "MA60",
            "boll_upper": "上轨",
            "boll_middle": "中轨",
            "boll_lower": "下轨",
            "main_flow": "主力净流入",
            "main_flow_ratio": "主力净流入占比",
        }

        df = df.rename(columns=column_mapping)
        df.index = df["日期"]
        df.index.name = "日期"
        df = df.drop(columns=["日期"])

        # 确保按日期升序排列（技术指标计算依赖时间序列顺序）
        df = df.sort_index(ascending=True)

        return df

    def _ensure_indicator_states_table(self):
        conn = get_connection()
        conn.autocommit = True
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'indicator_states'
            """)
            if not cur.fetchone():
                cur.execute("""
                    CREATE TABLE indicator_states (
                        id SERIAL PRIMARY KEY,
                        stock_code VARCHAR(10) NOT NULL,
                        indicator_name VARCHAR(50) NOT NULL,
                        state_json JSONB NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_indicator_states_stock
                    ON indicator_states (stock_code, indicator_name)
                """)
                db_logger.info("indicator_states表创建成功")
        finally:
            cur.close()
            release_connection(conn)

    def save_indicator_states(self, states: Dict):
        self._ensure_indicator_states_table()
        conn = get_connection()
        conn.autocommit = False
        cur = conn.cursor()
        try:
            for indicator_name, state in states.items():
                state_json = json.dumps(state, default=str)
                cur.execute(
                    """
                    INSERT INTO indicator_states (stock_code, indicator_name, state_json, updated_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (stock_code, indicator_name) DO UPDATE SET
                        state_json = EXCLUDED.state_json,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (self.stock_code, indicator_name, state_json),
                )
            conn.commit()
            db_logger.info(f"[{self.stock_code}] 指标状态已保存: {list(states.keys())}")
        finally:
            cur.close()
            release_connection(conn)

    def load_indicator_states(self) -> Dict:
        self._ensure_indicator_states_table()
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT indicator_name, state_json
                FROM indicator_states
                WHERE stock_code = %s
                """,
                (self.stock_code,),
            )
            rows = cur.fetchall()
            states = {}
            for row in rows:
                state_data = row[1] if isinstance(row[1], dict) else json.loads(row[1]) if row[1] else {}
                states[row[0]] = state_data
            db_logger.debug(f"[{self.stock_code}] 加载指标状态: {list(states.keys())}")
            return states
        finally:
            cur.close()
            release_connection(conn)


def _enrich_history_df(df: pd.DataFrame, stock_code: str = "") -> pd.DataFrame:
    """补充历史DataFrame中缺失的衍生字段

    多重保障机制：
    1. 从收盘价计算涨跌幅和涨跌额
    2. 从成交量×均价估算成交额
    3. 从baostock补充PE/PB/换手率（如果缺失）
    """
    if df is None or df.empty or "收盘" not in df.columns:
        return df

    df = df.copy()

    close = pd.to_numeric(df["收盘"], errors="coerce")

    if "涨跌幅" not in df.columns or df["涨跌幅"].isna().all():
        prev_close = close.shift(1)
        mask = prev_close.notna() & (prev_close != 0)
        df["涨跌幅"] = np.nan
        df.loc[mask, "涨跌幅"] = ((close[mask] - prev_close[mask]) / prev_close[mask] * 100).round(4)
    elif df["涨跌幅"].isna().any():
        prev_close = close.shift(1)
        mask = df["涨跌幅"].isna() & prev_close.notna() & (prev_close != 0)
        df.loc[mask, "涨跌幅"] = ((close[mask] - prev_close[mask]) / prev_close[mask] * 100).round(4)

    if "涨跌额" not in df.columns or df["涨跌额"].isna().all():
        prev_close = close.shift(1)
        mask = prev_close.notna()
        df["涨跌额"] = np.nan
        df.loc[mask, "涨跌额"] = (close[mask] - prev_close[mask]).round(2)
    elif df["涨跌额"].isna().any():
        prev_close = close.shift(1)
        mask = df["涨跌额"].isna() & prev_close.notna()
        df.loc[mask, "涨跌额"] = (close[mask] - prev_close[mask]).round(2)

    if "成交额" not in df.columns or df["成交额"].isna().all():
        if "成交量" in df.columns and "最高" in df.columns and "最低" in df.columns:
            vol = pd.to_numeric(df["成交量"], errors="coerce")
            high = pd.to_numeric(df["最高"], errors="coerce")
            low = pd.to_numeric(df["最低"], errors="coerce")
            avg_price = (high + low) / 2
            df["成交额"] = (vol * avg_price * 100).round(2)
    elif df["成交额"].isna().any():
        if "成交量" in df.columns and "最高" in df.columns and "最低" in df.columns:
            vol = pd.to_numeric(df["成交量"], errors="coerce")
            high = pd.to_numeric(df["最高"], errors="coerce")
            low = pd.to_numeric(df["最低"], errors="coerce")
            avg_price = (high + low) / 2
            mask = df["成交额"].isna()
            df.loc[mask, "成交额"] = (vol[mask] * avg_price[mask] * 100).round(2)

    needs_pe = "市盈率-动态" not in df.columns or df["市盈率-动态"].isna().all() if "市盈率-动态" in df.columns else True
    needs_pb = "市净率" not in df.columns or df["市净率"].isna().all() if "市净率" in df.columns else True
    needs_turn = "换手率" not in df.columns or df["换手率"].isna().all() if "换手率" in df.columns else True

    if needs_pe or needs_pb or needs_turn:
        df = _supplement_from_baostock(df, stock_code)

    return df


def _supplement_from_baostock(df: pd.DataFrame, stock_code: str = "") -> pd.DataFrame:
    """从baostock补充PE/PB/换手率/成交额等字段，并从收盘价反推历史市值"""
    try:
        import baostock as bs
        from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
        from scripts.core.data_fetcher import _baostock_lock

        if df.empty or "日期" not in df.columns or not stock_code:
            return df

        market = "sh" if stock_code.startswith(("6", "5", "9")) else "sz"
        bs_code = f"{market}.{stock_code}"

        dates = pd.to_datetime(df["日期"], errors="coerce")
        start_date = dates.min().strftime("%Y-%m-%d") if dates.notna().any() else "20200101"
        end_date = dates.max().strftime("%Y-%m-%d") if dates.notna().any() else "20991231"

        def _baostock_fetch():
            with _baostock_lock:
                lg = bs.login()
                if lg.error_code != "0":
                    raise RuntimeError(
                        f"baostock login failed: {lg.error_code} {lg.error_msg}"
                    )
                try:
                    rs = bs.query_history_k_data_plus(
                        bs_code,
                        "date,amount,turn,peTTM,pbMRQ",
                        start_date=start_date,
                        end_date=end_date,
                        frequency="d",
                        adjustflag="2",
                    )
                    data = []
                    while rs.error_code == "0" and rs.next():
                        data.append(rs.get_row_data())
                finally:
                    bs.logout()
            return data

        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(_baostock_fetch)
            done, not_done = futures_wait([future], timeout=20)
            if not_done:
                db_logger.warning(f"[{stock_code}] baostock查询超时(20s)，跳过补充数据")
                return df
            bs_data = future.result()
        finally:
            executor.shutdown(wait=False)

        if not bs_data:
            return df

        bs_df = pd.DataFrame(bs_data, columns=["日期", "成交额_bs", "换手率_bs", "市盈率_bs", "市净率_bs"])
        bs_df["日期"] = pd.to_datetime(bs_df["日期"], errors="coerce")
        bs_df["成交额_bs"] = pd.to_numeric(bs_df["成交额_bs"], errors="coerce")
        bs_df["换手率_bs"] = pd.to_numeric(bs_df["换手率_bs"], errors="coerce")
        bs_df["市盈率_bs"] = pd.to_numeric(bs_df["市盈率_bs"], errors="coerce")
        bs_df["市净率_bs"] = pd.to_numeric(bs_df["市净率_bs"], errors="coerce")

        df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
        df = df.merge(bs_df, on="日期", how="left")

        if "成交额" not in df.columns or df["成交额"].isna().all():
            df["成交额"] = df["成交额_bs"]
        else:
            mask = df["成交额_bs"].notna()
            df.loc[mask, "成交额"] = df.loc[mask, "成交额_bs"]

        if "换手率" not in df.columns or df["换手率"].isna().all():
            df["换手率"] = df["换手率_bs"]
        elif df["换手率"].isna().any():
            mask = df["换手率"].isna()
            df.loc[mask, "换手率"] = df.loc[mask, "换手率_bs"]

        if "市盈率-动态" not in df.columns or df["市盈率-动态"].isna().all():
            df["市盈率-动态"] = df["市盈率_bs"]
        elif df["市盈率-动态"].isna().any():
            mask = df["市盈率-动态"].isna()
            df.loc[mask, "市盈率-动态"] = df.loc[mask, "市盈率_bs"]

        if "市净率" not in df.columns or df["市净率"].isna().all():
            df["市净率"] = df["市净率_bs"]
        elif df["市净率"].isna().any():
            mask = df["市净率"].isna()
            df.loc[mask, "市净率"] = df.loc[mask, "市净率_bs"]

        df = df.drop(columns=["成交额_bs", "换手率_bs", "市盈率_bs", "市净率_bs"], errors="ignore")

    except Exception as e:
        db_logger.warning(f"baostock补充数据失败: {e}")

    return df


def _calc_market_cap(df: pd.DataFrame, stock_info: Dict) -> pd.DataFrame:
    """从收盘价变化比例反推历史总市值和流通市值

    原理：总市值 = 收盘价 × 总股本，总股本短期内不变
    所以：历史市值 = 最新市值 × (历史收盘价 / 最新收盘价)
    """
    if df is None or df.empty or "收盘" not in df.columns:
        return df

    latest_mkt_cap = stock_info.get("总市值")
    latest_circ_cap = stock_info.get("流通市值")

    if not latest_mkt_cap and not latest_circ_cap:
        return df

    df = df.copy()
    close = pd.to_numeric(df["收盘"], errors="coerce")
    last_close = close.iloc[-1] if close.notna().any() else None

    if last_close and last_close > 0:
        ratio = close / last_close
        if latest_mkt_cap:
            latest_mkt_cap = float(latest_mkt_cap)
            df["总市值"] = (latest_mkt_cap * ratio).round(2)
        if latest_circ_cap:
            latest_circ_cap = float(latest_circ_cap)
            df["流通市值"] = (latest_circ_cap * ratio).round(2)

    return df


def ensure_stock_table(stock_code: str):
    """确保股票数据表存在"""
    manager = StockDataManager(stock_code)
    manager.create_table()


def _check_data_cache(
    stock_code: str, force_refresh: bool, days: int, manager: StockDataManager
) -> Optional[pd.DataFrame]:
    """检查本地/内存缓存，返回缓存的 DataFrame 或 None"""
    if force_refresh:
        return None

    try:
        latest_date = manager.get_latest_trade_date()
        if latest_date is None:
            return None

        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                sql.SQL("SELECT MAX(created_at) FROM {}").format(
                    sql.Identifier(manager.table_name),
                )
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return None

            age_seconds = (datetime.now() - row[0]).total_seconds()

            # 判断DB数据是否已是最新（最新日期为今天或昨天）
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)
            latest_date_only = (
                latest_date.date()
                if hasattr(latest_date, "date") and not isinstance(latest_date, date_type)
                else latest_date
            )
            is_data_up_to_date = latest_date_only >= yesterday

            df = manager.get_historical_data()
            if df is None or df.empty or len(df) < 5:
                return None

            if is_data_up_to_date:
                db_logger.info(
                    f"[{stock_code}] 数据已是最新 (最新日期={latest_date_only}, {len(df)} 条, 缓存年龄{age_seconds:.0f}秒)"
                )
                return df

            if age_seconds < 300:
                db_logger.info(
                    f"[{stock_code}] 使用数据库缓存 ({len(df)} 条, 缓存年龄{age_seconds:.0f}秒)"
                )
                return df

            db_logger.info(f"[{stock_code}] 缓存数据不完整，重新获取")
        finally:
            cur.close()
            release_connection(conn)
    except Exception as e:
        db_logger.warning(f"[{stock_code}] 数据库缓存检查失败，回退到API: {e}")

    return None


def _fetch_data_from_sources(stock_code: str, days: int) -> Dict[str, Any]:
    """按优先级从数据库、baostock 等数据源获取数据"""
    from scripts.core.data_fetcher import DataFetcher
    from scripts.technical_indicators import calculate_all_indicators

    fetcher = DataFetcher({})
    stock_info = fetcher.fetch_stock_info(stock_code)
    fund_flow = fetcher.fetch_fund_flow(stock_code)
    history_df = fetcher.fetch_history_data(stock_code, days)

    if history_df is None or history_df.empty:
        raise ValueError("无法获取历史数据")

    history_df = _enrich_history_df(history_df, stock_code)
    history_df = _calc_market_cap(history_df, stock_info)

    indicators = calculate_all_indicators(history_df)

    return {
        "stock_info": stock_info,
        "fund_flow": fund_flow,
        "history_df": history_df,
        "indicators": indicators,
    }


def _build_daily_data_list(
    history_df: pd.DataFrame,
    stock_code: str,
    fund_flow: Dict[str, Any],
    stock_info: Dict[str, Any],
    manager: StockDataManager,
    force_refresh: bool,
) -> List[Dict[str, Any]]:
    """将 DataFrame 转换为 data_list 结构"""
    latest_date = manager.get_latest_trade_date()
    is_first_time = latest_date is None

    if is_first_time or force_refresh:
        new_data_df = history_df
    else:
        latest_date_only = (
            latest_date.date()
            if hasattr(latest_date, "date") and not isinstance(latest_date, date_type)
            else latest_date
        )
        cutoff_ts = pd.Timestamp(latest_date_only)
        new_data_df = history_df[pd.to_datetime(history_df["日期"]) > cutoff_ts]

    data_list: List[Dict[str, Any]] = []
    if new_data_df.empty:
        return data_list

    for i, row in enumerate(new_data_df.itertuples()):
        trade_date = pd.to_datetime(getattr(row, '日期', row.Index))
        if isinstance(trade_date, pd.Timestamp):
            trade_date = trade_date.to_pydatetime()
        trade_date_only = (
            trade_date.date() if hasattr(trade_date, "date") else trade_date
        )
        is_latest_row = i == len(new_data_df) - 1

        daily_data = {
            "trade_date": trade_date_only,
            "trade_time": trade_date,
            "open": to_python_type(getattr(row, '开盘', None)),
            "high": to_python_type(getattr(row, '最高', None)),
            "low": to_python_type(getattr(row, '最低', None)),
            "close": to_python_type(getattr(row, '收盘', None)),
            "volume": int(getattr(row, '成交量', 0)) if pd.notna(getattr(row, '成交量', None)) else 0,
            "amount": to_python_type(getattr(row, '成交额', None)),
            "change_pct": to_python_type(getattr(row, '涨跌幅', None)),
            "change_amount": to_python_type(getattr(row, '涨跌额', None)),
            "turnover_rate": to_python_type(getattr(row, '换手率', None)) or (to_python_type(stock_info.get("换手率")) if is_latest_row else None),
            "pe_dynamic": to_python_type(getattr(row, '市盈率_动态', None)) or (to_python_type(stock_info.get("市盈率-动态")) if is_latest_row else None),
            "pb": to_python_type(getattr(row, '市净率', None)) or (to_python_type(stock_info.get("市净率")) if is_latest_row else None),
            "total_market_cap": to_python_type(getattr(row, '总市值', None)),
            "circ_market_cap": to_python_type(getattr(row, '流通市值', None)),
            "main_flow": to_python_type(fund_flow.get("主力净流入")) if is_latest_row else None,
            "main_flow_ratio": to_python_type(fund_flow.get("主力净流入占比")) if is_latest_row else None,
            "day1_pred_high": to_python_type(getattr(row, 'day1_pred_high', None)),
            "day1_pred_low": to_python_type(getattr(row, 'day1_pred_low', None)),
            "day2_pred_high": to_python_type(getattr(row, 'day2_pred_high', None)),
            "day2_pred_low": to_python_type(getattr(row, 'day2_pred_low', None)),
            "trend": to_python_type(getattr(row, 'trend', None)),
        }
        data_list.append(daily_data)

    return data_list


def _batch_save_daily_data(
    data_list: List[Dict[str, Any]],
    stock_code: str,
    manager: StockDataManager,
    history_df: pd.DataFrame,
    indicators: Any,
) -> None:
    """批量插入/更新数据库"""
    if not data_list:
        return

    db_logger.info(f"[{stock_code}] 批量处理 {len(data_list)} 条数据...")
    manager.batch_insert_daily_data(data_list)
    manager.batch_update_technical_indicators(history_df, indicators)
    db_logger.info(f"[{stock_code}] 数据已保存到数据库")


def get_or_fetch_stock_data(
    stock_code: str, force_refresh: bool = False, days: int = 60
) -> Dict[str, Any]:
    """
    获取股票数据：优先使用数据库缓存，缓存过期或不存在时从API获取并存储

    Args:
        stock_code: 股票代码
        force_refresh: 是否强制刷新数据
        days: 获取历史数据天数

    Returns:
        dict: 包含数据和来源信息
    """
    db_logger.info("=" * 50)
    db_logger.info(
        f"[{stock_code}] 开始获取数据 (force_refresh={force_refresh}, days={days})"
    )

    manager = StockDataManager(stock_code)

    try:
        manager.create_table()
    except Exception as e:
        db_logger.error(f"[{stock_code}] 创建表失败: {e}")
        return {"source": "error", "error": str(e)}

    cached_df = _check_data_cache(stock_code, force_refresh, days, manager)
    if cached_df is not None:
        return {
            "source": "database",
            "stock_info": {},
            "fund_flow": {},
            "history_df": cached_df,
        }

    try:
        fetched = _fetch_data_from_sources(stock_code, days)
        stock_info = fetched["stock_info"]
        fund_flow = fetched["fund_flow"]
        history_df = fetched["history_df"]
        indicators = fetched["indicators"]

        data_list = _build_daily_data_list(
            history_df, stock_code, fund_flow, stock_info, manager, force_refresh
        )
        _batch_save_daily_data(data_list, stock_code, manager, history_df, indicators)

        db_logger.info(f"[{stock_code}] 数据获取完成")

        return {
            "source": "api",
            "stock_info": stock_info,
            "fund_flow": fund_flow,
            "history_df": history_df,
            "indicators": indicators,
        }

    except Exception as e:
        db_logger.error(f"[{stock_code}] 从API获取数据失败: {e}")
        import traceback

        db_logger.error(traceback.format_exc())

        try:
            df = manager.get_historical_data()
            if df is not None and not df.empty:
                db_logger.info(f"[{stock_code}] API失败，回退使用数据库数据 ({len(df)} 条)")
                return {
                    "source": "database_fallback",
                    "data_quality": "low",
                    "history_df": df,
                    "stock_info": {},
                    "fund_flow": {},
                }
        except Exception as fallback_err:
            db_logger.error(f"[{stock_code}] 数据库回退也失败: {fallback_err}")

        return {"source": "error", "error": str(e)}

def _ensure_ml_models_table():
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'ml_models'
        """)
        if not cur.fetchone():
            cur.execute("""
                CREATE TABLE ml_models (
                    id SERIAL PRIMARY KEY,
                    stock_code VARCHAR(10) NOT NULL,
                    model_path TEXT NOT NULL,
                    metrics JSONB,
                    params JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ml_models_stock_code
                ON ml_models (stock_code, created_at DESC)
            """)
            db_logger.info("ml_models表创建成功")
    finally:
        cur.close()
        release_connection(conn)


def save_model_record(stock_code: str, model_path: str, metrics: dict, params: dict):
    _ensure_ml_models_table()

    metrics_clean = {}
    for k, v in metrics.items():
        if k == "feature_importance":
            continue
        try:
            metrics_clean[k] = to_python_type(v)
        except (TypeError, ValueError):
            metrics_clean[k] = str(v)

    params_clean = {}
    for k, v in params.items():
        try:
            params_clean[k] = to_python_type(v)
        except (TypeError, ValueError):
            params_clean[k] = str(v)

    conn = get_connection()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO ml_models (stock_code, model_path, metrics, params)
            VALUES (%s, %s, %s, %s)
            """,
            (stock_code.zfill(6), model_path, json.dumps(metrics_clean), json.dumps(params_clean)),
        )
        conn.commit()
        db_logger.info(f"[{stock_code}] 模型记录已保存")
    finally:
        cur.close()
        release_connection(conn)


def load_model_record(stock_code: str) -> dict:
    _ensure_ml_models_table()

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT model_path, metrics, params, created_at
            FROM ml_models
            WHERE stock_code = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (stock_code.zfill(6),),
        )
        row = cur.fetchone()
        if row:
            return {
                "model_path": row[0],
                "metrics": row[1] if isinstance(row[1], dict) else json.loads(row[1]) if row[1] else {},
                "params": row[2] if isinstance(row[2], dict) else json.loads(row[2]) if row[2] else {},
                "created_at": row[3],
            }
        return {}
    finally:
        cur.close()
        release_connection(conn)
