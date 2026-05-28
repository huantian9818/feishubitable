from __future__ import annotations

from app.clients.feishu import FeishuBitableClient
from app.db import SessionLocal
from worker.job_runner import run_next_job
from worker.scheduler import enqueue_due_fallback_jobs


def run_worker_cycle(client=None) -> bool:
    resolved_client = client or FeishuBitableClient()

    with SessionLocal() as session:
        enqueue_due_fallback_jobs(session)
        return run_next_job(session, resolved_client)


def main() -> int:
    run_worker_cycle()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
