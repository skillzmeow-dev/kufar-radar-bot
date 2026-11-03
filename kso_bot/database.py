import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "kso_bot.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Subscribers table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            chat_id INTEGER PRIMARY KEY,
            chat_type TEXT,
            title TEXT,
            subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Processed files table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            filename TEXT PRIMARY KEY,
            file_id TEXT,
            date_str TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def add_subscriber(chat_id: int, chat_type: str = "private", title: str = ""):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO subscribers (chat_id, chat_type, title)
        VALUES (?, ?, ?)
    """, (chat_id, chat_type, title))
    conn.commit()
    conn.close()

def remove_subscriber(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

def get_subscribers():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT chat_id, chat_type FROM subscribers")
    rows = cur.fetchall()
    conn.close()
    return rows

def is_file_processed(filename: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM processed_files WHERE filename = ?", (filename,))
    row = cur.fetchone()
    conn.close()
    return row is not None

def mark_file_processed(filename: str, file_id: str, date_str: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO processed_files (filename, file_id, date_str)
        VALUES (?, ?, ?)
    """, (filename, file_id, date_str))
    conn.commit()
    conn.close()
