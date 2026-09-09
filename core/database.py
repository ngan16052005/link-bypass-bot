import sqlite3
import os
from datetime import datetime, timezone, timedelta

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
        # Bảng bộ nhớ đệm kết quả vượt link toàn cầu (Global Link Cache)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bypass_cache (
            url_hash TEXT PRIMARY KEY,
            original_url TEXT,
            result_url TEXT,
            engine TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bypass_cache_created ON bypass_cache(created_at)")
        # Bảng cài đặt hệ thống động (Admin ID, cấu hình)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        # Bảng quản lý hạn ngạch ngày & VIP thành viên
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_limits (
            user_id INTEGER PRIMARY KEY,
            is_vip INTEGER DEFAULT 0,
            vip_until TIMESTAMP,
            today_date TEXT,
            today_count INTEGER DEFAULT 0
        )
        """)
        # Đảm bảo bảng link_history có cột result_url
        try:
            cursor.execute("ALTER TABLE link_history ADD COLUMN result_url TEXT")
        except Exception:
            pass
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

def log_action(user_id: int, url: str, action_type: str, status: str, engine: str = "", result_url: str = ""):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO link_history (user_id, url, result_url, action_type, status, engine)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, url, result_url, action_type, status, engine))
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

def get_cached_bypass(url: str) -> dict | None:
    """
    Lấy kết quả giải mã đã lưu trong bộ nhớ đệm (Hạn sử dụng: 7 ngày).
    Trả về: {"result_url": ..., "engine": ...} hoặc None.
    """
    try:
        import hashlib
        clean_url = url.strip()
        url_hash = hashlib.sha256(clean_url.encode("utf-8")).hexdigest()
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT result_url, engine FROM bypass_cache 
            WHERE url_hash = ? AND created_at >= datetime('now', '-7 days')
            """, (url_hash,))
            row = cursor.fetchone()
            if row:
                return {
                    "result_url": row["result_url"],
                    "engine": row["engine"]
                }
    except Exception as e:
        print(f"[DB] get_cached_bypass error: {e}")
    return None

def save_cached_bypass(original_url: str, result_url: str, engine: str = ""):
    """
    Lưu kết quả giải mã vào cache toàn cầu.
    Tự động dọn dẹp các link cũ hơn 7 ngày và giữ tối đa 5000 link mới nhất để vĩnh viễn không đầy ổ cứng.
    """
    try:
        import hashlib
        clean_url = original_url.strip()
        res_url = result_url.strip()
        if not clean_url or not res_url or clean_url == res_url:
            return
        url_hash = hashlib.sha256(clean_url.encode("utf-8")).hexdigest()
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO bypass_cache (url_hash, original_url, result_url, engine, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (url_hash, clean_url, res_url, engine))
            
            # 1. Tự động xóa các link lưu quá 7 ngày
            cursor.execute("DELETE FROM bypass_cache WHERE created_at < datetime('now', '-7 days')")
            
            # 2. Giữ tối đa 5000 link mới nhất
            cursor.execute("""
            DELETE FROM bypass_cache 
            WHERE url_hash NOT IN (
                SELECT url_hash FROM bypass_cache ORDER BY created_at DESC LIMIT 5000
            )
            """)
            conn.commit()
    except Exception as e:
        print(f"[DB] save_cached_bypass error: {e}")

def get_setting(key: str, default: str = "") -> str:
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default
    except Exception as e:
        print(f"[DB] get_setting error: {e}")
        return default

def set_setting(key: str, value: str):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key, str(value).strip()))
            conn.commit()
    except Exception as e:
        print(f"[DB] set_setting error: {e}")

def get_admin_id() -> str:
    env_id = os.getenv("ADMIN_ID", "").strip()
    if env_id:
        return env_id
    return get_setting("admin_id", "")

def set_admin_id(user_id: int | str):
    set_setting("admin_id", str(user_id).strip())

def is_admin_user(user_id: int | None) -> bool:
    if not user_id:
        return False
    admin_id = get_admin_id()
    if not admin_id:
        return False
    return str(user_id).strip() == admin_id

def get_all_user_ids() -> list[int]:
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE user_id IS NOT NULL AND user_id > 0")
            rows = cursor.fetchall()
            return [row["user_id"] for row in rows]
    except Exception as e:
        print(f"[DB] get_all_user_ids error: {e}")
        return []

def get_recent_reports(limit: int = 10) -> list[dict]:
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, user_id, username, url, created_at 
            FROM reports 
            ORDER BY created_at DESC 
            LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[DB] get_recent_reports error: {e}")
        return []

def clear_all_reports() -> bool:
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reports")
            conn.commit()
            return True
    except Exception as e:
        print(f"[DB] clear_all_reports error: {e}")
        return False

def check_and_increment_quota(user_id: int, is_admin: bool = False, limit_per_day: int = 30) -> tuple[bool, int, bool]:
    """
    Kiểm tra và tăng số lượng link đã xử lý trong ngày của người dùng.
    Trả về: (allowed: bool, remaining_today: int, is_vip: bool)
    """
    if is_admin:
        return True, 999999, True

    vn_tz = timezone(timedelta(hours=7))
    now = datetime.now(vn_tz)
    today_str = now.strftime("%Y-%m-%d")

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_vip, vip_until, today_date, today_count FROM user_limits WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

            if not row:
                cursor.execute("""
                INSERT INTO user_limits (user_id, is_vip, vip_until, today_date, today_count)
                VALUES (?, 0, NULL, ?, 1)
                """, (user_id, today_str))
                conn.commit()
                return True, limit_per_day - 1, False

            is_vip = bool(row["is_vip"])
            vip_until_str = row["vip_until"]
            
            # Kiểm tra thời hạn VIP nếu có
            if is_vip and vip_until_str:
                try:
                    vip_until = datetime.fromisoformat(vip_until_str)
                    if vip_until.tzinfo is None:
                        vip_until = vip_until.replace(tzinfo=vn_tz)
                    if now > vip_until:
                        # VIP đã hết hạn
                        is_vip = False
                        cursor.execute("UPDATE user_limits SET is_vip = 0 WHERE user_id = ?", (user_id,))
                except Exception:
                    pass

            if is_vip:
                # Cập nhật số link VIP đã vượt hôm nay
                if row["today_date"] != today_str:
                    cursor.execute("UPDATE user_limits SET today_date = ?, today_count = 1 WHERE user_id = ?", (today_str, user_id))
                else:
                    cursor.execute("UPDATE user_limits SET today_count = today_count + 1 WHERE user_id = ?", (user_id,))
                conn.commit()
                return True, 999999, True

            # Người dùng miễn phí
            current_date = row["today_date"]
            current_count = row["today_count"]

            if current_date != today_str:
                cursor.execute("UPDATE user_limits SET today_date = ?, today_count = 1 WHERE user_id = ?", (today_str, user_id))
                conn.commit()
                return True, limit_per_day - 1, False

            if current_count >= limit_per_day:
                return False, 0, False

            cursor.execute("UPDATE user_limits SET today_count = today_count + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            return True, limit_per_day - (current_count + 1), False

    except Exception as e:
        print(f"[DB] check_and_increment_quota error: {e}")
        return True, limit_per_day, False

def set_user_vip(user_id: int, days: int) -> bool:
    """Cấp hoặc gia hạn VIP cho user theo số ngày."""
    vn_tz = timezone(timedelta(hours=7))
    now = datetime.now(vn_tz)
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT vip_until FROM user_limits WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

            start_date = now
            if row and row["vip_until"]:
                try:
                    cur_until = datetime.fromisoformat(row["vip_until"])
                    if cur_until.tzinfo is None:
                        cur_until = cur_until.replace(tzinfo=vn_tz)
                    if cur_until > now:
                        start_date = cur_until
                except Exception:
                    pass

            new_until = start_date + timedelta(days=days)
            until_str = new_until.isoformat()

            cursor.execute("""
            INSERT INTO user_limits (user_id, is_vip, vip_until, today_date, today_count)
            VALUES (?, 1, ?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                is_vip = 1,
                vip_until = ?
            """, (user_id, until_str, now.strftime("%Y-%m-%d"), until_str))
            conn.commit()
            return True
    except Exception as e:
        print(f"[DB] set_user_vip error: {e}")
        return False

def remove_user_vip(user_id: int) -> bool:
    """Hủy trạng thái VIP của user."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE user_limits SET is_vip = 0, vip_until = NULL WHERE user_id = ?", (user_id,))
            conn.commit()
            return True
    except Exception as e:
        print(f"[DB] remove_user_vip error: {e}")
        return False

def get_user_vip_info(user_id: int, limit_per_day: int = 30) -> dict:
    """Lấy thông tin VIP và hạn mức hôm nay của người dùng."""
    vn_tz = timezone(timedelta(hours=7))
    now = datetime.now(vn_tz)
    today_str = now.strftime("%Y-%m-%d")

    is_admin = is_admin_user(user_id)
    if is_admin:
        return {
            "is_vip": True,
            "is_admin": True,
            "vip_until": "Vĩnh viễn (Admin)",
            "today_count": 0,
            "remaining_today": 999999
        }

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_vip, vip_until, today_date, today_count FROM user_limits WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

            if not row:
                return {
                    "is_vip": False,
                    "is_admin": False,
                    "vip_until": None,
                    "today_count": 0,
                    "remaining_today": limit_per_day
                }

            is_vip = bool(row["is_vip"])
            vip_until_str = row["vip_until"]
            if is_vip and vip_until_str:
                try:
                    vip_until = datetime.fromisoformat(vip_until_str)
                    if vip_until.tzinfo is None:
                        vip_until = vip_until.replace(tzinfo=vn_tz)
                    if now > vip_until:
                        is_vip = False
                except Exception:
                    pass

            count = row["today_count"] if row["today_date"] == today_str else 0
            rem = 999999 if is_vip else max(0, limit_per_day - count)
            return {
                "is_vip": is_vip,
                "is_admin": False,
                "vip_until": vip_until_str if is_vip else None,
                "today_count": count,
                "remaining_today": rem
            }
    except Exception as e:
        print(f"[DB] get_user_vip_info error: {e}")
        return {"is_vip": False, "is_admin": False, "vip_until": None, "today_count": 0, "remaining_today": limit_per_day}

def get_user_history(user_id: int, limit: int = 5) -> list[dict]:
    """Lấy danh sách các link vượt thành công gần nhất của người dùng."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT url, result_url, engine, created_at
            FROM link_history
            WHERE user_id = ? AND status = 'success' AND result_url IS NOT NULL AND result_url != ''
            ORDER BY id DESC
            LIMIT ?
            """, (user_id, limit))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[DB] get_user_history error: {e}")
        return []

def get_channel_fsub() -> tuple[str, bool]:
    """Lấy thông tin kênh bắt buộc tham gia (channel_id_or_username, is_enabled)."""
    channel = get_setting("fsub_channel", "").strip()
    enabled = get_setting("fsub_enabled", "0").strip() == "1"
    return channel, enabled

def set_channel_fsub(channel: str, enabled: bool = True) -> bool:
    """Cài đặt kênh bắt buộc tham gia."""
    set_setting("fsub_channel", channel.strip())
    set_setting("fsub_enabled", "1" if enabled else "0")
    return True

def toggle_channel_fsub() -> bool:
    """Bật / Tắt chế độ bắt buộc tham gia kênh."""
    channel, enabled = get_channel_fsub()
    new_state = not enabled
    set_setting("fsub_enabled", "1" if new_state else "0")
    return new_state

# Khởi tạo DB khi load module
init_db()

