def test_run_full_sync_rebuilds_tables_records_and_sync_run(session, monkeypatch):
    from app.models import Monitor
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

    result = run_full_sync(session, monitor.id, FakeClient(), trigger_type="initial")

    assert result.trigger_type == "initial"
    assert result.record_count == 1
