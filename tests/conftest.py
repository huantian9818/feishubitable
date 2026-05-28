import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import create_sqlite_engine
from app.main import create_app
from app.models import Base, Monitor
from app.services.fallback_schedule import compute_next_fallback_at
from app.web.dependencies import get_session


@pytest.fixture
def session(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client(session):
    app = create_app(init_database=False)
    app.dependency_overrides[get_session] = lambda: session

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client_no_raise(session):
    app = create_app(init_database=False)
    app.dependency_overrides[get_session] = lambda: session

    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def seeded_monitor(session):
    anchor = datetime(2026, 5, 28, 9, 0, 0)
    monitor = Monitor(
        name="测试监控源",
        source_url="https://example.feishu.cn/base/app_seeded",
        app_token="app_seeded",
        fallback_interval_minutes=360,
        next_fallback_sync_at=compute_next_fallback_at(anchor, 360),
    )
    session.add(monitor)
    session.commit()
    return monitor
