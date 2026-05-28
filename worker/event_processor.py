from __future__ import annotations

from datetime import UTC, datetime
import json

from app.models import EventLog, Monitor
from app.services.incremental_sync import run_incremental_sync


def _event_time_from_header(header: dict) -> datetime:
    return datetime.fromtimestamp(int(header["create_time"]) / 1000, tz=UTC).replace(tzinfo=None)


def record_event(session, payload: dict) -> bool:
    header = payload["header"]
    if session.query(EventLog).filter_by(event_id=header["event_id"]).one_or_none() is not None:
        return False

    event = payload["event"]
    monitor = session.query(Monitor).filter_by(app_token=event["app_token"]).one()
    session.add(
        EventLog(
            event_id=header["event_id"],
            monitor_id=monitor.id,
            event_type=header["event_type"],
            table_id=event.get("table_id"),
            record_ids_json=json.dumps(
                [item["record_id"] for item in event.get("action_list", [])],
                ensure_ascii=False,
            ),
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
        run_incremental_sync(
            session=session,
            monitor_id=event_log.monitor_id,
            table_id=event["table_id"],
            actions=event.get("action_list", []),
            client=client,
        )
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
