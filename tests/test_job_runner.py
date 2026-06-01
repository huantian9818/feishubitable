import json


def test_try_acquire_table_job_lease_blocks_the_same_subtable(session):
    from app.models import Monitor
    from worker.table_job_leases import try_acquire_table_job_lease

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    assert try_acquire_table_job_lease(session, monitor.id, "tbl_accounts", "worker-a") is True
    assert try_acquire_table_job_lease(session, monitor.id, "tbl_accounts", "worker-b") is False


def test_try_acquire_table_job_lease_allows_a_different_subtable(session):
    from app.models import Monitor
    from worker.table_job_leases import try_acquire_table_job_lease

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    assert try_acquire_table_job_lease(session, monitor.id, "tbl_accounts", "worker-a") is True
    assert try_acquire_table_job_lease(session, monitor.id, "tbl_assets", "worker-b") is True


def test_release_table_job_lease_frees_the_subtable(session):
    from app.models import Monitor
    from worker.table_job_leases import release_table_job_lease, try_acquire_table_job_lease

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    assert try_acquire_table_job_lease(session, monitor.id, "tbl_accounts", "worker-a") is True

    release_table_job_lease(session, monitor.id, "tbl_accounts", "worker-a")

    assert try_acquire_table_job_lease(session, monitor.id, "tbl_accounts", "worker-b") is True


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


def test_job_runner_executes_field_changed_table_resync_job(session, monkeypatch):
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
    session.add(
        WorkerJob(
            job_type="field_changed_table_resync",
            monitor_id=monitor.id,
            payload_json=json.dumps({"table_id": "tbl_accounts", "source_event_id": "evt-1"}, ensure_ascii=False),
            status="queued",
        )
    )
    session.commit()

    called = []
    monkeypatch.setattr(
        "worker.job_runner.run_table_resync",
        lambda session, monitor_id, table_id, client, trigger_type: called.append(
            (monitor_id, table_id, trigger_type)
        ),
        raising=False,
    )

    run_next_job(session, client=object())

    assert called == [(monitor.id, "tbl_accounts", "event_field_table_resync")]


def test_scheduler_enqueues_fallback_job_when_monitor_is_due(session):
    from app.clock import utc_now
    from app.models import Monitor, WorkerJob
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
    jobs = session.query(WorkerJob).all()

    assert count == 1
    assert len(jobs) == 1
    assert jobs[0].job_type == "fallback_full_sync"
    assert jobs[0].monitor_id == monitor.id
    assert jobs[0].status == "queued"
