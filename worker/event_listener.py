from __future__ import annotations

from app.models import EventLog
from worker.event_processor import process_event, record_event


def handle_event_payload(session, payload: dict, client) -> bool:
    created = record_event(session, payload)
    if not created:
        return False

    event_id = payload["header"]["event_id"]
    event_log = session.query(EventLog).filter_by(event_id=event_id).one()
    process_event(session, event_log.id, client)
    return True
