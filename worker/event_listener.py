from __future__ import annotations

import logging
from threading import Thread

from app.db import SessionLocal
from app.models import EventLog
from worker.event_processor import process_event, record_event

LOGGER = logging.getLogger(__name__)


def handle_event_payload(session, payload: dict, client) -> bool:
    created = record_event(session, payload)
    if not created:
        return False

    event_id = payload["header"]["event_id"]
    event_log = session.query(EventLog).filter_by(event_id=event_id).one()
    process_event(session, event_log.id, client)
    return True


def _handle_payload(payload: dict, client) -> None:
    event_id = payload.get("header", {}).get("event_id")
    try:
        with SessionLocal() as session:
            handle_event_payload(session, payload, client)
    except Exception:
        LOGGER.exception("event listener callback failed for event_id=%s", event_id)


def start_event_listener(client=None):
    listen = getattr(client, "listen_bitable_record_events", None)
    if listen is None:
        LOGGER.info("event listener not started; client has no long-connection listener")
        return None

    def _run_listener() -> None:
        try:
            listen(lambda payload: _handle_payload(payload, client))
        except Exception:
            LOGGER.exception("event listener thread exited unexpectedly")

    thread = Thread(target=_run_listener, daemon=True)
    thread.start()
    LOGGER.info("event listener thread started")
    return thread
