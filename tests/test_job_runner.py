def test_job_runner_executes_manual_full_sync_job(session, monkeypatch):
    from app.models import Monitor, WorkerJob
    from worker.job_runner import run_next_job

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()
    session.add(WorkerJob(job_type="manual_full_sync", monitor_id=monitor.id, status="queued"))
    session.commit()

    called = []
    monkeypatch.setattr(
        "worker.job_runner.run_full_sync",
        lambda session, monitor_id, client, trigger_type: called.append((monitor_id, trigger_type)),
    )

    run_next_job(session, client=object())

    assert called == [(monitor.id, "manual_full")]


def test_scheduler_enqueues_fallback_job_when_monitor_is_due(session):
    from app.clock import utc_now
    from app.models import Monitor
    from worker.scheduler import enqueue_due_fallback_jobs

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
        next_fallback_sync_at=utc_now(),
    )
    session.add(monitor)
    session.commit()

    count = enqueue_due_fallback_jobs(session)

    assert count == 1
