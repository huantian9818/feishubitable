from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.fallback_schedule import compute_next_fallback_at


def test_compute_next_fallback_at_uses_minutes_from_now():
    anchor = datetime(2026, 5, 28, 2, 0, 0, tzinfo=UTC).replace(tzinfo=None)

    assert compute_next_fallback_at(anchor, 360).isoformat(sep=" ") == "2026-05-28 08:00:00"


def test_monitor_defaults_start_in_pending_state(session):
    from app.models import Monitor

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/abc",
        app_token="abc",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    assert monitor.watch_status == "pending"
    assert monitor.subscription_status == "pending"
    assert monitor.sync_status == "never"


def test_current_record_requires_existing_bitable_table(session):
    from app.models import CurrentRecord, Monitor

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/abc",
        app_token="abc",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    session.add(
        CurrentRecord(
            monitor_id=monitor.id,
            table_id="tbl_missing",
            record_id="rec_123",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
