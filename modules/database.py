import sqlite3
import os
import pandas as pd
from datetime import datetime
from modules.time_utils import get_taipei_timestamp, get_taipei_datestr

# 改用絕對路徑：避免從不同工作目錄啟動 streamlit 時，
# 相對路徑 "quant_firm.db" 指向不同資料夾，變成每次都生成新的空資料庫。
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quant_firm.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS trade_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            action TEXT,
            pnl REAL,
            strategy_type TEXT,
            reason TEXT,
            audit_status TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS macro_daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            report_type TEXT,
            title TEXT,
            summary TEXT,
            content_markdown TEXT,
            metrics_snapshot TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS sentiment_matrix_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            vix REAL,
            vix3m REAL,
            vix9d REAL,
            vix_ratio_30_90 REAL,
            skew REAL,
            vvix REAL,
            hy_oas REAL,
            hy_oas_5d_diff REAL,
            s_term REAL,
            s_credit REAL,
            s_tail REAL,
            s_implied REAL,
            news_shock_flag INTEGER,
            k_risk REAL,
            regime_label TEXT,
            details_json TEXT
        )
    ''')
    conn.commit()
    conn.close()


def insert_trade_log(symbol, action, pnl, strategy_type, reason, audit_status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO trade_logs (timestamp, symbol, action, pnl, strategy_type, reason, audit_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (get_taipei_timestamp(), symbol, action, pnl, strategy_type, reason, audit_status))
    conn.commit()
    conn.close()


def insert_batch_trade_logs(trades: list) -> int:
    """
    批次寫入多筆調倉與交易紀錄至 SQLite。
    trades 每個元素需為 dict: {'symbol', 'action', 'pnl', 'strategy_type', 'reason', 'audit_status'}
    """
    if not trades:
        return 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now_str = get_taipei_timestamp()
    records = [
        (
            now_str,
            t.get('symbol', ''),
            t.get('action', ''),
            float(t.get('pnl', 0.0)),
            t.get('strategy_type', '宏觀動態調倉'),
            t.get('reason', ''),
            t.get('audit_status', '待審計')
        )
        for t in trades
    ]
    c.executemany('''
        INSERT INTO trade_logs (timestamp, symbol, action, pnl, strategy_type, reason, audit_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', records)
    inserted_count = c.rowcount
    conn.commit()
    conn.close()
    return inserted_count


def get_trade_logs():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM trade_logs ORDER BY timestamp DESC", conn)
    conn.close()
    return df


def update_all_pending_trades_status(new_status: str = "已核准 (IC Verified)") -> int:
    """
    一鍵核准所有待審計狀態的交易訂單。
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE trade_logs SET audit_status = ? WHERE audit_status LIKE '%待審計%'", (new_status,))
    updated_count = c.rowcount
    conn.commit()
    conn.close()
    return updated_count


def get_today_realized_pnl():
    """今日（本機日期）所有交易紀錄的已實現損益加總，用於單日回撤熔斷計算。"""
    conn = sqlite3.connect(DB_PATH)
    today_str = get_taipei_datestr()
    df = pd.read_sql_query(
        "SELECT pnl FROM trade_logs WHERE timestamp LIKE ?",
        conn, params=(f"{today_str}%",)
    )
    conn.close()
    return float(df['pnl'].sum()) if not df.empty else 0.0


def get_cumulative_realized_pnl():
    """全部歷史交易紀錄的已實現損益加總。"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT pnl FROM trade_logs", conn)
    conn.close()
    return float(df['pnl'].sum()) if not df.empty else 0.0


def save_macro_report(report_type: str, title: str, summary: str, content_markdown: str, metrics_snapshot: str = "") -> int:
    """
    保存每日宏觀研報（晨報/夕報/即時投研）至 SQLite 歷史資料庫。
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now_str = get_taipei_timestamp()
    c.execute('''
        INSERT INTO macro_daily_reports (timestamp, report_type, title, summary, content_markdown, metrics_snapshot)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (now_str, report_type, title, summary, content_markdown, metrics_snapshot))
    report_id = c.lastrowid
    conn.commit()
    conn.close()
    return report_id


def get_macro_reports(limit: int = 30) -> pd.DataFrame:
    """
    讀取歷史宏觀研報列表，按時間降冪排序。
    """
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT id, timestamp, report_type, title, summary, content_markdown, metrics_snapshot FROM macro_daily_reports ORDER BY timestamp DESC LIMIT ?",
        conn, params=(limit,)
    )
    conn.close()
    return df


def get_macro_report_by_id(report_id: int):
    """
    依 ID 取得單筆宏觀研報詳情。
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, timestamp, report_type, title, summary, content_markdown, metrics_snapshot FROM macro_daily_reports WHERE id = ?", (report_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "timestamp": row[1],
            "report_type": row[2],
            "title": row[3],
            "summary": row[4],
            "content_markdown": row[5],
            "metrics_snapshot": row[6]
        }
    return None


def save_sentiment_matrix_log(entry: dict) -> int:
    """
    保存市場隱含情緒矩陣與動態風控乘數計算紀錄至 SQLite。
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now_str = get_taipei_timestamp()
    c.execute('''
        INSERT INTO sentiment_matrix_logs (
            timestamp, vix, vix3m, vix9d, vix_ratio_30_90,
            skew, vvix, hy_oas, hy_oas_5d_diff,
            s_term, s_credit, s_tail, s_implied,
            news_shock_flag, k_risk, regime_label, details_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        now_str,
        float(entry.get('vix', 0.0)),
        float(entry.get('vix3m', 0.0)),
        float(entry.get('vix9d', 0.0)),
        float(entry.get('vix_ratio_30_90', 1.0)),
        float(entry.get('skew', 0.0)),
        float(entry.get('vvix', 0.0)),
        float(entry.get('hy_oas', 0.0)),
        float(entry.get('hy_oas_5d_diff', 0.0)),
        float(entry.get('s_term', 0.0)),
        float(entry.get('s_credit', 0.0)),
        float(entry.get('s_tail', 0.0)),
        float(entry.get('s_implied', 0.0)),
        1 if entry.get('news_shock_flag') else 0,
        float(entry.get('k_risk', 1.0)),
        str(entry.get('regime_label', '中性')),
        str(entry.get('details_json', '{}'))
    ))
    row_id = c.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_recent_sentiment_matrix_logs(limit: int = 15) -> pd.DataFrame:
    """
    讀取最新市場隱含情緒紀錄。
    """
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM sentiment_matrix_logs ORDER BY timestamp DESC LIMIT ?",
        conn, params=(limit,)
    )
    conn.close()
    return df


init_db()
