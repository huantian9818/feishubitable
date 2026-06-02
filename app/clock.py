from datetime import datetime
from zoneinfo import ZoneInfo

from app.schemas import DEFAULT_TIMEZONE

SYSTEM_TIMEZONE = ZoneInfo(DEFAULT_TIMEZONE)


def system_now() -> datetime:
    return datetime.now(SYSTEM_TIMEZONE).replace(tzinfo=None)


def timestamp_ms_to_system_time(timestamp_ms: int | str) -> datetime:
    return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=SYSTEM_TIMEZONE).replace(tzinfo=None)
