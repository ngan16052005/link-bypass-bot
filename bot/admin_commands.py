import html
import asyncio
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.database import (
    log_user,
    is_admin_user,
    get_statistics,
    get_all_user_ids,
    get_recent_reports,
    clear_all_reports,
    get_admin_id,
    set_admin_id,
    set_user_vip,
    remove_user_vip,
    get_all_vip_users,
    get_channel_fsub,
    set_channel_fsub,
    toggle_channel_fsub
)

logger = logging.getLogger(__name__)


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
        ],
        [InlineKeyboardButton("🏠 Menu Chính", callback_data="dash:menu")]
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
        f"• <code>/viplist</code> - Xem danh sách thành viên VIP\n"
        f"• <code>/setvip</code> - Cấp quyền VIP cho người dùng\n"
        f"• <code>/removevip</code> - Hủy trạng thái VIP\n"
        f"• <code>/setchannel</code> - Cài đặt kênh bắt buộc tham gia\n"
        f"• <code>/togglefsub</code> - Bật/Tắt bắt buộc tham gia kênh\n"
        f"• Tự động nhận tin nhắn cảnh báo tức thì mỗi khi có người báo lỗi link!",
        parse_mode=ParseMode.HTML
    )


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
        [InlineKeyboardButton("📊 Thống Kê Chung", callback_data="dash:stats")],
        [InlineKeyboardButton("🏠 Menu Chính", callback_data="dash:menu")]
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
