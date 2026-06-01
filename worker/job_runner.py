from __future__ import annotations

import json

from sqlalchemy import select

from app.clock import utc_now
from app.models import WorkerJob
from app.services.full_sync import run_full_sync, run_table_resync

try:
    from app.services.subscription import resubscribe_monitor
except ImportError:
    def resubscribe_monitor(session, monitor_id, client):
        return None


def _table_resync_table_id(job: WorkerJob) -> str:
    payload = json.loads(job.payload_json or "{}")
    table_id = payload.get("table_id")
    if not table_id:
        raise ValueError("field_changed_table_resync job missing table_id")
    return str(table_id)


def run_next_job(session, client):
    job = session.scalars(
        select(WorkerJob).where(WorkerJob.status == "queued").order_by(WorkerJob.id)
    ).first()
    if job is None:
        return False

    job.status = "running"
    job.started_at = utc_now()
    session.commit()

    try:
        if job.job_type == "initial_full_sync":
            run_full_sync(session, job.monitor_id, client, trigger_type="initial")
        elif job.job_type == "manual_full_sync":
            run_full_sync(session, job.monitor_id, client, trigger_type="manual_full")
        elif job.job_type == "fallback_full_sync":
            run_full_sync(session, job.monitor_id, client, trigger_type="fallback_full")
        elif job.job_type == "field_changed_table_resync":
            run_table_resync(
                session,
                job.monitor_id,
                _table_resync_table_id(job),
                client,
                trigger_type="event_field_table_resync",
            )
        elif job.job_type == "resubscribe":
            resubscribe_monitor(session, job.monitor_id, client)

        job.status = "success"
        job.error_message = None
        job.finished_at = utc_now()
        session.commit()
        return True
    except Exception as error:
        session.rollback()
        failed_job = session.get(WorkerJob, job.id)
        if failed_job is None:
            raise

        failed_job.status = "failed"
        failed_job.error_message = str(error)
        failed_job.finished_at = utc_now()
        session.commit()
        raise
