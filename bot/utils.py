import re

URL_REGEX = re.compile(
    r'(?:https?://|www\.)[^\s/$.?#].[^\s]*',
    re.IGNORECASE
)

def extract_urls(text: str) -> list[str]:
    """
    Trích xuất danh sách các URL có trong một đoạn văn bản.
    """
    if not text:
        return []
    matches = URL_REGEX.findall(text)
    clean_urls = []
    for m in matches:
        # Làm sạch dấu câu cuối URL nếu có
        cleaned = m.rstrip(".,;!?)>]\'\"")
        if not cleaned.startswith(("http://", "https://")):
            cleaned = "https://" + cleaned
        clean_urls.append(cleaned)
    return clean_urls
