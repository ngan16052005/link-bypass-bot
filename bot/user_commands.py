import html
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.database import (
    log_user,
    log_action,
    is_admin_user,
    get_user_vip_info,
    process_referral,
    get_referral_stats,
    get_user_history
)
from core.engine_traffic_key import grab_traffic_key
from core.security_scanner import SecurityScanner
from .utils import extract_urls
from .texts import (
    WELCOME_MESSAGE,
    HELP_MESSAGE,
    SERVICES_MESSAGE,
    BATCH_MESSAGE,
    get_dashboard_text
)
from .keyboards import (
    get_main_menu_keyboard,
    get_dashboard_inline_keyboard,
    get_referral_keyboard,
    get_fail_keyboard
)
from .anti_spam import check_rate_limit

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)
    is_admin = is_admin_user(user.id if user else None)
    name = user.first_name if user and user.first_name else "bạn"

    # Xử lý link giới thiệu bạn bè (Deep Linking ?start=ref_123456789)
    if context.args and len(context.args) > 0:
        arg = context.args[0].strip()
        if arg.startswith("ref_") and user:
            try:
                referrer_id = int(arg[4:])
                res = process_referral(referrer_id, user.id)
                if res["success"]:
                    total_m = res["total_refs"]
                    alert_txt = (
                        f"🎉 <b>BẠN BÈ VỪA THAM GIA QUA LINK CỦA BẠN!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"👤 Người bạn: <b>{html.escape(user.full_name or 'Một người bạn')}</b> (@{user.username or 'Không có'})\n"
                        f"📊 Tổng số bạn bè bạn đã mời: <b>{total_m} người</b>\n"
                    )
                    if res["awarded_vip"]:
                        alert_txt += (
                            f"\n🎁 <b>CHÚC MỪNG BẠN ĐẠT MỐC THƯỞNG!</b>\n"
                            f"👑 Bạn vừa được cộng thêm <b>{res['days_awarded']} ngày VIP Member</b> vào tài khoản!"
                        )
                    else:
                        stats = get_referral_stats(referrer_id)
                        alert_txt += f"💡 Mời thêm <b>{stats['needed']} người nữa</b> để nhận ngay <b>{stats['reward_days']} ngày VIP</b>!"

                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=alert_txt,
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"[Ref] Error handling referral start: {e}")

    # Mở bàn phím menu cố định và gửi bảng điều khiển Interactive Dashboard
    await update.message.reply_text(
        "🚀 <i>Đang mở bảng điều khiển...</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(is_admin)
    )
    await update.message.reply_text(
        get_dashboard_text(name),
        parse_mode=ParseMode.HTML,
        reply_markup=get_dashboard_inline_keyboard(is_admin)
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)
    is_admin = is_admin_user(user.id if user else None)
    name = user.first_name if user and user.first_name else "bạn"
    await update.message.reply_text(
        get_dashboard_text(name),
        parse_mode=ParseMode.HTML,
        reply_markup=get_dashboard_inline_keyboard(is_admin)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)
    is_admin = is_admin_user(user.id if user else None)
    await update.message.reply_text(
        HELP_MESSAGE,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(is_admin)
    )


async def services_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)
    is_admin = is_admin_user(user.id if user else None)
    await update.message.reply_text(
        SERVICES_MESSAGE,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(is_admin)
    )


async def batch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)
    is_admin = is_admin_user(user.id if user else None)
    await update.message.reply_text(
        BATCH_MESSAGE,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(is_admin)
    )


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    log_user(user.id, user.username, user.first_name)
    is_admin = is_admin_user(user.id)
    vip_info = get_user_vip_info(user.id)

    if is_admin:
        rank_str = "👑 <b>Admin Quản Trị Tối Cao</b>"
        quota_str = "♾️ Không giới hạn"
    elif vip_info["is_vip"]:
        until_disp = str(vip_info['vip_until'])[:10] if vip_info['vip_until'] else "Vô thời hạn"
        rank_str = f"👑 <b>VIP Member</b> (Hạn dùng: <code>{until_disp}</code>)"
        quota_str = "♾️ Không giới hạn"
    else:
        rank_str = "👤 <b>Thành Viên Miễn Phí</b>"
        quota_str = f"<code>{vip_info['remaining_today']}/30</code> lượt vượt còn lại hôm nay"

    msg = (
        f"🆔 <b>THÔNG TIN TÀI KHOẢN CỦA BẠN:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Tên:</b> {html.escape(user.full_name or '')}\n"
        f"🔹 <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"🎖️ <b>Cấp bậc:</b> {rank_str}\n"
        f"📊 <b>Hạn mức:</b> {quota_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Chạm vào ID để tự động sao chép.</i>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def ref_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh xem link giới thiệu bạn bè và nhận VIP miễn phí."""
    user = update.effective_user
    if not user:
        return
    log_user(user.id, user.username, user.first_name)
    stats = get_referral_stats(user.id)
    ref_link = f"https://t.me/N1_link_bot?start=ref_{user.id}"

    msg = (
        "🎁 <b>CHƯƠNG TRÌNH MỜI BẠN BÈ - NHẬN VIP MIỄN PHÍ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Chia sẻ đường link độc quyền của bạn cho bạn bè, hội nhóm công nghệ. Càng mời nhiều, thời hạn VIP càng khủng!\n\n"
        "🔗 <b>Link giới thiệu của bạn:</b>\n"
        f"👉 <code>{ref_link}</code> 👈\n"
        "<i>(Chạm vào link để tự động sao chép)</i>\n\n"
        "📊 <b>Tiến trình của bạn:</b>\n"
        f"• Đã mời thành công: <b>{stats['total_refs']} người</b>\n"
        f"• Mốc tiếp theo: <b>{stats['target']} người</b> (🎁 Nhận <b>{stats['reward_days']} ngày VIP</b>)\n"
        f"• Cần mời thêm: <b>{stats['needed']} người nữa</b>\n\n"
        "🏆 <b>BẢNG MỐC THƯỞNG VIP:</b>\n"
        "• Mời <b>3 bạn</b> ➔ Tặng <b>3 ngày VIP</b>\n"
        "• Mời <b>5 bạn</b> ➔ Tặng <b>5 ngày VIP</b>\n"
        "• Mời <b>10 bạn</b> ➔ Tặng <b>15 ngày VIP</b>\n"
        "• Mời <b>20 bạn</b> ➔ Tặng <b>30 ngày VIP (1 tháng)</b>\n"
        "• Mỗi 10 bạn tiếp theo ➔ Tặng thêm <b>30 ngày VIP</b>!\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>Bấm nút bên dưới để chia sẻ 1-Click ngay cho bạn bè trên Telegram!</i>"
    )
    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=get_referral_keyboard(user.id)
    )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem danh sách 5 link đã vượt thành công gần nhất của người dùng."""
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)
    history = get_user_history(user.id if user else 0, limit=5)
    if not history:
        await update.message.reply_text(
            "📋 <b>LỊCH SỬ VƯỢT LINK CỦA BẠN:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✨ <i>Bạn chưa có link nào được lưu trong lịch sử! Hãy gửi link vào đây để trải nghiệm nhé.</i>",
            parse_mode=ParseMode.HTML
        )
        return

    msg = (
        "📋 <b>5 LINK VƯỢT THÀNH CÔNG GẦN NHẤT:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
    )
    for idx, item in enumerate(history, 1):
        msg += (
            f"<b>{idx}. {item['created_at'][:16]}</b> (⚡ <i>{html.escape(item['engine'])}</i>):\n"
            f"🔗 <b>Gốc:</b> <code>{html.escape(item['url'])}</code>\n"
            f"🎯 <b>Đích:</b> <code>{html.escape(item['result_url'])}</code>\n\n"
        )
    msg += "💡 <i>Chạm vào đường link đích để sao chép hoặc mở nhanh!</i>"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def do_grab_key(status_msg, url: str, user_id: int):
    escaped_url = html.escape(url)

    async def update_status(text: str):
        try:
            await status_msg.edit_text(
                f"🤖 <b>ĐANG TỰ ĐỘNG LẤY KEY TRÊN TRANG WEB...</b>\n\n"
                f"🌐 <b>URL:</b> <code>{escaped_url}</code>\n"
                f"📢 <b>Trạng thái:</b> {html.escape(text)}",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    success, key_code, details = await grab_traffic_key(url, status_callback=update_status)

    if success:
        log_action(user_id, url, "getkey", "success", "Playwright")
        success_text = (
            f"🎉 <b>LẤY KEY THÀNH CÔNG!</b>\n\n"
            f"🌐 <b>Trang web:</b>\n<code>{escaped_url}</code>\n\n"
            f"🔑 <b>MÃ / KEY CỦA BẠN:</b>\n"
            f"👉 <code>{html.escape(key_code)}</code> 👈\n\n"
            f"💡 <i>(Chạm vào đoạn mã trên để tự động sao chép)</i>\n"
            f"⚡ <i>{html.escape(details)}</i>"
        )
        await status_msg.edit_text(success_text, parse_mode=ParseMode.HTML)
    else:
        log_action(user_id, url, "getkey", "fail", "Playwright")
        fail_text = (
            f"⚠️ <b>CHƯA THỂ LẤY ĐƯỢC MÃ TỰ ĐỘNG!</b>\n\n"
            f"🌐 <b>URL:</b> <code>{escaped_url}</code>\n\n"
            f"📌 <b>Chi tiết:</b> {html.escape(details)}\n\n"
            f"💡 <i>Lưu ý: Hãy đảm bảo đây là link bài viết có đồng hồ đếm ngược (chứ không phải trang rút gọn giao nhiệm vụ).</i>"
        )
        await status_msg.edit_text(
            fail_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_fail_keyboard(url, is_task_shortener=False)
        )


async def key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ Vui lòng cung cấp link bài viết cần lấy Key!\nVí dụ: <code>/key https://tabare.com.co/vi-vn/</code>",
            parse_mode=ParseMode.HTML
        )
        return

    url = args[0].strip()

    # Kiểm tra chống spam yêu cầu mở trình duyệt
    allowed, wait_sec = check_rate_limit(user.id if user else 0, "key")
    if not allowed:
        await update.message.reply_text(
            f"⏳ <b>HỆ THỐNG ĐANG BẬN!</b>\n"
            f"Trình duyệt ảo cần thời gian nghỉ. Vui lòng chờ <b>{wait_sec}s</b> trước khi yêu cầu lấy key tiếp.",
            parse_mode=ParseMode.HTML
        )
        return

    status_msg = await update.message.reply_text(
        f"⏳ Đang khởi động trình duyệt ảo để lấy Key từ <code>{html.escape(url)}</code>...",
        parse_mode=ParseMode.HTML
    )
    await do_grab_key(status_msg, url, user.id if user else 0)


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Quét mã độc và virus của liên kết thông qua VirusTotal API v3 & Smart Heuristic Shield.
    """
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)

    # 1. Trích xuất URL từ args hoặc reply message
    target_url = None
    if context.args and len(context.args) > 0:
        target_url = context.args[0].strip()
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        found_urls = extract_urls(update.message.reply_to_message.text)
        if found_urls:
            target_url = found_urls[0]

    if not target_url:
        await update.message.reply_text(
            "🛡️ <b>HƯỚNG DẪN QUÉT BẢO MẬT VIRUSTOTAL SHIELD:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Kiểm tra độ an toàn của bất kỳ liên kết hoặc tệp tin nào trước khi tải về:\n\n"
            "• <b>Cách 1:</b> Gõ <code>/scan [link_cần_kiểm_tra]</code>\n"
            "  <i>(Ví dụ: <code>/scan https://example.com/setup.exe</code>)</i>\n\n"
            "• <b>Cách 2:</b> <b>Reply (trả lời)</b> bất kỳ tin nhắn nào chứa link và gõ <code>/scan</code>.\n\n"
            "⚡ <i>Hệ thống sẽ đối chiếu dữ liệu từ hơn 70 hãng bảo mật hàng đầu (Kaspersky, BitDefender, Microsoft Defender...)!</i>",
            parse_mode=ParseMode.HTML
        )
        return

    escaped_url = html.escape(target_url)
    status_msg = await update.message.reply_text(
        f"🛡️ Đang kiểm tra an toàn cho liên kết:\n<code>{escaped_url}</code>\n"
        f"<i>Đang gửi dữ liệu tới VirusTotal Security Shield...</i>",
        parse_mode=ParseMode.HTML
    )

    try:
        scan_res = await SecurityScanner.scan_url(target_url)

        risk_text = {
            "safe": "🟢 Rất thấp (An toàn)",
            "suspicious": "🟡 Trung bình (Cần cẩn trọng)",
            "danger": "🔴 RẤT CAO (Phát hiện mã độc/Lừa đảo!)"
        }.get(scan_res.risk_level, "🟢 An toàn")

        engine_info = f"<code>{scan_res.total_engines}</code> hệ thống" if scan_res.total_engines > 0 else "Smart Heuristic Engine"

        res_msg = (
            f"🛡️ <b>KẾT QUẢ PHÂN TÍCH BẢO MẬT (VIRUSTOTAL)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 <b>Liên kết:</b>\n<code>{escaped_url}</code>\n\n"
            f"📊 <b>Đánh giá:</b> {scan_res.scan_badge}\n"
            f"🎯 <b>Mức độ rủi ro:</b> <b>{risk_text}</b>\n"
            f"🔍 <b>Hệ thống bảo mật:</b> {engine_info}\n"
            f"🚨 <b>Phát hiện độc hại:</b> <code>{scan_res.malicious_count}</code>\n"
            f"⚠️ <b>Gắn cờ nghi vấn:</b> <code>{scan_res.suspicious_count}</code>\n\n"
            f"📌 <b>Chi tiết:</b>\n<i>{html.escape(scan_res.scan_details)}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>Mẹo: Tuyệt đối không mở các tệp tin lạ có cảnh báo nguy hiểm hoặc yêu cầu tắt Antivirus trên máy tính!</i>"
        )

        buttons = []
        if scan_res.report_url:
            buttons.append([InlineKeyboardButton("🛡️ Xem Chi Tiết Trên VirusTotal", url=scan_res.report_url)])
        if scan_res.is_safe:
            buttons.append([InlineKeyboardButton("🌐 Mở Liên Kết An Toàn", url=target_url)])

        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
        await status_msg.edit_text(res_msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"[Scan Command] Error: {e}")
        await status_msg.edit_text(
            f"⚠️ Có lỗi xảy ra trong quá trình quét bảo mật: <code>{html.escape(str(e))}</code>",
            parse_mode=ParseMode.HTML
        )
