import httpx
from urllib.parse import quote

PUBLIC_BYPASS_APIS = [
    {
        "name": "BypassVIP",
        "url": "https://api.bypass.vip/bypass?url={url}",
        "parser": lambda data: data.get("result") if data.get("status") == "success" else None
    },
    {
        "name": "ZenithBypass",
        "url": "https://api.zenithbypass.com/bypass?url={url}",
        "parser": lambda data: data.get("result") or data.get("destination")
    },
    {
        "name": "SlinkBypass",
        "url": "https://bypass.pm/bypass2?url={url}",
        "parser": lambda data: data.get("destination") or data.get("result")
    }
]


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json"
}

async def bypass_via_public_apis(url: str, timeout: float = 15.0) -> tuple[str | None, str]:
    """
    Thử gọi tuần tự các API bypass công cộng của cộng đồng (dành cho Linkvertise, AdFly, Work.ink, v.v.).
    Trả về: (direct_url, api_name) hoặc (None, "")
    """
    encoded_url = quote(url, safe="")
    
    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=timeout) as client:
        for api in PUBLIC_BYPASS_APIS:
            try:
                target_api_url = api["url"].format(url=encoded_url)
                resp = await client.get(target_api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    result = api["parser"](data)
                    if result and str(result).startswith(("http://", "https://")):
                        return str(result), api["name"]
            except Exception as e:
                # Log và tiếp tục thử API dự phòng kế tiếp
                continue

    return None, ""
