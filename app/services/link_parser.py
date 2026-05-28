from urllib.parse import urlparse


def parse_bitable_link(url: str) -> str:
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if len(parts) < 2 or parts[0] != "base":
        raise ValueError("仅支持飞书多维表格链接")
    return parts[1]
