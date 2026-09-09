from dataclasses import dataclass
import time
from .engine_redirect import unshorten_redirect
from .engine_resolvers import run_custom_resolvers
from .engine_api import bypass_via_public_apis
from .engine_stealth import bypass_stealth_browser
from .database import get_cached_bypass, save_cached_bypass

@dataclass
class BypassResult:
    success: bool
    original_url: str
    result_url: str = ""
    engine_used: str = ""
    error_message: str = ""
    time_taken: float = 0.0

class BypassManager:
    @staticmethod
    async def bypass(url: str, use_stealth: bool = True) -> BypassResult:
        start_time = time.time()
        clean_url = url.strip()

        # 0. Thử kiểm tra Bộ Nhớ Đệm Toàn Cầu (Global Cache - Tốc độ 0.01s)
        try:
            cached = get_cached_bypass(clean_url)
            if cached and cached.get("result_url"):
                return BypassResult(
                    success=True,
                    original_url=clean_url,
                    result_url=cached["result_url"],
                    engine_used=f"Global Cache ({cached.get('engine', 'Fast')})",
                    time_taken=0.01
                )
        except Exception as e:
            print(f"[BypassManager] Cache lookup error: {e}")

        # 1. Thử Engine Resolvers tùy biến (Terabox, Sub2Unlock, Mediafire, Google Drive...)
        try:
            custom_res = await run_custom_resolvers(clean_url)
            if custom_res and custom_res != clean_url:
                save_cached_bypass(clean_url, custom_res, "Custom Resolver")
                return BypassResult(
                    success=True,
                    original_url=clean_url,
                    result_url=custom_res,
                    engine_used="Custom Resolver",
                    time_taken=round(time.time() - start_time, 2)
                )
        except Exception as e:
            print(f"[BypassManager] Custom resolver error: {e}")

        # 2. Thử Engine Public Bypass APIs (Linkvertise, AdFly, Work.ink...)
        try:
            api_res, api_name = await bypass_via_public_apis(clean_url)
            if api_res and api_res != clean_url:
                save_cached_bypass(clean_url, api_res, f"Bypass API ({api_name})")
                return BypassResult(
                    success=True,
                    original_url=clean_url,
                    result_url=api_res,
                    engine_used=f"Bypass API ({api_name})",
                    time_taken=round(time.time() - start_time, 2)
                )
        except Exception as e:
            print(f"[BypassManager] API bypass error: {e}")

        # 3. Thử Engine Redirect nhanh (Bitly, TinyURL, Cuttly...)
        try:
            redirect_res = await unshorten_redirect(clean_url)
            if redirect_res and redirect_res != clean_url:
                save_cached_bypass(clean_url, redirect_res, "HTTP Redirect Tracker")
                return BypassResult(
                    success=True,
                    original_url=clean_url,
                    result_url=redirect_res,
                    engine_used="HTTP Redirect Tracker",
                    time_taken=round(time.time() - start_time, 2)
                )
        except Exception as e:
            print(f"[BypassManager] Redirect error: {e}")

        # 4. Thử Stealth Browser cao cấp (Vượt Cloudflare Turnstile & trang rút gọn nhiều bước)
        if use_stealth:
            try:
                stealth_res = await bypass_stealth_browser(clean_url, max_wait=20.0)
                if stealth_res and stealth_res != clean_url:
                    save_cached_bypass(clean_url, stealth_res, "Stealth Browser (Turnstile Bypass)")
                    return BypassResult(
                        success=True,
                        original_url=clean_url,
                        result_url=stealth_res,
                        engine_used="Stealth Browser (Turnstile Bypass)",
                        time_taken=round(time.time() - start_time, 2)
                    )
            except Exception as e:
                print(f"[BypassManager] Stealth browser error: {e}")

        # Nếu cả 4 tầng đều không vượt được
        return BypassResult(
            success=False,
            original_url=clean_url,
            error_message="Không thể tìm thấy link đích hoặc trang web có captcha bảo vệ nâng cao.",
            time_taken=round(time.time() - start_time, 2)
        )
