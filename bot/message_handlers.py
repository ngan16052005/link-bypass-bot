import io
import html
import asyncio
import hashlib
import logging
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQueryResultArticle,
    InputTextMessageContent
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.database import (
    log_user,
    log_action,
    is_admin_user,
    check_and_increment_quota
)
from core.bypass_manager import BypassManager
from core.link_enricher import clean_url, fetch_file_metadata
from .texts import TASK_SHORTENER_DOMAINS, SERVICES_MESSAGE
from .fsub import check_user_fsub
from .utils import extract_urls
from .keyboards import (
    get_result_keyboard,
    get_fail_keyboard,
    get_fsub_keyboard
)
from .anti_spam import check_rate_limit
from .user_commands import (
    help_command,
    batch_command,
    services_command,
    history_command,
    ref_command,
    myid_command
)
from .admin_commands import stats_command

logger = logging.getLogger(__name__)


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
    logger.info(f"[Inline] Processing query: '{query}' from user: {user.id if user else None}")
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
        return

    target_url = urls[0]

    # Thực hiện giải mã với timeout an toàn 2.5 giây để luôn phản hồi nhanh với Telegram UI
    res = None
    try:
        bypass_task = asyncio.create_task(BypassManager.bypass(target_url))
        res = await asyncio.wait_for(bypass_task, timeout=2.5)
    except asyncio.TimeoutError:
        logger.info(f"[Inline] Bypass timed out (>2.5s) for: {target_url}")
        res = None
    except Exception as e:
        logger.warning(f"[Inline] Bypass exception: {e}")
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
