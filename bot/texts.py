import html

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

BATCH_MESSAGE = (
    "📁 <b>HƯỚNG DẪN VƯỢT LINK HÀNG LOẠT BẰNG FILE .TXT:</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Nếu bạn có nhiều link cần giải mã cùng lúc (ví dụ tải phim, game nhiều part, tài liệu):\n\n"
    "1️⃣ Tạo một file <b>.txt</b> trên điện thoại hoặc máy tính.\n"
    "2️⃣ Dán các đường link rút gọn vào file đó (mỗi link một dòng, tối đa <b>30 link</b> / lần).\n"
    "3️⃣ Gửi file <b>.txt</b> đó trực tiếp vào khung chat này!\n\n"
    "⚡ <i>Bot sẽ tự động giải mã toàn bộ và gửi lại cho bạn 1 file kết quả chứa sạch link gốc!</i>"
)

KEY_INFO_MESSAGE = (
    "🔑 <b>HƯỚNG DẪN TỰ ĐỘNG LẤY MÃ ĐẾM NGƯỢC 60 GIÂY:</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Khi trang rút gọn yêu cầu bạn tìm Google để vào 1 trang bài viết lấy mã:\n\n"
    "👉 <b>Cách 1 (Nhanh nhất):</b> Bạn chỉ cần copy link bài viết đó và <b>dán thẳng vào chat</b>. Bot sẽ tự động hiện nút <code>[🔑 Tự Động Lấy Key Trên Web Này]</code> để bạn bấm!\n\n"
    "👉 <b>Cách 2:</b> Gõ theo cú pháp lệnh:\n"
    "<code>/key [link_bài_viết]</code>\n"
    "<i>(Ví dụ: <code>/key https://tabare.com.co/vi-vn/</code>)</i>\n\n"
    "⚡ <i>Bot sẽ tự động mở trình duyệt ngầm, cuộn trang, chờ đếm ngược 60s và trả mã ngay cho bạn!</i>"
)

REPORT_INFO_MESSAGE = (
    "📢 <b>HƯỚNG DẪN BÁO LỖI LINK CHO ADMIN:</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "• Khi bạn gửi link mà bot không vượt được hoặc trang bị lỗi:\n"
    "• Bot sẽ lập tức hiển thị nút bấm <b>[📢 Báo Lỗi Link Này Cho Admin]</b>.\n"
    "• Khi bạn chạm vào nút đó, link lỗi sẽ được gửi trực tiếp đến Admin để nâng cấp bộ giải mã sớm nhất!\n\n"
    "💡 <i>Hãy thử dán bất kỳ link nào vào đây để trải nghiệm nhé!</i>"
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
