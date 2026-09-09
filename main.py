import os
import sys
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Đảm bảo console Windows in chuẩn tiếng Việt UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    ContextTypes,
    filters
)
from bot.handlers import (
    start_command,
    menu_command,
    help_command,
    services_command,
    batch_command,
    myid_command,
    stats_command,
    broadcast_command,
    reports_command,
    clear_reports_command,
    claimadmin_command,
    key_command,
    callback_router,
    handle_message,
    handle_document,
    inline_query_handler
)



import collections

log_buffer = collections.deque(maxlen=100)

class BufferLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            log_buffer.append(msg)
        except Exception:
            pass

buf_handler = BufferLogHandler()
buf_handler.setLevel(logging.INFO)
buf_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logging.getLogger().setLevel(logging.INFO)
logging.getLogger().addHandler(buf_handler)

# Máy chủ HTTP mini kiểm tra tình trạng sống (Health Check) để treo 24/7 trên Cloud
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/diag":
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            logs_text = "\n".join(log_buffer) or "No logs recorded yet."
            self.wfile.write(logs_text.encode('utf-8'))
            return

        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write('{"status":"ok","version":"v2.3_diag_active","message":"Bot Telegram dang chay 24/7"}'.encode('utf-8'))

    def log_message(self, format, *args):
        pass

def start_health_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[+] May chu Keep-Alive 24/7 da mo tren cong {port}")

# Thiết lập logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if any(k in str(err) for k in ["getaddrinfo failed", "ReadError", "ConnectError"]):
        logging.warning(f"[Mang] Chap chon ket noi toi Telegram: {err}. Dang tu ket noi lai...")
    else:
        logging.error(f"[Loi Bot] {err}", exc_info=False)

def check_token(token: str | None) -> bool:
    if not token:
        return False
    token = token.strip()
    if token == "" or "YOUR_BOT_TOKEN" in token or "your_bot_token" in token:
        return False
    return True

async def post_init(application) -> None:
    """Đăng ký danh sách lệnh trực quan hiển thị tại nút Menu của Telegram."""
    commands = [
        BotCommand("start", "🚀 Bắt đầu / Làm mới bot"),
        BotCommand("menu", "⚡ Bảng điều khiển trung tâm"),
        BotCommand("help", "📖 Hướng dẫn sử dụng chi tiết"),
        BotCommand("batch", "📁 Vượt link hàng loạt bằng file .txt"),
        BotCommand("services", "🌐 Danh sách dịch vụ hỗ trợ"),
        BotCommand("key", "🔑 Lấy mã / key 60s từ link"),
        BotCommand("myid", "🆔 Xem ID Telegram của bạn"),
    ]


    try:
        await application.bot.set_my_commands(commands)
        print("[+] Da dong bo danh sach menu lenh voi Telegram!")
    except Exception as e:
        print(f"[-] Khong the cap nhat menu lenh: {e}")

def main():
    load_dotenv()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not check_token(bot_token):
        print("[-] CHUA CO TELEGRAM BOT TOKEN trong file .env!")
        sys.exit(1)

    # Bật máy chủ HTTP mini giữ bot online 24/7
    start_health_server()

    print("[*] Dang ket noi toi may chu Telegram...")
    
    request_config = HTTPXRequest(
        connection_pool_size=10,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )

    app = (
        ApplicationBuilder()
        .token(bot_token)
        .request(request_config)
        .post_init(post_init)
        .build()
    )


    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("services", services_command))
    app.add_handler(CommandHandler("batch", batch_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("reports", reports_command))
    app.add_handler(CommandHandler("clearreports", clear_reports_command))
    app.add_handler(CommandHandler("claimadmin", claimadmin_command))
    app.add_handler(CommandHandler("key", key_command))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(InlineQueryHandler(inline_query_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))



    print("=" * 60)
    print("🚀 BOT DA SAN SANG CHAY 24/7 TREN CLOUD & CA NHAN!")
    print("👉 Username Telegram: @N1_link_bot")
    print("👉 Link: https://t.me/N1_link_bot")
    print("=" * 60)

    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
