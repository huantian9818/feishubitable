from __future__ import annotations

import json

from sqlalchemy import select

from app.clock import system_now
from app.models import WorkerJob
from app.services.full_sync import run_full_sync, run_table_resync
from app.services.incremental_sync import run_incremental_sync
from worker.table_job_leases import release_table_job_lease, try_acquire_table_job_lease


RECORD_CHANGED_INCREMENTAL_JOB = "record_changed_incremental"
FIELD_CHANGED_TABLE_RESYNC_JOB = "field_changed_table_resync"


def _job_payload(job: WorkerJob) -> dict:
    return json.loads(job.payload_json or "{}")


def _record_changed_args(job: WorkerJob) -> tuple[str, list[dict]]:
    payload = _job_payload(job)
    table_id = payload.get("table_id")
    if not table_id:
        raise ValueError("record_changed_incremental job missing table_id")
    return str(table_id), list(payload.get("actions", []))


def _table_resync_table_id(job: WorkerJob) -> str:
    payload = _job_payload(job)
    table_id = payload.get("table_id")
    if not table_id:
        raise ValueError("field_changed_table_resync job missing table_id")
    return str(table_id)


def _job_table_key(job: WorkerJob) -> tuple[int, str] | None:
    if job.monitor_id is None:
        return None

    if job.job_type == RECORD_CHANGED_INCREMENTAL_JOB:
        table_id, _actions = _record_changed_args(job)
        return job.monitor_id, table_id

    if job.job_type == FIELD_CHANGED_TABLE_RESYNC_JOB:
        return job.monitor_id, _table_resync_table_id(job)

    return None


def _run_claimed_job(session, job: WorkerJob, client) -> None:
    if job.job_type == "initial_full_sync":
        run_full_sync(session, job.monitor_id, client, trigger_type="initial")
    elif job.job_type == "fallback_full_sync":
        run_full_sync(session, job.monitor_id, client, trigger_type="fallback_full")
    elif job.job_type == RECORD_CHANGED_INCREMENTAL_JOB:
        table_id, actions = _record_changed_args(job)
        run_incremental_sync(
            session,
            job.monitor_id,
            table_id,
            actions,
            client,
        )
    elif job.job_type == FIELD_CHANGED_TABLE_RESYNC_JOB:
        run_table_resync(
            session,
            job.monitor_id,
            _table_resync_table_id(job),
            client,
            trigger_type="event_field_table_resync",
        )


def run_next_job(session, client, worker_id: str):
    jobs = session.scalars(
        select(WorkerJob).where(WorkerJob.status == "queued").order_by(WorkerJob.id)
    ).all()
    if not jobs:
        return False

    selected_job = None
    lease_key = None
    for job in jobs:
        current_lease_key = _job_table_key(job)
        if current_lease_key is not None:
            monitor_id, table_id = current_lease_key
            if not try_acquire_table_job_lease(session, monitor_id, table_id, worker_id):
                continue
        selected_job = job
        lease_key = current_lease_key
        break

    if selected_job is None:
        return False

    selected_job.status = "running"
    selected_job.started_at = system_now()
    session.commit()

    try:
        _run_claimed_job(session, selected_job, client)

        selected_job.status = "success"
        selected_job.error_message = None
        selected_job.finished_at = system_now()
        session.commit()
        return True
    except Exception as error:
        session.rollback()
        failed_job = session.get(WorkerJob, selected_job.id)
        if failed_job is None:
            raise

        failed_job.status = "failed"
        failed_job.error_message = str(error)
        failed_job.finished_at = system_now()
        session.commit()
        raise
    finally:
        if lease_key is not None:
            release_table_job_lease(session, lease_key[0], lease_key[1], worker_id)
