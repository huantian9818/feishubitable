from __future__ import annotations

import argparse
import logging
import time
import uuid

from app.clients.feishu import FeishuBitableClient
from app.db import init_db
from app.db import SessionLocal
from worker.event_listener import start_event_listener
from worker.job_runner import run_next_job
from worker.scheduler import enqueue_due_fallback_jobs

LOGGER = logging.getLogger(__name__)


def run_worker_cycle(client=None, worker_id: str = "worker-single") -> bool:
    resolved_client = client or FeishuBitableClient()

    with SessionLocal() as session:
        enqueue_due_fallback_jobs(session)
        return run_next_job(session, resolved_client, worker_id)


def run_once(client=None, worker_id: str = "worker-single") -> bool:
    processed = run_worker_cycle(client=client, worker_id=worker_id)
    LOGGER.info("worker cycle finished; processed_job=%s", processed)
    return processed


def run_forever(interval_seconds: float = 5.0, client=None, worker_id: str = "worker-single") -> int:
    LOGGER.info("worker loop started; worker_id=%s interval_seconds=%s", worker_id, interval_seconds)
    try:
        while True:
            should_sleep = True
            try:
                processed = run_once(client=client, worker_id=worker_id)
                should_sleep = not processed
                if should_sleep:
                    LOGGER.info("no queued job found; sleeping for %ss", interval_seconds)
            except Exception:
                LOGGER.exception("worker cycle failed; continuing after %ss", interval_seconds)
            if should_sleep:
                time.sleep(interval_seconds)
    except KeyboardInterrupt:
        LOGGER.info("worker loop stopped by keyboard interrupt")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Feishu Bitable worker loop.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scheduling + job-consume cycle and exit.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Sleep interval in seconds between worker cycles in loop mode.",
    )
    parser.add_argument(
        "--no-listener",
        action="store_true",
        help="Consume queued jobs without starting the Feishu event listener thread.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    args = build_parser().parse_args(argv)

    if args.interval <= 0:
        raise SystemExit("--interval must be greater than 0")

    init_db()
    resolved_client = FeishuBitableClient()
    resolved_worker_id = uuid.uuid4().hex

    if args.once:
        run_once(client=resolved_client, worker_id=resolved_worker_id)
        return 0

    if not args.no_listener:
        start_event_listener(client=resolved_client)
    return run_forever(
        interval_seconds=args.interval,
        client=resolved_client,
        worker_id=resolved_worker_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
