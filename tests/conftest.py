import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import create_sqlite_engine
from app.main import create_app
from app.models import Base, BitableTable, CurrentRecord, Monitor
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


@pytest.fixture
def seeded_bitable_monitor(session):
    anchor = datetime(2026, 5, 28, 9, 0, 0)
    monitor = Monitor(
        name="员工信息监控",
        source_url="https://example.feishu.cn/base/app_bitable",
        app_token="app_bitable",
        fallback_interval_minutes=360,
        next_fallback_sync_at=compute_next_fallback_at(anchor, 360),
        current_record_count=22,
    )
    session.add(monitor)
    session.flush()

    session.add_all(
        [
            BitableTable(
                monitor_id=monitor.id,
                table_id="tbl1",
                table_name="员工表",
            ),
            BitableTable(
                monitor_id=monitor.id,
                table_id="tbl2",
                table_name="资产表",
            ),
        ]
    )

    employee_rows = [
        CurrentRecord(
            monitor_id=monitor.id,
            table_id="tbl1",
            record_id=f"rec_{index:02d}",
            sort_order=index,
            fields_json='{"姓名":"员工%02d","部门":"研发","状态":"在职"}' % index,
            display_text=f"员工{index:02d} 研发 在职",
        )
        for index in range(1, 22)
    ]
    asset_row = CurrentRecord(
        monitor_id=monitor.id,
        table_id="tbl2",
        record_id="asset_01",
        sort_order=1,
        fields_json='{"资产编号":"NB-001","负责人":"员工01"}',
        display_text="NB-001 员工01",
    )
    session.add_all([*employee_rows, asset_row])
    session.commit()
    return monitor
