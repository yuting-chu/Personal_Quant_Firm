import sqlite3
import os
import pandas as pd
from datetime import datetime

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
    conn.commit()
    conn.close()


def insert_trade_log(symbol, action, pnl, strategy_type, reason, audit_status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO trade_logs (timestamp, symbol, action, pnl, strategy_type, reason, audit_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), symbol, action, pnl, strategy_type, reason, audit_status))
    conn.commit()
    conn.close()


def get_trade_logs():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM trade_logs ORDER BY timestamp DESC", conn)
    conn.close()
    return df


def get_today_realized_pnl():
    """今日（本機日期）所有交易紀錄的已實現損益加總，用於單日回撤熔斷計算。"""
    conn = sqlite3.connect(DB_PATH)
    today_str = datetime.now().strftime("%Y-%m-%d")
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


init_db()