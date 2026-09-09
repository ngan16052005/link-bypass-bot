import html
from urllib.parse import urlparse
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from core.bypass_manager import BypassManager
from core.engine_traffic_key import grab_traffic_key
from .utils import extract_urls
from .keyboards import get_result_keyboard, get_traffic_key_keyboard

# Danh sách các tên miền thường là web rút gọn giao nhiệm vụ (chứa ô nhập mã chứ KHÔNG PHẢI nơi sinh mã)
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
    "🔹 <b>Trường hợp 1: Vượt link rút gọn thông thường</b>\n"
    "• Dán link rút gọn vào chat -> Bot tự trả về link tải trực tiếp.\n\n"
    "🔹 <b>Trường hợp 2: Tự động lấy Mã / Key 60 giây</b>\n"
    "• Trang web rút gọn (như <code>ontops.link</code>) sẽ bảo bạn vào Google tìm một trang web bài viết (như <code>tabare.com.co</code>).\n"
    "• Bạn chỉ cần copy link của <b>trang bài viết đó</b> và gõ: <code>/key [link_bài_viết]</code>\n"
    "• Bot sẽ tự vào chờ 60s và gửi mã về cho bạn để bạn dán ngược lại!"
)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode=ParseMode.HTML
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        HELP_MESSAGE,
        parse_mode=ParseMode.HTML
    )

async def do_grab_key(status_msg, url: str):
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
        fail_text = (
            f"⚠️ <b>CHƯA THỂ LẤY ĐƯỢC MÃ TỰ ĐỘNG!</b>\n\n"
            f"🌐 <b>URL:</b> <code>{escaped_url}</code>\n\n"
            f"📌 <b>Chi tiết:</b> {html.escape(details)}\n\n"
            f"💡 <i>Lưu ý: Hãy đảm bảo đây là link bài viết có đồng hồ đếm ngược (chứ không phải trang rút gọn giao nhiệm vụ).</i>"
        )
        await status_msg.edit_text(fail_text, parse_mode=ParseMode.HTML)

async def key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await do_grab_key(status_msg, url)

async def key_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data or ""
    if data.startswith("getkey:"):
        url = data[7:]
        status_msg = await query.message.reply_text(
            f"⏳ Đang khởi động trình duyệt ảo để lấy Key từ <code>{html.escape(url)}</code>...",
            parse_mode=ParseMode.HTML
        )
        await do_grab_key(status_msg, url)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        # Kiểm tra thông minh nếu người dùng gửi link của web rút gọn giao nhiệm vụ (như ontops.link)
        if any(td in domain for td in TASK_SHORTENER_DOMAINS):
            task_msg = (
                f"ℹ️ <b>ĐÂY LÀ TRANG RÚT GỌN GIAO NHIỆM VỤ!</b>\n\n"
                f"🔗 <b>Link:</b> <code>{escaped_url}</code>\n\n"
                f"📝 Trang này là nơi <b>NHẬP MÃ</b> (nó yêu cầu bạn tìm kiếm Google để vào 1 trang web bài viết khác).\n\n"
                f"👉 <b>Cách làm đúng:</b> Bạn hãy copy đường link của <b>trang bài viết</b> mà trang này yêu cầu vào, sau đó gửi cho bot theo cú pháp:\n"
                f"<code>/key [link_bài_viết]</code>\n"
                f"<i>(Bot sẽ tự vào trang bài viết đó đợi 60s và lấy mã giúp bạn!)</i>"
            )
            await update.message.reply_text(task_msg, parse_mode=ParseMode.HTML)
            continue

        status_msg = await update.message.reply_text(
            f"⏳ Đang kiểm tra liên kết: <code>{escaped_url}</code>\nVui lòng chờ trong giây lát...",
            parse_mode=ParseMode.HTML
        )

        try:
            result = await BypassManager.bypass(url)

            if result.success:
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
                # Nếu không phải link rút gọn redirect, cung cấp tùy chọn Lấy Key
                fail_text = (
                    f"ℹ️ <b>ĐÂY CÓ THỂ LÀ TRANG WEB BÀI VIẾT LÀM NHIỆM VỤ LẤY MÃ</b>\n\n"
                    f"🔗 <b>Link:</b> <code>{escaped_url}</code>\n\n"
                    f"👉 Nếu đây là trang web có nút đếm ngược 60s để lấy Key kích hoạt, hãy bấm nút dưới đây để Bot tự động vào lấy mã giúp bạn!"
                )
                await status_msg.edit_text(
                    fail_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_traffic_key_keyboard(url)
                )
        except Exception as e:
            await status_msg.edit_text(
                f"⚠️ Có lỗi phát sinh khi xử lý: <code>{html.escape(str(e))}</code>",
                parse_mode=ParseMode.HTML
            )
