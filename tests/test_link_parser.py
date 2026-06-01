import pytest


def test_parse_direct_bitable_link():
    from app.services.link_parser import parse_bitable_link

    parsed = parse_bitable_link("https://example.feishu.cn/base/app123")

    assert parsed.link_type == "bitable"
    assert parsed.link_token == "app123"


def test_parse_wiki_bitable_link():
    from app.services.link_parser import parse_bitable_link

    parsed = parse_bitable_link("https://example.feishu.cn/wiki/SioWwTP5Uiryn8kIez6cjjDMnNM")

    assert parsed.link_type == "wiki"
    assert parsed.link_token == "SioWwTP5Uiryn8kIez6cjjDMnNM"


def test_parse_bitable_link_rejects_empty_token():
    from app.services.link_parser import parse_bitable_link

    with pytest.raises(ValueError, match="仅支持飞书多维表格链接"):
        parse_bitable_link("https://example.feishu.cn/base/")
