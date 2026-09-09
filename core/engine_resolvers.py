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

async def resolve_ouo(url: str) -> str | None:
    """
    Bypass hệ thống rút gọn ouo.io và ouo.press bằng cách mô phỏng gửi 2 bước xác thực token.
    """
    try:
        parsed = urlparse(url)
        ouo_id = parsed.path.strip("/").split("/")[-1]
        if not ouo_id or ouo_id in ["go", "xreall"]:
            return None

        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Tìm token bước 1
            token_input = soup.find("input", {"name": "_token"})
            if not token_input:
                return None

            token = token_input.get("value", "")
            go_url = f"{parsed.scheme}://{parsed.netloc}/go/{ouo_id}"
            
            headers = {
                **DEFAULT_HEADERS,
                "Referer": url,
                "Origin": f"{parsed.scheme}://{parsed.netloc}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            # Gửi bước 1
            resp2 = await client.post(go_url, data={"_token": token}, headers=headers)
            
            # Ouo thường chuyển tiếp tới bước 2 hoặc đích trực tiếp
            if str(resp2.url) != go_url and "ouo." not in urlparse(str(resp2.url)).netloc:
                return str(resp2.url)
                
            soup2 = BeautifulSoup(resp2.text, "html.parser")
            token_input2 = soup2.find("input", {"name": "_token"})
            if token_input2:
                token2 = token_input2.get("value", "")
                xreall_url = f"{parsed.scheme}://{parsed.netloc}/xreall/{ouo_id}"
                resp3 = await client.post(xreall_url, data={"_token": token2}, headers=headers)
                final_url = str(resp3.url)
                if "ouo." not in urlparse(final_url).netloc:
                    return final_url
    except Exception as e:
        print(f"[engine_resolvers] ouo error: {e}")
    return None

def resolve_query_redirects(url: str) -> str | None:
    """
    Tự động bóc tách link đích được giấu trong Query Parameters (Base64, Hex, URL-encoded).
    Hỗ trợ hàng loạt SafeLink, web blog trung gian, link rút gọn qua tham số.
    """
    try:
        parsed = urlparse(url)
        current_domain = parsed.netloc.lower()
        queries = parse_qs(parsed.query)
        
        target_keys = [
            "url", "link", "dest", "destination", "target",
            "r", "to", "go", "safe", "u", "redirect", "out", "download"
        ]
        
        for key in target_keys:
            if key in queries and queries[key]:
                val = queries[key][0].strip()
                
                # 1. Nếu là URL trực tiếp
                if val.startswith(("http://", "https://")):
                    if urlparse(val).netloc.lower() != current_domain:
                        return val
                        
                # 2. Thử URL decode
                unquoted = unquote(val)
                if unquoted.startswith(("http://", "https://")):
                    if urlparse(unquoted).netloc.lower() != current_domain:
                        return unquoted

                # 3. Thử Base64 decode
                try:
                    # Bổ sung padding nếu thiếu
                    padded = val + '=' * (-len(val) % 4)
                    decoded = base64.b64decode(padded).decode("utf-8", errors="ignore").strip()
                    if decoded.startswith(("http://", "https://")):
                        if urlparse(decoded).netloc.lower() != current_domain:
                            return decoded
                except Exception:
                    pass

                # 4. Thử Hex decode
                try:
                    decoded_hex = bytes.fromhex(val).decode("utf-8", errors="ignore").strip()
                    if decoded_hex.startswith(("http://", "https://")):
                        if urlparse(decoded_hex).netloc.lower() != current_domain:
                            return decoded_hex
                except Exception:
                    pass
    except Exception as e:
        print(f"[engine_resolvers] query_redirects error: {e}")
    return None

async def resolve_meta_and_js_redirect(url: str) -> str | None:
    """
    Trích xuất link chuyển tiếp thông qua thẻ <meta refresh> hoặc mã JavaScript (window.location).
    """
    try:
        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
            text = resp.text
            current_domain = urlparse(url).netloc.lower()

            # 1. Quét Meta Refresh: <meta http-equiv="refresh" content="0;url=https://...">
            meta_match = re.search(r'<meta[^>]*?content=["\']\d+;\s*url=([^"\']+)["\']', text, re.IGNORECASE)
            if meta_match:
                dest = meta_match.group(1).strip()
                full_dest = urljoin(str(resp.url), dest)
                if full_dest.startswith(("http://", "https://")) and urlparse(full_dest).netloc.lower() != current_domain:
                    return full_dest

            # 2. Quét JavaScript Redirect: window.location.href / window.location.replace / location.href
            js_match = re.search(r'(?:window\.)?location(?:\.href|\.replace)?\s*(?:=|\()\s*["\'](https?://[^"\']+)["\']', text, re.IGNORECASE)
            if js_match:
                dest = js_match.group(1).strip()
                if dest.startswith(("http://", "https://")) and urlparse(dest).netloc.lower() != current_domain:
                    return dest
    except Exception as e:
        print(f"[engine_resolvers] meta_js_redirect error: {e}")
    return None

def resolve_google_drive(url: str) -> str | None:
    """
    Chuyển đổi link xem trước Google Drive sang Direct Download Link.
    """
    match = re.search(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return None

TERABOX_DOMAINS = [
    "terabox.com", "teraboxapp.com", "1024tera.com", "terasharelink.com",
    "terabox.app", "freeterabox.com", "mirrobox.com", "nephobox.com", "4funbox.com"
]

def is_terabox_url(url: str) -> bool:
    domain = urlparse(url).netloc.lower()
    return any(td in domain for td in TERABOX_DOMAINS)

def extract_terabox_surl(url: str) -> str | None:
    match = re.search(r'/s/([a-zA-Z0-9_-]+)', url)
    if match:
        surl = match.group(1)
        if surl.startswith("1"):
            return surl[1:]
        return surl
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "surl" in qs and qs["surl"]:
        surl = qs["surl"][0]
        if surl.startswith("1"):
            return surl[1:]
        return surl
    return None

async def resolve_terabox(url: str) -> str | None:
    """
    Bóc tách link tải trực tiếp (Direct Download Link) từ link Terabox không cần app.
    Hỗ trợ terabox.com, teraboxapp, 1024tera, terasharelink...
    """
    if not is_terabox_url(url):
        return None

    surl = extract_terabox_surl(url)
    
    # 1. Thử API Savetube Terabox Downloader
    try:
        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=12.0) as client:
            resp = await client.post(
                "https://ytshorts.savetube.me/api/v1/terabox-downloader",
                json={"url": url}
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("response", [])
                if items and isinstance(items, list):
                    item = items[0]
                    resolutions = item.get("resolutions", {})
                    dlink = (
                        resolutions.get("Fast Download")
                        or resolutions.get("HD Video")
                        or resolutions.get("Download")
                    )
                    if dlink and str(dlink).startswith(("http://", "https://")):
                        return str(dlink)
    except Exception as e:
        print(f"[engine_resolvers] terabox API 1 error: {e}")

    # 2. Thử API Workers Terabox DL
    if surl:
        try:
            async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=12.0) as client:
                api_url = f"https://terabox-dl.qtcloud.workers.dev/api/get-info?shorturl={surl}"
                resp = await client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    dlink = data.get("download_url") or data.get("dlink")
                    if dlink and str(dlink).startswith(("http://", "https://")):
                        return str(dlink)
                    file_list = data.get("list", [])
                    if file_list and isinstance(file_list, list):
                        dlink = file_list[0].get("dlink")
                        if dlink and str(dlink).startswith(("http://", "https://")):
                            return str(dlink)
        except Exception as e:
            print(f"[engine_resolvers] terabox API 2 error: {e}")

    # 3. Thử API Terabox App Info
    if surl:
        try:
            headers = {
                **DEFAULT_HEADERS,
                "Referer": "https://www.terabox.app/",
            }
            async with httpx.AsyncClient(headers=headers, timeout=12.0) as client:
                resp = await client.get(f"https://www.terabox.app/api/shorturlinfo?shorturl={surl}&root=1")
                if resp.status_code == 200:
                    data = resp.json()
                    file_list = data.get("list", [])
                    if file_list and isinstance(file_list, list):
                        dlink = file_list[0].get("dlink")
                        if dlink and str(dlink).startswith(("http://", "https://")):
                            return str(dlink)
        except Exception as e:
            print(f"[engine_resolvers] terabox API 3 error: {e}")

    return None

async def run_custom_resolvers(url: str) -> str | None:
    domain = urlparse(url).netloc.lower()
    
    # 1. Bóc tách tham số Query Parameters (cực nhanh, không cần mạng)
    query_res = resolve_query_redirects(url)
    if query_res:
        return query_res

    # 2. Terabox Direct Download Link
    if is_terabox_url(url):
        tb_res = await resolve_terabox(url)
        if tb_res:
            return tb_res

    # 3. Google Drive direct link
    if "drive.google.com" in domain:
        drive_res = resolve_google_drive(url)
        if drive_res:
            return drive_res

    # 4. Thử giải mã AdLinkFly (linkx, link1s, megaurl, droplink, shrtfly...)
    adlink_res = await resolve_adlinkfly(url)
    if adlink_res:
        return adlink_res

    # 5. Dịch vụ Ouo (ouo.io, ouo.press)
    if "ouo.io" in domain or "ouo.press" in domain:
        ouo_res = await resolve_ouo(url)
        if ouo_res:
            return ouo_res

    # 6. Dịch vụ Sub2Unlock / Sub4Unlock
    if "sub2unlock" in domain or "sub4unlock" in domain:
        return await resolve_sub2unlock(url)

    # 7. Mediafire
    if "mediafire.com" in domain:
        return await resolve_mediafire(url)

    # 8. Pastebin
    if "pastebin.com" in domain:
        return await resolve_pastebin(url)

    # 9. Quét Meta Refresh và JS Redirects nếu có
    meta_res = await resolve_meta_and_js_redirect(url)
    if meta_res:
        return meta_res
        
    return None

