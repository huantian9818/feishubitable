from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates

from app.schemas import DEFAULT_TIMEZONE

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
DISPLAY_TIMEZONE = ZoneInfo(DEFAULT_TIMEZONE)


def local_datetime(value: object) -> str:
    if value is None:
        return "-"
    if not isinstance(value, datetime):
        return str(value)

    if value.tzinfo is not None:
        return value.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    return value.strftime("%Y-%m-%d %H:%M:%S")


templates.env.filters["local_datetime"] = local_datetime
