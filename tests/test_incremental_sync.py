import json


def test_incremental_sync_updates_only_one_record(session):
    from app.models import BitableTable, CurrentRecord, Monitor
    from app.services.incremental_sync import run_incremental_sync

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()
    session.add(
        BitableTable(
            monitor_id=monitor.id,
            table_id="tbl1",
            table_name="账号表",
            field_schema_json=json.dumps([{"field_name": "姓名"}], ensure_ascii=False),
        )
    )
    session.commit()
    session.add(
        CurrentRecord(
            monitor_id=monitor.id,
            table_id="tbl1",
            record_id="rec1",
            sort_order=1,
            fields_json='{"姓名":"旧值"}',
            display_text="旧值",
        )
    )
    session.commit()

    class FakeClient:
        def get_bitable_record(self, app_token, table_id, record_id):
            assert app_token == "app123"
            assert table_id == "tbl1"
            assert record_id == "rec1"
            return {"record_id": record_id, "fields": {"姓名": "新值"}}

    run_incremental_sync(
        session=session,
        monitor_id=monitor.id,
        table_id="tbl1",
        actions=[{"record_id": "rec1", "action": "record_edited"}],
        client=FakeClient(),
    )

    row = session.query(CurrentRecord).filter_by(record_id="rec1").one()
    assert row.sort_order == 1
    assert json.loads(row.fields_json) == {"姓名": "新值"}
    assert row.display_text == "新值"


def test_incremental_sync_deletes_only_one_record(session):
    from app.models import BitableTable, CurrentRecord, Monitor
    from app.services.incremental_sync import run_incremental_sync

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()
    session.add(
        BitableTable(
            monitor_id=monitor.id,
            table_id="tbl1",
            table_name="账号表",
            field_schema_json=json.dumps([{"field_name": "姓名"}], ensure_ascii=False),
        )
    )
    session.commit()
    session.add_all(
        [
            CurrentRecord(
                monitor_id=monitor.id,
                table_id="tbl1",
                record_id="rec1",
                sort_order=1,
                fields_json='{"姓名":"张三"}',
                display_text="张三",
            ),
            CurrentRecord(
                monitor_id=monitor.id,
                table_id="tbl1",
                record_id="rec2",
                sort_order=2,
                fields_json='{"姓名":"李四"}',
                display_text="李四",
            ),
        ]
    )
    session.commit()

    class FakeClient:
        def get_bitable_record(self, app_token, table_id, record_id):
            raise AssertionError("delete events should not fetch the remote record")

    run_incremental_sync(
        session=session,
        monitor_id=monitor.id,
        table_id="tbl1",
        actions=[{"record_id": "rec1", "action": "record_deleted"}],
        client=FakeClient(),
    )

    rows = session.query(CurrentRecord).order_by(CurrentRecord.record_id).all()
    assert [(row.record_id, row.display_text) for row in rows] == [("rec2", "李四")]
