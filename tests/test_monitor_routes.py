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


def test_create_monitor_resolves_wiki_bitable_link(client, session, monkeypatch):
    from app.models import Monitor, WorkerJob

    monkeypatch.setattr(
        "app.web.routes.monitors.FeishuBitableClient.resolve_wiki_node",
        lambda self, wiki_token: {
            "obj_type": "bitable",
            "obj_token": f"app_from_{wiki_token}",
        },
    )

    response = client.post(
        "/monitors",
        data={
            "name": "知识库账号管理",
            "source_url": "https://example.feishu.cn/wiki/SioWwTP5Uiryn8kIez6cjjDMnNM",
            "fallback_choice": "preset",
            "fallback_interval_minutes": "360",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    monitor = session.query(Monitor).one()
    assert monitor.source_url.endswith("/wiki/SioWwTP5Uiryn8kIez6cjjDMnNM")
    assert monitor.app_token == "app_from_SioWwTP5Uiryn8kIez6cjjDMnNM"

    job = session.query(WorkerJob).one()
    assert job.job_type == "initial_full_sync"
    assert job.monitor_id == monitor.id


def test_monitor_detail_shows_interval_and_current_status(client, seeded_monitor):
    response = client.get(f"/monitors/{seeded_monitor.id}")

    assert response.status_code == 200
    assert "低频全量间隔" in response.text
    assert "下一次低频全量时间" in response.text
    assert "2026-05-28 15:00:00" in response.text


def test_monitor_detail_renders_table_tabs_and_pagination(client, seeded_bitable_monitor):
    response = client.get(f"/monitors/{seeded_bitable_monitor.id}?tab=tbl1&page=1")

    assert response.status_code == 200
    assert "当前数据" in response.text
    assert "员工表" in response.text
    assert "<table" in response.text
    assert "page=1" in response.text
    assert "删除监控源" in response.text


def test_list_monitors_shows_view_and_delete_actions(client, seeded_monitor):
    response = client.get("/monitors")

    assert response.status_code == 200
    assert "查看详情" in response.text
    assert "删除监控源" in response.text


def test_create_monitor_with_invalid_link_rerenders_form_with_error(client, session):
    from app.models import Monitor, WorkerJob

    response = client.post(
        "/monitors",
        data={
            "name": "账号管理",
            "source_url": "https://example.feishu.cn/docx/not-a-bitable-link",
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


def test_monitor_runs_page_uses_clearer_titles(client, seeded_monitor):
    response = client.get(f"/monitors/{seeded_monitor.id}/runs")

    assert response.status_code == 200
    assert "待处理/已处理任务" in response.text
    assert "实际同步结果" in response.text
    assert "异步任务" not in response.text
    assert "同步运行" not in response.text


def test_monitor_runs_page_formats_times_in_beijing_time(client, session, seeded_monitor):
    from datetime import datetime

    from app.models import SyncRun, WorkerJob

    session.add(
        WorkerJob(
            job_type="record_changed_incremental",
            monitor_id=seeded_monitor.id,
            status="success",
            created_at=datetime(2026, 5, 28, 1, 2, 3),
            started_at=datetime(2026, 5, 28, 1, 3, 4),
            finished_at=datetime(2026, 5, 28, 1, 4, 5),
        )
    )
    session.add(
        SyncRun(
            monitor_id=seeded_monitor.id,
            trigger_type="event_incremental",
            status="success",
            started_at=datetime(2026, 5, 28, 2, 3, 4),
            finished_at=datetime(2026, 5, 28, 2, 4, 5),
        )
    )
    session.commit()

    response = client.get(f"/monitors/{seeded_monitor.id}/runs")

    assert response.status_code == 200
    assert "2026-05-28 01:02:03" in response.text
    assert "2026-05-28 01:03:04" in response.text
    assert "2026-05-28 01:04:05" in response.text
    assert "2026-05-28 02:03:04" in response.text
    assert "2026-05-28 02:04:05" in response.text


def test_monitor_runs_page_shows_event_delivery_delay(client, session, seeded_monitor):
    from datetime import datetime
    import json

    from app.models import EventLog, WorkerJob

    session.add(
        EventLog(
            event_id="evt-delay",
            monitor_id=seeded_monitor.id,
            event_type="drive.file.bitable_record_changed_v1",
            table_id="tbl1",
            event_time=datetime(2026, 5, 28, 11, 29, 54),
            created_at=datetime(2026, 5, 28, 11, 38, 11),
            process_status="success",
            raw_json="{}",
        )
    )
    session.add(
        WorkerJob(
            job_type="record_changed_incremental",
            monitor_id=seeded_monitor.id,
            status="success",
            created_at=datetime(2026, 5, 28, 11, 38, 11),
            payload_json=json.dumps(
                {
                    "table_id": "tbl1",
                    "source_event_id": "evt-delay",
                    "actions": [{"record_id": "rec1", "action": "record_edited"}],
                },
                ensure_ascii=False,
            ),
        )
    )
    session.commit()

    response = client.get(f"/monitors/{seeded_monitor.id}/runs")

    assert response.status_code == 200
    assert "事件发生" in response.text
    assert "2026-05-28 11:29:54" in response.text
    assert "本地接收" in response.text
    assert "2026-05-28 11:38:11" in response.text
    assert "推送延迟" in response.text
    assert "8分17秒" in response.text


def test_delete_monitor_removes_monitor_and_related_data(client, session, seeded_bitable_monitor):
    from app.models import EventLog, SyncRun, TableJobLease, WorkerJob

    session.add(
        EventLog(
            event_id="evt-delete",
            monitor_id=seeded_bitable_monitor.id,
            event_type="drive.file.bitable_record_changed_v1",
            table_id="tbl1",
            raw_json="{}",
        )
    )
    session.add(
        SyncRun(
            monitor_id=seeded_bitable_monitor.id,
            trigger_type="event_incremental",
            status="success",
        )
    )
    session.add(
        WorkerJob(
            job_type="record_changed_incremental",
            monitor_id=seeded_bitable_monitor.id,
            status="queued",
        )
    )
    session.add(
        TableJobLease(
            monitor_id=seeded_bitable_monitor.id,
            table_id="tbl1",
            worker_id="worker-a",
            lease_expires_at=seeded_bitable_monitor.created_at,
        )
    )
    session.commit()

    response = client.post(
        f"/monitors/{seeded_bitable_monitor.id}/delete",
        follow_redirects=False,
    )

    from app.models import BitableTable, CurrentRecord, EventLog, Monitor, SyncRun, TableJobLease, WorkerJob

    assert response.status_code == 303
    assert response.headers["location"] == "/monitors"
    assert session.query(Monitor).count() == 0
    assert session.query(BitableTable).count() == 0
    assert session.query(CurrentRecord).count() == 0
    assert session.query(EventLog).count() == 0
    assert session.query(SyncRun).count() == 0
    assert session.query(WorkerJob).count() == 0
    assert session.query(TableJobLease).count() == 0


def test_delete_monitor_returns_404_for_missing_monitor(client):
    response = client.post("/monitors/999/delete", follow_redirects=False)

    assert response.status_code == 404
