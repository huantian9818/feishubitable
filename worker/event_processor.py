from __future__ import annotations

from datetime import UTC, datetime
import json

from app.models import EventLog, Monitor, WorkerJob
from app.services.incremental_sync import run_incremental_sync

BITABLE_RECORD_CHANGED = "drive.file.bitable_record_changed_v1"
BITABLE_FIELD_CHANGED = "drive.file.bitable_field_changed_v1"
FIELD_CHANGED_TABLE_RESYNC_JOB = "field_changed_table_resync"


def _event_time_from_header(header: dict) -> datetime:
    return datetime.fromtimestamp(int(header["create_time"]) / 1000, tz=UTC).replace(tzinfo=None)


def _event_monitor_token(event: dict) -> str:
    token = event.get("file_token") or event.get("app_token")
    if not token:
        raise ValueError("Bitable event missing file_token")
    return str(token)


def _field_changed_payload(table_id: str, source_event_id: str) -> str:
    return json.dumps(
        {"table_id": table_id, "source_event_id": source_event_id},
        ensure_ascii=False,
    )


def _record_ids_from_actions(event: dict) -> list[str]:
    record_ids = []
    for item in event.get("action_list", []):
        record_id = item.get("record_id") if isinstance(item, dict) else None
        if record_id:
            record_ids.append(str(record_id))
    return record_ids


def _queued_table_resync_jobs(session, monitor_id: int, table_id: str) -> list[WorkerJob]:
    jobs = (
        session.query(WorkerJob)
        .filter_by(
            job_type=FIELD_CHANGED_TABLE_RESYNC_JOB,
            monitor_id=monitor_id,
            status="queued",
        )
        .order_by(WorkerJob.id.asc())
        .all()
    )
    matched = []
    for job in jobs:
        payload = json.loads(job.payload_json or "{}")
        if payload.get("table_id") == table_id:
            matched.append(job)
    return matched


def _enqueue_field_changed_table_resync(session, monitor_id: int, table_id: str, source_event_id: str) -> None:
    if not table_id:
        raise ValueError("Field change event missing table_id")

    for job in _queued_table_resync_jobs(session, monitor_id, table_id):
        session.delete(job)

    session.add(
        WorkerJob(
            job_type=FIELD_CHANGED_TABLE_RESYNC_JOB,
            monitor_id=monitor_id,
            payload_json=_field_changed_payload(table_id, source_event_id),
            status="queued",
        )
    )


def record_event(session, payload: dict) -> bool:
    header = payload["header"]
    if session.query(EventLog).filter_by(event_id=header["event_id"]).one_or_none() is not None:
        return False

    event = payload["event"]
    monitor = session.query(Monitor).filter_by(app_token=_event_monitor_token(event)).one()
    session.add(
        EventLog(
            event_id=header["event_id"],
            monitor_id=monitor.id,
            event_type=header["event_type"],
            table_id=event.get("table_id"),
            record_ids_json=json.dumps(_record_ids_from_actions(event), ensure_ascii=False),
            event_time=_event_time_from_header(header),
            process_status="pending",
            raw_json=json.dumps(payload, ensure_ascii=False),
        )
    )
    session.commit()
    return True


def process_event(session, event_log_id: int, client) -> EventLog:
    event_log = session.get(EventLog, event_log_id)
    if event_log is None:
        raise ValueError(f"EventLog {event_log_id} does not exist")

    payload = json.loads(event_log.raw_json)
    header = payload["header"]
    event = payload["event"]

    event_log.process_status = "processing"
    event_log.error_message = None
    session.commit()

    try:
        if header["event_type"] == BITABLE_RECORD_CHANGED:
            run_incremental_sync(
                session=session,
                monitor_id=event_log.monitor_id,
                table_id=event["table_id"],
                actions=event.get("action_list", []),
                client=client,
            )
        elif header["event_type"] == BITABLE_FIELD_CHANGED:
            _enqueue_field_changed_table_resync(
                session,
                event_log.monitor_id,
                str(event.get("table_id") or ""),
                header["event_id"],
            )
        else:
            raise ValueError(f"Unsupported event type: {header['event_type']}")
    except Exception as error:
        session.rollback()

        event_log = session.get(EventLog, event_log_id)
        if event_log is None:
            raise ValueError(f"EventLog {event_log_id} does not exist")

        event_log.process_status = "failed"
        event_log.error_message = str(error)
        session.commit()
        raise

    event_log = session.get(EventLog, event_log_id)
    monitor = session.get(Monitor, event_log.monitor_id) if event_log is not None else None
    if event_log is None or monitor is None:
        raise ValueError(f"EventLog {event_log_id} does not exist")

    event_log.process_status = "success"
    event_log.error_message = None
    monitor.last_event_at = _event_time_from_header(header)
    monitor.last_event_type = header["event_type"]
    session.commit()
    return event_log
