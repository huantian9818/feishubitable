from datetime import datetime, timedelta

from app.schemas import PRESET_FALLBACK_INTERVALS

PRESET_INTERVALS = PRESET_FALLBACK_INTERVALS


def compute_next_fallback_at(anchor: datetime, minutes: int) -> datetime:
    return anchor + timedelta(minutes=minutes)
