import logging
from telegram.ext import ContextTypes
from core.database import get_channel_fsub, is_admin_user

logger = logging.getLogger(__name__)

async def check_user_fsub(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, str]:
    """
    Kiểm tra người dùng đã tham gia kênh bắt buộc hay chưa.
    Trả về (is_subscribed: bool, channel_url: str).
    """
    if is_admin_user(user_id):
        return True, ""

    channel, enabled = get_channel_fsub()
    if not enabled or not channel:
        return True, ""

    clean_chan = channel.strip()
    channel_url = f"https://t.me/{clean_chan.lstrip('@')}"

    try:
        chat_member = await context.bot.get_chat_member(chat_id=clean_chan, user_id=user_id)
        if chat_member.status in ["creator", "administrator", "member", "restricted"]:
            return True, ""
        return False, channel_url
    except Exception as e:
        # Nếu bot chưa được add quyền Admin trong kênh hoặc mạng lag, bỏ qua để không chặn nhầm người dùng
        logger.warning(f"[FSub] Warning checking chat member {user_id} in {clean_chan}: {e}")
        return True, ""
