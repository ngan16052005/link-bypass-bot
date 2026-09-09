import time
import os

# Lưu vết thời gian hành động cuối cùng: {user_id: {"message": timestamp, "key": timestamp}}
USER_ACTIVITY = {}

# Cấu hình thời gian giãn cách (Cooldown tính bằng giây)
MESSAGE_COOLDOWN = 3.0   # Gửi link / tin nhắn
KEY_GRAB_COOLDOWN = 10.0 # Chạy trình duyệt ảo cào key 60s (tiêu tốn tài nguyên)
BATCH_COOLDOWN = 15.0    # Gửi file vượt hàng loạt

def check_rate_limit(user_id: int, action_type: str = "message") -> tuple[bool, float]:
    """
    Kiểm tra người dùng có đang thao tác quá nhanh hay không.
    - Admin luôn được miễn trừ (Whitelisted).
    - Trả về: (is_allowed, remaining_seconds)
    """
    admin_id = os.getenv("ADMIN_ID", "").strip()
    if admin_id and str(user_id) == admin_id:
        return True, 0.0

    now = time.time()
    if action_type == "key":
        cooldown = KEY_GRAB_COOLDOWN
    elif action_type == "batch":
        cooldown = BATCH_COOLDOWN
    else:
        cooldown = MESSAGE_COOLDOWN


    user_records = USER_ACTIVITY.setdefault(user_id, {})
    last_time = user_records.get(action_type, 0.0)
    elapsed = now - last_time

    if elapsed < cooldown:
        remaining = round(cooldown - elapsed, 1)
        return False, remaining

    # Cập nhật thời gian thực hiện mới
    user_records[action_type] = now
    
    # Dọn dẹp bộ nhớ nếu danh sách quá lớn (> 2000 users)
    if len(USER_ACTIVITY) > 2000:
        for uid in list(USER_ACTIVITY.keys())[:500]:
            USER_ACTIVITY.pop(uid, None)

    return True, 0.0
