import json
from datetime import datetime
import pytest


def _field_changed_payload(event_id: str, table_id: str, *, file_token: str = "app123") -> dict:
    return {
        "header": {
            "event_id": event_id,
            "event_type": "drive.file.bitable_field_changed_v1",
            "create_time": "1779931045198",
        },
        "event": {
            "file_token": file_token,
            "table_id": table_id,
        },
    }


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
            "file_token": "app123",
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
            "file_token": "app123",
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
    assert row.event_time == datetime(2026, 5, 28, 9, 17, 25, 198000)


def test_record_event_accepts_legacy_app_token_payload(session):
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
            "event_id": "evt-legacy",
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
    assert session.query(EventLog).filter_by(event_id="evt-legacy").count() == 1


def test_handle_record_changed_event_enqueues_incremental_job_without_running_sync(session):
    from app.models import EventLog, Monitor, SyncRun, WorkerJob
    from worker.event_listener import handle_event_payload

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
            "event_id": "evt-3",
            "event_type": "drive.file.bitable_record_changed_v1",
            "create_time": "1779931045198",
        },
        "event": {
            "file_token": "app123",
            "table_id": "tbl1",
            "action_list": [{"record_id": "rec1", "action": "record_edited"}],
        },
    }

    handled = handle_event_payload(session, payload, client=object())
    duplicated = handle_event_payload(session, payload, client=object())

    event_log = session.query(EventLog).filter_by(event_id="evt-3").one()
    jobs = session.query(WorkerJob).order_by(WorkerJob.id.asc()).all()
    sync_runs = session.query(SyncRun).all()
    session.refresh(monitor)

    assert handled is True
    assert duplicated is False
    assert event_log.process_status == "success"
    assert event_log.error_message is None
    assert monitor.last_event_type == "drive.file.bitable_record_changed_v1"
    assert monitor.last_event_at == datetime(2026, 5, 28, 9, 17, 25, 198000)
    assert len(jobs) == 1
    assert jobs[0].job_type == "record_changed_incremental"
    assert json.loads(jobs[0].payload_json) == {
        "table_id": "tbl1",
        "source_event_id": "evt-3",
        "actions": [{"record_id": "rec1", "action": "record_edited"}],
    }
    assert sync_runs == []


def test_record_changed_event_keeps_every_job_for_the_same_subtable(session):
    from app.models import EventLog, Monitor, WorkerJob
    from worker.event_listener import handle_event_payload

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    first_payload = {
        "header": {
            "event_id": "evt-record-a1",
            "event_type": "drive.file.bitable_record_changed_v1",
            "create_time": "1779931045198",
        },
        "event": {
            "file_token": "app123",
            "table_id": "tbl_a",
            "action_list": [{"record_id": "rec1", "action": "record_edited"}],
        },
    }
    second_payload = {
        "header": {
            "event_id": "evt-record-a2",
            "event_type": "drive.file.bitable_record_changed_v1",
            "create_time": "1779931046200",
        },
        "event": {
            "file_token": "app123",
            "table_id": "tbl_a",
            "action_list": [{"record_id": "rec2", "action": "record_deleted"}],
        },
    }

    assert handle_event_payload(session, first_payload, client=object()) is True
    assert handle_event_payload(session, second_payload, client=object()) is True

    event_logs = session.query(EventLog).order_by(EventLog.id.asc()).all()
    jobs = session.query(WorkerJob).order_by(WorkerJob.id.asc()).all()

    assert [event_log.event_id for event_log in event_logs] == ["evt-record-a1", "evt-record-a2"]
    assert all(event_log.process_status == "success" for event_log in event_logs)
    assert [job.job_type for job in jobs] == ["record_changed_incremental", "record_changed_incremental"]
    assert [json.loads(job.payload_json)["source_event_id"] for job in jobs] == [
        "evt-record-a1",
        "evt-record-a2",
    ]
    assert [json.loads(job.payload_json)["table_id"] for job in jobs] == ["tbl_a", "tbl_a"]


def test_handle_field_changed_event_replaces_queued_job_and_keeps_table_order(session):
    from app.models import EventLog, Monitor, WorkerJob
    from worker.event_listener import handle_event_payload

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    assert handle_event_payload(session, _field_changed_payload("evt-a1", "tbl_a"), client=object()) is True
    assert handle_event_payload(session, _field_changed_payload("evt-b1", "tbl_b"), client=object()) is True
    assert handle_event_payload(session, _field_changed_payload("evt-a2", "tbl_a"), client=object()) is True

    event_logs = session.query(EventLog).order_by(EventLog.id.asc()).all()
    jobs = session.query(WorkerJob).order_by(WorkerJob.id.asc()).all()

    assert [event_log.event_id for event_log in event_logs] == ["evt-a1", "evt-b1", "evt-a2"]
    assert all(event_log.process_status == "success" for event_log in event_logs)
    assert [job.job_type for job in jobs] == ["field_changed_table_resync", "field_changed_table_resync"]
    assert [job.status for job in jobs] == ["queued", "queued"]
    assert [json.loads(job.payload_json)["table_id"] for job in jobs] == ["tbl_b", "tbl_a"]
    assert [json.loads(job.payload_json)["source_event_id"] for job in jobs] == ["evt-b1", "evt-a2"]


def test_handle_field_changed_event_keeps_one_followup_job_when_same_table_is_running(session):
    from app.models import Monitor, WorkerJob
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
        WorkerJob(
            job_type="field_changed_table_resync",
            monitor_id=monitor.id,
            payload_json=json.dumps({"table_id": "tbl_a", "source_event_id": "evt-running"}, ensure_ascii=False),
            status="running",
        )
    )
    session.commit()

    assert handle_event_payload(session, _field_changed_payload("evt-next", "tbl_a"), client=object()) is True
    assert handle_event_payload(session, _field_changed_payload("evt-latest", "tbl_a"), client=object()) is True

    jobs = session.query(WorkerJob).order_by(WorkerJob.id.asc()).all()

    assert len(jobs) == 2
    assert jobs[0].status == "running"
    assert json.loads(jobs[0].payload_json)["source_event_id"] == "evt-running"
    assert jobs[1].status == "queued"
    assert json.loads(jobs[1].payload_json) == {"table_id": "tbl_a", "source_event_id": "evt-latest"}


def test_handle_field_changed_event_with_non_record_action_items(session):
    from app.models import EventLog, Monitor, WorkerJob
    from worker.event_listener import handle_event_payload

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    payload = _field_changed_payload("evt-field-action", "tbl_a")
    payload["event"]["action_list"] = [
        {"field_id": "fld_1", "action": "field_created"},
        {"field_id": "fld_2", "action": "field_updated"},
    ]

    assert handle_event_payload(session, payload, client=object()) is True

    event_log = session.query(EventLog).filter_by(event_id="evt-field-action").one()
    job = session.query(WorkerJob).one()

    assert event_log.process_status == "success"
    assert json.loads(event_log.record_ids_json) == []
    assert json.loads(job.payload_json) == {"table_id": "tbl_a", "source_event_id": "evt-field-action"}


def test_process_event_marks_event_log_failed_when_record_changed_enqueue_raises(session, monkeypatch):
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
            "file_token": "app123",
            "table_id": "tbl1",
            "action_list": [{"record_id": "rec1", "action": "record_edited"}],
        },
    }

    assert record_event(session, payload) is True
    event_log = session.query(EventLog).filter_by(event_id="evt-4").one()

    def fail_enqueue(*_args, **_kwargs):
        raise RuntimeError("enqueue failed")

    monkeypatch.setattr("worker.event_processor._enqueue_record_changed_incremental", fail_enqueue)

    with pytest.raises(RuntimeError, match="enqueue failed"):
        process_event(session, event_log.id, client=object())

    session.refresh(event_log)
    assert event_log.process_status == "failed"
    assert event_log.error_message == "enqueue failed"


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
