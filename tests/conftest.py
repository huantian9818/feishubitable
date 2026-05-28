import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import create_sqlite_engine
import app.main as main_module
from app.models import Base, Monitor
from app.services.fallback_schedule import compute_next_fallback_at


@pytest.fixture
def session(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client(session):
    get_session = getattr(main_module, "get_session", None)
    if get_session is not None:
        main_module.app.dependency_overrides[get_session] = lambda: session

    try:
        yield TestClient(main_module.app)
    finally:
        main_module.app.dependency_overrides.clear()


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
