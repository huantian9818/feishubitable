from types import SimpleNamespace


def test_build_current_record_view_prefers_schema_headers_over_first_row_fields():
    from app.services.view_models import build_current_record_view

    rows = [
        SimpleNamespace(record_id="rec1", fields_json='{"姓名":"张三"}'),
        SimpleNamespace(record_id="rec2", fields_json='{"姓名":"李四","部门":"研发"}'),
    ]
    tables = [
        {
            "id": "tbl1",
            "label": "员工表",
            "count": 2,
            "field_names": ["姓名", "部门"],
        }
    ]

    view = build_current_record_view(
        records=rows,
        tables=tables,
        active_table_id="tbl1",
        page=1,
        page_size=20,
    )

    assert view["headers"] == ["记录ID", "姓名", "部门"]
    assert view["rows"][0] == ["rec1", "张三", ""]


def test_build_current_record_view_tolerates_bad_record_json():
    from app.services.view_models import build_current_record_view

    rows = [SimpleNamespace(record_id="rec1", fields_json="{bad json}")]
    tables = [{"id": "tbl1", "label": "员工表", "count": 1, "field_names": ["姓名"]}]

    view = build_current_record_view(
        records=rows,
        tables=tables,
        active_table_id="tbl1",
        page=1,
        page_size=20,
    )

    assert view["headers"] == ["记录ID", "姓名"]
    assert view["rows"] == [["rec1", ""]]


def test_build_current_record_view_limits_pagination_window_for_large_tables():
    from app.services.view_models import build_current_record_view

    view = build_current_record_view(
        records=[],
        tables=[{"id": "tbl1", "label": "员工表", "count": 600, "field_names": ["姓名"]}],
        active_table_id="tbl1",
        page=15,
        page_size=20,
    )

    assert view["pagination"]["pages"] == [1, None, 13, 14, 15, 16, 17, None, 30]
