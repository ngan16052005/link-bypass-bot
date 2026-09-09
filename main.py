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
from telegram import Update
from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from bot.handlers import (
    start_command,
    help_command,
    key_command,
    key_callback,
    handle_message
)

# Máy chủ HTTP mini kiểm tra tình trạng sống (Health Check) để treo 24/7 trên Cloud
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write('{"status":"ok","message":"Bot Telegram dang chay 24/7"}'.encode('utf-8'))

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
        .build()
    )

    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("key", key_command))
    app.add_handler(CallbackQueryHandler(key_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("=" * 60)
    print("🚀 BOT DA SAN SANG CHAY 24/7 TREN CLOUD & CA NHAN!")
    print("👉 Username Telegram: @N1_link_bot")
    print("👉 Link: https://t.me/N1_link_bot")
    print("=" * 60)

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
