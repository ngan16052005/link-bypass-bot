import hashlib
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Bộ nhớ tạm ánh xạ mã băm ngắn -> URL đầy đủ (đảm bảo không vượt quá giới hạn 64 bytes của Telegram callback_data)
URL_MAP = {}

def get_short_key(url: str) -> str:
    key = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
    URL_MAP[key] = url
    return key

def get_url_from_key(key: str) -> str | None:
    return URL_MAP.get(key)

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
