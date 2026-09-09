import re
import base64
import json
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote, urljoin

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
}

async def resolve_sub2unlock(url: str) -> str | None:
    """
    Bypass các trang bắt đăng ký/sub kênh youtube như sub2unlock, sub4unlock...
    Thường link đích được mã hóa base64 trong URL hoặc DOM script.
    """
    try:
        parsed = urlparse(url)
        queries = parse_qs(parsed.query)
        for key in ["url", "target", "link", "destination"]:
            if key in queries and queries[key]:
                val = queries[key][0]
                try:
                    decoded = base64.b64decode(val).decode("utf-8")
                    if decoded.startswith(("http://", "https://")):
                        return decoded
                except Exception:
                    if val.startswith(("http://", "https://")):
                        return val

        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
            text = resp.text
            match = re.search(r'(?:destination|targetUrl|theLink)\s*=\s*["\'](https?://[^"\']+)["\']', text)
            if match:
                return match.group(1)
            
            b64_matches = re.findall(r'[A-Za-z0-9+/=]{20,}', text)
            for item in b64_matches:
                try:
                    decoded = base64.b64decode(item).decode("utf-8")
                    if decoded.startswith(("http://", "https://")) and "youtube.com" not in decoded:
                        return decoded
                except Exception:
                    pass
    except Exception as e:
        print(f"[engine_resolvers] sub2unlock error: {e}")
    return None

async def resolve_adlinkfly(url: str) -> str | None:
    """
    Bypass các trang rút gọn kiếm tiền sử dụng mã nguồn AdLinkFly phổ biến ở VN và quốc tế
    (như linkx.me, link1s, megaurl, shrtfly...) bằng cách gọi trực tiếp API /links/go.
    """
    try:
        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Tìm form go-link
            form = soup.find("form", {"id": "go-link"})
            if not form:
                # Tìm form có action chứa /links/go
                form = soup.find("form", action=re.compile(r"/links/go", re.IGNORECASE))

            if form:
                action = form.get("action", "/links/go")
                target_api = urljoin(str(resp.url), action)
                
                # Thu thập dữ liệu input (csrfToken, ad_form_data...)
                payload = {}
                for inp in form.find_all("input"):
                    name = inp.get("name")
                    if name:
                        payload[name] = inp.get("value", "")

                headers = {
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": f"{resp.url.scheme}://{resp.url.netloc}",
                    "Referer": str(resp.url),
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
                }

                api_resp = await client.post(target_api, data=payload, headers=headers)
                if api_resp.status_code == 200:
                    try:
                        data = api_resp.json()
                        result_url = data.get("url")
                        if result_url and str(result_url).startswith(("http://", "https://")):
                            return str(result_url)
                    except Exception:
                        pass
    except Exception as e:
        print(f"[engine_resolvers] adlinkfly error: {e}")
    return None

async def resolve_mediafire(url: str) -> str | None:
    """
    Lấy direct download link từ trang Mediafire.
    """
    try:
        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            btn = soup.find("a", {"id": "downloadButton"})
            if btn and btn.get("href"):
                return btn.get("href")
    except Exception as e:
        print(f"[engine_resolvers] mediafire error: {e}")
    return None

async def resolve_pastebin(url: str) -> str | None:
    """
    Lấy nội dung raw từ pastebin hoặc trích xuất link đích nếu pastebin chứa 1 link duy nhất.
    """
    try:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if path and not path.startswith("raw/"):
            raw_url = f"https://pastebin.com/raw/{path}"
            async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=10.0) as client:
                resp = await client.get(raw_url)
                if resp.status_code == 200:
                    content = resp.text.strip()
                    if content.startswith(("http://", "https://")) and "\n" not in content:
                        return content
                    return raw_url
    except Exception as e:
        print(f"[engine_resolvers] pastebin error: {e}")
    return None

async def run_custom_resolvers(url: str) -> str | None:
    domain = urlparse(url).netloc.lower()
    
    # 1. Thử giải mã AdLinkFly (Hỗ trợ hầu hết các trang rút gọn VN như linkx, link1s, megaurl...)
    adlink_res = await resolve_adlinkfly(url)
    if adlink_res:
        return adlink_res

    # 2. Thử các dịch vụ chuyên biệt khác
    if "sub2unlock" in domain or "sub4unlock" in domain:
        return await resolve_sub2unlock(url)
    if "mediafire.com" in domain:
        return await resolve_mediafire(url)
    if "pastebin.com" in domain:
        return await resolve_pastebin(url)
        
    return None
