import sqlite3
import os
import threading
import logging
import atexit
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bot_data.db")

# Cấu hình Turso Cloud Database
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "").strip()
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "").strip()

# Chuẩn hóa URL Turso sang HTTPS cho giao thức Hrana HTTP ổn định tuyệt đối
if TURSO_DATABASE_URL.startswith("libsql://"):
    TURSO_DATABASE_URL = "https://" + TURSO_DATABASE_URL[9:]


class TursoRow:
    """Wrapper cho hàng dữ liệu Turso để tương thích 100% với sqlite3.Row."""
    def __init__(self, columns: list[str] | tuple[str, ...], values: list | tuple):
        self._columns = list(columns)
        self._values = list(values)
        self._dict = dict(zip(self._columns, self._values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._dict[key]

    def __iter__(self):
        # Trả về các cặp (key, value) để dict(row) hoạt động y hệt sqlite3.Row
        return iter(self._dict.items())

    def __len__(self):
        return len(self._values)

    def __repr__(self):
        return f"<TursoRow {self._dict}>"

    def keys(self):
        return self._dict.keys()

    def values(self):
        return self._dict.values()

    def items(self):
        return self._dict.items()

    def get(self, key, default=None):
        return self._dict.get(key, default)


class TursoCursor:
    """Cursor wrapper tương thích sqlite3.Cursor."""
    def __init__(self, client):
        self.client = client
        self._rows = []
        self._row_idx = 0
        self._columns = []
        self.rowcount = -1

    def execute(self, query: str, params: tuple | list = ()):
        clean_params = list(params) if isinstance(params, (tuple, list)) else []
        res = self.client.execute(query, clean_params)
        self._columns = list(res.columns) if hasattr(res, "columns") and res.columns else []
        self._rows = [TursoRow(self._columns, r) for r in res.rows]
        self._row_idx = 0
        self.rowcount = len(self._rows)
        return self

    def executemany(self, query: str, seq_of_params):
        for params in seq_of_params:
            self.execute(query, params)
        return self

    def fetchone(self):
        if self._row_idx < len(self._rows):
            row = self._rows[self._row_idx]
            self._row_idx += 1
            return row
        return None

    def fetchall(self):
        remaining = self._rows[self._row_idx:]
        self._row_idx = len(self._rows)
        return remaining

    def close(self):
        pass


class TursoConnection:
    """Connection wrapper tương thích sqlite3.Connection và context manager."""
    def __init__(self, client):
        self.client = client

    def cursor(self):
        return TursoCursor(self.client)

    def execute(self, query: str, params: tuple | list = ()):
        cur = self.cursor()
        return cur.execute(query, params)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


_turso_client = None
_turso_lock = threading.Lock()


def is_cloud_db() -> bool:
    """Kiểm tra xem hệ thống có đang dùng Turso Cloud DB hay không."""
    return bool(TURSO_DATABASE_URL and TURSO_AUTH_TOKEN)


def _get_turso_client():
    """Lấy hoặc khởi tạo singleton client kết nối Turso Cloud."""
    global _turso_client
    if _turso_client is not None and not getattr(_turso_client, "closed", False):
        return _turso_client

    with _turso_lock:
        if _turso_client is not None and not getattr(_turso_client, "closed", False):
            return _turso_client
        try:
            import collections
            import asyncio
            import libsql_client
            import libsql_client.sync

            # Patch _AsyncExecutor de luong chay la Daemon thread, khong gay treo tien trinh khi exit
            if not getattr(libsql_client.sync, "_daemon_patched", False):
                def _patched_async_init(self):
                    self._thread = threading.Thread(target=self._run, name="libsql_client", daemon=True)
                    self._loop = asyncio.new_event_loop()
                    self._lock = threading.Lock()
                    self._closed = False
                    self._queue = collections.deque()
                    self._waker = None
                    self._thread.start()

                libsql_client.sync._AsyncExecutor.__init__ = _patched_async_init
                libsql_client.sync._daemon_patched = True

            _turso_client = libsql_client.create_client_sync(
                url=TURSO_DATABASE_URL,
                auth_token=TURSO_AUTH_TOKEN
            )
            return _turso_client
        except Exception as e:
            logger.error(f"[DB] Loi ket noi Turso Cloud: {e}")
            raise


def close_turso_client():
    """Dong ket noi Turso Cloud khi thoat tien trinh."""
    global _turso_client
    if _turso_client is not None and not getattr(_turso_client, "closed", False):
        try:
            _turso_client.close()
        except Exception:
            pass
        _turso_client = None


atexit.register(close_turso_client)


def get_db():
    """Lấy kết nối cơ sở dữ liệu (ưu tiên Turso Cloud, fallback SQLite)."""
    if is_cloud_db():
        try:
            client = _get_turso_client()
            return TursoConnection(client)
        except Exception as e:
            logger.error(f"[DB] Khong the ket noi Turso Cloud, fallback sang SQLite: {e}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_local_to_turso_if_needed():
    """Tự động chuyển dữ liệu từ file SQLite cũ bot_data.db lên Turso Cloud một lần duy nhất."""
    if not is_cloud_db() or not os.path.exists(DB_PATH):
        return
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            row = cur.fetchone()
            turso_count = row[0] if row else 0
            if turso_count > 0:
                return  # Đã có dữ liệu trên Turso, không cần migrate lại

        print("[DB] Phat hien Turso Cloud DB moi, dang tu dong dong bo tu bot_data.db...")
        local_conn = sqlite3.connect(DB_PATH)
        local_cur = local_conn.cursor()

        tables = ["users", "link_history", "reports", "url_cache", "bypass_cache", "bot_settings", "user_limits", "referrals"]
        with get_db() as conn:
            for table in tables:
                try:
                    local_cur.execute(f"PRAGMA table_info({table})")
                    columns = [col[1] for col in local_cur.fetchall()]
                    if not columns:
                        continue
                    col_str = ", ".join(columns)
                    placeholders = ", ".join(["?"] * len(columns))

                    local_cur.execute(f"SELECT {col_str} FROM {table}")
                    rows = local_cur.fetchall()
                    if rows:
                        for r in rows:
                            conn.cursor().execute(f"INSERT OR REPLACE INTO {table} ({col_str}) VALUES ({placeholders})", list(r))
                        print(f"[DB] Da dong bo bang {table}: {len(rows)} ban ghi len Turso Cloud.")
                except Exception as ex:
                    print(f"[DB] Bo qua bang {table}: {ex}")

        local_conn.close()
        print("[DB] Dong bo du lieu len Turso Cloud hoan tat 100%!")
    except Exception as e:
        print(f"[DB] Loi tu dong dong bo Turso: {e}")


def init_db():
    db_type = "Turso Cloud (libSQL)" if is_cloud_db() else f"SQLite Local ({DB_PATH})"
    print(f"[DB] Khoi tao co so du lieu: {db_type}")
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            result_url TEXT
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
        # Bảng hệ thống giới thiệu bạn bè (Referral Viral System)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
        # Đảm bảo bảng link_history có cột result_url
        try:
            cursor.execute("ALTER TABLE link_history ADD COLUMN result_url TEXT")
        except Exception:
            pass
        conn.commit()

    if is_cloud_db():
        migrate_local_to_turso_if_needed()


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

            # Tổng số thành viên VIP
            cursor.execute("SELECT COUNT(*) FROM user_limits WHERE is_vip = 1")
            total_vips = cursor.fetchone()[0]

            rate = round((success_links / total_links * 100), 1) if total_links > 0 else 100.0

            return {
                "total_users": total_users,
                "today_users": today_users,
                "total_vips": total_vips,
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

def get_all_vip_users() -> list[dict]:
    """Lấy danh sách tất cả các tài khoản hiện đang là VIP còn hạn."""
    vn_tz = timezone(timedelta(hours=7))
    now = datetime.now(vn_tz)
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT l.user_id, l.vip_until, l.today_count, u.username, u.first_name
            FROM user_limits l
            LEFT JOIN users u ON l.user_id = u.user_id
            WHERE l.is_vip = 1
            ORDER BY l.vip_until DESC
            """)
            rows = cursor.fetchall()
            vips = []
            for r in rows:
                vip_until_str = r["vip_until"]
                is_active = True
                days_left = 0
                if vip_until_str:
                    try:
                        v_until = datetime.fromisoformat(vip_until_str)
                        if v_until.tzinfo is None:
                            v_until = v_until.replace(tzinfo=vn_tz)
                        if now > v_until:
                            is_active = False
                            # Cập nhật hết hạn trong DB
                            cursor.execute("UPDATE user_limits SET is_vip = 0 WHERE user_id = ?", (r["user_id"],))
                        else:
                            delta = v_until - now
                            days_left = max(1, int(delta.total_seconds() // 86400) if delta.total_seconds() >= 86400 else 1)
                    except Exception:
                        pass
                if is_active:
                    vips.append({
                        "user_id": r["user_id"],
                        "username": r["username"] or "",
                        "first_name": r["first_name"] or "Không tên",
                        "vip_until": vip_until_str[:10] if vip_until_str else "Vô thời hạn",
                        "days_left": days_left,
                        "today_count": r["today_count"] or 0
                    })
            conn.commit()
            return vips
    except Exception as e:
        print(f"[DB] get_all_vip_users error: {e}")
        return []

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

def process_referral(referrer_id: int, referred_id: int) -> dict:
    """
    Ghi nhận một lượt giới thiệu mới và tính toán thưởng VIP.
    Trả về dict chứa thông tin chi tiết.
    """
    if referrer_id == referred_id:
        return {"success": False, "reason": "self_referral"}

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Kiểm tra xem người được giới thiệu đã từng tồn tại trong hệ thống chưa
            cursor.execute("SELECT id FROM referrals WHERE referred_id = ?", (referred_id,))
            if cursor.fetchone():
                return {"success": False, "reason": "already_referred"}

            # Ghi nhận lượt giới thiệu
            cursor.execute("""
            INSERT INTO referrals (referrer_id, referred_id)
            VALUES (?, ?)
            """, (referrer_id, referred_id))
            conn.commit()

            # Tính tổng số người đã mời của referrer
            cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (referrer_id,))
            total_refs = cursor.fetchone()[0]

            # Kiểm tra mốc thưởng VIP tự động:
            # Mốc 3: 3 ngày
            # Mốc 5: 5 ngày
            # Mốc 10: 15 ngày
            # Mốc 20: 30 ngày
            # Mỗi 10 người tiếp theo (30, 40, 50...): 30 ngày
            awarded = False
            days = 0

            if total_refs == 3:
                awarded = True
                days = 3
            elif total_refs == 5:
                awarded = True
                days = 5
            elif total_refs == 10:
                awarded = True
                days = 15
            elif total_refs == 20:
                awarded = True
                days = 30
            elif total_refs > 20 and total_refs % 10 == 0:
                awarded = True
                days = 30

            if awarded and days > 0:
                set_user_vip(referrer_id, days)

            return {
                "success": True,
                "total_refs": total_refs,
                "awarded_vip": awarded,
                "days_awarded": days
            }
    except Exception as e:
        print(f"[DB] process_referral error: {e}")
        return {"success": False, "reason": "error"}

def get_referral_stats(user_id: int) -> dict:
    """Lấy thống kê mời bạn bè của người dùng."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
            row = cursor.fetchone()
            total_refs = row[0] if row else 0

            if total_refs < 3:
                target = 3
                reward = 3
            elif total_refs < 5:
                target = 5
                reward = 5
            elif total_refs < 10:
                target = 10
                reward = 15
            elif total_refs < 20:
                target = 20
                reward = 30
            else:
                target = ((total_refs // 10) + 1) * 10
                reward = 30

            needed = max(0, target - total_refs)
            return {
                "total_refs": total_refs,
                "target": target,
                "reward_days": reward,
                "needed": needed
            }
    except Exception as e:
        print(f"[DB] get_referral_stats error: {e}")
        return {"total_refs": 0, "target": 3, "reward_days": 3, "needed": 3}

# Khởi tạo DB khi load module
init_db()

