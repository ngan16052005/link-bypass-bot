import asyncio
import re
from urllib.parse import urlparse
from playwright.async_api import async_playwright

STEALTH_JS = """
// Che giấu dấu vết tự động hóa của Playwright / Selenium
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};

const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

Object.defineProperty(navigator, 'languages', {
    get: () => ['vi-VN', 'vi', 'en-US', 'en'],
});
"""

AD_DOMAINS = [
    "doubleclick.net", "googleadservices.com", "googlesyndication.com",
    "adroll.com", "adnxs.com", "popads.net", "popcash.net", "propellerads.com",
    "exoclick.com", "trafficjunky.com", "bet365", "1xbet", "sunwin"
]

def is_ad_domain(url: str) -> bool:
    domain = urlparse(url).netloc.lower()
    return any(ad in domain for ad in AD_DOMAINS)

async def bypass_stealth_browser(url: str, max_wait: float = 20.0) -> str | None:
    """
    Trình duyệt Playwright chế độ Ẩn Danh (Stealth Anti-Detect) cao cấp:
    - Che giấu cờ webdriver
    - Tự động phát hiện và bấm xác minh Cloudflare Turnstile
    - Tự động bấm nút 'Tiếp tục' / 'Get Link' / 'Continue'
    - Theo dõi trang cho tới khi chuyển hướng đến link đích
    """
    orig_domain = urlparse(url).netloc.lower()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars"
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh"
        )
        
        # Tiêm mã che giấu webdriver trước khi bất kỳ script nào chạy
        await context.add_init_script(STEALTH_JS)
        
        page = await context.new_page()
        
        target_found_url = None

        # Lắng nghe sự kiện chuyển trang
        def on_frame_navigated(frame):
            nonlocal target_found_url
            if frame == page.main_frame:
                curr_url = frame.url
                curr_domain = urlparse(curr_url).netloc.lower()
                if curr_url.startswith(("http://", "https://")) and curr_domain:
                    if curr_domain != orig_domain and not is_ad_domain(curr_url):
                        target_found_url = curr_url

        page.on("framenavigated", on_frame_navigated)

        try:
            # Điều hướng đến link rút gọn
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            await asyncio.sleep(2.0)

            # Kiểm tra nếu trang đã tự chuyển hướng ngay
            if target_found_url:
                await browser.close()
                return target_found_url

            start_time = asyncio.get_event_loop().time()
            
            while (asyncio.get_event_loop().time() - start_time) < max_wait:
                current_url = page.url
                current_domain = urlparse(current_url).netloc.lower()
                
                # Nếu đã ra khỏi domain rút gọn ban đầu và không phải domain rác
                if current_domain != orig_domain and not is_ad_domain(current_url):
                    await browser.close()
                    return current_url

                # 1. Phát hiện và xử lý Cloudflare Turnstile
                for frame in page.frames:
                    if "challenges.cloudflare.com" in frame.url:
                        try:
                            # Tìm checkbox hoặc vùng bấm của Turnstile
                            box = await frame.query_selector('input[type="checkbox"], #challenge-stage, .ctp-checkbox-label')
                            if box:
                                await box.click(timeout=3000)
                                await asyncio.sleep(2.0)
                        except Exception:
                            pass

                # 2. Tìm và bấm các nút chuyển bước thông dụng
                click_selectors = [
                    'button:has-text("Get Link")',
                    'a:has-text("Get Link")',
                    'button:has-text("Tiếp tục")',
                    'a:has-text("Tiếp tục")',
                    'button:has-text("Continue")',
                    'a:has-text("Continue")',
                    'button:has-text("Click here to continue")',
                    'a:has-text("Click here to continue")',
                    '#btn-main',
                    '#invisibleCaptchaFinished',
                    '.get-link'
                ]

                clicked = False
                for sel in click_selectors:
                    try:
                        elem = await page.query_selector(sel)
                        if elem and await elem.is_visible() and await elem.is_enabled():
                            await elem.click(timeout=2000)
                            clicked = True
                            await asyncio.sleep(2.0)
                            break
                    except Exception:
                        continue

                # Nếu không bấm được gì, cuộn nhẹ trang giả lập hành vi người dùng
                if not clicked:
                    await page.mouse.wheel(0, 300)
                    await asyncio.sleep(1.5)

            # Kiểm tra lần cuối
            final_url = page.url
            final_domain = urlparse(final_url).netloc.lower()
            if final_domain != orig_domain and not is_ad_domain(final_url):
                await browser.close()
                return final_url

        except Exception as e:
            print(f"[engine_stealth] Error during stealth bypass: {e}")
        finally:
            await browser.close()

    return None
