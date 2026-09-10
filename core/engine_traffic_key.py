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

                # Luôn duy trì trang web ở trạng thái visible/active để không bị dừng đếm ngược ngầm
                try:
                    await page.add_init_script("""
                        Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });
                        Object.defineProperty(document, 'hidden', { get: () => false });
                    """)
                except Exception:
                    pass

                # TỐI ƯU HÓA BĂNG THÔNG: Chặn ảnh, font chữ và media nặng
                async def route_filter(route):
                    req_url = route.request.url.lower()
                    if any(req_url.endswith(ext) or ext + "?" in req_url for ext in BLOCKED_EXTENSIONS):
                        await route.abort()
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
                    await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                except Exception:
                    pass

                if status_callback:
                    await status_callback("📜 Đang cuộn trang kiểm tra bộ đếm mã...")

                # 2. Cuộn trang mượt mà bằng JavaScript
                try:
                    await page.evaluate("""
                        window.scrollTo({ top: document.body.scrollHeight / 2, behavior: 'smooth' });
                    """)
                    await asyncio.sleep(0.4)
                    await page.evaluate("""
                        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
                    """)
                    await asyncio.sleep(0.4)
                except Exception:
                    pass

                # 3. Kích hoạt nút bấm lấy mã (Kiên nhẫn chờ script tiêm nút tối đa 15 giây)
                if status_callback:
                    await status_callback("🔍 Đang tìm nút [LẤY MÃ] trên trang web...")

                button_selectors = [
                    'text=LẤY MÃ',
                    '#xacthucButton',
                    'span:has-text("LẤY MÃ")',
                    'button:has-text("LẤY MÃ")',
                    'div:has-text("LẤY MÃ")',
                    'a:has-text("LẤY MÃ")',
                    '#show_code_button',
                    'button:has-text("Lấy mã")',
                    'button:has-text("BẤM VÀO ĐÂY")',
                    'text=BẤM VÀO ĐÂY',
                    'button:has-text("Get Code")',
                    'text=Get Code',
                    '[id*="layma"]',
                    '[id*="traffic"]'
                ]

                button_found = False
                for wait_round in range(7):  # Thử 7 vòng x 2s = 14s để đợi script bên ngoài nạp nút
                    for sel in button_selectors:
                        try:
                            btn = page.locator(sel).first
                            if await btn.is_visible(timeout=800):
                                await btn.scroll_into_view_if_needed()
                                await btn.click(timeout=1500)
                                button_found = True
                                if status_callback:
                                    await status_callback("✅ Đã bấm nút [LẤY MÃ]! Đang kích hoạt đồng hồ...")
                                break
                        except Exception:
                            pass
                    if button_found:
                        break
                    # Cuộn trang xuống dưới để kích hoạt các script yêu cầu cuộn
                    try:
                        await page.evaluate("window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });")
                    except Exception:
                        pass
                    await asyncio.sleep(2)

                # Kiểm tra nhanh: nếu trang không có nút và không có bất kỳ dấu hiệu nhiệm vụ lấy mã nào
                has_task_script = False
                try:
                    content_lower = (await page.content()).lower()
                    traffic_hints = [
                        "layma", "traffic", "countdown", "xacthuc", "getcode",
                        "lay-ma", "get-code", "demnguoc", "counter", "time_getcode"
                    ]
                    if any(h in content_lower for h in traffic_hints):
                        has_task_script = True
                except Exception:
                    pass

                if not button_found and not has_task_script:
                    return False, "", "Trang web này không có nút lấy mã hoặc đồng hồ đếm ngược nhiệm vụ."

                # 4. Vòng lặp chờ đếm ngược thông minh (Tự bẻ khóa tạm dừng & tự thích ứng thời gian)
                total_expected_wait = 60
                total_wait_fixed = False
                max_timeout = 150
                interval = 2.0
                waited = 0
                second_click_done = False
                post_clicked = False

                while waited < max_timeout:
                    if captured_key["code"]:
                        return True, captured_key["code"], "Đã nhận mã từ hệ thống thành công!"

                    # A. Bẻ khóa Checkpoint 1: Tự động "Chạm vào màn hình" (Touch Screen)
                    try:
                        await page.mouse.click(350, 350)
                        await page.evaluate("""() => {
                            window.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                            window.dispatchEvent(new Event('touchstart'));
                        }""")
                    except Exception:
                        pass

                    # B. Bẻ khóa Checkpoint 2: Định kỳ cuộn lên đỉnh trang (scrollTop=0) để kích hoạt scrollUp
                    if int(waited // interval) % 3 == 0:
                        try:
                            await page.evaluate("window.scrollTo(0, 0); window.dispatchEvent(new Event('scroll'));")
                            await asyncio.sleep(0.2)
                            await page.evaluate("window.scrollTo(0, document.body.scrollHeight); window.dispatchEvent(new Event('scroll'));")
                        except Exception:
                            pass

                    # C. Quét phần tử chứa mã trong DOM
                    try:
                        for code_sel in ['#traffic_code', '#show_code', '#code_output', '.layma-code', '[id*="traffic"]', '[id*="layma"]']:
                            try:
                                el = page.locator(code_sel).first
                                if await el.is_visible(timeout=100):
                                    val = (await el.text_content() or "").strip()
                                    clean_val = re.sub(r'[^A-Za-z0-9]', '', val)
                                    if len(clean_val) >= 4 and clean_val.lower() not in EXCLUDED_KEYWORDS:
                                        return True, clean_val, "Đã đọc được mã từ phần tử trên trang!"
                            except Exception:
                                pass

                        text_content = await page.evaluate("() => document.body ? document.body.innerText : ''")
                        
                        # 1. Bóc tách mã bằng biểu thức chính quy (Regex)
                        match = re.search(r'(?:Mã|Code|Key)(?:\s*của\s*bạn)?\s*[:=]\s*([A-Za-z0-9]{4,12})', text_content, re.IGNORECASE)
                        if match:
                            code_found = match.group(1).strip()
                            if code_found.lower() not in EXCLUDED_KEYWORDS:
                                return True, code_found, "Đã đọc được mã hiển thị trên trang!"

                        # 2. Đọc động số giây còn lại trên nút hoặc trên bài viết
                        m_countdown = re.search(r'(?:Lấy mã sau|Chờ|Wait|Còn lại|Sau|tiếp tục lấy mã sau)\s*(\d{1,3})', text_content, re.IGNORECASE)
                        detected_rem = None
                        if m_countdown:
                            detected_rem = int(m_countdown.group(1))
                            if not total_wait_fixed and detected_rem > 0:
                                total_expected_wait = max(total_expected_wait, detected_rem)
                                max_timeout = min(170, total_expected_wait + 45)
                                total_wait_fixed = True

                        # 3. Yêu cầu chuyển tiếp bài viết (Click Post Requirement)
                        msg_text = await page.evaluate("() => document.querySelector('#message') ? document.querySelector('#message').innerText : ''")
                        if ("nhấn bài viết" in (msg_text + text_content).lower() or "bài viết bất kỳ" in (msg_text + text_content).lower() or detected_rem == 0) and not post_clicked and waited > 15:
                            post_clicked = True
                            if status_callback:
                                await status_callback("⚡ Đang tự động chuyển tiếp sang bài viết xác thực cuối cùng...")
                            try:
                                current_host = urlparse(page.url).netloc
                                links = await page.locator('article a, .entry-title a, h2 a, h3 a, a[href*="/vi-vn/"]').all()
                                for l in links:
                                    try:
                                        h = await l.get_attribute("href")
                                        if h and current_host in h and h.rstrip("/") != page.url.rstrip("/"):
                                            await l.click()
                                            await page.wait_for_load_state("domcontentloaded", timeout=12000)
                                            await asyncio.sleep(1.5)
                                            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                                            break
                                    except Exception:
                                        continue
                            except Exception:
                                pass

                        # 4. Khi đồng hồ về 0: kiểm tra các nút bấm xác thực lần cuối (Second Click)
                        if (detected_rem == 0 or (detected_rem is None and waited > 20)) and not second_click_done:
                            second_click_selectors = [
                                '#xacthucButton',
                                'text=BẤM VÀO ĐÂY',
                                'button:has-text("BẤM VÀO ĐÂY")',
                                'text=LẤY MÃ NGAY',
                                'text=NHẬN MÃ',
                                'text=CLICK ĐỂ LẤY MÃ',
                                'span:has-text("LẤY MÃ")'
                            ]
                            for s_sel in second_click_selectors:
                                try:
                                    s_btn = page.locator(s_sel).first
                                    if await s_btn.is_visible(timeout=200):
                                        await s_btn.click(timeout=1000)
                                        second_click_done = True
                                        if status_callback:
                                            await status_callback("⚡ Đã kích hoạt bước nhận mã cuối cùng...")
                                        break
                                except Exception:
                                    pass

                        # 5. Kiểm tra xem có popup Captcha hình ảnh ngăn cản không
                        try:
                            if await page.locator('.qcaptcha-container, #captcha-modal, div[id*="qcaptcha"]').count() > 0:
                                return False, "", "Trang web yêu cầu người dùng phải tự giải Captcha xác thực hình ảnh (qCaptcha)."
                        except Exception:
                            pass

                    except Exception:
                        pass

                    # Cập nhật thanh tiến trình liên tục để người dùng biết bot đang đếm
                    if status_callback and waited > 0:
                        rem = detected_rem if detected_rem is not None else max(0, total_expected_wait - int(waited))
                        prog_bar = make_progress_bar(int(waited), max(total_expected_wait, 1))
                        if rem > 0:
                            await status_callback(f"⏳ {prog_bar} (còn ~{rem}s)")
                        else:
                            await status_callback("⏳ Đang chờ máy chủ nhả mã...")

                    await asyncio.sleep(interval)
                    waited += interval

                if captured_key["code"]:
                    return True, captured_key["code"], "Đã nhận được mã!"

                return False, "", "Hết thời gian chờ (trang web không trả về mã hoặc có captcha)."

            finally:
                await browser.close()

