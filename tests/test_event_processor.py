import json
from datetime import datetime


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
