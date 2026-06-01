import json

import pytest


def test_run_full_sync_rebuilds_tables_records_and_sync_run(session):
    from app.models import BitableTable, CurrentRecord, Monitor, SyncRun
    from app.services.full_sync import run_full_sync

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/abc",
        app_token="abc",
        fallback_interval_minutes=360,
        last_sync_error="old error",
    )
    session.add(monitor)
    session.commit()

    session.add(
        BitableTable(
            monitor_id=monitor.id,
            table_id="tbl_old",
            table_name="旧表",
            field_schema_json=json.dumps([{"field_name": "旧字段"}], ensure_ascii=False),
        )
    )
    session.commit()
    session.add(
        CurrentRecord(
            monitor_id=monitor.id,
            table_id="tbl_old",
            record_id="rec_old",
            sort_order=1,
            fields_json=json.dumps({"旧字段": "旧值"}, ensure_ascii=False),
            display_text="旧值",
        )
    )
    session.commit()

    class FakeClient:
        def get_bitable_meta(self, app_token):
            return {"app_token": app_token}

        def get_bitable_tables(self, app_token):
            return [
                {
                    "table_id": "tbl1",
                    "name": "员工表",
                    "fields": [{"field_id": "f1", "field_name": "姓名"}],
                }
            ]

        def list_bitable_records(self, app_token, table_id):
            return [{"record_id": "rec1", "fields": {"姓名": "张三"}}]

        def refresh_bitable_subscription(self, app_token):
            assert app_token == "abc"
            return {"ok": True}

    result = run_full_sync(session, monitor.id, FakeClient(), trigger_type="initial")

    session.refresh(monitor)
    tables = session.query(BitableTable).filter_by(monitor_id=monitor.id).all()
    records = session.query(CurrentRecord).filter_by(monitor_id=monitor.id).all()
    sync_runs = session.query(SyncRun).filter_by(monitor_id=monitor.id).all()

    assert result.trigger_type == "initial"
    assert result.record_count == 1
    assert [(table.table_id, table.table_name) for table in tables] == [("tbl1", "员工表")]
    assert json.loads(tables[0].field_schema_json) == [{"field_id": "f1", "field_name": "姓名"}]
    assert [(record.table_id, record.record_id, record.sort_order) for record in records] == [("tbl1", "rec1", 1)]
    assert json.loads(records[0].fields_json) == {"姓名": "张三"}
    assert records[0].display_text == "张三"
    assert monitor.current_record_count == 1
    assert monitor.sync_status == "success"
    assert monitor.subscription_status == "subscribed"
    assert monitor.subscription_error is None
    assert monitor.last_sync_error is None
    assert monitor.last_sync_at is not None
    assert monitor.last_full_sync_at == monitor.last_sync_at
    assert monitor.next_fallback_sync_at is not None
    assert len(sync_runs) == 1
    assert sync_runs[0].trigger_type == "initial"
    assert sync_runs[0].status == "success"
    assert sync_runs[0].error_message is None
    assert json.loads(sync_runs[0].stats_json) == {"record_count": 1}


def test_run_full_sync_marks_subscription_failed_without_rolling_back_data(session):
    from app.models import BitableTable, CurrentRecord, Monitor, SyncRun
    from app.services.full_sync import run_full_sync

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/abc",
        app_token="abc",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    class FakeClient:
        def get_bitable_meta(self, app_token):
            return {"app_token": app_token}

        def get_bitable_tables(self, app_token):
            return [
                {
                    "table_id": "tbl1",
                    "name": "员工表",
                    "fields": [{"field_id": "f1", "field_name": "姓名"}],
                }
            ]

        def list_bitable_records(self, app_token, table_id):
            return [{"record_id": "rec1", "fields": {"姓名": "张三"}}]

        def refresh_bitable_subscription(self, app_token):
            raise RuntimeError("subscription forbidden")

    result = run_full_sync(session, monitor.id, FakeClient(), trigger_type="initial")

    session.refresh(monitor)
    tables = session.query(BitableTable).filter_by(monitor_id=monitor.id).all()
    records = session.query(CurrentRecord).filter_by(monitor_id=monitor.id).all()
    sync_runs = session.query(SyncRun).filter_by(monitor_id=monitor.id).all()

    assert result.trigger_type == "initial"
    assert result.record_count == 1
    assert [(table.table_id, table.table_name) for table in tables] == [("tbl1", "员工表")]
    assert [(record.table_id, record.record_id, record.display_text) for record in records] == [("tbl1", "rec1", "张三")]
    assert monitor.sync_status == "success"
    assert monitor.subscription_status == "failed"
    assert monitor.subscription_error == "subscription forbidden"
    assert len(sync_runs) == 1
    assert sync_runs[0].status == "success"


def test_run_table_resync_refreshes_only_target_table(session):
    from app.models import BitableTable, CurrentRecord, Monitor, SyncRun
    from app.services.full_sync import run_table_resync

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/abc",
        app_token="abc",
        fallback_interval_minutes=360,
        current_record_count=3,
    )
    session.add(monitor)
    session.commit()
    session.add_all(
        [
            BitableTable(
                monitor_id=monitor.id,
                table_id="tbl_accounts",
                table_name="账号表",
                field_schema_json=json.dumps([{"field_name": "旧姓名"}], ensure_ascii=False),
            ),
            BitableTable(
                monitor_id=monitor.id,
                table_id="tbl_assets",
                table_name="资产表",
                field_schema_json=json.dumps([{"field_name": "资产编号"}], ensure_ascii=False),
            ),
        ]
    )
    session.commit()
    session.add_all(
        [
            CurrentRecord(
                monitor_id=monitor.id,
                table_id="tbl_accounts",
                record_id="rec_old_1",
                sort_order=1,
                fields_json=json.dumps({"旧姓名": "旧值1"}, ensure_ascii=False),
                display_text="旧值1",
            ),
            CurrentRecord(
                monitor_id=monitor.id,
                table_id="tbl_accounts",
                record_id="rec_old_2",
                sort_order=2,
                fields_json=json.dumps({"旧姓名": "旧值2"}, ensure_ascii=False),
                display_text="旧值2",
            ),
            CurrentRecord(
                monitor_id=monitor.id,
                table_id="tbl_assets",
                record_id="asset_1",
                sort_order=1,
                fields_json=json.dumps({"资产编号": "A-001"}, ensure_ascii=False),
                display_text="A-001",
            ),
        ]
    )
    session.commit()

    class FakeClient:
        def get_bitable_tables(self, app_token):
            assert app_token == "abc"
            return [
                {
                    "table_id": "tbl_accounts",
                    "name": "账号表",
                    "fields": [{"field_id": "f1", "field_name": "姓名"}],
                },
                {
                    "table_id": "tbl_assets",
                    "name": "资产表",
                    "fields": [{"field_id": "f2", "field_name": "资产编号"}],
                },
            ]

        def list_bitable_records(self, app_token, table_id):
            assert app_token == "abc"
            assert table_id == "tbl_accounts"
            return [
                {"record_id": "rec_new_1", "fields": {"姓名": "张三"}},
                {"record_id": "rec_new_2", "fields": {"姓名": "李四"}},
            ]

    result = run_table_resync(
        session,
        monitor.id,
        "tbl_accounts",
        FakeClient(),
        trigger_type="event_field_table_resync",
    )

    session.refresh(monitor)
    accounts_table = session.query(BitableTable).filter_by(monitor_id=monitor.id, table_id="tbl_accounts").one()
    assets_table = session.query(BitableTable).filter_by(monitor_id=monitor.id, table_id="tbl_assets").one()
    accounts_records = (
        session.query(CurrentRecord)
        .filter_by(monitor_id=monitor.id, table_id="tbl_accounts")
        .order_by(CurrentRecord.sort_order.asc())
        .all()
    )
    assets_records = session.query(CurrentRecord).filter_by(monitor_id=monitor.id, table_id="tbl_assets").all()
    sync_runs = session.query(SyncRun).filter_by(monitor_id=monitor.id).all()

    assert result.trigger_type == "event_field_table_resync"
    assert result.record_count == 2
    assert json.loads(accounts_table.field_schema_json) == [{"field_id": "f1", "field_name": "姓名"}]
    assert json.loads(assets_table.field_schema_json) == [{"field_name": "资产编号"}]
    assert [(record.record_id, record.display_text) for record in accounts_records] == [
        ("rec_new_1", "张三"),
        ("rec_new_2", "李四"),
    ]
    assert [(record.record_id, record.display_text) for record in assets_records] == [("asset_1", "A-001")]
    assert monitor.current_record_count == 3
    assert monitor.sync_status == "success"
    assert monitor.last_sync_error is None
    assert monitor.last_sync_at is not None
    assert monitor.last_full_sync_at is None
    assert len(sync_runs) == 1
    assert sync_runs[0].trigger_type == "event_field_table_resync"
    assert sync_runs[0].status == "success"
    assert json.loads(sync_runs[0].stats_json) == {"table_id": "tbl_accounts", "record_count": 2}


def test_run_full_sync_keeps_existing_rows_when_client_fetch_fails(session):
    from app.models import BitableTable, CurrentRecord, Monitor, SyncRun
    from app.services.full_sync import run_full_sync

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/abc",
        app_token="abc",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    session.add(
        BitableTable(
            monitor_id=monitor.id,
            table_id="tbl_old",
            table_name="旧表",
            field_schema_json=json.dumps([{"field_name": "旧字段"}], ensure_ascii=False),
        )
    )
    session.commit()
    session.add(
        CurrentRecord(
            monitor_id=monitor.id,
            table_id="tbl_old",
            record_id="rec_old",
            sort_order=1,
            fields_json=json.dumps({"旧字段": "旧值"}, ensure_ascii=False),
            display_text="旧值",
        )
    )
    session.commit()

    class FailingClient:
        def get_bitable_meta(self, app_token):
            return {"app_token": app_token}

        def get_bitable_tables(self, app_token):
            return [
                {
                    "table_id": "tbl1",
                    "name": "员工表",
                    "fields": [{"field_id": "f1", "field_name": "姓名"}],
                }
            ]

        def list_bitable_records(self, app_token, table_id):
            raise RuntimeError("remote fetch failed")

    with pytest.raises(RuntimeError, match="remote fetch failed"):
        run_full_sync(session, monitor.id, FailingClient(), trigger_type="initial")

    session.refresh(monitor)
    tables = session.query(BitableTable).filter_by(monitor_id=monitor.id).all()
    records = session.query(CurrentRecord).filter_by(monitor_id=monitor.id).all()
    sync_runs = session.query(SyncRun).filter_by(monitor_id=monitor.id).order_by(SyncRun.id).all()

    assert [(table.table_id, table.table_name) for table in tables] == [("tbl_old", "旧表")]
    assert [(record.table_id, record.record_id, record.display_text) for record in records] == [("tbl_old", "rec_old", "旧值")]
    assert monitor.sync_status == "failed"
    assert monitor.last_sync_error == "remote fetch failed"
    assert monitor.last_sync_at is not None
    assert monitor.last_full_sync_at is None
    assert monitor.current_record_count == 0
    assert len(sync_runs) == 1
    assert sync_runs[0].trigger_type == "initial"
    assert sync_runs[0].status == "failed"
    assert sync_runs[0].error_message == "remote fetch failed"
    assert sync_runs[0].stats_json is None


def test_parse_bitable_link_rejects_empty_app_token():
    from app.services.link_parser import parse_bitable_link

    with pytest.raises(ValueError, match="仅支持飞书多维表格链接"):
        parse_bitable_link("https://example.feishu.cn/base/")
