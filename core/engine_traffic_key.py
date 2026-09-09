import asyncio
import re
from urllib.parse import urlparse
from typing import Callable, Awaitable

# Giới hạn tối đa 2 trình duyệt chạy đồng thời để tránh ngốn RAM/CPU máy tính
BROWSER_SEMAPHORE = asyncio.Semaphore(2)

# Danh sách phần mở rộng file cần chặn để tăng tốc độ tải trang gấp 3-5 lần
BLOCKED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".webm", ".ogg", ".mp3", ".wav"
}

# Các từ khóa JS/HTML bị loại trừ để tránh nhận diện nhầm mã
EXCLUDED_KEYWORDS = {
    "string", "none", "null", "undefined", "window", "document", "location",
    "true", "false", "function", "object", "return", "const", "var", "let",
    "button", "action", "submit", "center", "middle", "inline", "block",
    "header", "footer", "content", "script", "style", "length", "value"
}


def make_progress_bar(current: int, total: int = 60, length: int = 10) -> str:
    """Tạo thanh tiến trình trực quan [██████░░░░]"""
    percent = min(1.0, max(0.0, current / total))
    filled = int(round(length * percent))
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {int(percent * 100)}%"

async def grab_traffic_key(
    url: str,
    status_callback: Callable[[str], Awaitable[None]] | None = None
) -> tuple[bool, str, str]:
    """
    Tự động mở trình duyệt ảo tối ưu hóa cao (chặn ảnh, font, media để tải siêu nhanh),
    cuộn trang web, kích hoạt đếm ngược và bóc tách mã Key.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False, "", "Thư viện Playwright chưa được cài đặt."

    async with BROWSER_SEMAPHORE:
        captured_key = {"code": None}

        async def on_response(response):
            try:
                url_str = response.url.lower()
                if any(k in url_str for k in ["getcode", "get-code", "layma", "traffic", "lay-ma"]):
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        data = await response.json()
                        if isinstance(data, dict):
                            for k in ["html", "code", "key", "result", "passcode"]:
                                val = data.get(k)
                                if val and isinstance(val, (str, int)):
                                    val_str = str(val).strip()
                                    clean_val = re.sub(r'<[^>]+>', '', val_str).strip()
                                    if clean_val and len(clean_val) >= 4:
                                        captured_key["code"] = clean_val
                                        return
            except Exception:
                pass

        async with async_playwright() as p:
            # Khởi chạy Edge hoặc Chromium với cờ tối ưu hóa tối đa
            browser = None
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-gpu",
                "--mute-audio"
            ]

            for channel in ["msedge", "chrome", None]:
                try:
                    opts = {"headless": True, "args": launch_args}
                    if channel:
                        opts["channel"] = channel
                    browser = await p.chromium.launch(**opts)
                    break
                except Exception:
                    continue

            if not browser:
                return False, "", "Không thể khởi động trình duyệt ảo trên hệ thống."

            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/130.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 720},
                    locale="vi-VN"
                )
                page = await context.new_page()

                # TỐI ƯU HÓA BĂNG THÔNG: Chặn ảnh, font chữ và media nặng
                async def route_filter(route):
                    req_url = route.request.url.lower()
                    # Chặn extension nặng
                    if any(req_url.endswith(ext) or ext + "?" in req_url for ext in BLOCKED_EXTENSIONS):
                        await route.abort()
                    # Chặn trackers / analytics
                    elif any(domain in req_url for domain in ["google-analytics.com", "googletagmanager.com", "facebook.net"]):
                        await route.abort()
                    else:
                        await route.continue_()

                await page.route("**/*", route_filter)
                page.on("response", on_response)

                if status_callback:
                    await status_callback("🌐 Đang kết nối nhanh tới trang web...")

                # 1. Truy cập trang web
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=35000)
                except Exception:
                    pass

                if status_callback:
                    await status_callback("📜 Đang cuộn trang kích hoạt bộ đếm mã...")

                # 2. Cuộn trang mượt mà bằng JavaScript
                try:
                    await page.evaluate("""
                        window.scrollTo({ top: document.body.scrollHeight / 2, behavior: 'smooth' });
                    """)
                    await asyncio.sleep(0.5)
                    await page.evaluate("""
                        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
                    """)
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

                # 3. Kích hoạt nút bấm nếu có
                button_selectors = [
                    '#xacthucButton',
                    'button:has-text("LẤY MÃ")',
                    'button:has-text("Lấy mã")',
                    'span:has-text("LẤY MÃ")',
                    'div:has-text("LẤY MÃ")',
                    '#show_code_button',
                    'a:has-text("LẤY MÃ")',
                    'button:has-text("BẤM VÀO ĐÂY")',
                    'button:has-text("Get Code")'
                ]
                for sel in button_selectors:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=800):
                            await btn.click(timeout=1000)
                            break
                    except Exception:
                        pass

                # 4. Vòng lặp chờ đếm ngược với thanh tiến trình trực quan
                total_expected_wait = 60
                max_timeout = 85
                interval = 3
                waited = 0

                while waited < max_timeout:
                    if captured_key["code"]:
                        return True, captured_key["code"], "Đã nhận mã từ hệ thống thành công!"

                    # Quét DOM (chỉ quét text hiển thị, loại bỏ thẻ script/style ngầm)
                    try:
                        # 1. Kiểm tra các phần tử hiển thị mã phổ biến
                        for code_sel in ['#traffic_code', '#show_code', '#code_output', '.layma-code', '[id*="traffic"]', '[id*="layma"]']:
                            try:
                                el = page.locator(code_sel).first
                                if await el.is_visible(timeout=150):
                                    val = (await el.text_content() or "").strip()
                                    clean_val = re.sub(r'[^A-Za-z0-9]', '', val)
                                    if len(clean_val) >= 4 and clean_val.lower() not in EXCLUDED_KEYWORDS:
                                        return True, clean_val, "Đã đọc được mã từ phần tử trên trang!"
                            except Exception:
                                pass

                        # 2. Quét text hiển thị trên trang bằng innerText (không quét script)
                        text_content = await page.evaluate("() => document.body ? document.body.innerText : ''")
                        match = re.search(r'(?:Mã|Code|Key)(?:\s*của\s*bạn)?\s*[:=]\s*([A-Za-z0-9]{4,12})', text_content, re.IGNORECASE)
                        if match:
                            code_found = match.group(1).strip()
                            if code_found.lower() not in EXCLUDED_KEYWORDS:
                                return True, code_found, "Đã đọc được mã hiển thị trên trang!"

                        # Thử click nút nhận mã nếu chuyển trạng thái
                        for sel in button_selectors:
                            try:
                                btn = page.locator(sel).first
                                if await btn.is_visible(timeout=300):
                                    await btn.click(timeout=500)
                            except Exception:
                                pass
                    except Exception:
                        pass


                    # Cập nhật thanh tiến trình mỗi 6 giây
                    if status_callback and waited > 0 and waited % 6 == 0:
                        prog_bar = make_progress_bar(waited, total_expected_wait)
                        rem = max(0, total_expected_wait - waited)
                        if rem > 0:
                            await status_callback(f"⏳ {prog_bar} (còn ~{rem}s)")
                        else:
                            await status_callback("⏳ Đang chờ máy chủ nhả mã...")

                    await asyncio.sleep(interval)
                    waited += interval

                if captured_key["code"]:
                    return True, captured_key["code"], "Đã nhận được mã!"

                return False, "", "Hết thời gian chờ hoặc trang yêu cầu giải Captcha."

            finally:
                await browser.close()
