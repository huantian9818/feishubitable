from __future__ import annotations

from sqlalchemy import and_, select

from app.clock import system_now
from app.models import Monitor, WorkerJob


def enqueue_due_fallback_jobs(session) -> int:
    due_monitors = session.scalars(
        select(Monitor).where(
            and_(
                Monitor.is_enabled.is_(True),
                Monitor.next_fallback_sync_at.is_not(None),
                Monitor.next_fallback_sync_at <= system_now(),
            )
        )
    ).all()

    for monitor in due_monitors:
        session.add(
            WorkerJob(
                job_type="fallback_full_sync",
                monitor_id=monitor.id,
                status="queued",
            )
        )

    session.commit()
    return len(due_monitors)
