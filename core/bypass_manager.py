from dataclasses import dataclass
import time
from .engine_redirect import unshorten_redirect
from .engine_resolvers import run_custom_resolvers
from .engine_api import bypass_via_public_apis

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
    async def bypass(url: str) -> BypassResult:
        start_time = time.time()
        clean_url = url.strip()

        # 1. Thử Engine Resolvers tùy biến trước (Sub2Unlock, Mediafire...)
        try:
            custom_res = await run_custom_resolvers(clean_url)
            if custom_res and custom_res != clean_url:
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
                return BypassResult(
                    success=True,
                    original_url=clean_url,
                    result_url=redirect_res,
                    engine_used="HTTP Redirect Tracker",
                    time_taken=round(time.time() - start_time, 2)
                )
        except Exception as e:
            print(f"[BypassManager] Redirect error: {e}")

        # Nếu cả 3 tầng đều không vượt được
        return BypassResult(
            success=False,
            original_url=clean_url,
            error_message="Không thể tìm thấy link đích hoặc trang web có captcha bảo vệ nâng cao.",
            time_taken=round(time.time() - start_time, 2)
        )
