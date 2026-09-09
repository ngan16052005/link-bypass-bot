import html
import logging
from urllib.parse import quote
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.database import (
    log_user,
    is_admin_user,
    get_statistics,
    get_recent_reports,
    get_all_vip_users,
    get_user_vip_info,
    get_user_history,
    get_referral_stats,
    save_report,
    get_admin_id
)
from .texts import (
    HELP_MESSAGE,
    BATCH_MESSAGE,
    SERVICES_MESSAGE,
    KEY_INFO_MESSAGE,
    REPORT_INFO_MESSAGE,
    get_dashboard_text
)
from .keyboards import (
    get_dashboard_inline_keyboard,
    get_back_to_menu_keyboard,
    get_referral_keyboard,
    get_url_from_key
)
from .anti_spam import check_rate_limit
from .fsub import check_user_fsub
from .user_commands import do_grab_key

logger = logging.getLogger(__name__)


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
        is_admin = bool(user and is_admin_user(user.id))
        name = user.first_name if user and user.first_name else "bạn"

        if action in ["menu", "refresh", "back"]:
            try:
                await query.edit_message_text(
                    get_dashboard_text(name),
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_dashboard_inline_keyboard(is_admin)
                )
            except Exception:
                pass
        elif action == "help":
            await query.edit_message_text(
                HELP_MESSAGE,
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_to_menu_keyboard()
            )
        elif action == "key":
            await query.edit_message_text(
                KEY_INFO_MESSAGE,
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
                [InlineKeyboardButton("🔙 Quay Lại Bảng Điều Khiển", callback_data="dash:menu")]
            ]
            try:
                await query.edit_message_text(
                    hist_text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception:
                pass
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
            await query.edit_message_text(
                REPORT_INFO_MESSAGE,
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
                [InlineKeyboardButton("🔙 Quay Lại Bảng Điều Khiển", callback_data="dash:menu")]
            ]
            try:
                await query.edit_message_text(
                    stats_msg,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(stats_keyboard)
                )
            except Exception:
                pass
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
                [InlineKeyboardButton("🏠 Menu Chính", callback_data="dash:menu")]
            ]
            try:
                await query.edit_message_text(
                    rep_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception:
                pass
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
                [InlineKeyboardButton("🏠 Menu Chính", callback_data="dash:menu")]
            ]
            try:
                await query.edit_message_text(
                    vip_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(vip_keyboard)
                )
            except Exception:
                pass
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
            logger.error(f"[QR] Error sending QR code: {e}")
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
                logger.error(f"[Report] Error alerting admin: {e}")

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "✅ <b>ĐÃ GỬI BÁO CÁO THÀNH CÔNG!</b>\n"
            "Cảm ơn bạn, link này đã được gửi trực tiếp cho Admin để kiểm tra và cập nhật bộ giải mã sớm nhất.",
            parse_mode=ParseMode.HTML
        )
