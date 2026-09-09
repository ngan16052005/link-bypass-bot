import os
import io
import asyncio
import html
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
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
    get_url_from_key,
    get_main_menu_keyboard
)
from .anti_spam import check_rate_limit



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
    "🌐 <b>DANH SÁCH DỊCH VỤ & LIÊN KẾT HỖ TRỢ:</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "💰 <b>Trang Rút Gọn Kiếm Tiền:</b>\n"
    "• <b>Ouo:</b> <code>ouo.io</code>, <code>ouo.press</code>\n"
    "• <b>AdLinkFly:</b> <code>link1s</code>, <code>linkx</code>, <code>megaurl</code>, <code>droplink</code>, <code>shrtfly</code>...\n"
    "• <b>Quốc tế:</b> <code>linkvertise.com</code>, <code>work.ink</code>, <code>adfly</code>...\n"
    "• <b>Sub Kênh:</b> <code>sub2unlock.com</code>, <code>sub4unlock.com</code>...\n\n"
    "⚡ <b>Rút Gọn Redirect Siêu Tốc:</b>\n"
    "• <code>bit.ly</code>, <code>tinyurl.com</code>, <code>cutt.ly</code>, <code>shorturl.at</code>, <code>is.gd</code>...\n"
    "• <b>SafeLink / Query:</b> Tự động giải mã link giấu trong Base64, Hex (<code>?url=</code>, <code>?dest=</code>, <code>?target=</code>...)\n"
    "• <b>Chuyển hướng ngầm:</b> Meta Refresh & JavaScript Redirects\n\n"
    "📁 <b>Tải File Trực Tiếp:</b>\n"
    "• <b>Google Drive:</b> Tự động tạo link tải trực tiếp\n"
    "• <b>Mediafire:</b> Bóc tách direct link tải nhanh không quảng cáo\n"
    "• <b>Pastebin:</b> Trích xuất nội dung raw / link đích\n\n"
    "🔑 <b>Tự Động Lấy Key Đếm Ngược 60s:</b>\n"
    "• Mạng lưới: <code>layma.net</code>, <code>traffic123</code>, <code>tabare</code> và các bài viết Google yêu cầu chờ 60s lấy mã.\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👉 <i>Chỉ cần copy và dán bất kỳ link nào vào chat để Bot tự động xử lý!</i>"
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)
    is_admin = bool(user and str(user.id) == os.getenv("ADMIN_ID", "").strip())
    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(is_admin)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)
    is_admin = bool(user and str(user.id) == os.getenv("ADMIN_ID", "").strip())
    await update.message.reply_text(
        HELP_MESSAGE,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(is_admin)
    )

async def services_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        log_user(user.id, user.username, user.first_name)
    is_admin = bool(user and str(user.id) == os.getenv("ADMIN_ID", "").strip())
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
    is_admin = bool(user and str(user.id) == os.getenv("ADMIN_ID", "").strip())
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

    # Xử lý nút Báo lỗi link cho Admin
    elif data.startswith("report:"):
        short_key = data[7:]
        url = get_url_from_key(short_key) or short_key
        
        save_report(user.id if user else 0, user.username if user else "", url)

        # Gửi thông báo đến Admin nếu có cấu hình ADMIN_ID
        admin_id_str = os.getenv("ADMIN_ID", "").strip()
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
        if update.message.document:
            await handle_document(update, context)
        return

    # 1. Bắt các nút bấm từ bàn phím Menu
    clean_text = text.strip()
    if clean_text == "📖 Hướng Dẫn Vượt Link":
        await help_command(update, context)
        return
    elif clean_text == "📁 Vượt Link File .txt":
        await batch_command(update, context)
        return
    elif clean_text == "🌐 Dịch Vụ Hỗ Trợ":
        await services_command(update, context)
        return
    elif clean_text == "🔑 Cách Lấy Mã 60s":
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
    elif clean_text == "📊 Thống Kê (Admin)":
        await stats_command(update, context)
        return
    elif clean_text == "🆔 ID Của Tôi":
        await myid_command(update, context)
        return
    elif clean_text == "📢 Hỗ Trợ / Báo Lỗi":
        msg = (
            "📢 <b>HỖ TRỢ & BÁO LỖI LINK:</b>\n\n"
            "• Nếu bạn gặp link rút gọn nào bot chưa giải mã được, bạn chỉ cần gửi link đó vào khung chat.\n"
            "• Bot sẽ lập tức hiển thị nút <b>[📢 Báo Lỗi Link Này Cho Admin]</b>.\n"
            "• Khi bạn chạm vào nút đó, link lỗi sẽ được gửi trực tiếp đến Admin để nâng cấp bộ giải mã!\n\n"
            "💡 <i>Hãy thử dán bất kỳ link nào vào đây để trải nghiệm nhé!</i>"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    urls = extract_urls(text)
    if not urls:
        await update.message.reply_text(
            "⚠️ Mình không tìm thấy đường link nào trong tin nhắn của bạn. Vui lòng gửi một liên kết hợp lệ (ví dụ: <code>https://...</code>)!",
            parse_mode=ParseMode.HTML
        )
        return

    # Kiểm tra chống spam gửi link
    allowed, wait_sec = check_rate_limit(user.id if user else 0, "message")
    if not allowed:
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
                if user:
                    log_action(user.id, url, "batch", "success" if res.success else "fail", res.engine_used)
                return url, res

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

        for idx, (orig_url, res) in enumerate(completed_results, 1):
            if res.success:
                success_count += 1
                output_lines.append(f"[{idx}] THÀNH CÔNG ({res.engine_used} - {res.time_taken}s)")
                output_lines.append(f"Link gốc: {orig_url}")
                output_lines.append(f"Link đích: {res.result_url}\n")
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

