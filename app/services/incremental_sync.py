from __future__ import annotations

from datetime import datetime
import json

from app.clock import system_now
from app.models import CurrentRecord, Monitor, SyncRun
from app.services.field_text import fields_to_display_text


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return int((finished_at - started_at).total_seconds() * 1000)


def run_incremental_sync(session, monitor_id: int, table_id: str, actions: list[dict], client) -> None:
    started_at = system_now()
    monitor = session.get(Monitor, monitor_id)
    if monitor is None:
        raise ValueError(f"Monitor {monitor_id} does not exist")

    updated_count = 0
    deleted_count = 0

    try:
        for action in actions:
            record_id = action["record_id"]
            if action["action"] == "record_deleted":
                deleted_count += session.query(CurrentRecord).filter_by(
                    monitor_id=monitor_id,
                    table_id=table_id,
                    record_id=record_id,
                ).delete()
                continue

            record = client.get_bitable_record(monitor.app_token, table_id, record_id)
            row = session.query(CurrentRecord).filter_by(
                monitor_id=monitor_id,
                table_id=table_id,
                record_id=record_id,
            ).one_or_none()
            if row is None:
                row = CurrentRecord(
                    monitor_id=monitor_id,
                    table_id=table_id,
                    record_id=record_id,
                    sort_order=0,
                    fields_json="{}",
                    display_text="",
                )
                session.add(row)

            row.fields_json = json.dumps(record["fields"], ensure_ascii=False)
            row.display_text = fields_to_display_text(record["fields"])
            row.updated_at = started_at
            updated_count += 1

        finished_at = system_now()
        monitor.current_record_count = session.query(CurrentRecord).filter_by(monitor_id=monitor_id).count()
        monitor.sync_status = "success"
        monitor.last_sync_at = finished_at
        monitor.last_sync_error = None
        session.add(
            SyncRun(
                monitor_id=monitor_id,
                trigger_type="event_incremental",
                status="success",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                stats_json=json.dumps(
                    {
                        "updated_count": updated_count,
                        "deleted_count": deleted_count,
                        "skipped_count": 0,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        session.commit()
    except Exception as error:
        session.rollback()

        monitor = session.get(Monitor, monitor_id)
        if monitor is None:
            raise ValueError(f"Monitor {monitor_id} does not exist")

        finished_at = system_now()
        monitor.sync_status = "failed"
        monitor.last_sync_at = finished_at
        monitor.last_sync_error = str(error)
        session.add(
            SyncRun(
                monitor_id=monitor_id,
                trigger_type="event_incremental",
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                error_message=str(error),
            )
        )
        session.commit()
        raise
