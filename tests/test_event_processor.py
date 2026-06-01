import json
from datetime import datetime
import pytest


def test_process_event_deduplicates_by_event_id(session):
    from app.models import EventLog, Monitor
    from worker.event_processor import record_event

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    payload = {
        "header": {
            "event_id": "evt-1",
            "event_type": "drive.file.bitable_record_changed_v1",
            "create_time": "1779931045198",
        },
        "event": {
            "app_token": "app123",
            "table_id": "tbl1",
            "action_list": [{"record_id": "rec1", "action": "record_edited"}],
        },
    }

    created = record_event(session, payload)
    duplicated = record_event(session, payload)

    assert created is True
    assert duplicated is False
    assert session.query(EventLog).filter_by(event_id="evt-1").count() == 1


def test_record_event_persists_monitor_and_record_ids(session):
    from app.models import EventLog, Monitor
    from worker.event_processor import record_event

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    payload = {
        "header": {
            "event_id": "evt-2",
            "event_type": "drive.file.bitable_record_changed_v1",
            "create_time": "1779931045198",
        },
        "event": {
            "app_token": "app123",
            "table_id": "tbl1",
            "action_list": [
                {"record_id": "rec1", "action": "record_edited"},
                {"record_id": "rec2", "action": "record_deleted"},
            ],
        },
    }

    created = record_event(session, payload)
    row = session.query(EventLog).filter_by(event_id="evt-2").one()

    assert created is True
    assert row.monitor_id == monitor.id
    assert row.event_type == "drive.file.bitable_record_changed_v1"
    assert row.table_id == "tbl1"
    assert json.loads(row.record_ids_json) == ["rec1", "rec2"]
    assert row.process_status == "pending"
    assert row.event_time == datetime(2026, 5, 28, 1, 17, 25, 198000)


def test_handle_event_payload_processes_single_record_and_deduplicates(session):
    from app.models import BitableTable, CurrentRecord, EventLog, Monitor, SyncRun
    from worker.event_listener import handle_event_payload

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

    payload = {
        "header": {
            "event_id": "evt-3",
            "event_type": "drive.file.bitable_record_changed_v1",
            "create_time": "1779931045198",
        },
        "event": {
            "app_token": "app123",
            "table_id": "tbl1",
            "action_list": [{"record_id": "rec1", "action": "record_edited"}],
        },
    }

    class FakeClient:
        def get_bitable_record(self, app_token, table_id, record_id):
            assert app_token == "app123"
            assert table_id == "tbl1"
            assert record_id == "rec1"
            return {"record_id": record_id, "fields": {"姓名": "新值"}}

    handled = handle_event_payload(session, payload, FakeClient())
    duplicated = handle_event_payload(session, payload, FakeClient())

    event_log = session.query(EventLog).filter_by(event_id="evt-3").one()
    record = session.query(CurrentRecord).filter_by(record_id="rec1").one()
    sync_runs = session.query(SyncRun).filter_by(monitor_id=monitor.id).all()
    session.refresh(monitor)

    assert handled is True
    assert duplicated is False
    assert event_log.process_status == "success"
    assert event_log.error_message is None
    assert record.display_text == "新值"
    assert monitor.last_event_type == "drive.file.bitable_record_changed_v1"
    assert monitor.last_event_at == datetime(2026, 5, 28, 1, 17, 25, 198000)
    assert len(sync_runs) == 1
    assert sync_runs[0].trigger_type == "event_incremental"
    assert sync_runs[0].status == "success"


def test_process_event_marks_event_log_failed_when_incremental_sync_raises(session, monkeypatch):
    from app.models import EventLog, Monitor
    from worker.event_processor import process_event, record_event

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    payload = {
        "header": {
            "event_id": "evt-4",
            "event_type": "drive.file.bitable_record_changed_v1",
            "create_time": "1779931045198",
        },
        "event": {
            "app_token": "app123",
            "table_id": "tbl1",
            "action_list": [{"record_id": "rec1", "action": "record_edited"}],
        },
    }

    assert record_event(session, payload) is True
    event_log = session.query(EventLog).filter_by(event_id="evt-4").one()

    def fail_incremental_sync(**_kwargs):
        raise RuntimeError("incremental failed")

    monkeypatch.setattr("worker.event_processor.run_incremental_sync", fail_incremental_sync)

    with pytest.raises(RuntimeError, match="incremental failed"):
        process_event(session, event_log.id, client=object())

    session.refresh(event_log)
    assert event_log.process_status == "failed"
    assert event_log.error_message == "incremental failed"


def test_resubscribe_monitor_marks_subscription_as_subscribed(session):
    from app.models import Monitor
    from app.services.subscription import resubscribe_monitor

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    class FakeClient:
        def refresh_bitable_subscription(self, app_token):
            assert app_token == "app123"
            return {"ok": True}

    result = resubscribe_monitor(session, monitor.id, FakeClient())

    session.refresh(monitor)
    assert result == {"ok": True}
    assert monitor.subscription_status == "subscribed"
    assert monitor.subscription_error is None
