from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import logging

from app.clock import system_now
from app.models import BitableTable, CurrentRecord, Monitor, SyncRun
from app.services.fallback_schedule import compute_next_fallback_at
from app.services.field_text import fields_to_display_text
from app.services.subscription import resubscribe_monitor

LOGGER = logging.getLogger(__name__)


@dataclass
class FullSyncResult:
    trigger_type: str
    record_count: int


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return int((finished_at - started_at).total_seconds() * 1000)


def _table_fields_snapshot(client, app_token: str, table: dict) -> list[dict]:
    list_fields = getattr(client, "list_bitable_fields", None)
    if callable(list_fields):
        return list_fields(app_token, table["table_id"])
    return list(table.get("fields", []))


def _collect_remote_snapshot(client, app_token: str) -> tuple[list[dict], int]:
    client.get_bitable_meta(app_token)
    tables = client.get_bitable_tables(app_token)

    snapshot = []
    record_count = 0
    for table in tables:
        fields = _table_fields_snapshot(client, app_token, table)
        records = client.list_bitable_records(app_token, table["table_id"])
        snapshot.append(
            {
                "table_id": table["table_id"],
                "name": table["name"],
                "fields": fields,
                "records": records,
            }
        )
        record_count += len(records)
    return snapshot, record_count


def _table_snapshot(client, app_token: str, table_id: str) -> tuple[dict, list[dict]]:
    tables = client.get_bitable_tables(app_token)
    table = next((item for item in tables if item["table_id"] == table_id), None)
    if table is None:
        raise ValueError(f"Table {table_id} does not exist in remote bitable")
    table = {**table, "fields": _table_fields_snapshot(client, app_token, table)}
    records = client.list_bitable_records(app_token, table_id)
    return table, records


def _record_failed_sync(session, monitor_id: int, trigger_type: str, started_at: datetime, error: Exception) -> None:
    session.rollback()

    monitor = session.get(Monitor, monitor_id)
    if monitor is None:
        raise ValueError(f"Monitor {monitor_id} does not exist")

    finished_at = system_now()
    message = str(error)

    monitor.sync_status = "failed"
    monitor.last_sync_at = finished_at
    monitor.last_sync_error = message
    session.add(
        SyncRun(
            monitor_id=monitor_id,
            trigger_type=trigger_type,
            status="failed",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
            error_message=message,
        )
    )
    session.commit()


def _refresh_subscription_after_initial_sync(session, monitor_id: int, client, trigger_type: str) -> None:
    if trigger_type != "initial":
        return

    try:
        resubscribe_monitor(session, monitor_id, client)
    except Exception as error:
        LOGGER.warning(
            "initial sync completed but subscription refresh failed for monitor_id=%s: %s",
            monitor_id,
            error,
        )


def _replace_table_snapshot(session, monitor_id: int, table: dict, records: list[dict]) -> None:
    row = session.query(BitableTable).filter_by(monitor_id=monitor_id, table_id=table["table_id"]).one_or_none()
    if row is None:
        row = BitableTable(
            monitor_id=monitor_id,
            table_id=table["table_id"],
            table_name=table["name"],
        )
        session.add(row)

    row.table_name = table["name"]
    row.field_schema_json = json.dumps(table.get("fields", []), ensure_ascii=False)

    session.query(CurrentRecord).filter_by(monitor_id=monitor_id, table_id=table["table_id"]).delete()
    for row_index, record in enumerate(records, start=1):
        session.add(
            CurrentRecord(
                monitor_id=monitor_id,
                table_id=table["table_id"],
                record_id=record["record_id"],
                sort_order=row_index,
                fields_json=json.dumps(record["fields"], ensure_ascii=False),
                display_text=fields_to_display_text(record["fields"]),
            )
        )


def run_full_sync(session, monitor_id: int, client, trigger_type: str) -> FullSyncResult:
    started_at = system_now()
    monitor = session.get(Monitor, monitor_id)
    if monitor is None:
        raise ValueError(f"Monitor {monitor_id} does not exist")

    try:
        snapshot, count = _collect_remote_snapshot(client, monitor.app_token)
    except Exception as error:
        _record_failed_sync(session, monitor_id, trigger_type, started_at, error)
        raise

    try:
        session.query(CurrentRecord).filter_by(monitor_id=monitor_id).delete()
        session.query(BitableTable).filter_by(monitor_id=monitor_id).delete()

        for table in snapshot:
            session.add(
                BitableTable(
                    monitor_id=monitor_id,
                    table_id=table["table_id"],
                    table_name=table["name"],
                    field_schema_json=json.dumps(table["fields"], ensure_ascii=False),
                )
            )
            for row_index, record in enumerate(table["records"], start=1):
                session.add(
                    CurrentRecord(
                        monitor_id=monitor_id,
                        table_id=table["table_id"],
                        record_id=record["record_id"],
                        sort_order=row_index,
                        fields_json=json.dumps(record["fields"], ensure_ascii=False),
                        display_text=fields_to_display_text(record["fields"]),
                    )
                )

        finished_at = system_now()
        monitor.current_record_count = count
        monitor.sync_status = "success"
        monitor.last_full_sync_at = finished_at
        monitor.last_sync_at = finished_at
        monitor.last_sync_error = None
        monitor.next_fallback_sync_at = compute_next_fallback_at(
            finished_at, monitor.fallback_interval_minutes
        )
        session.add(
            SyncRun(
                monitor_id=monitor_id,
                trigger_type=trigger_type,
                status="success",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                stats_json=json.dumps({"record_count": count}, ensure_ascii=False),
            )
        )
        session.commit()
        _refresh_subscription_after_initial_sync(session, monitor_id, client, trigger_type)
        return FullSyncResult(trigger_type=trigger_type, record_count=count)
    except Exception as error:
        _record_failed_sync(session, monitor_id, trigger_type, started_at, error)
        raise


def run_table_resync(session, monitor_id: int, table_id: str, client, trigger_type: str) -> FullSyncResult:
    started_at = system_now()
    monitor = session.get(Monitor, monitor_id)
    if monitor is None:
        raise ValueError(f"Monitor {monitor_id} does not exist")

    try:
        table, records = _table_snapshot(client, monitor.app_token, table_id)
    except Exception as error:
        _record_failed_sync(session, monitor_id, trigger_type, started_at, error)
        raise

    try:
        _replace_table_snapshot(session, monitor_id, table, records)

        finished_at = system_now()
        monitor.current_record_count = session.query(CurrentRecord).filter_by(monitor_id=monitor_id).count()
        monitor.sync_status = "success"
        monitor.last_sync_at = finished_at
        monitor.last_sync_error = None
        session.add(
            SyncRun(
                monitor_id=monitor_id,
                trigger_type=trigger_type,
                status="success",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                stats_json=json.dumps(
                    {"table_id": table_id, "record_count": len(records)},
                    ensure_ascii=False,
                ),
            )
        )
        session.commit()
        return FullSyncResult(trigger_type=trigger_type, record_count=len(records))
    except Exception as error:
        _record_failed_sync(session, monitor_id, trigger_type, started_at, error)
        raise
