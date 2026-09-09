import hashlib
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from core.database import save_url_key, get_url_by_key

# Bộ nhớ tạm ánh xạ mã băm ngắn -> URL đầy đủ
URL_MAP = {}

def get_short_key(url: str) -> str:
    key = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
    URL_MAP[key] = url
    save_url_key(key, url)
    return key

def get_url_from_key(key: str) -> str | None:
    if key in URL_MAP:
        return URL_MAP[key]
    db_url = get_url_by_key(key)
    if db_url:
        URL_MAP[key] = db_url
        return db_url
    return None


def get_result_keyboard(target_url: str) -> InlineKeyboardMarkup:
    """
    Tạo bàn phím nút bấm mở nhanh link đích trên trình duyệt.
    """
    keyboard = [
        [
            InlineKeyboardButton("🌐 Mở Link Đích Ngay", url=target_url)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_fail_keyboard(url: str, is_task_shortener: bool = False) -> InlineKeyboardMarkup:
    """
    Tạo nút bấm khi không vượt được link: Lấy Key (nếu có) + Báo lỗi cho Admin.
    """
    short_key = get_short_key(url)
    keyboard = []
    if not is_task_shortener:
        keyboard.append([
            InlineKeyboardButton("🔑 Tự Động Lấy Key Trên Web Này", callback_data=f"getkey:{short_key}")
        ])
    keyboard.append([
        InlineKeyboardButton("📢 Báo Lỗi Link Này Cho Admin", callback_data=f"report:{short_key}")
    ])
    return InlineKeyboardMarkup(keyboard)

def get_traffic_key_keyboard(url: str) -> InlineKeyboardMarkup:
    return get_fail_keyboard(url, is_task_shortener=False)

def get_main_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Tạo bàn phím menu cố định dưới thanh nhập tin nhắn Telegram.
    Tự động phân quyền: Admin thấy nút Thống kê, người dùng thấy nút Hỗ trợ/Báo lỗi.
    """
    if is_admin:
        keyboard = [
            [KeyboardButton("📖 Hướng Dẫn Vượt Link"), KeyboardButton("🔑 Cách Lấy Mã 60s")],
            [KeyboardButton("📁 Vượt Link File .txt"), KeyboardButton("🌐 Dịch Vụ Hỗ Trợ")],
            [KeyboardButton("📊 Thống Kê (Admin)"), KeyboardButton("🆔 ID Của Tôi")]
        ]
    else:
        keyboard = [
            [KeyboardButton("📖 Hướng Dẫn Vượt Link"), KeyboardButton("🔑 Cách Lấy Mã 60s")],
            [KeyboardButton("📁 Vượt Link File .txt"), KeyboardButton("🌐 Dịch Vụ Hỗ Trợ")],
            [KeyboardButton("📢 Hỗ Trợ / Báo Lỗi"), KeyboardButton("🆔 ID Của Tôi")]
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)




