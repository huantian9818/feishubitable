from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class ParsedBitableLink:
    link_type: str
    link_token: str


def parse_bitable_link(url: str) -> ParsedBitableLink:
    path = urlparse(url).path.strip("/")
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2 or not parts[-1]:
        raise ValueError("仅支持飞书多维表格链接")

    link_type = parts[-2]
    link_token = parts[-1]
    if link_type == "base":
        return ParsedBitableLink(link_type="bitable", link_token=link_token)
    if link_type == "wiki":
        return ParsedBitableLink(link_type="wiki", link_token=link_token)
    raise ValueError("仅支持飞书多维表格链接")


def resolve_bitable_app_token(url: str, client) -> str:
    parsed = parse_bitable_link(url)
    if parsed.link_type == "bitable":
        return parsed.link_token

    resolved = client.resolve_wiki_node(parsed.link_token)
    resolved_type = resolved.get("obj_type")
    resolved_token = resolved.get("obj_token")
    if resolved_type not in {"bitable", "base"} or not resolved_token:
        raise ValueError("知识库链接解析后不是飞书多维表格")
    return str(resolved_token)
