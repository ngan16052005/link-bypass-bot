import httpx
from urllib.parse import urlparse

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
}

async def unshorten_redirect(url: str, timeout: float = 12.0) -> str | None:
    """
    Theo dõi chuỗi chuyển hướng (HTTP 301/302/307/308) của các dịch vụ rút gọn link.
    Trả về URL đích cuối cùng nếu thành công, hoặc None nếu không thay đổi/lỗi.
    """
    try:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=timeout,
            verify=False
        ) as client:
            resp = await client.get(url)
            final_url = str(resp.url)
            
            # Nếu URL đích khác URL ban đầu và không phải trang lỗi
            if final_url != url and resp.status_code < 400:
                return final_url
    except Exception as e:
        print(f"[engine_redirect] Error following redirects for {url}: {e}")
        
    return None
