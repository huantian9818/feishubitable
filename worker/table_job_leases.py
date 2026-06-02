from __future__ import annotations

from datetime import timedelta

from app.clock import system_now
from app.models import TableJobLease


DEFAULT_TABLE_JOB_LEASE_SECONDS = 30


def try_acquire_table_job_lease(session, monitor_id: int, table_id: str, worker_id: str) -> bool:
    now = system_now()
    lease = session.query(TableJobLease).filter_by(monitor_id=monitor_id, table_id=table_id).one_or_none()
    if lease is None:
        session.add(
            TableJobLease(
                monitor_id=monitor_id,
                table_id=table_id,
                worker_id=worker_id,
                lease_expires_at=now + timedelta(seconds=DEFAULT_TABLE_JOB_LEASE_SECONDS),
            )
        )
        session.commit()
        return True

    if lease.lease_expires_at <= now or lease.worker_id == worker_id:
        lease.worker_id = worker_id
        lease.lease_expires_at = now + timedelta(seconds=DEFAULT_TABLE_JOB_LEASE_SECONDS)
        lease.updated_at = now
        session.commit()
        return True

    return False


def release_table_job_lease(session, monitor_id: int, table_id: str, worker_id: str) -> None:
    lease = session.query(TableJobLease).filter_by(
        monitor_id=monitor_id,
        table_id=table_id,
        worker_id=worker_id,
    ).one_or_none()
    if lease is None:
        return

    session.delete(lease)
    session.commit()
