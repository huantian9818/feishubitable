from datetime import datetime, timedelta


PRESET_INTERVALS = [360, 720, 1440, 4320]


def compute_next_fallback_at(anchor: datetime, minutes: int) -> datetime:
    return anchor + timedelta(minutes=minutes)
