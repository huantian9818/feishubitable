def test_handle_payload_callback_logs_and_swallows_listener_errors(monkeypatch):
    from worker import event_listener

    events = []

    class DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(event_listener, "SessionLocal", lambda: DummySession())

    def raise_error(_session, _payload, _client):
        raise RuntimeError("boom")

    monkeypatch.setattr(event_listener, "handle_event_payload", raise_error)
    monkeypatch.setattr(event_listener.LOGGER, "exception", lambda message, *args: events.append((message, args)))

    event_listener._handle_payload({"header": {"event_id": "evt-1"}}, client=object())

    assert events
