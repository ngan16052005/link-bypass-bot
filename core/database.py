import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bot_data.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        # Bảng người dùng
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        # Bảng lịch sử xử lý link
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS link_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            url TEXT,
            action_type TEXT,
            status TEXT,
            engine TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        # Bảng báo cáo lỗi
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        # Bảng lưu trữ ánh xạ short_key -> url bền vững
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS url_cache (
            short_key TEXT PRIMARY KEY,
            url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()


def log_user(user_id: int, username: str | None, first_name: str | None):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO users (user_id, username, first_name, last_active)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_active=CURRENT_TIMESTAMP
            """, (user_id, username or "", first_name or ""))
            conn.commit()
    except Exception as e:
        print(f"[DB] log_user error: {e}")

def log_action(user_id: int, url: str, action_type: str, status: str, engine: str = ""):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO link_history (user_id, url, action_type, status, engine)
            VALUES (?, ?, ?, ?, ?)
            """, (user_id, url, action_type, status, engine))
            conn.commit()
    except Exception as e:
        print(f"[DB] log_action error: {e}")

def save_report(user_id: int, username: str | None, url: str) -> bool:
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO reports (user_id, username, url)
            VALUES (?, ?, ?)
            """, (user_id, username or "", url))
            conn.commit()
            return True
    except Exception as e:
        print(f"[DB] save_report error: {e}")
        return False

def get_statistics() -> dict:
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Tổng số user
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            # User hoạt động hôm nay
            cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(last_active) = DATE('now')")
            today_users = cursor.fetchone()[0]
            
            # Tổng số link xử lý
            cursor.execute("SELECT COUNT(*) FROM link_history")
            total_links = cursor.fetchone()[0]
            
            # Link xử lý hôm nay
            cursor.execute("SELECT COUNT(*) FROM link_history WHERE DATE(created_at) = DATE('now')")
            today_links = cursor.fetchone()[0]
            
            # Số link thành công
            cursor.execute("SELECT COUNT(*) FROM link_history WHERE status = 'success'")
            success_links = cursor.fetchone()[0]
            
            # Tổng số báo cáo lỗi
            cursor.execute("SELECT COUNT(*) FROM reports")
            total_reports = cursor.fetchone()[0]

            rate = round((success_links / total_links * 100), 1) if total_links > 0 else 100.0

            return {
                "total_users": total_users,
                "today_users": today_users,
                "total_links": total_links,
                "today_links": today_links,
                "success_links": success_links,
                "success_rate": rate,
                "total_reports": total_reports
            }
    except Exception as e:
        print(f"[DB] get_statistics error: {e}")
        return {}

def save_url_key(short_key: str, url: str):

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO url_cache (short_key, url) VALUES (?, ?)", (short_key, url))
            conn.commit()
    except Exception as e:
        print(f"[DB] save_url_key error: {e}")

def get_url_by_key(short_key: str) -> str | None:
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM url_cache WHERE short_key = ?", (short_key,))
            row = cursor.fetchone()
            return row["url"] if row else None
    except Exception as e:
        print(f"[DB] get_url_by_key error: {e}")
        return None

# Khởi tạo DB khi load module
init_db()

