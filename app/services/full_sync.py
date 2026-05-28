from __future__ import annotations

from dataclasses import dataclass
import json

from app.clock import utc_now
from app.models import BitableTable, CurrentRecord, Monitor, SyncRun
from app.services.fallback_schedule import compute_next_fallback_at


@dataclass
class FullSyncResult:
    trigger_type: str
    record_count: int


def run_full_sync(session, monitor_id: int, client, trigger_type: str) -> FullSyncResult:
    monitor = session.get(Monitor, monitor_id)
    if monitor is None:
        raise ValueError(f"Monitor {monitor_id} does not exist")

    client.get_bitable_meta(monitor.app_token)
    tables = client.get_bitable_tables(monitor.app_token)

    session.query(CurrentRecord).filter_by(monitor_id=monitor_id).delete()
    session.query(BitableTable).filter_by(monitor_id=monitor_id).delete()

    count = 0
    for table in tables:
        session.add(
            BitableTable(
                monitor_id=monitor_id,
                table_id=table["table_id"],
                table_name=table["name"],
                field_schema_json=json.dumps(table.get("fields", []), ensure_ascii=False),
            )
        )
        records = client.list_bitable_records(monitor.app_token, table["table_id"])
        for row_index, record in enumerate(records, start=1):
            count += 1
            session.add(
                CurrentRecord(
                    monitor_id=monitor_id,
                    table_id=table["table_id"],
                    record_id=record["record_id"],
                    sort_order=row_index,
                    fields_json=json.dumps(record["fields"], ensure_ascii=False),
                    display_text=" | ".join(str(value) for value in record["fields"].values()),
                )
            )

    now = utc_now()
    monitor.current_record_count = count
    monitor.sync_status = "success"
    monitor.last_full_sync_at = now
    monitor.last_sync_at = now
    monitor.next_fallback_sync_at = compute_next_fallback_at(now, monitor.fallback_interval_minutes)
    session.add(
        SyncRun(
            monitor_id=monitor_id,
            trigger_type=trigger_type,
            status="success",
            started_at=now,
            finished_at=now,
            duration_ms=0,
            stats_json=json.dumps({"record_count": count}, ensure_ascii=False),
        )
    )
    session.commit()
    return FullSyncResult(trigger_type=trigger_type, record_count=count)
