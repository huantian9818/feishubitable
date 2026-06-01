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
        lambda interval_seconds=5.0, client=None: calls.append(("run_forever", interval_seconds, client)) or 0,
    )

    assert worker_main.main([]) == 0
    assert calls[0] == "init_db"
    assert calls[1][0] == "start_event_listener"
    assert calls[2][0] == "run_forever"
    assert calls[2][1] == 5.0
    assert calls[1][1] is calls[2][2]


def test_run_forever_logs_and_continues_after_job_error(monkeypatch):
    import worker.main as worker_main

    calls = []

    def fake_run_once(client=None):
        calls.append("run_once")
        raise RuntimeError("job failed")

    def stop_sleep(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(worker_main, "run_once", fake_run_once)
    monkeypatch.setattr(worker_main.time, "sleep", stop_sleep)

    assert worker_main.run_forever(interval_seconds=0.5) == 0
    assert calls == ["run_once"]
