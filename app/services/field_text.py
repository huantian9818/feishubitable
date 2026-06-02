from __future__ import annotations


_PREFERRED_DICT_KEYS = ("name", "text", "title", "label", "value", "en_name")
_IGNORED_DICT_KEYS = {
    "id",
    "email",
    "avatar_url",
    "record_ids",
    "table_id",
    "type",
    "url",
    "link",
    "href",
}


def value_to_plain_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        parts = [value_to_plain_text(item).strip() for item in value]
        return "、".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in _PREFERRED_DICT_KEYS:
            text = value_to_plain_text(value.get(key)).strip()
            if text:
                return text

        text_arr = value.get("text_arr")
        if isinstance(text_arr, list):
            text = value_to_plain_text(text_arr).strip()
            if text:
                return text

        parts = [
            value_to_plain_text(item).strip()
            for key, item in value.items()
            if key not in _IGNORED_DICT_KEYS
        ]
        return " ".join(part for part in parts if part)
    return str(value)


def fields_to_display_text(fields: dict) -> str:
    return " | ".join(
        text
        for text in (value_to_plain_text(value).strip() for value in fields.values())
        if text
    )
