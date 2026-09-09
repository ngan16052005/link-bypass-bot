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
    Gọn gàng, chuẩn UI mobile, không bị tràn viền.
    """
    if is_admin:
        keyboard = [
            [KeyboardButton("⚡ Vượt Link"), KeyboardButton("🔑 Lấy Mã 60s")],
            [KeyboardButton("📁 Vượt File .txt"), KeyboardButton("🌐 Dịch Vụ")],
            [KeyboardButton("📊 Thống Kê (Admin)"), KeyboardButton("🆔 ID Của Tôi")]
        ]
    else:
        keyboard = [
            [KeyboardButton("⚡ Vượt Link"), KeyboardButton("🔑 Lấy Mã 60s")],
            [KeyboardButton("📁 Vượt File .txt"), KeyboardButton("🌐 Dịch Vụ")],
            [KeyboardButton("📢 Hỗ Trợ"), KeyboardButton("🆔 ID Của Tôi")]
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

def get_dashboard_inline_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """
    Bảng điều khiển tương tác trực tiếp (Inline Interactive Dashboard).
    Chuyển trang ngay tại chỗ mà không làm trôi tin nhắn chat.
    """
    keyboard = [
        [
            InlineKeyboardButton("📖 Hướng Dẫn", callback_data="dash:help"),
            InlineKeyboardButton("🔑 Lấy Mã 60s", callback_data="dash:key")
        ],
        [
            InlineKeyboardButton("📁 Vượt File .txt", callback_data="dash:batch"),
            InlineKeyboardButton("🌐 Dịch Vụ", callback_data="dash:services")
        ],
        [
            InlineKeyboardButton("📢 Báo Lỗi", callback_data="dash:report_info"),
            InlineKeyboardButton("🆔 ID Của Tôi", callback_data="dash:myid")
        ]
    ]
    if is_admin:
        keyboard.append([
            InlineKeyboardButton("📊 Thống Kê Hệ Thống", callback_data="dash:stats"),
            InlineKeyboardButton("📋 Báo Cáo Lỗi", callback_data="dash:admin_reports")
        ])
    return InlineKeyboardMarkup(keyboard)

def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Nút quay lại menu điều khiển chính.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Quay Lại Bảng Điều Khiển", callback_data="dash:menu")]
    ])
