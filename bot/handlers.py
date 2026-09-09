import os
import io
import asyncio
import html
import hashlib
import logging
from urllib.parse import urlparse, quote
from datetime import datetime, timezone, timedelta
from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from core.bypass_manager import BypassManager
from core.engine_traffic_key import grab_traffic_key
from core.database import (
    log_user,
    log_action,
    save_report,
    get_statistics,
    get_admin_id,
    set_admin_id,
    is_admin_user,
    get_all_user_ids,
    get_recent_reports,
    clear_all_reports,
    check_and_increment_quota,
    set_user_vip,
    remove_user_vip,
    get_user_vip_info,
    get_user_history,
    get_channel_fsub,
    set_channel_fsub,
    toggle_channel_fsub,
    process_referral,
    get_referral_stats,
    get_all_vip_users
)
from core.link_enricher import clean_url, fetch_file_metadata
from .utils import extract_urls
from .keyboards import (
    get_result_keyboard,
    get_fail_keyboard,
    get_url_from_key,
    get_main_menu_keyboard,
    get_dashboard_inline_keyboard,
    get_back_to_menu_keyboard,
    get_fsub_keyboard,
    get_referral_keyboard
)
from .anti_spam import check_rate_limit




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
        print(f"[FSub] Warning checking chat member {user_id} in {clean_chan}: {e}")
        return True, ""

ADMIN_ID = os.getenv("ADMIN_ID")

TASK_SHORTENER_DOMAINS = [
    "ontops.link", "ontop.link", "link1s.com", "link1s.net",
    "traffic123.net", "traffic123.org", "layma.net", "laylink.net"
]

WELCOME_MESSAGE = (
    "👋 <b>Chào mừng bạn đến với Bot Vượt Link & Tự Động Lấy Key Siêu Tốc!</b>\n\n"
    "🚀 <b>Các tính năng nổi bật:</b>\n"
    "1️⃣ <b>Vượt link rút gọn:</b> Hỗ trợ <code>Ouo.io</code>, <code>Link1s</code>, <code>MegaURL</code>, <code>Linkvertise</code>, <code>Bitly</code>, <code>TinyURL</code>, <code>Sub2Unlock</code>, Google Drive, Mediafire...\n"
    "2️⃣ <b>Tự động lấy Key/Mã 60s:</b> Gõ <code>/key [link_bài_viết]</code> hoặc dán link bài viết -> Bot tự mở trình duyệt ngầm, cuộn trang, chờ 60s và lấy mã cho bạn!\n"
    "3️⃣ <b>Xem danh sách dịch vụ:</b> Bấm nút <b>[🌐 Dịch Vụ Hỗ Trợ]</b> để xem toàn bộ danh sách.\n\n"
    "👉 <i>Hãy dán ngay 1 đường link vào đây để trải nghiệm nhé!</i>"
)

HELP_MESSAGE = (
    "📖 <b>HƯỚNG DẪN SỬ DỤNG CHI TIẾT:</b>\n\n"
    "🔹 <b>Vượt link rút gọn:</b> Dán bất kỳ link rút gọn nào vào chat -> Nhận link gốc trực tiếp.\n"
    "🔹 <b>Tự động lấy Mã / Key 60 giây:</b> Dán link bài viết hoặc gõ <code>/key [link_bài_viết]</code>\n"
    "🔹 <b>Xem danh sách link hỗ trợ:</b> Bấm <b>[🌐 Dịch Vụ Hỗ Trợ]</b> hoặc gõ <code>/services</code>\n"
    "🔹 <b>Xem ID Telegram của bạn:</b> Gõ <code>/myid</code>\n"
    "🔹 <b>Báo lỗi link hỏng:</b> Bấm nút <b>[📢 Báo Lỗi Cho Admin]</b> khi gặp link không vượt được."
)

SERVICES_MESSAGE = (
    "🌐 <b>DANH SÁCH DỊCH VỤ & LIÊN KẾT HỖ TRỢ (VIP PRO):</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📁 <b>Tải Trực Tiếp Siêu Tốc (Cloud Direct Download):</b>\n"
    "• <b>Terabox:</b> <code>terabox.com</code>, <code>1024tera</code>, <code>terasharelink</code>... (Tải Max Speed không cần cài app rác!)\n"
    "• <b>Google Drive:</b> Tự động tạo link tải trực tiếp 1-click\n"
    "• <b>Mediafire:</b> Bóc tách direct link tải nhanh không quảng cáo\n"
    "• <b>Pastebin:</b> Trích xuất nội dung raw / link đích\n\n"
    "🛡️ <b>Công Nghệ Vượt Cloudflare Turnstile & Multi-Step:</b>\n"
    "• Giả lập trình duyệt người thật (Stealth Browser) tự động vượt xác minh Cloudflare và tự bấm các bước tiếp tục.\n\n"
    "💰 <b>Trang Rút Gọn Kiếm Tiền:</b>\n"
    "• <b>Ouo:</b> <code>ouo.io</code>, <code>ouo.press</code>\n"
    "• <b>AdLinkFly:</b> <code>link1s</code>, <code>linkx</code>, <code>megaurl</code>, <code>droplink</code>, <code>shrtfly</code>...\n"
    "• <b>Quốc tế:</b> <code>linkvertise.com</code>, <code>work.ink</code>, <code>adfly</code>...\n"
    "• <b>Sub Kênh:</b> <code>sub2unlock.com</code>, <code>sub4unlock.com</code>...\n\n"
    "⚡ <b>Rút Gọn Redirect Siêu Tốc & SafeLink:</b>\n"
    "• <code>bit.ly</code>, <code>tinyurl.com</code>, <code>cutt.ly</code>, <code>shorturl.at</code>, <code>is.gd</code>...\n"
    "• <b>SafeLink / Query:</b> Tự động giải mã link giấu trong Base64, Hex\n"
    "• <b>Bộ nhớ đệm toàn cầu:</b> Trả kết quả trong 0.01 giây cho các link đã từng vượt!\n\n"
    "🔑 <b>Tự Động Lấy Key Đếm Ngược 60s:</b>\n"
    "• Mạng lưới: <code>layma.net</code>, <code>traffic123</code>, <code>tabare</code> và các bài viết Google yêu cầu chờ 60s lấy mã.\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👉 <i>Chỉ cần copy và dán bất kỳ link nào vào chat để Bot tự động xử lý!</i>"
)


def get_dashboard_text(user_name: str) -> str:
    return (
        "╔═══════════════════════════════╗\n"
        "║  ⚡ <b>LINK BYPASS & KEY AUTOMATION PRO</b> ║\n"
        "╚═══════════════════════════════╝\n\n"
        f"👋 Xin chào, <b>{html.escape(user_name)}</b>!\n\n"
        "🤖 Hệ thống giải mã liên kết rút gọn & bóc tách mã 60s tự động chạy 24/7 trên Cloud.\n\n"
        "💡 <b>Lựa chọn tính năng nhanh từ Menu bên dưới:</b>"
    )

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
                print(f"[Ref] Error handling referral start: {e}")

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

BATCH_MESSAGE = (
    "📁 <b>HƯỚNG DẪN VƯỢT LINK HÀNG LOẠT BẰNG FILE .TXT:</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Nếu bạn có nhiều link cần giải mã cùng lúc (ví dụ tải phim, game nhiều part, tài liệu):\n\n"
    "1️⃣ Tạo một file <b>.txt</b> trên điện thoại hoặc máy tính.\n"
    "2️⃣ Dán các đường link rút gọn vào file đó (mỗi link một dòng, tối đa <b>30 link</b> / lần).\n"
    "3️⃣ Gửi file <b>.txt</b> đó trực tiếp vào khung chat này!\n\n"
    "⚡ <i>Bot sẽ tự động giải mã toàn bộ và gửi lại cho bạn 1 file kết quả chứa sạch link gốc!</i>"
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

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    log_user(user.id, user.username, user.first_name)

    if not is_admin_user(user.id):
        await update.message.reply_text("⛔ Lệnh này chỉ dành riêng cho Admin quản trị Bot!")
        return

    stats = get_statistics()
    if not stats:
        await update.message.reply_text("Chưa có số liệu thống kê.")
        return

    stats_msg = (
        f"📊 <b>BẢNG THỐNG KÊ HOẠT ĐỘNG BOT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Người dùng:</b>\n"
        f"• Tổng số người dùng: <code>{stats.get('total_users', 0)}</code>\n"
        f"• Hoạt động hôm nay: <code>{stats.get('today_users', 0)}</code>\n"
        f"• Thành viên VIP: <code>{stats.get('total_vips', 0)}</code> người 👑\n\n"
        f"🔗 <b>Xử lý liên kết:</b>\n"
        f"• Tổng link đã xử lý: <code>{stats.get('total_links', 0)}</code>\n"
        f"• Link xử lý hôm nay: <code>{stats.get('today_links', 0)}</code>\n"
        f"• Vượt thành công: <code>{stats.get('success_links', 0)}</code> (<code>{stats.get('success_rate', 100)}%</code>)\n\n"
        f"🚨 <b>Báo cáo lỗi:</b>\n"
        f"• Tổng số link báo lỗi: <code>{stats.get('total_reports', 0)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <i>Trạng thái: Máy chủ đám mây đang chạy 24/7</i>\n\n"
        f"🛠️ <b>Lệnh Admin nhanh:</b>\n"
        f"• <code>/viplist</code> - Xem danh sách thành viên VIP\n"
        f"• <code>/setvip [id] [ngày]</code> - Cấp/Gia hạn quyền VIP\n"
        f"• <code>/removevip [id]</code> - Hủy trạng thái VIP\n"
        f"• <code>/broadcast [nội dung]</code> - Phát thông báo toàn server\n"
        f"• <code>/reports</code> - Xem danh sách link lỗi gần nhất"
    )
    stats_keyboard = [
        [
            InlineKeyboardButton("👑 Danh Sách VIP", callback_data="dash:admin_viplist"),
            InlineKeyboardButton("🚨 Link Báo Lỗi", callback_data="dash:admin_reports")
        ]
    ]
    await update.message.reply_text(
        stats_msg,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(stats_keyboard)
    )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Phát thông báo đến toàn bộ người dùng trong database.
    Hỗ trợ cả gửi text trực tiếp hoặc reply vào 1 tin nhắn (ảnh, video, văn bản, file) để copy.
    """
    user = update.effective_user
    if not user or not is_admin_user(user.id):
        await update.message.reply_text("⛔ Lệnh này chỉ dành riêng cho Admin quản trị Bot!")
        return

    replied = update.message.reply_to_message
    broadcast_text = " ".join(context.args) if context.args else ""

    if not replied and not broadcast_text:
        await update.message.reply_text(
            "📢 <b>HƯỚNG DẪN PHÁT THÔNG BÁO TOÀN SERVER (BROADCAST):</b>\n\n"
            "• <b>Cách 1 (Gửi văn bản):</b> Gõ <code>/broadcast [Nội dung thông báo]</code>\n"
            "• <b>Cách 2 (Gửi ảnh/tin nhắn mẫu):</b> Soạn tin nhắn (hoặc gửi ảnh kèm chú thích), sau đó <b>Reply</b> tin nhắn đó và gõ <code>/broadcast</code>.\n\n"
            "💡 <i>Bot sẽ sao chép nguyên vẹn tin nhắn đó và gửi đến tất cả thành viên trong hệ thống!</i>",
            parse_mode=ParseMode.HTML
        )
        return

    all_users = get_all_user_ids()
    total = len(all_users)
    if total == 0:
        await update.message.reply_text("⚠️ Chưa có người dùng nào trong cơ sở dữ liệu để gửi thông báo!")
        return

    status_msg = await update.message.reply_text(
        f"⏳ <b>ĐANG BẮT ĐẦU PHÁT THÔNG BÁO...</b>\n"
        f"👥 <b>Tổng số người nhận:</b> <code>{total}</code> tài khoản.",
        parse_mode=ParseMode.HTML
    )

    success_count = 0
    blocked_count = 0

    for idx, target_id in enumerate(all_users, 1):
        try:
            if replied:
                await context.bot.copy_message(
                    chat_id=target_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=replied.message_id
                )
            else:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"📢 <b>THÔNG BÁO TỪ QUẢN TRỊ VIÊN:</b>\n\n{html.escape(broadcast_text)}",
                    parse_mode=ParseMode.HTML
                )
            success_count += 1
        except Exception:
            blocked_count += 1

        if idx % 10 == 0 or idx == total:
            try:
                await status_msg.edit_text(
                    f"⏳ <b>ĐANG PHÁT THÔNG BÁO...</b>\n\n"
                    f"📊 <b>Tiến độ:</b> <code>{idx}/{total}</code>\n"
                    f"✅ <b>Thành công:</b> <code>{success_count}</code>\n"
                    f"⛔ <b>Bị chặn:</b> <code>{blocked_count}</code>",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass

        await asyncio.sleep(0.04)

    await status_msg.edit_text(
        f"🎉 <b>PHÁT THÔNG BÁO HOÀN TẤT!</b>\n\n"
        f"📊 <b>Tổng số:</b> <code>{total}</code> người dùng\n"
        f"✅ <b>Gửi thành công:</b> <code>{success_count}</code> (<code>{round(success_count/total*100, 1)}%</code>)\n"
        f"⛔ <b>Bị chặn / Thất bại:</b> <code>{blocked_count}</code>",
        parse_mode=ParseMode.HTML
    )

async def reports_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem danh sách các link lỗi người dùng đã báo cáo."""
    user = update.effective_user
    if not user or not is_admin_user(user.id):
        await update.message.reply_text("⛔ Lệnh này chỉ dành riêng cho Admin quản trị Bot!")
        return

    reports = get_recent_reports(limit=10)
    if not reports:
        await update.message.reply_text(
            "✅ <b>DANH SÁCH BÁO CÁO LỖI TRỐNG!</b>\n"
            "Hiện tại không có link lỗi nào cần xử lý.",
            parse_mode=ParseMode.HTML
        )
        return

    msg_lines = [
        "📋 <b>DANH SÁCH 10 BÁO CÁO LỖI GẦN NHẤT:</b>",
        "━━━━━━━━━━━━━━━━━━━━"
    ]
    for idx, r in enumerate(reports, 1):
        uname = f"@{r['username']}" if r.get('username') else f"ID: <code>{r.get('user_id')}</code>"
        time_str = str(r.get('created_at', ''))[:16]
        url_esc = html.escape(r.get('url', ''))
        msg_lines.append(f"<b>[{idx}]</b> 👤 {uname} (<i>{time_str}</i>)")
        msg_lines.append(f"🔗 <code>{url_esc}</code>\n")

    msg_lines.append("━━━━━━━━━━━━━━━━━━━━")
    msg_lines.append("💡 <i>Gõ <code>/clearreports</code> nếu muốn xóa sạch danh sách này.</i>")

    await update.message.reply_text("\n".join(msg_lines), parse_mode=ParseMode.HTML)

async def clear_reports_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xóa sạch danh sách báo cáo lỗi trong database."""
    user = update.effective_user
    if not user or not is_admin_user(user.id):
        await update.message.reply_text("⛔ Lệnh này chỉ dành riêng cho Admin quản trị Bot!")
        return
    clear_all_reports()
    await update.message.reply_text("🗑️ Đã xóa sạch toàn bộ danh sách báo cáo lỗi trong cơ sở dữ liệu!")

async def claimadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cho phép chủ sở hữu nhận quyền Admin nhanh chóng."""
    user = update.effective_user
    if not user:
        return

    current_admin = get_admin_id()
    if current_admin:
        if str(user.id) == current_admin:
            await update.message.reply_text(f"👑 Bạn hiện đang là Admin chính thức của Bot (ID: <code>{user.id}</code>)!", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("⛔ Bot đã có Admin quản trị. Bạn không thể nhận quyền này!", parse_mode=ParseMode.HTML)
        return

    set_admin_id(user.id)
    await update.message.reply_text(
        f"🎉 <b>XÁC NHẬN ADMIN THÀNH CÔNG!</b>\n\n"
        f"👑 Quản trị viên: <b>{html.escape(user.full_name)}</b> (ID: <code>{user.id}</code>)\n"
        f"🚀 Bạn đã được kích hoạt đầy đủ các quyền quản trị:\n"
        f"• <code>/broadcast</code> - Phát thông báo toàn server\n"
        f"• <code>/reports</code> - Xem danh sách link lỗi người dùng báo\n"
        f"• <code>/stats</code> - Bảng thống kê hệ thống\n"
        f"• <code>/setvip</code> - Cấp quyền VIP cho người dùng\n"
        f"• <code>/setchannel</code> - Cài đặt kênh bắt buộc tham gia\n"
        f"• <code>/togglefsub</code> - Bật/Tắt bắt buộc tham gia kênh\n"
        f"• Tự động nhận tin nhắn cảnh báo tức thì mỗi khi có người báo lỗi link!",
        parse_mode=ParseMode.HTML
    )

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

async def setvip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cấp hoặc gia hạn quyền VIP cho người dùng (Dành cho Admin)."""
    user = update.effective_user
    if not user or not is_admin_user(user.id):
        await update.message.reply_text("⛔ Lệnh này chỉ dành riêng cho Admin quản trị Bot!")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ <b>Cú pháp lệnh cấp VIP:</b>\n"
            "<code>/setvip [user_id] [số_ngày]</code>\n"
            "<i>Ví dụ: <code>/setvip 123456789 30</code> (cấp VIP 30 ngày)</i>",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        target_id = int(context.args[0].strip())
        days = int(context.args[1].strip())
        success = set_user_vip(target_id, days)
        if success:
            await update.message.reply_text(
                f"👑 <b>CẤP QUYỀN VIP THÀNH CÔNG!</b>\n"
                f"• Tài khoản ID: <code>{target_id}</code>\n"
                f"• Thời hạn: <b>{days} ngày</b>\n"
                f"• Quyền lợi: Vượt link không giới hạn, không bị bóp băng thông!",
                parse_mode=ParseMode.HTML
            )
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"🎉 <b>CHÚC MỪNG!</b>\nBạn vừa được Quản trị viên nâng cấp lên tài khoản 👑 <b>VIP Member ({days} ngày)</b>!\nBạn có thể vượt link không giới hạn từ bây giờ.",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
        else:
            await update.message.reply_text("❌ Không thể cấp VIP. Vui lòng kiểm tra lại ID!")
    except ValueError:
        await update.message.reply_text("❌ ID hoặc số ngày không hợp lệ. Vui lòng nhập số nguyên!")

async def removevip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hủy quyền VIP của người dùng (Dành cho Admin)."""
    user = update.effective_user
    if not user or not is_admin_user(user.id):
        await update.message.reply_text("⛔ Lệnh này chỉ dành riêng cho Admin quản trị Bot!")
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Cú pháp lệnh hủy VIP:</b>\n"
            "<code>/removevip [user_id]</code>",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        target_id = int(context.args[0].strip())
        remove_user_vip(target_id)
        await update.message.reply_text(f"🗑️ Đã hủy trạng thái VIP của tài khoản ID: <code>{target_id}</code>.", parse_mode=ParseMode.HTML)
    except ValueError:
        await update.message.reply_text("❌ ID không hợp lệ!")

async def viplist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem danh sách các thành viên VIP hiện tại (Dành cho Admin)."""
    user = update.effective_user
    if not user or not is_admin_user(user.id):
        await update.message.reply_text("⛔ Lệnh này chỉ dành riêng cho Admin quản trị Bot!")
        return

    vips = get_all_vip_users()
    if not vips:
        await update.message.reply_text(
            "👑 <b>DANH SÁCH THÀNH VIÊN VIP</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✨ <i>Hiện tại chưa có người dùng nào được kích hoạt quyền VIP.</i>\n\n"
            "💡 <i>Dùng lệnh <code>/setvip [user_id] [số_ngày]</code> để cấp quyền VIP cho thành viên!</i>",
            parse_mode=ParseMode.HTML
        )
        return

    msg = (
        f"👑 <b>DANH SÁCH THÀNH VIÊN VIP ({len(vips)} người)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )
    for idx, v in enumerate(vips, 1):
        u_tag = f"@{v['username']}" if v['username'] else "<i>(Không username)</i>"
        msg += (
            f"<b>{idx}. {html.escape(v['first_name'])}</b> ({u_tag})\n"
            f"• Telegram ID: <code>{v['user_id']}</code> <i>(chạm để sao chép)</i>\n"
            f"• Thời hạn VIP: <b>{v['vip_until']}</b> (còn <b>{v['days_left']} ngày</b>)\n"
            f"• Đã vượt hôm nay: <b>{v['today_count']} link</b>\n\n"
        )
    msg += (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🛠️ <b>Thao tác nhanh cho Admin:</b>\n"
        "• Gia hạn/Cấp VIP: <code>/setvip [id] [ngày]</code>\n"
        "• Hủy quyền VIP: <code>/removevip [id]</code>"
    )

    keyboard = [
        [InlineKeyboardButton("🔄 Làm Mới", callback_data="dash:admin_viplist")],
        [InlineKeyboardButton("📊 Thống Kê Chung", callback_data="dash:stats")]
    ]
    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def setchannel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cài đặt Kênh Telegram bắt buộc người dùng tham gia (Dành cho Admin)."""
    user = update.effective_user
    if not user or not is_admin_user(user.id):
        await update.message.reply_text("⛔ Lệnh này chỉ dành riêng cho Admin quản trị Bot!")
        return

    if not context.args:
        curr_chan, is_en = get_channel_fsub()
        status_txt = "🟢 ĐANG BẬT" if is_en else "🔴 ĐANG TẮT"
        await update.message.reply_text(
            f"📢 <b>CẤU HÌNH KÊNH BẮT BUỘC THAM GIA:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• Kênh hiện tại: <code>{curr_chan or 'Chưa cài đặt'}</code>\n"
            f"• Trạng thái: <b>{status_txt}</b>\n\n"
            f"👉 <b>Cú pháp đổi kênh:</b> <code>/setchannel @ten_kenh_cua_ban</code>\n"
            f"👉 <b>Bật/Tắt chế độ:</b> <code>/togglefsub</code>\n\n"
            f"⚠️ <i>Lưu ý: Bạn phải thêm Bot làm Quản trị viên (Admin) của Kênh đó thì Bot mới kiểm tra được thành viên!</i>",
            parse_mode=ParseMode.HTML
        )
        return

    new_channel = context.args[0].strip()
    if not new_channel.startswith("@") and not new_channel.startswith("-100"):
        new_channel = f"@{new_channel}"
    set_channel_fsub(new_channel, enabled=True)
    await update.message.reply_text(
        f"✅ <b>ĐÃ CÀI ĐẶT KÊNH THÀNH CÔNG!</b>\n"
        f"• Kênh bắt buộc: <code>{new_channel}</code>\n"
        f"• Trạng thái: <b>🟢 ĐÃ BẬT</b>\n\n"
        f"💡 <i>Nhớ thêm @N1_link_bot làm Quản trị viên trong kênh {new_channel} nhé!</i>",
        parse_mode=ParseMode.HTML
    )

async def togglefsub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bật / Tắt nhanh chế độ bắt buộc tham gia kênh (Dành cho Admin)."""
    user = update.effective_user
    if not user or not is_admin_user(user.id):
        await update.message.reply_text("⛔ Lệnh này chỉ dành riêng cho Admin quản trị Bot!")
        return

    new_state = toggle_channel_fsub()
    curr_chan, _ = get_channel_fsub()
    await update.message.reply_text(
        f"📢 <b>CHẾ ĐỘ BẮT BUỘC THAM GIA KÊNH:</b>\n"
        f"• Kênh: <code>{curr_chan or 'Chưa cài đặt'}</code>\n"
        f"• Trạng thái mới: <b>{'🟢 ĐÃ BẬT' if new_state else '🔴 ĐÃ TẮT'}</b>",
        parse_mode=ParseMode.HTML
    )

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

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)

    await query.answer()
    data = query.data or ""

    # Xử lý Bảng Điều Khiển Interactive Dashboard (chuyển trang ngay tại chỗ)
    if data.startswith("dash:"):
        action = data[5:]
        is_admin = bool(user and str(user.id) == os.getenv("ADMIN_ID", "").strip())
        name = user.first_name if user and user.first_name else "bạn"

        if action in ["menu", "refresh"]:
            await query.edit_message_text(
                get_dashboard_text(name),
                parse_mode=ParseMode.HTML,
                reply_markup=get_dashboard_inline_keyboard(is_admin)
            )
        elif action == "help":
            await query.edit_message_text(
                HELP_MESSAGE,
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_to_menu_keyboard()
            )
        elif action == "key":
            key_info = (
                "🔑 <b>HƯỚNG DẪN TỰ ĐỘNG LẤY MÃ ĐẾM NGƯỢC 60 GIÂY:</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Khi trang rút gọn yêu cầu bạn tìm Google để vào 1 trang bài viết lấy mã:\n\n"
                "👉 <b>Cách 1 (Nhanh nhất):</b> Bạn chỉ cần copy link bài viết đó và <b>dán thẳng vào chat</b>. Bot sẽ tự động hiện nút <code>[🔑 Tự Động Lấy Key Trên Web Này]</code> để bạn bấm!\n\n"
                "👉 <b>Cách 2:</b> Gõ theo cú pháp lệnh:\n"
                "<code>/key [link_bài_viết]</code>\n"
                "<i>(Ví dụ: <code>/key https://tabare.com.co/vi-vn/</code>)</i>\n\n"
                "⚡ <i>Bot sẽ tự động mở trình duyệt ngầm, cuộn trang, chờ đếm ngược 60s và trả mã ngay cho bạn!</i>"
            )
            await query.edit_message_text(
                key_info,
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_to_menu_keyboard()
            )
        elif action == "batch":
            await query.edit_message_text(
                BATCH_MESSAGE,
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_to_menu_keyboard()
            )
        elif action == "services":
            await query.edit_message_text(
                SERVICES_MESSAGE,
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_to_menu_keyboard()
            )
        elif action == "history":
            history = get_user_history(user.id if user else 0, limit=5)
            if not history:
                hist_text = (
                    "📋 <b>LỊCH SỬ VƯỢT LINK CỦA BẠN</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "✨ <i>Bạn chưa vượt link nào gần đây! Hãy gửi link vào đây để trải nghiệm nhé.</i>"
                )
            else:
                hist_text = (
                    "📋 <b>5 LINK VƯỢT THÀNH CÔNG GẦN NHẤT:</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                )
                for idx, item in enumerate(history, 1):
                    hist_text += (
                        f"<b>{idx}. {item['created_at'][:16]}</b> (⚡ <i>{html.escape(item['engine'])}</i>):\n"
                        f"🔗 <b>Gốc:</b> <code>{html.escape(item['url'])}</code>\n"
                        f"🎯 <b>Đích:</b> <code>{html.escape(item['result_url'])}</code>\n\n"
                    )
            keyboard = [
                [InlineKeyboardButton("🔄 Làm Mới", callback_data="dash:history")],
                [InlineKeyboardButton("◀️ Quay Lại Menu", callback_data="dash:back")]
            ]
            await query.edit_message_text(
                hist_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif action == "myid":
            vip_info = get_user_vip_info(user.id if user else 0)
            if is_admin:
                rank_str = "👑 Admin Quản Trị Tối Cao"
                quota_str = "♾️ Không giới hạn"
            elif vip_info["is_vip"]:
                until_disp = str(vip_info['vip_until'])[:10] if vip_info['vip_until'] else "Vô thời hạn"
                rank_str = f"👑 VIP Member (Đến: {until_disp})"
                quota_str = "♾️ Không giới hạn"
            else:
                rank_str = "👤 Thành Viên Miễn Phí"
                quota_str = f"{vip_info['remaining_today']}/30 lượt còn lại hôm nay"

            myid_text = (
                f"🆔 <b>THÔNG TIN TÀI KHOẢN CỦA BẠN:</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Tên:</b> {html.escape(user.full_name or '')}\n"
                f"🔹 <b>Telegram ID:</b> <code>{user.id}</code>\n"
                f"🎖️ <b>Cấp bậc:</b> <b>{rank_str}</b>\n"
                f"📊 <b>Hạn mức:</b> <code>{quota_str}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 <i>Chạm vào ID để tự động sao chép.</i>"
            )
            await query.edit_message_text(
                myid_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_to_menu_keyboard()
            )
        elif action == "report_info":
            report_info = (
                "📢 <b>HƯỚNG DẪN BÁO LỖI LINK CHO ADMIN:</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Khi bạn gửi link mà bot không vượt được hoặc trang bị lỗi:\n"
                "• Bot sẽ lập tức hiển thị nút bấm <b>[📢 Báo Lỗi Link Này Cho Admin]</b>.\n"
                "• Khi bạn chạm vào nút đó, link lỗi sẽ được gửi trực tiếp đến Admin để nâng cấp bộ giải mã sớm nhất!\n\n"
                "💡 <i>Hãy thử dán bất kỳ link nào vào đây để trải nghiệm nhé!</i>"
            )
            await query.edit_message_text(
                report_info,
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_to_menu_keyboard()
            )
        elif action == "ref":
            stats = get_referral_stats(user.id if user else 0)
            ref_link = f"https://t.me/N1_link_bot?start=ref_{user.id if user else 0}"
            msg = (
                "🎁 <b>CHƯƠNG TRÌNH MỜI BẠN BÈ - NHẬN VIP MIỄN PHÍ</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Chia sẻ đường link riêng của bạn cho bạn bè, hội nhóm. Càng mời nhiều, thời hạn VIP càng khủng!\n\n"
                "🔗 <b>Link giới thiệu của bạn:</b>\n"
                f"👉 <code>{ref_link}</code> 👈\n\n"
                "📊 <b>Tiến trình của bạn:</b>\n"
                f"• Đã mời thành công: <b>{stats['total_refs']} người</b>\n"
                f"• Mốc tiếp theo: <b>{stats['target']} người</b> (🎁 Nhận <b>{stats['reward_days']} ngày VIP</b>)\n"
                f"• Cần mời thêm: <b>{stats['needed']} người nữa</b>\n\n"
                "🏆 <b>MỐC THƯỞNG VIP:</b>\n"
                "• Mời 3 bạn ➔ Tặng 3 ngày VIP\n"
                "• Mời 5 bạn ➔ Tặng 5 ngày VIP\n"
                "• Mời 10 bạn ➔ Tặng 15 ngày VIP\n"
                "• Mời 20 bạn ➔ Tặng 30 ngày VIP (1 tháng)\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "💡 <i>Bấm nút bên dưới để chia sẻ 1-Click ngay cho bạn bè!</i>"
            )
            await query.edit_message_text(
                msg,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=get_referral_keyboard(user.id if user else 0)
            )
        elif action == "stats":
            if not is_admin:
                await query.answer("⛔ Mục này chỉ dành riêng cho Admin quản trị Bot!", show_alert=True)
                return
            stats = get_statistics()
            stats_msg = (
                f"📊 <b>BẢNG THỐNG KÊ HOẠT ĐỘNG BOT</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👥 <b>Người dùng:</b>\n"
                f"• Tổng số người dùng: <code>{stats.get('total_users', 0)}</code>\n"
                f"• Hoạt động hôm nay: <code>{stats.get('today_users', 0)}</code>\n"
                f"• Thành viên VIP: <code>{stats.get('total_vips', 0)}</code> người 👑\n\n"
                f"🔗 <b>Xử lý liên kết:</b>\n"
                f"• Tổng link đã xử lý: <code>{stats.get('total_links', 0)}</code>\n"
                f"• Link xử lý hôm nay: <code>{stats.get('today_links', 0)}</code>\n"
                f"• Vượt thành công: <code>{stats.get('success_links', 0)}</code> (<code>{stats.get('success_rate', 100)}%</code>)\n\n"
                f"🚨 <b>Báo cáo lỗi:</b>\n"
                f"• Tổng số link báo lỗi: <code>{stats.get('total_reports', 0)}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🟢 <i>Trạng thái: Máy chủ đám mây đang chạy 24/7</i>"
            )
            stats_keyboard = [
                [
                    InlineKeyboardButton("👑 Danh Sách VIP", callback_data="dash:admin_viplist"),
                    InlineKeyboardButton("🚨 Danh Sách Báo Lỗi", callback_data="dash:admin_reports")
                ],
                [InlineKeyboardButton("◀️ Quay Lại Menu", callback_data="dash:back")]
            ]
            await query.edit_message_text(
                stats_msg,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(stats_keyboard)
            )
        elif action == "admin_reports":
            if not is_admin:
                await query.answer("⛔ Mục này chỉ dành riêng cho Admin quản trị Bot!", show_alert=True)
                return
            reports = get_recent_reports(limit=10)
            if not reports:
                rep_text = (
                    "📋 <b>DANH SÁCH BÁO CÁO LỖI GẦN ĐÂY</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "✨ <i>Hiện tại không có báo cáo lỗi nào cần xử lý! Bot đang hoạt động rất tốt.</i>"
                )
            else:
                rep_text = (
                    f"📋 <b>10 BÁO CÁO LỖI GẦN NHẤT:</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                )
                for idx, r in enumerate(reports, 1):
                    u_info = f"@{r['username']}" if r['username'] else f"ID: {r['user_id']}"
                    rep_text += (
                        f"<b>{idx}. {u_info}</b> ({r['reported_at']}):\n"
                        f"👉 <code>{html.escape(r['broken_url'])}</code>\n\n"
                    )
                rep_text += "💡 <i>Gõ lệnh <code>/clearreports</code> để xóa sạch danh sách khi đã xử lý xong.</i>"

            keyboard = [
                [InlineKeyboardButton("🔄 Làm Mới", callback_data="dash:admin_reports")],
                [InlineKeyboardButton("◀️ Trở Lại Thống Kê", callback_data="dash:stats")],
                [InlineKeyboardButton("🏠 Menu Chính", callback_data="dash:back")]
            ]
            await query.edit_message_text(
                rep_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif action == "admin_viplist":
            if not is_admin:
                await query.answer("⛔ Mục này chỉ dành riêng cho Admin quản trị Bot!", show_alert=True)
                return
            vips = get_all_vip_users()
            if not vips:
                vip_text = (
                    "👑 <b>DANH SÁCH THÀNH VIÊN VIP</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "✨ <i>Hiện tại chưa có người dùng nào được kích hoạt quyền VIP.</i>\n\n"
                    "💡 <i>Dùng lệnh <code>/setvip [user_id] [số_ngày]</code> để cấp quyền VIP cho thành viên!</i>"
                )
            else:
                vip_text = (
                    f"👑 <b>DANH SÁCH THÀNH VIÊN VIP ({len(vips)} người):</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                )
                for idx, v in enumerate(vips, 1):
                    u_tag = f"@{v['username']}" if v['username'] else "<i>(Không username)</i>"
                    vip_text += (
                        f"<b>{idx}. {html.escape(v['first_name'])}</b> ({u_tag})\n"
                        f"• Telegram ID: <code>{v['user_id']}</code> <i>(chạm để sao chép)</i>\n"
                        f"• Hết hạn: <b>{v['vip_until']}</b> (còn <b>{v['days_left']} ngày</b>)\n"
                        f"• Vượt hôm nay: <b>{v['today_count']} link</b>\n\n"
                    )
                vip_text += (
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "🛠️ <b>Lệnh Admin nhanh:</b>\n"
                    "• <code>/setvip [id] [ngày]</code>\n"
                    "• <code>/removevip [id]</code>"
                )
            vip_keyboard = [
                [InlineKeyboardButton("🔄 Làm Mới", callback_data="dash:admin_viplist")],
                [InlineKeyboardButton("◀️ Trở Lại Thống Kê", callback_data="dash:stats")],
                [InlineKeyboardButton("🏠 Menu Chính", callback_data="dash:back")]
            ]
            await query.edit_message_text(
                vip_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(vip_keyboard)
            )
        return

    # Xử lý nút Lấy Key
    if data.startswith("getkey:"):
        short_key = data[7:]
        url = get_url_from_key(short_key) or short_key

        # Kiểm tra chống spam lấy key qua nút bấm
        allowed, wait_sec = check_rate_limit(user.id if user else 0, "key")
        if not allowed:
            await query.message.reply_text(
                f"⏳ <b>HỆ THỐNG ĐANG BẬN!</b>\n"
                f"Trình duyệt ảo cần thời gian nghỉ. Vui lòng chờ <b>{wait_sec}s</b> trước khi bấm lấy key tiếp.",
                parse_mode=ParseMode.HTML
            )
            return

        status_msg = await query.message.reply_text(
            f"⏳ Đang khởi động trình duyệt ảo để lấy Key từ <code>{html.escape(url)}</code>...",
            parse_mode=ParseMode.HTML
        )
        await do_grab_key(status_msg, url, user.id if user else 0)

    # Xử lý nút Tạo Mã QR
    elif data.startswith("qr:"):
        short_key = data[3:]
        url = get_url_from_key(short_key) or short_key
        quoted_url = quote(url, safe="")
        qr_img_url = f"https://api.qrserver.com/v1/create-qr-code/?size=350x350&data={quoted_url}"
        try:
            await query.answer("📱 Đang tạo ảnh mã QR...")
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=qr_img_url,
                caption=(
                    f"📱 <b>MÃ QR CODE CHO ĐƯỜNG LINK ĐÍCH:</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔗 <code>{html.escape(url)}</code>\n\n"
                    f"👉 <i>Hãy mở camera điện thoại hoặc app Zalo / Google Lens để quét truy cập ngay nhé!</i>"
                ),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            print(f"[QR] Error sending QR code: {e}")
            await query.message.reply_text(f"⚠️ Không thể tạo ảnh QR: {e}")

    # Xử lý xác minh tham gia Kênh Telegram (Force Subscribe)
    elif data == "fsub:verify":
        is_sub, _ = await check_user_fsub(user.id if user else 0, context)
        if is_sub:
            await query.answer("🎉 Chúc mừng! Bạn đã tham gia kênh thành công.", show_alert=True)
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=user.id if user else 0,
                text="✅ <b>XÁC THỰC THÀNH CÔNG!</b>\nBạn đã mở khóa toàn bộ tính năng. Hãy dán bất kỳ link nào vào đây để bắt đầu vượt nhé!",
                parse_mode=ParseMode.HTML
            )
        else:
            await query.answer("⚠️ Bạn vẫn chưa tham gia kênh! Vui lòng bấm vào nút 'Tham Gia Kênh Telegram' phía trên trước nhé.", show_alert=True)

    # Xử lý nút Báo lỗi link cho Admin
    elif data.startswith("report:"):
        short_key = data[7:]
        url = get_url_from_key(short_key) or short_key
        
        save_report(user.id if user else 0, user.username if user else "", url)

        # Gửi thông báo đến Admin nếu có cấu hình ADMIN_ID hoặc đã claim
        admin_id_str = get_admin_id()
        if admin_id_str:
            try:
                vn_tz = timezone(timedelta(hours=7))
                now_str = datetime.now(vn_tz).strftime("%H:%M:%S - %d/%m/%Y")
                admin_alert = (
                    f"🚨 <b>BÁO CÁO LINK LỖI TỪ NGƯỜI DÙNG!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>Người báo:</b> @{user.username or 'Không có'} (ID: <code>{user.id}</code>)\n"
                    f"🔗 <b>Link lỗi:</b>\n<code>{html.escape(url)}</code>\n"
                    f"⏱️ <b>Thời gian:</b> <code>{now_str}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👉 Hãy kiểm tra để nâng cấp thêm engine cho link này!"
                )
                alert_keyboard = None
                if url.startswith("http://") or url.startswith("https://"):
                    alert_keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔗 Mở Thử Link", url=url)]
                    ])
                await context.bot.send_message(
                    chat_id=int(admin_id_str),
                    text=admin_alert,
                    parse_mode=ParseMode.HTML,
                    reply_markup=alert_keyboard
                )
            except Exception as e:
                print(f"[Report] Error alerting admin: {e}")

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "✅ <b>ĐÃ GỬI BÁO CÁO THÀNH CÔNG!</b>\n"
            "Cảm ơn bạn, link này đã được gửi trực tiếp cho Admin để kiểm tra và cập nhật bộ giải mã sớm nhất.",
            parse_mode=ParseMode.HTML
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if user:
        log_user(user.id, user.username, user.first_name)

    is_group = bool(chat and chat.type in ["group", "supergroup"])
    is_admin = is_admin_user(user.id if user else None)

    text = update.message.text
    if not text:
        if update.message.document:
            await handle_document(update, context)
        return

    clean_text = text.strip()
    urls = extract_urls(text)

    # Trong Nhóm Chat: Nếu không có đường link nào thì bỏ qua (không trả lời tin nhắn thường tránh làm phiền nhóm)
    if is_group and not urls:
        return

    # 1. Bắt các nút bấm từ bàn phím Menu (chỉ trong chat riêng với bot)
    if not is_group:
        if clean_text in ["⚡ Vượt Link", "📖 Hướng Dẫn Vượt Link", "📖 Hướng Dẫn"]:
            await help_command(update, context)
            return
        elif clean_text in ["📁 Vượt File .txt", "📁 Vượt Link File .txt"]:
            await batch_command(update, context)
            return
        elif clean_text in ["🌐 Dịch Vụ", "🌐 Dịch Vụ Hỗ Trợ"]:
            await services_command(update, context)
            return
        elif clean_text in ["🔑 Lấy Mã 60s", "🔑 Cách Lấy Mã 60s"]:
            msg = (
                "🔑 <b>HƯỚNG DẪN TỰ ĐỘNG LẤY MÃ ĐẾM NGƯỢC 60 GIÂY:</b>\n\n"
                "Khi trang rút gọn yêu cầu bạn tìm Google để vào 1 trang bài viết lấy mã:\n\n"
                "👉 <b>Cách 1 (Nhanh nhất):</b> Bạn chỉ cần copy link bài viết đó và <b>dán thẳng vào đây</b>. Bot sẽ tự động hiện nút <code>[🔑 Tự Động Lấy Key Trên Web Này]</code> để bạn bấm!\n\n"
                "👉 <b>Cách 2:</b> Gõ theo cú pháp lệnh:\n"
                "<code>/key [link_bài_viết]</code>\n"
                "<i>(Ví dụ: <code>/key https://tabare.com.co/vi-vn/</code>)</i>\n\n"
                "⚡ <i>Bot sẽ tự động mở trình duyệt ngầm, cuộn trang, chờ đếm ngược 60s và gửi mã kích hoạt lại cho bạn!</i>"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            return
        elif clean_text in ["📋 Lịch Sử", "📋 Lịch Sử Vượt", "📋 Lịch Sử Vượt Link"]:
            await history_command(update, context)
            return
        elif clean_text in ["🎁 Mời Bạn (VIP)", "🎁 Mời Bạn Bè", "🎁 Mời Bạn - Nhận VIP"]:
            await ref_command(update, context)
            return
        elif clean_text in ["📊 Thống Kê (Admin)", "📊 Thống Kê"]:
            await stats_command(update, context)
            return
        elif clean_text in ["🆔 ID Của Tôi", "🆔 ID"]:
            await myid_command(update, context)
            return
        elif clean_text in ["📢 Hỗ Trợ", "📢 Hỗ Trợ / Báo Lỗi"]:
            msg = (
                "📢 <b>HỖ TRỢ & BÁO LỖI LINK:</b>\n\n"
                "• Nếu bạn gặp link rút gọn nào bot chưa giải mã được, bạn chỉ cần gửi link đó vào khung chat.\n"
                "• Bot sẽ lập tức hiển thị nút <b>[📢 Báo Lỗi Link Này Cho Admin]</b>.\n"
                "• Khi bạn chạm vào nút đó, link lỗi sẽ được gửi trực tiếp đến Admin để nâng cấp bộ giải mã!\n\n"
                "💡 <i>Hãy thử dán bất kỳ link nào vào đây để trải nghiệm nhé!</i>"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            return

    if not urls:
        await update.message.reply_text(
            "⚠️ Mình không tìm thấy đường link nào trong tin nhắn của bạn. Vui lòng gửi một liên kết hợp lệ (ví dụ: <code>https://...</code>)!",
            parse_mode=ParseMode.HTML
        )
        return

    # 2. Kiểm tra bắt buộc tham gia Kênh Telegram (Force Channel Subscribe - chỉ áp dụng chat cá nhân)
    if not is_group and not is_admin:
        is_sub, chan_url = await check_user_fsub(user.id if user else 0, context)
        if not is_sub:
            await update.message.reply_text(
                "📢 <b>BẠN CẦN THAM GIA KÊNH ĐỂ SỬ DỤNG BOT!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Để tiếp tục sử dụng các dịch vụ vượt link miễn phí tốc độ cao, vui lòng nhấn nút tham gia kênh chính thức bên dưới:\n\n"
                "👉 <i>Sau khi tham gia xong, hãy bấm nút <b>'Tôi Đã Tham Gia Xong'</b> để mở khóa ngay nhé!</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_fsub_keyboard(chan_url)
            )
            return

    # 3. Kiểm tra hạn mức trong ngày (Daily Quota)
    allowed, remaining, is_vip = check_and_increment_quota(user.id if user else 0, is_admin=is_admin)
    if not allowed:
        await update.message.reply_text(
            "⚠️ <b>BẠN ĐÃ DÙNG HẾT HẠN MỨC HÔM NAY!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Mỗi tài khoản miễn phí được tặng <b>30 lượt vượt link/ngày</b>.\n"
            "• Hạn mức của bạn sẽ tự động được làm mới vào lúc <b>00:00 (nửa đêm)</b>.\n"
            "• Hoặc liên hệ Admin để nâng cấp gói 👑 <b>VIP Member</b> không giới hạn!",
            parse_mode=ParseMode.HTML
        )
        return

    # 4. Kiểm tra chống spam gửi link
    allowed_spam, wait_sec = check_rate_limit(user.id if user else 0, "message")
    if not allowed_spam:
        await update.message.reply_text(
            f"⏳ <b>BẠN THAO TÁC QUÁ NHANH!</b>\n"
            f"Vui lòng chờ <b>{wait_sec}s</b> nữa trước khi gửi link tiếp theo để tránh quá tải máy chủ.",
            parse_mode=ParseMode.HTML
        )
        return

    if len(urls) > 3:
        await update.message.reply_text("ℹ️ Bạn gửi nhiều link quá! Bot sẽ xử lý trước 3 link đầu tiên nhé.")
        urls = urls[:3]

    for url in urls:
        escaped_url = html.escape(url)
        domain = urlparse(url).netloc.lower()

        # Kiểm tra nếu gửi link rút gọn giao nhiệm vụ
        if any(td in domain for td in TASK_SHORTENER_DOMAINS):
            task_msg = (
                f"ℹ️ <b>ĐÂY LÀ TRANG RÚT GỌN GIAO NHIỆM VỤ!</b>\n\n"
                f"🔗 <b>Link:</b> <code>{escaped_url}</code>\n\n"
                f"📝 Trang này là nơi <b>NHẬP MÃ</b> (nó yêu cầu bạn tìm kiếm Google để vào 1 trang web bài viết khác).\n\n"
                f"👉 <b>Cách làm đúng:</b> Bạn hãy copy đường link của <b>trang bài viết</b> mà trang này yêu cầu vào, sau đó gửi cho bot theo cú pháp:\n"
                f"<code>/key [link_bài_viết]</code>\n"
                f"<i>(Bot sẽ tự vào trang bài viết đó đợi 60s và lấy mã giúp bạn!)</i>"
            )
            await update.message.reply_text(
                task_msg,
                parse_mode=ParseMode.HTML,
                reply_markup=get_fail_keyboard(url, is_task_shortener=True)
            )
            continue

        status_msg = await update.message.reply_text(
            f"⏳ Đang kiểm tra liên kết: <code>{escaped_url}</code>\nVui lòng chờ trong giây lát...",
            parse_mode=ParseMode.HTML
        )

        try:
            result = await BypassManager.bypass(url)

            if result.success:
                # 5. Lọc sạch URL Anti-Tracking & Xem trước thông tin tệp
                clean_target = clean_url(result.result_url)
                meta = await fetch_file_metadata(clean_target)
                file_info_str = ""
                if meta.get("has_info"):
                    file_info_str = f"📁 <b>Tệp tin:</b> <code>{html.escape(meta['file_name'])}</code> ({meta['file_size']})\n"

                log_action(user.id if user else 0, url, "bypass", "success", result.engine_used, result_url=clean_target)

                quota_str = ""
                if not is_vip and not is_admin:
                    quota_str = f"\n📊 <i>Hạn mức còn lại hôm nay: {remaining}/30 lượt</i>"

                msg_text = (
                    f"✅ <b>VƯỢT LINK THÀNH CÔNG!</b>\n\n"
                    f"🔗 <b>Link ban đầu:</b>\n<code>{html.escape(result.original_url)}</code>\n\n"
                    f"🎯 <b>Link đích:</b>\n<code>{html.escape(clean_target)}</code>\n\n"
                    f"{file_info_str}"
                    f"⚡ <b>Phương thức:</b> <code>{html.escape(result.engine_used)}</code>\n"
                    f"⏱️ <b>Thời gian xử lý:</b> <code>{result.time_taken}s</code>"
                    f"{quota_str}"
                )
                await status_msg.edit_text(
                    msg_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_result_keyboard(clean_target)
                )
            else:
                log_action(user.id if user else 0, url, "bypass", "fail")
                fail_text = (
                    f"ℹ️ <b>ĐÂY CÓ THỂ LÀ TRANG WEB BÀI VIẾT LÀM NHIỆM VỤ LẤY MÃ</b>\n\n"
                    f"🔗 <b>Link:</b> <code>{escaped_url}</code>\n\n"
                    f"👉 Nếu đây là trang web có nút đếm ngược 60s để lấy Key kích hoạt, hãy bấm nút dưới đây để Bot tự động vào lấy mã giúp bạn!"
                )
                await status_msg.edit_text(
                    fail_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_fail_keyboard(url, is_task_shortener=False)
                )
        except Exception as e:
            await status_msg.edit_text(
                f"⚠️ Có lỗi phát sinh khi xử lý: <code>{html.escape(str(e))}</code>",
                parse_mode=ParseMode.HTML
            )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Xử lý file .txt chứa danh sách nhiều link rút gọn và xuất file kết quả.
    """
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)

    doc = update.message.document
    if not doc:
        return

    # 1. Kiểm tra định dạng file
    file_name = doc.file_name or "links.txt"
    if not file_name.lower().endswith(".txt"):
        await update.message.reply_text(
            "⚠️ Bot hiện chỉ hỗ trợ xử lý hàng loạt qua file văn bản định dạng <b>.txt</b>!\nVui lòng lưu danh sách link vào file <code>.txt</code> rồi gửi lại nhé.",
            parse_mode=ParseMode.HTML
        )
        return

    # 2. Kiểm tra dung lượng file (tối đa 1MB)
    if doc.file_size and doc.file_size > 1024 * 1024:
        await update.message.reply_text("⚠️ File quá lớn (tối đa 1MB). Vui lòng chia nhỏ file và gửi lại.")
        return

    # 3. Kiểm tra chống spam gửi file
    allowed, wait_sec = check_rate_limit(user.id if user else 0, "batch")
    if not allowed:
        await update.message.reply_text(
            f"⏳ <b>BẠN GỬI FILE QUÁ NHANH!</b>\n"
            f"Vui lòng chờ <b>{wait_sec}s</b> nữa trước khi gửi file tiếp theo để hệ thống xử lý ổn định.",
            parse_mode=ParseMode.HTML
        )
        return

    status_msg = await update.message.reply_text(
        f"📥 Đang tải và kiểm tra file <code>{html.escape(file_name)}</code>...",
        parse_mode=ParseMode.HTML
    )

    try:
        # Tải file về bộ nhớ RAM
        tg_file = await context.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        
        # Đọc nội dung file với nhiều bảng mã
        text_content = ""
        for enc in ["utf-8", "utf-16", "latin-1", "cp1252"]:
            try:
                text_content = file_bytes.decode(enc)
                break
            except Exception:
                continue

        if not text_content:
            await status_msg.edit_text("⚠️ Không thể đọc nội dung file văn bản này.")
            return

        urls = extract_urls(text_content)
        if not urls:
            await status_msg.edit_text(
                "⚠️ Không tìm thấy bất kỳ đường link (URL) hợp lệ nào trong file bạn vừa gửi!\nHãy đảm bảo các link bắt đầu bằng <code>http://</code> hoặc <code>https://</code>.",
                parse_mode=ParseMode.HTML
            )
            return

        total_urls = len(urls)
        max_allowed = 30
        if total_urls > max_allowed:
            urls = urls[:max_allowed]
            await update.message.reply_text(f"ℹ️ File có {total_urls} link. Bot sẽ ưu tiên giải mã {max_allowed} link đầu tiên nhé!")

        num_to_process = len(urls)
        await status_msg.edit_text(
            f"⚡ <b>BẮT ĐẦU XỬ LÝ HÀNG LOẠT {num_to_process} LINK...</b>\n"
            f"⏳ Vui lòng chờ trong giây lát...",
            parse_mode=ParseMode.HTML
        )

        # Xử lý đa luồng song song với Semaphore(3)
        sem = asyncio.Semaphore(3)

        async def bypass_single(url: str):
            async with sem:
                res = await BypassManager.bypass(url)
                clean_target = clean_url(res.result_url) if res.success else ""
                if user:
                    log_action(user.id, url, "batch", "success" if res.success else "fail", res.engine_used, result_url=clean_target)
                return url, res, clean_target

        tasks = [bypass_single(u) for u in urls]
        completed_results = await asyncio.gather(*tasks)

        # Tổng hợp kết quả
        success_count = 0
        now_vn = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S - %d/%m/%Y")
        output_lines = [
            f"# ========================================================",
            f"# KẾT QUẢ VƯỢT LINK HÀNG LOẠT - BOT @N1_link_bot",
            f"# Thời gian xử lý: {now_vn}",
            f"# Tên file gốc: {file_name}",
            f"# ========================================================\n"
        ]

        for idx, (orig_url, res, clean_target) in enumerate(completed_results, 1):
            if res.success:
                success_count += 1
                output_lines.append(f"[{idx}] THÀNH CÔNG ({res.engine_used} - {res.time_taken}s)")
                output_lines.append(f"Link gốc: {orig_url}")
                output_lines.append(f"Link đích: {clean_target}\n")
            else:
                output_lines.append(f"[{idx}] THẤT BẠI")
                output_lines.append(f"Link gốc: {orig_url}")
                output_lines.append(f"Lý do: Không thể vượt hoặc yêu cầu captcha thủ công\n")

        output_lines.append(f"# ========================================================")
        output_lines.append(f"# TỔNG KẾT: {success_count}/{num_to_process} link thành công ({round(success_count/num_to_process*100, 1)}%)")
        output_lines.append(f"# Cảm ơn bạn đã sử dụng Bot @N1_link_bot!")

        file_data = "\n".join(output_lines).encode("utf-8")
        out_stream = io.BytesIO(file_data)
        out_stream.name = f"ket_qua_{file_name}"

        rate_val = round(success_count / num_to_process * 100, 1)
        await status_msg.edit_text(
            f"🎉 <b>XỬ LÝ HÀNG LOẠT HOÀN TẤT!</b>\n\n"
            f"📊 <b>Kết quả:</b> <code>{success_count}/{num_to_process}</code> link thành công (<code>{rate_val}%</code>)\n"
            f"📁 <i>File kết quả chi tiết đang được gửi bên dưới...</i>",
            parse_mode=ParseMode.HTML
        )

        caption = f"✅ Kết quả vượt link hàng loạt từ file: {file_name}\n🎯 Thành công: {success_count}/{num_to_process} link."
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=out_stream,
            filename=f"ket_qua_{file_name}",
            caption=caption
        )

    except Exception as e:
        await status_msg.edit_text(f"⚠️ Có lỗi xảy ra trong quá trình xử lý file: {html.escape(str(e))}")


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Xử lý tra cứu trực tiếp trong mọi nhóm chat hoặc kênh Telegram (Inline Query Mode):
    Người dùng chỉ cần gõ: @N1_link_bot [đường_link]
    """
    inline_query = update.inline_query
    if not inline_query:
        return

    query = inline_query.query.strip()
    user = update.effective_user
    logging.info(f"[Inline] Processing query: '{query}' from user: {user.id if user else None}")
    if user:
        log_user(user.id, user.username, user.first_name)

    results = []

    # 1. Trường hợp query trống: Hiển thị các thẻ gợi ý hữu ích
    if not query:
        results.append(
            InlineQueryResultArticle(
                id="hint_paste_link",
                title="⚡ Dán link rút gọn vào đây để giải mã",
                description="Ví dụ: @N1_link_bot https://ouo.io/xyz",
                input_message_content=InputTextMessageContent(
                    "💡 <b>HƯỚNG DẪN TRA CỨU NHANH (INLINE MODE):</b>\n\n"
                    "Tại bất kỳ nhóm chat hay kênh nào, bạn chỉ cần gõ:\n"
                    "<code>@N1_link_bot [link_rút_gọn]</code>\n\n"
                    "Kết quả link gốc sẽ hiện ra ngay lập tức dưới dạng thẻ xem trước để bạn gửi vào nhóm!",
                    parse_mode=ParseMode.HTML
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🤖 Mở Bot @N1_link_bot", url="https://t.me/N1_link_bot")]
                ])
            )
        )
        results.append(
            InlineQueryResultArticle(
                id="hint_services",
                title="🌐 Danh sách dịch vụ hỗ trợ",
                description="Ouo, Link1s, Sub2Unlock, AdLinkFly, Bitly, TinyURL, Google Drive, Mediafire...",
                input_message_content=InputTextMessageContent(
                    SERVICES_MESSAGE,
                    parse_mode=ParseMode.HTML
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🤖 Mở Bot @N1_link_bot", url="https://t.me/N1_link_bot")]
                ])
            )
        )
        results.append(
            InlineQueryResultArticle(
                id="hint_key",
                title="🔑 Hướng dẫn lấy mã đếm ngược 60s",
                description="Tự động bóc tách mã 60s từ bài viết Google / link đếm ngược",
                input_message_content=InputTextMessageContent(
                    "🔑 <b>TỰ ĐỘNG LẤY MÃ ĐẾM NGƯỢC 60 GIÂY:</b>\n\n"
                    "Bot hỗ trợ mở trình duyệt ngầm, cuộn trang tìm nút và chờ đếm ngược 60 giây để lấy mã cho bạn!\n\n"
                    "👉 Hãy mở @N1_link_bot và gửi link bài viết hoặc dùng lệnh <code>/key [link]</code> nhé!",
                    parse_mode=ParseMode.HTML
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 Mở Bot Lấy Mã 60s", url="https://t.me/N1_link_bot")]
                ])
            )
        )
        await inline_query.answer(results, cache_time=300)
        logging.info("[Inline] Answered empty query with 3 prompt cards")
        return

    # 2. Người dùng đã nhập nội dung: Trích xuất danh sách link
    urls = extract_urls(query)
    if not urls:
        results.append(
            InlineQueryResultArticle(
                id="no_url_found",
                title="⚠️ Chưa tìm thấy đường link hợp lệ",
                description=f"Nội dung: '{query[:40]}...' (Cần link bắt đầu bằng http:// hoặc https://)",
                input_message_content=InputTextMessageContent(
                    f"⚠️ Không nhận diện được link hợp lệ trong: <code>{html.escape(query)}</code>\n\n"
                    "👉 Cú pháp mẫu: <code>@N1_link_bot https://ouo.io/...</code>",
                    parse_mode=ParseMode.HTML
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🤖 Mở Bot @N1_link_bot", url="https://t.me/N1_link_bot")]
                ])
            )
        )
        await inline_query.answer(results, cache_time=10)
        logging.info("[Inline] Answered no_url_found card")
        return

    target_url = urls[0]

    # Thực hiện giải mã với timeout an toàn 2.5 giây để luôn phản hồi nhanh với Telegram UI
    res = None
    try:
        bypass_task = asyncio.create_task(BypassManager.bypass(target_url))
        res = await asyncio.wait_for(bypass_task, timeout=2.5)
    except asyncio.TimeoutError:
        logging.info(f"[Inline] Bypass timed out (>2.5s) for: {target_url}")
        res = None
    except Exception as e:
        logging.warning(f"[Inline] Bypass exception: {e}")
        res = None

    if res and res.success:
        dest_domain = urlparse(res.result_url).netloc or "Link gốc"
        article_id = hashlib.md5(f"ok_{target_url}".encode()).hexdigest()
        msg_text = (
            f"⚡ <b>KẾT QUẢ VƯỢT LINK (INLINE):</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 <b>Link đích:</b> <code>{html.escape(res.result_url)}</code>\n"
            f"🌐 <b>Link gốc:</b> <code>{html.escape(target_url)}</code>\n"
            f"⚙️ <b>Công nghệ:</b> <code>{html.escape(res.engine_used)} ({res.time_taken}s)</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <i>Giải mã siêu tốc bởi @N1_link_bot</i>"
        )
        buttons = []
        if res.result_url.startswith(("http://", "https://")):
            buttons.append([InlineKeyboardButton("🔗 Mở Link Đích", url=res.result_url)])
        buttons.append([InlineKeyboardButton("🤖 Mở Bot @N1_link_bot", url="https://t.me/N1_link_bot")])

        results.append(
            InlineQueryResultArticle(
                id=article_id,
                title=f"✅ Vượt thành công: {dest_domain}",
                description=f"Link đích: {res.result_url}",
                input_message_content=InputTextMessageContent(msg_text, parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        )
        if user:
            log_action(user.id, target_url, "inline_bypass", "success", res.engine_used)
        await inline_query.answer(results, cache_time=300)
        logging.info(f"[Inline] Successfully answered bypass result for: {target_url}")
    else:
        article_id = hashlib.md5(f"fail_{target_url}".encode()).hexdigest()
        orig_domain = urlparse(target_url).netloc or target_url
        msg_text = (
            f"⚠️ <b>CHƯA THỂ GIẢI MÃ TỰ ĐỘNG (INLINE):</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 <b>Đường link:</b> <code>{html.escape(target_url)}</code>\n\n"
            f"💡 <i>Đường link này có thể cần thực hiện nhiệm vụ lấy mã 60s hoặc cần giải mã chuyên sâu. Hãy mở Bot để được xử lý tốt nhất!</i>"
        )
        results.append(
            InlineQueryResultArticle(
                id=article_id,
                title=f"⚠️ Mở Bot để giải mã: {orig_domain}",
                description="Link này cần xử lý nâng cao hoặc lấy mã 60s",
                input_message_content=InputTextMessageContent(msg_text, parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 Mở Bot Giải Mã Chuyên Sâu", url="https://t.me/N1_link_bot?start=help")]
                ])
            )
        )
        if user:
            log_action(user.id, target_url, "inline_bypass", "fail", "Timeout / Failed")
        await inline_query.answer(results, cache_time=10)
        logging.info(f"[Inline] Answered fallback card for: {target_url}")

