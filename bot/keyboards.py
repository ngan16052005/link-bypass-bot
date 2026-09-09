from telegram import InlineKeyboardButton, InlineKeyboardMarkup

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

def get_traffic_key_keyboard(url: str) -> InlineKeyboardMarkup:
    """
    Tạo nút bấm tùy chọn tự động lấy Key/Mã trên trang web này.
    """
    keyboard = [
        [
            InlineKeyboardButton("🔑 Tự Động Lấy Key Trên Web Này", callback_data=f"getkey:{url}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
