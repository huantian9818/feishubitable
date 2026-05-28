from datetime import datetime


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
