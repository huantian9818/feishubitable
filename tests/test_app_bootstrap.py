import importlib
import sys

from fastapi.testclient import TestClient


def test_health_check_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_importing_app_main_does_not_initialize_default_db(monkeypatch):
    import app.db as db_module

    called = False

    def fake_init_db():
        nonlocal called
        called = True

    monkeypatch.setattr(db_module, "init_db", fake_init_db)
    sys.modules.pop("app.main", None)

    try:
        imported = importlib.import_module("app.main")
        assert imported.app is not None
        assert called is False
    finally:
        sys.modules.pop("app.main", None)


def test_create_app_can_skip_database_initialization(monkeypatch):
    import app.main as main_module

    called = False

    def fake_init_db():
        nonlocal called
        called = True

    monkeypatch.setattr(main_module, "init_db", fake_init_db)

    app = main_module.create_app(init_database=False)
    with TestClient(app) as test_client:
        response = test_client.get("/health")

    assert response.status_code == 200
    assert called is False
