import re
import urllib.parse
import httpx

# Danh sách các tham số quảng cáo / theo dõi cần loại bỏ
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id", "utm_name",
    "fbclid", "gclid", "gclsrc", "dclid", "msclkid", "twclid",
    "ref", "ref_src", "referrer", "affiliate_id", "subid", "partner",
    "igshid", "yclid", "mc_eid", "source", "ad_id", "campaign_id"
}

def clean_url(url: str) -> str:
    """
    Loại bỏ các tham số rác theo dõi (UTM, Facebook Click ID, Google Ads, v.v.)
    giúp URL đích luôn ngắn gọn, sạch sẽ và an toàn.
    """
    if not url or not isinstance(url, str):
        return url

    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.query:
            return url

        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        # Giữ lại các param không nằm trong danh sách tracking
        clean_pairs = [
            (k, v) for k, v in query_pairs 
            if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
        ]

        # Nếu không có gì thay đổi
        if len(clean_pairs) == len(query_pairs):
            return url

        new_query = urllib.parse.urlencode(clean_pairs)
        clean_parts = list(parsed)
        clean_parts[4] = new_query
        return urllib.parse.urlunparse(clean_parts)
    except Exception as e:
        print(f"[Enricher] clean_url error: {e}")
        return url

def format_file_size(size_bytes: int) -> str:
    """Định dạng byte sang KB, MB, GB dễ đọc."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

async def fetch_file_metadata(url: str) -> dict:
    """
    Gửi request nhanh (2.5s) để lấy thông tin tệp tải về (Tên file, dung lượng, định dạng)
    nếu URL là một tệp trực tiếp (Direct download, Terabox, Mediafire, Google Drive, v.v.)
    """
    default_res = {
        "has_info": False,
        "file_name": "",
        "file_size": "",
        "content_type": ""
    }

    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return default_res

    # Chỉ quét nếu URL có vẻ là tệp tải về hoặc domain lưu trữ
    file_extensions = (
        ".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".exe", ".apk", ".msi",
        ".mp4", ".mkv", ".mp3", ".wav", ".pdf", ".docx", ".xlsx", ".pptx", ".txt"
    )
    is_direct_ext = any(url.lower().split("?")[0].endswith(ext) for ext in file_extensions)
    storage_domains = ("mediafire.com", "terabox", "1024tera", "drive.google.com", "dropbox.com", "mega.nz", "fshare.vn")
    is_storage = any(sd in url.lower() for sd in storage_domains)

    if not (is_direct_ext or is_storage):
        return default_res

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }

    try:
        async with httpx.AsyncClient(timeout=2.5, follow_redirects=True, verify=False) as client:
            resp = await client.head(url, headers=headers)
            
            # Nếu HEAD bị chặn, thử Range GET 1 byte
            if resp.status_code in [403, 405]:
                headers["Range"] = "bytes=0-0"
                resp = await client.get(url, headers=headers)

            if resp.status_code in [200, 206]:
                # 1. Dung lượng file
                size_str = ""
                content_range = resp.headers.get("Content-Range", "")
                content_len = resp.headers.get("Content-Length", "")
                
                if "/" in content_range:
                    try:
                        total_bytes = int(content_range.split("/")[-1])
                        size_str = format_file_size(total_bytes)
                    except Exception:
                        pass
                elif content_len and content_len.isdigit():
                    size_bytes = int(content_len)
                    if size_bytes > 0:
                        size_str = format_file_size(size_bytes)

                # 2. Tên file từ header Content-Disposition
                fname = ""
                cd = resp.headers.get("Content-Disposition", "")
                if "filename=" in cd:
                    match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^";\n]+)["\']?', cd, re.I)
                    if match:
                        fname = urllib.parse.unquote(match.group(1).strip())
                
                # Nếu không có trong header, lấy từ đường dẫn URL
                if not fname:
                    path = urllib.parse.urlparse(url).path
                    base_name = path.split("/")[-1]
                    if any(base_name.lower().endswith(ext) for ext in file_extensions):
                        fname = urllib.parse.unquote(base_name)

                # 3. Content Type
                ctype = resp.headers.get("Content-Type", "").split(";")[0].strip()

                if size_str or fname:
                    return {
                        "has_info": True,
                        "file_name": fname or "Tệp tin trực tiếp",
                        "file_size": size_str,
                        "content_type": ctype
                    }

    except Exception as e:
        # Bỏ qua lỗi kết nối timeout nhanh
        pass

    return default_res
