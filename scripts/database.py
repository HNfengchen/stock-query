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
        if self.table_exists():
            db_logger.info(f"[{self.stock_code}] 表 {self.table_name} 已存在，跳过创建")
            return

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

            cur.execute(f"""
                ALTER TABLE {self.table_name} 
                ADD CONSTRAINT {self.table_name}_trade_date_key UNIQUE (trade_date)
            """)
            db_logger.info(f"[{self.stock_code}] trade_date唯一约束添加完成")
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
        """插入单条日线数据"""
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
        ) ON CONFLICT (trade_date) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            amount = EXCLUDED.amount
        """

        cur.execute(insert_sql, data)
        conn.commit()
        cur.close()
        conn.close()

    def batch_insert_daily_data(self, data_list: List[Dict[str, Any]]) -> tuple:
        """批量插入日线数据，返回 (新增数, 更新数)"""
        if not data_list:
            return (0, 0)

        conn = get_connection()
        cur = conn.cursor()

        cur.execute(f"SELECT COUNT(*) FROM {self.table_name}")
        before_count = cur.fetchone()[0]

        db_logger.info(f"[{self.stock_code}] 批量插入 {len(data_list)} 条数据")

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
        ) ON CONFLICT (trade_date) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            amount = EXCLUDED.amount
        """

        cur.executemany(insert_sql, data_list)
        conn.commit()

        cur.execute(f"SELECT COUNT(*) FROM {self.table_name}")
        after_count = cur.fetchone()[0]

        cur.close()
        conn.close()

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

        update_list = []

        for i, (idx, row) in enumerate(history_df.iterrows()):
            trade_date = pd.to_datetime(row.get("日期", idx))
            if isinstance(trade_date, pd.Timestamp):
                trade_date = trade_date.to_pydatetime()
            trade_date_only = (
                trade_date.date() if hasattr(trade_date, "date") else trade_date
            )

            ind_data = {"trade_date": trade_date_only}

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

            rsi6 = rsi_data.get("RSI(6)", {}).get("value")
            rsi12 = rsi_data.get("RSI(12)", {}).get("value")
            rsi24 = rsi_data.get("RSI(24)", {}).get("value")
            if isinstance(rsi6, (list, pd.Series)) and i < len(rsi6):
                rsi6 = rsi6.iloc[i] if hasattr(rsi6, "iloc") else rsi6[i]
                rsi12 = rsi12.iloc[i] if hasattr(rsi12, "iloc") else rsi12[i]
                rsi24 = rsi24.iloc[i] if hasattr(rsi24, "iloc") else rsi24[i]
            ind_data["rsi_6"] = to_python_type(rsi6)
            ind_data["rsi_12"] = to_python_type(rsi12)
            ind_data["rsi_24"] = to_python_type(rsi24)

            kdj_k = kdj_data.get("K")
            kdj_d = kdj_data.get("D")
            kdj_j = kdj_data.get("J")
            if isinstance(kdj_k, (list, pd.Series)) and i < len(kdj_k):
                kdj_k = kdj_k.iloc[i] if hasattr(kdj_k, "iloc") else kdj_k[i]
                kdj_d = kdj_d.iloc[i] if hasattr(kdj_d, "iloc") else kdj_d[i]
                kdj_j = kdj_j.iloc[i] if hasattr(kdj_j, "iloc") else kdj_j[i]
            ind_data["k"] = to_python_type(kdj_k)
            ind_data["d"] = to_python_type(kdj_d)
            ind_data["j"] = to_python_type(kdj_j)

            ma5 = ma_data.get("MA5")
            ma10 = ma_data.get("MA10")
            ma20 = ma_data.get("MA20")
            ma60 = ma_data.get("MA60")
            if isinstance(ma5, (list, pd.Series)) and i < len(ma5):
                ma5 = ma5.iloc[i] if hasattr(ma5, "iloc") else ma5[i]
                ma10 = ma10.iloc[i] if hasattr(ma10, "iloc") else ma10[i]
                ma20 = ma20.iloc[i] if hasattr(ma20, "iloc") else ma20[i]
                ma60 = ma60.iloc[i] if hasattr(ma60, "iloc") else ma60[i]
            ind_data["ma5"] = to_python_type(ma5)
            ind_data["ma10"] = to_python_type(ma10)
            ind_data["ma20"] = to_python_type(ma20)
            ind_data["ma60"] = to_python_type(ma60)

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

        if update_list:
            cur.executemany(update_sql, update_list)
            conn.commit()

        cur.close()
        conn.close()
        db_logger.info(f"[{self.stock_code}] 技术指标批量更新完成")

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

        return df


def ensure_stock_table(stock_code: str):
    """确保股票数据表存在"""
    manager = StockDataManager(stock_code)
    manager.create_table()


def get_or_fetch_stock_data(
    stock_code: str, force_refresh: bool = False, days: int = 60
) -> Dict[str, Any]:
    """
    获取股票数据：
    1. 首次运行（表为空）：获取所有历史数据并存储
    2. 后续运行：检查最新日期，补充缺失数据

    使用批量操作提高效率

    Args:
        stock_code: 股票代码
        force_refresh: 是否强制刷新数据
        days: 获取历史数据天数

    Returns:
        dict: 包含数据和来源信息
    """
    from . import stock_query

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

    try:
        from .stock_query import get_stock_info, get_fund_flow, get_history_data
        from .technical_indicators import calculate_all_indicators

        db_logger.info(f"[{stock_code}] 正在从API获取数据...")
        stock_info = get_stock_info(stock_code)
        fund_flow = get_fund_flow(stock_code)
        history_df = get_history_data(stock_code, days=days)

        if history_df is None or history_df.empty:
            db_logger.warning(f"[{stock_code}] 无法获取历史数据")
            return {"source": "error", "error": "无法获取历史数据"}

        db_logger.info(f"[{stock_code}] 计算技术指标...")
        indicators = calculate_all_indicators(history_df)

        db_logger.info(f"[{stock_code}] 获取到 {len(history_df)} 条历史数据")

        latest_date = manager.get_latest_trade_date()
        today = datetime.now().date()

        api_latest_date = None
        if not history_df.empty:
            date_col = history_df.get("日期")
            if date_col is not None and len(date_col) > 0:
                last_date = date_col.iloc[-1]
                if isinstance(last_date, str):
                    api_latest_date = pd.to_datetime(last_date).date()
                else:
                    api_latest_date = last_date
                db_logger.info(f"[{stock_code}] API最新日期: {api_latest_date}")

        db_logger.info(f"[{stock_code}] 数据库最新日期: {latest_date}, 今天: {today}")

        is_first_time = latest_date is None

        need_insert = is_first_time or force_refresh

        if not need_insert and api_latest_date and latest_date:
            latest_date_only = (
                latest_date.date() if hasattr(latest_date, "date") else latest_date
            )
            if api_latest_date > latest_date_only:
                db_logger.info(f"[{stock_code}] API有新增数据，需要更新")
                need_insert = True
            else:
                db_logger.info(f"[{stock_code}] API数据不新于数据库，跳过")
                df = manager.get_historical_data(days)
                indicators = None
                return {
                    "source": "database",
                    "stock_info": stock_info,
                    "fund_flow": fund_flow,
                    "history_df": df,
                    "indicators": None,
                }

        if need_insert:
            if is_first_time:
                db_logger.info(
                    f"[{stock_code}] 首次运行，将存入所有 {len(history_df)} 条历史数据"
                )
                new_data_df = history_df
            elif force_refresh:
                db_logger.info(
                    f"[{stock_code}] 强制刷新，更新所有 {len(history_df)} 条数据"
                )
                new_data_df = history_df
            else:
                db_logger.info(f"[{stock_code}] 已有数据，最新日期: {latest_date}")
                latest_date_only = (
                    latest_date.date() if hasattr(latest_date, "date") else latest_date
                )
                new_data_df = history_df[history_df["日期"] > str(latest_date_only)]
                db_logger.info(f"[{stock_code}] 需要新增 {len(new_data_df)} 条数据")

            if is_first_time:
                db_logger.info(f"[{stock_code}] 计算全部技术指标...")
                indicators = calculate_all_indicators(history_df)
            elif not new_data_df.empty:
                db_logger.info(
                    f"[{stock_code}] 计算新增数据的技术指标（使用完整历史数据）..."
                )
                indicators = calculate_all_indicators(history_df)
            else:
                indicators = {}

            if not new_data_df.empty:
                db_logger.info(
                    f"[{stock_code}] 准备插入 {len(new_data_df)} 条新数据..."
                )

                data_list = []

                for i, (idx, row) in enumerate(new_data_df.iterrows()):
                    trade_date = pd.to_datetime(row.get("日期", idx))
                    if isinstance(trade_date, pd.Timestamp):
                        trade_date = trade_date.to_pydatetime()

                    trade_date_only = (
                        trade_date.date() if hasattr(trade_date, "date") else trade_date
                    )
                    is_latest = api_latest_date and trade_date_only == api_latest_date

                    daily_data = {
                        "trade_date": trade_date_only,
                        "trade_time": trade_date,
                        "open": to_python_type(row.get("开盘")),
                        "high": to_python_type(row.get("最高")),
                        "low": to_python_type(row.get("最低")),
                        "close": to_python_type(row.get("收盘")),
                        "volume": int(row.get("成交量", 0))
                        if pd.notna(row.get("成交量"))
                        else 0,
                        "amount": to_python_type(row.get("成交额")),
                        "change_pct": to_python_type(row.get("涨跌幅"))
                        if is_latest
                        else None,
                        "change_amount": to_python_type(row.get("涨跌额"))
                        if is_latest
                        else None,
                        "turnover_rate": to_python_type(row.get("换手率"))
                        if is_latest
                        else None,
                        "pe_dynamic": to_python_type(stock_info.get("市盈率-动态"))
                        if is_latest
                        else None,
                        "pb": to_python_type(stock_info.get("市净率"))
                        if is_latest
                        else None,
                        "total_market_cap": to_python_type(stock_info.get("总市值"))
                        if is_latest
                        else None,
                        "circ_market_cap": to_python_type(stock_info.get("流通市值"))
                        if is_latest
                        else None,
                        "main_flow": to_python_type(fund_flow.get("主力净流入"))
                        if is_latest
                        else None,
                        "main_flow_ratio": to_python_type(
                            fund_flow.get("主力净流入占比")
                        )
                        if is_latest
                        else None,
                    }
                    data_list.append(daily_data)

                inserted_count = 0
                updated_count = 0
                if data_list:
                    db_logger.info(
                        f"[{stock_code}] 批量处理 {len(data_list)} 条数据..."
                    )
                    inserted_count, updated_count = manager.batch_insert_daily_data(
                        data_list
                    )
                    if is_first_time:
                        db_logger.info(f"[{stock_code}] 批量更新技术指标...")
                        manager.batch_update_technical_indicators(
                            history_df, indicators
                        )
                        db_logger.info(f"[{stock_code}] 技术指标更新完成")
                    elif new_data_df is not None and not new_data_df.empty:
                        db_logger.info(
                            f"[{stock_code}] 批量更新新增数据的技术指标（使用完整历史数据计算）..."
                        )
                        manager.batch_update_technical_indicators(
                            history_df, indicators
                        )
                        db_logger.info(f"[{stock_code}] 技术指标更新完成")
            else:
                inserted_count = 0
                updated_count = 0
        else:
            inserted_count = 0
            updated_count = 0

        db_logger.info(
            f"[{stock_code}] 数据同步完成: 新增 {inserted_count} 条, 更新 {updated_count} 条"
        )

        db_logger.info(f"[{stock_code}] 从数据库读取完整数据...")
        df = manager.get_historical_data(days)

        db_logger.info(f"[{stock_code}] 数据获取完成")

        return {
            "source": "api",
            "stock_info": stock_info,
            "fund_flow": fund_flow,
            "history_df": df,
            "indicators": indicators,
        }

    except Exception as e:
        db_logger.error(f"[{stock_code}] 从API获取数据失败: {e}")
        import traceback

        db_logger.error(traceback.format_exc())

        try:
            df = manager.get_historical_data(days)
            if df is not None and not df.empty:
                return {"source": "database", "dataframe": df}
        except:
            pass

        return {"source": "error", "error": str(e)}
