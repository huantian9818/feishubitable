from app.services.field_text import fields_to_display_text, value_to_plain_text


def test_value_to_plain_text_prefers_name_for_people_values():
    value = [
        {
            "id": "ou_1",
            "name": "仇东波",
            "email": "qiudongbo@boohee.com",
            "avatar_url": "https://example.com/a.jpg",
        },
        {
            "id": "ou_2",
            "name": "夏健",
            "email": "xiajian@boohee.com",
            "avatar_url": "https://example.com/b.jpg",
        },
    ]

    assert value_to_plain_text(value) == "仇东波、夏健"


def test_value_to_plain_text_uses_text_for_link_like_values():
    value = [{"record_ids": ["rec1"], "table_id": "tbl1", "text": "主账号", "text_arr": [], "type": "text"}]

    assert value_to_plain_text(value) == "主账号"


def test_fields_to_display_text_drops_empty_structured_fragments():
    fields = {
        "管理员": [{"id": "ou_1", "name": "仇东波"}],
        "父记录": [{"record_ids": None, "table_id": "tbl1", "text": None, "text_arr": [], "type": "text"}],
        "备注": None,
        "状态": "在线",
    }

    assert fields_to_display_text(fields) == "仇东波 | 在线"
