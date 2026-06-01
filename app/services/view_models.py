from __future__ import annotations

import json
from math import ceil


def _safe_load_fields(fields_json: str | None) -> dict:
    if not fields_json:
        return {}

    try:
        loaded = json.loads(fields_json)
    except json.JSONDecodeError:
        return {}

    return loaded if isinstance(loaded, dict) else {}


def _build_pagination_pages(current_page: int, total_pages: int) -> list[int | None]:
    if total_pages <= 7:
        return list(range(1, total_pages + 1))

    window_start = max(2, current_page - 2)
    window_end = min(total_pages - 1, current_page + 2)

    if current_page <= 4:
        window_start, window_end = 2, 6
    elif current_page >= total_pages - 3:
        window_start, window_end = total_pages - 5, total_pages - 1

    pages: list[int | None] = [1]
    if window_start > 2:
        pages.append(None)
    pages.extend(range(window_start, window_end + 1))
    if window_end < total_pages - 1:
        pages.append(None)
    pages.append(total_pages)
    return pages


def build_current_record_view(
    *,
    records,
    tables: list[dict],
    active_table_id: str | None,
    page: int,
    page_size: int = 20,
):
    table_map = {table["id"]: table for table in tables}
    ordered_table_ids = [table["id"] for table in tables]

    if active_table_id in table_map:
        selected_table_id = active_table_id
    else:
        selected_table_id = ordered_table_ids[0] if ordered_table_ids else None

    selected_table = table_map.get(selected_table_id) if selected_table_id else None
    field_names = list(selected_table.get("field_names", [])) if selected_table else []
    if not field_names and records:
        fallback_fields: list[str] = []
        for row in records:
            for field_name in _safe_load_fields(row.fields_json).keys():
                if field_name not in fallback_fields:
                    fallback_fields.append(field_name)
        field_names = fallback_fields

    headers = ["记录ID", *field_names]
    body_rows: list[list[str]] = []
    for row in records:
        fields = _safe_load_fields(row.fields_json)
        body_rows.append([row.record_id, *[str(fields.get(name, "")) for name in field_names]])

    total_count = selected_table.get("count", 0) if selected_table else 0
    total_pages = max(1, ceil(total_count / page_size)) if total_count else 1
    current_page = min(max(page, 1), total_pages)

    tabs = [
        {
            "id": table["id"],
            "label": table["label"],
            "count": table["count"],
            "active": table["id"] == selected_table_id,
        }
        for table in tables
    ]

    return {
        "tabs": tabs,
        "headers": headers,
        "rows": body_rows,
        "active_table_id": selected_table_id,
        "empty": total_count == 0,
        "pagination": {
            "page": current_page,
            "total_pages": total_pages,
            "pages": _build_pagination_pages(current_page, total_pages),
        },
    }
