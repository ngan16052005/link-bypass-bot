import os
import html
from urllib.parse import urlparse
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from core.bypass_manager import BypassManager
from core.engine_traffic_key import grab_traffic_key
from core.database import log_user, log_action, save_report, get_statistics
from .utils import extract_urls
from .keyboards import (
    get_result_keyboard,
    get_fail_keyboard,
    get_url_from_key
)

ADMIN_ID = os.getenv("ADMIN_ID")

TASK_SHORTENER_DOMAINS = [
    "ontops.link", "ontop.link", "link1s.com", "link1s.net",
    "traffic123.net", "traffic123.org", "layma.net", "laylink.net"
]

WELCOME_MESSAGE = (
    "👋 <b>Chào mừng bạn đến với Bot Vượt Link & Tự Động Lấy Key Siêu Tốc!</b>\n\n"
    "🚀 <b>2 Tính năng chính:</b>\n"
    "1️⃣ <b>Vượt link rút gọn:</b> Gửi link <code>bit.ly</code>, <code>tinyurl</code>, <code>linkx</code>, <code>linkvertise</code>... để lấy link gốc.\n"
    "2️⃣ <b>Tự động lấy Key/Mã 60s:</b> Gõ <code>/key [link_bài_viết]</code> (ví dụ: <code>tabare.com.co</code>) -> Bot tự mở trình duyệt ngầm, cuộn trang, chờ 60s và lấy mã cho bạn!\n\n"
    "👉 <i>Hãy thử gửi 1 link ngay bây giờ nhé!</i>"
)

HELP_MESSAGE = (
    "📖 <b>HƯỚNG DẪN CHI TIẾT:</b>\n\n"
    "🔹 <b>Vượt link rút gọn:</b> Dán link rút gọn vào chat -> Nhận link gốc trực tiếp.\n"
    "🔹 <b>Tự động lấy Mã / Key 60 giây:</b> Gõ <code>/key [link_bài_viết]</code>\n"
    "🔹 <b>Xem ID Telegram của bạn:</b> Gõ <code>/myid</code>\n"
    "🔹 <b>Thống kê hệ thống (Admin):</b> Gõ <code>/stats</code>"
)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)
    await update.message.reply_text(HELP_MESSAGE, parse_mode=ParseMode.HTML)

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    log_user(user.id, user.username, user.first_name)

    msg = (
        f"🆔 <b>ID TELEGRAM CỦA BẠN:</b>\n"
        f"👉 <code>{user.id}</code> 👈\n"
        f"<i>(Chạm vào dãy số trên để tự động sao chép)</i>\n\n"
        f"💡 <b>Dành cho Admin:</b> Hãy copy ID này và thêm vào Render (mục <b>Environment</b>) với biến <code>ADMIN_ID = {user.id}</code> để nhận báo cáo lỗi và mở khóa lệnh <code>/stats</code>!"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    log_user(user.id, user.username, user.first_name)

    # Nếu có ADMIN_ID thì chỉ cho phép Admin xem
    admin_env = os.getenv("ADMIN_ID", "").strip()
    if admin_env and str(user.id) != admin_env:
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
        f"• Hoạt động hôm nay: <code>{stats.get('today_users', 0)}</code>\n\n"
        f"🔗 <b>Xử lý liên kết:</b>\n"
        f"• Tổng link đã xử lý: <code>{stats.get('total_links', 0)}</code>\n"
        f"• Link xử lý hôm nay: <code>{stats.get('today_links', 0)}</code>\n"
        f"• Vượt thành công: <code>{stats.get('success_links', 0)}</code> (<code>{stats.get('success_rate', 100)}%</code>)\n\n"
        f"🚨 <b>Báo cáo lỗi:</b>\n"
        f"• Tổng số link báo lỗi: <code>{stats.get('total_reports', 0)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <i>Trạng thái: Máy chủ đám mây đang chạy 24/7</i>"
    )
    await update.message.reply_text(stats_msg, parse_mode=ParseMode.HTML)

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

    # Xử lý nút Lấy Key
    if data.startswith("getkey:"):
        short_key = data[7:]
        url = get_url_from_key(short_key) or short_key
        status_msg = await query.message.reply_text(
            f"⏳ Đang khởi động trình duyệt ảo để lấy Key từ <code>{html.escape(url)}</code>...",
            parse_mode=ParseMode.HTML
        )
        await do_grab_key(status_msg, url, user.id if user else 0)

    # Xử lý nút Báo lỗi link cho Admin
    elif data.startswith("report:"):
        short_key = data[7:]
        url = get_url_from_key(short_key) or short_key
        
        save_report(user.id if user else 0, user.username if user else "", url)

        # Gửi thông báo đến Admin nếu có cấu hình ADMIN_ID
        admin_id_str = os.getenv("ADMIN_ID", "").strip()
        if admin_id_str:
            try:
                now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
                admin_alert = (
                    f"🚨 <b>BÁO CÁO LINK LỖI TỪ NGƯỜI DÙNG!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>Người báo:</b> @{user.username or 'Không có'} (ID: <code>{user.id}</code>)\n"
                    f"🔗 <b>Link lỗi:</b>\n<code>{html.escape(url)}</code>\n"
                    f"⏱️ <b>Thời gian:</b> <code>{now_str}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👉 Hãy kiểm tra để nâng cấp thêm engine cho link này!"
                )
                await context.bot.send_message(chat_id=int(admin_id_str), text=admin_alert, parse_mode=ParseMode.HTML)
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
    if user:
        log_user(user.id, user.username, user.first_name)

    text = update.message.text
    if not text:
        return

    urls = extract_urls(text)
    if not urls:
        await update.message.reply_text(
            "⚠️ Mình không tìm thấy đường link nào trong tin nhắn của bạn. Vui lòng gửi một liên kết hợp lệ (ví dụ: <code>https://...</code>)!",
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
                log_action(user.id if user else 0, url, "bypass", "success", result.engine_used)
                msg_text = (
                    f"✅ <b>VƯỢT LINK THÀNH CÔNG!</b>\n\n"
                    f"🔗 <b>Link ban đầu:</b>\n<code>{html.escape(result.original_url)}</code>\n\n"
                    f"🎯 <b>Link đích:</b>\n<code>{html.escape(result.result_url)}</code>\n\n"
                    f"⚡ <b>Phương thức:</b> <code>{html.escape(result.engine_used)}</code>\n"
                    f"⏱️ <b>Thời gian xử lý:</b> <code>{result.time_taken}s</code>"
                )
                await status_msg.edit_text(
                    msg_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_result_keyboard(result.result_url)
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
