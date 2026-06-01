import pytest


def test_main_initializes_db_and_starts_event_listener_before_forever_loop(monkeypatch):
    import worker.main as worker_main

    calls = []

    monkeypatch.setattr(worker_main, "init_db", lambda: calls.append("init_db"), raising=False)
    monkeypatch.setattr(
        worker_main,
        "start_event_listener",
        lambda client=None: calls.append(("start_event_listener", client)),
        raising=False,
    )
    monkeypatch.setattr(
        worker_main,
        "run_forever",
        lambda interval_seconds=5.0, client=None, worker_id=None: calls.append(
            ("run_forever", interval_seconds, client, worker_id)
        )
        or 0,
    )
    monkeypatch.setattr(worker_main.uuid, "uuid4", lambda: type("FixedUuid", (), {"hex": "worker-fixed"})())

    assert worker_main.main([]) == 0
    assert calls[0] == "init_db"
    assert calls[1][0] == "start_event_listener"
    assert calls[2][0] == "run_forever"
    assert calls[2][1] == 5.0
    assert calls[1][1] is calls[2][2]
    assert calls[2][3] == "worker-fixed"


def test_run_forever_logs_and_continues_after_job_error(monkeypatch):
    import worker.main as worker_main

    calls = []

    def fake_run_once(client=None, worker_id=None):
        calls.append("run_once")
        raise RuntimeError("job failed")

    def stop_sleep(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(worker_main, "run_once", fake_run_once)
    monkeypatch.setattr(worker_main.time, "sleep", stop_sleep)

    assert worker_main.run_forever(interval_seconds=0.5, worker_id="worker-a") == 0
    assert calls == ["run_once"]


def test_run_worker_cycle_passes_worker_id_to_job_runner(monkeypatch):
    import worker.main as worker_main

    calls = []

    monkeypatch.setattr(worker_main, "enqueue_due_fallback_jobs", lambda session: None)
    monkeypatch.setattr(
        worker_main,
        "run_next_job",
        lambda session, client, worker_id: calls.append(worker_id) or False,
    )

    assert worker_main.run_worker_cycle(client=object(), worker_id="worker-a") is False
    assert calls == ["worker-a"]


def test_main_can_disable_event_listener(monkeypatch):
    import worker.main as worker_main

    calls = []

    monkeypatch.setattr(worker_main, "init_db", lambda: calls.append("init_db"), raising=False)
    monkeypatch.setattr(
        worker_main,
        "start_event_listener",
        lambda client=None: calls.append("listener"),
        raising=False,
    )
    monkeypatch.setattr(
        worker_main,
        "run_forever",
        lambda interval_seconds=5.0, client=None, worker_id=None: calls.append(
            ("run_forever", interval_seconds, worker_id)
        )
        or 0,
        raising=False,
    )
    monkeypatch.setattr(worker_main.uuid, "uuid4", lambda: type("FixedUuid", (), {"hex": "worker-fixed"})())

    assert worker_main.main(["--no-listener"]) == 0
    assert calls[0] == "init_db"
    assert "listener" not in calls
    assert calls[1] == ("run_forever", 5.0, "worker-fixed")
