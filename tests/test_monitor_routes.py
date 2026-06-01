def test_create_monitor_enqueues_initial_full_sync_job(client, session):
    from app.models import AppSetting, Monitor, WorkerJob

    session.add(AppSetting(app_id="cli_x", app_secret="secret"))
    session.commit()

    response = client.post(
        "/monitors",
        data={
            "name": "账号管理",
            "source_url": "https://example.feishu.cn/base/app123",
            "fallback_choice": "preset",
            "fallback_interval_minutes": "360",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    monitor = session.query(Monitor).one()
    assert monitor.name == "账号管理"
    assert monitor.app_token == "app123"
    assert monitor.fallback_interval_minutes == 360
    assert monitor.next_fallback_sync_at is not None

    job = session.query(WorkerJob).one()
    assert job.job_type == "initial_full_sync"
    assert job.monitor_id == monitor.id
    assert job.status == "queued"


def test_monitor_detail_shows_interval_and_current_status(client, seeded_monitor):
    response = client.get(f"/monitors/{seeded_monitor.id}")

    assert response.status_code == 200
    assert "低频全量间隔" in response.text
    assert "下一次低频全量时间" in response.text


def test_monitor_detail_renders_table_tabs_and_pagination(client, seeded_bitable_monitor):
    response = client.get(f"/monitors/{seeded_bitable_monitor.id}?tab=tbl1&page=1")

    assert response.status_code == 200
    assert "当前数据" in response.text
    assert "员工表" in response.text
    assert "<table" in response.text
    assert "page=1" in response.text


def test_create_monitor_with_invalid_link_rerenders_form_with_error(client, session):
    from app.models import Monitor, WorkerJob

    response = client.post(
        "/monitors",
        data={
            "name": "账号管理",
            "source_url": "https://example.feishu.cn/wiki/not-a-bitable-link",
            "fallback_choice": "preset",
            "fallback_interval_minutes": "360",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "仅支持飞书多维表格链接" in response.text
    assert session.query(Monitor).count() == 0
    assert session.query(WorkerJob).count() == 0


def test_create_monitor_with_invalid_interval_rerenders_form_with_error(client, session):
    from app.models import Monitor, WorkerJob

    response = client.post(
        "/monitors",
        data={
            "name": "账号管理",
            "source_url": "https://example.feishu.cn/base/app123",
            "fallback_choice": "preset",
            "fallback_interval_minutes": "123",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "请选择允许的低频全量间隔" in response.text
    assert session.query(Monitor).count() == 0
    assert session.query(WorkerJob).count() == 0


def test_create_monitor_rolls_back_when_initial_job_enqueue_fails(client_no_raise, session):
    from sqlalchemy import event

    from app.models import Monitor, WorkerJob

    def fail_worker_job_insert(_mapper, _connection, _target):
        raise RuntimeError("queue unavailable")

    event.listen(WorkerJob, "before_insert", fail_worker_job_insert)
    try:
        response = client_no_raise.post(
            "/monitors",
            data={
                "name": "账号管理",
                "source_url": "https://example.feishu.cn/base/app123",
                "fallback_choice": "preset",
                "fallback_interval_minutes": "360",
            },
            follow_redirects=False,
        )
    finally:
        event.remove(WorkerJob, "before_insert", fail_worker_job_insert)

    assert response.status_code == 500
    assert session.query(Monitor).count() == 0
    assert session.query(WorkerJob).count() == 0


def test_monitor_runs_page_limits_history_to_recent_records(client, session, seeded_monitor):
    from app.models import SyncRun, WorkerJob

    for index in range(1, 56):
        session.add(
            WorkerJob(
                job_type=f"job_{index:03d}",
                monitor_id=seeded_monitor.id,
                status="success",
            )
        )
        session.add(
            SyncRun(
                monitor_id=seeded_monitor.id,
                trigger_type=f"run_{index:03d}",
                status="success",
            )
        )
    session.commit()

    response = client.get(f"/monitors/{seeded_monitor.id}/runs")

    assert response.status_code == 200
    assert "job_055" in response.text
    assert "run_055" in response.text
    assert "job_005" not in response.text
    assert "run_005" not in response.text
